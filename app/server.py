"""Powerball Quant Lab: Python statistical API + standalone frontend."""
from __future__ import annotations
from datetime import date
from functools import lru_cache
from collections import Counter
import json
from threading import Lock
from pathlib import Path
from typing import Optional
import os
from fastapi import FastAPI, HTTPException, Body, Query, Request, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app import data,engine,advanced

app=FastAPI(title='Powerball Quant Lab',version='3.0.0',description='Research-only models for Australia Powerball.')
ROOT=Path(__file__).resolve().parent
LEDGER_FILE=data.LEDGER_FILE
app.add_middleware(GZipMiddleware, minimum_size=1024)
ledger_mutex=Lock()

@lru_cache(maxsize=4)
def computed_edge(size:int,mtime:int):
    return advanced.edge_report(draws())
app.mount('/static',StaticFiles(directory=str(ROOT/'static')),name='static')

def check_write_access(request:Request):
    if os.getenv('POWERBALL_READ_ONLY','').lower() in ('1','true','yes'):
        raise HTTPException(403, 'Instancia pública en modo lectura. Configura almacenamiento persistente y desactiva POWERBALL_READ_ONLY para guardar cambios.')
    token=os.getenv('POWERBALL_ADMIN_TOKEN')
    if token:
        import secrets
        if not secrets.compare_digest(request.headers.get('X-Admin-Token',''),token):
            raise HTTPException(403,'Se requiere POWERBALL_ADMIN_TOKEN para modificar el histórico')
    elif request.client is None or request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'Edición restringida a localhost. Configure POWERBALL_ADMIN_TOKEN en un servidor público.')

class SimRequest(BaseModel):
    ticket:list[int]
    powerball:int
    n:int=Field(default=10000,ge=1,le=300000)
    seed:Optional[int]=None

class GenerateRequest(BaseModel):
    model:str='uniform'
    seed:Optional[int]=None

class TestRequest(BaseModel):
    year:Optional[int]=None
    reps:int=Field(default=2000,ge=100,le=10000)
    seed:int=42

class PairRequest(BaseModel):
    reps:int=Field(default=1000,ge=100,le=4000)
    seed:int=612

class NullRequest(BaseModel):
    reps:int=Field(default=100,ge=30,le=300)
    seed:int=444

class RegimeRequest(BaseModel):
    reps:int=Field(default=450,ge=100,le=2500)
    seed:int=390

class UpdateRequest(BaseModel):
    start_year:int=2018
    end_year:Optional[int]=None


def draws():
    try: return data.load_draws()
    except Exception as exc:raise HTTPException(500,str(exc))

@app.get('/')
def index():return FileResponse(ROOT/'static'/'index.html')

@app.get('/api/meta')
def meta():
    d=draws()
    years=sorted({int(r['date'][:4]) for r in d})
    return {'app':'Powerball Quant Lab','n':len(d),'years':years,
            'start':d[0]['date'],'end':d[-1]['date'],
            'models':{key:entry[0] for key,entry in engine.MODELS.items()},
            'advanced_models':advanced.LABELS,
            'jackpot_odds':engine.JACKPOT_ODDS,
            'source':'Powerball.net / Australia, archivos 2018–2026; fuente secundaria contrastable',
            'rules':'Powerball Australia, formato vigente desde sorteo 1144 · 2018-04-19',
            'storage':('persistent_directory' if data.STORAGE_DIR else ('ephemeral' if os.getenv('RENDER') else 'local')),
            'read_only':os.getenv('POWERBALL_READ_ONLY','').lower() in ('1','true','yes')}

@app.get('/api/overview')
def overview(year:Optional[int]=None):
    d=draws()
    if year:d=[r for r in d if int(r['date'][:4])==year]
    try:return engine.overview(d)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/history')
def history(year:Optional[int]=None,limit:int=Query(default=40,ge=1,le=1000)):
    d=draws()
    if year:d=[r for r in d if int(r['date'][:4])==year]
    return {'total':len(d),'draws':list(reversed(d[-limit:]))}

@app.get('/api/backtest')
def backtest():
    try:return engine.backtest(draws())
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/model-comparison')
def model_comparison():
    try:return engine.compare_all_models(draws())
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/ranking')
def ranking(model:str='uniform'):
    try:return engine.model_ranking(draws(),model)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/tests')
def tests(req:TestRequest, request: Request):
    if os.getenv('RENDER') and req.reps>2000:
        raise HTTPException(422,'En Render se permiten hasta 2.000 réplicas por solicitud para controlar uso de CPU')
    d=draws()
    if req.year:d=[r for r in d if int(r['date'][:4])==req.year]
    try:return engine.null_tests(d,req.reps,req.seed)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/simulate')
def simulate(req:SimRequest, request: Request):
    if os.getenv('RENDER') and req.n>100000:
        raise HTTPException(422,'En Render se permiten hasta 100.000 sorteos por solicitud para controlar uso de CPU')
    try:return engine.simulate_ticket(req.ticket,req.powerball,req.n,req.seed)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/generate')
def generate(req:GenerateRequest):
    try:return engine.generate_ticket(draws(),req.model,req.seed)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/import')
def import_csv(csv_text:str=Body(...,media_type='text/plain'),_access=Depends(check_write_access)):
    if len(csv_text)>2_000_000:raise HTTPException(413,'CSV excede 2 MB')
    try:
        incoming=data.parse_csv(csv_text)
        merged,created=data.merge_draws(draws(),incoming)
        data.save_draws(merged)
        return {'added':created,'total':len(merged),'message':'Importación validada y guardada'}
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/update')
def update(req:UpdateRequest,_access=Depends(check_write_access)):
    years=list(range(req.start_year,(req.end_year or date.today().year)+1))
    if not years or len(years)>12:raise HTTPException(400,'Selecciona máximo 12 años válidos')
    result=data.fetch_archives(years)
    if not result['rows']:
        return {'added':0,'total':len(draws()),'logs':result['log'],'message':'No se añadieron sorteos. Puedes importar un CSV.'}
    try:
        merged,added=data.merge_draws(draws(),result['rows'])
        data.save_draws(merged)
        return {'added':added,'total':len(merged),'logs':result['log'],'message':'Actualización completada con los años válidos'}
    except ValueError as exc:raise HTTPException(409,str(exc))

@app.get('/api/download')
def download():
    data.ensure_data_file()
    return FileResponse(data.DATA_FILE,filename='powerball_australia.csv',media_type='text/csv')

@app.get('/api/health')
def health():return {'ok':True,'draws':len(draws())}


@app.get('/api/edge')
def edge():
    data.ensure_data_file()
    st=data.DATA_FILE.stat()
    try:return computed_edge(st.st_size,st.st_mtime_ns)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/regimes')
def regimes(req:RegimeRequest,_access=Depends(check_write_access)):
    try:return advanced.regime_scan(draws(),req.reps,req.seed)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/edge-null')
def edge_null(req:NullRequest,_access=Depends(check_write_access)):
    try:return advanced.fair_null_calibration(draws(),req.reps,req.seed)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/audit')
def audit():
    data.ensure_data_file()
    from hashlib import sha256
    d=draws()
    years=dict(sorted(Counter(x['date'][:4] for x in d).items()))
    missing=[i for i in range(d[0]['draw'],d[-1]['draw']+1) if i not in {x['draw'] for x in d}]
    return {'n':len(d),'first':d[0]['date'],'last':d[-1]['date'],
            'first_draw':d[0]['draw'],'last_draw':d[-1]['draw'],
            'sha256':sha256(data.DATA_FILE.read_bytes()).hexdigest(),
            'missing_draw_ids':missing, 'years':years,
            'validation':'Reglas, fecha semanal, duplicados, numeración y rangos (automática).',
            'source':'powerball.net/australia/archive/{year} · fuente secundaria',
            'limitation':'La coincidencia de las cifras con el operador oficial NO se ha verificado registro por registro.'}

@app.get('/api/ledger')
def ledger():
    try:return {'entries':advanced.ledger_entries(LEDGER_FILE,draws())}
    except (ValueError,KeyError) as exc:raise HTTPException(400,str(exc))

@app.post('/api/ledger/lock')
def lock_ledger(_access=Depends(check_write_access)):
    with ledger_mutex:
        try:return advanced.lock_forecast(draws(),LEDGER_FILE,edge())
        except ValueError as exc:raise HTTPException(409,str(exc))

@app.post('/api/edge-tickets')
def edge_tickets(req:GenerateRequest):
    try:return advanced.ticket_comparison(edge(),req.seed)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/edge-export')
def export_edge():
    result=edge()
    return JSONResponse(result,headers={'Content-Disposition':'attachment; filename="powerball_analisis_v3.json"'})


@app.post('/api/pairs')
def pairs(req:PairRequest,_access=Depends(check_write_access)):
    try:return advanced.pair_scan(draws(),req.reps,req.seed)
    except ValueError as exc:raise HTTPException(400,str(exc))
