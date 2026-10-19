# PR #13 全架构验收：只读初始审计（冻结基线）

日期：2026-10-17（Asia/Shanghai）。本文件先于本轮代码修复与测试保存；后续缺口和修复追加到最终报告，不能删除或改写本基线。

## 仓库与范围

- 仓库 `shengda119703-gif/tele-rehabilitation`，PR #13 OPEN / Draft / 未合并。
- 分支 `codex/unified-llm-entry-20261015`，HEAD `c3a5aaff28dc6f58699f63fe3a7233e5895e9b12`。
- main `8f1fc2c706504f4119fb9bad984ab9ded87aa86d`；三点差异 53 文件，11041 additions / 51 deletions，PR 71 commits。
- 全新隔离 clone，初始 `git status --porcelain=v1 --untracked-files=all` 为空；目标分支远端 SHA 与本地一致。既有代码及报告已在该 HEAD 的 Git 历史中；无法替其他电脑或未附加会话证明其未提交状态。
- 已读根/应用 AGENTS、HANDOFF、SOFTWARE_SPEC、START_WITH_CODEX 及旧验收/剩余清单。旧计数和真实模型 trace 只作历史参考。
- 仅本轮隔离 SYNTHETIC/TEST 数据。无 main 合并、部署、真实患者资料操作。既有隐私/安全/专业审核规则为验收约束。
- 本机 Node 24.20.0 / npm 11.19.0 / Python 3.11.9；本机现有模型私密配置读取为 false，用户表示将通过原应用设置配置。没有读取/输出密钥值。

## 初始总体结论

**FAIL，不能按完整树状图验收合并 main。** 有可追踪实现，但存在隐私、待确认变更失效、验证及入口错误。自然语言到候选 JSON 不等于经过适用性验证并保存到患者 App。

状态口径：PASS 必须有本轮实际测试证据；本阶段只有只读源码证据，所以存在实现的节点暂记 PARTIAL，受环境限制的节点记 UNVERIFIED；确定错误记 FAIL；没有功能链路记 NOT IMPLEMENTED。

| 节点 | 实现文件（相对仓库） | 实际入口/静态证据 | 本轮测试证据 | 状态 | 初始缺口 |
|---|---|---|---|---|---|
| 1.1 第一层真实 DeepSeek | scripts/chat-model.cjs（均位于 ankang/route1-health-agent，除非另注） | AgentSession → semanticRouter → model.reply(purpose=understanding) | 尚未运行 | UNVERIFIED | 当前配置缺失 |
| 1.2 JSON route/intents/mentions/events/relations/uncertain | src/runtime/semanticRouter.ts | parseSemanticTurn 校验 | 尚未运行 | PARTIAL | 旧 fixtures/验收脚本缺新必需字段 |
| 1.3 多意图/主体/时间/否定/纠正/上下文 | src/runtime/semanticRouter.ts, semanticLegacyAdapter.ts | session 上下文和原文证据 | 尚未运行 | PARTIAL | 真实模型语义质量未验收 |
| 1.4 异常回退与第一层权限 | src/runtime/session.ts, semanticExecution.ts | 第一层提示要求不选工具；后续执行器 | 静态矛盾 | FAIL | 记录路由却依赖第一层 tool_requests |
| 2.1 普通聊天连续对话 | src/runtime/conversation.ts, semanticExecution.ts | route=chat → reply | 尚未运行 | PARTIAL | 真实自然程度未知 |
| 2.2 模型故障回退 | src/runtime/session.ts | local fallback | 尚未运行 | PARTIAL | 待确认状态回退失效不完整 |
| 3.1 公共健康知识 | src/runtime/semanticExecution.ts, scripts/chat-model.cjs | health → public reply | 尚未运行 | PARTIAL | 历史错路由需本轮验证 |
| 3.2 本人健康/评估辅助问答 | src/runtime/rehabTools.ts, ProductService.ts | 三康复读工具；本地格式化 | 尚未运行 | PARTIAL | 通用个人健康问答未全接通 |
| 3.3 Watch/HealthKit | src/adapters/HealthKitDeviceAdapter.ts, src/product/ExtensionPorts.ts | 可选外部桥接，非默认接入 | 无 iOS/Watch | UNVERIFIED | 适配器存在，当前产品未证明接通，DemoDeviceAdapter 不是设备证据 |
| 3.4 个人数据不擅自外发 | src/rehab/workflow.ts, programOperations.ts | candidate/buildPlan 序列化 tool_results 给模型 | 静态调用 | FAIL | 已存个人记录可能进入外部模型 |
| 3.5 既有医疗安全 | src/runtime/turn.ts, semanticLegacyAdapter.ts | 原临床 planner 优先 | 尚未运行 | PARTIAL | 混合/否定急症仍需回归 |
| 4.A 当前计划/历史/评估读取 | app/rehab_read_tools.py（应用目录 rehab_codex_single_camera_v2_1） | ProductBackend → Python/Node callback → Storage | 尚未运行 | PARTIAL | 不得用 Mock Host 代替 |
| 4.A 个人限制来源 | src/rehab/workflow.ts | algorithm_input、工具载荷 | 静态调用 | FAIL | LLM 可自填筛查/限制，可信来源不足 |
| 4.B 真实动作卡与剂量/条件/来源 | src/rehab/catalogue.ts, assistant.ts | searchCards | 尚未运行 | PARTIAL | 同义词/无匹配需测试 |
| 4.C 康复指导按任务检索 | src/rehab/guidance.ts, assistant.ts | searchGuidance | 尚未运行 | PARTIAL | 疲劳/休息/专业边界需测试 |
| 4.D localPlan 真算法 | src/rehab/workflow.ts, assistant.ts | rehab.run_plan_algorithm → localPlan | 尚未运行 | PARTIAL | 可选算法导致一致性门禁缺口 |
| 5.1 动作指导 | src/rehab/workflow.ts | rehabAnswerTask → runRehabReadOnlyAnswer | 尚未运行 | PARTIAL | 不应强制候选计划 |
| 5.2 康复记录分析 | src/rehab/workflow.ts | record 分流/本地个人资料 | 尚未运行 | PARTIAL | 跨分支数据与权限需核对 |
| 5.3 康复问题咨询 | src/rehab/workflow.ts | guidance 和 reply | 尚未运行 | PARTIAL | 公共/个人边界 |
| 5.4 候选方案生成 | src/rehab/workflow.ts | LLM 工具规划 → Host → LLM JSON | 尚未运行 | PARTIAL | 尚未保存到 App |
| 6.1 ID/完整训练卡/评估卡 | src/rehab/workflow.ts | validateRehabPlan | 尚未运行 | PARTIAL | 候选 ID 需一致性证明 |
| 6.2 适用性/剂量/算法/专业审核 | src/rehab/workflow.ts | validateRehabPlan | 静态调用 | FAIL | 无可信筛查也可 passed；未充分处理算法 reviewRequired |
| 6.3 确认不能代替专业审核 | src/runtime/semanticExecution.ts | 混合操作 needs_review 门禁 | 尚未运行 | PARTIAL | 确认/Host 防线需要真 DB 测试 |
| 7.1 页面导航 | src/product/ProductAgent.ts, UI consumer | open_module → UI response | 尚未运行 | PARTIAL | 第一层不提工具时接线存疑 |
| 7.2 查看本人计划 | src/runtime/semanticExecution.ts | route=records | 静态矛盾 | FAIL | prompt/执行器矛盾 |
| 7.3 改名/参数/增删动作 | src/rehab/programOperations.ts, app/rehab_operation_tools.py | preview → confirmation → commit | 尚未运行 | PARTIAL | 医生已发布计划可能保留审核引用却被改写 |
| 7.4 改日期时间/新增取消安排 | app/rehab_operation_tools.py, app/product/daily_store.py | DailyStore | 尚未运行 | PARTIAL | expected_existing 读写竞态、回执缺真实保存 ID |
| 7.5 外部提醒 | src/product/ExtensionPorts.ts | optional extension，无自然语言实际执行接线 | 无实现证据 | NOT IMPLEMENTED | 不能声称提醒已设置 |
| 7.6 预览/确认/取消/离题失效 | src/runtime/session.ts, semanticExecution.ts | pendingRehabOperation | 静态调用 | FAIL | 隐私、解析失败、安全早退未统一失效 |
| 7.7 revision/audit/concurrency | app/rehab_operation_tools.py, storage.py, daily_store.py | plan revision + operation audit | 尚未运行 | PARTIAL | schedule 非原子冲突校验 |
| 7.8 本人和来源隔离 | app/rehab_operation_tools.py, rehabTools.ts | scope_key/receipt | 尚未运行 | PARTIAL | 部分规划原始回执未逐层核验 |
| 8.1 混合意图分析→校验→预览 | src/runtime/semanticExecution.ts | rehab workflow 后操作 | 尚未运行 | PARTIAL | 分支存在，隐私/适用性错误阻断 |
| 8.2 急性症状优先 | src/runtime/turn.ts | 原规则优先 | 尚未运行 | PARTIAL | 待确认安全早退问题 |
| 8.3 缺资料不默认暂停删空 | src/rehab/workflow.ts, programOperations.ts | uncertainties/review | 尚未运行 | PARTIAL | 需反例测试 |
| 9.1 候选采用并存储 | src/runtime/semanticExecution.ts | 候选回复明确停在 JSON；注册写工具仅既有计划修改 | 无实现 | NOT IMPLEMENTED | 没有 create/adopt candidate 工具 |
| 9.2 T-* 到患者可执行动作映射 | app/rehab_catalogue.py/训练目录 | 部分既有起始映射；新 workflow 未引用 | 无完整实现 | NOT IMPLEMENTED | 全候选映射、参数转换和校验未贯通 |
| 9.3 专业审核后采用 | workflow/programOperations | 只有阻止未审核方案的门禁 | 无采用实现 | NOT IMPLEMENTED | 没有候选专业审核状态到采用的链路 |
| 9.4 保存/reopen/顺序剂量状态待办 | app/storage.py, product_window.py, mobile_rehab/static/unified.js | 既有手工计划 UI 与新 workflow 分离 | 新链路未接 | NOT IMPLEMENTED | 不能以旧 UI 存在判定新链路通过 |
| 9.5 自动 4–5 动作 | src/rehab/assistant.ts | localPlan 选实际匹配，数量不保证 | 尚未运行 | PARTIAL | 图示 A–E 不是产品承诺 |
| 10.1 超范围/缺知识/外部操作分因 | src/runtime/scopeFallback.ts | resolveScopeFallback | 尚未运行 | PARTIAL | 真实模型路由未验收 |
| 10.2 医生升级/紧急情况 | src/runtime/scopeFallback.ts, turn.ts | 本地建议，非真实联系工具 | 尚未运行 | PARTIAL | 不代表联系成功 |
| 10.3 联系医生/预约执行 | 无新自然语言工具 | 仅建议/手动入口 | 无实现 | NOT IMPLEMENTED | 不能伪造执行回执 |
| 11.1 多轮计划补充/器材纠正 | semanticRouter/workflow | 有限原始用户上下文 | 尚未运行 | PARTIAL | 新计划采用仍缺失 |
| 11.2 话题切换后确认 | session/semanticExecution | pending 生命周期 | 静态错误 | FAIL | 部分绕过失效路径 |
| UI.1 桌面 | app/product/backend.py, product_window.py | ProductBackend/AgentBridge | 待隔离测试 | UNVERIFIED | 未实际启动 |
| UI.2 配对网页 | mobile_rehab/static/unified.js | 共用 ProductBackend | 待隔离测试 | UNVERIFIED | 未实际浏览器验收 |
| UI.3 独立 Android/网页 | android_offline/web/local-api.js | ProductService 构造第9参数错位 | 静态调用 | FAIL | runtimeOptions 未传到第10参数；无操作 Host |
| UI.4 APK/iOS/Watch 真机 | 原生入口/可选适配器 | 本机无 adb/java/设备 | 无设备 | UNVERIFIED | 未运行，不猜测 PASS |

## 冻结初始问题清单

| ID | 严重度 | 复现/预期/实际/根因 | 涉及文件 | 修复状态 |
|---|---|---|---|---|
| G01 | P1 | 查询本人计划，第一层按 prompt 输出空 tool_requests；预期调用授权读工具，实际无法接通。理解层与执行层契约不一致。 | semanticRouter.ts/semanticExecution.ts | 未修复 |
| G02 | P0 | 康复工具返回含本人记录；预期只在本地处理，实际 candidate/buildPlan 将其 JSON 交给模型。 | workflow.ts/programOperations.ts | 未修复 |
| G03 | P1 | 预览→隐私/无效JSON/安全话题→确认；预期旧提案失效，实际可保留 pending。 | session.ts/semanticExecution.ts | 未修复 |
| G04 | P1 | LLM 选任意完整卡并自称筛查完成、无算法；预期不能通过个人适用性，实际可 passed。 | workflow.ts | 未修复 |
| G05 | P1 | Android 开启开关；预期进入语义路径，实际 options 成为 rehabOperations，第10参数默认关闭。测试 fixture 同样漂移。 | local-api.js/semantic-host-wiring.test.cjs | 未修复 |
| G06 | P1 | 改医生发布 ACTIVE 计划参数；预期需专业审核，实际 schema patch 后可保留 doctor_publication。 | rehab_operation_tools.py | 待动态复现 |
| G07 | P1 | 两提交共享 schedule 快照；预期原子拒绝后者，实际快照校验在事务外；写回回执也缺持久化 ID。 | rehab_operation_tools.py/daily_store.py | 待动态复现 |
| G08 | P1 | 腰突自然语言→候选→采用→患者显示；预期完整闭环，实际没有 candidate adoption/映射/存储/显示链路。 | workflow/semanticExecution/UI | NOT IMPLEMENTED，不扩建新模块 |
| G09 | P2 | 运行旧验收脚本/测试；预期符合新 schema，实际省略 events/relations。 | verify-semantic-acceptance.cjs/fixtures | 待测试确认 |
| E01 | 环境 | 配置读取 false，无本轮 DeepSeek 调用；等待用户原设置配置。 | 私密配置不入库 | UNVERIFIED |
| E02 | 环境 | Java/adb/iOS/Watch 不可用；旧设备测试不能替代。 | 原生环境 | UNVERIFIED |

## 七条静态调用链（此时没有本轮运行回执）

1. chat：ProductService → AgentSession → DeepSeek understanding → semantic 校验 → executeSemanticTurn → reply → 最终文本；应无业务工具/数据库变化。
2. health：同入口 → health → 原安全规则/公共 reply；已存个人记录必须本地展示，当前新康复规划外发路径为 G02。
3. 动作指导：rehabAnswerTask → runRehabReadOnlyAnswer → searchCards/searchGuidance → 公共资料 reply；不应生成候选计划。
4. 计划生成：selectRehabTools（LLM）→ runRehabToolSelection（Host/localPlan）→ generateRehabCandidate（LLM）→ validateRehabPlan → renderRehabDraft；无采用写库。
5. 程序操作：selectReads（LLM）→ Host plan/schedule → buildPlan（LLM）→ Host preview → pending → 用户确认 → Host commit → Storage/DailyStore；需本轮真库回执。
6. 混合意图：rehab workflow → validation → program preview → confirmation → commit；needs_review 应阻止，G02/G04 使当前链路不能验收。
7. other：resolveScopeFallback → 分原因本地说明/医生建议；不代表真实联系医生或预约。

## 后续

保存本文件后才运行现有测试；保留失败日志，补充确定性反例。按 P0/P1 修复可确定根因，隔离 SYNTHETIC/TEST Host 真读写并复查范围。真实模型/真实设备/完整 UI 独立判定，不降低 schema、权限或医疗约束。最终报告补充精确运行计数、节点统计、调用回执、提交 SHA 和最小剩余计划。
