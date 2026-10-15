"use strict";
const $ = (s) => document.querySelector(s),
  E = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const ui = {
  page: "home",
  snapshot: null,
  day: today(),
  source: "LIVE_CAMERA",
  rehabMode: "training",
  draft: "",
  private: false,
  generation: 0,
  busy: false,
  homeConnection: "loading",
  homeRouteDay: null,
};
const names = {
  home: "首页",
  rehab: "康复",
  health: "健康",
  medication: "用药",
  family: "家人",
};
const icons = {
  home: "M3 10 12 3l9 7v11h-6v-7H9v7H3Z",
  rehab: "M8 3h8v4H8z M7 5H4v16h16V5h-3 M8 12h8 M8 16h5",
  health: "M12 20S2 14 2 8a5 5 0 0 1 10-2 5 5 0 0 1 10 2c0 6-10 12-10 12Z",
  medication:
    "M5 19a5 5 0 0 1 0-7l7-7a5 5 0 0 1 7 7l-7 7a5 5 0 0 1-7 0 M8 9l7 7",
  family:
    "M8 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M1 21v-3a7 7 0 0 1 14 0v3 M17 4a4 4 0 0 1 0 8 M19 15a6 6 0 0 1 4 6",
};
let messageTimer;
function say(text) {
  $("#message").textContent = text;
  $("#message").hidden = false;
  clearTimeout(messageTimer);
  messageTimer = setTimeout(() => ($("#message").hidden = true), 8000);
}
async function api(path, data, options = {}) {
  const ctrl = new AbortController(),
    timer = setTimeout(() => ctrl.abort(), options.timeout || 175000);
  try {
    const r = await fetch("/api" + path, {
      method: data === undefined ? "GET" : "POST",
      headers: {
        "X-Rehab-Client": "mobile-v1",
        ...(data !== undefined ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
      body:
        data === undefined ? undefined : (options.raw ?? JSON.stringify(data)),
      signal: ctrl.signal,
    });
    let value;
    try {
      value = await r.json();
    } catch {
      throw Error("服务没有正常响应，请检查电脑连接。");
    }
    if (!r.ok) {
      if (r.status === 401) pair();
      const error = Error(
        typeof value.detail === "string"
          ? value.detail
          : "操作未完成，请检查填写内容。",
      );
      error.status = r.status;
      throw error;
    }
    return value;
  } catch (e) {
    if (e.name === "AbortError")
      throw Error("等待超时，请刷新核对是否已保存，避免重复提交。");
    if (e instanceof TypeError)
      throw Error("已断开电脑连接。请确认电脑仍开启，并连接同一 Wi-Fi。");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
const post = (operation, data) => api("/product/" + operation + (operation === "chat" ? "?source=" + ui.source : ""), data);
const daily = (operation, data = {}) =>
  api("/unified/daily." + operation + "?source=" + ui.source, data);
const snapshot = () => ui.snapshot || {},
  profile = () => snapshot().profile?.profile || {},
  data = () => snapshot().dailyProduct || {};
const plans = () =>
  snapshot().rehabilitation_ui?.["rehab.get_training_plan"]?.records || [];
const stamp = (v) =>
  v
    ? new Date(v).toLocaleString("zh-CN", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "时间未记录";
const button = (text, id, primary = false) =>
  `<button id="${id}" class="${primary ? "primary" : ""}">${text}</button>`;
function link(text, path, primary = false) {
  return `<a class="button ${primary ? "primary" : ""}" href="${path}">${text}</a>`;
}
function bind(id, fn) {
  const n = $("#" + id);
  if (n) n.onclick = fn;
}
async function act(fn, success = "已保存") {
  if (ui.busy) return;
  ui.busy = true;
  document.body.dataset.busy = 'true';
  say("处理中…");
  clearTimeout(messageTimer);
  document
    .querySelectorAll("button[type=submit],dialog button.primary")
    .forEach((b) => (b.disabled = true));
  try {
    await fn();
    if (success) say(success);
    else $("#message").hidden = true;
    return true;
  } catch (e) {
    say(e.message);
    return false;
  } finally {
    ui.busy = false;
    document.body.dataset.busy = 'false';
    document
      .querySelectorAll("button[type=submit],dialog button.primary")
      .forEach((b) => (b.disabled = false));
  }
}
async function load() {
  const generation = ++ui.generation;
  ui.homeConnection = "loading";
  if (ui.page === "family") window.FamilyV10?.beforeLoad();
  if (ui.page === "health" && !ui.snapshot && window.HealthV131) window.HealthV131.loading();
  if (ui.page === "medication" && !ui.snapshot && window.MedicationV121) window.MedicationV121.loading();
  if (ui.page === "home" && ui.snapshot) home();
  if (ui.page === "rehab" && ui.snapshot && window.RehabV51) rehab();
  try {
    const result = await api("/unified?source=" + ui.source);
    if (generation !== ui.generation) return;
    ui.snapshot = result.snapshot;
    ui.homeConnection = "ready";
    if (ui.page === "family") ui.familyReadAt = Date.now()/1000;
    $("#nav").hidden = false;
    $("#profile").textContent = (profile().name || "我").slice(0, 1);
    render();
  } catch (e) {
    if (generation !== ui.generation) return;
    ui.snapshot = null;
    ui.homeConnection = "offline";
    if (!$("#pair-form") && ui.page === "home") { home(); return; }
    if (!$("#pair-form") && ui.page === "rehab" && window.RehabV51) { rehab(); return; }
    if (!$("#pair-form") && ui.page === "health" && window.HealthV131) { window.HealthV131.failure(e.message); return; }
    if (!$("#pair-form") && ui.page === "medication" && window.MedicationV121) { window.MedicationV121.failure(e.message); return; }
    if (!$("#pair-form") && ui.page === "family" && window.FamilyV10) { window.FamilyV10.failure(e.message); return; }
    if (!$("#pair-form"))
      $("#content").innerHTML =
        `<h1>暂时无法读取</h1><p>${E(e.message)}</p>${button("重新连接", "retry", true)}`;
    bind("retry", load);
  }
}
function nav() {
  if (!$("#nav").querySelector('a')) $("#nav").innerHTML = Object.entries(names)
    .map(
      ([key, title]) =>
        `<a href="#${key}" ${ui.page === key || (ui.page === "assistant" && key === "home") ? 'aria-current="page"' : ""}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[key]}"/></svg><span class="nav-label">${title}</span></a>`,
    )
    .join("");
  $("#nav").querySelectorAll('a').forEach(a => {
    const label = a.querySelector('.nav-label');
    if (label) label.textContent = a.hash === '#family' && ['home','rehab'].includes(ui.page) ? '家人' : names[a.hash.slice(1)];
    if(a.hash === '#' + (['assistant','records','settings','notifications'].includes(ui.page) ? 'home' : ui.page)) a.setAttribute('aria-current','page');
    else a.removeAttribute('aria-current');
  });
  window.ProductMotion?.selectNavigation();
}
function route() {
  if (voiceStarting || recorder?.state === "recording") {
    if (ui.page === "family" && window.FamilyV10?.isAI()) { location.hash = "#family/ai"; say("请先结束或取消录音。"); return; }
    location.hash = ui.page === "medication" && window.MedicationV121?.isAI() ? "#medication/ai" : "#assistant";
    say("请先结束或取消录音。");
    return;
  }
  let key = location.hash.slice(1) || "home";
  if (window.FamilyV10 && window.FamilyV10.reportCode(location.hash) !== null) { window.FamilyV10.routeGuest(); return; }
  if (key === "history") key = "records";
  if (key === "fitness") {
    const context = window.RehabV51?.context(ui.source, ui.day);
    location.href = "/capture?tab=fitness" + (context ? "&" + context : "");
    return;
  }
  ui.page = key.startsWith("family/") ? "family" : key.startsWith("health/") ? "health" : key.startsWith("medication/") ? "medication" : Object.hasOwn(names, key) || ["assistant", "records", "settings", "notifications"].includes(key) ? key : "home";
  if (ui.page === "medication" && ui.homeRouteDay) window.MedicationV121?.selectDay(ui.homeRouteDay);
  ui.day = ui.homeRouteDay || (ui.page === "home" ? ui.day : today());
  ui.homeRouteDay = null;
  if (ui.page === 'rehab' && window.RehabV51) {
    const params=new URLSearchParams(location.search), source=params.get('rehabSource'), day=params.get('rehabDay');
    if (['LIVE_CAMERA','REPLAY_FILE'].includes(source) && window.AnkangHomeV36.dateOf(day)) {
      ui.source=source; ui.day=day;
      window.history.replaceState(null,'',location.pathname+'#rehab');
    }
  }
  nav();
  if (ui.page === "family") load();
  else if (ui.snapshot) render();
  else load();
  window.scrollTo(0, 0);
}
function pair() {
  window.FamilyV10?.reset();
  window.HealthV131?.reset();
  window.MedicationV121?.reset();
  document.body.dataset.page = "pair";
  ui.homeRouteDay = null;
  ui.homeConnection = "loading";
  ui.generation++;
  ui.snapshot = null;
  ui.draft = "";
  ui.private = false;
  const oldDialog=$("#dialog");
  if(oldDialog){oldDialog.close();oldDialog.replaceChildren();}
  $("#nav").hidden = true;
  $("#content").innerHTML =
    `<section class="pair"><h1>连接我的档案</h1><form id="pair-form"><label>电脑显示的连接码<input name="code" autocomplete="off" autocapitalize="none" required maxlength="32"></label><button type="submit" class="primary">连接本人档案</button></form><details><summary>在哪里找连接码？</summary><p>电脑“我的档案” → “连接我的手机”。</p><p>连接后使用同一份档案和记录。电脑保持开启，手机与电脑连接同一可信 Wi-Fi。</p></details></section>`;
  $("#pair-form").onsubmit = async (e) => {
    e.preventDefault();
    const code = new FormData(e.target).get("code").trim();
    if (await act(() => api("/pair", { code }), "已连接本人档案")) await load();
  };
}
function render() {
  document.body.dataset.page = ui.page;
  nav();
  ({ home, rehab, health, medication, family, assistant, records, settings, notifications })[ui.page]();
  window.ProductMotion?.decorate(ui.page);
}
function schedules(day = ui.day) {
  return (data().schedules || [])
    .filter((s) => s.date === day)
    .sort((a, b) => a.time.localeCompare(b.time));
}
function doses(day = ui.day) {
  const rows = [];
  for (const med of profile().medicationRecords || []) {
    const s = data().medSchedules?.[med.id];
    if (
      med.status !== "active" ||
      !s ||
      day < s.start ||
      (s.end && day > s.end)
    )
      continue;
    for (const time of s.times)
      rows.push({
        med,
        time,
        day,
        status:
          data().doses?.[med.id + "|" + day + "|" + time]?.status ||
          "unrecorded",
      });
  }
  return rows.sort((a, b) => a.time.localeCompare(b.time));
}
function homeModel() {
  return window.AnkangHomeV36.model(ui.homeConnection === "ready" ? snapshot() : {}, ui.source, ui.day, today(), ui.homeConnection);
}
function home() {
  document.body.dataset.page = "home";
  const m = homeModel();
  $("#content").innerHTML = window.AnkangHomeV36.markup(m, ui.homeConnection === "ready" ? doses(ui.day) : [], today());
  bind("home-primary", async () => {
    if (ui.busy) return;
    if (m.task.action === "retry") { await load(); return; }
    const generation = ui.generation + 1, source = ui.source, day = ui.day, owner = snapshot().profile?.ownerId;
    await load(); // Recheck bound person, source, plan revision and availability before acting.
    if (ui.page !== "home" || ui.homeConnection !== "ready" || ui.generation !== generation || ui.source !== source || ui.day !== day || snapshot().profile?.ownerId !== owner) return;
    const current = homeModel();
    if (current.task.action === "plan" && current.plan) planDetail(current.plan);
    else if (["train","assess","history"].includes(current.task.action)) location.href = "/capture?tab=" + ({train:"plan",assess:"assess",history:"history"})[current.task.action];
    else { ui.homeRouteDay = ui.day; location.hash = "#rehab"; }
  });
  bind("home-plan", async () => {
    if (ui.busy) return;
    const generation = ui.generation + 1, source = ui.source, day = ui.day, owner = snapshot().profile?.ownerId;
    await load();
    if (ui.page !== "home" || ui.homeConnection !== "ready" || ui.generation !== generation || ui.source !== source || ui.day !== day || snapshot().profile?.ownerId !== owner) return;
    const p = homeModel().plan;
    if (p) planDetail(p);
    else { ui.homeRouteDay = ui.day; location.hash = "#rehab"; }
  });
  bind("home-search", () => {
    const dialog = modal("搜索入口", `<p>暂未提供全局搜索。可在现有动作库中搜索动作。</p><div class="home-search-links">${link("搜索康复动作", "/capture?tab=assess")}${link("我的计划", "#rehab")}${link("历史记录", "#records")}</div>`);
    dialog.querySelectorAll('.home-search-links a').forEach(a => a.onclick = () => dialog.close());
  });
  bind("home-profile", () => $("#profile").click());
  bind("home-refresh", load);
  bind("home-context", () => {
    modal("日期与记录来源", `${sourcePicker()}<label>查看日期<input id="home-date" type="date" value="${E(ui.day)}"></label>`);
    bindSource();
    const changeSource = $("#source").onchange;
    $("#source").onchange = e => { $("#dialog").close(); changeSource(e); };
    $("#home-date").onchange = e => {
      if (!window.AnkangHomeV36.dateOf(e.target.value)) return;
      ui.day = e.target.value; $("#dialog").close(); load();
    };
  });
  document.querySelectorAll('[data-home-day]').forEach(b => b.onclick = () => { ui.day = b.dataset.homeDay; load(); });
  document.querySelectorAll('[data-home-target]').forEach(b => b.onclick = () => { ui.homeRouteDay = ui.day; ui.rehabMode = "training"; location.hash = "#" + b.dataset.homeTarget; });
}

function weeklyPreview() {
 const report=snapshot().history?.report||{};
 return `<section class="journal"><div class="heading"><h2>我的记录与周报</h2>${link("查看全部","#records")}</div><p class="muted">${E(report.rangeText||"本周")}</p><details class="weekly-preview"><summary>本周摘要</summary><div class="report-preview">${(report.sections||[]).slice(0,3).map(s=>`<article><h3>${E(s.title)}</h3><p>${E((s.lines||[]).slice(0,2).join("；"))}</p></article>`).join("")||'<p>暂无记录。</p>'}</div></details></section>`;
}
function records() {
 const report=snapshot().history?.report||{},entries=(snapshot().state?.events||[]).slice().sort((a,b)=>String(b.timestamp).localeCompare(String(a.timestamp)));
 const rehab=Object.entries(snapshot().rehabilitation_ui||{}).filter(([k])=>k!=="rehab.get_training_plan").flatMap(([,v])=>v.records||[]);
 $("#content").innerHTML=`<div class="heading"><h1>我的记录与周报</h1><a href="#home">返回首页</a></div><section class="weekly-report"><h2>本周健康周报</h2><p class="muted">${E(report.rangeText||"")}</p>${(report.sections||[]).map(s=>`<article><h3>${E(s.title)}</h3>${(s.lines||[]).map(x=>`<p>${E(x)}</p>`).join("")}</article>`).join("")}</section><details><summary>健康记录</summary>${entries.map(e=>`<article class="row"><div><small>${stamp(e.timestamp)}</small><p>${E(eventText(e))}</p></div></article>`).join("")||'<p class="empty">暂无记录。</p>'}</details><p>${link("查看逐次服药记录","#medication")}</p><details open><summary>康复评估与训练记录</summary>${sourcePicker()}${rehab.map(r=>`<article class="row"><div><strong>${E(r.exercise_label||r.exercise_id||"动作记录")}</strong><p>${stamp(r.end_utc||r.timestamp)} · ${E(r.side==='left'?'左侧':r.side==='right'?'右侧':'')}</p></div></article>`).join("")||'<p class="empty">当前来源尚无保存的康复记录。</p>'}${link("查看手机分析报告","/capture?tab=history")}</details>`;
 bindSource();
}

function settings() {
  const mode = snapshot().profile?.dataMode;
  let connected=false;try{connected=!!assistantIdentity();}catch{}
  $("#content").innerHTML = `<div class="heading"><h1>设置</h1><a href="#home">返回首页</a></div><section><h2>我的档案</h2><p>${E(profile().name || "称呼未填写")}${profile().age ? " · " + E(profile().age) + " 岁" : ""}</p><p class="muted">${mode === "demo" ? "演示档案" : mode === "personal" ? "个人档案" : "请在电脑核对档案类型"}</p>${button("编辑我的档案", "settings-profile")}</section><p>${button("联系康复医师", "settings-clinician")}</p><section><h2>查看记录的来源</h2>${sourcePicker()}<p class="muted">来源选择用于查看康复记录，不会启动摄像头或训练。</p></section><p>${link("查看通知记录", "#notifications")}</p><section><h2>智能服务</h2><p>${connected ? "管家通过安康云端服务回答；每条回复标明实际来源。" : "登录本人云账号后可使用云端管家；当前使用本地回复。"}</p>${link("打开康复管家", "#assistant")}</section>`;
  bind("settings-profile", editProfile);
  bind("settings-clinician", openClinicianContact);
  bindSource();
}

function notifications() {
  const ledger = Array.isArray(snapshot().notifications) ? snapshot().notifications : [];
  const phases = {pending:"待处理",accepted:"通道已受理",sent:"通道回报已发送",delivered:"通道回报已送达",failed:"通道失败",unavailable:"通道不可用"};
  const channels = {in_app:"应用内",browser_push:"浏览器推送",webhook_push:"外部推送"};
  $("#content").innerHTML = `<div class="heading"><h1>通知记录</h1><a href="#home">返回首页</a></div><p class="muted">以下为已有通知台账。受理、发送和送达是不同状态；查看此页不会发送新通知。</p>${ledger.slice().sort((a,b)=>String(b.createdAt).localeCompare(String(a.createdAt))).map(n=>`<article class="row"><div><strong>${E(n.title || "通知")}</strong><p>${E(n.message || "")}</p><small>${E(stamp(n.createdAt))} · ${E(phases[n.phase] || "状态待核对")}</small>${(Array.isArray(n.deliveries)?n.deliveries:[]).map(d=>`<p><small>${E(channels[d.channel] || d.channel || "通知通道")}：${E(phases[d.status] || "状态待核对")}${d.detail?" · "+E(d.detail):""}</small></p>`).join("")}</div></article>`).join("") || '<p class="empty">暂无通知台账。</p>'}`;
}

function eventText(e) {
 const labels={weight:'体重',sbp:'收缩压',systolic:'收缩压',dbp:'舒张压',diastolic:'舒张压',heartRate:'心率',restingHr:'静息心率',spo2:'血氧',temperature:'体温',glucose:'血糖',bloodGlucose:'血糖',steps:'步数',walkSpeed:'步行速度',sleepHours:'睡眠时长',nightWakes:'夜间醒来'};
 const m=e.measurement,l=e.labResult;
 return e.observation?.text || (m ? `${labels[m.metric]||m.metric} ${m.value} ${m.unit||''}` : l ? `${l.name} ${l.value} ${l.unit||''}` : '健康记录');
}

function sourcePicker() {
  return `<label class="source">记录来源<select id="source"><option value="LIVE_CAMERA">电脑实时</option><option value="REPLAY_FILE">录像分析</option></select></label>`;
}
function bindSource() {
  if ($("#source")) {
    $("#source").value = ui.source;
    $("#source").onchange = (e) => {
      ui.source = e.target.value;
      load();
    };
  }
}
function rehabModes() {
  return `<div class="mode-nav" role="group" aria-label="康复功能">${[["training","训练"],["assessment","评估"],["fitness","健身"]].map(([k,t])=>`<button data-rehab-mode="${k}" aria-pressed="${ui.rehabMode===k}">${t}</button>`).join("")}</div>`;
}
function bindModes() {document.querySelectorAll('[data-rehab-mode]').forEach(b=>b.onclick=()=>{ui.rehabMode=b.dataset.rehabMode;rehab();});}
function rehab() {
  if (window.RehabV51) { renderRehabV51(); return; }
  if(ui.rehabMode!=="training") {
    const assessment=ui.rehabMode==="assessment";
    $("#content").innerHTML=`<div class="heading"><h1>康复</h1></div>${rehabModes()}<section class="tool-intro"><h2>${assessment?"身体评估":"健身动作"}</h2><p>${assessment?"选一个动作，拍摄后查看结果。":"选择动作，分析你的训练录像。"}</p>${link(assessment?"开始评估":"打开动作库",assessment?"/capture?tab=assess":"/capture?tab=fitness",true)}</section>`;
    bindModes();return;
  }
  const p = plans()[0],
    next = p?.items.find((i) => i.key === p.progress?.next_key);
  $("#content").innerHTML =
    `<div class="heading"><h1>康复</h1></div>${rehabModes()}${sourcePicker()}<section class="hero"><p class="eyebrow">${p ? "下一项训练" : "我的训练计划"}</p><h1>${E(next?.exercise_label || (p ? "这一轮已完成" : "先做一次评估"))}</h1><p class="muted">${next ? `${next.side === "left" ? "左侧" : "右侧"} · ${E(next.settings.target_reps ?? "未设置")} 次 × ${E(next.settings.target_sets ?? 1)} 组` : p ? "结果已保存，可在历史记录中查看。" : "根据评估结果安排训练。"}</p>${p ? `<progress value="${Number(p.progress?.completed) || 0}" max="${Math.max(1, Number(p.progress?.total) || 1)}" aria-label="本轮完成进度"></progress>` : ""}${p?.availability_reason ? `<p class="notice">${E(p.availability_reason)}</p>` : ""}<div class="actions">${ui.source === "REPLAY_FILE" ? link(p && next ? "开始下一项" : "查看训练计划", "/capture?tab=plan", true) : p ? button("查看计划", "plan-detail", true) : link("开始评估", "/capture?tab=assess", true)}${p ? button("安排日期", "schedule") : ""}</div>${ui.source === "LIVE_CAMERA" && p ? '<p class="muted">在电脑康复页开始训练；手机可查看、安排日期。</p>' : ""}</section><div class="heading"><h2>日期安排</h2><input class="date" id="day" type="date" aria-label="查看康复日期" value="${ui.day}"></div>${
      schedules()
        .map(
          (s) =>
            `<div class="row"><time>${E(s.time)}</time><div><strong>${E(s.name)}</strong><p><small>${s.kind === "assessment" ? "评估安排" : "训练安排"}</small></p></div><button data-cancel="${E(s.id)}" aria-label="取消${E(s.name)}的安排">取消</button></div>`,
        )
        .join("") ||
      '<p class="empty">当天暂无安排。</p>'
    }<details><summary>计划与更多工具</summary>${plans()
      .map(
        (p) =>
          `<div class="row"><div><strong>${E(p.name)}</strong><p><small>版本 ${E(p.revision)} · ${p.items.length} 项</small></p></div><button data-plan="${E(p.id)}">详情</button></div>`,
      )
      .join(
        "",
      )}<div class="actions">${link("手机制定计划", "/capture?tab=plan")}${link("体态与动作库", "/capture?tab=assess")}${link("健身工具", "/capture?tab=fitness")}</div><p class="muted">电脑端保留手动添加、编辑及旧计划版本。新计划另存，旧记录保留。</p></details>`;
  bindSource();
  $("#day").onchange = (e) => {
    if (e.target.value) {
      ui.day = e.target.value;
      rehab();
    }
  };
  bindModes();
  bind("plan-detail", () => planDetail(p));
  bind("schedule", () => schedule(p));
  document
    .querySelectorAll("[data-plan]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          planDetail(plans().find((p) => p.id === b.dataset.plan))),
    );
  document
    .querySelectorAll("[data-cancel]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          confirmAction("取消这次安排？", "训练记录和原计划会保留。", () =>
            daily("unschedule", { id: b.dataset.cancel }),
          )),
    );
}
let modalGeneration=0;
function modal(title, body) {
  ++modalGeneration;
  const d = $("#dialog");
  d.classList.remove('paired-contact');
  d.innerHTML = `<div class="heading"><h2 id="dialog-title">${E(title)}</h2><button id="close-dialog" class="quiet" aria-label="关闭">关闭</button></div>${body}`;
  bind("close-dialog", () => d.close());
  if (!d.open) d.showModal();
  return d;
}
function confirmAction(title, text, fn) {
  modal(
    title,
    `<p>${E(text)}</p><button class="primary" id="confirm">确认</button>`,
  );
  bind("confirm", async () => {
    if (await act(fn)) {
      $("#dialog").close();
      load();
    }
  });
}
function planDetail(p) {
  modal(
    p.name,
    `<p class="muted">版本 ${E(p.revision)} · ${ui.source === "LIVE_CAMERA" ? "电脑实时" : "手机录像"}</p>${p.items.map((i, n) => `<div class="row"><span>${n + 1}</span><div><strong>${E(i.exercise_label)}</strong><p>${i.side === "left" ? "左侧" : "右侧"} · ${E(i.settings.target_reps ?? "未设置")} 次 × ${E(i.settings.target_sets ?? 1)} 组</p><small>${E(i.availability_reason || "")}</small></div></div>`).join("")}<div class="actions">${button("安排日期", "detail-schedule", true)}</div>`,
  );
  bind("detail-schedule", () => schedule(p));
}
function schedule(p) {
  modal(
    "安排训练日期",
    `<form id="schedule-form"><p>${E(p.name)}</p><label>日期<input name="date" type="date" required min="${today()}" value="${today()}"></label><label>时间<input name="time" type="time" required value="09:00"></label><button type="submit" class="primary">保存安排</button></form>`,
  );
  $("#schedule-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    if (
      await act(() =>
        daily("schedule", {
          ...f,
          kind: "training",
          name: p.name,
          planId: p.id,
          revision: p.revision,
        }),
      )
    ) {
      $("#dialog").close();
      load();
    }
  };
}
function health() {
  if (window.HealthV131) { window.HealthV131.render(); return; }
  const events = (snapshot().state?.events || [])
    .slice()
    .sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));
  $("#content").innerHTML =
    `<div class="heading"><h1>健康档案</h1>${button("编辑资料", "edit-profile")}</div><p class="muted">${E(profile().name)}${profile().age ? " · " + E(profile().age) + " 岁" : ""}<br>${E((profile().conditions || []).join("、") || "健康情况未填写")}</p><div class="actions">${button("上传资料", "upload", true)}${link("手动记录指标", "/capture?tab=health")}${link("问 AI", "#assistant")}</div><div class="heading"><h2>资料与图片</h2></div>${(snapshot().attachments || []).map((a) => `<div class="row"><div><strong>${E(a.name)}</strong><p><small>${E(a.category)} · ${stamp(a.date)}</small></p></div><button data-archive="${E(a.id)}">查看</button></div>`).join("") || '<p class="empty">暂无资料。</p>'}<div class="heading"><h2>最近记录</h2></div><div class="timeline">${
      events
        .slice(0, 20)
        .map(
          (e) =>
            `<article><small>${stamp(e.timestamp)}</small><p>${E(eventText(e))}</p></article>`,
        )
        .join("") ||
      '<p class="empty">暂无身体记录。</p>'
    }</div><div class="actions">${link("资料回收站与备份", "/capture?tab=archive")}</div>`;
  bind("edit-profile", editProfile);
  bind("upload", upload);
  bindSource();
  document
    .querySelectorAll("[data-archive]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          archiveDetail(
            snapshot().attachments.find((a) => a.id === b.dataset.archive),
          )),
    );
}
function openClinicianContact() {
  $("#dialog")?.close();
  if (window.PhoneAccount?.open) return window.PhoneAccount.open();
  return pairedClinicianContact();
}
function editProfile() {
  if (!ui.snapshot) return;
  const p = profile();
  modal(
    "我的档案",
    `<form id="profile-form"><label>称呼<input name="name" maxlength="40" value="${E(p.name)}" required></label><label>年龄<input type="number" name="age" min="0" max="130" value="${Number(p.age) || 0}" required></label><label>已知健康情况，用逗号分隔<textarea name="conditions" maxlength="1000">${E((p.conditions || []).join("，"))}</textarea></label><button type="submit" class="primary">保存资料</button></form><div class="actions"><a href="#settings" id="profile-settings">设置</a><a href="#notifications" id="profile-notifications">通知记录</a>${button("联系康复医师", "profile-clinician")}</div>`,
  );
  bind("profile-clinician", openClinicianContact);
  for (const id of ["profile-settings", "profile-notifications"]) bind(id, () => $("#dialog").close());
  $("#profile-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    if (
      await act(() =>
        post("profile.save", {
          profile: {
            ...p,
            ...f,
            age: Number(f.age),
            conditions: f.conditions
              .split(/[,，]/)
              .map((x) => x.trim())
              .filter(Boolean),
          },
        }),
      )
    ) {
      $("#dialog").close();
      load();
    }
  };
}
function upload() {
  modal(
    "拍照或上传健康资料",
    `<form id="upload-form"><label>资料名称<input name="name" maxlength="100" required placeholder="例如：本次复查报告"></label><label>分类<select name="category">${["体检报告", "就诊记录", "检验检查", "影像资料", "病历资料", "其他资料"].map((c) => `<option>${c}</option>`).join("")}</select></label><div class="actions"><button type="button" id="take-photo">用手机拍照</button><input id="photo-file" type="file" accept="image/jpeg,image/png" capture="environment" hidden></div><p id="photo-selected" class="muted"></p><label>或选择文件（最多 8 MB）<input id="file" type="file" accept="image/jpeg,image/png,application/pdf,text/plain"></label><button type="submit" class="primary">保存到本人档案</button></form>`,
  );
  let chosenFile = null;
  bind("take-photo", () => $("#photo-file").click());
  $("#photo-file").onchange = (e) => {
    chosenFile = e.target.files[0];
    $("#photo-selected").textContent = chosenFile
      ? "已选择照片"
      : "";
  };
  $("#file").onchange = (e) => {
    chosenFile = e.target.files[0];
    $("#photo-selected").textContent = "";
  };
  $("#upload-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target),
      file = chosenFile;
    if (!file) {
      say("先拍照或选择文件。");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      say("请选择 8 MB 以内的资料。");
      return;
    }
    if (
      await act(() =>
        api(
          "/product-archive?consent=yes&" +
            new URLSearchParams({
              name: f.get("name"),
              category: f.get("category"),
            }),
          {},
          { raw: file, headers: { "Content-Type": file.type } },
        ),
      )
    ) {
      $("#dialog").close();
      load();
    }
  };
}
function archiveDetail(a) {
  modal(
    a.name,
    `<p class="muted">${E(a.category)}</p><div class="actions">${link("下载原件", "/api/product-archive/" + encodeURIComponent(a.id))}${button("手动记录指标", "manual-health", true)}${button("移入回收站", "trash")}</div><p class="muted">报告原件仅作资料保存，不识字、不自动提取指标。请核对后手动填写。</p>`,
  );
  bind("trash", () =>
    confirmAction("移入回收站？", "资料可以在回收站恢复。", () =>
      api("/product-archive/" + a.id + "/trash", { confirm: true }),
    ),
  );
  bind("manual-health", () => {
    $("#dialog").close();
    location.href = "/capture?tab=health";
  });
}
function medication() {
  if (window.MedicationV121) { window.MedicationV121.render(); return; }
  const rows = doses();
  $("#content").innerHTML =
    `<div class="heading"><h1>用药</h1><input class="date" id="day" type="date" value="${ui.day}" aria-label="查看用药日期"></div><details class="page-note"><summary>用药记录说明</summary><p>按已有医嘱安排。未记录不等于漏服。</p></details>${rows.map((r, i) => `<div class="row"><time>${E(r.time)}</time><div><strong>${E(r.med.name)}</strong><p>${E(r.med.dose || "剂量未填写")}</p><small class="${r.status === "taken" ? "status" : ""}">${{ taken: "已服用", skipped: "已跳过", unrecorded: "未记录" }[r.status]}</small></div><button data-dose="${i}" ${r.day > today() ? "disabled" : ""}>${r.status === "unrecorded" ? "记录" : "更正"}</button></div>`).join("") || '<p class="empty">当天暂无用药安排。</p>'}<div class="heading"><h2>我的药物</h2>${button("添加药物", "add-med")}</div>${(profile().medicationRecords || []).map((m) => `<div class="row"><div><strong>${E(m.name)}</strong><p><small>${E(m.dose)} · ${m.status === "active" ? "在用" : "已停用"}</small></p></div><button data-med="${E(m.id)}">管理</button></div>`).join("")}<details><summary>记录更正历史</summary>${
      (data().doseAudit || [])
        .slice(0, 20)
        .map(
          (r) =>
            `<p><small>${stamp(r.at)}</small><br>${E(r.record.medName)} · ${E(r.record.date)} ${E(r.record.time)}：${{ taken: "已服用", skipped: "已跳过", unrecorded: "未记录" }[r.record.status]}</p>`,
        )
        .join("") || '<p class="muted">暂无更正记录。</p>'
    }</details>`;
  $("#day").onchange = (e) => {
    if (e.target.value) {
      ui.day = e.target.value;
      medication();
    }
  };
  bind("add-med", () => editMed());
  document
    .querySelectorAll("[data-dose]")
    .forEach((b) => (b.onclick = () => dose(rows[Number(b.dataset.dose)])));
  document
    .querySelectorAll("[data-med]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          editMed(
            (profile().medicationRecords || []).find(
              (m) => m.id === b.dataset.med,
            ),
          )),
    );
}
function dose(r) {
  modal(
    "记录这次服药",
    `<p>${E(r.med.name)} · ${E(r.med.dose)}<br>${E(r.day)} ${E(r.time)}</p><div class="actions">${["taken", "skipped", "unrecorded"].map((s, i) => button(["已服用", "已跳过", "更正为未记录"][i], s, i === 0)).join("")}</div>`,
  );
  for (const status of ["taken", "skipped", "unrecorded"])
    bind(status, async () => {
      if (
        await act(() =>
          daily("dose", { medId: r.med.id, date: r.day, time: r.time, status }),
        )
      ) {
        $("#dialog").close();
        load();
      }
    });
}
function editMed(m = {}) {
  modal(
    m.id ? "管理药物" : "添加药物",
    `<form id="med-form"><label>药物名称<input name="name" maxlength="100" required value="${E(m.name)}"></label><label>每次剂量<input name="dose" maxlength="100" value="${E(m.dose)}" placeholder="按已有医嘱填写"></label><label>用途<input name="purpose" maxlength="200" value="${E(m.purpose)}"></label><label>服用说明<input name="times" maxlength="100" value="${E(m.times)}"></label><div class="actions"><button type="submit" class="primary">保存药物</button>${m.id ? button("设置提醒时间", "med-times") : ""}${m.id ? button(m.status === "active" ? "标记停用" : "恢复在用", "med-status") : ""}</div></form>`,
  );
  $("#med-form").onsubmit = async (e) => {
    e.preventDefault();
    const record = {
      id:
        m.id || "med-" + Date.now() + "-" + Math.random().toString(16).slice(2),
      status: m.status || "active",
      ...Object.fromEntries(new FormData(e.target)),
    };
    if (await act(() => post("medication.save", { record }))) {
      $("#dialog").close();
      await load();
      medTimes(record);
    }
  };
  bind("med-times", (e) => {
    e.preventDefault();
    medTimes(m);
  });
  bind("med-status", (e) => {
    e.preventDefault();
    confirmAction(
      "更改药物状态？",
      "这只更改你的记录，不会删除过去的服用历史。",
      () =>
        post("medication.status", {
          id: m.id,
          status: m.status === "active" ? "stopped" : "active",
        }),
    );
  });
}
function medTimes(m) {
  const s = data().medSchedules?.[m.id] || {};
  modal(
    "设置服用时间",
    `<form id="times-form"><p>${E(m.name)}</p><label>每天的时间，以逗号分隔<input name="times" required value="${E((s.times || []).join(", "))}" placeholder="08:00, 20:00"></label><label>开始日期<input name="start" type="date" required value="${E(s.start || today())}"></label><label>结束日期（可选）<input name="end" type="date" value="${E(s.end)}"></label><button type="submit" class="primary">保存时间</button></form>`,
  );
  $("#times-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    if (
      await act(() =>
        daily("medSchedule", {
          medId: m.id,
          ...f,
          times: f.times
            .split(/[,，]/)
            .map((s) => s.trim())
            .filter(Boolean),
        }),
      )
    ) {
      $("#dialog").close();
      load();
    }
  };
}
const categoryNames = {
  health: "健康近况",
  rehab: "康复完成情况",
  medication: "用药记录",
};
function family() {
  if (window.FamilyV10) { window.FamilyV10.render(); return; }
  $("#content").innerHTML =
    `<h1>家人的近况</h1><p class="muted">仅显示家人已授权的记录。</p>${
      (snapshot().familyMembers || [])
        .map(
          (m) =>
            `<section class="sheet"><h2>${E(m.name)}</h2><p class="muted">${m.categories.map((c) => categoryNames[c]).join("、") || "对方尚未共享信息"}</p>${(m.health || []).map((r) => `<p>${E(r.text)}<br><small>${stamp(r.timestamp)}</small></p>`).join("")}${(m.rehab || []).map((r) => `<p>${E(r.text)}<br><small>${stamp(r.timestamp)}</small></p>`).join("")}${(
              m.doses || []
            )
              .slice(-3)
              .map(
                (r) =>
                  `<p>${E(r.medName)} · ${E(r.date)} ${E(r.time)} · ${{ taken: "已服用", skipped: "已跳过", unrecorded: "未记录" }[r.status]}</p>`,
              )
              .join(
                "",
              )}<div class="actions"><button data-grant="${E(m.ownerId)}">我向对方共享什么</button><button data-unbind="${E(m.ownerId)}">解除关联</button></div></section>`,
        )
        .join("") ||
      '<section class="hero"><h2>还未关联家人</h2><p class="muted">输入家人的邀请码，关联后选择共享内容。</p></section>'
    }<div class="actions">${button("关联家人", "bind", true)}${button("家庭邀请码", "invite")}</div><p class="notice">关联后默认不共享记录。</p><details><summary>关联与共享说明</summary><p>双方分别建立本人档案并连接手机，使用家庭邀请码关联。共享范围分别选择，不能修改对方档案。</p><p>家庭邀请码与手机连接码不同；手机连接码允许操作本人档案，请勿提供给家人作为邀请码。</p></details>`;
  bind("invite", async () => {
    let r;
    if (
      await act(async () => {
        r = await daily("familyInvite");
      }, "")
    )
      modal(
        "家庭邀请码",
        `<p>让家人在其本人档案的“家庭”页输入：</p><h1>${E(r.code)}</h1><p class="muted">15 分钟内有效。关联后再分别选择共享范围。</p>`,
      );
  });
  bind("bind", () => {
    modal(
      "关联家人",
      `<form id="bind-form"><label>家人提供的家庭邀请码<input name="code" required maxlength="8"></label><button type="submit" class="primary">确认关联</button></form>`,
    );
    $("#bind-form").onsubmit = async (e) => {
      e.preventDefault();
      if (
        await act(() =>
          daily("familyBind", Object.fromEntries(new FormData(e.target))),
        )
      ) {
        $("#dialog").close();
        load();
      }
    };
  });
  document.querySelectorAll("[data-grant]").forEach(
    (b) =>
      (b.onclick = () => {
        const member = b.dataset.grant,
          selected = data().grants?.[member] || [];
        modal(
          "我向这位家人共享",
          `<form id="grant-form" class="checklist">${Object.entries(
            categoryNames,
          )
            .map(
              ([c, n]) =>
                `<label><input type="checkbox" name="category" value="${c}" ${selected.includes(c) ? "checked" : ""}>${n}</label>`,
            )
            .join(
              "",
            )}<p class="muted">聊天、病历原件和联系方式不会在这里共享。健康近况只包含已单独允许家人查看的记录。</p><button type="submit" class="primary">保存共享范围</button></form>`,
        );
        $("#grant-form").onsubmit = async (e) => {
          e.preventDefault();
          const categories = new FormData(e.target).getAll("category");
          if (await act(() => daily("familyGrant", { member, categories }))) {
            $("#dialog").close();
            load();
          }
        };
      }),
  );
  document
    .querySelectorAll("[data-unbind]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          confirmAction(
            "解除家庭关联？",
            "双方将不再通过此关系查看彼此的近况。",
            () => daily("familyUnbind", { member: b.dataset.unbind }),
          )),
    );
}
let recorder = null,
  stream = null,
  recordTimer = null,
  recordCancelled = false,
  voiceStarting = false;
function conversationSource(metadata) {
  if (metadata?.provider === "deepseek" && metadata.status === "replied") return "DeepSeek 回复";
  if (metadata?.provider === "local" && metadata.status === "replied") return "本地回复";
  if (metadata?.provider === "local" && metadata.status === "unavailable" && metadata.reason === "not_configured") return "未配置 DeepSeek · 本地回复";
  if (metadata?.provider === "local" && metadata.status === "failed") return "DeepSeek 本轮未完成 · 本地回复";
  return "";
}
function assistantPrivate(text,flag=false){
  if(window.PhoneAccount?.assistantPrivate)return window.PhoneAccount.assistantPrivate(text,flag);
  return flag===true||/(不要|别).{0,4}(记录|记下来|保存)|(?:不要|别|不想|不希望|不愿意|不愿|不需要).{0,4}(告诉|让|通知).{0,3}(孩子|女儿|儿子|家人|他|她|他们|她们)|(?:不想|不希望|不愿意|不愿|不需要).{0,2}(?:让|叫)?(?:孩子|女儿|儿子|家人).{0,3}(?:知道|看见)/.test(text);
}
function assistantIdentity(){
  if(window.PhoneLocal){
    if(!window.PhoneAccount?.identity())return null;
    try{const value=window.PhoneAccount.aiScope(window.PhoneLocal.store);
    return {key:[snapshot().ownerId,value.account_id,value.patient_id].join(':'),...value};}catch{return null;}
  }
  const value=snapshot().cloudAssistant;
  return value?.connected?{...value,key:[snapshot().ownerId,value.account_id,value.patient_id].join(':')}:null;
}
async function assistantRequest(action,body={}){
  if(window.PhoneLocal){
    const account=window.PhoneAccount,store=window.PhoneLocal.store;
    if(action==='assistantPreferences')return account.assistantPreferences(store,body.health_context===undefined?undefined:body);
    if(action==='assistantConversation')return account.assistantConversation(store,body.after??0);
    if(action==='assistantTurn')return account.assistantTurn(store,body.text??null,body.retry_operation_id??null);
    if(['candidate','workflow','workflowProfile'].includes(action)){const before={...account.aiScope(store)},result=await account.request(action,before,body),after=account.aiScope(store);if(before.account_id!==after.account_id||before.patient_id!==after.patient_id)throw Error('账号已变化');return result;}
    throw Error('未开放此管家操作');
  }
  return api('/unified/workbench.'+action+'?source='+encodeURIComponent(ui.source),body);
}
function assistantTurns(items){
  const rows=new Map();for(const row of items||[])if(row&&typeof row.id==='string'&&typeof row.text==='string'&&typeof row.answer==='string')rows.set(row.id,row);
  return [...rows.values()].sort((a,b)=>a.sequence-b.sequence);
}
function assistantMessages(items){
  return assistantTurns(items).flatMap(row=>{
    const time=typeof row.created_at==='number'?new Date(row.created_at*1000).toISOString():row.created_at;
    const common={time,cloud_turn_id:row.id,persisted:true};
    return [{...common,id:row.id+':user',role:'elder',text:row.text},{...common,id:row.id+':answer',role:'agent',text:row.answer,actions:row.actions,conversation:row.source?{provider:row.source,status:'replied'}:undefined}];
  });
}
function assistantActions(actions,turnId){
  return (Array.isArray(actions)?actions:[]).slice(0,4).map(action=>{
    if(action?.kind==='assessment_plan'&&/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(action.plan_id))return link('查看评估计划','/capture?tab=plan&assessmentPlan='+encodeURIComponent(action.plan_id)+'#assessment-plans');
    if(action?.kind==='assessment'&&/^[a-z][a-z0-9_]{0,79}$/.test(action.exercise_id))return link('打开本人评估','/capture?tab=assess&entry=assistant&exercise='+encodeURIComponent(action.exercise_id));
    if(action?.kind==='plan')return link('查看康复计划','#rehab');
    if(action?.kind==='candidate'&&['STARTER','PROGRESSION'].includes(action.candidate_kind))return `<button type="button" data-assistant-turn="${E(turnId)}" data-assistant-candidate="${action.candidate_kind}">${action.candidate_kind==='STARTER'?'提交起始候选核对':'提交进阶候选核对'}</button>`;
    if(action?.kind==='doctor_review')return '<button type="button" data-assistant-doctor>联系康复医师</button>';
    return '';
  }).join('');
}
function pendingAssistantQuestions(){
  if(window.PhoneLocal&&window.PhoneAccount?.assistantPending)return window.PhoneAccount.assistantPending(window.PhoneLocal.store);
  const old=window.PhoneLocal?.store.value.cloudAssistantPending||snapshot().cloudAssistant?.pending;
  return old?[old]:[];
}
function scheduleAssistantRecovery(state){
  if(ui.page!=='assistant'||ui.assistantCloud!==state)return;
  const key=pendingAssistantQuestions().map(row=>row.operation_id).join(':');
  if(state.recoveryKey!==key){state.recoveryKey=key;state.recoveryAttempts=0;}
  if(!key||state.recoveryTimer||state.recoveryAttempts>=15)return;
  state.recoveryTimer=setTimeout(()=>{
    state.recoveryTimer=null;
    if(ui.page!=='assistant'||ui.assistantCloud!==state)return;
    state.recoveryAttempts++;
    if(ui.busy||state.loading){scheduleAssistantRecovery(state);return;}
    void refreshAssistant(state,true);
  },4000);
}
async function refreshAssistant(state,quiet=false){
  if(state.loading)return;state.loading=true;
  const priorPending=pendingAssistantQuestions(),before=JSON.stringify([state.items,state.error,priorPending]);
  try{
    const [preferences,conversation]=await Promise.all([assistantRequest('assistantPreferences'),assistantRequest('assistantConversation',{after:state.pending_after??state.next_after??0})]);
    if(assistantIdentity()?.key!==state.key)return;
    const rows=new Map((state.rows||[]).map(row=>[row.id,row]));for(const row of conversation.items)rows.set(row.id,row);
    state.rows=[...rows.values()];const unresolved=state.rows.filter(row=>typeof row.answer!=='string');
    state.pending_after=unresolved.length?Math.min(...unresolved.map(row=>row.sequence))-1:null;
    if(priorPending.some(intent=>intent.text===ui.draft&&conversation.items.some(row=>row.operation_id===intent.operation_id&&row.text===intent.text&&typeof row.answer==='string')))ui.draft='';
    state.preferences=preferences;state.items=assistantTurns([...state.items,...conversation.items]);state.next_after=conversation.next_after;state.has_more=conversation.has_more;state.error='';state.loaded=true;
  }catch(error){state.error=error.message;state.loaded=true;}
  finally{
    state.loading=false;
    if(ui.page==='assistant'&&ui.assistantCloud===state){
      if(!quiet||before!==JSON.stringify([state.items,state.error,pendingAssistantQuestions()])){
        const focused=quiet&&document.activeElement?.id==='draft',start=focused?document.activeElement.selectionStart:null,end=focused?document.activeElement.selectionEnd:null;
        assistant();if(focused){$('#draft')?.focus?.();$('#draft')?.setSelectionRange?.(start,end);}
      }
      scheduleAssistantRecovery(state);
    }
  }
}
async function openAssistantWorkflow(state){
  const value=await assistantRequest('workflow');
  if(assistantIdentity()?.key!==state.key)throw Error('账号已变化');
  const p=value.profile||{},regions=['肩','肘','腕','髋','膝','踝','颈','躯干','一般活动'];
  modal('康复目标与条件',`<form id="assistant-workflow-form"><label>目标<textarea id="assistant-goal" maxlength="500" required>${E(p.goal||'')}</textarea></label><label>身体部位<select id="assistant-region">${regions.map(region=>`<option ${region===p.region?'selected':''}>${region}</option>`).join('')}</select></label><label>器材（逗号分隔）<input id="assistant-equipment" value="${E((p.equipment||[]).join('，'))}" maxlength="1000"></label><label>限制（逗号分隔，无则留空）<input id="assistant-restrictions" value="${E((p.restrictions||[]).join('，'))}" maxlength="1000"></label><label>当前任务等级<select id="assistant-level">${[0,1,2,3].map(level=>`<option value="${level}" ${level===(p.level??0)?'selected':''}>L${level}</option>`).join('')}</select></label><label><input id="assistant-screening" type="checkbox" required>我已核对适用条件、器材及限制；不确定时先联系康复医师</label><p class="muted">保存目标不会开启资料上传或医生共享。提交候选前，需在原评估页面保存真实评估，并另行明确开启同步与医生授权。</p><button type="submit" class="primary">保存目标与条件</button></form>`);
  $('#assistant-workflow-form').onsubmit=async event=>{
    event.preventDefault();
    const split=id=>$(id).value.split(/[,，]/).map(item=>item.trim()).filter(Boolean);
    const document={expected_version:value.profile_version,goal:$('#assistant-goal').value.trim(),region:$('#assistant-region').value,equipment:split('#assistant-equipment'),restrictions:split('#assistant-restrictions'),level:Number($('#assistant-level').value),screening_confirmed:$('#assistant-screening').checked};
    const ok=await act(async()=>{if(assistantIdentity()?.key!==state.key)throw Error('账号已变化');await assistantRequest('workflowProfile',document);},'目标与条件已保存；评估同步和医生授权仍需另行开启');
    if(ok)$('#dialog').close();
  };
}
function assistant() {
  let identity=null,identityError='';try{identity=assistantIdentity();}catch(error){identityError=error.message;}
  if(!identity||ui.assistantCloud?.key!==identity.key)ui.assistantCloud=identity?{key:identity.key,items:[],preferences:null,loaded:false,loading:false,candidates:{}}:null;
  const cloud=ui.assistantCloud,local=snapshot().state?.chat||[];
  const chat=cloud?[...local.filter(m=>!m.cloud_turn_id),...assistantMessages(cloud.items)]:local;
  const preferences=cloud?.preferences,pendingRows=cloud?pendingAssistantQuestions():[],pending=pendingRows[0];
  const cloudControls=cloud?`<label><input id="assistant-health-context" type="checkbox" ${preferences?.health_context===true?'checked':''} ${!Number.isSafeInteger(preferences?.version)?'disabled':''}>允许管家使用我的云端康复资料</label><p class="muted">仅使用已同步到本人云账号的资料。此授权不会开启记录上传或医生共享。</p><button type="button" id="assistant-workflow">康复目标与条件</button><button type="button" id="assistant-sync">${cloud.has_more?'继续同步对话':'同步对话'}</button><p role="status">${E(cloud.error||(cloud.loading?'正在同步管家对话…':''))}</p>`:`<p class="muted">${E(identityError||'登录本人云账号后可同步管家对话；未登录及私密对话使用本地回复。')}</p>`;
  $("#content").innerHTML =
    `<div class="heading"><h1>康复管家</h1><a href="#home">返回首页</a></div><details class="assistant-capability"><summary>使用说明</summary><p>${cloud?"康复问答与结果解说；云端管家已连接。":"康复问答与结果解说；当前使用本地资料。"}</p><p>${cloud?'云端管家可将评估安排保存到“我的计划”的评估计划；完成状态由实际上传评估核对。':'登录本人云账号后可读取管家保存的评估计划。'}对话不代填测量结果。共用动作库含63张评估卡和122张训练卡；候选计划先使用已整理的起始模板。</p>${cloudControls}</details><section class="conversation" aria-label="对话记录">${chat.map((m) => `<div class="bubble ${m.role === "elder" ? "mine" : ""}"><small>${m.role === "elder" ? "我" : "康复管家"}${m.time ? " · " + stamp(m.time) : ""}${m.persisted === false ? " · 本次不记录" : ""}${m.pending ? " · 待确认" : ""}${m.role !== "elder" && conversationSource(m.conversation) ? " · " + E(conversationSource(m.conversation)) : ""}</small>${E(m.text)}${assistantActions(m.actions,m.cloud_turn_id)}</div>`).join("") || '<section class="hero"><h2>有什么康复问题？</h2><p class="muted">可以询问动作做法或解释已有康复结果。</p></section>'}</section>${button("本地候选计划", "local-plan")}<form id="chat-form" class="composer"><label for="draft">发消息给康复管家</label><textarea id="draft" required maxlength="1900" placeholder="坐姿踝内翻与外翻方向观察怎么做？">${E(ui.draft)}</textarea><div class="actions"><label><input id="private" type="checkbox" ${ui.private ? "checked" : ""}>本次不记录</label><div>${button("语音输入", "voice")} <button type="button" id="voice-cancel" hidden>取消录音</button> <button type="submit" class="primary">发送</button></div></div><p id="voice-state" class="muted" role="status"></p><input id="audio-file" type="file" accept="audio/*" hidden></form>`;
  if(cloud){
    bind('assistant-workflow',()=>act(()=>openAssistantWorkflow(cloud),''));
    document.querySelectorAll('[data-assistant-doctor]').forEach(control=>control.onclick=openClinicianContact);
    bind('assistant-sync',()=>{cloud.loaded=false;void refreshAssistant(cloud);});
    $('#assistant-health-context').onchange=async event=>{
      const enabled=event.target.checked,version=cloud.preferences?.version;
      const ok=await act(async()=>{const value=await assistantRequest('assistantPreferences',{expected_version:version,health_context:enabled});if(assistantIdentity()?.key===cloud.key)cloud.preferences=value;},'管家授权设置已保存');
      if(!ok)cloud.loaded=false;if(ui.page==='assistant')assistant();
    };
    // Recovery stays beside the original question, not inside collapsed help.
    if(pending){
      const conversation=$('.conversation');
      conversation.insertAdjacentHTML?.('beforeend',pendingRows.map(row=>`<div class="bubble mine"><small>我 · 等待回复</small>${E(row.text)}<div class="actions"><button type="button" data-assistant-retry="${E(row.operation_id||'')}">重试这条</button></div></div>`).join(''));
      document.querySelectorAll('[data-assistant-retry]').forEach(control=>control.onclick=()=>act(async()=>{
        const result=await assistantRequest('assistantTurn',{retry_operation_id:control.dataset.assistantRetry||null});
        if(assistantIdentity()?.key!==cloud.key)throw Error('账号已变化');
        cloud.items=assistantTurns([...cloud.items,{...result.turn,source:result.source}]);cloud.loaded=false;await load();
      },'管家已回复'));
      scheduleAssistantRecovery(cloud);
    }
    document.querySelectorAll('[data-assistant-candidate]').forEach(control=>control.onclick=()=>{
      const kind=control.dataset.assistantCandidate;
      modal('提交候选给医生核对？','<p>程序会重新核对本人已同步评估、目标和授权；候选不会自动启用或增加训练量。</p><button class="primary" id="assistant-candidate-confirm">确认提交</button>');
      bind('assistant-candidate-confirm',async()=>{
        let status;
        const ok=await act(async()=>{
          if(assistantIdentity()?.key!==cloud.key)throw Error('账号已变化');
          const key=control.dataset.assistantTurn+':'+kind,operation_id=cloud.candidates[key]??=crypto.randomUUID(),result=await assistantRequest('candidate',{operation_id,kind});
          if(assistantIdentity()?.key!==cloud.key)throw Error('账号已变化');
          status=result.state==='PENDING_REVIEW'?'候选已提交，等待医生核对。':'候选状态：'+(result.state||'待核对');
        },'');
        if(ok){$('#dialog').close();say(status);}
      });
    });
    if(!cloud.loaded&&!cloud.loading)void refreshAssistant(cloud);
  }
  bind('local-plan',()=>{
    modal('本地候选计划','<p>本地规则筛选，不调用付费模型。先支持肩、髋、膝、踝的起始模板；核对条件及当次试做后再采用。</p><form id="local-plan-form"><label>目标<input id="plan-goal" required maxlength="200"></label><label>身体部位<input id="plan-region" required maxlength="40"></label><label>器材（逗号分隔）<input id="plan-equipment" maxlength="200" placeholder="稳固椅、硬床、滑布、垫、稳定桌面"></label><label>限制（逗号分隔，无则留空）<input id="plan-restrictions" maxlength="200"></label><label>当前任务等级<select id="plan-level"><option value="0">L0</option><option value="1">L1</option><option value="2">L2</option><option value="3">L3</option></select></label><label><input id="plan-confirmed" type="checkbox" required>已核对适用条件、器材与限制</label><button type="submit">生成候选计划</button></form><p id="plan-result" role="status" style="white-space:pre-wrap"></p>');
    const owner=snapshot().ownerId,source=ui.source;
    $('#local-plan-form').onsubmit=async e=>{e.preventDefault();if(owner!==snapshot().ownerId||source!==ui.source)return;
      const split=id=>$(id).value.replaceAll('，',',').split(',').map(v=>v.trim()).filter(Boolean);
      try{const operation=window.PhoneLocal?'/product/rehab.plan.draft':'/unified/rehab.plan.draft?source='+encodeURIComponent(source);
        const result=await api(operation,{goal:$('#plan-goal').value.trim(),region:$('#plan-region').value.trim(),equipment:split('#plan-equipment'),restrictions:split('#plan-restrictions'),level:Number($('#plan-level').value),screeningConfirmed:$('#plan-confirmed').checked});
        if(owner===snapshot().ownerId&&source===ui.source&&$('#plan-result'))$('#plan-result').textContent=result.note+'\n'+(result.items||[]).map(item=>`${item.id}｜${item.name}\n候选版本：${item.variant}\n器材原文：${item.equipment}\n开始条件：${item.startConditions}\n试做与候选剂量原文：${item.sourceDose}\n停止或调整条件：${item.stopConditions}`).join('\n');
      }catch(error){if($('#plan-result'))$('#plan-result').textContent=error.message;}
    };
  });
  $("#draft").oninput = (e) => (ui.draft = e.target.value);
  $("#private").onchange = (e) => (ui.private = e.target.checked);
  $("#chat-form").onsubmit = async (e) => {
    e.preventDefault();
    if (voiceStarting || recorder?.state === "recording") {
      say("请先结束或取消录音，再发送消息。");
      return;
    }
    const text = ui.draft,
      priv = ui.private;
    let destination, turn;
    const source=ui.source,owner=snapshot().ownerId;
    const ok = await act(
      async () => {
        const account=assistantIdentity();
        if(window.OfflineAndroid?.accountIdentity&&!account&&!assistantPrivate(text,priv))throw Error('请先登录本人账号，再向康复管家提问。');
        if(account&&!assistantPrivate(text,priv)){
          const result=await assistantRequest('assistantTurn',{text});
          if(assistantIdentity()?.key!==account.key)throw Error('账号已变化');
          cloud.items=assistantTurns([...cloud.items,{...result.turn,source:result.source}]);
          turn={...result.turn,conversation:{provider:result.source,status:'replied'}};cloud.loaded=false;
        }else{const result=await post("chat", { text, private: priv });turn=result.turn;destination=turn?.agent?.navigation;}
      },
      "",
    );
    if (ok) {
      if(source!==ui.source||owner!==snapshot().ownerId)return;
      if (ui.draft === text) ui.draft = "";
      await load();
      if(source!==ui.source||owner!==snapshot().ownerId)return;
      say(conversationSource(turn?.conversation) || "管家已回复");
      if(destination==='history')destination='records';
      if(destination&&(names[destination]||['assistant','records','settings','notifications','fitness'].includes(destination))){
        if(location.hash.slice(1)===destination)route();
        else location.hash=destination;
      }
    }else if(cloud&&ui.page==='assistant'&&assistantIdentity()?.key===cloud.key){
      assistant();
    }
  };
  bind("voice-cancel", () => {
    recordCancelled = true;
    if (recorder?.state === "recording") recorder.stop();
  });
  bind("voice", async (e) => {
    e.preventDefault();
    if (voiceStarting) return;
    if (recorder?.state === "recording") {
      recorder.stop();
      return;
    }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      say(
        "当前 HTTP 页面不能直接使用麦克风，可选择短录音，或使用手机键盘语音输入。",
      );
      $("#audio-file").click();
      return;
    }
    try {
      voiceStarting = true;
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (ui.page !== "assistant" && !(ui.page === "family" && window.FamilyV10?.isAI())) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      recordCancelled = false;
      $("#voice-cancel").hidden = false;
      const chunks = [];
      recorder = new MediaRecorder(stream);
      const recording = recorder,
        recordingStream = stream;
      recorder.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      recorder.onstop = () => {
        clearTimeout(recordTimer);
        recordingStream.getTracks().forEach((t) => t.stop());
        if ($("#voice")) $("#voice").textContent = "语音输入";
        if ($("#voice-cancel")) $("#voice-cancel").hidden = true;
        if ($("#voice-state"))
          $("#voice-state").textContent = recordCancelled
            ? "已取消，原草稿保留。"
            : "";
        if (!recordCancelled)
          transcribe(new Blob(chunks, { type: recording.mimeType }));
      };
      recorder.start();
      $("#voice").textContent = "结束录音";
      $("#voice-state").textContent = "正在录音，再点一次结束（最长 30 秒）";
      recordTimer = setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, 30000);
    } catch (e) {
      stream?.getTracks().forEach((t) => t.stop());
      say("无法录音，请检查麦克风权限或使用键盘语音输入。");
    } finally {
      voiceStarting = false;
    }
  });
  $("#audio-file").onchange = (e) => {
    const file = e.target.files[0];
    if (file) transcribe(file);
  };
  window.ProductMotion?.decorate(ui.page);
}
async function transcribe(file) {
  if (file.size > 8 * 1024 * 1024) {
    say("录音不能超过 8 MB。");
    return;
  }
  const before = ui.draft;
  if ($("#voice-state")) $("#voice-state").textContent = "正在识别…";
  try {
    const r = await api(
      "/product-voice",
      {},
      { raw: file, headers: { "Content-Type": file.type }, timeout: 110000 },
    );
    ui.draft =
      ui.draft === before
        ? [before, r.text].filter(Boolean).join("\n")
        : ui.draft + "\n" + r.text;
    if (ui.page === "assistant") assistant();
    else if (ui.page === "medication" && window.MedicationV121?.isAI()) window.MedicationV121.render();
    else if (ui.page === "family" && window.FamilyV10?.isAI()) window.FamilyV10.render();
    say("已填入草稿，核对后发送。");
  } catch (e) {
    say(e.message);
    if ($("#voice-state"))
      $("#voice-state").textContent = "识别失败，原草稿已保留。";
  }
}
$("#profile").onclick = () => {
  if (voiceStarting || recorder?.state === "recording") {
    say("请先结束或取消录音。");
    return;
  }
  editProfile();
};
$("#refresh").onclick = () => {
  if (ui.busy || voiceStarting || recorder?.state === "recording") {
    say("请先完成当前操作。");
    return;
  }
  load();
};
// Paired pages use the desktop's bound account and durable queue.
// PhoneAccount owns the independent public browser / APK patient conversation.
function mountPairedClinicianContact() {
  if (window.PhoneAccount || typeof document.createElement !== 'function' || $("#paired-contact-clinician")) return;
  const entry=document.createElement('button');entry.id='paired-contact-clinician';entry.className='quiet';entry.textContent='联系康复医师';entry.onclick=pairedClinicianContact;
  $("#profile").before(entry);
}
async function pairedClinicianContact() {
  if (ui.busy || voiceStarting || recorder?.state==='recording') {say('请先完成当前操作。');return;}
  const request=(action,body={})=>api('/unified/workbench.'+action,body,{timeout:30000});
  let identity;
  try{identity=await request('identity');}catch(e){say(e.message);return;}
  if(!identity.connected){modal('联系康复医师','<p>请先在电脑“联系康复医师”确认本人身份和医师授权。</p>');return;}
  const dialog=modal('康复医师',`<p id="paired-status" role="status"></p><div id="paired-detail"></div><form id="paired-send-form" class="paired-composer"><button id="paired-report" type="button" class="quiet">报告</button><label class="paired-input-label" for="paired-message">给康复医师留言</label><textarea id="paired-message" name="text" rows="2" maxlength="1000" placeholder="输入消息…" required></textarea><button type="submit" class="primary">发送</button></form>`);
  dialog.classList.add('paired-contact');
  const heading=dialog.querySelector('.heading');
  heading.insertAdjacentHTML('afterbegin','<button id="paired-messages" class="quiet" aria-label="返回医师对话" hidden>返回</button>');
  heading.querySelector('#close-dialog').insertAdjacentHTML('beforebegin','<details class="paired-more"><summary aria-label="更多医师服务">更多</summary><div><button id="paired-plans">医生方案</button><button id="paired-settings">资料与授权</button><button id="paired-refresh">刷新消息</button></div></details>');
  const own=modalGeneration,active=()=>dialog.open&&own===modalGeneration;
  let requestPending=false,view='messages',pendingSend=null;
  function showView(next){
    view=next;$("#dialog-title").textContent={messages:'康复医师',plans:'医生方案',settings:'资料与授权'}[view];
    $("#paired-send-form").hidden=view!=='messages';$("#paired-messages").hidden=view==='messages';dialog.querySelector('.paired-more').open=false;
  }
  async function perform(fn,success=''){
    if(requestPending||!active())return;requestPending=true;
    dialog.querySelectorAll('button:not(#close-dialog)').forEach(b=>b.disabled=true);
    try{await fn();if(active())$("#paired-status").textContent=success;}
    catch(e){if(active())$("#paired-status").textContent=e.message;}
    finally{requestPending=false;if(active()){dialog.querySelectorAll('button:not(#close-dialog)').forEach(b=>b.disabled=false);if($("#paired-sync"))$("#paired-sync").disabled=!identity.upload_enabled;}}
  }
  async function messages(before=null){
    const value=await request('messages',before?{before}:{});if(!active())return;
    showView('messages');
    const area=$("#paired-detail");area.innerHTML=`${value.has_older?'<button id="paired-older">更早的对话</button>':''}${value.items.map(item=>`<article class="paired-message ${item.author_role==='DOCTOR_ADMIN'?'doctor':'mine'}"><strong>${item.author_role==='DOCTOR_ADMIN'?'康复医师':'我'}</strong><p>${E(item.text)}</p><small>${E(stamp(item.created_at*1000))}</small></article>`).join('')||'<p class="paired-empty">暂无消息</p>'}`;
    if(value.items.length&&value.next_cursor>value.read_cursor)await request('read',{cursor:value.next_cursor});
    bind('paired-older',()=>perform(()=>messages(value.previous_cursor)));
    if(!before)area.scrollTop=area.scrollHeight;
  }
  async function retryMessages(){
    const prior=pendingSend;
    await request('retry');
    if(pendingSend===prior){
      pendingSend=null;
      if(prior&&$("#paired-message").value.trim()===prior.text)$("#paired-message").value='';
    }
    await messages();
  }
  $("#paired-send-form").onsubmit=event=>{
      event.preventDefault();const text=event.currentTarget.elements.text.value.trim();if(!text)return;
      if(pendingSend&&pendingSend.text!==text){$("#paired-status").textContent='上一条消息仍待核对，请先重试原消息，再发送新内容。';return;}
      pendingSend??={operation_id:crypto.randomUUID(),text};
      perform(async()=>{await request('send',pendingSend);pendingSend=null;if($("#paired-message").value.trim()===text)$("#paired-message").value='';await messages();});
  };
  async function showProfessionalPlans(){
    const value=await request('plans');if(!active())return;
    showView('plans');
    $("#paired-detail").innerHTML=value.items.map(plan=>`<article class="journal"><h3>${E(plan.title)}${plan.id===value.current_plan_id?' · 当前采用':''}</h3><p>${E(plan.summary)}</p><ol>${plan.items.map(item=>`<li><strong>${E(item.name)} · ${item.side==='left'?'左侧':'右侧'}</strong><p>${E(item.settings.target_reps)} 次 × ${E(item.settings.target_sets)} 组；角度 ${item.settings.target_angle_deg===null?'未指定':E(item.settings.target_angle_deg)+'°'}</p><p>${E(item.caution)}</p></li>`).join('')}</ol><button data-paired-adopt="${E(plan.id)}">核对并采用</button></article>`).join('')||'<p>暂无医生方案</p>';
    dialog.querySelectorAll('[data-paired-adopt]').forEach(button=>button.onclick=()=>{
      const plan=value.items.find(item=>item.id===button.dataset.pairedAdopt);
      if(!confirm('核对并采用“'+plan.title+'”？程序会检查本人电脑档案的已保存评估；条件不足时保留现有计划。'))return;
      perform(async()=>{await request('adopt',{plan_id:plan.id,expected_version:plan.version,expected_current_revision:value.current_revision});await showProfessionalPlans();},'方案已核对并采用。请回康复页查看当前计划。');
    });
  }
  function settings(){
    showView('settings');$("#paired-detail").innerHTML=`<p>自动同步：${identity.upload_enabled?'已开启':'未开启'}</p><p>授权设置请在电脑“联系康复医师 → 资料与授权”调整。</p><div class="actions"><button id="paired-sync" ${identity.upload_enabled?'':'disabled'}>同步已保存资料</button><button id="paired-retry" class="quiet">重试待发送消息</button></div>`;
    bind('paired-sync',()=>perform(()=>request('sync'),'已同步。'));
    bind('paired-retry',()=>perform(retryMessages));
  }
  bind('paired-messages',()=>perform(()=>messages()));
  bind('paired-refresh',()=>perform(()=>messages()));
  bind('paired-settings',settings);
  bind('paired-plans',()=>perform(showProfessionalPlans));
  bind('paired-report',()=>{if(active())$("#paired-status").textContent='请在电脑聊天窗口点击“报告”选择原件。';});
  await perform(()=>messages());
  const refresh=setInterval(()=>{if(active()&&view==='messages'&&!requestPending&&document.visibilityState!=='hidden')perform(retryMessages);},15000);
  dialog.addEventListener('close',()=>{clearInterval(refresh);dialog.classList.remove('paired-contact');},{once:true});
}
mountPairedClinicianContact();

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && ui.page === "family" && window.FamilyV10 && window.FamilyV10.reportCode(location.hash) !== null) { window.FamilyV10.refreshGuest(); return; }
  if (
    !document.hidden &&
    ui.snapshot &&
    !ui.busy &&
    !$("#dialog").open &&
    !voiceStarting &&
    recorder?.state !== "recording"
  )
    load();
});
window.addEventListener("hashchange", route);
window.addEventListener("beforeunload", (e) => {
  if (ui.busy || voiceStarting || recorder?.state === "recording") {
    e.preventDefault();
    e.returnValue = "";
  }
});
route();
