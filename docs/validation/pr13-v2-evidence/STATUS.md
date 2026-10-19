# PR13 V2 当前逐项验收状态

工程未完成，不建议合并 main。历史状态和本轮状态分列；未继承历史 PASS。

源码基准：`02c0eb638163fa0edaeeced300514b49273ef41d`；运行及源码摘要见 `run-manifest.json`。

| ID | 节点 | 历史 | 当前 | 源码／入口 | 本轮证据 | 未解决问题 |
|---|---|---|---|---|---|---|
| 1.1 | 真实 DeepSeek 第一层 | PARTIAL | UNVERIFIED | R/scripts/chat-model.cjs / Session→understandSemanticTurn→reply(understanding) | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 1.2 | 六类语义字段与 schema | PASS | PASS | R/src/runtime/semanticRouter.ts / parseSemanticTurn | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 1.3 | 五路语义分类 | PARTIAL | UNVERIFIED | R/src/runtime/semanticRouter.ts / 第一层 route/intents | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 1.4 | 第一层只理解 | PASS | PASS | R/src/runtime/semanticRouter.ts / 无业务调用／无写入 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 1.5 | JSON异常／故障回退 | PASS | PASS | R/src/runtime/session.ts / null→原本地处理 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 1.6 | 多意图保留／分流 | PARTIAL | UNVERIFIED | R/src/runtime/semanticExecution.ts / intents→康复优先门禁 | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 1.7 | 主体／时间／否定／假设／纠正 | FAIL | UNVERIFIED | R/src/runtime/semanticLegacyAdapter.ts / prepareTurn→原临床规则 | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 2.1 | 普通聊天真实回复 | PASS | UNVERIFIED | R/src/runtime/semanticExecution.ts / chat→reply | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 2.2 | 连续聊天上下文 | PARTIAL | UNVERIFIED | R/src/runtime/session.ts, conversation.ts / 同来源用户上下文 | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 2.3 | 聊天不调用康复工具 | PASS | PASS | R/src/runtime/semanticExecution.ts / chat分支 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 2.4 | 模型故障本地回退 | PASS | PASS | R/src/runtime/session.ts / reply拒绝／超时 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 3.1 | 公共健康知识问答 | PASS | UNVERIFIED | R/src/runtime/semanticExecution.ts / health→公共reply | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 3.2 | 个人健康数据辅助咨询 | NOT IMPLEMENTED | NOT IMPLEMENTED | R/src/runtime/semanticExecution.ts / health无个人指标工具 | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 3.3 | 既有健康指标／导入接口 | PARTIAL | UNVERIFIED | R/src/product/ProductService.ts / health.record/healthkit.import | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 3.4 | Watch/HealthKit咨询工具 | NOT IMPLEMENTED | NOT IMPLEMENTED | R/src/adapters/HealthKitDeviceAdapter.ts / 可选桥接，非health工具 | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 3.5 | HealthKit硬件读取 | UNVERIFIED | UNVERIFIED | R/native-ios及adapter / iOS授权→外部bridge | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 3.6 | 已存个人资料外发隔离 | PASS | PASS | R/src/rehab/workflow.ts, programOperations.ts / 公共allowlist／本地读取 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 3.7 | 临床安全优先 | PASS | PASS | R/src/runtime/turn.ts / 原planner先于业务操作 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 4A.1 | 当前计划真实读取 | PASS | PASS | D/app/rehab_read_tools.py / Host→Storage→scope回执 | host-tests.txt, host-junit.xml | 本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。 |
| 4A.2 | 历史／近期评估读取 | PASS | PASS | D/app/rehab_read_tools.py / get_training_history/get_recent_assessments | host-tests.txt, host-junit.xml | 本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。 |
| 4A.3 | 个人限制可信来源 | NOT IMPLEMENTED | NOT IMPLEMENTED | R/src/rehab/workflow.ts / 缺profile/restrictions reader | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 4B.1 | 真实动作卡内容／条件／剂量 | PASS | PASS | R/src/rehab/catalogue.ts, assistant.ts / searchCards | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 4B.2 | 中文口语／同义词／来源完整回传 | PARTIAL | PARTIAL | R/src/rehab/assistant.ts, workflow.ts / 名称／ID搜索与projection | agent-ci.txt | 动作检索结果已完整回传 sourceRefs；尚无本轮真实模型口语覆盖。 |
| 4B.3 | 无匹配动作 | PASS | PASS | R/src/rehab/assistant.ts / 搜索空集→明确补充信息 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 4C.1 | 指导资料按任务检索 | PASS | PASS | R/src/rehab/guidance.ts, assistant.ts / searchGuidance | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 4C.2 | 疼痛／疲劳／休息／进退阶／器材／协助 | PASS | PASS | R/src/rehab/assistant.ts / 指导关键词与专业边界 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 4D.1 | 真localPlan调用 | PASS | PASS | R/src/rehab/assistant.ts, workflow.ts / rehab.run_plan_algorithm | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 4D.2 | 算法参数个体来源解析 | NOT IMPLEMENTED | NOT IMPLEMENTED | R/src/rehab/workflow.ts / 未接可信评估resolver | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 4D.3 | 腰椎起始算法模板 | NOT IMPLEMENTED | NOT IMPLEMENTED | R/src/rehab/planRules.ts / 5个既有起始映射 | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 5.1 | 动作指导不强制计划 | PASS | UNVERIFIED | R/src/runtime/semanticExecution.ts / rehabAnswerTask→公共搜索→reply | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 5.2 | 本人康复记录分析 | PARTIAL | UNVERIFIED | R/src/rehab/workflow.ts / 三只读工具→本地格式化 | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 5.3 | 康复问题咨询 | PASS | UNVERIFIED | R/src/runtime/semanticExecution.ts / 公共guidance→grounded reply | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 5.4 | 结构化候选计划 | PARTIAL | PARTIAL | R/src/rehab/workflow.ts / LLM规划→工具→LLM候选→校验 | agent-ci.txt | AI 自然语言入口恢复真实检索、模型候选与校验；未完成持久化审核采用。 |
| 6.1 | ID／完整训练卡／空集／重复／评估卡校验 | PASS | PASS | R/src/rehab/workflow.ts / validateRehabPlan | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 6.2 | passed/needs_review/rejected边界 | PASS | PASS | R/src/rehab/workflow.ts / 程序校验状态 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 6.3 | 剂量来源与算法一致性 | PARTIAL | PARTIAL | R/src/rehab/workflow.ts / 卡片原文／候选与算法比对 | agent-ci.txt | 模型编造剂量现被拒绝；个体适用性与剂量专业审批尚未连接。 |
| 6.4 | 专业审核回执连接 | NOT IMPLEMENTED | PARTIAL | cloud_service/rehab_workflow.py / POST rehab-candidates/{id}/review（现有规则候选，非AI草案） | cloud-tests.txt, review-tests.txt | 既有规则候选审核已绑定内容摘要、资料及授权版本，持久化审核人回执；尚未连接 AI 草案。 |
| 6.5 | 用户确认不能代替审核 | PASS | PASS | R/src/runtime/semanticExecution.ts / review门禁 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 7.1 | 页面导航 | PARTIAL | UNVERIFIED | R/src/product/ProductAgent.ts, ProductService.ts / open_module→turn.agent.navigation | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 7.2 | 自然语言查看本人计划 | PASS | UNVERIFIED | R/src/runtime/semanticExecution.ts / records→Host选读→本地回执 | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 7.3 | 真Host改名／参数／增删动作 | PASS | PASS | D/app/rehab_operation_tools.py, storage.py / plan.change直接API | host-tests.txt, host-junit.xml | 本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。 |
| 7.4 | 真Host日期时间／新增取消安排 | PASS | PASS | D/app/rehab_operation_tools.py, product/daily_store.py / schedule.upsert/remove直接API | host-tests.txt, host-junit.xml | 本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。 |
| 7.5 | NLP预览→确认→写入→重读 | NOT IMPLEMENTED | PARTIAL | R/src/rehab/programOperations.ts / 个人资料处理授权缺口→阻断 | host-tests.txt, host-junit.xml, agent-ci.txt | 本人唯一有效计划的明确改名已接本地解析→真实预览→确认→SQLite写入→权威重读，重复确认不再写；改动作、剂量和时间的自然语言链路仍未接通。模型仅为协议fixture。 |
| 7.6 | 自然语言设置提醒 | NOT IMPLEMENTED | NOT IMPLEMENTED | 无已注册执行工具 / 无调用链 | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 7.7 | 取消／离题／隐私／故障／重置失效 | PASS | PASS | R/src/runtime/session.ts / pending生命周期 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 7.8 | revision及审计 | PASS | PASS | D/app/storage.py, rehab_operation_tools.py / 事务内revision/audit | host-tests.txt, host-junit.xml | 本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。 |
| 7.9 | 并发冲突 | PASS | PASS | D/app/product/daily_store.py / 同事务expected_existing | host-tests.txt, host-junit.xml | 本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。 |
| 7.10 | 跨用户／来源拒绝 | PASS | PASS | D/app/rehab_operation_tools.py, R/src/runtime/rehabTools.ts / scope/receipt双边界 | host-tests.txt, host-junit.xml | 本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。 |
| 8.1 | 混合问题识别并先分析 | PARTIAL | UNVERIFIED | R/src/runtime/semanticExecution.ts / rehab/health/module+intents | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 8.2 | 缺信息不默认删空／暂停 | PASS | PASS | R/src/rehab/workflow.ts, programOperations.ts / uncertainties/review阻断 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 8.3 | 急症先于修改 | PASS | PASS | R/src/runtime/turn.ts, session.ts / safetyAction先行并清pending | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 8.4 | 分析→建议→专业核验→确认→App变化 | NOT IMPLEMENTED | NOT IMPLEMENTED | 新跨分支链路缺失 / 在review／授权处停止 | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 9.1 | 候选采用并创建新计划 | NOT IMPLEMENTED | NOT IMPLEMENTED | 无create/adopt工具 / 候选回复止于文本 | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 9.2 | 知识卡到可执行动作映射 | NOT IMPLEMENTED | PARTIAL | R/src/rehab/exerciseMapping.ts / runRehabWorkflow → mapKnowledgeActionToApp | agent-ci.txt | 已有两个显式技术动作映射；完整动作覆盖与采用链路未完成。 |
| 9.3 | 专业批准后采用 | NOT IMPLEMENTED | NOT IMPLEMENTED | 候选与医生流程未连接 / 无review receipt→adopt | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 9.4 | 新候选保存／患者显示／重开／待办 | NOT IMPLEMENTED | NOT IMPLEMENTED | D/UI与M/unified仅旧计划读取 / 候选详情仅文本／关闭 | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 9.5 | 既有计划重开／顺序／剂量存储 | PASS | PASS | D/app/storage.py / 真实SQLite重开与reader | host-tests.txt, host-junit.xml | 本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。 |
| 9.6 | 自动生成4–5个可执行动作 | NOT IMPLEMENTED | NOT IMPLEMENTED | R/src/rehab/assistant.ts / localPlan最多3个匹配项 | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 10.1 | 超范围问题分因 | PASS | PASS | R/src/runtime/scopeFallback.ts / out_of_scope | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 10.2 | 知识缺失区别临床升级 | PASS | PASS | R/src/rehab/assistant.ts / 无匹配补名称／编号 | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 10.3 | 未接外部操作不伪造回执 | PASS | PASS | R/src/runtime/scopeFallback.ts / unsupported_operation | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 10.4 | 诊断／处方／治疗决定升级建议 | PASS | PASS | R/src/runtime/scopeFallback.ts / clinical_handoff | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 10.5 | 真实联系医生／预约 | NOT IMPLEMENTED | NOT IMPLEMENTED | 无注册自然语言工具 / 手动入口或本地建议 | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| 10.6 | 一般健康问题不机械升级 | PARTIAL | UNVERIFIED | R/src/runtime/semanticExecution.ts / health提示与回复guard | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| 11.1 | 多轮原文指代／纠正 | FAIL | PARTIAL | R/src/runtime/semanticRouter.ts, session.ts / 获准同来源history | agent-ci.txt | 本轮验证任务重开和原话器材更正；原真实模型的复杂指代失败尚未以真实模型复验。 |
| 11.2 | 器材／限制可编辑候选状态 | NOT IMPLEMENTED | PARTIAL | R/src/rehab/taskState.ts, R/src/runtime/session.ts, ports.ts / Session → executeSemanticTurn → taskUserText → runRehabWorkflow | agent-ci.txt | 新增本地持久任务、原话证据、修订版与器材追问；尚未完成可信限制解析和专业审核版本连接。 |
| 11.3 | “按这个计划”不能盲目采用 | PASS | PASS | R/src/rehab/workflow.ts / needs_review／无adopt | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| 11.4 | 换话题后的“好的”失效 | PASS | PASS | R/src/runtime/session.ts / 统一清pending | agent-ci.txt | 限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。 |
| UI.1 | 桌面实际入口 | PARTIAL | PARTIAL | D/app/product/backend.py, UI / ProductBackend→AgentBridge | ui-tests.txt, desktop-results.json, desktop-real-launch.png | 隔离 TEST 目录实际 Qt 六页、离线聊天及真实主启动截图通过；未验证 AI 审核采用页面。语义 flag 默认关闭。 |
| UI.2 | 配对网页实际入口 | UNVERIFIED | PARTIAL | M/unified.py, static/unified.js / SharedProduct→同桌面owner | browser-review.md | 实际浏览器完成 TEST 配对、页面导航、离线消息与重载保留；康复拍摄来源下无新AI计划，审核采用仍未验证。 |
| UI.3 | 独立Android JS入口 | PARTIAL | UNVERIFIED | A/web/local-api.js / ProductService第10参数 | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| UI.4 | 独立Python手机Host | NOT IMPLEMENTED | NOT IMPLEMENTED | M/product_host.cjs / new ProductService(store) | 无 | 当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。 |
| UI.5 | APK/iOS/Watch真机 | UNVERIFIED | UNVERIFIED | 原生入口 / 实际安装／硬件 | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| UI.6 | 公网实际运行 | UNVERIFIED | UNVERIFIED | 独立云服务 / 既有部署环境 | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| REG.2 | 扩展桌面产品回归 | FAIL | FAIL | D/tests/test_product_*.py / Qt/真实bridge回归 | desktop-tests.txt, desktop-junit.xml | 本轮完整桌面产品回归存在实际失败；保留失败和堆栈，未修改旧测试预期或恢复已退役操作。详见日志与检查点。 |
| REG.3 | 手机视觉模型回归 | UNVERIFIED | UNVERIFIED | M/tests / 真实本地模型/IPC/空白视频 | 无 | 尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。 |
| REG.1 | 旧三问桥接协议兼容 | FAIL | PASS | D/tests/test_rehab_read_tools.py / real_bridge_three_questions_and_scope_isolation | host-tests.txt, host-junit.xml | 本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。 |
| UX01 | 首次进入时提供可忽略的快捷问题；不限制自由提问。 | 新增 | NOT IMPLEMENTED | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | 无 | 尚未实现本轮 V2 首次欢迎与可忽略的快捷提问。 |
| UX02 | 任务缺必要信息时仅问优先级最高的 1–2 个问题；用户回答后推进状态。 | 新增 | PARTIAL | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | agent-ci.txt | 缺器材时仅追问一个问题，补充后推进同一任务；更广的信息缺口尚待实现。 |
| UX03 | 能使用已授权的既有可靠记录免重复追问；无权限不读取，不推断缺失字段。 | 新增 | NOT IMPLEMENTED | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | 无 | 未接可信个人资料 reader，不能宣称已有可靠记录免重复追问。 |
| UX04 | 新条件（如无弹力带）会修改草案条件，标记版本并在必要时撤销旧审核。 | 新增 | PARTIAL | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | agent-ci.txt, review-tests.txt | 器材补充推进同一任务修订；本地拦下与明确不可用器材冲突的候选，可选器材不作必需。云端资料修改使旧核对失效；尚未贯通 AI 审核采用。 |
| UX05 | 用户取消、换话题、超时、权限变更或安全升级，旧待确认操作失效。 | 新增 | PARTIAL | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | agent-ci.txt | 任务取消、换话题、隐私、来源切换及30分钟过期清理；权限变化尚未贯通全部客户端。 |
| UX06 | 普通闲聊、健康知识、康复指导和计划制定各有适当交互，不强制走计划生成。 | 新增 | UNVERIFIED | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | 无 | 当前没有本轮全链路验收证据。 |
| UX07 | 聊天不得逐条暴露内部工具调用、JSON、推理或重复进度；工具失败仅给用户可理解的说明及下一步。 | 新增 | PARTIAL | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | agent-ci.txt, browser-review.md | 候选入口不逐条输出工具事件，规则状态改为自然语言；实际浏览器仅验离线聊天，尚未验证在线候选及失败呈现。 |
| UX08 | 生成待审核草案仅提供“调整草案/提交审核”，不得出现“立即执行”。 | 新增 | UNVERIFIED | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | 无 | 当前没有本轮全链路验收证据。 |
| UX09 | 已获批准的特定版本经用户确认才可执行；必须重新读取后证明持久化和动作可执行。 | 新增 | NOT IMPLEMENTED | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | 无 | AI 草案没有经专业批准、患者确认、实际采用及重读链路。 |
| UX10 | 审核退回、候选无匹配、资料缺失时主动询问或说明阻断，不虚构审批或保存成功。 | 新增 | UNVERIFIED | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | 无 | 当前没有本轮全链路验收证据。 |
| UX11 | 紧急危险信号优先处理，阻断后续训练/修改，并保留来源、必要风险信息。 | 新增 | UNVERIFIED | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | 无 | 当前没有本轮全链路验收证据。 |
| UX12 | 对同一个合成患者完成“用户自然语言→主动追问→实际检索→结构化草案→程序验证→专业审核→用户确认→持久化→患者端重开”全流程，并留审计证据。 | 新增 | NOT IMPLEMENTED | docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md / 尚待实际客户端集成验收 | 无 | 核心 AI 草案→审核→采用→患者重开仍缺连接；不将单元测试称为端到端通过。 |

原 77 项当前统计：`{"UNVERIFIED": 20, "PASS": 33, "NOT IMPLEMENTED": 13, "PARTIAL": 10, "FAIL": 1}`

UX01–UX12 当前统计：`{"NOT IMPLEMENTED": 4, "PARTIAL": 4, "UNVERIFIED": 4}`
