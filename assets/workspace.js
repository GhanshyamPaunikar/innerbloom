/* View composition and local preferences. No third-party requests or storage. */
(() => {
  const node = id => document.getElementById(id);
  let collection = [], calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
  let activeInsight = 'overview';
  const storage = {get:k=>{try{return localStorage.getItem(k)}catch{return null}},set:(k,v)=>{try{localStorage.setItem(k,v)}catch{}}};
  const prefs = {calm:storage.get('innerbloom.calmBackground')==='true',solid:storage.get('innerbloom.solidSurfaces')==='true'};
  function applyPrefs() {document.body.classList.toggle('calm-background',prefs.calm);document.body.classList.toggle('solid-surfaces',prefs.solid);}
  applyPrefs();
  const demo = !!document.querySelector('meta[name="innerbloom-demo"]');
  if (demo) { const label=document.createElement('div');label.className='demo-banner';label.textContent='Design preview · fictional journal · AI responses are simulated · changes are temporary';document.querySelector('.main').prepend(label); }
  const headings={write:'YOUR JOURNAL',entries:'YOUR COLLECTION',chat:'YOUR INNER CONVERSATION',insights:'A LITTLE PERSPECTIVE',graph:'THE THREADS BETWEEN',music:'LISTEN A LITTLE CLOSER',people:'YOUR CONNECTIONS',settings:'YOUR SPACE'};
  const now=new Date();
  node('today-label').textContent=now.toLocaleDateString([], {weekday:'short',day:'numeric',month:'short'});
  node('editor-date').textContent=now.toLocaleDateString([], {weekday:'long',day:'numeric',month:'long'});
  node('day-name').textContent=now.toLocaleDateString([], {weekday:'short'});
  node('day-number').textContent=String(now.getDate()).padStart(2,'0');
  node('month-label').textContent=now.toLocaleDateString([], {month:'long',year:'numeric'});
  node('menu-btn').setAttribute('aria-expanded','false');node('menu-btn').setAttribute('aria-controls','sidebar');
  const current=document.querySelector('.view.active')?.id.replace('view-','')||'write';
  node('section-eyebrow').textContent=headings[current];
  const [title,subtitle]=TITLES[current]();node('page-title').textContent=title;node('greeting').textContent=subtitle;
  document.querySelector('.nav-item.active')?.setAttribute('aria-current','page');
  document.addEventListener('innerbloom:view',ev=>{node('section-eyebrow').textContent=headings[ev.detail];node('focus-write').textContent='Focus ↗';node('focus-write').setAttribute('aria-pressed','false');});
  document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.go)));
  document.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',openPalette));
  node('focus-write').addEventListener('click',()=>{const on=document.body.classList.toggle('focus-writing');node('focus-write').textContent=on?'Leave focus ↙':'Focus ↗';node('focus-write').setAttribute('aria-pressed',String(on));});
  document.addEventListener('click',ev=>{if(node('sidebar').classList.contains('open')&&!ev.target.closest('.sidebar,#menu-btn')){node('sidebar').classList.remove('open');node('menu-btn').setAttribute('aria-expanded','false');}});
  // Make preserved custom controls operable without a pointer.
  document.addEventListener('keydown',ev=>{
    if((ev.key==='Enter'||ev.key===' ')&&ev.target.matches('[role="button"]:not(button)')) {ev.preventDefault();ev.target.click();return;}
    if(ev.key==='Escape'){node('sidebar').classList.remove('open');document.body.classList.remove('focus-writing');node('focus-write').textContent='Focus ↗';node('focus-write').setAttribute('aria-pressed','false');}
    if(ev.target.closest('input,textarea,select,[contenteditable="true"],[role="dialog"],.crisis-modal.active')||ev.metaKey||ev.ctrlKey||ev.altKey)return;
    const views={w:'write',e:'entries',c:'chat',i:'insights',g:'graph'};
    if(views[ev.key.toLowerCase()])switchView(views[ev.key.toLowerCase()]);
  });
  function selectInsight(key, focus=false) {
    activeInsight=key;
    document.querySelectorAll('[data-insight-tab]').forEach(b=>{const selected=b.dataset.insightTab===key;b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;if(selected&&focus)b.focus();});
    document.querySelectorAll('.insight-panel').forEach(p=>p.hidden=p.id!=='insight-'+key);
    if(key==='overview')requestAnimationFrame(()=>renderDailyChart(lastChartData));
  }
  document.querySelectorAll('[data-insight-tab]').forEach(b=>{
    b.addEventListener('click',()=>selectInsight(b.dataset.insightTab));
    b.addEventListener('keydown',ev=>{const tabs=[...document.querySelectorAll('[data-insight-tab]')],i=tabs.indexOf(b);let target;
      if(ev.key==='ArrowRight')target=(i+1)%tabs.length;if(ev.key==='ArrowLeft')target=(i-1+tabs.length)%tabs.length;if(ev.key==='Home')target=0;if(ev.key==='End')target=tabs.length-1;
      if(target!==undefined){ev.preventDefault();selectInsight(tabs[target].dataset.insightTab,true);}
    });
  });
  const chartObserver=new ResizeObserver(()=>{if(activeInsight==='overview'&&node('view-insights').classList.contains('active'))renderDailyChart(lastChartData);});chartObserver.observe(node('mood-line-wrap'));
  function adoptEntries(entries) {
    collection=[...entries].sort((a,b)=>new Date(b.timestamp)-new Date(a.timestamp));
    const latest=collection.slice(0,3), host=node('write-recent');host.replaceChildren();
    if(!latest.length)host.innerHTML='<p class="muted">Your first moment is waiting to be written.</p>';
    latest.forEach(e=>{const b=document.createElement('button');b.className='recent-moment';b.innerHTML=`<span>${escapeHtml(e.title||e.summary||'Untitled')}</span><small>${fmtDateShort(e.timestamp)}</small>`;b.addEventListener('click',()=>openEntry(e));host.append(b);});
    const evidence=node('insight-evidence');evidence.replaceChildren();
    if(!latest.length)evidence.innerHTML='<p class="muted">Your entries are the starting point. Write a little, then return here.</p>';
    latest.slice(0,2).forEach(e=>{const b=document.createElement('button');b.className='evidence-entry';b.innerHTML=`<header><h4>${escapeHtml(e.title||e.summary||'Untitled')}</h4><time>${fmtDateShort(e.timestamp)}</time></header><p>${escapeHtml(e.text||'')}</p>`;b.addEventListener('click',()=>openEntry(e));evidence.append(b);});
    renderCalendar();
  }
  async function refreshEntries() {try{const data=await api('/journal');adoptEntries(data.entries||[]);}catch{node('write-recent').innerHTML='<p class="muted">Start your local journal to see recent entries.</p>';node('insight-evidence').innerHTML='<p class="muted">Your local journal is currently offline.</p>';}}
  document.addEventListener('innerbloom:entries',ev=>adoptEntries(ev.detail));
  document.addEventListener('innerbloom:saved',refreshEntries);
  document.addEventListener('innerbloom:stats',ev=>{
    const stats=ev.detail,tags=(stats.top_tags||[]).slice(0,3);node('theme-count').textContent=String(tags.length).padStart(2,'0');
    const host=node('themes-summary');host.replaceChildren();
    if(!tags.length)host.innerHTML='<p class="muted">Your recurring topics will take shape as you write.</p>';
    tags.forEach(([tag,count],i)=>{const b=document.createElement('button');b.className='theme-item';b.innerHTML=`<small>${String(i+1).padStart(2,'0')}</small><strong>${escapeHtml(tag)}</strong><span>Appears in ${count} ${count===1?'entry':'entries'} ↗</span>`;b.addEventListener('click',()=>{node('search-input').value=tag;window.innerbloomDateFilter=null;currentEmotionFilter=null;switchView('entries');});host.append(b);});
  });
  const dateKey=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  function renderCalendar() {
    node('archive-month').innerHTML=`${calendarMonth.toLocaleDateString([], {month:'short'})}<span>${calendarMonth.getFullYear()}</span>`;
    const host=node('archive-calendar');host.replaceChildren();
    const first=(calendarMonth.getDay()+6)%7,n=new Date(calendarMonth.getFullYear(),calendarMonth.getMonth()+1,0).getDate();
    const dates=new Map();collection.forEach(e=>{const d=(e.timestamp||'').slice(0,10);dates.set(d,(dates.get(d)||0)+1);});
    for(let i=0;i<first;i++)host.append(document.createElement('span'));
    for(let day=1;day<=n;day++) {
      const d=new Date(calendarMonth.getFullYear(),calendarMonth.getMonth(),day),key=dateKey(d),b=document.createElement('button');b.textContent=day;
      b.classList.toggle('today',key===dateKey(now));b.classList.toggle('has-entry',dates.has(key));b.classList.toggle('selected',key===window.innerbloomDateFilter);
      b.setAttribute('aria-label',`${d.toLocaleDateString([], {month:'long',day:'numeric',year:'numeric'})}, ${dates.get(key)||0} entries`);b.setAttribute('aria-pressed',String(key===window.innerbloomDateFilter));
      b.addEventListener('click',()=>{window.innerbloomDateFilter=window.innerbloomDateFilter===key?null:key;renderEntries();renderCalendar();});host.append(b);
    }
    node('calendar-clear').hidden=!window.innerbloomDateFilter;
  }
  document.addEventListener('innerbloom:archive-date',ev=>{calendarMonth=new Date(ev.detail.slice(0,7)+'-01T12:00:00');renderCalendar();});
  node('calendar-prev').addEventListener('click',()=>{calendarMonth.setMonth(calendarMonth.getMonth()-1);renderCalendar();});
  node('calendar-next').addEventListener('click',()=>{calendarMonth.setMonth(calendarMonth.getMonth()+1);renderCalendar();});
  node('calendar-clear').addEventListener('click',()=>{window.innerbloomDateFilter=null;renderEntries();renderCalendar();});
  node('entry-sort').addEventListener('change',renderEntries);
  renderCalendar();refreshEntries();
  // Trap and restore focus for entry, command, and support overlays.
  let previousFocus=null, openOverlay=null;
  const overlays=['entry-modal','palette','crisis-modal'].map(node);
  const observer=new MutationObserver(()=>{
    const active=[...overlays].reverse().find(el=>el.classList.contains('active'));
    if(active&&active!==openOverlay){previousFocus=document.activeElement;openOverlay=active;requestAnimationFrame(()=>{const first=active.querySelector('input,button,[tabindex="0"]');first?.focus();});}
    else if(!active&&openOverlay){openOverlay=null;if(previousFocus?.isConnected)previousFocus.focus();}
  });overlays.forEach(el=>observer.observe(el,{attributes:true,attributeFilter:['class']}));
  document.addEventListener('keydown',ev=>{if(ev.key!=='Tab'||!openOverlay)return;const items=[...openOverlay.querySelectorAll('button:not(:disabled),input,textarea,select,[tabindex="0"],[contenteditable="true"],a[href]')].filter(el=>el.getClientRects().length);if(!items.length)return;const first=items[0],last=items.at(-1);if(ev.shiftKey&&document.activeElement===first){ev.preventDefault();last.focus();}else if(!ev.shiftKey&&document.activeElement===last){ev.preventDefault();first.focus();}});
  window.reflectWorkspace={settings(){
    if(node('pref-calm'))return;
    const host=node('settings-content'),section=document.createElement('section');section.className='settings-section';
    section.innerHTML=`<h3>A space that feels right</h3><p class="desc">Keep the sculptural setting, or turn the visual volume down. These preferences stay on this device.</p><div class="settings-choice"><label for="pref-calm">Quiet background<small>Replace the room with a simple warm surface.</small></label><input id="pref-calm" type="checkbox" ${prefs.calm?'checked':''}></div><div class="settings-choice"><label for="pref-solid">Opaque panels<small>More contrast, less transparency.</small></label><input id="pref-solid" type="checkbox" ${prefs.solid?'checked':''}></div>`;
    host.prepend(section);
    node('pref-calm').addEventListener('change',ev=>{prefs.calm=ev.target.checked;storage.set('innerbloom.calmBackground',prefs.calm);applyPrefs();});
    node('pref-solid').addEventListener('change',ev=>{prefs.solid=ev.target.checked;storage.set('innerbloom.solidSurfaces',prefs.solid);applyPrefs();});
  }};
  if(current==='settings'&&node('settings-content').children.length)window.reflectWorkspace.settings();
})();
