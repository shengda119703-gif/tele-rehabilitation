/* Approved V1.2.1 presentation adapter. Existing APIs remain authoritative. */
'use strict';
const MedicationV121 = (() => {
  const labels = {taken:'已服用', skipped:'已跳过', unrecorded:'未记录'};
  const key = r => `${r.medId}|${r.date}|${r.time}`;
  const medicines = s => s?.profile?.profile?.medicationRecords || [];
  const dailyData = s => s?.dailyProduct || {};
  function validDate(v) {
    if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
    const d = new Date(v + 'T12:00:00');
    return d.getFullYear() > 0 && `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` === v;
  }
  function arrangements(s, day) {
    const data = dailyData(s), out = [];
    for (const med of medicines(s)) {
      const plan = data.medSchedules?.[med.id];
      if (med.status !== 'active' || !plan || day < plan.start || (plan.end && day > plan.end)) continue;
      for (const time of plan.times || []) {
        const r = {medId:med.id, date:day, time, med};
        out.push({...r, status:data.doses?.[key(r)]?.status ?? 'unrecorded'});
      }
    }
    return out.sort((a,b) => a.time.localeCompare(b.time));
  }
  function records(s) {
    // The backend's correction snapshot can use today's drug fields. Retain the
    // earliest available audit snapshot for the original occurrence's display.
    const originals = new Map();
    for (const item of [...(dailyData(s).doseAudit || [])].reverse()) {
      const r = item.record;
      if (r && !originals.has(key(r))) originals.set(key(r), r);
    }
    return Object.values(dailyData(s).doses || {}).map(r => {
      const original = originals.get(key(r));
      return {...r, medName:original?.medName ?? r.medName, dose:original?.dose ?? r.dose};
    }).sort((a,b) => b.date.localeCompare(a.date) || a.time.localeCompare(b.time));
  }
  const step = (i, dx, dy, count) => Math.max(0, Math.min(Math.max(0,count-1), i + (Math.abs(dx)>=35 && Math.abs(dx)>Math.abs(dy)*1.1 ? dx<0?1:-1 : 0)));
  function wheelStep(gesture,i,dx,dy,count,now) {
    if(Math.abs(dx)<=Math.abs(dy)*1.1)return i;
    if(now-gesture.at>180){gesture.moved=false;gesture.sum=0;}
    gesture.at=now;
    if(gesture.moved)return i;
    gesture.sum+=dx;
    if(Math.abs(gesture.sum)<35)return i;
    gesture.moved=true;
    return Math.max(0,Math.min(Math.max(0,count-1),i+(gesture.sum>0?1:-1)));
  }
  const initial = rows => Math.max(0, rows.findIndex(r => r.status === 'unrecorded'));
  const question = context => context === 'drug'
    ? '怎样理解已经填写的服用说明？请解释一般含义，不给出处方或剂量建议。'
    : '怎样理解服药记录中的“已服用”“已跳过”和“未记录”？';
  function savedMatches(s, operation, p) {
    const data = dailyData(s);
    if (operation === 'dose') return data.doses?.[key(p)]?.status === p.status;
    if (operation === 'medSchedule') {
      const r = data.medSchedules?.[p.medId];
      return !!r && JSON.stringify(r.times) === JSON.stringify([...new Set(p.times)].sort()) && r.start === p.start && r.end === p.end;
    }
    if (operation === 'medication.save') {
      const r = medicines(s).find(m => m.id === p.record.id);
      return !!r && ['id','name','dose','purpose','times','status'].every(k => r[k] === p.record[k]);
    }
    return medicines(s).find(m => m.id === p.id)?.status === p.status;
  }
  if (typeof document === 'undefined') return {arrangements,records,key,step,wheelStep,initial,validDate,question,savedMatches};

  const enc = encodeURIComponent;
  let owner=null, day='', incomingDay=null, selectedKey=null, currentHash='', epoch=0;
  let drafts=new Map(), scrolls=new Map(), filter='', historyTab='records', searchQ='', aiVisit=null, pending=null, errors=new Map();
  let wheelGesture={at:0,sum:0,moved:false};
  const routeParts = () => {
    try { return location.hash.slice(1).split('/').slice(1).map(decodeURIComponent); }
    catch (_) { return []; }
  };
  const mine = id => medicines(snapshot()).find(m => m.id === id);
  const statusName = s => Object.hasOwn(labels,s)?labels[s]:'状态待核对';
  const statusClass = s => Object.hasOwn(labels,s) ? s : 'unrecorded';
  const zh = d => validDate(d) ? `${Number(d.slice(5,7))}月${Number(d.slice(8))}日` : '日期待核对';
  const dayLabel = d => d === today() ? '今天' : zh(d);
  function dateOffset(d,n) {
    const t=new Date(d+'T12:00:00');t.setDate(t.getDate()+n);
    return `${t.getFullYear()}-${String(t.getMonth()+1).padStart(2,'0')}-${String(t.getDate()).padStart(2,'0')}`;
  }
  const button = (text, action, cls='btn primary') => `<button type="button" class="${cls}" data-med-action="${E(action)}">${text}</button>`;
  const head = (title, action='') => `<div class="backHeader"><button type="button" class="back" id="mv-back" aria-label="返回原页面">‹</button><h1>${E(title)}</h1>${action}</div>`;
  const wrap = content => `<div class="shell"><div class="scroller" id="mv-scroller"><div class="page">${content}</div></div></div>`;
  function reset() {
    if ($('#dialog')?.querySelector('#mv-confirm')) $('#dialog').close();
    owner=null;day=today();incomingDay=null;selectedKey=null;currentHash='';epoch++;
    drafts.clear();scrolls.clear();errors.clear();filter='';historyTab='records';searchQ='';aiVisit=null;pending=null;
    wheelGesture={at:0,sum:0,moved:false};
  }
  function selectDay(value) { if (validDate(value)) incomingDay=value; }
  function saveScroll() { const n=$('#mv-scroller');if(n)scrolls.set(currentHash || location.hash,n.scrollTop); }
  function go(target) {
    if(ui.busy || voiceStarting || recorder?.state==='recording'){say('请先完成当前操作。');return;}
    saveScroll();window.history.pushState({medicationV121:true},'',target?'#medication/'+target:'#medication');render();
  }
  function back() {
    if(ui.busy || voiceStarting || recorder?.state==='recording'){say('请先完成当前操作。');return;}
    saveScroll();
    if(window.history.state?.medicationV121)window.history.back();else go('');
  }
  function restoreAI() {
    if(!aiVisit)return;
    ui.draft=aiVisit.draft;ui.private=aiVisit.private;aiVisit=null;
  }
  window.addEventListener('hashchange',()=>{if(location.hash!=='#medication/ai')restoreAI();});
  window.addEventListener('popstate',()=>{if(location.hash!=='#medication/ai')restoreAI();});
  function top() {
    return `<div class="searchbar">${button('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/></svg>搜索我的药物','search','searchbtn')}<button type="button" class="aibtn" data-med-action="ai" aria-label="询问 AI">AI</button></div>`;
  }
  function tool(title,sub,target,asset,short) {
    return `<button type="button" class="tool ${target==='meds'?'design-med':'design-record'}" data-med-action="${target}" aria-label="${title}，${E(sub)}"><span class="tool-copy"><b>${title}</b><span class="tool-desc">${E(sub)}</span><span class="tool-desc-short">${E(short)}</span></span><span class="tool-art" aria-hidden="true"><img src="/static/medication-v121/${asset}.svg" alt="" width="90" height="90"></span></button>`;
  }
  function selection(rows) {
    const i=rows.findIndex(r=>key(r)===selectedKey);
    return i<0 ? initial(rows) : i;
  }
  function home() {
    const rows=arrangements(snapshot(),day), i=selection(rows), r=rows[i];
    const count=rows.filter(r=>r.status==='taken'||r.status==='skipped').length;
    const medCount=medicines(snapshot()).filter(m=>m.status==='active').length;
    return `${top()}<div class="heading"><h1>${E(dayLabel(day))}用药</h1><div class="dateNav"><button type="button" id="mv-prev-day" aria-label="前一天">‹</button><strong>${zh(day)}</strong><input id="mv-day" aria-label="选择日期" type="date" value="${day}"><button type="button" id="mv-next-day" ${day>=today()?'disabled':''} aria-label="后一天">›</button></div></div>
      <section class="hero dose-carousel" aria-label="选择服药安排并登记"><div class="heroTop"><span class="eyebrow">逐次登记 · ${E(dayLabel(day))}安排</span><span class="hero-count">已登记 <b>${count}/${rows.length}</b></span></div>
      ${r?`<div class="dose-swipe" id="mv-swipe" tabindex="0" role="group" aria-roledescription="可左右滑动的服药安排" aria-label="第${i+1}项，共${rows.length}项；${E(r.time)}，${E(r.med.name)}，${statusName(r.status)}"><div class="slideContent" id="mv-slide"><div class="selected-dose"><span class="slot-time">${E(r.time)}</span><span class="slot-index">${i+1} / ${rows.length}</span><span class="slot-state ${statusClass(r.status)}">${statusName(r.status)}</span></div><h2 class="slot-name">${E(r.med.name)}</h2><div class="slot-meta">${r.med.dose?'每次 '+E(r.med.dose):'剂量未填写'}</div></div></div>
      <div class="dose-control"><button type="button" class="side-btn" id="mv-prev" aria-label="上一项安排" ${i===0?'disabled':''}>‹</button><button type="button" class="bigpill" data-med-log="${i}" ${day>today()?'disabled':''}>${r.status==='unrecorded'?'登记本次':'查看 / 更正'}　›</button><button type="button" class="side-btn" id="mv-next" aria-label="下一项安排" ${i===rows.length-1?'disabled':''}>›</button></div>
      <div class="dose-pagination" role="group" aria-label="选择当日服药安排">${rows.map((r,j)=>`<button type="button" class="dose-dot ${j===i?'current':r.status==='taken'?'recorded':r.status==='skipped'?'skipped':''}" data-med-select="${j}" aria-label="第${j+1}项 ${E(r.time)} ${statusName(r.status)}" aria-current="${i===j}"></button>`).join('')}</div><div class="swipe-hint">左右滑动选择安排 · 登记需单独确认</div>`:
      `<div class="dose-empty"><h2>${medicines(snapshot()).length?'当天没有服药安排':'还没有添加药物'}</h2><p>${medicines(snapshot()).length?'可查看其他日期或编辑药物安排':'先建立药物，再设置服用时间'}</p>${button(medicines(snapshot()).length?'查看我的药物 ›':'添加药物 ›','meds','bigpill')}</div>`}</section>
      <div class="sectionRow"><h2>全部安排</h2><small>${rows.length?`${rows.length} 项 · 点击选择`:'未记录不代表漏服'}</small></div><div class="doseList">${rows.length?rows.map((r,j)=>`<div class="doseItem ${i===j?'focused':''}"><button type="button" class="selectDose" data-med-list-select="${j}" aria-label="选择 ${E(r.time)} ${E(r.med.name)}"><span class="timeCol">${E(r.time)}</span><span class="dosebody"><b>${E(r.med.name)}</b><span>${E(r.med.dose||'剂量未填写')}</span></span></button><button type="button" class="status ${r.status==='unrecorded'?'not':statusClass(r.status)}" data-med-log="${j}" ${day>today()?'disabled':''}>${r.status==='unrecorded'?'登记':statusName(r.status)+' ›'}</button></div>`).join(''):'<div class="empty" style="padding:20px 8px"><p>当天没有服药安排。<br>未记录不代表漏服。</p></div>'}</div>
      <div class="sectionRow"><h2>用药管理</h2></div><div class="tools-grid">${tool('我的药物',`${medCount} 种在用 · 管理`,'meds','my-drugs',`${medCount} 种在用`)}${tool('服药记录','已登记与更正记录','history','dose-records','历史与更正')}</div><p class="notice">时间安排 · 不是服药提醒服务</p>`;
  }
  function drugRow(m) {
    const s=dailyData(snapshot()).medSchedules?.[m.id];
    return button(`<span class="symbol" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 19a5 5 0 0 1 0-7l7-7a5 5 0 0 1 7 7l-7 7a5 5 0 0 1-7 0M8 9l7 7"/></svg></span><span class="txt"><b>${E(m.name)}</b><small>${E(m.dose||'剂量未填写')} · ${m.status==='active'?'在用':'已停用'} · ${s?.times?.length?E(s.times.join(' / ')):'未设置时间'}</small></span><span class="chev" aria-hidden="true">›</span>`,'detail/'+enc(m.id),'medRow');
  }
  function medList() {
    return `${head('我的药物',button('＋ 添加','new','minor'))}<div class="stack">${medicines(snapshot()).map(drugRow).join('')||`<div class="panel empty">暂无药品。${button('添加药物','new','btn primary full')}</div>`}</div><p class="notice">停用不会删除已登记历史 · 当前不支持系统提醒</p>`;
  }
  function detail(id) {
    const m=mine(id),s=dailyData(snapshot()).medSchedules?.[id];
    if(!m)return `${head('药品详情')}<p role="alert">药品记录不可用，请返回核对。</p>`;
    return `${head('药品详情',button('编辑','edit/'+enc(id),'minor'))}<div class="panel"><span class="tag ${m.status==='active'?'lime':''}">${m.status==='active'?'在用':'已停用'}</span><div class="cardTitle">${E(m.name)}</div>${[['每次剂量',m.dose],['用途',m.purpose],['服用说明',m.times]].map(([t,v])=>`<div class="labelGrid"><span>${t}</span><b>${E(v||'未填写')}</b></div>`).join('')}</div><div class="panel"><div class="row"><h3 style="margin:0">服用时间</h3>${button('编辑时间 ›','times/'+enc(id),'link')}</div>${s?.times?.length?`<div class="times">${s.times.map(t=>`<span class="time-chip">${E(t)}</span>`).join('')}</div><div class="sub">${zh(s.start)} 起${s.end?' · '+zh(s.end)+' 止':''} · 每日固定时间</div>`:'<p class="sub">尚未建立时间安排，药物资料已保存。</p>'}<p class="tiny">此处只保存计划时间，不会在关闭应用后发送提醒。</p></div><button type="button" id="mv-status" class="btn full ${m.status==='active'?'outline':'dark'}">${m.status==='active'?'标记停用':'恢复在用'}</button><div class="row" style="margin-top:13px">${button('查看该药已登记记录 ›','history/'+enc(id),'link')}${button('问 AI','ai/drug','link')}</div>`;
  }
  function formDraft(name,initialValue) {
    if(!drafts.has(name))drafts.set(name,initialValue);
    return drafts.get(name);
  }
  function errorBox() {
    const message=errors.get(location.hash) || (pending?'有一次保存结果尚待核对，请先核对记录。':'');
    return `<div class="mv-errors" id="mv-errors" ${message?'':'hidden'}><p class="error" role="alert">${E(message||'')}</p>${pending?button('核对保存状态','verify','btn outline full'):''}</div>`;
  }
  function medForm(id) {
    const m=mine(id);
    if(id&&!m)return `${head('编辑药物')}<p role="alert">药品记录不可用。</p>`;
    const f=formDraft('drug/'+(id||'new'),{id:m?.id || 'med-'+Date.now()+'-'+Math.random().toString(36).slice(2),name:m?.name||'',dose:m?.dose||'',purpose:m?.purpose||'',times:m?.times||'',status:m?.status||'active'});
    return `${head(id?'编辑药物':'添加药物')}<form id="mv-drug-form" novalidate><div class="panel">${[['name','药物名称 *',100,true],['dose','每次剂量',100,false],['purpose','用途（选填）',200,false]].map(([k,t,max,required])=>`<div class="field"><label for="mv-${k}">${t}</label><input id="mv-${k}" name="${k}" maxlength="${max}" ${required?'required':''} value="${E(f[k])}" data-med-field="${k}"></div>`).join('')}<div class="field"><label for="mv-notes">服用说明（选填）</label><textarea id="mv-notes" name="times" maxlength="100" data-med-field="times">${E(f.times)}</textarea></div>${errorBox()}<div class="callout">药物资料与服用时间分别保存。本页面不会给出剂量建议。</div></div><div class="foot"><button type="submit" class="btn primary full" ${pending||ui.busy?'disabled':''}>保存药物</button></div></form>`;
  }
  function timeForm(id) {
    const m=mine(id),s=dailyData(snapshot()).medSchedules?.[id];
    if(!m)return `${head('服用时间')}<p role="alert">药品记录不可用。</p>`;
    const f=formDraft('times/'+id,{times:[...(s?.times||[])],start:s?.start||today(),end:s?.end||'',timeDraft:''});
    return `${head('服用时间')}<form id="mv-time-form" novalidate><div class="panel"><h3>${E(m.name)}</h3><p class="sub">每日固定时间，最多 12 个，不会自动发送提醒。</p><div class="field"><label>已选时间</label><div class="times">${f.times.map((t,i)=>`<span class="time-chip">${E(t)}<button type="button" data-med-remove-time="${i}" aria-label="移除${E(t)}">×</button></span>`).join('')||'<span class="sub">尚未添加时间</span>'}</div></div><div class="field"><label for="mv-time-value">添加 HH:mm 时间</label><div class="btnrow"><input id="mv-time-value" name="timeDraft" type="text" placeholder="08:00" value="${E(f.timeDraft)}" data-med-field="timeDraft" style="min-width:0;flex:1;border:1px solid #dce2d8;border-radius:12px;padding:0 12px;font-size:13px"><button type="button" id="mv-add-time" class="btn dark">添加</button></div></div><div class="two"><div class="field"><label for="mv-start">开始日期</label><input id="mv-start" name="start" type="date" required value="${E(f.start)}" data-med-field="start"></div><div class="field"><label for="mv-end">结束日期（可空）</label><input id="mv-end" name="end" type="date" value="${E(f.end)}" data-med-field="end"></div></div>${m.status==='stopped'?'<p class="error">仅在用药物可保存新的时间安排。</p>':''}${errorBox()}</div><div class="callout">此处是时间安排，不是手机通知。取消不影响已经保存的药物资料。</div><div class="foot"><button type="submit" class="btn primary full" ${pending||ui.busy||m.status!=='active'?'disabled':''}>保存时间安排</button></div></form>`;
  }
  function occurrence(parts) {
    const [medId,date,time]=parts;
    return records(snapshot()).find(r=>r.medId===medId&&r.date===date&&r.time===time)
      || arrangements(snapshot(),date).find(r=>r.medId===medId&&r.time===time);
  }
  function logForm(parts) {
    const r=occurrence(parts),old=r&&dailyData(snapshot()).doses?.[key(r)],m=r&&mine(r.medId);
    if(!r)return `${head('服药记录')}<p role="alert">该次记录或安排不可用，请返回核对。</p>`;
    const f=formDraft('dose/'+key(r),{status:null});
    return `${head(old?'更正记录':'登记服药')}<form id="mv-dose-form"><div class="panel"><div class="row"><span class="tag">计划时段</span><span class="tiny">${E(r.date)} ${E(r.time)}</span></div><div class="cardTitle">${E(old?r.medName:m?.name||'药品不可用')}</div><p class="sub">${E((old?r.dose:m?.dose)||'剂量未填写')} · 此处记录的是你的选择，非系统检测结果。</p>${old?`<div class="banner">已登记：${statusName(r.status)} · ${stamp(r.recordedAt)}。更正后保留历史。</div>`:''}<h3>本次登记</h3><div role="radiogroup" aria-label="本次登记状态">${Object.entries(labels).map(([s,t])=>`<button type="button" role="radio" aria-checked="${f.status===s}" class="choice simplified ${f.status===s?'selected':''}" data-med-status="${s}"><strong>${s==='unrecorded'?'更正为未记录':t}</strong><span class="check" aria-hidden="true">${f.status===s?'●':'○'}</span></button>`).join('')}</div>${r.date>today()?'<p class="error">未来日期不能登记。</p>':''}${!m?'<p class="error">药品已不可用，暂不能更正。</p>':''}${errorBox()}</div><div class="foot"><button type="submit" class="btn primary full" ${!f.status||pending||ui.busy||r.date>today()||!m?'disabled':''}>保存登记</button></div><p class="tiny">计划时间不等于实际服用时间；登记时间另行记录。</p></form>`;
  }
  function historyView() {
    const all=records(snapshot()),rs=all.filter(r=>!filter||r.medId===filter);
    const audit=(dailyData(snapshot()).doseAudit||[]).filter(r=>!filter||r.record.medId===filter);
    const drugs=new Map(medicines(snapshot()).map(m=>[m.id,m.name]));
    for(const r of all)if(!drugs.has(r.medId))drugs.set(r.medId,r.medName||'既有药品记录');
    const groups=[...new Set(rs.map(r=>r.date))].map(date=>{
      const entries=rs.filter(r=>r.date===date);
      return `<section class="history-group"><div class="history-date"><strong>${date===today()?'今天 · ':''}${E(date)}</strong><small>${entries.length} 项</small></div><div class="history-card">${entries.map((r)=>button(`<span class="h-time">${E(r.time)}</span><span class="h-info"><span class="h-name">${E(r.medName||'既有药品记录')}</span><span class="h-dose">${E(r.dose||'剂量未填写')}</span></span><span class="h-end"><span class="h-status ${statusClass(r.status)}">${statusName(r.status)}</span><span class="h-chevron" aria-hidden="true">›</span></span>`,'log/'+[r.medId,r.date,r.time].map(enc).join('/'),'history-entry')).join('')}</div></section>`;
    }).join('');
    return `${head('服药记录')}<div class="history-overview"><div class="history-summary"><b>${historyTab==='audit'?audit.length:rs.length}</b>${historyTab==='audit'?'次状态变更':'条状态记录'}</div></div><div class="history-tabs" role="tablist" aria-label="记录类型">${[['records','服药记录'],['audit','更正历史']].map(([k,t])=>`<button type="button" role="tab" data-med-history-tab="${k}" aria-selected="${historyTab===k}" class="${historyTab===k?'active':''}">${t}</button>`).join('')}</div><div class="history-tools"><select id="mv-filter" aria-label="筛选药物"><option value="">全部药物</option>${[...drugs].map(([id,name])=>`<option value="${E(id)}" ${filter===id?'selected':''}>${E(name)}</option>`).join('')}</select><span class="hint">${historyTab==='records'?'按计划日期查看':'按登记时间查看'}</span></div>${historyTab==='records'?(groups||'<div class="panel empty">暂无状态记录</div>'):`<div class="audit-card">${audit.map(a=>`<div class="audit-row"><span class="audit-dot"></span><span class="audit-copy"><b>${E(a.record.medName||'既有药品记录')}</b><small>${E(a.record.date)} ${E(a.record.time)} · ${statusName(a.record.previous)} → ${statusName(a.record.status)}</small></span><time>${stamp(a.at)}</time></div>`).join('')||'<div class="empty">暂无状态变更</div>'}</div>`}<p class="history-note">未记录不代表漏服。记录仅代表用户登记，不是自动检测结果。${historyTab==='audit'?'审计仅显示接口返回的最近 300 条。':''}</p>`;
  }
  function searchView() {
    return `${head('搜索药物',button('刷新','refresh','minor'))}<input class="searchInput" id="mv-search" type="search" placeholder="搜索已保存的药品名称" aria-label="搜索已保存的药品名称" value="${E(searchQ)}"><div id="mv-search-results" class="stack search-results"></div>`;
  }
  function refreshSearch() {
    $('#mv-search-results').innerHTML=medicines(snapshot()).filter(m=>m.name.toLowerCase().includes(searchQ.toLowerCase())).map(drugRow).join('')||'<div class="empty">未找到已保存的药物</div>';
    bindActions();
  }
  async function write(operation,payload,message) {
    if(ui.busy||pending)return false;
    const token=epoch,origin=location.hash,localOwner=owner;
    errors.delete(origin);
    const fields=[...document.querySelectorAll('#content form input,#content form textarea,#content form select')].map(n=>[n,n.disabled]);
    fields.forEach(([n])=>n.disabled=true);
    let ok,requestError;
    try { ok=await act(async()=>{
      try { return await (['dose','medSchedule'].includes(operation)?daily(operation,payload):post(operation,payload)); }
      catch(error){requestError=error;throw error;}
    },message); }
    finally { fields.forEach(([n,disabled])=>{if(n.isConnected)n.disabled=disabled;}); }
    if(token!==epoch||owner!==localOwner)return false;
    if(!ok){
      const error=$('#message').textContent;
      errors.set(origin,error);
      if(requestError?.status>=500 || /超时|断开|没有正常响应|保存失败/.test(error))pending={operation,payload,origin};
      if(location.hash===origin)render();
      return false;
    }
    await load();
    if(token!==epoch||owner!==localOwner)return false;
    if(!ui.snapshot){
      pending={operation,payload,origin};
      errors.set(origin,'服务端已确认保存，但暂时无法刷新。请先核对记录，避免重复提交。');
      return false;
    }
    return true;
  }
  async function verify() {
    const expected=pending,token=epoch;
    if(!expected||ui.busy)return;
    await load();
    if(!ui.snapshot||epoch!==token||pending!==expected)return;
    const matches=savedMatches(snapshot(),expected.operation,expected.payload);
    pending=null;
    errors.set(expected.origin,matches?'已核对：服务端已有这些记录。无需重复保存。':'当前记录尚未显示此次修改，请核对后再保存。');
    if(matches){
      const p=expected.payload;
      if(expected.operation==='dose')drafts.delete('dose/'+key(p));
      if(expected.operation==='medSchedule')drafts.delete('times/'+p.medId);
      if(expected.operation==='medication.save'){
        drafts.delete('drug/new');drafts.delete('drug/'+p.record.id);
      }
      selectedKey=null;
      if(location.hash===expected.origin){
        if(expected.operation==='medication.save'){
          if(expected.origin.startsWith('#medication/edit/'))back();
          else {window.history.replaceState(window.history.state,'','#medication/detail/'+enc(p.record.id));render();}
        }else if(expected.operation==='medication.status'){
          if($('#dialog').querySelector('#mv-confirm'))$('#dialog').close();render();
        }else back();
      }else render();
      say('已核对：服务端已有这些记录。无需重复保存。');
    }else render();
  }
  function bindActions() {
    document.querySelectorAll('[data-med-action]').forEach(n=>n.onclick=()=>{
      const target=n.dataset.medAction;
      if(target==='verify'){verify();return;}
      if(target==='refresh'){load();return;}
      if(target.startsWith('history')){filter=target.split('/')[1]?decodeURIComponent(target.split('/')[1]):'';historyTab='records';go('history');return;}
      if(target.startsWith('ai')){
        if(ui.busy||voiceStarting||recorder?.state==='recording'){say('请先完成当前操作。');return;}
        aiVisit={draft:ui.draft,private:ui.private};ui.draft=question(target==='ai/drug'?'drug':'home');go('ai');return;
      }
      go(target);
    });
  }
  function choose(i,scrollToCard=false) {
    const rows=arrangements(snapshot(),day);
    if(!rows[i])return;
    saveScroll();selectedKey=key(rows[i]);render();
    if(scrollToCard)$('#mv-scroller').scrollTop=0;
  }
  function bindHome() {
    const rows=arrangements(snapshot(),day),i=selection(rows);
    bind('mv-prev-day',()=>{day=dateOffset(day,-1);selectedKey=null;render();});
    bind('mv-next-day',()=>{if(day<today()){day=dateOffset(day,1);selectedKey=null;render();}});
    $('#mv-day').onchange=e=>{if(validDate(e.target.value)){day=e.target.value;selectedKey=null;render();}};
    bind('mv-prev',()=>choose(i-1));bind('mv-next',()=>choose(i+1));
    document.querySelectorAll('[data-med-select]').forEach(n=>n.onclick=()=>choose(Number(n.dataset.medSelect)));
    document.querySelectorAll('[data-med-list-select]').forEach(n=>n.onclick=()=>choose(Number(n.dataset.medListSelect),true));
    document.querySelectorAll('[data-med-log]').forEach(n=>n.onclick=()=>{
      const r=rows[Number(n.dataset.medLog)];
      if(r && r.date<=today())go('log/'+[r.medId,r.date,r.time].map(enc).join('/'));
    });
    const el=$('#mv-swipe'),slide=$('#mv-slide');if(!el)return;
    let down=null;
    const resetSlide=()=>{slide.style.transform='';slide.style.transition='';};
    el.onpointerdown=e=>{if(!e.isPrimary||(e.pointerType==='mouse'&&e.button!==0))return;down={x:e.clientX,y:e.clientY,id:e.pointerId};};
    el.onpointermove=e=>{if(!down||down.id!==e.pointerId)return;const dx=e.clientX-down.x,dy=e.clientY-down.y;if(Math.abs(dx)>Math.abs(dy)+8){el.setPointerCapture(e.pointerId);slide.style.transition='none';if(!matchMedia('(prefers-reduced-motion: reduce)').matches)slide.style.transform=`translateX(${Math.max(-42,Math.min(42,dx*.35))}px)`;}};
    el.onpointerup=e=>{if(!down||down.id!==e.pointerId)return;const start=down;down=null;const next=step(i,e.clientX-start.x,e.clientY-start.y,rows.length);if(next===i)resetSlide();else choose(next);};
    el.onpointercancel=()=>{down=null;resetSlide();};
    el.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();choose(e.key==='Home'?0:e.key==='End'?rows.length-1:i+(e.key==='ArrowRight'?1:-1));$('#mv-swipe')?.focus();}};
    el.addEventListener('wheel',e=>{
      if(Math.abs(e.deltaX)<=Math.abs(e.deltaY)*1.1)return;
      e.preventDefault();const next=wheelStep(wheelGesture,i,e.deltaX,e.deltaY,rows.length,performance.now());
      if(next!==i)choose(next);
    },{passive:false});
    const bar=$('.dose-pagination'),dot=bar?.querySelector('[aria-current="true"]');
    if(dot)bar.scrollLeft=Math.max(0,dot.offsetLeft-(bar.clientWidth-dot.offsetWidth)/2);
  }
  function bindForms(page,id,parts) {
    if(page==='new'||page==='edit') {
      const f=drafts.get('drug/'+(id||'new'));if(!f||!$('#mv-drug-form'))return;
      document.querySelectorAll('[data-med-field]').forEach(n=>n.oninput=()=>{f[n.dataset.medField]=n.value;});
      $('#mv-drug-form').onsubmit=async e=>{
        e.preventDefault();if(ui.busy||pending)return;
        if(!f.name.trim()){errors.set(location.hash,'请填写药物名称。');render();return;}
        const record={...f};for(const k of ['name','dose','purpose','times'])record[k]=record[k].trim();
        const origin=location.hash;
        if(await write('medication.save',{record},id?'药物资料已保存':'药品已保存，服用时间尚未设置')){
          drafts.delete('drug/'+(id||'new'));
          if(location.hash===origin){
            if(id)back();
            else {window.history.replaceState(window.history.state,'','#medication/detail/'+enc(record.id));render();}
          }
        }
      };
    } else if(page==='times') {
      const f=drafts.get('times/'+id);if(!f||!$('#mv-time-form'))return;
      document.querySelectorAll('[data-med-field]').forEach(n=>n.oninput=()=>{f[n.dataset.medField]=n.value;});
      bind('mv-add-time',()=>{
        if(ui.busy)return;
        const t=f.timeDraft.trim();
        if(!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(t)||f.times.includes(t)||f.times.length>=12){errors.set(location.hash,'请添加不重复的 HH:mm 时间，最多 12 个。');render();return;}
        f.times=[...f.times,t].sort();f.timeDraft='';errors.delete(location.hash);render();
      });
      document.querySelectorAll('[data-med-remove-time]').forEach(n=>n.onclick=()=>{if(!ui.busy){f.times.splice(Number(n.dataset.medRemoveTime),1);render();}});
      $('#mv-time-form').onsubmit=async e=>{
        e.preventDefault();if(ui.busy||pending)return;
        if(f.timeDraft.trim()){errors.set(location.hash,'请先添加填写的时间，再保存安排。');render();return;}
        if(!f.times.length||!validDate(f.start)||(f.end&&(!validDate(f.end)||f.end<f.start))){errors.set(location.hash,'请核对服用时间和开始、结束日期。');render();return;}
        const origin=location.hash;
        if(await write('medSchedule',{medId:id,times:[...f.times],start:f.start,end:f.end},'时间安排已保存')){
          drafts.delete('times/'+id);selectedKey=null;if(location.hash===origin)back();
        }
      };
    } else if(page==='log') {
      const r=occurrence(parts),f=r&&drafts.get('dose/'+key(r));if(!f||!$('#mv-dose-form'))return;
      document.querySelectorAll('[data-med-status]').forEach((n,i)=>{
        n.onclick=()=>{if(!ui.busy){f.status=n.dataset.medStatus;render();document.querySelectorAll('[data-med-status]')[i].focus();}};
        n.onkeydown=e=>{if(['ArrowRight','ArrowDown','ArrowLeft','ArrowUp'].includes(e.key)){e.preventDefault();const j=(i+(['ArrowRight','ArrowDown'].includes(e.key)?1:-1)+3)%3;document.querySelectorAll('[data-med-status]')[j].click();}};
      });
      $('#mv-dose-form').onsubmit=async e=>{
        e.preventDefault();if(!f.status||ui.busy||pending||r.date>today())return;
        const origin=location.hash;
        if(await write('dose',{medId:r.medId,date:r.date,time:r.time,status:f.status},'登记已保存')){
          drafts.delete('dose/'+key(r));selectedKey=null;if(location.hash===origin)back();
        }
      };
    }
  }
  function confirmStatus(id) {
    const m=mine(id);if(!m||ui.busy)return;
    const status=m.status==='active'?'stopped':'active';
    const d=modal(status==='stopped'?'标记停用？':'恢复在用？',`<p class="sub">只更改药品记录状态，不删除已登记历史。此操作不代表医生调整治疗方案。</p><p id="mv-dialog-error" role="alert" class="error" hidden></p><button type="button" id="mv-dialog-verify" class="btn outline full" hidden>核对保存状态</button><div class="btnrow"><button type="button" class="btn outline" id="mv-cancel">取消</button><button type="button" class="btn dark primary" id="mv-confirm">确认</button></div>`);
    bind('mv-cancel',()=>d.close());
    bind('mv-dialog-verify',verify);
    bind('mv-confirm',async()=>{
      if(ui.busy||pending)return;
      if(await write('medication.status',{id,status},'药物记录状态已更新')){if(d.open)d.close();}
      else if(d.open){const error=$('#mv-dialog-error');error.hidden=false;error.textContent=errors.get(location.hash)||$('#message').textContent;$('#mv-dialog-verify').hidden=!pending;}
    });
  }
  function ai() {
    if(!aiVisit)aiVisit={draft:ui.draft,private:ui.private};
    assistant();
    const content=$('#content'),nodes=[...content.childNodes];content.innerHTML=wrap('');
    const page=content.querySelector('.page');page.classList.add('mv-ai');for(const n of nodes)page.append(n);
    const heading=page.querySelector('.heading');heading.innerHTML=head('AI 助手');
    const note=document.createElement('p');note.className='sub';note.textContent='仅预填问题，发送前请核对。辅助理解，不作处方建议。';heading.after(note);
    if(!snapshot().modelAvailable){const availability=document.createElement('p');availability.className='sub';availability.setAttribute('role','status');availability.textContent='联网解释未配置，可使用现有记录对话。';note.after(availability);}
    bind('mv-back',back);
  }
  function failure(message,loading=false) {
    document.body.dataset.page='medication';document.body.dataset.medicationView='home';$('#nav').hidden=false;
    $('#content').innerHTML=wrap(`<div class="heading"><h1>用药</h1></div><section class="panel mv-loading"><div class="empty"><h3>${loading?'正在读取用药资料':'暂时无法读取'}</h3><p role="${loading?'status':'alert'}">${E(message)}</p>${loading?'':button('重新连接','refresh','btn primary full')}</div></section>`);
    bindActions();
  }
  function render() {
    const nextOwner=snapshot().profile?.ownerId+':'+snapshot().profile?.dataMode;
    if(!snapshot().profile?.ownerId){failure('请先连接本人档案。');return;}
    if(nextOwner!==owner){const proposed=incomingDay;if(owner){ui.draft='';ui.private=false;}reset();owner=nextOwner;day=proposed||today();}
    if(incomingDay){day=incomingDay;incomingDay=null;selectedKey=null;}
    const [page='home',id,...rest]=routeParts();
    if(currentHash && currentHash!==location.hash){const n=$('#mv-scroller');if(n)scrolls.set(currentHash,n.scrollTop);}
    currentHash=location.hash;
    if(page!=='ai')restoreAI();
    document.body.dataset.page='medication';document.body.dataset.medicationView=page==='home'?'home':'detail';
    const familyLabel=$('#nav a[href="#family"] .nav-label');if(familyLabel)familyLabel.textContent='家人';$('#nav').hidden=page!=='home';
    if(page==='ai')ai();
    else {
      const views={home,meds:medList,detail:()=>detail(id),new:()=>medForm(),edit:()=>medForm(id),times:()=>timeForm(id),log:()=>logForm([id,...rest]),history:historyView,search:searchView};
      $('#content').innerHTML=wrap((views[page]||home)());bind('mv-back',back);bindActions();
      if(page==='home')bindHome();
      if(page==='detail')bind('mv-status',()=>confirmStatus(id));
      bindForms(page,id,[id,...rest]);
      if(page==='history'){
        $('#mv-filter').onchange=e=>{filter=e.target.value;render();};
        document.querySelectorAll('[data-med-history-tab]').forEach(n=>n.onclick=()=>{historyTab=n.dataset.medHistoryTab;render();});
      }
      if(page==='search'){refreshSearch();$('#mv-search').oninput=e=>{searchQ=e.target.value;refreshSearch();};}
    }
    const scroller=$('#mv-scroller');if(scroller)scroller.scrollTop=scrolls.get(currentHash)||0;
  }
  return {render,failure,loading:()=>failure('请稍候…',true),reset,selectDay,isAI:()=>location.hash==='#medication/ai',arrangements,records,key,step,wheelStep,initial,validDate,question,savedMatches};
})();
if(typeof module!=='undefined')module.exports=MedicationV121;
else window.MedicationV121=MedicationV121;
