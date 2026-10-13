/* Session secrets stay in HttpOnly cookies/memory; only scoped pending sends persist. */
(() => {
  'use strict';
  const base = '/api/cloud/v1', main = document.getElementById('content');
  const logout = document.getElementById('logout');
  let account = null, generation = 0, csrf = '', authPending = false, liveView = null, actionNames = Object.create(null);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function resultDetails(payload) {
    if (payload.schema === 'ankang-sync-acceptance-1') return dossierDetails(payload);
    if (payload.schema === 'ankang-workbench-record-1') return workbenchRecordDetails(payload);
    if (payload.schema !== 'ankang-result-1' || !payload.result) return '';
    const result = payload.result, summary = result.summary || {}, lines = [];
    const metric = (label, value, unit = '') => {
      if (typeof value === 'number' && Number.isFinite(value)) lines.push(`<div><dt>${escape(label)}</dt><dd>${escape(Number(value.toFixed(2)))} ${escape(unit)}</dd></div>`);
    };
    metric('完成次数', summary.completed, '次');
    metric('本人记录次数', result.self_reported_count, '次');
    metric('有效画面占比', typeof summary.valid_ratio === 'number' ? summary.valid_ratio * 100 : null, '%');
    metric('观察时长', summary.observed_span_s, '秒');
    metric('最大投影角', summary.motion_range?.max_deg, '°');
    const entries = Array.isArray(summary.metrics) ? summary.metrics : Object.values(summary.metrics || {});
    for (const item of entries) {
      // Desktop scalar metadata is not an angle. Only named metrics are displayed.
      if (!item || typeof item !== 'object' || typeof item.label !== 'string') continue;
      const hasValue = typeof item.value === 'number';
      metric(item.label + (hasValue ? '' : '最大值'), hasValue ? item.value : item.max,
             item.unit === 'deg' ? '°' : item.unit);
    }
    const bar = result.barbell?.summary;
    if (bar) { metric('器械峰值速度', bar.peak_velocity_m_s, 'm/s'); metric('器械峰值功率', bar.peak_power_w, 'W'); }
    const source = ({REPLAY_FILE:'录像分析',LIVE_CAMERA:'实时分析',SELF_RECORDED:'本人记录',GUIDED_PRACTICE:'跟练记录'})[payload.source] || payload.source || '未记录来源';
    return `<p>${escape(source)}${payload.measured_at ? ' · ' + escape(new Date(payload.measured_at).toLocaleString('zh-CN')) : ''}</p><dl class="cloud-metrics">${lines.join('')}</dl><details><summary>原始结果与来源</summary><pre>${escape(JSON.stringify(payload, null, 2))}</pre></details>`;
  }
  function dossierDetails(payload) {
    const note = '<p role="note">同步验收资料：不是实测结果或医嘱，不启用服药提醒和自动训练。</p>';
    if (payload.source !== 'SYNC_ACCEPTANCE' || payload.synthetic !== true || payload.read_only !== true || payload.clinical_use !== false || payload.execution_enabled !== false || !Array.isArray(payload.sections) || payload.sections.some(s=>!s || typeof s!=='object' || !Array.isArray(s.rows) || s.rows.some(r=>!r || typeof r!=='object'))) return '<p role="alert">档案来源需核对，未展示为正式数据。</p>';
    const sections = payload.sections.slice(0, 11).map(s => {
      const rows = Array.isArray(s.rows) ? s.rows.slice(0,25) : [];
      return `<details class="cloud-dossier-section" data-section="${escape(s.key)}"><summary>${escape(s.title)}</summary><p>${escape(s.summary)}</p><dl class="cloud-metrics">${rows.map(r=>`<div><dt>${escape(r.label)}</dt><dd>${escape(r.value)}</dd></div>`).join('')}</dl></details>`;
    }).join('');
    return note + sections + `<details><summary>原始档案与来源</summary><pre>${escape(JSON.stringify(payload,null,2))}</pre></details>`;
  }
  const fieldNames = {name:'姓名／名称',age:'年龄',profile:'个人资料',conditions:'健康问题',medications:'用药资料',medicationRecords:'用药记录',mobility:'活动情况',usesCane:'使用拐杖',nightVision:'夜间视力',cognition:'认知情况',familySharing:'家庭共享',summary:'结果摘要',completed:'完成次数',valid_ratio:'有效画面占比',observed_span_s:'观察时长（秒）',motion_range:'活动幅度',max_deg:'最大投影角（度）',min_deg:'最小投影角（度）',metrics:'测量指标',label:'指标名称',value:'数值',max:'最大值',min:'最小值',unit:'单位',exercise_id:'动作',exercise:'动作',side:'侧别',mode:'记录类别',created_at:'记录时间',measured_at:'测量时间',captured_at:'资料保存时间',received_at:'云端收到时间',start_utc:'开始时间',end_utc:'结束时间',items:'训练内容',settings:'训练设置',target_reps:'目标次数',target_sets:'目标组数',target_angle_deg:'目标角度（度）',rest_between_sets_s:'组间休息（秒）',rest_between_reps_s:'次间休息（秒）',feedback:'训练感受',pain:'疼痛程度',fatigue:'疲劳程度',instruction:'动作说明',source:'资料来源',reason:'说明',rationale:'安排原因',revision:'版本',status:'状态',title:'标题',text:'本人记录',dose:'剂量／用量',times:'时间',purpose:'用途',weight:'体重',systolic:'收缩压',diastolic:'舒张压',bloodGlucose:'血糖',restingHr:'静息心率',spo2:'血氧',steps:'步数',sleepHours:'睡眠时长',nightWakes:'夜间醒来次数',measurement:'健康指标',timestamp:'记录时间',date:'日期',time:'时间',plan_completed:'本次目标完成',target:'目标',active:'启用状态'};
  const valueNames = {left:'左侧',right:'右侧',bilateral:'双侧',assessment:'评估',training:'训练',fitness:'健身',posture:'体态',unknown:'未填写',private:'仅本人',denied:'未授权',ACTIVE:'当前采用',DRAFT:'草稿',PUBLISHED:'已发布',real:'本人档案',demo:'演示资料'};
  function readableFields(value, depth = 0, budget = {remaining:160}, key = '') {
    if (value === null || value === undefined) return '<span class="muted">未记录</span>';
    if (typeof value !== 'object') return escape(typeof value === 'boolean' ? value ? '是' : '否' : ['exercise_id','exercise'].includes(key) ? actionNames[value] || value : key === 'unit' && value === 'deg' ? '°' : Object.hasOwn(valueNames,value) ? valueNames[value] : value);
    if (depth > 4 || budget.remaining < 1) return '<span class="muted">更多内容见原始资料</span>';
    if (Array.isArray(value)) return value.length ? `<ol class="cloud-data-list">${value.slice(0,30).map(v=>`<li>${readableFields(v,depth+1,budget)}</li>`).join('')}</ol>` : '<span class="muted">尚无记录</span>';
    const entries = Object.entries(value).filter(([key])=>!['owner_id','patient_id','ownerId','participant_id','id','key','bytes','dataMode','record_id','assessment_id','installation_id'].includes(key));
    return `<dl class="cloud-metrics">${entries.slice(0,35).map(([key,item])=>{if(budget.remaining--<1)return '';return `<div><dt>${escape(Object.hasOwn(fieldNames,key)?fieldNames[key]:key)}</dt><dd>${readableFields(item,depth+1,budget,key)}</dd></div>`;}).join('')}</dl>`;
  }
  function workbenchRecordDetails(payload) {
    if (!payload.result || !['DESKTOP_LOCAL','APK_LOCAL','WEB_LOCAL'].includes(payload.source)) return '<p role="alert">资料来源需核对，请查看原始记录。</p>';
    const source = {DESKTOP_LOCAL:'电脑保存的本人资料',APK_LOCAL:'手机保存的本人资料',WEB_LOCAL:'网页保存的本人资料'}[payload.source];
    return `<p class="muted">${source} · ${escape(payload.captured_at || '保存时间未记录')} · 客户端声明来源</p>${readableFields(payload.result)}<details><summary>原始资料与来源</summary><pre>${escape(JSON.stringify(payload,null,2))}</pre></details>`;
  }
  async function api(path, method = 'GET', data) {
    const headers = {};
    if (method !== 'GET') { headers['Content-Type'] = 'application/json'; headers['X-CSRF-Token'] = csrf; }
    const response = await fetch(base + path, {method, headers, credentials: 'same-origin',
      body: data === undefined ? undefined : JSON.stringify(data), cache: 'no-store', signal: AbortSignal.timeout(20000)});
    const result = await response.json();
    if (!response.ok) throw Object.assign(new Error(result.message || '暂时无法连接，请稍后再试'), {status: response.status});
    return result;
  }
  function error(message) { const target = document.querySelector('.cloud-error'); if (target) target.textContent = message; }
  function failed(e, own) {
    if (own !== generation) return;
    if (e.status === 401) { showAuth(); error('登录已失效，请重新登录。'); return; }
    if (e.status === 404 && liveView?.doctor) {
      ++generation; liveView = null;
      main.innerHTML = '<h1>无法打开档案</h1><p>当前没有这份档案的访问权限，请返回列表重新核对。</p><button id="back">返回患者列表</button><p class="cloud-error" role="alert"></p>';
      document.getElementById('back').onclick = () => showPatients(0).catch(e=>error(e.message)); return;
    }
    error(e.message || '暂时无法连接，请保留内容后重试。');
  }
  function showAuth(register = false) {
    ++generation; account = null; csrf = ''; liveView = null; actionNames = Object.create(null); logout.hidden = true;
    const doctor = location.pathname === '/care';
    main.innerHTML = `<section class="cloud-form"><h1>${register ? '创建账号' : doctor ? '医生登录' : '登录安康'}</h1>
      <form id="account-form"><label>账号<input name="username" autocomplete="username" maxlength="64" required></label>
      ${register ? '<label>姓名<input name="display_name" autocomplete="name" maxlength="80"></label>' : ''}
      <label>密码<input name="password" type="password" autocomplete="${register ? 'new-password' : 'current-password'}" maxlength="128" required></label>
      <p class="cloud-error" role="alert"></p><button class="primary" type="submit">${register ? '创建账号' : '登录'}</button></form>
      <div class="cloud-toolbar">${doctor ? '<a href="/">患者入口</a>' : `<button id="switch-auth" class="quiet">${register ? '已有账号，去登录' : '没有账号，去注册'}</button><a href="/care">医生入口</a>`}</div></section>`;
    document.getElementById('switch-auth')?.addEventListener('click', () => { if (!authPending) showAuth(!register); });
    document.getElementById('account-form').addEventListener('submit', async event => {
      event.preventDefault(); if (authPending) return; authPending = true; const own = generation;
      const form = event.currentTarget, button = form.querySelector('button'); button.disabled = true; error('');
      const data = Object.fromEntries(new FormData(form));
      try {
        if (register) await api('/auth/register', 'POST', data);
        const signed = await api('/auth/password/login', 'POST', {username: data.username, password: data.password});
        if (own !== generation) return;
        account = signed; csrf = signed.csrf_token; await showHome();
      } catch (e) { if (own === generation) error(e.message); }
      finally { authPending = false; if (own === generation) button.disabled = false; }
    });
  }
  async function showHome() {
    const own = ++generation; logout.hidden = false;
    if (account.role === 'DOCTOR_ADMIN') return showPatients(0);
    if (location.pathname === '/account' && new URLSearchParams(location.search).get('next') === '/') {
      location.replace('/'); return;
    }
    if (location.pathname === '/care') {
      main.innerHTML = '<h1>工作台</h1><p>请使用医生账号登录。</p><p class="cloud-error" role="alert"></p>';
      return;
    }
    main.innerHTML = '<p role="status">正在读取档案…</p>';
    const profile = await api(`/patients/${account.patient_id}`);
    if (own !== generation) return;
    liveView = {ident:account.patient_id, own, doctor:false};
    main.innerHTML = `<h1>工作台 · ${escape(profile.display_name)}</h1><p>账号：${escape(account.username)}</p><p><a class="button" href="/">进入安康：对话与采用方案</a></p>
      <section><h2>医生共享</h2><p>${profile.doctor_access ? '已授权医生查看云端资料、与你对话并发布康复方案。' : '你的云端档案目前仅本人可见。开启授权后可与医生对话。'}</p>
      <button id="grant" class="${profile.doctor_access ? '' : 'primary'}">${profile.doctor_access ? '停止共享' : '授权医生查看'}</button></section>
      <section><h2>云端记录</h2><div id="records"><p>正在读取…</p></div></section>
      <section><h2>医生对话 <span id="unread-count" class="cloud-badge"></span></h2><p>进入安康打开“工作台”发送消息；断网时内容会保留在当前账号，连接恢复后可重试。</p><button id="load-messages">读取对话</button><div id="conversation"></div></section>
      <section><h2>康复方案</h2><p>这里可以查看医生方案。在本人安康客户端核对评估与训练条件后，才能采用并继续训练。</p><div id="plans"><p>正在读取…</p></div></section>
      <details><summary>修改密码</summary><form id="password-form"><label>原密码<input type="password" name="current_password" autocomplete="current-password" required maxlength="128"></label><label>新密码<input type="password" name="new_password" autocomplete="new-password" required maxlength="128"></label><button type="submit">保存新密码</button></form></details><p class="cloud-error" role="alert"></p>`;
    document.getElementById('grant').onclick = async event => {
      const button = event.currentTarget; button.disabled = true;
      try { await api(`/patients/${account.patient_id}/doctor-access`, 'PUT', {enabled: !profile.doctor_access, expected_version: profile.grant_version}); if (own === generation) await showHome(); }
      catch(e) { failed(e,own); button.disabled = false; }
    };
    document.getElementById('password-form').onsubmit = async event => {
      event.preventDefault(); const form = event.currentTarget, button = form.querySelector('button'); button.disabled = true;
      try { await api('/auth/password/change', 'POST', Object.fromEntries(new FormData(form))); if (own === generation) { showAuth(); error('密码已修改，请重新登录'); } }
      catch(e) { if (own === generation) { error(e.message); button.disabled = false; } }
    };
    document.getElementById('load-messages').onclick = () => showMessages(account.patient_id, own).catch(e=>failed(e,own));
    await Promise.all([showRecords(account.patient_id, own), showPlans(account.patient_id, own), messageStatus(account.patient_id, own)]);
  }
  async function showRecords(ident, own, offset = 0) {
    const result = await api(`/patients/${ident}/records?offset=${offset}&limit=10`);
    if (own !== generation) return;
    const area = document.getElementById('records');
    area.innerHTML = (result.items.length ? result.items.map(r => `<article class="cloud-record" data-kind="${escape(r.payload.kind || '')}"><strong>${escape(r.payload.title || '使用记录')}</strong><p>${escape(r.payload.text || '')}</p>${resultDetails(r.payload)}<time>上传时间：${escape(new Date(r.received_at * 1000).toLocaleString('zh-CN'))}</time></article>`).join('') : '<p class="muted">这一页没有云端记录。请在本人客户端上传已保存的资料与结果。</p>') + `<div class="cloud-toolbar"><button id="records-previous" ${offset===0?'disabled':''}>上一页记录</button><span>第 ${offset/10+1} 页</span><button id="records-next" ${result.items.length<10?'disabled':''}>下一页记录</button></div>`;
    document.getElementById('records-previous').onclick = () => showRecords(ident,own,Math.max(0,offset-10)).catch(e=>failed(e,own));
    document.getElementById('records-next').onclick = () => showRecords(ident,own,offset+10).catch(e=>failed(e,own));
  }
  async function showPatients(offset, search = '') {
    const own = ++generation; liveView = null; main.innerHTML = '<p role="status">正在读取患者…</p>';
    const result = await api(`/care/patients?offset=${offset}&limit=30&search=${encodeURIComponent(search)}`);
    if (own !== generation) return;
    main.innerHTML = `<h1>工作台</h1><p>查看患者已保存的资料、文字随访和康复方案。${result.total} 位已授权患者。</p><form id="patient-search" class="cloud-toolbar"><label>查找患者<input name="search" value="${escape(search)}" maxlength="80" autocomplete="off"></label><button type="submit">查找</button></form><div class="cloud-patients">${result.items.map(p => `<div class="cloud-patient"><div><strong>${escape(p.display_name)}</strong>${p.unread_count ? `<span class="cloud-badge">${escape(p.unread_count)} 条未读</span>` : ''}</div><button data-patient="${escape(p.id)}">查看档案</button></div>`).join('') || '<p>患者授权共享后，会显示在这里。</p>'}</div>
      <div class="cloud-toolbar"><button id="previous" ${offset === 0 ? 'disabled' : ''}>上一页</button><button id="next" ${offset + 30 >= result.total ? 'disabled' : ''}>下一页</button></div><p class="cloud-error" role="alert"></p>`;
    main.querySelectorAll('[data-patient]').forEach(button => button.onclick = () => openPatient(button.dataset.patient).catch(e => failed(e,generation)));
    document.getElementById('patient-search').onsubmit = event => {event.preventDefault();showPatients(0,new FormData(event.currentTarget).get('search')).catch(e=>failed(e,generation));};
    document.getElementById('previous').onclick = () => showPatients(Math.max(0, offset - 30),search).catch(e => failed(e,generation));
    document.getElementById('next').onclick = () => showPatients(offset + 30,search).catch(e => failed(e,generation));
  }
  async function openPatient(ident) {
    const own = ++generation; main.innerHTML = '<p role="status">正在读取档案…</p>';
    try {
      const profile = await api(`/patients/${ident}`);
      if (own !== generation) return;
      const actions = await api('/care/actions?offset=0&limit=100');
      if (own !== generation) return;
      actionNames = Object.fromEntries(actions.items.map(item=>[item.exercise_id,item.name]));
      liveView = {ident,own,doctor:true};
      main.innerHTML = `<button id="back">返回患者列表</button><h1>工作台 · ${escape(profile.display_name)}</h1><p>资料由患者客户端明确上传。请结合资料来源、评估与训练感受核对方案。</p>
        <section><h2>已保存的资料与结果</h2><p class="muted">以下是各设备最新上传的个人资料、评估、训练和本机计划。没有上传的资料不会补造。</p><div id="rehab-summary"></div><details><summary>查看全部云端记录与历史版本</summary><div id="records"></div></details></section>
        <section><h2>文字随访 <span id="unread-count" class="cloud-badge"></span></h2><button id="load-messages">读取对话</button><div id="conversation"></div><form id="message-form"><label>发送给患者<textarea name="text" rows="3" maxlength="4000" required placeholder="填写需要核对的问题或反馈"></textarea></label><div class="cloud-toolbar"><button class="primary" type="submit">发送消息</button><span id="message-status" role="status"></span></div></form></section>
        <section><div class="cloud-section-title"><h2>康复方案</h2><button id="new-plan">新建草稿</button></div><div id="plans"></div><div id="plan-editor"></div></section><p class="cloud-error" role="alert"></p>`;
      document.getElementById('back').onclick = () => showPatients(0).catch(e => error(e.message));
      document.getElementById('load-messages').onclick = () => showMessages(ident,own).catch(e=>failed(e,own));
      document.getElementById('new-plan').onclick = () => editPlan(ident,own).catch(e=>failed(e,own));
      bindMessageForm(ident,own);
      await Promise.all([showRecords(ident, own),showSavedSummary(ident,own),showPlans(ident,own),messageStatus(ident,own)]);
    } catch(e) { if (own === generation) {liveView=null;main.innerHTML = `<h1>无法打开档案</h1><p>${escape(e.message)}</p><button id="back">返回患者列表</button>`;document.getElementById('back').onclick=()=>showPatients(0).catch(e=>error(e.message));} }
  }
  async function showSavedSummary(ident,own){
    const result=await api(`/patients/${ident}/rehab-summary`);if(own!==generation)return;
    document.getElementById('rehab-summary').innerHTML=[['profile','个人资料'],['assessment','已保存评估'],['training','训练与反馈'],['rehab_plan','当前本机计划']].map(([kind,label])=>{
      const rows=result[kind]||[];
      return `<details class="cloud-dossier-section" data-saved-kind="${kind}" ${kind==='rehab_plan'?'open':''}><summary>${label} · ${rows.length} 份</summary>${rows.length?rows.map(r=>`<article class="cloud-record"><strong>${escape(r.payload.title)}</strong>${resultDetails(r.payload)}</article>`).join(''):'<p class="muted">尚未上传这一类本人资料。</p>'}</details>`;
    }).join('');
  }
  async function messageStatus(ident, own) {
    const result = await api(`/patients/${ident}/messages?latest=true&limit=1`);
    if (own!==generation) return;
    document.getElementById('unread-count').textContent = result.unread_count ? `${result.unread_count} 条未读` : '没有未读';
  }
  function messageHtml(item) {
    return `<article class="cloud-chat ${item.author_role==='DOCTOR_ADMIN'?'doctor':'patient'}" data-sequence="${escape(item.sequence)}"><strong>${item.author_role==='DOCTOR_ADMIN'?'医生':'患者本人'}</strong><time>${escape(new Date(item.created_at*1000).toLocaleString('zh-CN'))}</time><p>${escape(item.text)}</p></article>`;
  }
  async function showMessages(ident,own,before=null) {
    const result=await api(`/patients/${ident}/messages?limit=50&${before===null?'latest=true':'before='+before}`);
    if(own!==generation)return;
    const area=document.getElementById('conversation');
    if(before===null)area.innerHTML='<div id="message-history"></div><div id="chat-items"></div>';
    const target=document.getElementById('chat-items');
    const html=result.items.map(messageHtml).join('');
    if(before===null)target.innerHTML=html||'<p class="muted">还没有对话记录。</p>';
    else target.insertAdjacentHTML('afterbegin',html);
    document.getElementById('message-history').innerHTML=result.has_older?'<button id="older-messages">读取更早的对话</button>':'';
    document.getElementById('older-messages')?.addEventListener('click',()=>showMessages(ident,own,result.previous_cursor).catch(e=>failed(e,own)));
    // Only messages actually rendered in this view advance the server cursor.
    if(result.items.length && result.next_cursor>result.read_cursor)await api(`/patients/${ident}/messages/read`,'POST',{operation_id:crypto.randomUUID(),cursor:result.next_cursor});
    if(own===generation)await messageStatus(ident,own);
  }
  function bindMessageForm(ident,own) {
    const form=document.getElementById('message-form'),actor=account.account_id;
    const key='ankang-workbench-doctor-outbox-1:'+actor+':'+ident;
    let pending=null;
    const locked=fn=>navigator.locks?.request?navigator.locks.request(key,fn):Promise.resolve().then(fn);
    function restore(){
      const raw=localStorage.getItem(key);if(!raw)return;
      const value=JSON.parse(raw);
      if(value.schema!==1||value.account_id!==actor||value.patient_id!==ident||typeof value.operation_id!=='string'||typeof value.text!=='string'||value.text.length>4000)throw Error('待发送消息格式需核对，原数据已保留。');
      pending=value;
      form.elements.text.value=pending.text;form.elements.text.readOnly=true;
      form.querySelector('button').textContent='重试待发送消息';
      document.getElementById('message-status').textContent='有待核对消息：原文和操作编号已保留。请重试，避免重复发送。';
    }
    try{restore();}catch(e){error(e.message);form.querySelector('button').disabled=true;return;}
    form.onsubmit=async event=>{
      event.preventDefault();const text=form.elements.text.value.trim();if(!text)return;
      if(!pending){
        pending={schema:1,account_id:actor,patient_id:ident,operation_id:crypto.randomUUID(),text};
        try{await locked(()=>{
          if(localStorage.getItem(key))throw Error('另一个页面已有待核对消息，原文已保留。请返回档案重新打开并重试原消息。当前输入未发送。');
          localStorage.setItem(key,JSON.stringify(pending));
        });}
        catch(e){pending=null;error(e.message||'浏览器未能保存待发送消息，请保留原文后检查本地存储。');return;}
      }
      const button=form.querySelector('button');button.disabled=true;error('');
      const status=document.getElementById('message-status');status.textContent='正在发送…';
      try{
        await api(`/patients/${ident}/messages`,'POST',{operation_id:pending.operation_id,text:pending.text});
        const acknowledged=pending.operation_id;
        await locked(()=>{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved?.operation_id===acknowledged)localStorage.removeItem(key);});
        pending=null;if(own!==generation)return;
        form.reset();form.elements.text.readOnly=false;button.textContent='发送消息';status.textContent='已发送';await showMessages(ident,own);
      }
      catch(e){if(own===generation){form.elements.text.readOnly=true;button.textContent='重试待发送消息';status.textContent='尚未收到成功回执，原文和操作编号已保留；刷新或重新登录后仍可重试。';failed(e,own);}}
      finally{button.disabled=false;}
    };
  }
  function planHtml(plan,currentId,doctor) {
    const state=plan.id===currentId?'本人已采用':plan.status==='DRAFT'?'草稿，患者尚不可见':'已发布，等待本人核对';
    return `<article class="cloud-plan"><div class="cloud-section-title"><h3>${escape(plan.title)}</h3><span class="cloud-badge">${state}</span></div><p class="cloud-preserve">${escape(plan.summary)}</p><ol class="cloud-plan-items">${plan.items.map(item=>`<li><strong>${escape(item.name)} · ${item.side==='left'?'左侧':'右侧'}</strong><p>${escape(item.settings.target_reps)} 次 × ${escape(item.settings.target_sets)} 组；组间休息 ${item.settings.rest_between_sets_s===null?'未指定':escape(item.settings.rest_between_sets_s)+' 秒'}；目标角度 ${item.settings.target_angle_deg===null?'未指定':escape(item.settings.target_angle_deg)+'°'}</p>${item.dose?`<p>${escape(item.dose)}</p>`:''}${item.caution?`<p>注意：${escape(item.caution)}</p>`:''}<details><summary>查看完整训练设置</summary>${readableFields(item.settings)}</details></li>`).join('')}</ol><p class="muted">版本 ${escape(plan.version)}${plan.published_at?' · 发布于 '+escape(new Date(plan.published_at*1000).toLocaleString('zh-CN')):''}</p>${doctor?`<div class="cloud-toolbar"><button data-edit-plan="${escape(plan.id)}">${plan.status==='DRAFT'?'编辑草稿':'以此创建新版本'}</button>${plan.status==='DRAFT'?`<button data-publish-plan="${escape(plan.id)}">核对并发布</button>`:''}</div>`:''}</article>`;
  }
  function planQueue(ident){
    const actor=account.account_id,key='ankang-workbench-plan-outbox-1:'+actor+':'+ident;
    const read=()=>{
      const value=JSON.parse(localStorage.getItem(key)||'null');
      if(value && (value.schema!==1||value.account_id!==actor||value.patient_id!==ident||!['POST','PUT'].includes(value.method)||!new RegExp('^/patients/'+ident+'/plans(?:/[a-f0-9-]{36})?$').test(value.path)||typeof value.document?.operation_id!=='string'))throw Error('待保存草稿格式需核对，原数据已保留。');
      return value;
    };
    const locked=fn=>navigator.locks?.request?navigator.locks.request(key,fn):Promise.resolve().then(fn);
    return{read,save:document=>locked(()=>{const prior=read();if(prior&&prior.document.operation_id!==document.document.operation_id)throw Error('另一个页面已有待保存草稿，请先重试原操作。');localStorage.setItem(key,JSON.stringify(document));}),
      remove:operation=>locked(()=>{if(read()?.document.operation_id===operation)localStorage.removeItem(key);}),actor};
  }
  async function showPlans(ident,own,offset=0) {
    const result=await api(`/patients/${ident}/plans?offset=${offset}&limit=10`);
    if(own!==generation)return;
    const doctor=account.role==='DOCTOR_ADMIN',area=document.getElementById('plans');
    const queue=doctor?planQueue(ident):null,pending=queue?.read();
    area.innerHTML=(pending?`<div class="cloud-plan"><strong>草稿保存回执待核对：${escape(pending.document.title)}</strong><p>原操作编号和内容已保留。请先重试，避免创建另一份草稿。</p><button id="retry-plan-save">重试待保存草稿</button></div>`:'')+(result.items.map(p=>planHtml(p,result.current_plan_id,doctor)).join('')||'<p class="muted">还没有康复方案。</p>')+`<div class="cloud-toolbar"><button id="plans-previous" ${offset===0?'disabled':''}>上一页方案</button><button id="plans-next" ${offset+10>=result.total?'disabled':''}>下一页方案</button></div>`;
    if(doctor){document.getElementById('new-plan').disabled=Boolean(pending);area.querySelectorAll('[data-edit-plan],[data-publish-plan]').forEach(button=>button.disabled=Boolean(pending));}
    document.getElementById('retry-plan-save')?.addEventListener('click',async event=>{
      event.currentTarget.disabled=true;
      try{await api(pending.path,pending.method,pending.document);await queue.remove(pending.document.operation_id);if(own===generation){document.getElementById('plan-editor').replaceChildren();await showPlans(ident,own);}}
      catch(e){failed(e,own);event.currentTarget.disabled=false;}
    });
    document.getElementById('plans-previous').onclick=()=>showPlans(ident,own,Math.max(0,offset-10)).catch(e=>failed(e,own));
    document.getElementById('plans-next').onclick=()=>showPlans(ident,own,offset+10).catch(e=>failed(e,own));
    area.querySelectorAll('[data-edit-plan]').forEach(button=>button.onclick=()=>editPlan(ident,own,result.items.find(p=>p.id===button.dataset.editPlan)).catch(e=>failed(e,own)));
    area.querySelectorAll('[data-publish-plan]').forEach(button=>button.onclick=()=>publishPlan(ident,own,result.items.find(p=>p.id===button.dataset.publishPlan),button));
  }
  async function publishPlan(ident,own,plan,button) {
    if(!confirm(`发布“${plan.title}”？请核对动作、侧别、次数、组数和注意事项。发布后保留原文，修改将创建新版本。患者仍需在本人客户端核对并采用。`))return;
    button.disabled=true;
    const operation=button.dataset.operationId||(button.dataset.operationId=crypto.randomUUID());
    try{await api(`/patients/${ident}/plans/${plan.id}/publish`,'POST',{operation_id:operation,expected_version:plan.version});if(own===generation)await showPlans(ident,own);}
    catch(e){failed(e,own);button.disabled=false;}
  }
  async function editPlan(ident,own,existing=null) {
    if(planQueue(ident).read()){await showPlans(ident,own);error('请先重试待保存草稿，原操作编号和内容已经保留。');return;}
    const actions=await api('/care/actions?offset=0&limit=100');if(own!==generation)return;
    const area=document.getElementById('plan-editor'),editing=existing?.status==='DRAFT';
    area.innerHTML=`<form id="plan-form" class="cloud-plan-editor"><h3>${editing?'编辑草稿':existing?'新版本草稿':'新建草稿'}</h3><p>从已支持的训练动作选择项目；次数、组数和目标由医生填写。空白角度表示未指定。</p><label>方案名称<input name="title" maxlength="80" value="${escape(existing?.title||'')}" required></label><label>方案说明<textarea name="summary" rows="3" maxlength="8000">${escape(existing?.summary||'')}</textarea></label><div id="plan-items"></div><div class="cloud-toolbar"><button id="add-plan-item" type="button">添加训练项目</button><button class="primary" type="submit">保存草稿</button><button id="cancel-plan" type="button">收起</button><span id="plan-save-status" role="status"></span></div></form>`;
    const form=document.getElementById('plan-form'),itemsArea=document.getElementById('plan-items');let operation=null;
    function addItem(item=null){
      const row=document.createElement('fieldset');row.className='cloud-plan-item';
      const s=item?.settings||{};
      row.innerHTML=`<legend>训练项目</legend><div class="cloud-item-grid"><label>动作<select name="exercise_id" required><option value="">请选择</option>${actions.items.map(a=>`<option value="${escape(a.exercise_id)}" ${a.exercise_id===item?.exercise_id?'selected':''}>${escape(a.name)}${a.experimental?'（实验动作）':''}</option>`).join('')}</select></label><label>侧别<select name="side" required><option value="">请选择</option><option value="left" ${item?.side==='left'?'selected':''}>左侧</option><option value="right" ${item?.side==='right'?'selected':''}>右侧</option></select></label><label>目标次数<input name="target_reps" type="number" min="1" max="999" step="1" value="${escape(s.target_reps??'')}" required></label><label>目标组数<input name="target_sets" type="number" min="1" max="20" step="1" value="${escape(s.target_sets??'')}" required></label><label>组间休息（秒）<input name="rest_between_sets_s" type="number" min="0" max="1800" step="any" value="${escape(s.rest_between_sets_s??'')}" placeholder="未指定"></label><label>目标角度（度）<input name="target_angle_deg" type="number" min="0" max="180" step="any" value="${escape(s.target_angle_deg??'')}" placeholder="未指定"></label></div><details><summary>更多训练设置</summary><div class="cloud-item-grid"><label>允许肘部弯曲（度）<input name="allowed_elbow_flexion_deg" type="number" min="0" max="180" step="any" value="${escape(s.allowed_elbow_flexion_deg??'')}"></label><label>允许躯干倾斜（度）<input name="allowed_trunk_tilt_deg" type="number" min="0" max="90" step="any" value="${escape(s.allowed_trunk_tilt_deg??'')}"></label><label>下降最短时间（秒，仅坐站）<input name="lowering_tempo_min_s" type="number" min="0" max="60" step="any" value="${escape(s.lowering_tempo_min_s??'')}"></label><label>下降最长时间（秒，仅坐站）<input name="lowering_tempo_max_s" type="number" min="0" max="60" step="any" value="${escape(s.lowering_tempo_max_s??'')}"></label><label>扶物安排<select name="use_of_hands">${[['not_recorded','未指定'],['allowed','允许扶物'],['not_allowed','不允许扶物'],['used_hands','已记录使用扶物']].map(([v,label])=>`<option value="${v}" ${v===(s.use_of_hands||'not_recorded')?'selected':''}>${label}</option>`).join('')}</select></label><label class="cloud-check"><input name="needs_companion" type="checkbox" ${s.needs_companion?'checked':''}>需要陪同</label><label class="cloud-check"><input name="sound_enabled" type="checkbox" ${s.sound_enabled?'checked':''}>训练提示音</label></div></details><label>补充训练安排<textarea name="dose" rows="2" maxlength="2000">${escape(item?.dose||'')}</textarea></label><label>注意事项<textarea name="caution" rows="2" maxlength="2000">${escape(item?.caution||'')}</textarea></label><button class="quiet remove-item" type="button">移除此项目</button>`;
      // Select option text must not become part of the control's accessible name.
      row.querySelectorAll('select').forEach(select=>select.setAttribute('aria-label',select.parentElement.firstChild.textContent.trim()));
      const timing=document.createElement('div');timing.className='cloud-item-grid';
      timing.innerHTML=[['outbound_min_s','移出最短时间'],['outbound_max_s','移出最长时间'],['return_min_s','返回最短时间'],['return_max_s','返回最长时间'],['hold_min_s','连续保持时间']].map(([key,label])=>`<label>${label}（秒）<input name="${key}" type="number" min="0" max="300" step="any" value="${escape(s.timing_plan?.[key]??'')}" placeholder="未指定"></label>`).join('');
      row.querySelector('details').append(timing);
      row.querySelector('.remove-item').onclick=()=>row.remove();itemsArea.append(row);
    }
    (existing?.items||[null]).forEach(addItem);
    document.getElementById('add-plan-item').onclick=()=>{if(itemsArea.children.length<40)addItem();else error('最多添加 40 项训练。');};
    document.getElementById('cancel-plan').onclick=()=>area.replaceChildren();
    form.onsubmit=async event=>{
      event.preventDefault();const items=[...itemsArea.children].map(row=>{
        const get=name=>row.querySelector(`[name="${name}"]`),number=name=>get(name).value===''?null:Number(get(name).value),action=actions.items.find(a=>a.exercise_id===get('exercise_id').value);
        return{exercise_id:action.exercise_id,name:action.name,measurement_contract:action.measurement_contract,side:get('side').value,settings:{target_reps:number('target_reps'),target_sets:number('target_sets'),rest_between_sets_s:number('rest_between_sets_s'),target_angle_deg:number('target_angle_deg'),allowed_elbow_flexion_deg:number('allowed_elbow_flexion_deg'),allowed_trunk_tilt_deg:number('allowed_trunk_tilt_deg'),lowering_tempo_min_s:number('lowering_tempo_min_s'),lowering_tempo_max_s:number('lowering_tempo_max_s'),use_of_hands:get('use_of_hands').value,needs_companion:get('needs_companion').checked,sound_enabled:get('sound_enabled').checked,timing_plan:Object.fromEntries(['outbound_min_s','outbound_max_s','return_min_s','return_max_s','hold_min_s'].map(key=>[key,number(key)]))},dose:get('dose').value,caution:get('caution').value};
      });
      if(!items.length){error('请至少添加一个训练项目。');return;}
      const documentValue={title:form.elements.title.value,summary:form.elements.summary.value,items,parent_plan_id:editing?existing.parent_plan_id:existing?.id||null,...(editing?{expected_version:existing.version}:{})};
      const fingerprint=JSON.stringify(documentValue);if(!operation||operation.fingerprint!==fingerprint)operation={id:crypto.randomUUID(),fingerprint};
      const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);error('');
      const queue=planQueue(ident),path=`/patients/${ident}/plans${editing?'/'+existing.id:''}`,method=editing?'PUT':'POST',savedDocument={operation_id:operation.id,...documentValue};
      try{await queue.save({schema:1,account_id:queue.actor,patient_id:ident,path,method,document:savedDocument});await api(path,method,savedDocument);await queue.remove(operation.id);if(own!==generation)return;area.replaceChildren();await showPlans(ident,own);}
      catch(e){
        if(e.status===422)await queue.remove(operation.id);
        if(own===generation){document.getElementById('plan-save-status').textContent=e.status===422?'草稿尚未保存，请按提示核对填写。':'未收到成功回执，原操作及草稿内容已保留。';failed(e,own);await showPlans(ident,own).catch(error=>failed(error,own));}
      }
      finally{buttons.forEach(b=>b.disabled=false);}
    };
    area.scrollIntoView({behavior:'smooth',block:'start'});
  }
  logout.onclick = async () => {
    logout.disabled = true;
    try { await api('/auth/logout', 'POST', {}); showAuth(); }
    catch(e) { error(e.message); }
    finally { logout.disabled = false; }
  };
  (async () => {
    try { account = await api('/auth/me'); csrf = account.csrf_token; await showHome(); }
    catch(e) { showAuth(); if (e.status !== 401) error(e.message); }
  })();
  // Recheck authorization on return and periodically; leave unsaved forms intact.
  async function checkVisibleView(){
    const view=liveView;if(!view||document.hidden)return;
    try{await api(`/patients/${view.ident}`);if(view.own===generation)await messageStatus(view.ident,view.own);}
    catch(e){failed(e,view.own);}
  }
  addEventListener('focus',checkVisibleView);
  setInterval(checkVisibleView,30000);
})();
