/* No persistent session tokens or third-party patient cache in this browser. */
(() => {
  'use strict';
  const base = '/api/cloud/v1', main = document.getElementById('content');
  const logout = document.getElementById('logout');
  let account = null, generation = 0, csrf = '', authPending = false;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function resultDetails(payload) {
    if (payload.schema === 'ankang-sync-acceptance-1') return dossierDetails(payload);
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
  async function api(path, method = 'GET', data) {
    const headers = {};
    if (method !== 'GET') { headers['Content-Type'] = 'application/json'; headers['X-CSRF-Token'] = csrf; }
    const response = await fetch(base + path, {method, headers, credentials: 'same-origin',
      body: data === undefined ? undefined : JSON.stringify(data), cache: 'no-store'});
    const result = await response.json();
    if (!response.ok) throw Object.assign(new Error(result.message || '暂时无法连接，请稍后再试'), {status: response.status});
    return result;
  }
  function error(message) { const target = document.querySelector('.cloud-error'); if (target) target.textContent = message; }
  function showAuth(register = false) {
    ++generation; account = null; csrf = ''; logout.hidden = true;
    const doctor = location.pathname === '/care';
    main.innerHTML = `<section class="cloud-form"><h1>${register ? '创建账号' : doctor ? '医生登录' : '登录安康'}</h1>
      <form id="account-form"><label>账号<input name="username" autocomplete="username" maxlength="64" required></label>
      ${register ? '<label>姓名<input name="display_name" autocomplete="name" maxlength="80"></label>' : ''}
      <label>密码<input name="password" type="password" autocomplete="${register ? 'new-password' : 'current-password'}" maxlength="128" required></label>
      <p class="cloud-error" role="alert"></p><button class="primary" type="submit">${register ? '创建账号' : '登录'}</button></form>
      <div class="cloud-toolbar">${doctor ? '<a href="/">患者入口</a>' : `<button id="switch-auth" class="quiet">${register ? '已有账号，去登录' : '没有账号，去注册'}</button><a href="/care">医生入口</a>`}<a href="/download">下载App</a></div></section>`;
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
      main.innerHTML = '<h1>医生工作台</h1><p>请使用医生账号登录。</p><p class="cloud-error" role="alert"></p>';
      return;
    }
    main.innerHTML = '<p role="status">正在读取档案…</p>';
    const profile = await api(`/patients/${account.patient_id}`);
    if (own !== generation) return;
    main.innerHTML = `<h1>${escape(profile.display_name)}</h1><p>账号：${escape(account.username)}</p><p><a href="/">进入安康</a></p>
      <section><h2>医生共享</h2><p>${profile.doctor_access ? '医生工作台可以查看你的云端档案和记录。' : '你的云端档案目前仅本人可见。'}</p>
      <button id="grant" class="${profile.doctor_access ? '' : 'primary'}">${profile.doctor_access ? '停止共享' : '授权医生查看'}</button></section>
      <section><h2>云端记录</h2><div id="records"><p>正在读取…</p></div></section>
      <details><summary>修改密码</summary><form id="password-form"><label>原密码<input type="password" name="current_password" autocomplete="current-password" required maxlength="128"></label><label>新密码<input type="password" name="new_password" autocomplete="new-password" required maxlength="128"></label><button type="submit">保存新密码</button></form></details><p class="cloud-error" role="alert"></p>`;
    document.getElementById('grant').onclick = async event => {
      const button = event.currentTarget; button.disabled = true;
      try { await api(`/patients/${account.patient_id}/doctor-access`, 'PUT', {enabled: !profile.doctor_access, expected_version: profile.grant_version}); if (own === generation) await showHome(); }
      catch(e) { if (own === generation) { error(e.message); button.disabled = false; } }
    };
    document.getElementById('password-form').onsubmit = async event => {
      event.preventDefault(); const form = event.currentTarget, button = form.querySelector('button'); button.disabled = true;
      try { await api('/auth/password/change', 'POST', Object.fromEntries(new FormData(form))); if (own === generation) { showAuth(); error('密码已修改，请重新登录'); } }
      catch(e) { if (own === generation) { error(e.message); button.disabled = false; } }
    };
    await showRecords(account.patient_id, own);
  }
  async function showRecords(ident, own) {
    const result = await api(`/patients/${ident}/records?offset=0&limit=10`);
    if (own !== generation) return;
    const area = document.getElementById('records');
    area.innerHTML = result.items.length ? result.items.map(r => `<article class="cloud-record"><strong>${escape(r.payload.title || '使用记录')}</strong><p>${escape(r.payload.text || '')}</p>${resultDetails(r.payload)}<time>上传时间：${escape(new Date(r.received_at * 1000).toLocaleString('zh-CN'))}</time></article>`).join('') : '<p class="muted">还没有同步到云端的记录。</p>';
  }
  async function showPatients(offset) {
    const own = ++generation; main.innerHTML = '<p role="status">正在读取患者…</p>';
    const result = await api(`/care/patients?offset=${offset}&limit=30`);
    if (own !== generation) return;
    main.innerHTML = `<h1>医生工作台</h1><p>${result.total} 位已授权患者</p><div class="cloud-patients">${result.items.map(p => `<div class="cloud-patient"><strong>${escape(p.display_name)}</strong><button data-patient="${escape(p.id)}">查看档案</button></div>`).join('') || '<p>患者授权共享后，会显示在这里。</p>'}</div>
      <div class="cloud-toolbar"><button id="previous" ${offset === 0 ? 'disabled' : ''}>上一页</button><button id="next" ${offset + 30 >= result.total ? 'disabled' : ''}>下一页</button></div><p class="cloud-error" role="alert"></p>`;
    main.querySelectorAll('[data-patient]').forEach(button => button.onclick = () => openPatient(button.dataset.patient).catch(e => error(e.message)));
    document.getElementById('previous').onclick = () => showPatients(Math.max(0, offset - 30)).catch(e => error(e.message));
    document.getElementById('next').onclick = () => showPatients(offset + 30).catch(e => error(e.message));
  }
  async function openPatient(ident) {
    const own = ++generation; main.innerHTML = '<p role="status">正在读取档案…</p>';
    try {
      const profile = await api(`/patients/${ident}`);
      if (own !== generation) return;
      main.innerHTML = `<button id="back">返回患者列表</button><h1>${escape(profile.display_name)}</h1><h2>云端记录</h2><div id="records"></div><p class="cloud-error" role="alert"></p>`;
      document.getElementById('back').onclick = () => showPatients(0).catch(e => error(e.message));
      await showRecords(ident, own);
    } catch(e) { if (own === generation) main.innerHTML = `<h1>无法打开档案</h1><p>${escape(e.message)}</p><button id="back">返回患者列表</button>`; document.getElementById('back')?.addEventListener('click', () => showPatients(0).catch(e => error(e.message))); }
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
})();
