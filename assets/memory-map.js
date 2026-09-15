/* Local grouping from shared tags/themes. No external services. */
function buildMemoryNetwork(entries) {
  const nodes=entries.map(e=>({...e,date:(e.timestamp||'').slice(0,10),themes:e.themes||[],tags:e.tags||[]}));
  const features=n=>new Set([...n.themes,...n.tags].map(v=>String(v).trim().toLowerCase()).filter(Boolean));
  const sets=new Map(nodes.map(n=>[n.id,features(n)])), index=new Map(), pairs=new Map();
  nodes.forEach(n=>sets.get(n.id).forEach(f=>{if(!index.has(f))index.set(f,[]);index.get(f).push(n.id)}));
  // Bound comparisons for very large archives, keeping chronological neighbours.
  index.forEach(ids=>ids.forEach((id,i)=>ids.slice(i+1,i+121).forEach(other=>{
    const key=[id,other].sort().join('|'); if(pairs.has(key))return;
    const a=sets.get(id),b=sets.get(other),shared=[...a].filter(f=>b.has(f));
    const weight=shared.length/(a.size+b.size-shared.length);
    if(weight>=.25&&shared.length>=2)pairs.set(key,{source:id,target:other,weight,shared});
  })));
  return {nodes,edges:[...pairs.values()]};
}
function memoryCommunities(nodes,edges) {
  const adjacent=new Map(nodes.map(n=>[n.id,[]]));
  edges.forEach(e=>{adjacent.get(e.source)?.push([e.target,e.weight]);adjacent.get(e.target)?.push([e.source,e.weight])});
  const labels=new Map(nodes.map(n=>[n.id,n.id]));
  const order=[...nodes].sort((a,b)=>a.id.localeCompare(b.id));
  for(let pass=0;pass<8;pass++) {
    let changed=0;
    order.forEach(n=>{
      const votes=new Map();
      (adjacent.get(n.id)||[]).filter(([,w])=>w>=.4).sort((a,b)=>b[1]-a[1]).slice(0,8).forEach(([id,w])=>{const l=labels.get(id);votes.set(l,(votes.get(l)||0)+w)});
      const best=[...votes].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0];
      if(best&&best[0]!==labels.get(n.id)){labels.set(n.id,best[0]);changed++}
    });
    if(!changed)break;
  }
  const buckets=new Map();
  order.forEach(n=>{const key=labels.get(n.id);if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(n)});
  const clusters=[],solo=[];
  buckets.forEach(members=>{
    if(members.length<3){solo.push(...members);return}
    const counts=new Map();
    members.forEach(n=>new Set([...n.tags,...n.themes]).forEach(t=>counts.set(t,(counts.get(t)||0)+1)));
    const terms=[...counts].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).slice(0,2).map(([t])=>t);
    clusters.push({id:members.map(n=>n.id).sort()[0],name:terms.join(' & '),members:members.sort((a,b)=>b.date.localeCompare(a.date))});
  });
  return {clusters:clusters.sort((a,b)=>a.id.localeCompare(b.id)),solo};
}
function renderDotMemoryMap(state,host) {
  const esc=escapeHtml,palette=['#929e7e','#d39b67','#93a4b8','#bc929f','#b4a269','#a390af','#91a69d'];
  const period=state.period||'all',cutoff=new Date();cutoff.setMonth(cutoff.getMonth()-(period==='year'?24:3));
  const nodes=state.nodes.filter(n=>period==='all'||new Date(n.date)>=cutoff);
  const ids=new Set(nodes.map(n=>n.id)),edges=state.edges.filter(e=>ids.has(e.source)&&ids.has(e.target));
  const {clusters,solo}=memoryCommunities(nodes,edges);
  if(!nodes.length){host.innerHTML='<p class="empty">No memories in this period. <button id="atlas-all" class="btn">Show all time</button></p>';host.querySelector('button').onclick=()=>{state.period='all';renderMemoryConnections()};return}
  const selected=nodes.find(n=>n.id===state.selected)||nodes[0];state.selected=selected.id;
  const focus=clusters.find(c=>c.id===state.focusGroup);
  const height=760,width=1040,points=new Map(),hulls=[];
  const groupPage=state.groupPage||0;
  const visibleClusters=focus?[focus]:clusters.slice(groupPage*9,groupPage*9+9);
  const page=state.atlasPage||0;
  if(focus){
    focus.members.slice(page*50,page*50+50).forEach((n,i)=>{const a=i*2.399963,r=40+Math.sqrt(i/50)*255;points.set(n.id,{...n,x:480+Math.cos(a)*r,y:360+Math.sin(a)*r,color:palette[clusters.indexOf(focus)%7]})});
  } else {
    visibleClusters.forEach((c,i)=>{
      const columns=visibleClusters.length<=4?2:3,rows=Math.ceil(visibleClusters.length/columns);
      const x=180+(i%columns)*(680/Math.max(1,columns-1))+(i%2?15:-15),y=155+Math.floor(i/columns)*(420/Math.max(1,rows-1))+(i%3-1)*20;
      const rx=Math.min(145,450/columns),ry=Math.min(118,240/Math.max(1,rows)),color=palette[(groupPage*9+i)%7];
      hulls.push({...c,x,y,rx,ry,color});
      const members=[...c.members.filter(n=>n.id===selected.id),...c.members.filter(n=>n.id!==selected.id)].slice(0,24);
      members.forEach((n,j)=>{const a=j*2.399963,r=Math.sqrt((j+.5)/members.length);points.set(n.id,{...n,x:x+Math.cos(a)*rx*.77*r,y:y+Math.sin(a)*ry*.73*r,color})});
    });
    solo.slice(0,20).forEach((n,i)=>points.set(n.id,{...n,x:90+(i%10)*95,y:690+Math.floor(i/10)*30,color:'#aaa79f'}));
  }
  const incident=edges.filter(e=>e.source===selected.id||e.target===selected.id).sort((a,b)=>b.weight-a.weight);
  const byId=new Map(nodes.map(n=>[n.id,n]));
  const displayEdges=[],seen=new Set(),clusterOf=new Map(clusters.flatMap(c=>c.members.map(n=>[n.id,c.id])));
  [...edges].sort((a,b)=>b.weight-a.weight).forEach(e=>{
    if(!points.has(e.source)||!points.has(e.target))return;
    const a=clusterOf.get(e.source),b=clusterOf.get(e.target),key=a===b?e.source:[a,b].sort().join('|');
    if(!seen.has(key)){displayEdges.push(e);seen.add(key)}
  });
  incident.filter(e=>points.has(e.source)&&points.has(e.target)).slice(0,8).forEach(e=>{if(!displayEdges.includes(e))displayEdges.push(e)});
  const mainPoint=points.get(selected.id);
  const curve=(a,b)=>'M '+a.x+' '+a.y+' Q '+((a.x+b.x)/2+25)+' '+((a.y+b.y)/2-28)+' '+b.x+' '+b.y;
  host.innerHTML=`<div class="dotmap-toolbar"><div><span class="eyebrow">CONNECTIONS, AS THEY GROW</span><p>${nodes.length} memories · ${clusters.length} emerging groups · ${solo.length} individual memories</p></div><div class="dotmap-controls"><select id="atlas-period" aria-label="Memory map period"><option value="all">All time</option><option value="year">Last two years</option><option value="quarter">Last three months</option></select><button class="btn" id="atlas-fit">Fit</button><button class="btn" id="atlas-zoom" aria-label="Zoom in">+</button></div></div><div class="dotmap-layout"><div class="dotmap-canvas"><svg class="dotmap-svg" viewBox="0 0 ${width} ${height}" aria-label="Evolving clusters of connected memories"><g class="dotmap-world">
  ${hulls.map(c=>`<g role="button" tabindex="0" class="atlas-group" data-cluster="${esc(c.id)}" aria-label="Explore ${esc(c.name)}"><path d="M ${c.x-c.rx} ${c.y} C ${c.x-c.rx-20} ${c.y-c.ry}, ${c.x-10} ${c.y-c.ry-20}, ${c.x+c.rx*.5} ${c.y-c.ry*.8} S ${c.x+c.rx+40} ${c.y+c.ry*.55}, ${c.x+c.rx*.45} ${c.y+c.ry} S ${c.x-c.rx-25} ${c.y+c.ry*.8}, ${c.x-c.rx} ${c.y}" fill="${c.color}" fill-opacity=".075" stroke="${c.color}" stroke-opacity=".18"/><text x="${c.x}" y="${c.y-c.ry-22}" text-anchor="middle" class="dotmap-cluster-title" fill="#514b40">${esc(c.name)}<tspan x="${c.x}" dy="18" class="dotmap-count" fill="#9c9285">${c.members.length} moments · explore ↗</tspan></text></g>`).join('')}
  ${displayEdges.map(e=>{const a=points.get(e.source),b=points.get(e.target),active=e.source===selected.id||e.target===selected.id;return `<path d="${curve(a,b)}" fill="none" stroke="${active?'#c88a50':'#b9afa0'}" stroke-width="${active?1.5:.8}" opacity="${active?.65:.23}"/>`}).join('')}
  ${[...points.values()].map(p=>`<g role="button" tabindex="0" class="dotmap-node" data-memory="${esc(p.id)}" aria-label="${esc(p.title)} — ${esc(p.date)}"><title>${esc(p.date+' · '+p.title)}</title><circle cx="${p.x}" cy="${p.y}" r="13" fill="transparent"/><circle cx="${p.x}" cy="${p.y}" r="${p.id===selected.id?11:5+(p.intensity||3)/3}" fill="${p.id===selected.id?'#e29854':p.color}" stroke="#fff9ef" stroke-width="${p.id===selected.id?3:1}"/></g>`).join('')}
  ${mainPoint?`<g pointer-events="none"><rect x="${Math.min(mainPoint.x+16,790)}" y="${mainPoint.y-14}" width="230" height="28" rx="12" fill="#fffcf6"/><text x="${Math.min(mainPoint.x+25,799)}" y="${mainPoint.y+4}" font-size="12" fill="#4b4337">${esc(fmtDateShort(selected.date)+' · '+selected.title.replace(/^\[Sample\]\s*/,'').slice(0,26))}</text></g>`:''}
  ${!focus&&solo.length?'<text x="60" y="657" font-size="12" fill="#928b80">Not connected to a group yet</text>':''}</g></svg><div class="dotmap-legend"><span>Groups emerge from shared topics</span><span>${focus?'Showing '+(page*50+1)+'–'+Math.min(page*50+50,focus.members.length)+' of '+focus.members.length:'Up to 24 dots per group · open a group to explore all'}</span><button class="text-action" id="atlas-back">${focus?'← All groups':'Reset selection'}</button>${focus&&focus.members.length>50?'<button class="text-action" id="atlas-next">Next memories →</button>':''}</div></div><aside class="dotmap-detail"><span class="eyebrow">SELECTED MEMORY</span><time>${esc(fmtDateShort(selected.date))} · ${esc(selected.emotion||'')}</time><h2>${esc(selected.title.replace(/^\[Sample\]\s*/,''))}</h2><p>${esc((selected.text||selected.summary||'').replace(/^Fictional sample entry[^\n]*\n*/,'').slice(0,170))}</p><button class="btn btn-primary" id="dotmap-open">Read entry ↗</button><div class="dotmap-related-heading">${incident.length} connected memories</div><div class="dotmap-related">${incident.slice(0,100).map(e=>{const n=byId.get(e.source===selected.id?e.target:e.source);return `<button data-memory="${esc(n.id)}"><time>${esc(fmtDateShort(n.date))}</time><strong>${esc(n.title.replace(/^\[Sample\]\s*/,''))}</strong><small>${esc(e.shared.join(' · '))}</small></button>`}).join('')||'<p>A moment of its own. Connections can emerge as you write.</p>'}</div></aside></div>`;
  if(!focus&&clusters.length>9){const more=document.createElement('button');more.className='text-action';more.textContent='More groups →';more.onclick=()=>{state.groupPage=(groupPage+1)%Math.ceil(clusters.length/9);renderMemoryConnections()};host.querySelector('.dotmap-legend').append(more)}
  host.querySelector('#atlas-period').value=period;
  host.querySelector('#atlas-period').onchange=e=>{state.period=e.target.value;state.focusGroup=null;state.groupPage=0;renderMemoryConnections()};
  host.querySelectorAll('[data-memory]').forEach(el=>{
    const choose=()=>{state.selected=el.dataset.memory;const c=clusters.find(c=>c.members.some(n=>n.id===state.selected));if(focus&&c?.id!==focus.id)state.focusGroup=null;renderMemoryIndex();renderMemoryConnections()};
    el.onclick=choose;el.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();choose()}};
  });
  host.querySelectorAll('[data-cluster]').forEach(el=>{const choose=()=>{state.focusGroup=el.dataset.cluster;state.atlasPage=0;renderMemoryConnections()};el.onclick=choose;el.onkeydown=e=>{if(e.key==='Enter')choose()}});
  host.querySelector('#atlas-back').onclick=()=>{state.focusGroup=null;state.atlasPage=0;renderMemoryConnections()};
  host.querySelector('#atlas-next')?.addEventListener('click',()=>{state.atlasPage=(page+1)%Math.ceil(focus.members.length/50);renderMemoryConnections()});
  host.querySelector('#dotmap-open').onclick=()=>openMemory(selected.id);
  const svg=host.querySelector('svg'),world=host.querySelector('.dotmap-world');let scale=1,tx=0,ty=0,drag=null;
  const transform=()=>world.setAttribute('transform',`translate(${tx} ${ty}) scale(${scale})`);
  host.querySelector('#atlas-fit').onclick=()=>{scale=1;tx=ty=0;transform()};
  host.querySelector('#atlas-zoom').onclick=()=>{scale=Math.min(3,scale*1.25);tx=520*(1-scale);ty=380*(1-scale);transform()};
  svg.onpointerdown=e=>{if(e.target.closest('[data-memory],[data-cluster]'))return;drag={x:e.clientX,y:e.clientY,tx,ty};svg.setPointerCapture(e.pointerId)};
  svg.onpointermove=e=>{if(!drag)return;const r=svg.getBoundingClientRect();tx=drag.tx+(e.clientX-drag.x)*width/r.width;ty=drag.ty+(e.clientY-drag.y)*height/r.height;transform()};
  svg.onpointerup=svg.onpointercancel=()=>drag=null;
}
