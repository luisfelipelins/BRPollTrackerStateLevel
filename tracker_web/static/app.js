const $ = id => document.getElementById(id);
const contributionColors = {SP:'#477EAB',MG:'#B13B42',RJ:'#245C48',BA:'#E1B45C',PR:'#80609A',RS:'#173F66',PE:'#4D8974',CE:'#D78058',PA:'#8B4259',Others:'#AAB4BE','Voting-weight change':'#795548'};
const colors = ['#477EAB','#B13B42','#245C48','#E1B45C','#80609A','#173F66','#4D8974','#D78058','#8B4259','#AAB4BE','#795548'];
const stateNames = {AC:'Acre',AL:'Alagoas',AP:'Amapá',AM:'Amazonas',BA:'Bahia',CE:'Ceará',DF:'Federal District',ES:'Espírito Santo',GO:'Goiás',MA:'Maranhão',MT:'Mato Grosso',MS:'Mato Grosso do Sul',MG:'Minas Gerais',PA:'Pará',PB:'Paraíba',PR:'Paraná',PE:'Pernambuco',PI:'Piauí',RJ:'Rio de Janeiro',RN:'Rio Grande do Norte',RS:'Rio Grande do Sul',RO:'Rondônia',RR:'Roraima',SC:'Santa Catarina',SP:'São Paulo',SE:'Sergipe',TO:'Tocantins',ZZ:'Overseas'};
let data, tab = 'live', requestId = 0, sortKey = 'data', sortDirection = -1;
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value,digits=2) => value == null ? 'Unavailable' : Number(value).toFixed(digits);
const dateLabel = value => new Date(value).toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'});
let columnFilters = {}, selectedPolls = {}, filterDraft, filterColumn;
const pollKey = r => [r.coverage,r.institute,r.data,r.id_pesquisa].join('|');
const chartPolls = coverage => data.polls.filter(r=>r.coverage===coverage && r.data.slice(0,10)>=data.start);
const config = {responsive:true,displaylogo:false,scrollZoom:false,modeBarButtonsToRemove:['lasso2d','select2d','autoScale2d'],toImageButtonOptions:{format:'png',scale:2}};

function layout(ytitle,mini=false) {
  return {paper_bgcolor:'white',plot_bgcolor:'white',font:{family:'Segoe UI, sans-serif',size:11,color:'#526878'},margin:{l:mini?49:54,r:16,t:12,b:mini?37:65},
    hovermode:'x unified',hoverlabel:{bgcolor:'#fff',font:{size:12}},
    xaxis:{type:'date',range:[data.start+'T00:00:00',data.end+'T23:59:59'],tickformat:'%d %b',nticks:mini?4:6,gridcolor:'#eef1f3',showspikes:true,spikemode:'across',spikesnap:'data',spikecolor:'#9caeb9',spikethickness:1},
    yaxis:{title:{text:ytitle,font:{size:10}},gridcolor:'#e8eef1',zerolinecolor:'#b2c2ca',ticksuffix: ytitle.includes('%')?'%':''},
    legend:{orientation:'h',x:0,y:1,xanchor:'left',yanchor:'top',bgcolor:'rgba(255,255,255,.85)',font:{size:10}},
    uirevision:`${data.year}-${data.method}`};
}

function line(key,name,color,extra=false) {
  return {x:data.daily.map(r=>r.data),y:data.daily.map(r=>r[key+'_0']),name,type:'scatter',mode:'lines',line:{color,width:2.4,dash:key==='matched'?'dot':'solid'},connectgaps:false,
    customdata:data.daily.map(r=>[fmt(r[key+'_1']),fmt(r.coverage,1)]),
    hovertemplate:`<b>${name}</b><br>${esc(data.candidates[0])}: %{y:.2f}%<br>${esc(data.candidates[1])}: %{customdata[0]}%`+(extra?'<br>Polling coverage: %{customdata[1]}%':'')+'<extra></extra>'};
}

function pollTrace(polls,chart) {
  const selected = polls.findIndex(r=>pollKey(r)===selectedPolls[chart]);
  return {x:polls.map(r=>r.data),y:polls.map(r=>r.share_0),type:'scatter',mode:'markers',name:'Individual polls',ids:polls.map(pollKey),selectedpoints:selected<0?null:[selected],selected:{marker:{size:13,color:'#d58b28',opacity:1}},unselected:{marker:{opacity:.28}},marker:{size:8,color:'#ffffff',line:{color:'#8497a6',width:1.6}},
    text:polls.map(r=>`<b>${esc(r.institute)}</b><br>${dateLabel(r.data)} · ${esc(r.coverage==='BR'?'National':r.coverage)}<br>${esc(data.candidates[0])}: ${fmt(r.share_0)}%<br>${esc(data.candidates[1])}: ${fmt(r.share_1)}%<br>Registry: ${esc(r.registry||'Not provided')}`),hovertemplate:'%{text}<extra></extra>'};
}

function actualTrace(value) {
  return {x:[data.start,data.end],y:[value,value],name:'Actual result',type:'scatter',mode:'lines',line:{color:'#6f7f88',width:1.3,dash:'dash'},hovertemplate:'Actual result: %{y:.2f}%<extra></extra>'};
}

function drawMain() {
  const traces = [line('national','National polls','#173F66'),line('aggregate','State aggregate','#B13B42',true)];
  if(data.common.length) traces.push(line('matched','National · shared institutes','#39735e'));
  if(data.actual) traces.push(actualTrace(data.actual[0]));
  traces.push(pollTrace(chartPolls('BR'),'trackers'));
  const options = layout('Vote share (%)');
  options.hovermode = false;
  Plotly.react('trackers',traces,options,config).then(()=>bindPollSelection('trackers'));
  $('common-note').textContent = data.common.length ? 'Shared institutes: '+data.common.join(', ')+'. Hover any date to compare all three trackers in one box. Coverage is shown with the state aggregate.' : 'No institutes appear at both levels during this period; the shared-institute series is unavailable.';
}

function drawContributions() {
  const rows = data.contributions, columns = rows.length?Object.keys(rows[0]).filter(k=>!['data','Total'].includes(k)):[];
  const traces = columns.map((key,i)=>({type:'bar',name:key,x:rows.map(r=>r.data),y:rows.map(r=>r[key]),marker:{color:contributionColors[key]},customdata:rows.map(r=>fmt(r[key])),hovertemplate:`${esc(key)}: %{customdata} pp<extra></extra>`}));
  traces.push({type:'scatter',mode:'markers',name:data.year===2026?'National change':'National error',x:rows.map(r=>r.data),y:rows.map(r=>r.Total),marker:{size:6,color:'#182f40'},customdata:rows.map(r=>fmt(r.Total)),hovertemplate:'Total: %{customdata} pp<extra></extra>'});
  const options = layout('Contribution (pp)');
  options.yaxis.tickformat = '.2f';
  options.barmode = 'relative'; options.bargap = .2; options.margin.t = 65; options.legend.y = 1.23;
  if(!rows.length) options.annotations = [{text:'No state tracker changes in this period',xref:'paper',yref:'paper',x:.5,y:.5,showarrow:false}];
  Plotly.react('contributions',traces,options,config);
}

function drawDiagnostic(id,key,title,color) {
  const options = layout(title,true);
  options.showlegend = false;
  if(key==='coverage') options.yaxis.range = [0,105]; else options.yaxis.rangemode = 'tozero';
  Plotly.react(id,[{x:data.daily.map(r=>r.data),y:data.daily.map(r=>r[key]),type:'scatter',mode:'lines',line:{color,width:2},fill:'tozeroy',fillcolor:color+'12',name:title,hovertemplate:`%{y:.1f}${key==='coverage'?'%':' days'}<extra></extra>`}],options,config);
}

function drawState() {
  if(!data) return;
  const state = $('state').value, rows = data.states[state];
  const traces = [{x:rows.map(r=>r.data),y:rows.map(r=>r.share_0),name:state+' tracker',type:'scatter',mode:'lines',line:{color:'#173F66',width:2.3},customdata:rows.map(r=>[fmt(r.share_1),r.polled?'State polls':'Previous-election fallback']),hovertemplate:`<b>${esc(stateNames[state])}</b><br>%{x|%d %b %Y}<br>${esc(data.candidates[0])}: %{y:.2f}%<br>${esc(data.candidates[1])}: %{customdata[0]}%<br>%{customdata[1]}<extra></extra>`}];
  if(data.state_actual[state]) traces.push(actualTrace(data.state_actual[state][0]));
  traces.push(pollTrace(chartPolls(state),'state-chart'));
  const options = layout('Vote share (%)',true);
  options.hovermode = false; options.uirevision += state;
  Plotly.react('state-chart',traces,options,config).then(()=>bindPollSelection('state-chart'));
}

function trackerTooltip(chart,index) {
  if(chart==='state-chart') {
    const row=data.states[$('state').value][index];
    return `<b>${dateLabel(row.data)} ? ${esc($('state').value)}</b><br>${esc(data.candidates[0])}: ${fmt(row.share_0)}%<br>${esc(data.candidates[1])}: ${fmt(row.share_1)}%<br>${row.polled?'State polls':'Previous-election fallback'}`;
  }
  const row=data.daily[index];
  return `<b>${dateLabel(row.data)}</b>`+[['national','National polls'],['aggregate','State aggregate'],['matched','National - shared institutes']].filter(([key])=>key!=='matched'||data.common.length).map(([key,name])=>`<div class="hover-series"><strong>${name}</strong><br>${esc(data.candidates[0])}: ${fmt(row[key+'_0'])}%<br>${esc(data.candidates[1])}: ${fmt(row[key+'_1'])}%${key==='aggregate'?'<br>Polling coverage: '+fmt(row.coverage,1)+'%':''}</div>`).join('');
}

function hoverTarget(chart,x,y,axes,traces) {
  // Poll tooltips require proximity in BOTH dimensions, not just the same date.
  let poll=null,distance=11;
  traces.forEach((trace,curveNumber)=>{
    if(trace.name!=='Individual polls'||trace.visible===false||trace.visible==='legendonly') return;
    trace.x.forEach((date,pointNumber)=>{
      const dx=axes.x.d2p(date)-x,dy=axes.y.d2p(trace.y[pointNumber])-y;
      const gap=Math.hypot(dx,dy);
      if(gap<distance) {distance=gap;poll={curveNumber,pointNumber,trace};}
    });
  });
  if(poll) return {poll,date:poll.trace.x[poll.pointNumber],html:poll.trace.text[poll.pointNumber]};
  const date=axes.x.p2d(x),time=new Date(date).getTime();
  let index=0;
  data.daily.forEach((row,i)=>{if(Math.abs(new Date(row.data)-time)<Math.abs(new Date(data.daily[index].data)-time))index=i;});
  return {poll:null,date:data.daily[index].data,html:trackerTooltip(chart,index)};
}

function selectPoll(chart,poll) {
  const node=$(chart),key=poll.trace.ids[poll.pointNumber];
  selectedPolls[chart]=selectedPolls[chart]===key?null:key;
  Plotly.restyle(node,{selectedpoints:[selectedPolls[chart]?[poll.pointNumber]:null]},[poll.curveNumber]);
}

function bindPollSelection(chart) {
  const node=$(chart);
  const tooltip=$(chart+'-details');
  if(!node.hoverLine) {
    node.hoverLine=document.createElement('div');
    node.hoverLine.className='tracker-hover-line';
    node.append(node.hoverLine);
  }
  const guide=node.hoverLine;
  let pinned=false;
  function reset() {
    tooltip.innerHTML='<span class="hover-hint">Hover a date to inspect the trackers, or a poll dot for its details.</span>';
    guide.hidden=true;
  }
  reset();
  function target(event) {
    const box=node.getBoundingClientRect(),axes={x:node._fullLayout.xaxis,y:node._fullLayout.yaxis};
    const x=event.clientX-box.left-axes.x._offset,y=event.clientY-box.top-axes.y._offset;
    if(x<0||y<0||x>axes.x._length||y>axes.y._length) return null;
    return {...hoverTarget(chart,x,y,axes,node.data),left:event.clientX-box.left,top:event.clientY-box.top};
  }
  function show(hit) {
    tooltip.innerHTML=hit.poll?'<div class="poll-detail">'+hit.html+'</div>':hit.html;
    const axes=node._fullLayout;
    guide.style.left=(axes.xaxis._offset+axes.xaxis.d2p(hit.date))+'px';
    guide.style.top=axes.yaxis._offset+'px';
    guide.style.height=axes.yaxis._length+'px';
    guide.hidden=false;
  }
  node.onmousemove=event=>{
    if(pinned||event.buttons) return;
    const hit=target(event);
    if(hit) show(hit);else reset();
  };
  node.onmouseleave=()=>{if(!pinned)reset();};
  node.onclick=event=>{
    const hit=target(event);
    if(hit?.poll) {
      selectPoll(chart,hit.poll);
      pinned=!!selectedPolls[chart];
      if(pinned)show(hit);else reset();
    } else {pinned=false;reset();}
  };
}

function filterValue(row,key) {
  if(key==='data') return row.data.slice(0,10);
  if(key.startsWith('share_')) return fmt(row[key]);
  return String(row[key]??'');
}

function filteredPolls(except=null) {
  return data.polls.filter(row=>Object.entries(columnFilters).every(([key,values])=>key===except||values.has(filterValue(row,key))));
}

function drawTable() {
  if(!data) return;
  const rows=filteredPolls();
  rows.sort((a,b)=>typeof a[sortKey]==='number'?sortDirection*(a[sortKey]-b[sortKey]):sortDirection*String(a[sortKey]??'').localeCompare(String(b[sortKey]??'')));
  $('poll-table').querySelector('tbody').innerHTML=rows.map(r=>`<tr><td>${esc(r.institute)}</td><td>${dateLabel(r.data)}</td><td>${r.coverage==='BR'?'National':esc(r.coverage)}</td><td class="number">${fmt(r.share_0)}%</td><td class="number">${fmt(r.share_1)}%</td><td class="registry">${esc(r.registry||'Not provided')}</td></tr>`).join('');
  $('poll-count').textContent=`${rows.length} / ${data.polls.length}`;
  $('empty-polls').hidden=!!rows.length;
  document.querySelectorAll('[data-filter]').forEach(button=>button.classList.toggle('filtered',!!columnFilters[button.dataset.filter]));
}

function closeFilter() {
  $('column-menu').hidden=true;
  document.querySelectorAll('[data-filter]').forEach(button=>button.setAttribute('aria-expanded','false'));
}

function openFilter(button) {
  filterColumn=button.dataset.filter;
  const values=[...new Set(filteredPolls(filterColumn).map(row=>filterValue(row,filterColumn)))].sort((a,b)=>filterColumn.startsWith('share_')?Number(a)-Number(b):a.localeCompare(b));
  filterDraft=new Set(columnFilters[filterColumn]??values);
  const menu=$('column-menu');
  menu.innerHTML=`<strong>Filter ${esc(button.closest('th').querySelector('[data-sort]').textContent)}</strong><input type="search" id="filter-search" placeholder="Search values..." aria-label="Search filter values"><div class="filter-actions"><button id="filter-all">Select all visible</button><button id="filter-none">Clear visible</button></div><div id="filter-values"></div><div class="filter-actions"><button id="filter-reset">Remove filter</button><button id="filter-cancel">Cancel</button><button id="filter-apply">Apply</button></div>`;
  function showValues() {
    const query=$('filter-search').value.toLowerCase();
    const visible=values.filter(value=>value.toLowerCase().includes(query));
    $('filter-values').replaceChildren(...visible.map(value=>{
      const label=document.createElement('label'),input=document.createElement('input');
      input.type='checkbox'; input.checked=filterDraft.has(value);
      input.addEventListener('change',()=>input.checked?filterDraft.add(value):filterDraft.delete(value));
      label.append(input,document.createTextNode(filterColumn==='data'?dateLabel(value):value==='BR'?'National':value||'Not provided'));
      return label;
    }));
    $('filter-all').onclick=()=>{visible.forEach(value=>filterDraft.add(value));showValues();};
    $('filter-none').onclick=()=>{visible.forEach(value=>filterDraft.delete(value));showValues();};
  }
  $('filter-search').addEventListener('input',showValues);
  $('filter-apply').onclick=()=>{columnFilters[filterColumn]=new Set(filterDraft);closeFilter();drawTable();};
  $('filter-reset').onclick=()=>{delete columnFilters[filterColumn];closeFilter();drawTable();};
  $('filter-cancel').onclick=closeFilter;
  const rect=button.getBoundingClientRect();
  menu.hidden=false;
  menu.style.left=Math.max(8,Math.min(rect.left,window.innerWidth-300))+'px';
  menu.style.top=Math.max(8,Math.min(rect.bottom+6,window.innerHeight-430))+'px';
  button.setAttribute('aria-expanded','true');
  showValues(); $('filter-search').focus();
}

function clearFilters() {
  columnFilters={}; closeFilter(); drawTable();
}

function chartExport(chart) {
  const candidate0=data.candidates[0]+' (%)',candidate1=data.candidates[1]+' (%)';
  if(chart==='contributions') return data.contributions.map(row=>({Date:row.data,...Object.fromEntries(Object.entries(row).filter(([key])=>key!=='data').map(([key,value])=>[key+' (pp)',value]))}));
  if(chart==='coverage'||chart==='freshness') return data.daily.map(row=>({Date:row.data,[chart==='coverage'?'Polling coverage (%)':'Average latest-poll age (days)']:row[chart]}));
  const state=$('state').value,rows=[];
  if(chart==='trackers') {
    for(const [series,name] of [['national','National polls'],['aggregate','State aggregate'],['matched','National polls - shared institutes']]) {
      if(series==='matched'&&!data.common.length) continue;
      for(const row of data.daily) rows.push({Date:row.data,Type:'Tracker',Series:name,[candidate0]:row[series+'_0'],[candidate1]:row[series+'_1'],'Coverage (%)':series==='aggregate'?row.coverage:null,'Freshness (days)':series==='aggregate'?row.freshness:null});
    }
  } else {
    for(const row of data.states[state]) rows.push({Date:row.data,Type:'Tracker',Series:state,[candidate0]:row.share_0,[candidate1]:row.share_1,Source:row.polled?'State polls':'Previous-election fallback'});
  }
  const actual=chart==='trackers'?data.actual:data.state_actual[state];
  if(actual) for(const date of [data.start,data.end]) rows.push({Date:date,Type:'Result',Series:'Actual result',[candidate0]:actual[0],[candidate1]:actual[1]});
  for(const row of chartPolls(chart==='trackers'?'BR':state)) rows.push({Date:row.data,Type:'Poll',Series:row.coverage,[candidate0]:row.share_0,[candidate1]:row.share_1,Institute:row.institute,Registry:row.registry,'Survey ID':row.id_pesquisa});
  return rows;
}

function csvText(rows) {
  if(!rows.length) return 'Date\r\n';
  const columns=[...new Set(rows.flatMap(row=>Object.keys(row)))];
  const cell=value=>{
    let text=String(value??'');
    if(typeof value==='string'&&/^[=+@\-\t\r]/.test(text)) text="'"+text;
    return '"'+text.replace(/"/g,'""')+'"';
  };
  return [columns.map(cell).join(','),...rows.map(row=>columns.map(key=>cell(row[key])).join(','))].join('\r\n');
}

function exportChart(chart) {
  if(!data) return;
  const blob=new Blob(['\uFEFF'+csvText(chartExport(chart))],{type:'text/csv;charset=utf-8'});
  const url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download=`${data.year}_${data.method}_${chart}${chart==='state-chart'?'_'+$('state').value:''}.csv`;
  document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function render() {
  const last=data.daily.at(-1);
  $('period').textContent=`${dateLabel(data.start)} – ${dateLabel(data.end)} · Two-candidate vote shares`;
  $('page-title').textContent=`${data.year} presidential runoff`;
  $('candidate-badge').textContent=data.candidates[0]+' share';
  for(const [id,key] of [['aggregate','aggregate'],['national','national']]) {
    $(id+'-value').textContent=last[key+'_0']==null?'Unavailable':fmt(last[key+'_0'])+'%';
    $(id+'-detail').textContent=`${data.candidates[0]} · ${data.candidates[1]} ${fmt(last[key+'_1'])}%`;
  }
  for(const key of ['aggregate','national']) {
    const error=$(key+'-error');
    error.hidden=!data.actual;
    const value=last[key+'_0'];
    error.textContent=data.actual&&value!=null?`${data.candidates[0]} error: ${value-data.actual[0]>=0?'+':''}${fmt(value-data.actual[0])} pp ? actual ${fmt(data.actual[0])}%`:'Error unavailable';
  }
  $('coverage-value').textContent=fmt(last.coverage,1)+'%';
  $('freshness-value').textContent=last.freshness==null?'Unavailable':fmt(last.freshness,1)+' days';
  $('contribution-title').textContent=data.year===2026?'What moved the national aggregate?':'Where did the national error come from?';
  $('contribution-note').textContent=data.year===2026?`${data.candidates[0]} · Daily weighted state changes. Dots show the net change. Others includes overseas.`:`${data.candidates[0]} · State estimation errors plus voting-weight correction. Dots show total national error.`;
  $('performance-card').hidden=data.year===2026;
  $('performance').querySelector('tbody').innerHTML=data.performance.map(r=>`<tr><td>${esc(r.institute)}</td>${['national','national_pct','national_error','state','state_pct','state_error'].map(k=>`<td class="number">${r[k]==null?'—':fmt(r[k],['national','state'].includes(k)?0:2)}</td>`).join('')}</tr>`).join('');
  for(let i=0;i<2;i++) $('poll-name-'+i).textContent=data.candidates[i];
  drawMain(); drawContributions(); drawDiagnostic('coverage','coverage','Covered votes (%)','#39735e'); drawDiagnostic('freshness','freshness','Age (days)','#477EAB'); drawState(); drawTable();
}

async function load() {
  const id=++requestId,year=tab==='history'?$('year').value:2026;
  $('status').hidden=false; $('status').className=''; $('status').textContent='Loading surveys and election data. The first load may take a few seconds.';
  $('content').hidden=true;
  try {
    const response=await fetch(`/api/dashboard?year=${year}&method=${$('method').value}`);
    const payload=await response.json();
    if(id!==requestId) return;
    if(!response.ok) throw new Error(payload.error||'Unable to load the dashboard.');
    const changedYear=data&&data.year!==payload.year;
    data=payload;
    if(changedYear) {selectedPolls={};clearFilters();}
    $('content').hidden=false; $('status').hidden=true;
    render();
  } catch(error) {
    if(id!==requestId) return;
    $('status').className='error'; $('status').textContent=error.message+' Use Refresh to try again.';
  }
}

document.querySelectorAll('.tab').forEach(button=>button.addEventListener('click',()=>{
  tab=button.dataset.tab;
  document.querySelectorAll('.tab').forEach(b=>{b.classList.toggle('active',b===button);if(b===button)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  $('dashboard').hidden=tab==='methodology'; $('methodology').hidden=tab!=='methodology'; $('year-control').hidden=tab!=='history';
  $('edition').textContent=tab==='history'?'LOOKING BACK':'THE ROAD TO OCTOBER';
  if(tab!=='methodology') load();
}));
$('state').replaceChildren(...Object.entries(stateNames).map(([code,name])=>new Option(code+' · '+name,code))); $('state').value='SP';
$('state').addEventListener('change',drawState);
['method','year'].forEach(id=>$(id).addEventListener('change',load));
$('refresh').addEventListener('click',load);
$('clear-filters').addEventListener('click',clearFilters);
document.querySelectorAll('[data-sort]').forEach(button=>button.addEventListener('click',()=>{sortDirection=sortKey===button.dataset.sort?-sortDirection:1;sortKey=button.dataset.sort;drawTable();}));
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>openFilter(button)));
document.querySelectorAll('[data-export]').forEach(button=>button.addEventListener('click',()=>exportChart(button.dataset.export)));
document.querySelectorAll('[data-clear-selection]').forEach(button=>button.addEventListener('click',()=>{selectedPolls[button.dataset.clearSelection]=null;button.dataset.clearSelection==='trackers'?drawMain():drawState();}));
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeFilter();});
document.addEventListener('click',event=>{if(!event.target.closest('#column-menu')&&!event.target.closest('[data-filter]'))closeFilter();});
load();
