"""V3: independent tests of chronological safeguards, validity and endpoints."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app import advanced, data, engine
from app.server import app

HIST=data.load_draws()


def test_candidate_probabilities_are_normalized():
    y,pb=engine.arrays(HIST)
    q,r=advanced.build_forecasts(y,pb)
    assert q.shape==(444,len(advanced.CANDIDATES),35)
    assert r.shape==(444,len(advanced.CANDIDATES),20)
    assert (q>=0).all() and (q<=1).all()
    assert (r>=0).all() and (r<=1).all()
    assert np.allclose(q.sum(axis=2),7)
    assert np.allclose(r.sum(axis=2),1)


def test_no_access_to_a_future_draw():
    y,pb=engine.arrays(HIST)
    changed=y.copy();bp=pb.copy()
    changed[125:]=np.roll(y[125:],4,axis=1)
    bp[125:]=(bp[125:]+9)%20
    for model in (advanced.empirical_bayes,advanced.regime_guard):
        q0,p0=model(y,pb,125)
        q1,p1=model(changed,bp,125)
        assert np.allclose(q0,q1)
        assert np.allclose(p0,p1)
    q,r=advanced.build_forecasts(y,pb)
    qc,rc=advanced.build_forecasts(changed,bp)
    assert np.allclose(q[:126],qc[:126])
    assert np.allclose(r[:126],rc[:126])


def test_v3_validation_cannot_see_holdout():
    y,pb=engine.arrays(HIST)
    yr,ty,vi,ti=advanced._years(HIST)
    assert (yr,ty,len(vi),len(ti))==(2025,2026,52,41)
    q,p=advanced.build_forecasts(y,pb)
    a=advanced.tuned_ensemble(y,pb,q,p,vi)
    changed=y.copy(); bp=pb.copy()
    changed[ti]=np.roll(changed[ti],1,axis=1)
    bp[ti]=(bp[ti]+5)%20
    qc,pc=advanced.build_forecasts(changed,bp)
    b=advanced.tuned_ensemble(changed,bp,qc,pc,vi)
    assert a['main_config']==b['main_config']
    assert a['pb_config']==b['pb_config']
    assert np.allclose(a['q'][ti[0]],b['q'][ti[0]])
    assert np.allclose(a['r'][ti[0]],b['r'][ti[0]])
    assert np.allclose(a['main_weights'][ti[0]],b['main_weights'][ti[0]])


def test_dynamic_weights_react_only_to_previous_losses():
    rng=np.random.default_rng(10)
    x=rng.random((90,7))
    w=advanced.dynamic_weights(x,400,26)
    changed=x.copy();changed[60:]+=3
    wc=advanced.dynamic_weights(changed,400,26)
    assert np.allclose(w[:61],wc[:61])
    assert np.allclose(w.sum(axis=1),1)
    assert np.all(w[:,0]>=.65-1e-12)


def test_edge_report_outputs_valid_analysis():
    r=advanced.edge_report(HIST,seed=10,bootstrap=300)
    assert r['legacy_selected']['main']=='win13_k100'
    assert r['test_draws']==41
    assert len(r['rows'])==5
    assert len(r['timeline'])==41
    assert len(r['main_forecast'])==35 and len(r['pb_forecast'])==20
    assert np.isclose(sum(a['ensemble'] for a in r['main_forecast']),7)
    assert np.isclose(sum(a['ensemble'] for a in r['pb_forecast']),1)
    assert sum(v['n'] for v in r['calibration'])==41*35
    for row in r['rows'][1:]:
        assert np.isfinite(row['brier_ci']['simultaneous_ci95']).all()
        assert np.isfinite(row['pb_ci']['simultaneous_ci95']).all()
    assert r['forecast_for']=={'draw':1587,'date':'2026-10-15'}


def test_regime_scan_respects_permuted_draws_and_is_reproducible():
    a=advanced.regime_scan(HIST,reps=150,seed=72)
    b=advanced.regime_scan(HIST,reps=150,seed=72)
    assert a==b
    for typ in ('main','powerball'):
        assert 0<a[typ]['p_value']<=1
        assert a[typ]['p_adjusted_2tests']>=a[typ]['p_value']


def test_fair_null_calibration_is_reproducible_and_counts_correctly():
    a=advanced.fair_null_calibration(HIST,reps=30,seed=90)
    b=advanced.fair_null_calibration(HIST,reps=30,seed=90)
    assert a==b
    assert len(a['samples'])==30
    assert 0<a['main']['p_fair_null']<=1
    assert 0<a['powerball']['p_fair_null']<=1


def test_ledger_cannot_overwrite_and_validates_hash(tmp_path:Path):
    report=advanced.edge_report(HIST,bootstrap=300)
    report['forecast_for']={'draw':9999,'date':(datetime.now(timezone.utc).date()+timedelta(days=14)).isoformat()}
    path=tmp_path/'ledger.jsonl'
    saved=advanced.lock_forecast(HIST,path,report)
    assert saved['sha256']
    entries=advanced.ledger_entries(path,HIST)
    assert len(entries)==1 and entries[0]['hash_valid'] and not entries[0]['resolved']
    with pytest.raises(ValueError,match='sellada'):
        advanced.lock_forecast(HIST,path,report)
    text=path.read_text()
    path.write_text(text.replace('adaptive_ensemble','uniform'))
    assert not advanced.ledger_entries(path,HIST)[0]['hash_valid']


def test_ticket_pair_fair_odds_are_identical():
    report=advanced.edge_report(HIST,bootstrap=300)
    r=advanced.ticket_comparison(report,seed=300)
    assert r['fair_jackpot_odds']==134490400
    for key in ('uniform','ensemble'):
        assert len(r[key]['main'])==7 and len(set(r[key]['main']))==7
        assert all(1<=v<=35 for v in r[key]['main'])
        assert 1<=r[key]['pb']<=20


def test_pair_scan_corrects_search_across_all_595_pairs():
    a=advanced.pair_scan(HIST,reps=130,seed=10)
    b=advanced.pair_scan(HIST,reps=130,seed=10)
    assert a==b
    assert a['tested_pairs']==595
    assert 0<a['p_familywise']<=1
    assert len(a['extremes'])==12
    assert np.isclose(a['expected_per_pair'],len(HIST)*42/(35*34))


def test_advanced_api_endpoints():
    c=TestClient(app)
    assert c.get('/api/edge').status_code==200
    assert c.get('/api/audit').json()['missing_draw_ids']==[]
    assert c.get('/api/ledger').json()['entries']==[]
    assert c.get('/api/edge-export').headers['content-disposition'].startswith('attachment;')
    assert c.post('/api/regimes',json={'reps':100}).status_code==200
    assert c.post('/api/regimes',json={'reps':10}).status_code==422
    assert c.post('/api/edge-tickets',json={'seed':5}).status_code==200
    assert c.post('/api/pairs',json={'reps':100}).status_code==200
    r=c.post('/api/edge-null',json={'reps':30})
    assert r.status_code==200 and len(r.json()['samples'])==30
