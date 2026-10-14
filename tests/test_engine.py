from __future__ import annotations
from datetime import date
from math import comb
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app import data,engine
from app.server import app

HIST=data.load_draws()


def test_historical_integrity():
    assert len(HIST)==443
    assert HIST[0]['draw']==1144 and HIST[-1]['draw']==1586
    assert all(HIST[i]['draw']+1==HIST[i+1]['draw'] for i in range(len(HIST)-1))
    assert all(len(set(d['main']))==7 for d in HIST)


def test_uniform_probabilities():
    y,pb=engine.arrays(HIST)
    q,r=engine.predict(y,pb,len(HIST),'uniform')
    assert np.allclose(q,0.2) and np.allclose(r,.05)
    assert np.isclose(q.sum(),7) and np.isclose(r.sum(),1)
    assert engine.JACKPOT_ODDS == comb(35,7)*20 == 134490400


def test_models_are_marginally_calibrated():
    y,pb=engine.arrays(HIST)
    for model in engine.MODELS:
        q,r=engine.predict(y,pb,len(HIST),model)
        assert np.all((q>=0)&(q<=1))
        assert np.all((r>=0)&(r<=1))
        assert np.isclose(q.sum(),7)
        assert np.isclose(r.sum(),1)


def test_no_future_data_leakage():
    y,pb=engine.arrays(HIST)
    flipped=y.copy(); flipped[100:]=np.roll(flipped[100:],1,axis=1)
    pbf=pb.copy();pbf[100:]=(pbf[100:]+3)%20
    for k in engine.MODELS:
        before=engine.predict(y,pb,100,k)
        after=engine.predict(flipped,pbf,100,k)
        assert np.allclose(before[0],after[0])
        assert np.allclose(before[1],after[1])


def test_walk_forward_selection_metrics():
    b=engine.backtest(HIST,bootstrap=200)
    assert b['years']=={'validation':2025,'test':2026}
    assert b['counts']=={'validation':52,'test':41}
    assert b['selected_main']==min(engine.MODELS,key=lambda k:b['validation'][k]['brier'])
    assert b['selected_pb']==min(engine.MODELS,key=lambda k:b['validation'][k]['pb_logloss'])
    assert np.isclose(b['test']['uniform']['brier'],.16)


def test_prize_probabilities():
    p=engine.theoretical_division_probs()
    assert len(p)==9
    assert np.isclose(p[0],1/134490400)
    assert 1/45<sum(p)<1/43
    m=np.array([7,7,6,6,5,4,5,3,2,1]);b=np.array([1,0,1,0,1,1,0,1,1,1],dtype=bool)
    assert engine.prize_division(m,b).tolist()==list(range(9))+[-1]


def test_simulation_total_and_consistency():
    r=engine.simulate_ticket([3,8,12,17,21,29,34],12,5000,seed=20)
    assert sum(r['hits'])==5000
    assert sum(r['freq'])==7*5000
    assert sum(r['pb_freq'])==5000
    assert sum(r['divisions'])==r['prizes']
    assert r['jackpots']==r['divisions'][0]
    with pytest.raises(ValueError):engine.simulate_ticket([1,1,2,3,4,5,6],1,10)


def test_valid_archive_parser_and_premodern_rejection():
    html='''<html><body><div>December 28th 2023 - Draw 1441 9 11 15 16 24 27 35 1 ›</div><div>April 12th 2018 - Draw 1143 14 16 18 31 32 33 17 3 ›</div></body></html>'''
    parsed=data.parse_archive(html)
    assert len(parsed)==1 and parsed[0]['draw']==1441
    a=dict(parsed[0]);a['draw']=1143;a['date']='2018-04-12'
    with pytest.raises(ValueError):data.validate_row({'draw':a['draw'],'date':a['date'],**{f'n{i+1}':a['main'][i] for i in range(7)},'powerball':a['powerball']})


def test_merging_conflicts():
    rows,created=data.merge_draws(HIST,HIST[:5])
    assert created==0 and len(rows)==443
    x=dict(HIST[0]);x['powerball']=x['powerball']+1
    with pytest.raises(ValueError):data.merge_draws(HIST,[x])


def test_fastapi_endpoints():
    client=TestClient(app)
    assert client.get('/').status_code==200
    assert client.get('/static/app.js').status_code==200
    assert client.get('/api/health').json()['draws']==443
    assert client.get('/api/overview').json()['n']==443
    assert client.get('/api/ranking?model=uniform').json()['top_pb']==1
    r=client.post('/api/simulate',json={'ticket':[1,2,3,4,5,6,7],'powerball':11,'n':100,'seed':4})
    assert r.status_code==200 and r.json()['n']==100
    assert client.post('/api/simulate',json={'ticket':[1,2,3,4,5,6,6],'powerball':11,'n':100}).status_code==400
    assert client.get('/api/download').status_code==200


def test_comparison_all_models_and_cis():
    result=engine.compare_all_models(HIST,bootstrap=750,seed=77)
    assert (result['validation_year'],result['test_year'])==(2025,2026)
    assert result['test_draws']==41
    for metric in ('brier','pb_logloss'):
        rows=result['metrics'][metric]
        assert len(rows)==17
        assert {r['key'] for r in rows}==set(engine.MODELS)
        baseline=next(r for r in rows if r['key']=='uniform')
        assert np.isclose(baseline['gain_vs_uniform'],0,atol=1e-12)
        assert np.isclose(baseline['test_score'],.16 if metric=='brier' else np.log(20))
        assert baseline['simultaneous_ci95']==[0.0,0.0]
        for row in rows:
            assert np.isclose(row['gain_vs_uniform'],baseline['test_score']-row['test_score'])
            lo,hi=row['simultaneous_ci95']
            assert lo<=hi and np.isfinite([lo,hi]).all()
            assert row['beats_uniform']==(lo>0)
    assert result['selected_main']==engine.backtest(HIST,bootstrap=100)['selected_main']


def test_comparison_is_reproducible_and_api():
    a=engine.compare_all_models(HIST,bootstrap=600,seed=888)
    b=engine.compare_all_models(HIST,bootstrap=600,seed=888)
    assert a==b
    client=TestClient(app)
    res=client.get('/api/model-comparison')
    assert res.status_code==200
    assert len(res.json()['metrics']['brier'])==17
