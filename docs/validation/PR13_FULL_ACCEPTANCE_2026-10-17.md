# PR #13 全架构、全链路与缺口验收

日期：2026-10-17（Asia/Shanghai）。仓库：`shengda119703-gif/tele-rehabilitation`；分支：`codex/unified-llm-entry-20261015`；PR #13 保持 Draft，未合并 main、未部署。

本报告验收的修复代码提交：`59c5226c82f482eccacd71424060540b45663254`；远端一致性：`修复代码与报告一并推送到目标分支；最终交付以该分支HEAD及最终回复的SHA为准`。本轮先冻结只读审计并提交 [8667766](https://github.com/shengda119703-gif/tele-rehabilitation/commit/86677662e1c55b81fbb62ac979808a767ec60175)，再运行反例、修复和复测；[初始报告](PR13_FULL_INITIAL_2026-10-17.md)及 G01–G09、E01–E02 均保留。

## A. 总体结论

**整体 FAIL；部分底层能力验收通过，不能按用户要求的完整树状图合并 main。** 本轮修复了已存个人资料外发、虚假适用性通过、旧确认跨话题执行、医生处方改写、日程竞态及入口漂移。修复安全问题不等于补齐缺失功能。

公共问答、严格 JSON、本人的授权只读接口、直接 Host 的真实 SQLite 修改及并发保护已有可复现证据。自然语言修改目前因缺少合规的个人资料处理／本地目标解析链路而明确阻断；新候选的专业审核、采用、动作映射、存储和患者界面没有接通。

**对核心问题的回答：不能。** 用户说“我有腰椎间盘突出，帮我制定一套在家的训练计划。”，本轮实际第一层理解成功，但第二层工具规划的search_guidance遗漏query，被程序拒绝，未检索或形成候选；不能一直运行到患者 App 出现经过适用性验证的训练计划。阻断位置依次是：可信个体评估／限制／等级来源不足；`localPlan()` 没有腰椎起始模板；候选必须保留 `needs_review`；没有候选专业审核回执、T-* 到可执行动作的验证映射、create/adopt 写库工具及候选到患者页面的连接。“确认”不能补齐这些节点。

本轮只使用明确的 SYNTHETIC/TEST 范围及隔离目录。真实模型调用使用用户本轮授权凭据，仅通过静默stdin进入进程内存，未保存到应用配置，模型凭据不进入源码、证据或报告；没有读写真实患者资料。真实 DeepSeek、真实 Host、Mock Host、UI 与设备证据分别判断。

## 证据索引与运行边界

`T/P/H/W/C/Y/A/L/U` 是下表的证据缩写；最终日志与脱敏 trace 统一放在 [pr13-full-evidence](pr13-full-evidence/)。原始结果、失败日志hash、复现命令及真实调用链均已保存，不能由旧计数升级状态。

| 证据 | 实际运行／结果 | 口径与限制 |
|---|---|---|
| B | 初始 HEAD `c3a5aaff28dc6f58699f63fe3a7233e5895e9b12`；干净隔离 clone；main `8f1fc2c`；三点差异 53 文件、11041+/51- | 既有代码及报告已提交；不能证明其他电脑的未提交内容 |
| T | `npm run typecheck`、`npm run build:bridge` 通过；全 TS 曾 559/559，新增混合路由回归后的终跑：`561/561（含最后新增的原文时间/null反例）；build/typecheck/security PASS` | 编译、确定性规则、Mock model/Host；不能替代真实数据库或模型 |
| P | 五个产品 cjs 文件终跑：`35/35`；前次 34/35，唯一筛查校验缺口已修 | 真 Node bridge/真实 ProductService，供应商 fetch 被替换；不是实际 DeepSeek |
| H | 真实 SQLite 64/64，通过 `test_rehab_operation_tools/daily_store/care_host/saved_training_plans` | 临时 SYNTHETIC/TEST 数据；预览、写入、重读、重开、审计、竞态、医生约束 |
| W | 网页脚本测试 129/129 | 浏览器逻辑回归，不代表实际网页交互／截图验收 |
| C | 云服务 75 passed / 4 skipped；Windows UTF-8 fixture 修复后复跑 | 本地 API／存储；4 skip 不是通过；未验证公网部署 |
| Y | Python 扩展回归当前 227 passed / 1 failed，终跑：`227 passed / 1 failed，原失败断言保留` | 保留旧三问桥接协议失败；初次 226/2 的一项为 fixture，另一项不能删除 |
| A | Android JS／生成资源终跑：`85/85 JS通过；APK资源构建因缺pose_landmarker_full.task失败，无Java/adb真机证据` | 已修构造参数、生成资产／测试 fixture；无安装 APK、真机或摄像头证据 |
| L | [真实模型＋真实隔离 SQLite trace](pr13-full-evidence/live-20261017.json)：22 场景，`最终22组/28轮/42调用，23/27第一层有效，19组理解通过/3失败；总任务84次真实调用（含中间harness轮），无模型余额/账单验收` | 模型 `deepseek-flash`；JSON/route 成功仅是理解证据，不是方案、写入或 UI 成功 |
| U | 实际 Qt 隔离 smoke 与截图；浏览器尝试失败：`Qt offscreen 6页+离线聊天通过、4截图；浏览器无可用surface，UNVERIFIED` | 桌面已运行、配对网页UNVERIFIED；离线 smoke 不能证明在线模型或新计划采用 |

初始 typecheck/test 因源码类型错误及新必需字段遗漏而失败；新 SQLite 反例初次 11 failed / 5 passed，其中 3 项原 fixture 的 `LOCAL` 来源无效、8 项为真实缺陷。早期桥接未构建产生的 11 errors／2 failures 归为环境前置失败，构建后另行复测；保留初始日志。首次真实模型 harness 缺时间参数的失败保留在 [初始 harness 证据](pr13-full-evidence/live-harness-initial-20261017.json)，不计作模型能力失败或成功。

## B. 树状图逐节点对照

路径缩写：`R=ankang/route1-health-agent`，`D=rehab_codex_single_camera_v2_1`，`M=mobile_rehab`，`A=android_offline`。PASS 表示该行限定节点有本轮实际证据；直接 Host PASS 不代表自然语言入口 PASS。UNVERIFIED 行保留实际环境限制。

| 节点 | 实现文件 | 实际调用入口 | 测试证据 | 状态 | 缺口／限定范围 |
|---|---|---|---|---|---|
| 1.1 真实 DeepSeek 第一层 | R/scripts/chat-model.cjs | Session→understandSemanticTurn→reply(understanding) | L/live-review | PARTIAL | 不以 Mock 代替真实兼容性 |
| 1.2 六类语义字段与 schema | R/src/runtime/semanticRouter.ts | parseSemanticTurn | T/语义83 | PASS | 校验版本、白名单、证据、原文与索引；兼容旧 optional 字段 |
| 1.3 五路语义分类 | R/src/runtime/semanticRouter.ts | 第一层 route/intents | L/live-review | PARTIAL | schema 合法不能证明分流正确 |
| 1.4 第一层只理解 | R/src/runtime/semanticRouter.ts | 无业务调用／无写入 | T | PASS | 第一层输出空工具列表，由业务层决定读取 |
| 1.5 JSON异常／故障回退 | R/src/runtime/session.ts | null→原本地处理 | T | PASS | 无内部 JSON 或伪造成功回执泄漏 |
| 1.6 多意图保留／分流 | R/src/runtime/semanticExecution.ts | intents→康复优先门禁 | T/L/live-review | PARTIAL | 完整混合修改仍被阻断 |
| 1.7 主体／时间／否定／假设／纠正 | R/src/runtime/semanticLegacyAdapter.ts | prepareTurn→原临床规则 | T/L/live-review | FAIL | 确定性边界通过；L更正/取消自引用relation被拒；详见R04 |
| 2.1 普通聊天真实回复 | R/src/runtime/semanticExecution.ts | chat→reply | L/live-review | PASS | 无工具及数据库变更预期 |
| 2.2 连续聊天上下文 | R/src/runtime/session.ts, conversation.ts | 同来源用户上下文 | T/L/live-review | PARTIAL | 语义历史为会话内用户原文，无完整候选状态 |
| 2.3 聊天不调用康复工具 | R/src/runtime/semanticExecution.ts | chat分支 | T | PASS | 模型 route 误判另计 |
| 2.4 模型故障本地回退 | R/src/runtime/session.ts | reply拒绝／超时 | T | PASS | 不声称已执行模块操作 |
| 3.1 公共健康知识问答 | R/src/runtime/semanticExecution.ts | health→公共reply | L/live-review | PASS | 回答质量与是否机械就医须核对 |
| 3.2 个人健康数据辅助咨询 | R/src/runtime/semanticExecution.ts | health无个人指标工具 | 源码/实际注册表 | NOT IMPLEMENTED | 不与公共健康问答合并判定 |
| 3.3 既有健康指标／导入接口 | R/src/product/ProductService.ts | health.record/healthkit.import | T/P | PARTIAL | 存储／产品接口存在，尚未连接健康咨询 |
| 3.4 Watch/HealthKit咨询工具 | R/src/adapters/HealthKitDeviceAdapter.ts | 可选桥接，非health工具 | 注册表 | NOT IMPLEMENTED | 不以模拟样本当真实设备数据 |
| 3.5 HealthKit硬件读取 | R/native-ios及adapter | iOS授权→外部bridge | 无设备 | UNVERIFIED | 适配器测试不代表真机授权／采样 |
| 3.6 已存个人资料外发隔离 | R/src/rehab/workflow.ts, programOperations.ts | 公共allowlist／本地读取 | T/边界18/L | PASS | G02安全修复；NLP修改能力未完成 |
| 3.7 临床安全优先 | R/src/runtime/turn.ts | 原planner先于业务操作 | T | PASS | 保留急症、否定、未知归属防线 |
| 4A.1 当前计划真实读取 | D/app/rehab_read_tools.py | Host→Storage→scope回执 | H | PASS | 实际SQLite本人／来源范围 |
| 4A.2 历史／近期评估读取 | D/app/rehab_read_tools.py | get_training_history/get_recent_assessments | Y/L/live-review | PASS | 最终真实模型接通历史/评估；旧口语三问协议仍有失败 |
| 4A.3 个人限制可信来源 | R/src/rehab/workflow.ts | 缺profile/restrictions reader | 源码 | NOT IMPLEMENTED | LLM自填不能作为评估／许可 |
| 4B.1 真实动作卡内容／条件／剂量 | R/src/rehab/catalogue.ts, assistant.ts | searchCards | T/P | PASS | 185卡：63评估、122训练；不是185项可执行App动作 |
| 4B.2 中文口语／同义词／来源完整回传 | R/src/rehab/assistant.ts, workflow.ts | 名称／ID搜索与projection | T/L/live-review | PARTIAL | 有限别名；工作流sourceRefs回传不完整 |
| 4B.3 无匹配动作 | R/src/rehab/assistant.ts | 搜索空集→明确补充信息 | T | PASS | 不编造动作，不自动等同必须就医 |
| 4C.1 指导资料按任务检索 | R/src/rehab/guidance.ts, assistant.ts | searchGuidance | T/边界18 | PASS | 固定关键词检索一个真实章节 |
| 4C.2 疼痛／疲劳／休息／进退阶／器材／协助 | R/src/rehab/assistant.ts | 指导关键词与专业边界 | T/边界18 | PASS | 本轮补直接疼痛匹配；不提供个体医疗许可 |
| 4D.1 真localPlan调用 | R/src/rehab/assistant.ts, workflow.ts | rehab.run_plan_algorithm | T/P | PASS | 缺可信screening返回needs_review，不冒充生成成功 |
| 4D.2 算法参数个体来源解析 | R/src/rehab/workflow.ts | 未接可信评估resolver | 源码/边界18 | NOT IMPLEMENTED | 不让模型伪造等级／筛查／限制 |
| 4D.3 腰椎起始算法模板 | R/src/rehab/planRules.ts | 5个既有起始映射 | 真localPlan反例 | NOT IMPLEMENTED | 腰突请求无匹配模板 |
| 5.1 动作指导不强制计划 | R/src/runtime/semanticExecution.ts | rehabAnswerTask→公共搜索→reply | T/L/live-review | PASS | 公共模型链路存在；L动作解释有效且保留开始/停止条件 |
| 5.2 本人康复记录分析 | R/src/rehab/workflow.ts | 三只读工具→本地格式化 | T/H/L | PARTIAL | 可呈现记录，未完成可信纵向效果分析 |
| 5.3 康复问题咨询 | R/src/runtime/semanticExecution.ts | 公共guidance→grounded reply | T/L/live-review | PASS | 不应把所有问题转成计划 |
| 5.4 结构化候选计划 | R/src/rehab/workflow.ts | LLM规划→工具→LLM候选→校验 | T/边界18/L | PARTIAL | 候选不是个人处方，未写库 |
| 6.1 ID／完整训练卡／空集／重复／评估卡校验 | R/src/rehab/workflow.ts | validateRehabPlan | T/边界18 | PASS | 不存在、未检索、重复、空候选拒绝 |
| 6.2 passed/needs_review/rejected边界 | R/src/rehab/workflow.ts | 程序校验状态 | T/边界18 | PASS | 当前普通LLM候选不能自证passed |
| 6.3 剂量来源与算法一致性 | R/src/rehab/workflow.ts | 卡片原文／候选与算法比对 | T/边界18 | PARTIAL | 个体参数／适用性尚无可信来源 |
| 6.4 专业审核回执连接 | R/src/rehab/workflow.ts | 未实现候选专业批准接口 | 源码 | NOT IMPLEMENTED | 既有云医生手工流程不能代替本链路 |
| 6.5 用户确认不能代替审核 | R/src/runtime/semanticExecution.ts | review门禁 | T/H | PASS | needs_review不写；医生发布处方不能被患者改剂量 |
| 7.1 页面导航 | R/src/product/ProductAgent.ts, ProductService.ts | open_module→turn.agent.navigation | P/U | PARTIAL | 句末。已覆盖，ProductService导航回执通过；网页交互仍UNVERIFIED |
| 7.2 自然语言查看本人计划 | R/src/runtime/semanticExecution.ts | records→Host选读→本地回执 | T/H/L | PASS | 保留全句本人授权gate；L路由质量另计 |
| 7.3 真Host改名／参数／增删动作 | D/app/rehab_operation_tools.py, storage.py | plan.change直接API | H | PASS | 仅既有计划；不代表NLP可写 |
| 7.4 真Host日期时间／新增取消安排 | D/app/rehab_operation_tools.py, product/daily_store.py | schedule.upsert/remove直接API | H | PASS | 真保存ID、重读、重开、删除回执 |
| 7.5 NLP预览→确认→写入→重读 | R/src/rehab/programOperations.ts | 个人资料处理授权缺口→阻断 | T/边界18 | NOT IMPLEMENTED | 当前明确请用户在康复页手动修改 |
| 7.6 自然语言设置提醒 | 无已注册执行工具 | 无调用链 | 注册表 | NOT IMPLEMENTED | 日程记录不是通知调度 |
| 7.7 取消／离题／隐私／故障／重置失效 | R/src/runtime/session.ts | pending生命周期 | T/语义83 | PASS | 旧pending内部注入回归；不是新NLP写入证据 |
| 7.8 revision及审计 | D/app/storage.py, rehab_operation_tools.py | 事务内revision/audit | H | PASS | 预览不写；commit恰增一次；失败不改 |
| 7.9 并发冲突 | D/app/product/daily_store.py | 同事务expected_existing | H | PASS | 竞态注入及双确认一胜一冲突 |
| 7.10 跨用户／来源拒绝 | D/app/rehab_operation_tools.py, R/src/runtime/rehabTools.ts | scope/receipt双边界 | H/T | PASS | 其他owner/source/context不能读写 |
| 8.1 混合问题识别并先分析 | R/src/runtime/semanticExecution.ts | rehab/health/module+intents | T/L/live-review | PARTIAL | 不能因主route=module绕过分析；L混合请求仍因审核/规划缺口停止 |
| 8.2 缺信息不默认删空／暂停 | R/src/rehab/workflow.ts, programOperations.ts | uncertainties/review阻断 | T/边界18 | PASS | 不自动重排既有动作 |
| 8.3 急症先于修改 | R/src/runtime/turn.ts, session.ts | safetyAction先行并清pending | T/L/live-review | PASS | L急症实际停止活动/寻求急救，无写入 |
| 8.4 分析→建议→专业核验→确认→App变化 | 新跨分支链路缺失 | 在review／授权处停止 | 源码/T | NOT IMPLEMENTED | 无临床适用性＋NLP写入闭环 |
| 9.1 候选采用并创建新计划 | 无create/adopt工具 | 候选回复止于文本 | 注册表/UI源码 | NOT IMPLEMENTED | 没有新计划ID／revision |
| 9.2 知识卡到可执行动作映射 | 新workflow未连接映射 | T-*≠患者snake_case动作ID | 源码 | NOT IMPLEMENTED | 不允许无证明的ID转换 |
| 9.3 专业批准后采用 | 候选与医生流程未连接 | 无review receipt→adopt | 源码 | NOT IMPLEMENTED | 普通“确认”不补批准 |
| 9.4 新候选保存／患者显示／重开／待办 | D/UI与M/unified仅旧计划读取 | 候选详情仅文本／关闭 | UI源码/U | NOT IMPLEMENTED | 旧计划UI存在不能算新闭环 |
| 9.5 既有计划重开／顺序／剂量存储 | D/app/storage.py | 真实SQLite重开与reader | H | PASS | 限直接Host已有计划，不扩大为新候选 |
| 9.6 自动生成4–5个可执行动作 | R/src/rehab/assistant.ts | localPlan最多3个匹配项 | T/P | NOT IMPLEMENTED | A–E仅图示；腰椎匹配0，不承诺4–5 |
| 10.1 超范围问题分因 | R/src/runtime/scopeFallback.ts | out_of_scope | T/L/live-review | PASS | 本地解释能力范围 |
| 10.2 知识缺失区别临床升级 | R/src/rehab/assistant.ts | 无匹配补名称／编号 | T | PASS | 不自动要求就医 |
| 10.3 未接外部操作不伪造回执 | R/src/runtime/scopeFallback.ts | unsupported_operation | T/L/live-review | PASS | 未联系／预约明确说明 |
| 10.4 诊断／处方／治疗决定升级建议 | R/src/runtime/scopeFallback.ts | clinical_handoff | T/H | PASS | 保留原安全处理；只是建议 |
| 10.5 真实联系医生／预约 | 无注册自然语言工具 | 手动入口或本地建议 | 注册表 | NOT IMPLEMENTED | 不得声称执行成功 |
| 10.6 一般健康问题不机械升级 | R/src/runtime/semanticExecution.ts | health提示与回复guard | T/L人工复核 | PARTIAL | 咖啡睡眠样例没有机械就医建议；不能泛化所有问法 |
| 11.1 多轮原文指代／纠正 | R/src/runtime/semanticRouter.ts, session.ts | 获准同来源history | T/L/live-review | FAIL | 只保留有限用户原文；不代表条件状态完成 |
| 11.2 器材／限制可编辑候选状态 | 无持久化candidate/profile state | 下游主要收本轮语义 | 源码/L/live-review | NOT IMPLEMENTED | “没有弹力带只有椅子”需程序状态闭环 |
| 11.3 “按这个计划”不能盲目采用 | R/src/rehab/workflow.ts | needs_review／无adopt | T | PASS | 只证明拒绝越权，不证明采用能力 |
| 11.4 换话题后的“好的”失效 | R/src/runtime/session.ts | 统一清pending | T/语义83 | PASS | 包含来源切换／privacy／invalid JSON／安全／reset |
| UI.1 桌面实际入口 | D/app/product/backend.py, UI | ProductBackend→AgentBridge | U | PARTIAL | 默认feature flag关闭；隔离测试需显式启用 |
| UI.2 配对网页实际入口 | M/unified.py, static/unified.js | SharedProduct→同桌面owner | U | UNVERIFIED | 不能以网页单元测试代替交互 |
| UI.3 独立Android JS入口 | A/web/local-api.js | ProductService第10参数 | A85 | PARTIAL | 构造漂移修复；无真实operation port／新计划采用 |
| UI.4 独立Python手机Host | M/product_host.cjs | new ProductService(store) | 注册入口 | NOT IMPLEMENTED | 未接模型／语义flag／康复读写ports |
| UI.5 APK/iOS/Watch真机 | 原生入口 | 实际安装／硬件 | 无设备 | UNVERIFIED | 资源构建／JS PASS不等于真机PASS |
| UI.6 公网实际运行 | 独立云服务 | 既有部署环境 | 未部署 | UNVERIFIED | 本轮不授权更新公网 |
| REG.2 扩展桌面产品回归 | D/tests/test_product_*.py | Qt/真实bridge回归 | Q | FAIL | 129通过、18失败、2skip；含退役控制调用及界面/回执断言冲突，完整归因尚待复核 |
| REG.3 手机视觉模型回归 | M/tests | 真实本地模型/IPC/空白视频 | M | UNVERIFIED | 121通过、4失败、2skip；当前缺真实视觉模型/环境，未伪造检测成功 |
| REG.1 旧三问桥接协议兼容 | D/tests/test_rehab_read_tools.py | real_bridge_three_questions_and_scope_isolation | Y | FAIL | 旧模型fixture按JSON读取当前自然语言prompt，当前整项仍失败 |

## C. 七条实际调用链与数据库变化

真实最终层次及逐例人工判断见 [live-review.md](pr13-full-evidence/live-review.md)；复现命令、全部失败ID与日志hash见 [test-summary.json](pr13-full-evidence/test-summary.json)。

下列链路逐次标识 LLM／工具／Host／最终行为。L 的原始模型响应与读取回执保留在脱敏 JSON；P/T 的替代模型明确标记 Mock。`[逐例人工复核](pr13-full-evidence/live-review.md)`：主审补充各条真实案例ID、LLM次数及实际reply，不用设计图冒充执行。

1. **普通聊天**：ProductService.request(chat)→Session→LLM #1 `understanding`→parseSemanticTurn→route=chat→LLM #2 `reply`→用户文本。T/P证明无康复工具；L案例`chat`提供真实两轮模型响应。业务计划／日程DB应不变，聊天revision仅表示会话变化。
2. **健康咨询**：同入口→LLM #1→prepareTurn原安全规则→health→LLM #2一般健康解释。L案例`health_public`；个人指标、Watch工具没有执行。急症改由本地安全回复；不能据此声称读取个人健康记录或已联系医生。
3. **动作指导**：LLM #1→rehab/exercise_guidance→真实`searchCards/searchGuidance`→公共资料→LLM #2 grounded reply→isUserFacingSemanticReply及保留条件。T/P＋L案例`action_guidance/rest_guidance`；无计划创建、无DB写入；缺匹配输出补充信息。
4. **康复计划生成**：LLM #1→plan_generation→LLM #2 `selectRehabTools`→Host `get_training_plan/history/assessments`或真实公共搜索／`localPlan()`→LLM #3候选JSON→validateRehabPlan→`needs_review/rejected`→确定性候选文本。个人回执从LLM载荷剔除；L案例`lumbar_plan`记录实际选工具。候选未创建计划，DB不变。
5. **程序操作**：LLM #1→program_operation→LLM #2选择读取→真实本地Host plan/schedule→隐私／可信解析缺口→明确阻断，无新pending、无commit。L最终harness安装真实Python操作端口，实际只调用get_schedule读取；隐私阻断后没有commit。T也验证该阻断。**另立H直接API链**：preview(commit=false)→记录/audit不变→commit(true)→Storage/DailyStore→权威read/reopen核对ID/revision/audit；这是程序API证据，不是用户一句话闭环。
6. **混合意图**：LLM #1保留rehab_question+program_operation→原安全优先→康复工具规划／公共资料候选→validation非passed→停止，未进入程序预览写入。T覆盖primary module/health反例；L案例`knee_mixed/mixed_discomfort/urgent`补真实情况。数据库不变；不能把安全阻断称为调整成功。
7. **其他问题／医生建议**：LLM #1→other或明确临床边界→resolveScopeFallback→out_of_scope/unsupported_operation/clinical_handoff本地文本；没有后续医生工具、预约或写库。T＋L案例`other/external/clinical/unknown_action`；缺知识不会自动升级为必须看医生。

## D. 初始问题、修复及复测清单

已修复问题对应同一个源代码提交；未修复问题保留明确失败。原始结果与冻结报告不删除。

| ID／严重度 | 复现与预期 | 初始实际／根因及涉及文件 | 修复／当前状态 | 修复SHA | 复测结论 |
|---|---|---|---|---|---|
| G01/P1 | 查本人计划；第一层输出空工具仍应读取 | 执行依赖第一层tool_requests，与prompt冲突；semanticExecution | 业务层选读，原授权与scope保留 | 59c5226c82f482eccacd71424060540b45663254 | T新增三类合规空工具查询通过；L三个读取例有效 |
| G02/P0 | Host回执含已存资料；未经授权不应交外部模型 | workflow/programOperations发送raw tool_results；合成marker反例=true | 候选仅公共allowlist；NLP修改规划依赖私有资料故fail-closed，功能未补齐 | 59c5226c82f482eccacd71424060540b45663254 | 边界18/18；L：13次真实读取，个人记录未外发 |
| G03/P1 | preview→privacy/错误JSON/安全话题→确认应失效 | pending只在有效语义执行器晚清理；session/semanticExecution | 回合、context、故障、安全、reset统一清理 | 59c5226c82f482eccacd71424060540b45663254 | T七情境旧pending注入回归通过 |
| G04/P1 | 任意真卡＋模型screening=true不能获个人适用性PASS | validateRehabPlan可绕算法、检索和reviewRequired | 空／重复／未检索等拒绝；普通候选永需核对；无可信筛查不生成算法项 | 59c5226c82f482eccacd71424060540b45663254 | 边界18/18；适用性/专业审核功能仍缺 |
| G05/P1 | Android开语义flag应正确接线 | 第9构造参数误当rehabOperations；local-api/host fixture | 正确第10参数；未新增Android写入Host | 59c5226c82f482eccacd71424060540b45663254 | P语义宿主4/4；A85通过 |
| G06/P1 | 医生ACTIVE处方改剂量应拒绝且不污染审计 | adapter/Storage保留旧doctor_publication但接受动作patch | preview拒绝；Storage事务内复核，去批准字段不能绕过；允许安全改名 | 59c5226c82f482eccacd71424060540b45663254 | H真SQLite通过，revision/audit不变 |
| G07/P1 | 同快照竞态第二次写应拒绝；成功应返回持久ID | 日程快照比较在事务外，dailyReceipt缺schedule ID | expected_existing事务内比较；返回保存记录及ID | 59c5226c82f482eccacd71424060540b45663254 | H竞态注入、双线程一胜一冲突、重开重读通过 |
| G08/P1 | 腰突请求最终产生经核验App计划 | 无可信个体resolver、腰椎模板、review/adopt、映射、保存与展示链 | NOT IMPLEMENTED；本轮未新建临床模块 | — | 不能通过；候选文本不算闭环 |
| G09/P2 | 新schema应可编译／测试，无需放宽字段 | TS收窄／strict arguments／错误read签名，旧fixtures缺events/relations | 修真实类型guard及调用对象，更新fixtures；公共reply执行遗漏也恢复 | 59c5226c82f482eccacd71424060540b45663254 | T/typecheck通过；保留首次编译与公共reply失败 |
| E01/环境 | 使用已配置真实DeepSeek验证 | 初始配置不可用／无调用 | 按本轮用户授权静默stdin实际调用 | — | L：3组语义失败；不保留凭据 |
| E02/环境 | 真APK/iOS/Watch运行 | 无Java/adb/iOS/Watch硬件 | 未安装、未模拟通过 | — | UNVERIFIED |
| R01/P2 | 旧三问桥接及中文口语兼容应通过 | test_rehab_read_tools模型fixture按旧JSON协议读取新prompt，现仍失败 | 保留失败，不降低原协议断言换PASS | — | Y最终227通过、1失败 |

| R04/P1 | 左右膝更正、取消、多轮器材补充需保留有效语义 | L返回自引用relation、无效字段/证据等，被严格schema拒绝；工具规划也有search_guidance缺query | 未修复，保持校验与安全回退 | — | 最终3组FAIL；第一层23/27有效；腰突第二层未通过 |
| R05/P2 | 扩展产品/手机回归应全部通过 | 桌面18失败（含退役操作/界面断言）；手机4真实视觉测试失败，环境模型缺失 | 未改UI或恢复退役操作；未安装大模型依赖骗过测试 | — | Q129/18/2skip；M121/4/2skip，失败ID及堆栈保存 |

辅助缺口：痛觉关键词、原样 `\\n`、内部记录JSON展示及不可信候选summary已定向修复；直接localPlan未筛查拒绝恢复，workflow仍不能相信模型筛查值。专业审核和临床可用性没有由单元测试获得。

## E. 最终节点统计

统计严格以 B 表每一数据行一个节点计算；不是测试用例数量，也不把安全阻断记作被阻断的功能PASS。已按最终证据重新计算。

| 状态 | 节点数 |
|---|---:|
| PASS | 37 |
| PARTIAL | 14 |
| NOT IMPLEMENTED | 17 |
| FAIL | 4 |
| UNVERIFIED | 5 |
| 合计 | 77 |

真实模型统计：`最终22组/28轮/42调用，23/27第一层有效，19组理解通过/3失败；总任务84次真实调用（含中间harness轮），无模型余额/账单验收`；真实Host操作范围：H 64测试；最终综合命令计数：`T561；P35；H64；W129；C75+4skip；Y227+1fail；A85；扩展桌面129+18fail+2skip；手机Python121+4fail+2skip。存在重叠，不相加`。这些分母不同，不合并成一个“通过率”。L的schema/route PASS只能升级对应理解节点，不能自动升级7.5、8.4或9.*。

## F. 最小剩余工作与交付

1. 先解决真实模型更正/取消/器材补充的Schema兼容、第二层缺query和仍失败的旧三问桥接契约；冻结并上传最终可复现日志、源码／构建hash与远端SHA，保留原失败证据。
2. 明确个人储存资料的本地目标解析方案或独立有效外发授权，接通NLP既有计划预览／确认／commit／权威重读；不恢复未经授权的raw资料外发，不用Mock Host代替业务存储。
3. 给候选计划建立可信个体评估／限制／等级来源与专业审核回执，再实现有限且验证过的知识卡→可执行动作映射及create/adopt接口；无腰椎规则时继续明确无匹配，不能靠模型补造。
4. 使用同一SYNTHETIC患者验证候选→审核→采用→计划ID/revision→患者显示→重开持久化→动作顺序／剂量／状态／待办，之后才评估整图合并资格。
5. 为多轮器材纠正保存明确可修改的候选条件状态；独立Android／Python手机Host补齐端口后分别验收；提醒、真实医生预约和可穿戴咨询按独立未实现节点安排，不能虚构执行。

本次交付：本报告、冻结初始报告、定向修复及证据；修复代码：`59c5226c82f482eccacd71424060540b45663254`；报告提交及远端核对在最终交付时给出，PR仍Draft。保持默认关闭，未合并 main、未部署、未变更真实患者数据。

未验证：真实摄像／动作精度、已安装手机APK、Apple硬件、通知送达、公网部署与临床结局。已知风险：新自然语言计划采用及调整闭环缺失，不能作为经过个体适用性确认的训练处方使用。

补充复测：扩展桌面产品18项及手机视觉4项失败均保留在Q/M原始日志中，不宣称属于已修复或全部既有。第一轮harness缺now为测试器错误（0调用）；中间direct Runtime未传只读/导航端口，42调用不计产品验收；最终产品式harness重新运行42调用，原始轮次全部保留。

复现入口与证据口径：[证据README](pr13-full-evidence/README.md)。

扩展回归逐项归因：[broad-regression-review.md](pr13-full-evidence/broad-regression-review.md)。18项桌面失败的源码/测试在main及初始PR的相关UI文件无差异，7项调用已退役care API；这只是源码比较，不声称已运行历史版本得出相同18失败。4项手机视觉测试缺YOLO权重，保留失败计数并将能力记UNVERIFIED。

Git上传说明：本机命令行无可用推送凭据，改用已连接GitHub工具上传。初始与修复提交的Git tree均与本地验收提交逐字节相同；远端修复59c5226对应本地e453993，初始8667766对应本地aa8cf7b。原trace/source_head不改写，完整映射见[git-publication.json](pr13-full-evidence/git-publication.json)。未强推。
