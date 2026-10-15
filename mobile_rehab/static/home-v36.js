/* Read-only home presentation over the existing authenticated unified snapshot. */
(function (root) {
  "use strict";
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const localDay = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
  function dateOf(day) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day || "")) return null;
    const [y,m,d] = day.split("-").map(Number), date = new Date(y,m-1,d,12);
    return localDay(date) === day ? date : null;
  }
  function week(day) {
    const date = dateOf(day);
    if (!date) return [];
    date.setDate(date.getDate()-(date.getDay()+6)%7);
    return Array.from({length:7},(_,i) => {const d = new Date(date);d.setDate(d.getDate()+i);return localDay(d);});
  }
  function records(snapshot, source, tool) {
    const read = snapshot.rehabilitation_ui?.[tool], scope = read?.scope;
    if (scope && (scope.participant_id !== snapshot.profile?.ownerId || scope.source_kind !== source || scope.usage_context !== "SELF_USE")) return [];
    return read?.records || [];
  }
  function savedTraining(snapshot, source) {
    return records(snapshot,source,"rehab.get_training_history").filter(r => r.id && r.end_utc && Number.isFinite(new Date(r.end_utc).getTime()) && ["FINISHED","COMPLETED","INTERRUPTED"].includes(r.status));
  }
  function model(snapshot, source, day, today, connection = "ready") {
    const plans = records(snapshot,source,"rehab.get_training_plan"), plan = plans[0];
    const next = plan?.items?.find(i => i.key === plan.progress?.next_key);
    const schedules = (snapshot.dailyProduct?.schedules || []).filter(s => s.date === day).slice().sort((a,b)=>a.time.localeCompare(b.time));
    const mainSchedule = schedules.find(s => plan && s.kind === "training" && s.planId === plan.id && s.revision === plan.revision) || schedules.find(s=>s.kind === "assessment");
    const history = savedTraining(snapshot,source), dates = new Set(history.map(r=>localDay(new Date(r.end_utc))));
    const days = week(day), profile = snapshot.profile?.profile || {};
    let task = {label:"首次评估",title:"活动度评估",meta:source === "REPLAY_FILE" ? "手机录像评估" : "需在电脑端进行",button:source === "REPLAY_FILE" ? "开始评估" : "前往康复",action:source === "REPLAY_FILE" ? "assess" : "rehab",notice:"",exercise:null};
    if (plan) {
      const index = plan.items.findIndex(i=>i.key===next?.key), settings = next?.settings || {};
      task = {label:next?"下一项 · 训练":"本轮训练",title:next?.exercise_label || "本轮已完成",meta:next ? [mainSchedule?.time || "时间未安排",next.side === "left" ? "本人左侧" : next.side === "right" ? "本人右侧" : "侧别未记录",`${settings.target_reps ?? "未设置"}次×${settings.target_sets ?? "未设置"}组`].join(" · ") : "查看已保存的训练记录",button:next?"开始训练":"查看结果",action:next?"train":"history",notice:"",exercise:next?.exercise_id,index:index<0?null:index+1,total:plan.items.length};
      if (plan.progress?.blocked) task = {...task,label:"训练受阻",title:"查看训练状态",button:"查看训练结果",action:source === "REPLAY_FILE" ? "history" : "plan",notice:plan.progress.blocked};
      else if (next && plan.next_available !== true) task = {...task,label:"条件待核验",button:"查看计划",action:"plan",notice:plan.availability_reason || "请先核对本次训练条件。"};
      if (source === "LIVE_CAMERA") task = {...task,label:"电脑实时 · 查看",button:"查看电脑计划",action:"plan",notice:plan.progress?.blocked || plan.availability_reason && !plan.next_available && plan.availability_reason || "在电脑端开始；手机可查看计划、安排日期。"};
    }
    if (mainSchedule?.kind === "assessment") task = {...task,label:"评估安排",title:mainSchedule.name,meta:mainSchedule.time,button:source === "REPLAY_FILE" ? "准备评估" : "查看评估安排",action:source === "REPLAY_FILE" ? "assess" : "rehab",notice:"",exercise:null,index:null};
    if (day !== today) task = {...task,label:"日程浏览",button:"查看当日安排",action:"rehab",notice:"",title:mainSchedule?.name || "查看当日安排",meta:mainSchedule?.time || day,exercise:null,index:null};
    if (connection !== "ready") task = {label:connection === "loading" ? "正在核验" : "连接中断",title:connection === "loading" ? "正在读取任务" : "暂时无法读取",meta:"确认电脑开启、同一 Wi-Fi",button:connection === "loading" ? "正在读取…" : "重新连接",action:"retry",notice:"",disabled:connection === "loading",exercise:null};
    return {profile,plan,next,task,source,day,days,trained:days.filter(d=>dates.has(d)),mainSchedule,schedules,history,connection};
  }
  function hero(m) {
    const t = m.task;
    return `<section class="home-task" aria-label="当前主要康复任务"><svg class="home-streaks" viewBox="0 0 350 206" preserveAspectRatio="none" aria-hidden="true"><polygon points="185,150 196,128 350,5 350,21 205,139 190,153" class="sport-band"/><path d="M173 206 350 87" class="sport-line"/></svg><img class="home-athlete" src="/static/assets/home-v36/athlete-cutout.png" alt="" aria-hidden="true"><svg class="home-streak-front" viewBox="0 0 350 206" preserveAspectRatio="none" aria-hidden="true"><polygon points="240,185 254,169 350,99 350,103 263,169" class="sport-cut"/></svg><div class="home-task-copy"><p class="home-task-label">${escape(t.label)}</p><h1 class="${t.title.length>4?"home-long-title":""}" title="${escape(t.title)}">${escape(t.title)}</h1><p class="home-task-meta">${escape(t.meta)}</p><button id="home-primary" ${t.disabled?"disabled":""}>${escape(t.button)}<span aria-hidden="true">→</span></button></div>${t.index?`<span class="home-task-index">${String(t.index).padStart(2,"0")} / ${String(t.total).padStart(2,"0")}</span>`:""}</section>${t.notice?`<p class="home-task-notice" role="status">${escape(t.notice)}</p>`:""}`;
  }
  function arrangements(m, doses) {
    return [...m.schedules.filter(s=>s.id !== m.mainSchedule?.id).map(s=>({id:s.id,time:s.time,title:s.name,status:s.kind === "assessment"?"待评估":"查看计划",target:"rehab"})),...doses.map((d,i)=>({id:String(i),time:d.time,title:d.med.name,status:{taken:"已服用",skipped:"已跳过",unrecorded:"待记录"}[d.status] || "未记录",target:"medication"}))].sort((a,b)=>a.time.localeCompare(b.time));
  }
  function markup(m, doses, today) {
    const date = dateOf(m.day), labels = ["一","二","三","四","五","六","日"], items = arrangements(m,doses);
    return `<div class="home-v36"><div class="home-top"><button id="home-search" aria-label="搜索动作、计划、记录"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></svg><span>搜索动作、计划、记录</span></button><a class="home-ai" href="#assistant" aria-label="AI 康复管家">AI<i aria-hidden="true"></i></a></div><div class="home-calendar-caption"><span>${date?date.getMonth()+1:""}月</span><span>${date?.getFullYear() || ""}</span></div><div class="home-week" aria-label="本地自然周日期">${m.days.map((day,i)=>`<button data-home-day="${day}" ${day===m.day?'aria-current="date"':''} aria-label="${day} 星期${labels[i]}${m.trained.includes(day)?' 有训练记录':''}"><span>${labels[i]}</span><time datetime="${day}">${dateOf(day).getDate()}</time><i aria-hidden="true" class="${m.trained.includes(day)?"has-record":""}"></i></button>`).join("")}</div><section class="home-weekly" aria-label="本周已保存训练记录"><div class="home-weekly-top"><h2>本周训练</h2><p>${m.connection === "ready"?`<b>${m.trained.length}</b> 天有记录`:"暂未读取"}</p></div><div class="home-bars">${m.days.map((day,i)=>`<div class="home-mark" aria-label="星期${labels[i]} ${m.connection !== 'ready'?'尚未读取':m.trained.includes(day)?'有已保存训练记录':'暂无记录'}"><span>${labels[i]}</span><i class="${m.trained.includes(day)?'trained ':''}${day===m.day?'selected':''}" aria-hidden="true"></i></div>`).join("")}</div></section><div class="home-section-heading"><h2>${m.day===today?"今日":"当日"}安排</h2><span>${m.connection === "ready"?(m.schedules.length+doses.length)+" 项安排":"—"}</span></div>${hero(m)}<section class="home-shortcuts" aria-label="常用功能"><button id="home-plan"><strong>我的计划</strong><span aria-hidden="true">→</span><i class="home-mini-calendar" aria-hidden="true">${"<i></i>".repeat(6)}</i></button><a href="#records"><strong>历史报告</strong><span aria-hidden="true">→</span><i class="home-mini-chart" aria-hidden="true">${"<i></i>".repeat(4)}</i></a></section><section class="home-other"><div class="home-other-heading"><h2>${m.day===today?"今日":"当日"}其他安排</h2><span>${m.connection === "ready"?items.length+" 项":"—"}</span></div>${items.map(i=>`<button class="home-other-row" data-home-target="${i.target}" data-home-schedule="${escape(i.id)}" aria-label="${escape(i.time+' '+i.title+' '+i.status)}"><time>${escape(i.time)}</time><strong>${escape(i.title)}</strong><span>${escape(i.status)}</span><b aria-hidden="true">›</b></button>`).join("")||`<p class="home-empty">${m.connection === "ready"?"当天暂无其他安排":"安排暂时无法读取"}</p>`}</section><div class="home-context"><button id="home-profile" ${m.connection!=="ready"?"disabled":""}>${escape(m.profile.name || "我的档案")}</button><button id="home-context">${m.source === "REPLAY_FILE"?"手机录像":"电脑实时"} · ${escape(m.day.slice(5))}</button><button id="home-refresh">刷新</button></div></div>`;
  }
  const api = {escape,localDay,dateOf,week,records,savedTraining,model,hero,arrangements,markup};
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AnkangHomeV36 = api;
})(typeof window === "object" ? window : this);
