/* Approved family V1.0 presentation. Existing authorization APIs remain authoritative. */
'use strict';
const FamilyV10 = (() => {
  const categories=['health','rehab','medication'];
  const allowed = values => categories.filter(c=>Array.isArray(values)&&values.includes(c));
  const enc=encodeURIComponent;
  function reportCode(hash) {
    if(!hash.startsWith('#care='))return null;
    try { const value=decodeURIComponent(hash.slice(6));return value.length<=100?value:''; }
    catch (_) { return ''; }
  }
  const metricNames={steps:'活动步数',restingHr:'静息心率',spo2:'血氧',sleepHours:'睡眠时长',walkSpeed:'步行速度',weight:'体重',systolic:'收缩压',diastolic:'舒张压',bloodGlucose:'血糖',nightWakes:'夜间醒来'};
  const healthText=text=>String(text??'').replace(/^([A-Za-z]+):/,(_,key)=>(metricNames[key]||key)+':');
  function members(s) {
    return (s?.familyMembers||[]).map(m=>{
      const received=allowed(m.categories),offered=allowed(s?.dailyProduct?.grants?.[m.ownerId]);
      const rows=k=>received.includes(k)?(m[k==='medication'?'doses':k]||[]):[];
      return {id:m.ownerId,name:m.name||'关联家人',received,offered,
        health:rows('health').map(r=>({...r,text:healthText(r.text),time:time(r.timestamp)})),
        rehab:rows('rehab').map(r=>({...r,time:time(r.timestamp)})),
        doses:[...rows('medication')].sort((a,b)=>String(b.date).localeCompare(String(a.date))||String(b.time).localeCompare(String(a.time))).map(r=>({text:`${r.medName||'药品名称未记录'} · ${{taken:'已服用',skipped:'已跳过',unrecorded:'未记录'}[r.status]||'状态待核对'}`,time:`${r.date||'日期未记录'} ${r.time||''}`}))};
    });
  }
  const time = value => {
    if(!value)return '时间未记录';
    const d=new Date(typeof value==='number'?value*1000:value);
    return Number.isNaN(d.getTime())?'时间未记录':d.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  };
  const contactPayload = (p,c) => ({...p,familyContact:c.name,familyPhone:c.phone,communityDoctorPhone:c.doctor});
  const question = origin => origin==='concept'?'什么是健康记录的“家人可见”范围？请解释一般概念，不作诊断。':'家庭关系和健康信息共享权限有什么区别？';
  if(typeof document==='undefined')return {allowed,members,reportCode,contactPayload,question};
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const initial=()=>({page:'home',members:[],selected:'',modal:'',draft:[],dirty:false,bindCode:'',bindError:'',inviteCode:'',shareConsent:false,shares:[],shareCode:'',shareError:'',viewingShare:null,reportGuest:'',reportMessage:'',reportError:'',contact:{name:'',phone:'',doctor:''},contactDraft:null,contactError:'',search:'',stamp:'',offline:false,error:'',uncertain:false});
  let state=initial(),owner=null,epoch=0,readEpoch=0,currentHash='',scrolls=new Map(),aiVisit=null,viewCode='',reportReadKey='';
  const member=()=>state.members.find(m=>m.id===state.selected)||state.members[0];
  const truncate=(v,max=34)=>String(v).length>max?String(v).slice(0,max)+'…':String(v);
  const categoryText=arr=>arr.length?arr.map(x=>x==='health'?'健康':x==='rehab'?'康复':'用药').join(' · '):'未共享';
  function reset() {
    if($('#dialog')?.querySelector('[data-fv-modal]'))$('#dialog').close();
    restoreAI();state=initial();owner=null;epoch++;readEpoch++;scrolls.clear();currentHash='';viewCode='';reportReadKey='';
  }
  const busy=()=>ui.busy||voiceStarting||recorder?.state==='recording';
  const path=()=>location.hash.startsWith('#family/')?location.hash.slice(8):'home';
  function remember() {const n=$('#fv-screen');if(n&&currentHash)scrolls.set(currentHash,n.scrollTop);}
  function push(page) {
    if(busy()){say('请先完成当前操作。');return;}
    remember();history.pushState({familyV10:true},'',page==='home'?'#family':'#family/'+page);render();
  }
  function back() {
    if(busy()){say('请先完成当前操作。');return;}
    if(reportCode(location.hash)!==null){history.replaceState(null,'','#family');route();return;}
    remember();if(history.state?.familyV10)history.back();else push('home');
  }
  function restoreAI(){if(aiVisit){ui.draft=aiVisit.draft;ui.private=aiVisit.private;aiVisit=null;}}
  window.addEventListener('hashchange',()=>{if(location.hash!=='#family/ai'&&!busy())restoreAI();});
  window.addEventListener('popstate',()=>{if(location.hash!=='#family/ai'&&!busy())restoreAI();if(ui.page==='family')route();});
  function sync() {
    const s=snapshot(),id=s.profile?.ownerId+'|'+s.profile?.dataMode;
    if(owner!==id){reset();owner=id;}
    if(state.readError){state.error='';state.readError=false;}
    state.members=members(s);state.stamp=ui.familyReadAt?time(ui.familyReadAt):'读取时间待核对';
    if(!state.members.some(m=>m.id===state.selected))state.selected=state.members[0]?.id||'';
    const p=s.profile?.profile||{};state.contact={name:p.familyContact||'',phone:p.familyPhone||'',doctor:p.communityDoctorPhone||''};
  }
  async function refresh() {
    if(busy())return;
    await load();
    if(ui.homeConnection==='ready'&&ui.page==='family'){
      state.uncertain=false;state.error='';
      if(state.page==='reports')await readShares();
      if(state.page==='reportView')await readReport(viewCode);
      render();
    }
  }
  // No optimistic writes. If the response is lost, require a fresh read before another mutation.
  async function write(fn,done,message='已保存') {
    if(busy()||state.uncertain){say('请先刷新核对上一次操作结果。');return;}
    const e=epoch;let result,error;
    const ok=await act(async()=>{try{result=await fn();}catch(ex){error=ex;throw ex;}},'');
    if(e!==epoch||ui.page!=='family')return;
    if(!ok){if(error?.status===404&&state.page==='reportView'){state.viewingShare=null;state.reportError=error.message;}state.error=error?.message||'操作未完成';state.uncertain=!error?.status||error.status>=500;render();const d=$('#dialog');if(d.open&&d.querySelector('[data-fv-modal]')){let n=d.querySelector('.fv-modal-error');if(!n){n=document.createElement('p');n.className='error fv-modal-error';n.setAttribute('role','alert');d.querySelector('.sheet').append(n);}n.textContent=state.error+(state.uncertain?'；结果未确认，请取消弹窗后刷新核对。':'');}say(state.error);return;}
    state.error='';await done(result);say(message);
  }
  async function readShares() {
    const e=epoch,k=++readEpoch;state.sharesLoading=true;state.sharesError='';render();
    try {const r=await api('/care/shares',undefined,{timeout:15000});if(e!==epoch||k!==readEpoch)return;state.shares=Array.isArray(r)?r:[];}
    catch(ex){if(e!==epoch||k!==readEpoch)return;state.shares=[];state.sharesError=ex.message;}
    finally{if(e===epoch&&k===readEpoch){state.sharesLoading=false;if(ui.page==='family')render();}}
  }
  async function readReport(code) {
    const e=epoch,k=++readEpoch;if(viewCode!==code){state.reportGuest='';state.reportMessage='';}viewCode=code;reportReadKey=code;state.viewingShare=null;state.reportLoading=true;state.reportError='';render();
    try {if(!code)throw Error('请填写有效报告分享码。');const r=await api('/care/view',{code},{timeout:15000});if(e!==epoch||k!==readEpoch)return;state.viewingShare=r;}
    catch(ex){if(e!==epoch||k!==readEpoch)return;state.reportError=ex.message;}
    finally {if(e===epoch&&k===readEpoch){state.reportLoading=false;if(ui.page==='family')render();}}
  }
  function renderAI() {
    if(!aiVisit)aiVisit={draft:ui.draft,private:ui.private};
    assistant();const content=$('#content');const nodes=[...content.childNodes];
    content.innerHTML='<div class="app-frame"><div class="screen" id="fv-screen"><div class="page"></div></div></div>';
    const page=$('#fv-screen .page');nodes.forEach(n=>page.append(n));
    const link=$('#content .heading a');if(link){link.textContent='返回家人';link.href='#family';link.onclick=e=>{e.preventDefault();back();};}
    const h=$('#content .heading h1');if(h)h.textContent='AI 助手';
    const note=document.createElement('p');note.className='small-note';note.textContent='使用本人会话，不自动附上家人的姓名、数值或报告；回答仅辅助理解。';$('#content .composer').prepend(note);
  }
const ico={search:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><circle cx="10.6" cy="10.6" r="7"/><path d="m16 16 5.5 5.5"/></svg>`,person:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="7.7" r="3.5"/><path d="M4 21c0-5 3.6-8 8-8s8 3 8 8"/></svg>`,shield:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m12 2 8 4v6c0 6-3.6 8.7-8 10-4.4-1.3-8-4-8-10V6z"/><path d="m9 12 2 2 4-4"/></svg>`,heart:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 21s-9-5.6-9-12a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 6.4-9 12-9 12z"/></svg>`,file:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>`};
const clipart={connect:`<svg viewBox="0 0 90 94" fill="none"><circle cx="61" cy="23" r="17" fill="#E3EFCE"/><circle cx="22" cy="66" r="19" fill="#D7E5CD"/><path d="m34 61 26-34" stroke="#5F8758" stroke-width="5" stroke-linecap="round" stroke-dasharray="5 8"/><rect x="5" y="52" width="35" height="29" rx="12" fill="#19341E" transform="rotate(-12 5 52)"/><circle cx="22" cy="65" r="5.5" fill="#DFFF54"/><rect x="47" y="8" width="36" height="32" rx="12" fill="#DFFF54" transform="rotate(12 47 8)"/><circle cx="64" cy="23" r="6" fill="#35572A"/></svg>`,report:`<svg viewBox="0 0 90 94" fill="none"><rect x="19" y="19" width="60" height="59" rx="9" fill="#D7E4CE" transform="rotate(12 19 19)"/><rect x="11" y="10" width="57" height="66" rx="8" fill="#1E2C22" transform="rotate(-6 11 10)"/><path d="m22 60 9-13 9 7 10-21" stroke="#DFFF54" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 22h23M24 28h15" stroke="#87958A" stroke-width="3" stroke-linecap="round"/></svg>`,contact:`<svg viewBox="0 0 90 94" fill="none"><rect x="13" y="18" width="61" height="57" rx="12" fill="#DFEADC" transform="rotate(7 13 18)"/><rect x="8" y="12" width="61" height="64" rx="10" fill="#263A2A" transform="rotate(-9 8 12)"/><circle cx="35" cy="32" r="9" fill="#DFFF54"/><path d="M17 62c3-12 11-15 18-15s15 3 18 15" stroke="#DFFF54" stroke-width="6" stroke-linecap="round"/></svg>`,open:`<svg viewBox="0 0 90 94" fill="none"><rect x="10" y="21" width="63" height="46" rx="11" fill="#DCE8D2" transform="rotate(-10 10 21)"/><rect x="17" y="12" width="60" height="55" rx="10" fill="#203423"/><path d="M25 28h39M25 38h28M25 48h34" stroke="#97B894" stroke-width="4" stroke-linecap="round"/><circle cx="69" cy="66" r="14" fill="#DFFF54"/><path d="M63 66h12m-5-5 5 5-5 5" stroke="#203423" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>`};
const cats=[{id:'health',name:'健康近况',desc:'仅我标为家人可见的记录'},{id:'rehab',name:'康复完成',desc:'已保存的有限训练摘要'},{id:'medication',name:'用药记录',desc:'仅已登记状态，不是服药提醒'}];const catName=id=>cats.find(c=>c.id===id)?.name||id;
function title(s,action=''){return `<div class="page-header"><button class="back" aria-label="返回" data-fv-call="F.back()">‹</button><h1>${s}</h1>${action}</div>`}
function searchTop(){return `<div class="search-row"><button class="search-btn" data-fv-call="F.openSearch()">${ico.search}搜索已关联家人</button><button class="ai-square" aria-label="打开 AI 助手" data-fv-call="F.ai('home')">AI</button></div>`}
function home(){if(state.offline)return `<main class="page family-home">${searchTop()}<div class="topline"><h2>家人</h2></div><div class="feature offline"><div class="eyebrow">连接状态</div><h2>${ui.homeConnection==='loading'?'正在核验家人信息':'暂时无法读取家人信息'}</h2><p>${ui.homeConnection==='loading'?'正在重新读取授权与摘要。':esc(state.error||'请恢复连接后重新核验。无法读取不代表没有共享记录。')}</p><button class="main-btn" data-fv-call="F.refresh()">重新连接　›</button></div>${management()}</main>`;
const m=member();let main='';if(!m){main=`<div class="feature empty"><div class="eyebrow">家庭关系</div><h2>还没有关联家人</h2><p>邀请码关联，双方分别授权。</p><div class="button-row"><button class="main-btn" data-fv-call="F.inviteEntry('bind')">关联家人　›</button><button class="cta outline" data-fv-call="F.inviteEntry('generate')">我的邀请码</button></div></div>`}
else{const snapshot=m.received.includes('health')&&m.health.length?truncate(m.health[0].text,18):m.received.includes('medication')&&m.doses.length?'有已登记用药记录':m.received.includes('rehab')&&m.rehab.length?truncate(m.rehab[0].text,18):m.received.length?'已授权 · 暂无可见摘要':'对方尚未共享信息';main=`<section class="feature" aria-label="已关联成员"><div class="feature-head"><span class="eyebrow">已关联 · ${state.members.length} 位家人</span><span class="badge dark">${state.members.findIndex(x=>x.id===m.id)+1} / ${state.members.length}</span></div><div class="member-main"><div class="avatar" aria-hidden="true">${esc(m.name.slice(-1))}</div><div><h1>${esc(m.name)}</h1><p>收到的授权：${m.received.length?m.received.length+' 类':'暂无'}</p></div></div><div class="feature-mini"><span>${esc(snapshot)}</span><span>${esc(state.stamp)}</span></div><div class="feature-foot"><button class="main-btn" data-fv-call="F.openMember()">查看近况 <span class="arr">›</span></button><button class="secondary-btn" data-fv-call="F.openPermission()">共享权限</button></div>${state.members.length>1?`<div class="member-switch">${state.members.map(x=>`<button class="${x.id===m.id?'active':''}" aria-label="切换到${esc(x.name)}" data-fv-call="F.selectMember('${enc(x.id)}')"></button>`).join('')}</div>`:''}</section>`}
return `<main class="page family-home">${searchTop()}<div class="topline"><h2>家人近况</h2><button class="mini-link" data-fv-call="F.refresh()">刷新 ↻</button></div>${main}${m?`<div class="topline"><h2>共享权限</h2><button class="mini-link" data-fv-call="F.openPermission()">查看详情 ›</button></div><div class="split"><button class="permission-box" data-fv-call="F.openPermission()"><span class="minor">TA 共享给我</span><strong>${m.received.length?m.received.length+' 类可查看':'尚未共享'}</strong><span class="edge"><em>${categoryText(m.received)}</em></span></button><button class="permission-box accent" data-fv-call="F.openPermission()"><span class="minor">我共享给 TA</span><strong>${m.offered.length?m.offered.length+' 类已开放':'未授权'}</strong><span class="edge"><em>${categoryText(m.offered)}</em></span></button></div>`:''}<div class="topline"><h2>家人管理</h2></div>${management()}<div class="home-footnote">仅展示授权信息，非实时监测</div></main>`}
function management(){return `<div class="tools"><button class="tool-card" data-fv-call="F.inviteEntry('choose')"><span class="tool-txt"><b>关联家人</b><small>邀请码关联</small></span><span class="tool-visual">${clipart.connect}</span></button><button class="tool-card" data-fv-call="F.go('reports')"><span class="tool-txt"><b>共享报告</b><small>7天快照<br>独立分享</small></span><span class="tool-visual">${clipart.report}</span></button><button class="tool-card" data-fv-call="F.go('contact')"><span class="tool-txt"><b>联系人</b><small>本人联系方式</small></span><span class="tool-visual">${clipart.contact}</span></button><button class="tool-card" data-fv-call="F.go('reportOpen')"><span class="tool-txt"><b>查看分享</b><small>报告分享码</small></span><span class="tool-visual">${clipart.open}</span></button></div>`}
function detailCategory(m,id) {
  if(!m.received.includes(id))return '<div class="empty-note">对方尚未开放此类信息</div>';
  const rows=id==='health'?m.health:id==='rehab'?m.rehab:m.doses;
  if(!rows.length)return '<div class="empty-note">已开放类别，暂无可见记录</div>';
  return `<div class="section-list">${rows.slice(0,3).map(r=>`<div class="srow"><i class="dot" aria-hidden="true"></i><div class="srow-content"><strong>${esc(r.text)}</strong><small>${esc(r.time)} · ${id==='health'?'家人可见记录':id==='medication'?'用户登记状态':'已保存摘要'}</small></div></div>`).join('')}</div>`;
}
function memberDetail(){const m=member();if(!m)return home();return `<main class="page">${title('家人近况',`<button class="mini-link" data-fv-call="F.refresh()">刷新 ↻</button>`)}<div class="panel"><div class="member-heading"><div class="avatar">${esc(m.name.slice(-1))}</div><div><h2>${esc(m.name)}</h2><div class="sub">已关联 · ${esc(state.stamp)}</div></div></div><div class="divider"></div><div class="chipline">${m.received.length?m.received.map(i=>`<span class="chip">${catName(i)}</span>`).join(''):'<span class="chip dim">对方尚未授权</span>'}</div></div>${cats.map(c=>`<section class="panel"><div class="row section-row fv-style-f5a34f35"><h2 class="panel-title fv-style-ab79ea2b">${c.name}</h2>${c.id==='health'?`<button class="mini-link" data-fv-call="F.ai('concept')">问 AI ›</button>`:''}</div>${detailCategory(m,c.id)}</section>`).join('')}<div class="panel panel-tight"><button class="action-item" data-fv-call="F.openPermission()"><span class="item-copy"><strong>共享权限</strong><span>查看 TA 的授权 · 管理我授出的权限</span></span><span class="chev">›</span></button><button class="action-item" data-fv-call="F.unbindAsk()"><span class="item-copy"><strong>解除关联</strong><span>双方关系与分类授权将失效</span></span><span class="chev">›</span></button></div><p class="small-note">仅展示对方允许共享的有限摘要。记录不是实时监测，也不能代表完整健康状况。</p></main>`}
function permissionPage(){const m=member();if(!m)return home();return `<main class="page">${title('共享权限')}<div class="panel"><div class="member-heading"><div class="avatar">${esc(m.name.slice(-1))}</div><div><h2>${esc(m.name)}</h2><div class="sub">关联成员 · 双向授权独立</div></div></div></div><section class="panel"><div class="panel-title">TA 共享给我</div><div class="sub fv-style-b922c89f">由对方决定 · 仅供查看</div><div class="chipline">${m.received.length?m.received.map(c=>`<span class="chip">${catName(c)}</span>`).join(''):'<span class="chip dim">尚无授权类别</span>'}</div><div class="small-note fv-style-fa769ae0">健康记录还需标为家人可见；其他类别只展示有限摘要。</div></section><section class="panel"><div class="panel-title">我共享给 TA</div><div class="sub fv-style-b922c89f">选择允许 TA 查看我的哪些类别</div>${cats.map(c=>`<div class="setting"><div class="setting-body"><b>${c.name}</b><p>${c.desc}</p></div><button class="toggle ${state.draft.includes(c.id)?'active':''}" role="switch" aria-label="${c.name}" aria-checked="${state.draft.includes(c.id)}" data-fv-call="F.toggle('${c.id}')"></button></div>`).join('')}<div class="small-note">不自动共享完整档案。健康记录还需单独标记“家人可见”。</div>${state.dirty?'<p class="form-hint">有未保存的更改</p>':''}<div class="button-row"><button class="cta soft" data-fv-call="F.permissionCancel()">取消</button><button class="cta" data-fv-call="F.savePermission()" ${state.dirty?'':'disabled'}>保存权限</button></div></section><div class="unbinding">全部取消后保存，只撤销我授出的分类权限，不解除关系，也不会撤销独立报告链接。</div><button class="mini-link fv-style-c53ea1da" data-fv-call="F.unbindAsk()">解除与 ${esc(m.name)} 的关联　›</button></main>`}
function invitePage(){return `<main class="page">${title('关联家人')}<div class="panel"><div class="panel-title">输入家庭邀请码</div><p class="sub">向对方获取家庭邀请码。提交成功会直接建立关系，不会先显示对方身份预览。</p><div class="form-field"><label for="inv">8 位家庭邀请码</label><input id="inv" class="input" placeholder="输入 8 位邀请码" autocapitalize="characters" spellcheck="false" maxlength="8" required pattern="[A-Fa-f0-9]{8}" value="${esc(state.bindCode)}" data-fv-input="F.setBind(this.value)"></div>${state.bindError?`<div class="error" role="alert">${esc(state.bindError)}</div>`:''}<button class="cta" data-fv-call="F.bind()">确认关联</button><div class="small-note">仅适用于同一共享服务中的本人档案，不能使用手机连接码。关联后默认不共享健康数据。</div></div><div class="panel panel-tight"><button class="action-item" data-fv-call="F.go('inviteGenerate')"><span class="item-copy"><strong>生成我的家庭邀请码</strong><span>给另一位家人输入 · 15 分钟有效</span></span><span class="chev">›</span></button></div></main>`}
function inviteGenerate(){return `<main class="page">${title('我的家庭邀请码')}<section class="panel"><h2 class="panel-title">让家人输入此邀请码</h2>${state.inviteCode?`<div class="inset-code">${esc(state.inviteCode)}</div><p class="sub center-note">15 分钟有效 · 一次性使用</p>`:'<div class="empty-note fv-style-812b952e">尚未生成邀请码</div>'}<button class="cta" data-fv-call="F.generateInvite()">${state.inviteCode?'重新生成邀请码':'生成邀请码'}</button><p class="small-note">真实邀请码 15 分钟有效、一次性使用。重新生成会替换旧码；关闭本页不会自动取消已生成的邀请码。</p></section><div class="panel panel-tight"><button class="action-item" data-fv-call="F.go('invite')"><span class="item-copy"><strong>我有家人的邀请码</strong><span>使用对方提供的码建立关系</span></span><span class="chev">›</span></button></div></main>`}
function reportCreate(){return `<main class="page">${title('生成分享报告')}<div class="panel"><div class="panel-title">本次报告的分享范围</div><p class="sub">最近健康指标、在用药物和已保存评估与训练摘要。不含原始录像，创建后不更新。</p><div class="report-mark"><svg viewBox="0 0 145 85" fill="none"><rect x="54" y="9" width="73" height="62" rx="10" fill="#C3D8AF" transform="rotate(12 54 9)"/><rect x="28" y="8" width="77" height="67" rx="10" fill="#263B28" transform="rotate(-9 28 8)"/><path d="M43 28h35M43 39h27M43 52h22" stroke="#DFFF54" stroke-width="5" stroke-linecap="round"/><circle cx="116" cy="64" r="14" fill="#DFFF54"/><path d="m111 64 4 4 8-9" stroke="#234128" stroke-width="3" stroke-linecap="round"/></svg></div><label class="checkrow"><input type="checkbox" ${state.shareConsent?'checked':''} data-fv-input="F.consent(this.checked)"><span>我已确认分享范围，并同意生成有效期为 7 天的只读报告。</span></label><p class="small-note">知道有效分享码的人可访问快照；与家庭分类授权、是否关联家人无关。</p><button class="cta" ${!state.shareConsent?'disabled':''} data-fv-call="F.generateReport()">生成分享报告</button></div></main>`}
function reportOpen(){return `<main class="page">${title('查看分享报告')}<div class="panel"><div class="panel-title">输入报告分享码</div><div class="form-field"><label for="shareCode">分享码</label><input class="input" id="shareCode" placeholder="由分享人提供" value="${esc(state.shareCode)}" data-fv-input="F.shareInput(this.value)"></div>${state.shareError?`<div class="error" role="alert">${esc(state.shareError)}</div>`:''}<button class="cta" data-fv-call="F.openReport()">查看报告</button><p class="small-note">这是独立报告分享，不必先与发布者建立家人关系；仅能查看分享快照。</p></div></main>`}
function contact(){const c=state.contact;return `<main class="page">${title('本人联系人',`<button class="mini-link" data-fv-call="F.editContact()">编辑 ›</button>`)}<div class="panel"><div class="panel-title">已保存的联系人</div><div class="action-item"><span class="item-copy"><strong>家庭联系人</strong><span>${esc(c.name||'未填写')}</span></span></div><div class="action-item"><span class="item-copy"><strong>联系电话</strong><span>${esc(c.phone||'未填写')}</span></span></div><div class="action-item"><span class="item-copy"><strong>社区医生电话</strong><span>${esc(c.doctor||'未填写')}</span></span></div></div><div class="note-box">联系人是本人资料字段，不会自动读取已关联家人的电话，也不提供自动拨号或紧急求助功能。</div></main>`}
function contactEdit(){const c=state.contactDraft;return `<main class="page">${title('编辑联系人')}<div class="panel"><div class="form-field"><label>家庭联系人姓名</label><input class="input" placeholder="姓名" maxlength="40" aria-label="家庭联系人姓名" value="${esc(c.name||'')}" data-fv-input="F.contactInput('name',this.value)"></div><div class="form-field"><label>联系电话</label><input class="input" inputmode="tel" placeholder="电话号码" maxlength="30" aria-label="联系电话" value="${esc(c.phone||'')}" data-fv-input="F.contactInput('phone',this.value)"></div><div class="form-field"><label>社区医生电话</label><input class="input" inputmode="tel" placeholder="电话号码" maxlength="30" aria-label="社区医生电话" value="${esc(c.doctor||'')}" data-fv-input="F.contactInput('doctor',this.value)"></div>${state.contactError?`<div class="error">${esc(state.contactError)}</div>`:''}<button class="cta" data-fv-call="F.saveContact()">保存</button></div></main>`}
function searchPage(){const result=state.members.filter(x=>x.name.includes(state.search));return `<main class="page">${title('搜索家人')}<div class="form-field"><input class="input" aria-label="搜索已关联的家人" placeholder="搜索已关联的家人" value="${esc(state.search)}" data-fv-input="F.search(this.value)"></div><div class="panel panel-tight">${result.length?result.map(m=>`<button class="action-item" data-fv-call="F.chooseSearch('${enc(m.id)}')"><span class="item-copy"><strong>${esc(m.name)}</strong><span>已关联 · ${m.received.length} 类收到的授权</span></span><span class="chev">›</span></button>`).join(''):'<div class="empty-note">没有匹配的已关联家人</div>'}</div><p class="small-note">仅搜索当前已有的关联成员，不支持通过姓名或手机号查找其他账号。</p></main>`}
  function reports() {
    return `<main class="page">${title('共享报告')}<div class="report-card"><div class="body"><div class="report-tag">FAMILY REPORT</div><h2>单独分享健康报告</h2><p>七天只读快照。它不等于家人关系授权。</p></div><div class="report-art"><svg viewBox="0 0 145 133" fill="none"><rect x="60" y="14" width="73" height="102" rx="9" fill="#D8E6C8" transform="rotate(13 60 14)"/><rect x="46" y="5" width="74" height="107" rx="9" fill="#1C2A1E" transform="rotate(-9 46 5)"/><path d="m58 82 18-21 15 10 18-30" stroke="#DEFF54" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><path d="M61 28h31" stroke="#6A886A" stroke-width="5" stroke-linecap="round"/></svg></div></div><div class="section-head"><h2>报告管理</h2><button class="mini-link" data-fv-call="F.refresh()">刷新 ↻</button></div><div class="panel panel-tight"><button class="action-item" data-fv-call="F.go('reportCreate')"><span class="item-copy"><strong>生成分享报告</strong><span>每次需要明确同意 · 有效 7 天</span></span><span class="chev">›</span></button><button class="action-item" data-fv-call="F.go('reportOpen')"><span class="item-copy"><strong>查看别人分享的报告</strong><span>使用报告分享码 · 只读</span></span><span class="chev">›</span></button></div><div class="section-head"><h2>我分享的报告</h2><span class="muted">${state.shares.length} 份</span></div><div class="panel panel-tight">${state.sharesLoading?'<p role="status">正在读取…</p>':state.sharesError?`<p class="error" role="alert">${esc(state.sharesError)}</p>`:state.shares.length?state.shares.map(r=>`<div class="audit-entry"><div><strong>健康摘要 · 分享快照</strong><small>有效截止 ${esc(time(r.expires))}</small><small>与家庭分类授权独立 · ${r.notes.length} 条留言</small>${r.notes.map(n=>`<small>${esc(n.author)}（未核验）：${esc(n.text)}</small>`).join('')}</div><div><span class="badge ${r.active?'':'slate'}">${r.active?'有效':'已失效'}</span>${r.active?`<button class="mini-link" data-fv-call="F.revokeAsk('${enc(r.id)}')">撤销</button>`:''}</div></div>`).join(''):'<div class="empty-note">目前没有已生成的分享报告</div>'}</div><p class="small-note">解除家人关系不会自动撤销这里的报告链接。已生成的报告码无法从列表重新获取，请在生成时妥善保存。</p></main>`;
  }
  function reportCreated() {
    const r=state.createdReport;
    return `<main class="page">${title('报告已创建')}<div class="panel"><span class="badge">只读快照</span><h2 class="panel-title fv-style-d108cd54">分享报告码</h2><div class="inset-code fv-report-code">${esc(r?.code||'当前没有新生成的报告码')}</div>${r?`<p class="sub">有效截止 ${esc(time(r.expires))}</p><label class="form-field">报告链接<input class="input" readonly aria-label="报告链接" value="${esc(location.origin+location.pathname+'#care='+enc(r.code))}"></label><p class="small-note">链接包含访问凭据。仅分享给你确认的对象，不公开发布。</p>`:''}<button class="cta" data-fv-call="F.finishShare()">管理分享报告</button></div></main>`;
  }
  function reportView() {
    const r=state.viewingShare, report=r?.report;
    const list=(label,rows)=>`<section class="panel"><h2 class="panel-title">${label}</h2>${rows.length?rows.map(x=>`<div class="audit-entry"><div><strong>${esc(x.text)}</strong><small>${esc(x.time)}</small></div></div>`).join(''):'<div class="empty-note">本次快照暂无记录</div>'}</section>`;
    const health=(report?.health?.measurements||[]).map(m=>({text:`${metricNames[m.metric]||m.metric}: ${m.value} ${m.unit||''}`,time:time(m.timestamp)}));
    const meds=(report?.health?.medications||[]).map(m=>({text:m.name,time:[m.dose,m.times].filter(Boolean).join(' · ')||'说明未填写'}));
    const records=(report?.records||[]).map(r=>({text:`${r.label||r.exercise} · ${{training:'训练',assessment:'评估',posture:'体态',fitness:'健身'}[r.mode]||r.mode}`,time:[time(r.created_at),r.side==='left'?'左侧':r.side==='right'?'右侧':'侧别未记录',r.source_kind==='REPLAY_FILE'?'录像来源':r.source_kind==='LIVE_CAMERA'?'实时来源':'来源未记录',r.summary?.completed!=null?String(r.summary.completed)+' 次':'次数未记录',r.summary?.motion_range?.range_deg!=null?'活动幅度 '+r.summary.motion_range.range_deg+'°':'',r.mode==='training'?(r.summary?.plan_completed===true?'目标已核实完成':'目标完成未核实'):'',r.feedback?'疼痛 '+r.feedback.pain+' / 疲劳 '+r.feedback.fatigue:'',...(Array.isArray(r.summary?.metrics)?r.summary.metrics.filter(m=>m.valid).map(m=>m.label+' '+m.value+' '+m.unit):[])].filter(Boolean).join(' · ')}));
    return `<main class="page">${title('分享报告', '<button class="mini-link" data-fv-call="F.refreshReport()">刷新 ↻</button>')}<div class="panel"><span class="badge">只读快照</span><h2 class="panel-title fv-style-5747f4ee">健康报告摘要</h2><p class="sub">内容是生成时的快照 · 链接有效期 7 天</p>${state.reportLoading?'<p role="status">正在读取报告…</p>':!report?`<div class="error" role="alert">${esc(state.reportError||'报告未读取')}</div>`:''}</div>${report?list('健康指标',health)+list('在用药物',meds)+list('已保存评估与训练',records)+(report.next_step?.title?`<p class="small-note">${esc(report.next_step.title)} · 分享时摘要，不是实时监护。</p>`:''):''}${report?`<div class="section-head"><h2>关怀留言</h2><span class="muted">${r.notes.length} / 30</span></div><div class="panel"><div class="form-field"><label for="fv-author">称呼（身份未核验）</label><input id="fv-author" class="input" maxlength="40" value="${esc(state.reportGuest)}" data-fv-input="F.reportInput('reportGuest',this.value)"></div><div class="form-field"><label for="fv-note">留言</label><textarea id="fv-note" class="input" maxlength="1000" data-fv-input="F.reportInput('reportMessage',this.value)">${esc(state.reportMessage)}</textarea></div>${state.reportError?`<p class="error" role="alert">${esc(state.reportError)}</p>`:''}<button class="cta" data-fv-call="F.comment()" ${r.notes.length>=30?'disabled':''}>发送留言</button></div>${r.notes.length?`<div class="panel">${r.notes.map(n=>`<div class="audit-entry"><div><strong>${esc(n.author)} <span class="muted">· 未核验</span></strong><small>${esc(n.text)}</small><small>${esc(time(n.created))}</small></div></div>`).join('')}</div>`:''}<p class="small-note">留言不修改训练计划或用药记录，也不代表专业医疗建议。</p>`:''}</main>`;
  }
  function openPermission() {const m=member();if(!m){say('请先关联家人。');return;}state.draft=[...m.offered];state.dirty=false;push('permission');}
  function openDialog(kind) {
    if(busy())return;
    const m=member();if(kind==='unbind'&&!m)return;
    state.modal=kind;const d=$('#dialog');d.classList.add('fv-dialog');
    d.innerHTML=`<div data-fv-modal class="sheet" role="document"><h2 id="dialog-title">${kind==='unbind'?'解除与 '+esc(m.name)+' 的关联？':'撤销这份报告分享？'}</h2><p>${kind==='unbind'?'双方关系与分类授权将失效。对方原有健康数据不会被删除。':'撤销后持码者不能再读取或留言，不影响家人关系。'}</p>${kind==='unbind'?'<div class="unbinding fv-style-13c413a4">独立报告分享不会自动撤销，需前往“共享报告”管理。</div>':''}<div class="sheet-buttons"><button class="cta soft" id="fv-dismiss">取消</button><button class="cta dark" id="fv-confirm">${kind==='unbind'?'确认解除':'确认撤销'}</button></div></div>`;
    d.oncancel=e=>{if(busy())e.preventDefault();else{state.modal='';d.classList.remove('fv-dialog');}};
    d.onclose=()=>{state.modal='';d.classList.remove('fv-dialog');};
    bind('fv-dismiss',()=>{if(!busy()){d.close();state.modal='';d.classList.remove('fv-dialog');}});
    bind('fv-confirm',()=>kind==='unbind'?F.unbind():F.revoke());d.showModal();$('#fv-dismiss').focus();
  }
  async function revokeReport(id) {
    const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),15000);
    try {const r=await fetch('/api/care/shares/'+enc(id),{method:'DELETE',headers:{'X-Rehab-Client':'mobile-v1'},signal:ctrl.signal});const data=await r.json();if(!r.ok){const e=Error(data.detail||'撤销未完成');e.status=r.status;throw e;}return data;}
    finally{clearTimeout(timer);}
  }
  const F={back,go:push,refresh,openSearch(){push('search');},search(v){state.search=v;const y=$('#fv-screen').scrollTop;render();$('#fv-screen').scrollTop=y;const input=$('#fv-screen input');input.focus();input.setSelectionRange(v.length,v.length);},
    chooseSearch(id){state.selected=decodeURIComponent(id);push('detail');},selectMember(id){state.selected=decodeURIComponent(id);render();},openMember(){push('detail');},openPermission,
    toggle(id){if(busy()||state.uncertain)return;state.draft=state.draft.includes(id)?state.draft.filter(c=>c!==id):allowed([...state.draft,id]);state.dirty=JSON.stringify(allowed(state.draft))!==JSON.stringify(member()?.offered);const y=$('#fv-screen').scrollTop;render();$('#fv-screen').scrollTop=y;$('#fv-screen [role="switch"][aria-label="'+catName(id)+'"]').focus();},
    permissionCancel(){state.dirty=false;back();},
    savePermission(){if(!state.dirty||!member())return;const p={member:member().id,categories:allowed(state.draft)};write(()=>daily('familyGrant',p),async()=>{state.dirty=false;await load();if(ui.homeConnection==='ready')back();},'共享权限已保存');},
    unbindAsk(){openDialog('unbind');},unbind(){const id=member()?.id;if(!id)return;write(()=>daily('familyUnbind',{member:id}),async()=>{$('#dialog').close();$('#dialog').classList.remove('fv-dialog');state.modal='';state.dirty=false;state.selected='';await load();push('home');},'家庭关联已解除；独立报告分享保持原状态');},
    revokeAsk(id){state.targetReport=decodeURIComponent(id);openDialog('revoke');},revoke(){write(()=>revokeReport(state.targetReport),async()=>{$('#dialog').close();$('#dialog').classList.remove('fv-dialog');state.modal='';await readShares();},'报告分享已撤销');},
    inviteEntry(which){push(which==='generate'?'inviteGenerate':'invite');},setBind(v){state.bindCode=v;state.bindError='';},
    bind(){if(!/^[a-f0-9]{8}$/i.test(state.bindCode.trim())){state.bindError='请填写 8 位家庭邀请码。';render();return;}write(()=>daily('familyBind',{code:state.bindCode.trim()}),async()=>{state.bindCode='';await load();push('home');},'已关联；分类数据仍需分别授权');},
    generateInvite(){write(()=>daily('familyInvite'),r=>{state.inviteCode=r.code;render();},'邀请码已生成；15 分钟内一次有效');},
    consent(v){state.shareConsent=v;const y=$('#fv-screen').scrollTop;render();$('#fv-screen').scrollTop=y;},
    generateReport(){if(!state.shareConsent)return;write(()=>api('/product-share',{consent:true}),r=>{state.createdReport=r;state.shareConsent=false;push('reportCode');},'报告已创建');},
    finishShare(){if(busy())return;remember();history.replaceState({familyV10:false},'','#family/reports');render();readShares();},shareInput(v){state.shareCode=v;state.shareError='';},
    openReport(){const code=state.shareCode.trim();if(!code||code.length>100){state.shareError='请填写有效报告分享码。';render();return;}push('reportView');readReport(code);},refreshReport(){if(!busy()){state.uncertain=false;readReport(viewCode);}},
    reportInput(k,v){if(['reportGuest','reportMessage'].includes(k))state[k]=v;state.reportError='';},
    comment(){const author=state.reportGuest.trim(),text=state.reportMessage.trim();if(!author||author.length>40||!text||text.length>1000){state.reportError='请填写 1–40 字称呼与 1–1000 字留言。';render();return;}write(()=>api('/care/note',{code:viewCode,author,text}),async()=>{state.reportGuest='';state.reportMessage='';await readReport(viewCode);},'留言已保存，称呼未经核验');},
    editContact(){state.contactDraft={...state.contact};state.contactError='';push('contactEdit');},contactInput(k,v){if(['name','phone','doctor'].includes(k))state.contactDraft[k]=v;state.contactError='';},
    saveContact(){const c=state.contactDraft;if(c.name.length>40||c.phone.length>30||c.doctor.length>30){state.contactError='姓名最多 40 字，电话最多 30 字。';render();return;}write(()=>post('profile.save',{profile:contactPayload(profile(),c)}),async()=>{await load();if(ui.homeConnection==='ready')back();},'本人联系人已保存');},
    ai(origin){if(busy())return;if(!aiVisit)aiVisit={draft:ui.draft,private:ui.private};ui.draft=question(origin);ui.private=true;push('ai');}
  };
  function bindEvents() {
    $('#content').querySelectorAll('[data-fv-call]').forEach(n=>n.onclick=()=>{
      if(busy())return;const call=n.getAttribute('data-fv-call').match(/^F\.(\w+)\((.*)\)$/);if(!call||!Object.hasOwn(F,call[1]))return;
      const arg=call[2].match(/^'(.*)'$/);F[call[1]](arg?arg[1]:undefined);
    });
    $('#content').querySelectorAll('[data-fv-input]').forEach(n=>{
      const run=()=>{const call=n.getAttribute('data-fv-input').match(/^F\.(\w+)\((.*)\)$/);if(!call||!Object.hasOwn(F,call[1]))return;const key=call[2].match(/^'([^']+)',/);const value=n.type==='checkbox'?n.checked:n.value;if(key)F[call[1]](key[1],value);else F[call[1]](value);};
      if(n.type==='checkbox')n.onchange=run;else n.oninput=run;
    });
  }
  function loading() {state.offline=true;state.error='正在重新核验…';render();}
  function failure(message){state.members=[];state.offline=true;state.error=message;state.readError=true;render();}
  function render() {
    const guest=reportCode(location.hash)!==null;
    if(!guest&&ui.snapshot&&ui.homeConnection==='ready'){sync();state.offline=false;}
    document.body.dataset.page='family';
    const p=guest?'reportView':path();
    if(state.page!==p){remember();state.page=p;}
    if(p==='permission'&&!state.offline){if(state.draftMember!==member()?.id)state.dirty=false;state.draftMember=member()?.id;if(!state.dirty)state.draft=[...(member()?.offered||[])];}
    if(p==='contactEdit'&&!state.offline&&!state.contactDraft)state.contactDraft={...state.contact};
    currentHash=location.hash;
    $('#nav').hidden=p!=='home';$('#nav a[href="#family"] .nav-label').textContent='家人';
    if(p==='ai'){renderAI();}else{
      const pages={home,detail:memberDetail,permission:permissionPage,invite:invitePage,inviteGenerate,reports,reportCreate,reportCode:reportCreated,reportOpen,reportView,contact,contactEdit,search:searchPage};
      const show=state.offline&&!guest?home:(['detail','permission'].includes(p)&&!member()?()=>`<main class="page">${title(p==='detail'?'家人近况':'共享权限')}<div class="empty-note">当前成员已不可用，请返回重新核验关联。</div></main>`:pages[p]||home);
      $('#content').innerHTML=`<div class="app-frame"><div class="screen" id="fv-screen">${show()}${state.error&&!state.offline?`<div class="page"><p class="error" role="alert">${esc(state.error)}${state.uncertain?'；结果未确认，请刷新核对后再操作。':''}</p><button class="cta outline" data-fv-call="F.refresh()">刷新核对</button></div>`:''}</div></div>`;bindEvents();
      if(busy()||state.uncertain)$('#content').querySelectorAll('button.cta,button.toggle').forEach(b=>{if(!b.dataset.fvCall?.includes('refresh'))b.disabled=true;});
    }
    const n=$('#fv-screen');if(n)n.scrollTop=scrolls.get(currentHash)||0;
    if(p==='reports'&&!state.sharesLoading&&!state.sharesLoaded){state.sharesLoaded=true;readShares();}
    if(guest&&reportReadKey!==reportCode(location.hash))readReport(reportCode(location.hash));
    if(state.page==='permission'&&!member()&&!state.offline){state.dirty=false;state.draft=[];}
  }
  // Hide cached summaries before each server revalidation, including foreground return.
  function beforeLoad(){if(ui.page==='family'&&reportCode(location.hash)===null){remember();state.offline=true;state.members=[];render();}}
  function routeGuest(){ui.page='family';nav();render();}
  return {render,reset,loading,failure,beforeLoad,routeGuest,refreshGuest:()=>{if(!busy())readReport(reportCode(location.hash));},isAI:()=>state.page==='ai'&&!!aiVisit,allowed,members,reportCode,contactPayload,question};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=FamilyV10;
else window.FamilyV10=FamilyV10;
