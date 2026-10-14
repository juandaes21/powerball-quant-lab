"""Probability models and Monte Carlo methods for Powerball AU (draw 1144+).

All ticket combinations remain equiprobable under the fair lottery null.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import comb, log, sqrt
from typing import Optional
import numpy as np
from scipy.stats import hypergeom, norm

MAIN_MAX, MAIN_PICK, PB_MAX = 35, 7, 20
JACKPOT_ODDS = comb(MAIN_MAX, MAIN_PICK) * PB_MAX
MODELS = {
    "uniform": ("Uniforme · referencia", "uniform", None, None),
    "all_k25": ("Toda la historia · K=25", "all", None, 25),
    "all_k100": ("Toda la historia · K=100", "all", None, 100),
    "all_k300": ("Toda la historia · K=300", "all", None, 300),
    "win13_k25": ("Ventana 13 · K=25", "window", 13, 25),
    "win13_k100": ("Ventana 13 · K=100", "window", 13, 100),
    "win13_k300": ("Ventana 13 · K=300", "window", 13, 300),
    "win26_k100": ("Ventana 26 · K=100", "window", 26, 100),
    "win52_k25": ("Ventana 52 · K=25", "window", 52, 25),
    "win52_k100": ("Ventana 52 · K=100", "window", 52, 100),
    "win52_k300": ("Ventana 52 · K=300", "window", 52, 300),
    "win104_k100": ("Ventana 104 · K=100", "window", 104, 100),
    "ewm13_k25": ("Exponencial 13 · K=25", "ewm", 13, 25),
    "ewm13_k100": ("Exponencial 13 · K=100", "ewm", 13, 100),
    "ewm13_k300": ("Exponencial 13 · K=300", "ewm", 13, 300),
    "ewm26_k100": ("Exponencial 26 · K=100", "ewm", 26, 100),
    "ewm52_k100": ("Exponencial 52 · K=100", "ewm", 52, 100),
}


def arrays(draws: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Binary inclusion matrix (n,35), Powerball zero-based class (n,)."""
    y = np.zeros((len(draws), 35), dtype=np.float64)
    for i, d in enumerate(draws):
        y[i, np.asarray(d['main'], dtype=int)-1] = 1
    pb = np.asarray([d['powerball']-1 for d in draws], dtype=np.int64)
    return y, pb


def predict(y: np.ndarray, pb: np.ndarray, at: int, model_id: str) -> tuple[np.ndarray, np.ndarray]:
    """Forecast draw at index `at` using strictly earlier draws only."""
    if model_id not in MODELS:
        raise ValueError("Modelo desconocido")
    _, kind, value, strength = MODELS[model_id]
    q0, r0 = np.full(35, .2), np.full(20, .05)
    if kind == 'uniform' or at == 0:
        return q0, r0
    if kind == 'window':
        start = max(0, at-int(value))
        history, prev = y[start:at], pb[start:at]
        weights = np.ones(len(prev))
    elif kind == 'ewm':
        history, prev = y[:at], pb[:at]
        weights = np.exp2(-np.arange(at-1, -1, -1, dtype=float)/float(value))
    else:
        history, prev = y[:at], pb[:at]
        weights = np.ones(at)
    mass = float(weights.sum())
    cnt = np.dot(weights, history)
    pcnt = np.bincount(prev, weights=weights, minlength=20)
    # Historical 7-of-35 *marginal* inclusions, not independent picks.
    q = (cnt + float(strength)*.2)/(mass+float(strength))
    r = (pcnt + float(strength)*.05)/(mass+float(strength))
    return q, r


def model_ranking(draws: list[dict], model_id: str):
    y, pb = arrays(draws)
    q, r = predict(y, pb, len(draws), model_id)
    return {"model": model_id, "label": MODELS[model_id][0],
            "main": [round(float(t), 7) for t in q],
            "pb": [round(float(t), 7) for t in r],
            "top_main": [int(i)+1 for i in np.argsort(-q, kind='stable')[:7]],
            "top_pb": int(np.argmax(r))+1}


def _evaluate(y, pb, idx, model):
    bs, ll, hs = [], [], []
    for t in idx:
        q, r = predict(y, pb, t, model)
        bs.append(np.mean((y[t]-q)**2))
        ll.append(-log(max(float(r[pb[t]]), 1e-12)))
        hs.append(y[t, np.argsort(-q)[:7]].sum())
    return {
        'brier': float(np.mean(bs)), 'pb_logloss': float(np.mean(ll)),
        'top7_matches': float(np.mean(hs)), 'draw_count': len(idx),
        'per_draw_brier': [float(v) for v in bs],
        'per_draw_pb_logloss': [float(v) for v in ll],
    }


def backtest(draws: list[dict], seed: int=171, bootstrap: int=1500):
    y, pb = arrays(draws)
    if len(draws)<60:
        raise ValueError('Se requieren al menos 60 sorteos para el backtest')
    years = sorted({int(d['date'][:4]) for d in draws})
    if len(years)<3:
        raise ValueError('Se necesitan al menos 3 años distintos para validación cronológica')
    from collections import Counter
    yc=Counter(int(d['date'][:4]) for d in draws)
    usable=[year for year in years if yc[year]>=10]
    if len(usable)<2:raise ValueError('Se necesitan dos años con al menos diez sorteos')
    valid_year, test_year = usable[-2:]
    val_idx = [i for i,d in enumerate(draws) if int(d['date'][:4])==valid_year and i>=26]
    test_idx= [i for i,d in enumerate(draws) if int(d['date'][:4])==test_year and i>=26]
    if len(val_idx)<10 or len(test_idx)<10:
        raise ValueError('Se requieren al menos diez sorteos de validación y diez de prueba')
    validation = {k:_evaluate(y,pb,val_idx,k) for k in MODELS}
    testing = {k:_evaluate(y,pb,test_idx,k) for k in MODELS}
    # Choices are based on validation ONLY; holdout is never consulted for model selection.
    best_main = min(MODELS, key=lambda k: validation[k]['brier'])
    best_pb = min(MODELS, key=lambda k: validation[k]['pb_logloss'])
    def ci(model, key, null):
        rng=np.random.default_rng(seed)
        diff=np.array(testing[null][key])-np.array(testing[model][key])
        means=np.mean(diff[rng.integers(0,len(diff),(bootstrap,len(diff)))], axis=1)
        return [round(float(v),9) for v in np.quantile(means,[.025,.975])]
    summary = {
        'years': {'validation':valid_year,'test':test_year},
        'counts': {'validation':len(val_idx),'test':len(test_idx)},
        'selected_main':best_main, 'selected_pb':best_pb,
        'main_gain_vs_uniform': float(testing['uniform']['brier']-testing[best_main]['brier']),
        'pb_gain_vs_uniform':float(testing['uniform']['pb_logloss']-testing[best_pb]['pb_logloss']),
        'main_gain_ci95':ci(best_main,'per_draw_brier','uniform'),
        'pb_gain_ci95':ci(best_pb,'per_draw_pb_logloss','uniform'),
        'validation':{k:{x:v for x,v in a.items() if not x.startswith('per_draw')} for k,a in validation.items()},
        'test':{k:{x:v for x,v in a.items() if not x.startswith('per_draw')} for k,a in testing.items()},
        'models':{k:MODELS[k][0] for k in MODELS},
        'parameters':{k:{'family':v[1],'lookback_or_halflife':v[2],'k':v[3]} for k,v in MODELS.items()},
        'rule':'Selección SOLO en el año de validación; reporte del año posterior fuera de selección',
    }
    return summary


def null_tests(draws: list[dict], reps: int=2000, seed: int=42):
    """Monte Carlo exact game mechanism for global frequency and max-deviation tests."""
    if not 100<=reps<=10000:
        raise ValueError('Las réplicas deben estar entre 100 y 10.000')
    n=len(draws)
    if n<2: raise ValueError('Se requieren al menos 2 sorteos')
    y,pb=arrays(draws)
    a=y.sum(axis=0); b=np.bincount(pb,minlength=20)
    ea, eb=n*.2, n*.05
    obs_a=float(((a-ea)**2/ea).sum()); obs_b=float(((b-eb)**2/eb).sum())
    obs_max=float(np.max(abs(a-ea)/sqrt(n*.2*.8)))
    rng=np.random.default_rng(seed)
    far_a=far_b=far_max=0
    bs=min(40,max(1,200000//max(35*n,1)))
    for start in range(0,reps,bs):
        batch=min(bs,reps-start)
        selected=np.argpartition(rng.random((batch,n,35)),6,axis=2)[:,:,:7]
        counts=np.zeros((batch,35), dtype=np.int32)
        np.add.at(counts,(np.repeat(np.arange(batch),n*7),selected.ravel()),1)
        chi=((counts-ea)**2/ea).sum(axis=1)
        zs=np.max(abs(counts-ea)/sqrt(n*.2*.8),axis=1)
        powers=rng.integers(0,20,size=(batch,n))
        pcounts=np.zeros((batch,20),dtype=np.int32)
        np.add.at(pcounts,(np.repeat(np.arange(batch),n),powers.ravel()),1)
        chip=((pcounts-eb)**2/eb).sum(axis=1)
        far_a+=int((chi>=obs_a).sum());far_max+=int((zs>=obs_max).sum());far_b+=int((chip>=obs_b).sum())
    return {
        'reps':reps,'n':n,
        'main':{'chi2':obs_a,'p_value':(far_a+1)/(reps+1),'max_z':obs_max,'p_max_z':(far_max+1)/(reps+1)},
        'pb':{'chi2':obs_b,'p_value':(far_b+1)/(reps+1)},
        'meaning':'Un valor p alto no demuestra uniformidad; uno bajo exige replicación en muestras nuevas.'
    }


def overview(draws: list[dict]):
    if not draws:raise ValueError('Sin sorteos en el período')
    y,pb=arrays(draws)
    n=len(draws)
    f=y.sum(axis=0).astype(int).tolist()
    p=np.bincount(pb,minlength=20).astype(int).tolist()
    sums=[sum(d['main']) for d in draws]
    odds=[sum(v%2 for v in d['main']) for d in draws]
    overlaps=[len(set(a['main'])&set(b['main'])) for a,b in zip(draws[:-1],draws[1:])]
    theo_overlap=[float(hypergeom.pmf(k,35,7,7)) for k in range(8)]
    bins=list(range(45,211,15))
    observed_hist=np.histogram(sums,bins=[0]+bins+[246])[0].tolist()
    # Fair 7-of-35 sum simulated with stable seed as a visual reference.
    rng=np.random.default_rng(311)
    u=np.argpartition(rng.random((40000,35)),6,axis=1)[:,:7]+1
    theoretical_hist=(np.histogram(u.sum(axis=1),bins=[0]+bins+[246])[0]/40000*n).tolist()
    return {'n':n,'first':draws[0]['date'],'last':draws[-1]['date'],
            'first_draw':draws[0]['draw'],'last_draw':draws[-1]['draw'],
            'freq':f,'pb_freq':p,'expected_main':.2*n,'expected_pb':.05*n,
            'sum':{'observed_mean':float(np.mean(sums)),'expected_mean':126,
                   'observed_sd':float(np.std(sums,ddof=1)) if n>1 else 0,
                   'edges':['<45']+[f'{bins[i]}–{bins[i+1]-1}' for i in range(len(bins)-1)]+['210+'],
                   'observed':observed_hist,'expected':theoretical_hist},
            'odd':{'observed':np.bincount(odds,minlength=8).tolist(),
                   'expected':(hypergeom.pmf(np.arange(8),35,18,7)*n).tolist()},
            'overlap':{'observed':np.bincount(overlaps,minlength=8).tolist(),
                       'expected':(np.asarray(theo_overlap)*len(overlaps)).tolist(),
                       'observed_mean':float(np.mean(overlaps)) if overlaps else None,
                       'expected_mean':1.4},
            'theoretical_odds':JACKPOT_ODDS,
            'top_main': [int(i)+1 for i in np.argsort(-np.array(f))[:7]],
            'top_pb':[int(i)+1 for i in np.argsort(-np.array(p))[:5]],
            }


def prize_division(main_matches: np.ndarray, pb_matches: np.ndarray) -> np.ndarray:
    out=np.full(len(main_matches),-1, dtype=int)
    for count,pb,division in [(7,True,0),(7,False,1),(6,True,2),(6,False,3),
                              (5,True,4),(4,True,5),(5,False,6),(3,True,7),(2,True,8)]:
        out[(main_matches==count)&(pb_matches==pb)]=division
    return out


def theoretical_division_probs():
    denom=comb(35,7)
    result=[]
    for m,p in [(7,True),(7,False),(6,True),(6,False),(5,True),(4,True),(5,False),(3,True),(2,True)]:
        chance=comb(7,m)*comb(28,7-m)/denom * (1/20 if p else 19/20)
        result.append(chance)
    return result


def simulate_ticket(ticket: list[int], powerball: int, n: int=10000, seed: Optional[int]=None):
    if len(ticket)!=7 or len(set(ticket))!=7 or any(v<1 or v>35 for v in ticket):
        raise ValueError('Se requieren 7 números únicos entre 1 y 35')
    if not 1<=powerball<=20:raise ValueError('Powerball debe estar entre 1 y 20')
    if not 1<=n<=300000:raise ValueError('Sorteos entre 1 y 300.000')
    rng=np.random.default_rng(seed)
    nums=np.array(ticket)-1
    hit=np.zeros(8,dtype=int);div=np.zeros(9,dtype=int);freq=np.zeros(35,dtype=int);pf=np.zeros(20,dtype=int)
    for start in range(0,n,5000):
        k=min(n-start,5000)
        d=np.argpartition(rng.random((k,35)),6,axis=1)[:,:7]
        powers=rng.integers(1,21,size=k)
        counts=np.isin(d,nums).sum(axis=1)
        good=powers==powerball
        hit+=np.bincount(counts,minlength=8)
        cats=prize_division(counts,good)
        div+=np.bincount(cats[cats>=0],minlength=9)
        freq+=np.bincount(d.ravel(),minlength=35)
        pf+=np.bincount(powers-1,minlength=20)
    theo=theoretical_division_probs()
    return {'n':n,'ticket':sorted(ticket),'powerball':powerball,
            'hits':hit.tolist(),'divisions':div.tolist(),'prizes':int(div.sum()),
            'jackpots':int(div[0]),'freq':freq.tolist(),'pb_freq':pf.tolist(),
            'expected_divisions':[float(n*v) for v in theo],
            'theoretical_any_prize':float(sum(theo)),
            'jackpot_prob_at_least_once':float(-np.expm1(n*np.log1p(-1/JACKPOT_ODDS)))}


def generate_ticket(draws: list[dict], model_id: str='uniform', seed:Optional[int]=None):
    rng=np.random.default_rng(seed)
    probs=model_ranking(draws,model_id)
    q=np.asarray(probs['main']);p=np.asarray(probs['pb'])
    # Sampling 7 without replacement using shrinkage-derived relative weights.
    # These are NOT true posterior combo win probabilities.
    selected=np.sort(rng.choice(np.arange(1,36),size=7,replace=False,p=q/q.sum()))
    power=int(rng.choice(np.arange(1,21),p=p/p.sum()))
    return {'ticket':selected.astype(int).tolist(),'powerball':power,
            'model':model_id,'label':probs['label'],'fair_jackpot_odds':JACKPOT_ODDS,
            'warning':'La combinación no ha demostrado una mayor probabilidad real de ganar.'}


def compare_all_models(draws: list[dict], bootstrap: int=1800, seed: int=171, block: int=4):
    """Paired, blocked bootstrap on the fixed final-year holdout, all 17 models.

    Selection takes place only during the prior year. These are *retrospective*
    post-selection comparisons; pointwise CIs are exploratory. Simultaneous CIs
    control the bootstrap maximum standardized error among 16 alternatives.
    """
    if not 500 <= bootstrap <= 10000:
        raise ValueError('bootstrap entre 500 y 10.000')
    y,pb=arrays(draws)
    years=sorted({int(r['date'][:4]) for r in draws})
    if len(years)<3:raise ValueError('Se requieren al menos tres años')
    from collections import Counter
    yc=Counter(int(d['date'][:4]) for d in draws)
    usable=[year for year in years if yc[year]>=10]
    if len(usable)<2:raise ValueError('Se necesitan dos años con al menos diez sorteos')
    val_year,test_year=usable[-2:]
    val_idx=[i for i,d in enumerate(draws) if int(d['date'][:4])==val_year and i>=26]
    test_idx=[i for i,d in enumerate(draws) if int(d['date'][:4])==test_year and i>=26]
    if len(val_idx)<10 or len(test_idx)<10:raise ValueError('No hay suficientes sorteos fuera de muestra')
    # Compute each prediction once for the full holdout (no training on the future).
    scores=np.empty((len(MODELS),len(test_idx),2),dtype=float)
    labels=list(MODELS)
    for j,model in enumerate(labels):
        for tpos,t in enumerate(test_idx):
            q,r=predict(y,pb,t,model)
            scores[j,tpos,0]=float(np.mean((y[t]-q)**2))
            scores[j,tpos,1]=-float(np.log(max(r[pb[t]],1e-12)))
    val={k:_evaluate(y,pb,val_idx,k) for k in labels}
    uniform_i=labels.index('uniform')
    improvements=scores[uniform_i:uniform_i+1,:,:]-scores
    n=len(test_idx)
    rng=np.random.default_rng(seed)
    nblocks=int(np.ceil(n/block))
    starts=rng.integers(0,n,(bootstrap,nblocks))
    offsets=np.arange(block)
    samples=((starts[:,:,None]+offsets[None,None,:])%n).reshape(bootstrap,-1)[:,:n]
    empirical=improvements.mean(axis=1)
    boot=improvements[:,samples,:].mean(axis=2).transpose(1,0,2)  # (B,model,metric)
    lo=np.quantile(boot,.025,axis=0);hi=np.quantile(boot,.975,axis=0)
    se=boot.std(axis=0,ddof=1)
    std=np.maximum(se,1e-12)
    z=np.abs((boot[:,1:,:]-empirical[None,1:,:])/std[None,1:,:])
    critical=np.quantile(z.max(axis=1),.95,axis=0)
    sim_lo=empirical-critical[None,:]*se
    sim_hi=empirical+critical[None,:]*se
    sim_lo[uniform_i]=0;sim_hi[uniform_i]=0
    bymetric={}
    for mi,metric in enumerate(['brier','pb_logloss']):
        records=[]
        for j,key in enumerate(labels):
            records.append({
                'key':key,'label':MODELS[key][0], 'family':MODELS[key][1],
                'window_or_halflife':MODELS[key][2],'k':MODELS[key][3],
                'validation_score':float(val[key][metric]),
                'test_score':float(scores[j,:,mi].mean()),
                'gain_vs_uniform':float(empirical[j,mi]),
                'ci95':[float(lo[j,mi]),float(hi[j,mi])],
                'simultaneous_ci95':[float(sim_lo[j,mi]),float(sim_hi[j,mi])],
                'beats_uniform': bool(sim_lo[j,mi]>0),
            })
        bymetric[metric]=records
    main_choice=min(labels,key=lambda k:val[k]['brier'])
    pb_choice=min(labels,key=lambda k:val[k]['pb_logloss'])
    return {
        'validation_year':val_year,'test_year':test_year,
        'validation_draws':len(val_idx),'test_draws':n,'bootstrap_samples':bootstrap,
        'block_size':block,'selected_main':main_choice,'selected_pb':pb_choice,
        'metrics':bymetric,
        'interpretation': 'Ganancia = error uniforme - error del modelo. Positivo mejora. IC95 simultáneos son exploratorios, con bootstrap por bloques y corrección por comparación de todos los modelos; no prueban sesgo físico ni garantizan ventaja futura.',
    }
