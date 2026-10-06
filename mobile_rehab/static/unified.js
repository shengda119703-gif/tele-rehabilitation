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
  draft: "",
  private: false,
  generation: 0,
  busy: false,
};
const names = {
  home: "首页",
  rehab: "康复",
  health: "健康",
  medication: "用药",
  family: "家庭",
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
      throw Error(
        typeof value.detail === "string"
          ? value.detail
          : "操作未完成，请检查填写内容。",
      );
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
const post = (operation, data) => api("/product/" + operation, data);
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
  say("正在处理，请稍候…");
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
    document
      .querySelectorAll("button[type=submit],dialog button.primary")
      .forEach((b) => (b.disabled = false));
  }
}
async function load() {
  const generation = ++ui.generation;
  try {
    const result = await api("/unified?source=" + ui.source);
    if (generation !== ui.generation) return;
    ui.snapshot = result.snapshot;
    $("#nav").hidden = false;
    $("#profile").textContent = (profile().name || "我").slice(0, 1);
    render();
  } catch (e) {
    if (generation !== ui.generation) return;
    ui.snapshot = null;
    if (!$("#pair-form"))
      $("#content").innerHTML =
        `<h1>暂时无法读取</h1><p>${E(e.message)}</p>${button("重新连接", "retry", true)}`;
    bind("retry", load);
  }
}
function nav() {
  $("#nav").innerHTML = Object.entries(names)
    .map(
      ([key, title]) =>
        `<a href="#${key}" ${ui.page === key || (ui.page === "assistant" && key === "home") ? 'aria-current="page"' : ""}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[key]}"/></svg>${title}</a>`,
    )
    .join("");
}
function route() {
  if (voiceStarting || recorder?.state === "recording") {
    location.hash = "#assistant";
    say("请先结束或取消录音。");
    return;
  }
  const key = location.hash.slice(1) || "home";
  ui.page = Object.hasOwn(names, key) || key === "assistant" ? key : "home";
  ui.day = today();
  nav();
  if (ui.snapshot) render();
  else load();
  window.scrollTo(0, 0);
}
function pair() {
  ui.generation++;
  ui.snapshot = null;
  ui.draft = "";
  ui.private = false;
  $("#nav").hidden = true;
  $("#content").innerHTML =
    `<section class="pair"><p class="eyebrow">连接我的电脑</p><h1>你的康复，<br>在手机上继续。</h1><p class="muted">先在电脑的“我的档案”中打开“连接我的手机”。这里使用同一份档案、安排和记录。</p><form id="pair-form"><label>电脑显示的连接码<input name="code" autocomplete="off" autocapitalize="none" required maxlength="32"></label><button type="submit" class="primary">连接本人档案</button></form><p class="muted">手机与电脑需连接同一可信 Wi-Fi，电脑保持开启。</p></section>`;
  $("#pair-form").onsubmit = async (e) => {
    e.preventDefault();
    const code = new FormData(e.target).get("code").trim();
    if (await act(() => api("/pair", { code }), "已连接本人档案")) await load();
  };
}
function render() {
  nav();
  ({ home, rehab, health, medication, family, assistant })[ui.page]();
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
function home() {
  const items = [
    ...schedules(today()).map((s) => ({
      time: s.time,
      title: s.name,
      to: "rehab",
    })),
    ...doses(today()).map((d) => ({
      time: d.time,
      title:
        d.med.name +
        " · " +
        { taken: "已服用", skipped: "已跳过", unrecorded: "待记录" }[d.status],
      to: "medication",
    })),
  ].sort((a, b) => a.time.localeCompare(b.time));
  $("#content").innerHTML =
    `<section class="hero"><p class="eyebrow">${E(new Date().toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "long" }))}</p><h1>${E(profile().name)}，<br>今天感觉怎么样？</h1><p class="muted">说说身体感受，整理今天的记录。<br>康复管家会陪你一步一步来。</p>${link("和康复管家聊聊", "#assistant", true)}</section><div class="heading"><h2>今天的安排</h2><a href="#rehab">查看康复安排</a></div>${
      items
        .slice(0, 4)
        .map(
          (i) =>
            `<div class="row"><time>${E(i.time)}</time><div><strong>${E(i.title)}</strong></div><a href="#${i.to}" aria-label="查看${E(i.title)}">查看</a></div>`,
        )
        .join("") ||
      '<p class="empty">今天没有安排。可以先完成一次评估，或在康复页选择训练日期。</p>'
    }${items.length > 4 ? '<p class="muted">其余安排可在康复和用药页查看。</p>' : ""}<p class="eyebrow">已连接电脑 · 本人资料同步保存</p>`;
}
function sourcePicker() {
  return `<label class="source">康复记录来源<select id="source"><option value="LIVE_CAMERA">电脑实时评估与训练</option><option value="REPLAY_FILE">手机录像评估与训练</option></select></label>`;
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
function rehab() {
  const p = plans()[0],
    next = p?.items.find((i) => i.key === p.progress?.next_key);
  $("#content").innerHTML =
    `<div class="heading"><h1>康复</h1>${link("开始评估", "/capture?tab=assess")}</div>${sourcePicker()}<section class="hero"><p class="eyebrow">${p ? "下一项训练" : "我的训练计划"}</p><h1>${E(next?.exercise_label || (p ? "这一轮已完成" : "从一次评估开始"))}</h1><p class="muted">${next ? `${next.side === "left" ? "左侧" : "右侧"} · ${E(next.settings.target_reps ?? "未设置")} 次 × ${E(next.settings.target_sets ?? 1)} 组` : p ? "已保存的训练会留在健康记录里。" : "完成动作评估后，康复管家根据有效结果准备计划。"}</p>${p ? `<progress value="${Number(p.progress?.completed) || 0}" max="${Math.max(1, Number(p.progress?.total) || 1)}" aria-label="本轮完成进度"></progress>` : ""}${p?.availability_reason ? `<p class="notice">${E(p.availability_reason)}</p>` : ""}<div class="actions">${ui.source === "REPLAY_FILE" ? link(p && next ? "开始下一项" : "康复管家制定计划", "/capture?tab=plan", true) : p ? button("查看这份计划", "plan-detail", true) : link("用手机完成评估", "/capture?tab=assess", true)}${p ? button("安排日期", "schedule") : ""}</div>${ui.source === "LIVE_CAMERA" && p ? '<p class="muted">这份计划使用电脑实时测量条件。请在电脑“康复”页开始；手机可查看和安排日期。</p>' : ""}</section><div class="heading"><h2>日期安排</h2><input class="date" id="day" type="date" aria-label="查看康复日期" value="${ui.day}"></div>${
      schedules()
        .map(
          (s) =>
            `<div class="row"><time>${E(s.time)}</time><div><strong>${E(s.name)}</strong><p><small>${s.kind === "assessment" ? "评估安排" : "训练安排"} · 完成情况见保存记录</small></p></div><button data-cancel="${E(s.id)}" aria-label="取消${E(s.name)}的安排">取消</button></div>`,
        )
        .join("") ||
      '<p class="empty">这一天没有安排。已有计划可以选择日期；未完成评估可先开始评估。</p>'
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
function modal(title, body) {
  const d = $("#dialog");
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
  const events = (snapshot().state?.events || [])
    .slice()
    .sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));
  const records = Object.entries(snapshot().rehabilitation_ui || {})
    .filter(([k]) => k !== "rehab.get_training_plan")
    .flatMap(([, v]) => v.records || []);
  $("#content").innerHTML =
    `<div class="heading"><h1>健康档案</h1>${button("编辑资料", "edit-profile")}</div><p class="muted">${E(profile().name)}${profile().age ? " · " + E(profile().age) + " 岁" : ""}<br>${E((profile().conditions || []).join("、") || "尚未填写已知健康情况")}</p><div class="actions">${button("拍照 / 上传资料", "upload", true)}${link("记录身体感受", "#assistant")}</div><div class="heading"><h2>资料与图片</h2></div>${(snapshot().attachments || []).map((a) => `<div class="row"><div><strong>${E(a.name)}</strong><p><small>${E(a.category)} · ${stamp(a.createdAt || a.savedAt)}</small></p></div><button data-archive="${E(a.id)}">查看</button></div>`).join("") || '<p class="empty">把病历、报告或仪器照片放在这里。识别文字后，先核对，再选择是否记录。</p>'}<div class="heading"><h2>最近记录</h2></div><div class="timeline">${
      events
        .slice(0, 20)
        .map(
          (e) =>
            `<article><small>${stamp(e.timestamp)}</small><p>${E(e.observation?.text || [e.measurement?.metric || e.labResult?.name, e.measurement?.value ?? e.labResult?.value, e.measurement?.unit || e.labResult?.unit].filter((x) => x !== undefined).join(" ") || "健康记录")}</p></article>`,
        )
        .join("") ||
      '<p class="empty">还没有身体记录，可以和康复管家说说今天的情况。</p>'
    }</div><details><summary>康复记录与更多资料</summary>${sourcePicker()}${
      records
        .slice(0, 20)
        .map(
          (r) =>
            `<div class="row"><div><strong>${E(r.exercise_label || r.exercise_id || "动作记录")}</strong><p><small>${stamp(r.end_utc || r.timestamp)} · ${E(r.side === "left" ? "左侧" : r.side === "right" ? "右侧" : "")}</small></p></div></div>`,
        )
        .join("") || '<p class="muted">当前来源尚无保存的康复记录。</p>'
    }<div class="actions">${link("查看手机分析报告", "/capture?tab=history")}${link("资料回收站与备份", "/capture?tab=archive")}</div></details>`;
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
function editProfile() {
  if (!ui.snapshot) return;
  const p = profile();
  modal(
    "我的档案",
    `<form id="profile-form"><label>称呼<input name="name" maxlength="40" value="${E(p.name)}" required></label><label>年龄<input type="number" name="age" min="0" max="130" value="${Number(p.age) || 0}" required></label><label>已知健康情况，用逗号分隔<textarea name="conditions" maxlength="1000">${E((p.conditions || []).join("，"))}</textarea></label><button type="submit" class="primary">保存资料</button></form>`,
  );
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
      ? "已选择照片，填写名称后保存。"
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
    `<p class="muted">${E(a.category)}</p><div class="actions">${link("下载原件", "/api/product-archive/" + encodeURIComponent(a.id))}${/image\/(jpeg|png)/.test(a.mediaType) ? button("识别图片文字", "ocr", true) : ""}${button("移入回收站", "trash")}</div><div id="ocr-result"></div>`,
  );
  bind("trash", () =>
    confirmAction("移入回收站？", "资料可以在回收站恢复。", () =>
      api("/product-archive/" + a.id + "/trash", { confirm: true }),
    ),
  );
  bind("ocr", async () => {
    let result;
    if (
      await act(async () => {
        result = await api("/product-ocr/" + a.id, {});
      }, "识别完成，请核对文字")
    ) {
      $("#ocr-result").innerHTML =
        `<label>识别文字，可修改<textarea id="ocr-text" rows="7">${E(result.text)}</textarea></label><p class="muted">核对本人、日期和数值后，再交给管家整理。识别文字不会自动写入身体记录。</p>${button("带入管家对话", "ocr-chat", true)}`;
      bind("ocr-chat", () => {
        ui.draft = $("#ocr-text").value.slice(0, 1800);
        $("#dialog").close();
        location.hash = "#assistant";
      });
    }
  });
}
function medication() {
  const rows = doses();
  $("#content").innerHTML =
    `<div class="heading"><h1>用药</h1><input class="date" id="day" type="date" value="${ui.day}" aria-label="查看用药日期"></div><p class="muted">按已有医嘱安排，逐次记录。未记录不会自动算作漏服。</p>${rows.map((r, i) => `<div class="row"><time>${E(r.time)}</time><div><strong>${E(r.med.name)}</strong><p>${E(r.med.dose || "剂量未填写")}</p><small class="${r.status === "taken" ? "status" : ""}">${{ taken: "已服用", skipped: "已跳过", unrecorded: "未记录" }[r.status]}</small></div><button data-dose="${i}" ${r.day > today() ? "disabled" : ""}>${r.status === "unrecorded" ? "记录" : "更正"}</button></div>`).join("") || '<p class="empty">这一天没有用药安排。添加正在使用的药物，再设置服用时间。</p>'}<div class="heading"><h2>我的药物</h2>${button("添加药物", "add-med")}</div>${(profile().medicationRecords || []).map((m) => `<div class="row"><div><strong>${E(m.name)}</strong><p><small>${E(m.dose)} · ${m.status === "active" ? "在用" : "已停用"}</small></p></div><button data-med="${E(m.id)}">管理</button></div>`).join("")}<details><summary>记录更正历史</summary>${
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
  $("#content").innerHTML =
    `<h1>家人的近况</h1><p class="muted">只查看家人主动共享的信息。双方分别选择共享范围，不能修改对方的档案。</p>${
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
      '<section class="hero"><h2>让关心有一个入口</h2><p class="muted">双方先在电脑建立各自档案，再分别连接自己的手机。用家庭邀请码关联后，选择愿意共享的内容。</p></section>'
    }<div class="actions">${button("关联家人", "bind", true)}${button("生成家庭邀请码", "invite")}</div><p class="notice">家庭邀请码只建立关系，默认不共享任何记录。手机连接码则允许操作本人档案，两者请勿混用。</p>`;
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
function assistant() {
  const chat = snapshot().state?.chat || [];
  $("#content").innerHTML =
    `<div class="heading"><h1>康复管家</h1><a href="#home">返回首页</a></div><p class="muted">表达 → 理解 → 核对 → 记录。需要更正时，可以直接说“撤回上一条记录”。</p><section class="conversation" aria-label="对话记录">${chat.map((m) => `<div class="bubble ${m.role === "elder" ? "mine" : ""}"><small>${m.role === "elder" ? "我" : "康复管家"}${m.time ? " · " + stamp(m.time) : ""}${m.persisted === false ? " · 本次不记录" : ""}${m.pending ? " · 待确认" : ""}</small>${E(m.text)}</div>`).join("") || '<section class="hero"><h2>说说你今天的情况</h2><p class="muted">可以说身体感受、用药情况，或询问已有康复安排。识别出的内容由你核对。</p></section>'}</section><form id="chat-form" class="composer"><label for="draft">发消息给康复管家</label><textarea id="draft" required maxlength="1900" placeholder="例如：今天左肩有点酸，想记下来">${E(ui.draft)}</textarea><div class="actions"><label><input id="private" type="checkbox" ${ui.private ? "checked" : ""}>本次不记录</label><div>${button("语音输入", "voice")} <button type="button" id="voice-cancel" hidden>取消录音</button> <button type="submit" class="primary">发送</button></div></div><p id="voice-state" class="muted" role="status"></p><input id="audio-file" type="file" accept="audio/*" hidden></form>`;
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
    const ok = await act(
      () => post("chat", { text, private: priv }),
      "管家已回复",
    );
    if (ok) {
      if (ui.draft === text) ui.draft = "";
      await load();
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
      if (ui.page !== "assistant") {
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
document.addEventListener("visibilitychange", () => {
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
