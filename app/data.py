"""Storage, validation, and optional historical archive retrieval."""
from __future__ import annotations
import csv, io, os, re, shutil
from datetime import date, datetime, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
# For Render paid services, attach a persistent disk and set POWERBALL_STORAGE_DIR
# to its mount point (e.g. /var/data). Without one, local files are ephemeral.
STORAGE_DIR = os.getenv('POWERBALL_STORAGE_DIR', '').strip()
BUNDLED_DATA = ROOT/'data'/'powerball_australia.csv'
DATA_FILE = Path(os.getenv('POWERBALL_DATA_FILE') or (str(Path(STORAGE_DIR)/'powerball_australia.csv') if STORAGE_DIR else str(BUNDLED_DATA)))
LEDGER_FILE = (Path(STORAGE_DIR)/'forecast_ledger.jsonl') if STORAGE_DIR else ROOT/'data'/'forecast_ledger.jsonl'


def ensure_data_file() -> None:
    if DATA_FILE.exists():
        return
    # Seed a newly attached disk from the original, audited historical file.
    if STORAGE_DIR and not os.getenv('POWERBALL_DATA_FILE'):
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with BUNDLED_DATA.open('rb') as src, DATA_FILE.open('xb') as dst:
            shutil.copyfileobj(src, dst)
    else:
        raise FileNotFoundError(f'No existe archivo histórico: {DATA_FILE}')

COLUMNS=['draw','date']+[f'n{i}' for i in range(1,8)]+['powerball']
MODERN_START=date(2018,4,19)
ARCHIVE='https://www.powerball.net/australia/archive/{year}'


def validate_row(row:dict)->dict:
    try:
        draw=int(row['draw']); day=date.fromisoformat(str(row['date']).strip())
        main=sorted(int(row[f'n{i}']) for i in range(1,8))
        pb=int(row['powerball'])
    except (ValueError,KeyError,TypeError) as exc:
        raise ValueError(f'Registro inválido: {row!r}: {exc}') from exc
    if draw<1144 or day<MODERN_START:
        raise ValueError(f'Formato anterior a 19-04-2018: {draw}')
    if day>date.today():raise ValueError(f'Sorteo con fecha futura: {day}')
    if day.weekday()!=3:raise ValueError(f'El sorteo {draw} no tiene fecha jueves')
    expected_day=MODERN_START+timedelta(weeks=draw-1144)
    if day!=expected_day:raise ValueError(f'Fecha {day} no corresponde al número de sorteo {draw}; se esperaba {expected_day}')
    if len(main)!=7 or len(set(main))!=7 or not all(1<=v<=35 for v in main):
        raise ValueError(f'Números principales inválidos en sorteo {draw}')
    if pb<1 or pb>20:raise ValueError(f'Powerball inválida en sorteo {draw}')
    return {'draw':draw,'date':day.isoformat(),'main':main,'powerball':pb}


def parse_csv(text:str)->list[dict]:
    # Tolerate BOM, CRLF, semicolon-separated files and 8-ball regular CSVs.
    if not text.strip():raise ValueError('Archivo vacío')
    try: dialect=csv.Sniffer().sniff(text[:2048],delimiters=',;\t')
    except csv.Error: dialect=csv.excel
    rows=list(csv.DictReader(io.StringIO(text.lstrip('\ufeff')), dialect=dialect))
    if not rows:raise ValueError('CSV sin registros')
    required=set(COLUMNS)
    if not required.issubset(set(rows[0])):
        raise ValueError('Columnas requeridas: '+', '.join(COLUMNS))
    out=[validate_row(row) for row in rows]
    return dedupe(out)


def dedupe(rows:list[dict])->list[dict]:
    byid={}; byday={}
    for row in rows:
        draw=row['draw']; day=row['date']
        if draw in byid and byid[draw]!=row:
            raise ValueError(f'Conflicto de datos para el sorteo {draw}')
        if day in byday and byday[day]!=row:
            raise ValueError(f'Conflicto de datos para el día {day}')
        byid[draw]=row;byday[day]=row
    return sorted(byid.values(),key=lambda x:(x['date'],x['draw']))


def load_draws()->list[dict]:
    ensure_data_file()
    return parse_csv(DATA_FILE.read_text(encoding='utf-8'))


def save_draws(rows:list[dict])->None:
    DATA_FILE.parent.mkdir(parents=True,exist_ok=True)
    buffer=io.StringIO();w=csv.writer(buffer);w.writerow(COLUMNS)
    for row in dedupe(rows):w.writerow([row['draw'],row['date'],*row['main'],row['powerball']])
    tmp=DATA_FILE.with_suffix('.tmp');tmp.write_text(buffer.getvalue(),encoding='utf-8');tmp.replace(DATA_FILE)


def merge_draws(current:list[dict],incoming:list[dict]):
    old={r['draw']:r for r in current}
    updates=[]
    for row in incoming:
        if row['draw'] in old and old[row['draw']]!=row:
            raise ValueError(f'Conflicto en sorteo {row["draw"]}. No se reemplazó el histórico.')
        if row['draw'] not in old:updates.append(row)
    merged=dedupe(current+incoming)
    return merged,len(updates)

MONTHS={s:i for i,s in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
DATE_RESULTS=re.compile(
  r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
  r'(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})\s*[-–—]\s*Draw\s+(\d{4})\s+'
  r'((?:\d{1,2}\s+){7}\d{1,2})(?=\s|$)',re.I)


def parse_archive(html:str)->list[dict]:
    """Strictly parse compact archived results from powerball.net; fail closed if changed."""
    soup=BeautifulSoup(html,'html.parser')
    for bad in soup(['script','style']):bad.decompose()
    text=soup.get_text(' ',strip=True).replace('\xa0',' ')
    out=[]
    for month,day,year,draw,numbers in DATE_RESULTS.findall(text):
        vals=[int(v) for v in numbers.split()]
        try:
            dt=date(int(year),MONTHS[month.capitalize()],int(day))
            rec=validate_row({'draw':draw,'date':dt.isoformat(),
                    **{f'n{i+1}':vals[i] for i in range(7)},'powerball':vals[7]})
            out.append(rec)
        except ValueError as exc:
            # pre-modern rows legitimately appear in 2018; keep only new-matrix draws
            if int(draw)<1144:continue
            raise ValueError(f'Sorteo {draw}: {exc}') from exc
    return dedupe(out)


def fetch_archives(years:list[int],timeout:float=12.0)->dict:
    # No silent partial success: surface year-by-year errors to user for review.
    found=[];logs=[]
    for yr in sorted(set(years)):
        if not 2018<=yr<=date.today().year:
            logs.append({'year':yr,'status':'error','message':'Año fuera de rango'});continue
        try:
            r=requests.get(ARCHIVE.format(year=yr),headers={'User-Agent':'Mozilla/5.0 (Powerball Quant Research; public statistics)'},timeout=timeout)
            r.raise_for_status()
            parsed=[d for d in parse_archive(r.text) if int(d['date'][:4])==yr]
            if len(parsed)<5:raise ValueError('El formato HTML cambió o no se encontraron suficientes resultados verificables')
            found.extend(parsed)
            logs.append({'year':yr,'status':'ok','count':len(parsed)})
        except (requests.RequestException,ValueError) as exc:
            logs.append({'year':yr,'status':'error','message':str(exc)[:240]})
    return {'rows':dedupe(found),'log':logs,'source':'powerball.net/australia/archive/{year}'}
