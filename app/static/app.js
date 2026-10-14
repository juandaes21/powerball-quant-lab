'use strict';
const $=id=>document.getElementById(id);
const num=x=>Number(x).toLocaleString('es-CO');
const dec=(x,n=4)=>Number(x).toLocaleString('es-CO',{minimumFractionDigits:n,maximumFractionDigits:n});
let META={}, BACKTEST=null, COMPARISON=null, ticket=[3,8,12,17,21,29,34],power=12,lastR=null;
const divLabels=['7 + Powerball','7 números','6 + Powerball','6 números','5 + Powerball','4 + Powerball','5 números','3 + Powerball','2 + Powerball'];
async function api(path,options={}){
 const res=await fetch(path,options);let body;
 try{body=await res.json()}catch{throw Error('Respuesta inválida del servidor Python')}
 if(!res.ok)throw Error(typeof body.detail==='string'?body.detail:'Error HTTP '+res.status);
 return body;
}
function post(path,body){return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
let timer;
function toast(message){const el=$('toast');el.textContent=message;el.classList.add('visible');clearTimeout(timer);timer=setTimeout(()=>el.classList.remove('visible'),5500)}
function lock(btn,working){btn.disabled=working;const before=btn.dataset.original||(btn.dataset.original=btn.textContent);btn.textContent=working?'Calculando…':before}
async function safe(btn,task){try{if(btn)lock(btn,true);await task()}catch(err){console.error(err);toast(err.message)}finally{if(btn)lock(btn,false)}}
function ball(n,pb=false,sm=false){return `<span class="ball${pb?' pb':''}${sm?' sm':''}">${String(n).padStart(2,'0')}</span>`}
function barChart(where,observed,expected){const el=$(where);if(!el)return;const highest=Math.max(1,...observed,...(Array.isArray(expected)?expected:[expected]));let out='';observed.forEach((v,i)=>{const ref=Array.isArray(expected)?expected[i]:expected;const height=Math.max(1,100*v/highest),pos=100*ref/highest;out+=`<div class="freq-col" title="Número ${i+1}: observado ${num(v)}, esperado ${dec(ref,2)}"><div class="freq-inner"><div class="freq-expected" style="bottom:${pos}%"></div><div class="freq-bar${v<ref?' over':''}" style="height:${height}%"></div></div><span class="freq-label">${String(i+1).padStart(2,'0')}</span></div>`});el.innerHTML=out}
function compareChart(where,labels,observed,expected){const el=$(where),highest=Math.max(1,...observed,...expected);el.innerHTML=labels.map((label,i)=>`<div class="comparison-group" title="${label}: ${dec(observed[i],2)} observado; ${dec(expected[i],2)} esperado"><div class="obs" style="height:${Math.max(1,100*observed[i]/highest)}%"></div><div class="exp" style="height:${Math.max(1,100*expected[i]/highest)}%"></div><span>${label}</span></div>`).join('')}
function fillYears(){const options='<option value="">Todos los años</option>'+META.years.map(x=>`<option value="${x}">${x}</option>`).join('');$('history-year').innerHTML=options;$('test-year-filter').innerHTML=options}
async function loadMeta(){META=await api('/api/meta');const sw=$('storage-warning');if(sw&&META.read_only){sw.style.display='block';sw.textContent='Demo de solo lectura: las funciones de importación, actualización y sellado de predicciones están deshabilitadas. Para persistencia utiliza un disco en Render.';for(const id of ['update-data','upload-data','ledger-lock','regime-run','null-run','pair-run']){const btn=$(id);if(btn){btn.disabled=true;btn.title='Demo de solo lectura: requiere configuración con almacenamiento persistente';}}}else if(sw&&META.storage==='ephemeral'){sw.style.display='block';sw.textContent='Atención: este servidor no tiene almacenamiento persistente. Los cambios pueden perderse en reinicios o despliegues.';}if(META.storage==='ephemeral'){const sel=$('simulation-qty');if(sel)Array.from(sel.options).filter(o=>Number(o.value)>100000).forEach(o=>o.remove());}$('connection').textContent='● Motor Python activo';$('connection').classList.add('ready');$('m-count').textContent=num(META.n);$('source-last').textContent=META.end;$('m-range').textContent=`${META.start} → ${META.end}`;$('m-period').textContent=META.years[0]+' – '+META.years.at(-1);$('m-models').textContent=Object.keys(META.models).length+' + '+(Object.keys(META.advanced_models).length-2);fillYears();$('ranking-model').innerHTML=Object.entries(META.models).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}
async function loadHistorical(){const yr=$('history-year').value,params=yr?'?year='+yr:'';const [x,y]=await Promise.all([api('/api/overview'+params),api('/api/history?limit=30'+(yr?'&year='+yr:''))]);barChart('main-chart',x.freq,x.expected_main);barChart('pb-chart',x.pb_freq,x.expected_pb);compareChart('sum-chart',x.sum.edges,x.sum.observed,x.sum.expected);compareChart('overlap-chart',x.overlap.observed.map((_,i)=>i),x.overlap.observed,x.overlap.expected);$('overlap-note').textContent=`Coincidencias medias entre sorteos: ${dec(x.overlap.observed_mean??0,2)} observadas vs. ${dec(x.overlap.expected_mean,2)} esperadas. Suma media observada ${dec(x.sum.observed_mean,1)} vs. 126 teórica.`;$('draw-table').innerHTML=y.draws.map(d=>`<tr><td>${d.draw}</td><td>${d.date}</td><td><div class="numbers">${d.main.map(n=>ball(n,false,true)).join('')}</div></td><td>${ball(d.powerball,true)}</td></tr>`).join('')}
function metricDisplay(n,metric){return dec(n,metric==='brier'?6:4)}
function parameterText(r){if(r.family==='uniform')return 'Referencia';if(r.family==='all')return `Historia · K=${r.k}`;if(r.family==='window')return `Ventana ${r.window_or_halflife} · K=${r.k}`;return `Vida media ${r.window_or_halflife} · K=${r.k}`}
function fmtGain(n,metric){const dp=metric==='brier'?7:5;return (n>0?'+':'')+dec(n,dp)}
function renderModels(){
 if(!BACKTEST||!COMPARISON)return;
 const metric=$('metric-select').value;
 const rows=[...COMPARISON.metrics[metric]].sort((a,b)=>a.validation_score-b.validation_score);
 const ciType=$('ci-select').value;
 const uniform=rows.find(r=>r.key==='uniform');
 const displayCI=r=>`[${dec(r.simultaneous_ci95[0],metric==='brier'?6:4)}; ${dec(r.simultaneous_ci95[1],metric==='brier'?6:4)}]`;
 $('model-table').innerHTML=rows.map(row=>`<tr><td>${row.key==='uniform'?'● ':''}${row.label}</td><td class="tinyparam">${parameterText(row)}</td><td class="numeric">${metricDisplay(row.validation_score,metric)}</td><td class="numeric">${metricDisplay(row.test_score,metric)}</td><td class="numeric ${row.gain_vs_uniform>0?'good':row.gain_vs_uniform<0?'bad':''}">${fmtGain(row.gain_vs_uniform,metric)}</td><td class="numeric tinyparam">${displayCI(row)}</td></tr>`).join('');
 const elements=rows.map(r=>[r.gain_vs_uniform,...r[ciType]]).flat().filter(Number.isFinite);
 const maxabs=Math.max(...elements.map(Math.abs),1e-6)*1.12;
 const zero=50;
 const pxPct=v=>Math.max(0,Math.min(100,50+50*v/maxabs));
 $('model-forest').innerHTML=`<div class="forest-axis-head"><span>← Empeora</span><span>0</span><span>Mejora →</span></div>`+rows.map(row=>{
   const ci=row[ciType],p=pxPct(row.gain_vs_uniform),l=pxPct(ci[0]),h=pxPct(ci[1]);
   const selected=(metric==='brier'?COMPARISON.selected_main:COMPARISON.selected_pb)===row.key;
   const state=row.key==='uniform'?'neutral':row.gain_vs_uniform>=0?'positive':'negative';
   return `<div class="forest-row ${selected?'forest-selected':''}" title="${row.label} · diferencia ${fmtGain(row.gain_vs_uniform,metric)} · IC95 [${fmtGain(ci[0],metric)},${fmtGain(ci[1],metric)}]">
     <span class="forest-name" title="${row.label}">${row.label}${selected?'<sup>★</sup>':''}</span>
     <div class="forest-track"><div class="forest-zero"></div><i class="forest-range" style="left:${l}%;width:${Math.max(h-l,.18)}%"></i><i class="forest-point ${state}" style="left:${p}%"></i></div>
     <span class="forest-number ${state}">${fmtGain(row.gain_vs_uniform,metric)}</span></div>`;
 }).join('');
 const positives=rows.filter(r=>r.key!=='uniform'&&r[ciType][0]>0);
 $('forest-reading').textContent=`${positives.length} de 16 modelos alternativos con IC 95% enteramente por encima de cero. ${positives.length?'Hallazgo exploratorio: confirmar en sorteos nuevos.':'Ninguno muestra mejora concluyente con este intervalo.'}`;
 $('forest-scale').textContent=`Escala simétrica ±${dec(maxabs,metric==='brier'?5:3)} ${metric==='brier'?'Brier':'nats'}`;
}
async function loadBacktest(){
 const [b,c]=await Promise.all([api('/api/backtest'),api('/api/model-comparison')]);
 BACKTEST=b;COMPARISON=c;
 $('val-year').textContent=b.years.validation;$('test-year').textContent=b.years.test;
 $('val-count').textContent=num(b.counts.validation)+' sorteos · elige hiperparámetros';
 $('test-count').textContent=num(b.counts.test)+' sorteos · evalúa rendimiento';
 const mainGood=b.main_gain_vs_uniform>0,pbGood=b.pb_gain_vs_uniform>0;
 $('chosen-main').innerHTML=`<span class="stat-label">POR MENOR BRIER EN ${b.years.validation}</span><strong>${b.models[b.selected_main]}</strong><p>Brier posterior: <b>${dec(b.test[b.selected_main].brier,6)}</b> · uniforme: ${dec(b.test.uniform.brier,6)}</p><p class="${mainGood?'good':'bad'}">${mainGood?'Mejora':'No mejora'} en el año de prueba (${dec(b.main_gain_vs_uniform,7)} unidades Brier)</p><p class="ci">IC 95% de mejora individual: [${dec(b.main_gain_ci95[0],7)}, ${dec(b.main_gain_ci95[1],7)}]</p>`;
 $('chosen-pb').innerHTML=`<span class="stat-label">POR MENOR LOG-LOSS EN ${b.years.validation}</span><strong>${b.models[b.selected_pb]}</strong><p>Log-loss posterior: <b>${dec(b.test[b.selected_pb].pb_logloss,5)}</b> · uniforme: ${dec(b.test.uniform.pb_logloss,5)}</p><p class="${pbGood?'good':'bad'}">${pbGood?'Mejora':'No mejora'} en la prueba (${dec(b.pb_gain_vs_uniform,6)} nats)</p><p class="ci">IC 95% de mejora individual: [${dec(b.pb_gain_ci95[0],6)}, ${dec(b.pb_gain_ci95[1],6)}]</p>`;
 renderModels();
}
async function runTests(){const yr=$('test-year-filter').value,body={reps:+$('test-reps').value};if(yr)body.year=+yr;const r=await post('/api/tests',body);$('p-main').textContent=dec(r.main.p_value,3);$('p-max').textContent=dec(r.main.p_max_z,3);$('p-pb').textContent=dec(r.pb.p_value,3);const unusual=r.main.p_value<.05||r.main.p_max_z<.05||r.pb.p_value<.05;const el=$('test-reading');el.classList.toggle('warn',unusual);el.textContent=`${num(r.n)} sorteos y ${num(r.reps)} réplicas. ${unusual?'Se detectó alguna desviación inusual bajo la hipótesis uniforme, pero puede ser un falso positivo por pruebas múltiples. Requiere datos nuevos para validarse.':'No se observó una desviación estadísticamente clara respecto del mecanismo justo con estas pruebas.'} Un p-valor no proporciona combinaciones con ventaja demostrada.`}
function buildPickers(){const draw=(target,n,active)=>{$(target).innerHTML=Array.from({length:n},(_,i)=>`<button class="pick${active(i+1)?' active':''}" data-num="${i+1}">${String(i+1).padStart(2,'0')}</button>`).join('')};draw('number-picker',35,n=>ticket.includes(n));draw('power-picker',20,n=>n===power);$('selected-count').textContent=`${ticket.length} de 7 seleccionados`;[...$('number-picker').querySelectorAll('button')].forEach(btn=>btn.addEventListener('click',()=>{let v=+btn.dataset.num;if(ticket.includes(v))ticket=ticket.filter(n=>n!==v);else if(ticket.length<7)ticket=[...ticket,v].sort((a,b)=>a-b);buildPickers()}));[...$('power-picker').querySelectorAll('button')].forEach(btn=>btn.addEventListener('click',()=>{power=+btn.dataset.num;buildPickers()}))}
async function runSimulation(){if(ticket.length!==7)throw Error('Selecciona exactamente 7 números principales');const r=await post('/api/simulate',{ticket,powerball:power,n:+$('simulation-qty').value});$('sim-empty').classList.add('hidden');$('sim-results').classList.remove('hidden');$('s-prizes').textContent=num(r.prizes);$('s-jackpots').textContent=num(r.jackpots);compareChart('hits-chart',r.hits.map((_,i)=>i),r.hits,r.hits.map((_,k)=>r.n*(Math.exp(logChoose(7,k)+logChoose(28,7-k)-logChoose(35,7)))));$('div-table').innerHTML=divLabels.map((x,i)=>`<tr><td>Div. ${i+1} · ${x}</td><td class="numeric">${num(r.divisions[i])}</td><td class="numeric">${dec(r.expected_divisions[i],2)}</td></tr>`).join('');$('sim-reading').textContent=`En ${num(r.n)} sorteos, la proporción con premios fue ${dec(100*r.prizes/r.n,3)}%. Probabilidad teórica de ≥1 jackpot: ${dec(r.jackpot_prob_at_least_once*100,5)}%. Cero jackpots es el resultado habitual de una muestra así.`}
function logChoose(n,k){if(k<0||k>n)return -Infinity;let res=0;for(let i=1;i<=k;i++)res+=Math.log(n+1-i)-Math.log(i);return res}
async function loadRanking(){const model=$('ranking-model').value,r=await api('/api/ranking?model='+encodeURIComponent(model));const ranks=r.main.map((p,i)=>({n:i+1,p})).sort((a,b)=>b.p-a.p||a.n-b.n).slice(0,12),max=Math.max(...r.main);$('ranking-chart').innerHTML=ranks.map((v)=>`<div class="rankrow"><b>${String(v.n).padStart(2,'0')}</b><div class="ranktrack"><i style="width:${100*v.p/max}%"></i></div><em>${dec(v.p*100,2)}%</em></div>`).join('')+'<p class="micro-note">Probabilidad marginal estimada de aparición por el modelo; sin garantía de ser la probabilidad real. La suma de las 35 probabilidades marginales = 700% (7 números por sorteo).</p>'}
async function generate(){const model=$('ranking-model').value,r=await post('/api/generate',{model});$('ticket-result').classList.remove('empty');$('ticket-result').innerHTML=`<div class="ticket-output"><div class="ticket-label">${r.label.toUpperCase()}</div><div class="numbers" style="margin-top:15px">${r.ticket.map(n=>ball(n)).join('')}${ball(r.powerball,true)}</div></div><p class="subline">Una muestra aleatoria ponderada del modelo, no una predicción garantizada.</p><button class="outline" id="use-ticket">Usar en Monte Carlo ↗</button>`;$('use-ticket').addEventListener('click',()=>{ticket=r.ticket;power=r.powerball;buildPickers();switchPage('simulation')})}
function switchPage(page){document.querySelectorAll('.tab').forEach(e=>e.classList.toggle('active',e.dataset.page===page));document.querySelectorAll('.page').forEach(e=>e.classList.toggle('active',e.id==='page-'+page));location.hash=page}
async function reloadAll(){await loadMeta();await Promise.all([loadHistorical(),loadBacktest(),loadRanking(),loadEdge(),loadAudit(),loadLedger()])}
async function updateData(){const r=await api('/api/update',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':$('admin-token').value},body:JSON.stringify({start_year:+$('update-from').value})});$('update-log').textContent=`Nuevos: ${r.added} | Total: ${r.total}\n`+r.logs.map(x=>`${x.year}: ${x.status==='ok'?x.count+' sorteos leídos':'ERROR · '+x.message}`).join('\n');toast(r.message);await reloadAll()}
async function uploadData(){const file=$('csv-upload').files[0];if(!file)throw Error('Selecciona un archivo CSV');const text=await file.text();const result=await api('/api/import',{method:'POST',headers:{'Content-Type':'text/plain; charset=utf-8','X-Admin-Token':$('admin-token').value},body:text});$('upload-log').textContent=`${num(result.added)} nuevos sorteos; ${num(result.total)} en total.`;toast(result.message);await reloadAll()}
async function initialize(){document.querySelectorAll('.tab').forEach(e=>e.addEventListener('click',()=>switchPage(e.dataset.page)));$('history-year').addEventListener('change',()=>safe(null,loadHistorical));$('metric-select').addEventListener('change',renderModels);$('ci-select').addEventListener('change',renderModels);$('refresh-backtest').addEventListener('click',()=>safe($('refresh-backtest'),loadBacktest));$('run-tests').addEventListener('click',()=>safe($('run-tests'),runTests));$('randomize-ticket').addEventListener('click',()=>{ticket=[];while(ticket.length<7){let x=1+Math.floor(Math.random()*35);if(!ticket.includes(x))ticket.push(x)}ticket.sort((a,b)=>a-b);power=1+Math.floor(Math.random()*20);buildPickers()});$('run-simulation').addEventListener('click',()=>safe($('run-simulation'),runSimulation));$('ranking-model').addEventListener('change',()=>safe(null,loadRanking));$('generate-ticket').addEventListener('click',()=>safe($('generate-ticket'),generate));$('update-data').addEventListener('click',()=>safe($('update-data'),updateData));$('upload-data').addEventListener('click',()=>safe($('upload-data'),uploadData));$('edge-pick').addEventListener('click',()=>safe($('edge-pick'),generateEdgeTickets));$('pair-run').addEventListener('click',()=>safe($('pair-run'),runPairs));$('edge-metric').addEventListener('change',drawEdge);$('edge-prob-type').addEventListener('change',drawForecast);$('regime-run').addEventListener('click',()=>safe($('regime-run'),runRegimes));$('null-run').addEventListener('click',()=>safe($('null-run'),runFairNull));$('ledger-reload').addEventListener('click',()=>safe($('ledger-reload'),loadLedger));$('ledger-lock').addEventListener('click',()=>safe($('ledger-lock'),sealForecast));buildPickers();try{await reloadAll();if(['history','models','test','simulation','combinations','edge','data'].includes(location.hash.slice(1)))switchPage(location.hash.slice(1));}catch(err){console.error(err);$('connection').textContent='● Error con el servidor';toast('No se pudo conectar con el motor Python: '+err.message)}}

// V3: chronological evidence dashboard. All results are generated by Python.
let EDGE=null;
const pct=(v,d=2)=>dec(v*100,d)+'%';
function edgeMetricKey(){return $('edge-metric').value==='brier'?'brier':'pb_logloss'}
function drawEdge(){
 if(!EDGE)return;
 const metric=edgeMetricKey(), isMain=metric==='brier',gainField=isMain?'brier_gain':'pb_gain',scoreField=isMain?'brier':'pb_logloss',ciField=isMain?'brier_ci':'pb_ci';
 const rows=EDGE.rows, formatted=v=>(v>0?'+':'')+dec(v,isMain?7:5);
 const scale=Math.max(1e-6,...rows.flatMap(x=>[Math.abs(x[gainField]),...x[ciField].simultaneous_ci95.map(Math.abs)]))*1.12;
 const place=v=>Math.min(100,Math.max(0,50+v/scale*50));
 $('edge-forest').innerHTML='<div class="forest-axis-head"><span>← Empeora</span><span>0</span><span>Mejora →</span></div>'+rows.map(r=>{
   const lo=r[ciField].simultaneous_ci95[0],hi=r[ciField].simultaneous_ci95[1],value=r[gainField],l=place(lo),h=place(hi);
   return `<div class="forest-row"><span class="forest-name" title="${r.label}">${r.label}</span><div class="forest-track"><div class="forest-zero"></div><i class="forest-range" style="left:${l}%;width:${Math.max(.18,h-l)}%"></i><i class="forest-point ${value>=0?'positive':'negative'}" style="left:${place(value)}%"></i></div><span class="forest-number ${value>=0?'positive':'negative'}">${formatted(value)}</span></div>`;
 }).join('');
 $('edge-table').innerHTML=rows.map(r=>`<tr><td>${r.label}</td><td class="numeric">${dec(r[scoreField],isMain?7:5)}</td><td class="numeric ${r[gainField]>0?'good':'bad'}">${formatted(r[gainField])}</td><td class="numeric tinyparam">[${formatted(r[ciField].simultaneous_ci95[0])}; ${formatted(r[ciField].simultaneous_ci95[1])}]</td></tr>`).join('');
 const improved=rows.filter(r=>r.key!=='uniform'&&r[ciField].simultaneous_ci95[0]>0);
 $('edge-reading').textContent=`${improved.length} de ${rows.length-1} alternativas con intervalo simultáneo totalmente positivo. Los intervalos son exploratorios (bootstrap por bloques, n=${EDGE.test_draws} sorteos de prueba) y deben confirmarse en predicciones futuras.`;
 drawEdgeCurve();
}
function drawEdgeCurve(){
 if(!EDGE)return;
 const isMain=edgeMetricKey()==='brier', arr=EDGE.timeline,vals=arr.map(x=>isMain?x.brier_cumulative_gain:x.pb_cumulative_gain);
 const W=720,H=220,mar={t:14,r:25,b:32,l:65},w=W-mar.l-mar.r,h=H-mar.t-mar.b;
 let lo=Math.min(0,...vals),hi=Math.max(0,...vals),span=hi-lo||.001;
 lo-=span*.13;hi+=span*.13;
 const x=i=>mar.l+(w*i/Math.max(1,vals.length-1)),y=v=>mar.t+h*(hi-v)/(hi-lo),zero=y(0);
 const grid=[0,.25,.5,.75,1].map(fr=>{let v=lo+(hi-lo)*fr;return `<line x1="${mar.l}" y1="${y(v)}" x2="${W-mar.r}" y2="${y(v)}" stroke="#304456" stroke-width="1"/><text x="${mar.l-9}" y="${y(v)+4}" font-size="11" fill="#94aabb" text-anchor="end">${dec(v,3)}</text>`}).join('');
 const points=vals.map((v,i)=>`${x(i)},${y(v)}`).join(' ');
 $('edge-curve').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Ganancia acumulada del ensemble, respecto al modelo uniforme, en ${arr.length} sorteos"><title>Ganancia acumulada; cero significa igualdad con uniforme</title>${grid}<line x1="${mar.l}" x2="${W-mar.r}" y1="${zero}" y2="${zero}" stroke="#e4c487" stroke-dasharray="5 4" stroke-width="1.5"/><polyline points="${points}" fill="none" stroke="#67d9b6" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${x(vals.length-1)}" cy="${y(vals.at(-1))}" r="5" fill="#e4c487"/><text x="${mar.l}" y="${H-6}" font-size="12" fill="#9fb6c2">${arr[0].date}</text><text x="${W-mar.r}" y="${H-6}" font-size="12" fill="#9fb6c2" text-anchor="end">${arr.at(-1).date}</text></svg>`;
}
function drawForecast(){
 if(!EDGE)return;
 const main=$('edge-prob-type').value==='main';const data=main?EDGE.main_forecast:EDGE.pb_forecast;const base=main?.2:.05;
 const sorted=[...data].sort((a,b)=>b.ensemble-a.ensemble);
 $('edge-target').textContent=`Pronóstico experimental para sorteo ${EDGE.forecast_for.draw} · ${EDGE.forecast_for.date} · modelo ensemble · ${main?'probabilidad marginal por número':'probabilidad de cada Powerball'}.`;
 $('edge-heatmap').className='edge-heatmap '+(main?'main':'pb');
 $('edge-heatmap').innerHTML=data.map(r=>{
  const dev=(r.ensemble-base)/base,opacity=Math.min(.68,.14+Math.abs(dev)*4);
  const color=dev>=0?`rgba(103,217,182,${opacity})`:`rgba(239,136,150,${opacity})`;
  return `<div class="heatbox" title="${r.number}: ensemble ${pct(r.ensemble,3)}, referencia ${pct(base,2)}, intervalo Beta con K=100 [${pct(r.band90[0],2)}, ${pct(r.band90[1],2)}]" style="background:${color}"><strong>${String(r.number).padStart(2,'0')}</strong><span>${pct(r.ensemble,2)}</span></div>`;
 }).join('');
 $('edge-top').innerHTML=`<table><thead><tr><th>${main?'Número':'Powerball'}</th><th>Ensemble (estimado)</th><th>Bayes empírico</th><th>IC creíble 90% · K=100</th><th>Uniforme</th></tr></thead><tbody>${sorted.slice(0,10).map(r=>`<tr><td>${String(r.number).padStart(2,'0')}</td><td class="numeric">${pct(r.ensemble,3)}</td><td class="numeric">${pct(r.eb,3)}</td><td class="numeric">${pct(r.band90[0],2)} — ${pct(r.band90[1],2)}</td><td class="numeric">${pct(base,2)}</td></tr>`).join('')}</tbody></table>`;
}
function drawCalibration(){
 if(!EDGE)return;
 const max=Math.max(.23,...EDGE.calibration.flatMap(r=>[r.predicted,r.observed]));
 $('edge-calibration').innerHTML=EDGE.calibration.map(r=>`<div class="calibration-row"><strong>Grupo ${r.bucket}</strong><div class="cal-bars"><div class="cal-bard"><i style="width:${100*r.predicted/max}%"></i></div><div class="cal-bard actual"><i style="width:${100*r.observed/max}%"></i></div></div><span>${pct(r.predicted,2)} / ${pct(r.observed,2)} <small>(n=${r.n})</small></span></div>`).join('')+'<div class="micro-note">Barra verde: pronosticado · barra azul: observado.</div>';
}
async function loadEdge(){
 EDGE=await api('/api/edge');
 $('edge-years').textContent=EDGE.validation_year+' → '+EDGE.test_year;
 $('edge-range').textContent=`${EDGE.test_draws} sorteos test (${EDGE.holdout_start} al ${EDGE.holdout_end})`;
 const best=EDGE.rows.find(x=>x.key==='adaptive_ensemble');
 $('edge-main-gain').textContent=(best.brier_gain>0?'+':'')+dec(best.brier_gain,7);
 $('edge-pb-gain').textContent=(best.pb_gain>0?'+':'')+dec(best.pb_gain,6);
 const significant=best.brier_ci.simultaneous_ci95[0]>0||best.pb_ci.simultaneous_ci95[0]>0;
 $('edge-verdict').textContent=significant?'Exploratorio':'Sin ventaja probada';
 $('edge-config').innerHTML=`<div>Principales: <b>ventana ${EDGE.ensemble.main.window}</b> · η=${EDGE.ensemble.main.eta}</div><div>Powerball: <b>ventana ${EDGE.ensemble.pb.window}</b> · η=${EDGE.ensemble.pb.eta}</div><div>Elegidos con el desempeño de ${EDGE.validation_year}, sin mirar ${EDGE.test_year}.</div>`;
 const weights=EDGE.ensemble.main_weights;
 const nam={uniform:'Uniforme',all_k100:'Histórico',win13_k100:'Ventana 13',win52_k100:'Ventana 52',ewm26_k100:'Exponencial 26',empirical_bayes:'Bayes empírico',regime_guard:'Regímenes'};
 $('edge-weights').innerHTML=Object.entries(weights).map(([k,v])=>`<div class="weight-row"><span>${nam[k]||k}</span><div class="weight-track"><i style="width:${v*100}%"></i></div><b>${pct(v,1)}</b></div>`).join('');
 drawEdge();drawForecast();drawCalibration();
}
async function runRegimes(){
 const r=await api('/api/regimes',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':$('admin-token').value},body:JSON.stringify({reps:+$('regime-reps').value})});
 $('regime-result').innerHTML=`<div class="edge-result-grid"><div><strong>${dec(r.main.p_adjusted_2tests,3)}</strong><small>p corregido · principales</small><span>${r.main.first_after_split}</span></div><div><strong>${dec(r.powerball.p_adjusted_2tests,3)}</strong><small>p corregido · Powerball</small><span>${r.powerball.first_after_split}</span></div></div><p>Fechas del corte máximo son candidatas exploratorias. ${r.main.p_adjusted_2tests<.05||r.powerball.p_adjusted_2tests<.05?'Señal temporal inusual; confirmar externamente.':'Sin evidencia sólida de ruptura temporal.'}</p>`;
}
async function runFairNull(){
 const r=await api('/api/edge-null',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':$('admin-token').value},body:JSON.stringify({reps:+$('null-reps').value})});
 $('null-result').innerHTML=`<div class="edge-result-grid"><div><strong>${dec(r.main.p_fair_null,3)}</strong><small>p placebo · 35 números</small><span>Mejor Δ ${dec(r.main.observed_best_gain,7)}</span></div><div><strong>${dec(r.powerball.p_fair_null,3)}</strong><small>p placebo · Powerball</small><span>Mejor Δ ${dec(r.powerball.observed_best_gain,6)}</span></div></div><p>${r.reps} historiales aleatorios independientes, cada uno reajustando el ensemble en la validación. No incluye los 17 modelos v2 ni intentos anteriores.</p>`;
}
async function loadAudit(){const r=await api('/api/audit');$('audit-info').innerHTML=`<div><b>${r.n} sorteos</b> · ${r.first} — ${r.last} · huecos de identificador: ${r.missing_draw_ids.length}</div><div>Años: ${Object.entries(r.years).map(([k,v])=>k+': '+v).join(' · ')}</div><div>SHA-256 CSV: <code>${r.sha256}</code></div><div>${r.limitation}</div>`}
async function loadLedger(){const r=await api('/api/ledger');$('ledger-table').innerHTML=r.entries.length?r.entries.slice().reverse().map(e=>`<tr><td>${e.target_draw} · ${e.target_date}</td><td>${e.created_utc}</td><td>${e.hash_valid?(e.resolved?'Evaluado':'Pendiente'):'Integridad fallida'}</td><td class="numeric">${e.resolved?dec(e.result.brier,6):'—'}</td><td><code>${e.sha256.slice(0,14)}…</code></td></tr>`).join(''):'<tr><td colspan="5">Sin predicciones selladas. Se pueden guardar antes de próximos sorteos.</td></tr>'}
async function runPairs(){
 const r=await api('/api/pairs',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':$('admin-token').value},body:JSON.stringify({reps:+$('pair-reps').value})});
 $('pair-summary').textContent=`Valor p global = ${dec(r.p_familywise,4)} · ${r.tested_pairs} pares · esperado ${dec(r.expected_per_pair,2)} apariciones por par. ${r.p_familywise<.05?'Desviación inusual, necesita confirmación independiente.':'La diferencia más extrema también es compatible con el azar.'}`;
 $('pair-table').innerHTML=`<table><thead><tr><th>Par</th><th>Apariciones</th><th>Esperadas</th><th>Desviación Z</th></tr></thead><tbody>${r.extremes.map(v=>`<tr><td>${String(v.a).padStart(2,'0')} + ${String(v.b).padStart(2,'0')}</td><td class="numeric">${num(v.count)}</td><td class="numeric">${dec(r.expected_per_pair,2)}</td><td class="numeric">${dec(v.z,2)}</td></tr>`).join('')}</tbody></table>`;
}
async function generateEdgeTickets(){
 const r=await post('/api/edge-tickets',{model:'adaptive_ensemble'});
 $('edge-tickets').innerHTML=[['Uniforme',r.uniform],['Ensemble · muestra ponderada',r.ensemble]].map(([label,d])=>`<div class="edge-ticket"><span>${label}</span><div class="numbers">${d.main.map(x=>ball(x)).join('')}${ball(d.pb,true)}</div><small>Jackpot teórico · 1 en ${num(r.fair_jackpot_odds)}</small></div>`).join('');
}
async function sealForecast(){const r=await api('/api/ledger/lock',{method:'POST',headers:{'X-Admin-Token':$('admin-token').value}});toast('Pronóstico sellado para sorteo '+r.target_draw+' · SHA '+r.sha256.slice(0,12));await loadLedger()}

window.addEventListener('DOMContentLoaded',initialize);
