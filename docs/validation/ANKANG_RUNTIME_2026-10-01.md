# 安康独立 TypeScript Runtime 验收

日期：2026-10-01。开发分支 `codex/rehab-agent-stage1`。开始时本地/远端 HEAD 均为 `ef5a767d33fe87b5714bbf3c0125b5ed32c88575`；远端 main 为 `2ebc388d4160d647456487007670d89f02f80914`。没有 merge main，没有进入康复 B，没有接 Python/PySide6、Home Twin 或修改康复算法。

## 交付与范围

新增 [runtime/index.ts](../../ankang/route1-health-agent/src/runtime/index.ts) 导出的 `AgentRuntime`，在同进程 Node/TypeScript 中独立运行。一次 `processTurn` 完成理解、规划、应用事件与更正、检测、Context/Person Twin、任务对账、持久化和可选送达回执；不要求调用方拼领域函数。

没有删除任何上游文件、React UI、route2、iOS、硬件或测试。没有改动 `understanding.ts`、`llmUnderstanding.ts`、`agent.ts`、`pipeline/events.ts`、检测规则、Context、Person Twin 或领域 `tasks.ts`。`elderTurn.ts` 只新增可选的 session 审计输入，默认兼容旧全局读取路径，回复与规则分支不变。

架构图和 33 模块闭包见 [更新后的边界文档](../plans/ANKANG_CORE_BOUNDARY.md)。新 Runtime 的传递 import 闭包无 React、react-dom、TSX、UI hook、PeerJS、Home Twin、route2 或其他 npm 包；使用 TypeScript 内置类型和原领域模块。源码仍使用 fetch/URL 等 Web 标准契约，Node 22 提供这些能力，不要求 DOM 页面。

## 同进程 API

```ts
import { AgentRuntime, InMemoryPersistence } from './src/runtime';

const runtime = new AgentRuntime();
await runtime.openSession({
  sessionId: 'local-person-session',
  profile, // 原 ElderProfile，宿主提供，包含 familySharing 等
  now: new Date(),
  persistence: new InMemoryPersistence(), // 返回 memory-only，不声称磁盘保存
});
const result = await runtime.processTurn('local-person-session', {
  text: '我今天量了血压150/95',
  now: new Date(),
  expectedRevision: 0, // 可省略；执行到队首时校验
});
const snapshot = runtime.readSnapshot('local-person-session');
await runtime.closeSession('local-person-session');
```

| API | 契约 |
| --- | --- |
| `openSession(options)` | 独占该 registry 中的 ID；先 await port.load，读取失败直接拒绝，不能用空状态覆盖未读历史。port 有历史时优先于 initialHealth；复制 profile/种子/config 防宿主意外改写 |
| `processTurn(id, {text, now, expectedRevision?})` | 捕获输入时钟，在队首读取最新 session 状态；返回 reply/replyBlocks、understanding、appliedChanges（原 plan）、sourceMessageId、完整 snapshot、findings、Person Twin、tasks、persistence/delivery、revision |
| `readSnapshot(id)` | 深拷贝，不暴露内部可变数组；reset 已开始尚未完成时拒绝旧代快照；关闭后不可读 |
| `updateTaskStatus(id, taskId, status)` | 与 turn 同队列，复用原任务状态函数；增加 revision；任务仍 session-only |
| `resetSession(id, now)` | 立即使旧代 turn 失效，排队等待已开始 I/O，再清空会话与 port；按 profile 初始化当天任务；revision 递增 |
| `closeSession(id)` | 立即禁止后续操作、使迟到规划失效，等待已开始 I/O/队列排空，释放内存；不删除持久化历史；之后可重新 open |

`now` 是显式注入的本地 Date，入队时复制；每回合按它生成本地日期、聊天标签、receivedAt，重算回合前后 Context。排队跨午夜不会重新套用模块加载时的 TODAY，也不把 UTC 日期当本地日期。没有计时器要求：无新回合时 snapshot 保持最后计算日期。

同一 registry 阻止重复 session ID，包括正在 open 的 ID。宿主必须让 ID 对应真实独立用户，并为 port 做一致的 namespace；**不承诺不同 AgentRuntime 实例/进程对同一存储 key 的分布式锁**。

## 搬出的业务与仍在 React 的内容

| 来源 | 已抽取、共享的生产实现 | 保留在 React/浏览器中的内容 |
| --- | --- | --- |
| `useElderChat.ts` | `prepareTurn`：隐私门禁、规则/LLM 理解选择、planner 调用；`applyTurnPlan`：按原顺序更正、家庭事件、审计、共享、本人事件、广播意图、用药回调；`settlePendingReply` | UI 回显与占位、setter 适配、toast、图片选择/解析/确认、browser config、原 UI queue 与聊天时间生成 |
| `App.tsx` | `deriveHealthState`：materialize → detection → context（内部生成完整和公开 Twin） | React 状态持有、浏览器 IndexedDB 水合/save effect、设备/照片事件、授权与通知、导航/TTS/外部 tool 路由、每日用药初始化的触发 effect |
| `useCareTasks.ts` | `reconcileCareTasks / ensureMedicationTask / changeTaskStatus` | React state/effect；旧 tasks module-global 已删除；清除旧 localStorage key 的浏览器兼容行为 |

这些领域运行规则只有一份共享生产实现，reference fixture 仅用于测试。独立 Runtime 自己持有 session 和完整事务；当前 React App 复用相同函数但**未整体改为 Runtime session 的 UI adapter**。因此不宣称当前 React 的旧闭包、设备并发和持久化都已获得新 Runtime 的事务保证。后续可单独迁移 App 状态所有权，不能在本阶段顺带重做 UI。

## 状态、顺序与失败语义

- Runtime 唯一拥有其 chat、本人 HealthEvent、familyEvents、tasks、audit、一次性共享 ID 集合；调用方只能获得深拷贝。领域输入也取当前 session 的副本。
- 每 session 使用原 `createTurnQueue` 串行。不同 session 独立并行；第二轮规划读取第一轮已完成的结果，不复用入队时的旧 React closure。expectedRevision 在开始执行时校验，冲突拒绝但不破坏队列。
- 每个成功回合增加 revision；有事件/回复已在内存提交后，存储失败不回滚事实，而返回 failed 回执。任务更新、reset 也增加 revision。读取失败/open 不成功不会建立 session。
- generation 是 reset/close 的失效门禁；异步理解/planning 完成后、I/O 完成后都校验。尚未提交的旧代结果不会写回；已开始的存储/送达不能被“撤销”，reset/close 等待它结束。reset 的 clear 在旧 save 之后执行，防迟到 save 覆盖清空。
- close 不是撤销已提交事实或删除历史；重开从 port 恢复健康记录。消息序号从已存 chat 延续，事件数字种子从已存事件继续，避免相同时钟重开后冲突。session ID 提供来源命名空间。
- tasks 和 sharing audit 与上游一样仅在会话内，不写入健康持久化；重开 tasks 从 findings/profile 重建，audit 为空。原审计条数上限 100 保留。
- Runtime 以及 React hook 都显式向 planner 提供本 session audit。`sharingAudit.ts` 的 legacy 全局函数仍保留兼容上游测试/未迁移旧调用；独立 Runtime 不调用它们，不能据此把旧全局 API 当成多用户实现。
- Runtime 不接受 UI setter、DOM、toast、TTS、文件 input 或导航。应用 UI 效果仍由 React adapter 处理。

reset/close 是逻辑失效与排空，未改动原 LLM adapter 来增加 AbortSignal。非隐私的在途请求不会被物理中断；port 实现必须最终 settle，否则等待其排空也会等待。没有把超时/取消包装成已保存，也没有引入 Python A1–A3 action-token 协议。

## Persistence / delivery port

`PersistencePort.load/save/clear` 全部异步。save 只接收 `{revision, health: {events, familyEvents, chat}}`；chat 过滤 `persisted === false`，从不持久化 pending/no_record 消息、task、audit 或 LLM 配置。该 port **只允许宿主提供受信任的本地存储**，不能把含私密事实的完整快照直接接网络上传。

返回状态：未配置 `not-configured`、已配置但未保存 `not-saved`、成功水合 `loaded`、写入中 `pending`、durable 实现成功 `saved`、测试/内存实现 `memory-only`、异常 `failed`（包含 error 和 revision）。Runtime 只在实际 await 完成后报告成功；port 负责如实区分磁盘与内存。

本轮提供 `InMemoryPersistence`，不硬绑定 IndexedDB。原 React `PersistentHealthRecordStore.save(): void` 仍保持原 fire-and-forget 行为；**没有冒充其具备真实写入回执**，也未把它当作新的 port 使用。浏览器真实回执 adapter、PySide6 宿主存储都是后续工作。

`DeliveryPort` 是可选受信任宿主 adapter，只处理本轮广播/共享意图。它必须自行执行接收方授权、visibility 过滤和真实 transport；不能把本地事件广播直接等同发给家属。private/no_record 不调用理解/回复外部模型，也不调用 delivery。其他回合返回 `not-requested / not-configured / accepted / delivered / failed`，明确区别排队接收、实际送达和共享审计计划。没有提供 PeerJS、Home Twin 或通知平台实现。

## 保留的行为与明确差异

1. 本人 correction 仍仅在 `eventsToAppend.length > 0` 时应用；只更正但无新增本人事件的旧限制特意保留并测试。家庭更正仍先执行。
2. 原 private/no_record 门禁、LLM 失败回退、安全检测、公开/完整 Twin、家庭事实与本人事实隔离均调用原领域代码。
3. 对账仍保留已完成 finding 任务、删除失效未完成 finding 任务，最多取前两个 alert/urgent，使用原稳定任务 ID。当天 medication task 完成后不会复活。
4. 原 App 忽略漏服药回调的 createdAt，默认生成当天 08:00 任务，Runtime 保留该行为。
5. 独立 Runtime 使用确定性的 session 消息 ID、入队输入时钟，并在队首取最新状态；这是隔离/并发契约的明确增强，不宣称重现旧 hook 的 stale closure 缺陷。原领域文本/理解逻辑没有修改。
6. 原 React tasks/audit 从 module-global 改成 hook 实例所有，重挂 App 不再继承别的实例临时状态。这是必要的状态所有权变化。

## 测试与 parity 证据

工具链：沿用 Node **22.14.0**、npm **10.9.2**、原 `package-lock.json` 和已安装依赖；未改 package.json、lock、tsconfig 或原测试。日志保存在工作区外层 `.runtime/ankang-runtime/`，不提交测试输出或用户数据。

| 检查 | 本轮结果 |
| --- | --- |
| `npm run typecheck` | 通过 |
| `npm test` | **396/396 通过**：原 378 + 新增 18；无 skip/cancel |
| `npm run build` | 通过 |
| `npm run security:check` | 通过 |
| Runtime AST 传递依赖门禁 | 33 模块，无外部 npm import、TSX/UI/platform 依赖 |
| Runtime 独立功能测试 | 17 项通过，另 1 项依赖测试 |
| 原正式浏览器八组 | **8/8 组、71/71 检查通过**：smoke 16、SOS 4、onboarding 10、webhook 9、notification 6、cross-device 6、binding 10、crosstab 10 |
| 补充浏览器四组 | demo-filled 通过；family-management、four-tab-flow、voice-dialog 仍失败，详情如下 |

补充黑盒三个失败与导入阶段在独立 upstream 副本保存的失败一致：family-management 等待旧文案“请先绑定家人，并由父母授权共享药物资料。”超时；four-tab-flow 等待旧按钮“我是老人”超时；voice-dialog 的取消按钮不在手机首屏。已逐项对比 `.runtime/ankang-validation/upstream-*.log`，本轮未更改对应 UI/测试，也没有放宽断言。因此不能声称所有补充黑盒全绿。独立 P0 runner 上次在 Windows `spawn npm ENOENT`，本轮未重跑/修复该 runner；硬件实机、真实外部 LLM、真实通知收件人也不属于本轮测试证据。

新增 [runtime.test.ts](../../ankang/route1-health-agent/tests/runtime.test.ts) 覆盖：顺序/并发、source ID、append、安全 detection、Twin、tasks、correction 与旧 gate、private/no_record、session/audit 隔离、reset/close、revision conflict、持久化读写/clear 失败、在途 save 后 reset、重开 ID 唯一、跨午夜、LLM 回退、送达失败。

parity 使用 [legacyReactOrchestration.ts](../../ankang/route1-health-agent/tests/fixtures/legacyReactOrchestration.ts)：从 **ef5a767d** 的 hook/App/useCareTasks 原流程转录的仅测试 reference，不依赖 `src/runtime`，由测试注入相同时钟/ID，并把 React setter/effect 换成内存状态更新。12 轮连续输入比较完整 reply、understanding、plan、本人/家庭事件、chat、tasks、audit、共享 ID、materialized data、findings、Context（含两种 Twin），全部一致。

这是**业务编排 reference parity**，不是渲染两套 React DOM，也不是对所有可能输入的数学证明。reference 与新实现共用未变领域代码；共享审计在 reference 中显式注入相同初始值代替单浏览器全局。浏览器回归另验证实际保留 App，不能把 reference 当作完整 React 并发等价证明。通知/webhook 使用测试替身，不证明真实家属送达；cross-device 中拒绝连接是原失败状态门禁的预期场景。

## 文件与 Git 交付

新增生产文件：`src/runtime/{index,session,ports,turn,derive,careTasks}.ts`。

修改生产文件仅 `src/App.tsx`、`src/hooks/useElderChat.ts`、`src/hooks/useCareTasks.ts`、`src/engine/elderTurn.ts`（以上均在 ankang/route1-health-agent 下）。

新增测试文件：`tests/runtime.test.ts`、`tests/runtime-dependencies.test.ts`、`tests/fixtures/legacyReactOrchestration.ts`。文档：更新 core boundary，新增本报告。原康复 Python 项目、根文件、route2、iOS、hardware 和原 70 个 TypeScript 测试均未修改。

包含本报告的 commit 无法把自己的 SHA 写入自身；最终 SHA、远端一致性、ahead/behind 和 clean 状态以交付答复及以下命令实查：

```sh
git rev-parse HEAD
git ls-remote origin refs/heads/codex/rehab-agent-stage1 refs/heads/main
git rev-list --left-right --count origin/main...HEAD
git status --porcelain
git diff --name-status ef5a767d33fe87b5714bbf3c0125b5ed32c88575 HEAD
```

本轮到 Runtime 抽取与验收为止；提交推送后停止，等待人工审核。
