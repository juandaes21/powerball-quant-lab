"""V3 prequential research. No model uses draw t when forecasting t.

Empirical Bayes is a conservative partial-pooling approximation, not an
exact physical-lottery posterior. Model-selection is restricted to the year
preceding the held-out final year. Fair-null resampling repeats this process.
"""
from __future__ import annotations
from datetime import date, datetime, timezone, timedelta
from hashlib import sha256
from math import log
from typing import Any
import json
import numpy as np
from scipy.stats import beta
from app import engine

CANDIDATES = ('uniform','all_k100','win13_k100','win52_k100','ewm26_k100','empirical_bayes','regime_guard')
ALL = ('uniform','v2_selected','empirical_bayes','regime_guard','adaptive_ensemble')
LABELS = {'uniform':'Uniforme · referencia','v2_selected':'Mejor v2 según 2025',
          'empirical_bayes':'Bayes empírico · pooling','regime_guard':'Detector adaptativo · conservador',
          'adaptive_ensemble':'Ensemble online · peso uniforme ≥65%'}
MAIN_ETAS=(0.,100.,400.)
PB_ETAS=(0.,.5,2.)
WINDOWS=(26,52,104)


def empirical_bayes(y:np.ndarray,pb:np.ndarray,at:int)->tuple[np.ndarray,np.ndarray]:
    """Approximate James–Stein shrinkage on 35 and 20 class marginals.

    A shared excess-variance estimate learns the shrinkage (0 <= a <= .6).
    Formula assumes exchangeable latent marginal deviations and is a
    *working model*; it does not assert independent within-draw selections.
    """
    q0=np.full(35,.2);r0=np.full(20,.05)
    if at<52:return q0,r0
    f=y[:at].mean(axis=0)
    h=np.bincount(pb[:at],minlength=20)/at
    def shrink(f,base,var):
        sampling=var/at
        excess=max(0.,float(np.mean((f-base)**2))-sampling)
        alpha=min(.6,excess/(excess+4*sampling)) if excess else 0.
        return base+alpha*(f-base)
    return shrink(f,.2,.16),shrink(h,.05,.0475)


def regime_guard(y:np.ndarray,pb:np.ndarray,at:int)->tuple[np.ndarray,np.ndarray]:
    """Conservative exploratory time-variation heuristic with fixed gate.

    Strong within-history change required; 52 recent vs preceding 104.
    Output pulled toward fair null. Gate is NOT a validated physical bias test.
    """
    if at<104:return np.full(35,.2),np.full(20,.05)
    older=y[max(0,at-156):at-52];recent=y[at-52:at]
    op=np.bincount(pb[max(0,at-156):at-52],minlength=20)/len(older)
    rp=np.bincount(pb[at-52:at],minlength=20)/52
    def shift(a,b,null,var):
        z=float(np.max(np.abs(b-a)/np.sqrt(var*(1/len(older)+1/52))))
        lam=min(.35,max(0.,(z-3.2)/5))
        return null+lam*(b-null)
    return shift(older.mean(axis=0),recent.mean(axis=0),.2,.16),shift(op,rp,.05,.0475)


def build_forecasts(y:np.ndarray,pb:np.ndarray):
    """Forecast arrays index t trained on [0,t), including t=N next draw."""
    n=len(y); k=len(CANDIDATES)
    qm=np.zeros((n+1,k,35)); pr=np.zeros((n+1,k,20))
    for t in range(n+1):
        for j,name in enumerate(CANDIDATES):
            if name=='empirical_bayes':q,r=empirical_bayes(y,pb,t)
            elif name=='regime_guard':q,r=regime_guard(y,pb,t)
            else:q,r=engine.predict(y,pb,t,name)
            qm[t,j]=q;pr[t,j]=r
    # Every forecast is a valid set of inclusion marginals, not a joint law.
    assert np.allclose(qm.sum(axis=2),7,atol=1e-8)
    assert np.allclose(pr.sum(axis=2),1,atol=1e-8)
    return qm,pr


def basic_losses(y,pb,qm,pr):
    main=np.mean((qm[:-1]-y[:,None,:])**2,axis=2)
    pbloss=-np.log(np.maximum(np.take_along_axis(pr[:-1],pb[:,None,None].repeat(pr.shape[1],axis=1),axis=2).squeeze(-1),1e-12))
    return main,pbloss


def dynamic_weights(loss:np.ndarray,eta:float,window:int,floor:float=.65):
    """At t, scores only use losses of draws <t; uniform retains floor."""
    n,k=loss.shape
    weights=np.zeros((n+1,k),dtype=float)
    weights[:,0]=1.
    for t in range(26,n+1):
        recent=loss[max(0,t-window):t].mean(axis=0)
        rel=recent[1:]-recent[0]
        raw=-eta*rel
        raw-=raw.max()
        z=np.exp(raw);z/=z.sum()
        weights[t,:]=np.r_[floor,(1-floor)*z]
    return weights


def tuned_ensemble(y,pb,qm,pr,validation_indices):
    mainloss,pbloss=basic_losses(y,pb,qm,pr)
    options_main=[]; options_pb=[]
    for window in WINDOWS:
        for eta in MAIN_ETAS:
            w=dynamic_weights(mainloss,eta,window)
            q=np.einsum('tk,tkj->tj',w,qm)
            sc=float(np.mean((q[validation_indices]-y[validation_indices])**2))
            options_main.append((sc,window,eta,w,q))
        for eta in PB_ETAS:
            w=dynamic_weights(pbloss,eta,window)
            r=np.einsum('tk,tkj->tj',w,pr)
            sc=float(-np.log(np.maximum(r[validation_indices,pb[validation_indices]],1e-12)).mean())
            options_pb.append((sc,window,eta,w,r))
    bestm=min(options_main,key=lambda z:(z[0],z[1],z[2]))
    bestp=min(options_pb,key=lambda z:(z[0],z[1],z[2]))
    return {'q':bestm[4],'r':bestp[4], 'main_weights':bestm[3], 'pb_weights':bestp[3],
            'main_config':{'window':bestm[1],'eta':bestm[2],'validation_brier':bestm[0]},
            'pb_config':{'window':bestp[1],'eta':bestp[2],'validation_logloss':bestp[0]}}


def _years(draws):
    ys=sorted({int(d['date'][:4]) for d in draws})
    if len(ys)<3:raise ValueError('Se requieren al menos tres años históricos')
    from collections import Counter
    yc=Counter(int(d['date'][:4]) for d in draws)
    valid_years=[year for year in ys if yc[year]>=10]
    if len(valid_years)<2:raise ValueError('Se requieren al menos dos años con diez sorteos')
    val,test=valid_years[-2:]
    vi=np.array([i for i,d in enumerate(draws) if int(d['date'][:4])==val and i>=104],dtype=int)
    ti=np.array([i for i,d in enumerate(draws) if int(d['date'][:4])==test and i>=104],dtype=int)
    if len(vi)<10 or len(ti)<10:raise ValueError('Muestra de validación/prueba demasiado corta')
    return val,test,vi,ti


def _legacy(y,pb,vi,ti):
    models=list(engine.MODELS)
    scoresm={k:engine._evaluate(y,pb,vi,k)['brier'] for k in models}
    scoresp={k:engine._evaluate(y,pb,vi,k)['pb_logloss'] for k in models}
    bm=min(models,key=lambda k:scoresm[k]);bpbest=min(models,key=lambda k:scoresp[k])
    # Only forecast selected models over held-out dates; no test-based selection.
    at=np.r_[vi,ti,len(y)]
    q={int(t):engine.predict(y,pb,int(t),bm)[0] for t in at}
    r={int(t):engine.predict(y,pb,int(t),bpbest)[1] for t in at}
    return bm,bpbest,q,r


def _candidate_result(draws,include_legacy=True):
    y,pb=engine.arrays(draws)
    vy,ty,vi,ti=_years(draws)
    qm,pr=build_forecasts(y,pb)
    dyn=tuned_ensemble(y,pb,qm,pr,vi)
    m={'uniform':qm[:,0,:], 'empirical_bayes':qm[:,CANDIDATES.index('empirical_bayes'),:],
       'regime_guard':qm[:,CANDIDATES.index('regime_guard'),:], 'adaptive_ensemble':dyn['q']}
    p={'uniform':pr[:,0,:], 'empirical_bayes':pr[:,CANDIDATES.index('empirical_bayes'),:],
       'regime_guard':pr[:,CANDIDATES.index('regime_guard'),:], 'adaptive_ensemble':dyn['r']}
    chosen={}
    if include_legacy:
        bm,bpbest,lm,lp=_legacy(y,pb,vi,ti)
        # fill only required entries, no early model usage
        mq=np.tile(np.full(35,.2),(len(y)+1,1))
        rp=np.tile(np.full(20,.05),(len(y)+1,1))
        for t,q in lm.items():mq[t]=q
        for t,r in lp.items():rp[t]=r
        m['v2_selected']=mq;p['v2_selected']=rp
        chosen={'main':bm,'pb':bpbest}
    keys=[k for k in ALL if k in m]
    sm={key:np.mean((m[key][ti]-y[ti])**2,axis=1) for key in keys}
    sp={key:-np.log(np.maximum(p[key][ti,pb[ti]],1e-12)) for key in keys}
    return locals()


def _intervals(diff:np.ndarray,reps:int,seed:int,block:int=4):
    """Rows = candidate improvements, columns = holdout draws. Simultaneous
    studentized max-|error| bootstrap. Exploratory in small holdouts.
    """
    rng=np.random.default_rng(seed)
    n=diff.shape[1]
    starts=rng.integers(0,n,(reps,int(np.ceil(n/block))))
    ix=(starts[:,:,None]+np.arange(block)[None,None,:])%n
    ix=ix.reshape(reps,-1)[:,:n]
    boot=diff[:,ix].mean(axis=2).T
    obs=diff.mean(axis=1)
    se=boot.std(axis=0,ddof=1)
    den=np.maximum(se,1e-12)
    z=np.abs((boot-obs[None,:])/den[None,:])
    critical=float(np.quantile(z.max(axis=1),.95))
    out=[]
    lo=np.quantile(boot,.025,axis=0);hi=np.quantile(boot,.975,axis=0)
    for j in range(len(obs)):
        out.append({'mean':float(obs[j]),'ci95':[float(lo[j]),float(hi[j])],
                    'simultaneous_ci95':[float(obs[j]-critical*se[j]),float(obs[j]+critical*se[j])]})
    return out


def edge_report(draws:list[dict],seed:int=229,bootstrap:int=2200):
    z=_candidate_result(draws)
    y,pb,vi,ti=z['y'],z['pb'],z['vi'],z['ti']
    m,p,sm,sp=z['m'],z['p'],z['sm'],z['sp']
    keys=z['keys']
    base_m=np.full(len(ti),.16)
    base_p=np.full(len(ti),np.log(20))
    rows=[]
    main_ix=[i for i,k in enumerate(keys) if k!='uniform']
    mainci=_intervals(np.vstack([base_m-sm[keys[j]] for j in main_ix]),bootstrap,seed)
    pbci=_intervals(np.vstack([base_p-sp[keys[j]] for j in main_ix]),bootstrap,seed+1)
    by_key_m={keys[j]:v for j,v in zip(main_ix,mainci)}
    by_key_p={keys[j]:v for j,v in zip(main_ix,pbci)}
    for key in keys:
        entry={'key':key,'label':LABELS[key],
               'brier':float(sm[key].mean()),'pb_logloss':float(sp[key].mean()),
               'brier_gain':float((base_m-sm[key]).mean()),
               'pb_gain':float((base_p-sp[key]).mean())}
        if key!='uniform':
            entry.update({'brier_ci':by_key_m[key], 'pb_ci':by_key_p[key]})
        else:entry.update({'brier_ci':{'ci95':[0,0],'simultaneous_ci95':[0,0]},
                           'pb_ci':{'ci95':[0,0],'simultaneous_ci95':[0,0]}})
        rows.append(entry)
    timeline=[{'draw':int(draws[t]['draw']),'date':draws[t]['date'],
               'uniform_brier':.16,'ensemble_brier':float(sm['adaptive_ensemble'][i]),
               'brier_cumulative_gain':float(np.sum(base_m[:i+1]-sm['adaptive_ensemble'][:i+1])),
               'pb_cumulative_gain':float(np.sum(base_p[:i+1]-sp['adaptive_ensemble'][:i+1]))}
              for i,t in enumerate(ti)]
    forecast=z['dyn'];latest=len(y)
    top_main=[];top_pb=[]
    ebm=m['empirical_bayes'][latest]; ebr=p['empirical_bayes'][latest]
    # Separate per-number Beta(20,80) / Beta(5,95) reference posterior.
    # These are marginal credible intervals conditional on a FIXED K=100 prior,
    # NOT uncertainty intervals for the empirical-Bayes shrinkage estimator,
    # and NOT simultaneous bounds over all numbers.
    cnt=y.sum(axis=0)
    pcnt=np.bincount(pb,minlength=20)
    ciq=beta.ppf(np.array([.05,.95])[:,None],cnt[None,:]+20,(len(y)-cnt)[None,:]+80)
    cir=beta.ppf(np.array([.05,.95])[:,None],pcnt[None,:]+5,(len(y)-pcnt)[None,:]+95)
    for i in range(35):
        top_main.append({'number':i+1,'fair':.2,'eb':float(ebm[i]),
                         'ensemble':float(m['adaptive_ensemble'][latest,i]),
                         'band90':[float(ciq[0,i]),float(ciq[1,i])]})
    for i in range(20):
        top_pb.append({'number':i+1,'fair':.05,'eb':float(ebr[i]),
                       'ensemble':float(p['adaptive_ensemble'][latest,i]),
                       'band90':[float(cir[0,i]),float(cir[1,i])]})
    # Reliability buckets based only on forecast p, never on outcomes.
    pred=m['adaptive_ensemble'][ti].ravel(); actual=y[ti].ravel()
    edges=np.quantile(pred,[0,.2,.4,.6,.8,1.]);cal=[]
    for j in range(5):
        mask=(pred>=edges[j])&((pred<=edges[j+1]) if j==4 else (pred<edges[j+1]))
        if mask.any():cal.append({'bucket':j+1,'predicted':float(pred[mask].mean()),
                                  'observed':float(actual[mask].mean()),'n':int(mask.sum())})
    return {'validation_year':z['vy'],'test_year':z['ty'],'validation_draws':len(vi),'test_draws':len(ti),
            'holdout_start':draws[int(ti[0])]['date'],'holdout_end':draws[int(ti[-1])]['date'],
            'rows':rows,'timeline':timeline,'calibration':cal,
            'ensemble':{'main':forecast['main_config'],'pb':forecast['pb_config'],
                        'main_weights':dict(zip(CANDIDATES,[float(v) for v in forecast['main_weights'][latest]])),
                        'pb_weights':dict(zip(CANDIDATES,[float(v) for v in forecast['pb_weights'][latest]]))},
            'legacy_selected':z['chosen'],'main_forecast':top_main,'pb_forecast':top_pb,
            'interval_note':'Intervalos marginales Beta(20,80) y Beta(5,95) con K=100 fijo; NO son intervalos del modelo Bayes empírico y NO están corregidos por 35/20 comparaciones.',
            'forecast_for':{'draw':draws[-1]['draw']+1,'date':(date.fromisoformat(draws[-1]['date'])+timedelta(days=7)).isoformat()},
            'methodology':'Prequential: predecir t usando solamente sorteos anteriores; seleccionar parámetros del ensemble en año de validación; evaluar en año siguiente. Intervalos simultáneos exploratorios por bootstrap pareado circular de 4 sorteos sobre alternativas. Intervalos marginales Beta con prior fija K=100 (no del estimador EB); NO se han corregido por comparaciones múltiples ni demuestran probabilidades físicas.'}


def regime_scan(draws:list[dict],reps:int=450,seed:int=390,min_segment:int=52):
    """Max over all allowable splits; permutes full draws to test temporal exchangeability.
    Not a test of fairness and not an estimator of physical changes.
    """
    if not 100<=reps<=2500:raise ValueError('Réplicas entre 100 y 2500')
    y,pb=engine.arrays(draws)
    n=len(y)
    if n<2*min_segment+1:raise ValueError('Insuficientes sorteos para probar cambios de régimen')
    x=np.eye(20)[pb]
    splits=np.arange(min_segment,n-min_segment+1)
    aa=splits[:,None];bb=(n-splits)[:,None]
    def maximum(seq,var):
        c=np.cumsum(seq,axis=0)
        mu_l=c[splits-1]/aa
        mu_r=(c[-1]-c[splits-1])/bb
        s=np.sum((mu_l-mu_r)**2 / (var*(1/aa+1/bb)),axis=1)
        loc=int(np.argmax(s));return float(s[loc]),int(splits[loc])
    m,mi=maximum(y,.16);p,pi=maximum(x,.0475)
    rng=np.random.default_rng(seed); exceed_m=exceed_p=0
    for _ in range(reps):
        ix=rng.permutation(n)
        exceed_m+=maximum(y[ix],.16)[0]>=m
        exceed_p+=maximum(x[ix],.0475)[0]>=p
    rawm=(exceed_m+1)/(reps+1);rawp=(exceed_p+1)/(reps+1)
    return {'n':n,'reps':reps,'main':{'stat':m,'split_index':mi,'first_after_split':draws[mi]['date'],
            'p_value':rawm,'p_adjusted_2tests':min(1.,2*rawm)},
            'powerball':{'stat':p,'split_index':pi,'first_after_split':draws[pi]['date'],
            'p_value':rawp,'p_adjusted_2tests':min(1.,2*rawp)},
            'interpretation':'Permutar la secuencia de sorteos enteros mantiene frecuencias y coocurrencias y calibra la búsqueda del mejor punto de cambio; prueba estabilidad temporal (no uniformidad), con Bonferroni para dos familias. Fechas candidatas no demuestran cambios físicos.'}


def _null_maxgain(draws):
    z=_candidate_result(draws,include_legacy=False)
    bm=np.full(len(z['ti']),.16); bp=np.full(len(z['ti']),np.log(20))
    keys=('empirical_bayes','regime_guard','adaptive_ensemble')
    return max(float((bm-z['sm'][k]).mean()) for k in keys),max(float((bp-z['sp'][k]).mean()) for k in keys)


def fair_null_calibration(draws:list[dict],reps:int=100,seed:int=444):
    """A full fair-game placebo re-fits and tunes the v3 pipeline per trial.

    Selection of the best among the 3 advanced candidate families on the
    holdout is likewise repeated in every placebo. Legacy v2 excluded.
    """
    if not 30<=reps<=300:raise ValueError('Réplicas entre 30 y 300')
    observed_main,observed_pb=_null_maxgain(draws)
    rng=np.random.default_rng(seed)
    exceed_main=exceed_pb=0
    samples=[]
    for j in range(reps):
        simulated=[]
        for d in draws:
            main=np.sort(rng.choice(np.arange(1,36),7,replace=False)).tolist()
            simulated.append({'main':main,'powerball':int(rng.integers(1,21)),
                              'draw':d['draw'],'date':d['date']})
        gm,gp=_null_maxgain(simulated)
        exceed_main+=gm>=observed_main
        exceed_pb+=gp>=observed_pb
        samples.append([gm,gp])
    return {'reps':reps,'main':{'observed_best_gain':observed_main,'p_fair_null':(exceed_main+1)/(reps+1)},
            'powerball':{'observed_best_gain':observed_pb,'p_fair_null':(exceed_pb+1)/(reps+1)},
            'samples':samples,
            'interpretation':'Simula loterías perfectamente justas y repite selección del ensemble usando validación. Compara la mejor mejora EN EL HOLDOUT de tres candidatos avanzados. Es exploratorio; no incluye la búsqueda anterior de v2 ni otras hipótesis intentadas.'}


def ledger_entries(path,draws):
    lookup={d['draw']:d for d in draws}
    if not path.exists():return []
    out=[]
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        rec=json.loads(line)
        d=lookup.get(rec['target_draw'])
        verified={k:v for k,v in rec.items() if k!='sha256'}
        digest=sha256(json.dumps(verified,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        entry={**rec,'hash_valid':digest==rec.get('sha256'),'resolved':d is not None}
        if d is not None:
            q=np.array(rec['main_probs']); r=np.array(rec['pb_probs'])
            y=np.zeros(35);y[np.array(d['main'])-1]=1
            entry['result']={'main':d['main'],'powerball':d['powerball'],
                'brier':float(np.mean((y-q)**2)),'uniform_brier':.16,
                'pb_logloss':float(-log(max(r[d['powerball']-1],1e-12))),
                'uniform_pb_logloss':float(log(20)),
                'top7_matches':len(set(d['main'])&set(np.argsort(-q)[:7]+1))}
        out.append(entry)
    return out


def lock_forecast(draws,path,report):
    target=report['forecast_for'];target_date=date.fromisoformat(target['date'])
    # Conservative restriction: no snapshots from the date of the draw onward.
    if target_date<=datetime.now(timezone.utc).date():
        raise ValueError('El siguiente sorteo ya es hoy o pasó según UTC: no se permite registrar a posteriori.')
    if any(e['target_draw']==target['draw'] for e in ledger_entries(path,draws)):
        raise ValueError('Ya existe una predicción sellada para este sorteo; no se sobrescribe.')
    content={'target_draw':target['draw'],'target_date':target['date'],
        'created_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'history_last_draw':draws[-1]['draw'], 'history_last_date':draws[-1]['date'],
        'model':'adaptive_ensemble','main_config':report['ensemble']['main'],
        'pb_config':report['ensemble']['pb'],
        'main_probs':[v['ensemble'] for v in report['main_forecast']],
        'pb_probs':[v['ensemble'] for v in report['pb_forecast']],
        'disclaimer':'Predicción bloqueada para auditoría, no demuestra una ventaja real.'}
    payload=json.dumps(content,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    content['sha256']=sha256(payload.encode()).hexdigest()
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(content,ensure_ascii=False)+'\n')
    return content


def ticket_comparison(report:dict,seed:int|None=None):
    """Purely experimental weighted sample vs uniformly sampled ticket.

    Weighted without-replacement sampling does not reproduce exact specified
    inclusion marginals, nor does it establish an improved jackpot chance.
    """
    rng=np.random.default_rng(seed)
    q=np.array([v['ensemble'] for v in report['main_forecast']],dtype=float)
    p=np.array([v['ensemble'] for v in report['pb_forecast']],dtype=float)
    weighted=np.sort(rng.choice(np.arange(1,36),size=7,replace=False,p=q/q.sum()))
    random=np.sort(rng.choice(np.arange(1,36),size=7,replace=False))
    return {'ensemble':{'main':weighted.astype(int).tolist(),
                       'pb':int(rng.choice(np.arange(1,21),p=p/p.sum()))},
            'uniform':{'main':random.astype(int).tolist(),
                       'pb':int(rng.integers(1,21))},
            'fair_jackpot_odds':engine.JACKPOT_ODDS,
            'warning':'Las dos combinaciones tienen la misma probabilidad de jackpot bajo un sorteo justo; el muestreo ponderado no es una ley conjunta calibrada.'}


def pair_scan(draws:list[dict],reps:int=1000,seed:int=612):
    """Calibrates the most extreme of ALL 595 pairs, under uniform 7-of-35.

    A familywise max statistic avoids treating the pair selected for having
    the largest deviation as if it had been specified in advance.
    """
    if not 100<=reps<=4000:raise ValueError('Réplicas entre 100 y 4.000')
    n=len(draws)
    if n<15:raise ValueError('Se requieren al menos quince sorteos')
    a,b=np.triu_indices(35,1)
    i,j=np.triu_indices(7,1)
    def occurrences(picks):
        # All 21 unordered pairs for each 7-number draw, vectorized.
        x=np.minimum(picks[:,i],picks[:,j])*35+np.maximum(picks[:,i],picks[:,j])
        mat=np.bincount(x.reshape(-1),minlength=35*35).reshape(35,35)
        return mat[a,b]
    historical=np.array([r['main'] for r in draws],dtype=int)-1
    counts=occurrences(historical)
    probability=(7*6)/(35*34)
    expected=n*probability
    std=float(np.sqrt(n*probability*(1-probability)))
    deviation=(counts-expected)/std
    max_observed=float(np.max(np.abs(deviation)))
    rng=np.random.default_rng(seed);larger=0
    for _ in range(reps):
        picks=np.argpartition(rng.random((n,35)),6,axis=1)[:,:7]
        sim=occurrences(picks)
        larger+=float(np.max(np.abs(sim-expected))/std)>=max_observed
    strongest=np.argsort(-np.abs(deviation))[:12]
    return {'n':n,'reps':reps,'tested_pairs':len(counts),'expected_per_pair':float(expected),
            'max_abs_z':max_observed,'p_familywise':(larger+1)/(reps+1),
            'extremes':[{'a':int(a[k])+1,'b':int(b[k])+1,'count':int(counts[k]),
                         'z':float(deviation[k])} for k in strongest],
            'interpretation':'P global del máximo absoluto entre 595 pares frente a 7 bolas de 35 sin reemplazo. Una desviación no implica que el par tenga más probabilidad el próximo sorteo.'}
