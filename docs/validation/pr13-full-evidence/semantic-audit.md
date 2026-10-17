# PR #13 只读语义/健康/多轮审计基线

审计基准：codex/unified-llm-entry-20261015 HEAD c3a5aaff。已读取根 AGENTS.md、docs/HANDOFF.md 以及用户附件；未修改仓库源码、未调用外部模型、未读取真实患者数据库。以下 PASS 在尚未执行本次测试前不授予，存在代码仅判 PARTIAL/UNVERIFIED。

## 审计范围

阶段 1、2、3、10、11：semanticRouter.ts -> session.ts -> turn.ts/semanticLegacyAdapter.ts -> semanticExecution.ts -> conversation.ts/scopeFallback.ts；关联 ProductService、agent-bridge、Android local-api 与 HealthKit adapter；测试 semantic-router/runtime/legacy/host-wiring、conversation、scope-fallback、rehab-program-operations。

## 节点与实际链路

- 第一层理解：ProductService.request(chat) -> session(owner) (ProductService.ts 207-223) -> AgentRuntime.processTurn -> Session.process (session.ts 171-181) -> understandSemanticTurn (semanticRouter.ts 231-254) -> ConversationModel.reply(purpose=understanding) -> parseSemanticTurn (131-211)。schema 检查版本、枚举、数组上限、白名单字段、原文 evidence/context source；未知/不合法/超时返回 null。严格与旧字段兼容共存；症状 status/subject 仍 optional，以兼容旧 schema。未调用工具/未写业务。PARTIAL / 真实 DeepSeek 兼容性 UNVERIFIED。
- 普通聊天：semantic route=chat -> executeSemanticTurn (semanticExecution.ts 258-298) -> model.reply(purpose=reply) -> isUserFacingSemanticReply (50-56) -> applyTurnPlan 后聊天保存。无工具为正常路径。带最近获准用户原文 context（非 assistant 回复）；最多 4 条传递/6 条保留。模型失败返回本地。PARTIAL / 真实连续语境 UNVERIFIED。
- 公共健康咨询：route=health -> 既有临床安全先行 (semanticExecution.ts 74-77，turn.ts 27-48) -> scopeFallback -> 公共模型解释 (258-298)；明确禁止无资料诊断/操作声称。PARTIAL / 真实回答质量 UNVERIFIED。
- 个人健康数据辅助咨询：semanticExecution.ts 255-261 明确没有 Watch、个人健康数据库工具；语义层 SemanticToolName 仅康复读取与知识搜索 (semanticRouter.ts 12-13)。健康仪表/HealthKit 产品导入接口确实存在（ProductService.ts 325-336、HealthKitDeviceAdapter.ts），但未接通本次健康咨询分支。该咨询节点 NOT IMPLEMENTED，不应把已有 adapter 当成助手可调用。
- 否定/假设/主体：prepareTurn -> adaptSemanticUnderstanding -> 既有规则 polarity merger；证据须覆盖完整 clause、主体一致，冲突先澄清；urgent 本地安全规则不能由模型否定消除 (turn.ts 24-48)。schema本身只保证枚举与证据原文字面，不能验证 polarity 事实。PARTIAL / 实际 LLM 正确率 UNVERIFIED。
- other：executeSemanticTurn -> resolveScopeFallback (scopeFallback.ts 18-51) 在本地返回 clinical_handoff / unsupported_operation / out_of_scope，不会调用医生或预约；缺知识在 rehab read-only 返回补充动作信息，不应强制升级。PARTIAL / 此轮未运行测试。真实医生联系/预约工具 NOT IMPLEMENTED。
- 逐步计划条件更新：semanticHistory 只存在当前 session 内，不落盘；历史用户原文可引用，未保存独立可编辑的候选草案或当前条件状态。workflow只收到semantic JSON和本轮userText。设备纠正/计划采用流程只能依赖模型本次复述，缺程序级状态与采用接口。PARTIAL；专业审核/新候选存储由康复审计继续细化。

## 明确缺口（初始发现必须保留）

SEM-01 [P1] 旧待确认操作跨安全/隐私/解析失败回合存活。
- 根因：pendingRehabOperation 清理只在 semanticExecution.ts 80-99；既有安全/健康 early return 74-77 早于它。Session.process 208 仅有效 semantic 才调用 execution。invalid JSON、privacy fallback不会进入清理。resetSession 440 也只清 semanticHistory，未清 pending；close 清history，pending依对象销毁。
- 复现：生成合法修改预览 -> 换话题为严重症状/不要记录/故意无效 JSON -> 再回复确认。预期旧修改失效；实际代码仍可 commit。
- 必要修复范围：session.ts（统一回合边界/重置清理）、semanticExecution.ts（安全回合清理）、semantic-runtime 或独立 regression tests；不要降低安全医疗门槛。
- 状态 FAIL（静态确定，动态待复现）。

SEM-02 [P1/P2] 合规第一层 records 查询不会读取记录。
- 根因：semanticRouter.ts SYSTEM 94 要求 suggested_tool=null、tool_requests=[]；semanticExecution.ts 194-196 仅处理这些字段里的工具；records route/intents无业务工具选择，最终 247 回复“尚未执行”。现测试 91-147 使用旧模型工具提案，掩盖新 prompt 路径。
- 复现：输入查看我的训练计划，第一层返回 records/plan_query 且工具数组为空 -> 不读 Host。
- 必要修复范围：semanticExecution.ts 或现有业务读取选择器，根据任务语义做第二阶段选择，并保留 canUseModuleTools 和 readRehabReceipt 身份/来源校验；semantic-runtime regression覆盖 plan/history/assessment，混合聊天查询以及不授权。
- 状态 FAIL（静态确定）。

SEM-03 [P1] ProductService 构造参数漂移导致 Android/host wiring 回归。
- ProductService.ts 62-64：第 8 参数 conversationModel，第 9 rehabOperations，第 10 runtimeOptions。
- tests/semantic-host-wiring.test.cjs 14-17 以及 android_offline/web/local-api.js 10 把 runtimeOptions 传到第 9，this.rehabOperations?.(owner) 会 TypeError；host test parsed fixture 9 缺 events/relations，不符合 schema。
- 必要范围：全部 new ProductService 调用点检索；仅补 undefined/真实 operation factory，更新 mock fixture events/relations，不放宽 schema。该项由主agent协调 Android 覆盖避免冲突。
- 状态 FAIL（静态确定）。

SEM-04 [P1] privacy 边界不一致（已通知康复审计）。
- semanticExecution.ts 243-246个人读取留本地，但 programOperations.buildPlan 171-190把raw tool_results送模型；preview 211+绕过readRehabReceipt读取与scope验证。没有独立个人储存资料外发 consent gate。workflow也应核查相同路径。必须与康复/Host审计合并，不能给模型发送真实资料验证。
- 状态 FAIL（静态外发路径），实际合成Host测试待验。

## 建议确定性命令

在 ankang/route1-health-agent 中：npm test（全 TS）；npm run test:product（真 bridge + Mock fetch，不能称真实模型）；node --test .test-build/tests/semantic-router.test.js .test-build/tests/semantic-runtime.test.js .test-build/tests/semantic-legacy.test.js .test-build/tests/scope-fallback.test.js .test-build/tests/conversation-runtime.test.js .test-build/tests/rehab-program-operations.test.js。

HealthKit adapter/bridge 测试可以证明导入接口；不能替代真实 Apple Watch/iPhone 授权、样本读取与助手咨询链路。

## 基线后定向修复与复测（2026-10-17）

- SEM-01：Session 在每回合路由前撤销非确认/取消消息及跨 conversationContext 的旧 proposal；解析失败、隐私 gate、临床安全结果、reset 同样清理。executeSemanticTurn 独立安全 early return 也清 pending。旧 pending 测试通过内部注入模拟历史待办；当前新增 NLP 写入因个人资料外发授权缺失被康复修复 fail-closed 阻断，不能声称该测试证明新自然语言操作写入闭环。
- SEM-02：records 分支以当前查询描述选择三类既有 Host read 工具；第一层仍输出空 tool_requests。保留原 canUseModuleTools 全句本人/否定/假设授权 gate、readRehabReceipt 本人/来源校验、结果本地渲染和外发隔离。真实业务 Host/数据库验证交由主审计，不把单元 Mock read 当数据库证据。
- SEM-03：schema 关系索引补 typeof number 收窄（原严格校验不变）；legacy/host-wiring fixtures 补 events/relations 与构造参数占位。Android 构造参数由主agent修复。
- 公共动作/指导问答恢复现有 catalogue/guidance -> grounded final model.reply -> isUserFacingSemanticReply 路径；个人进度分析继续本地只读。初次执行发现2个公共问答测试失败，已修复执行路径而未降低测试断言。
- 导航：仅 opt-in 时以 ProductAgent([]) 复用既有 open_module 白名单；ProductAgent 增加康复计划->康复模块映射及句末标点规范化。返回 turn.agent.navigation，由已有手机与桌面消费者导航。宿主测试证明真实 ProductService 返回 receipt；实际 UI截图/点击应由主审计补证。
- 混合意图：primary route=module/health 但含 rehab_question/program_operation 时同样先走康复分析，资料/审核不足禁止 preview/write，不能仅因主 route 不是 rehab 绕过。

测试结果：
1. npm run typecheck：PASS（修复后）。
2. npm run build:bridge：PASS；此构建供主审计真实模型与Host测试使用。
3. npm test：首次可执行后557/559，2失败为公共知识/指导没有final LLM；修复后559/559 PASS。再新增1项混合route回归后，Focused语义/schema/legacy/conversation/scope共83/83 PASS。最终全量计数由主agent重跑确定。
4. 五个 product cjs test文件：34/35；semantic-host-wiring四项均PASS（含正常/句末。导航），唯一失败为既有 localPlan(screeningConfirmed:false) 未拒绝（simple-rehab-assistant.test.cjs42），已移交康复agent修复共享入口。
5. git diff --check：PASS。

完整日志位于父工作区work/semantic-all-tests.txt、work/semantic-product-tests.txt。全部是SYNTHETIC/TEST或Mock fetch/Host，不包含真实个人健康数据。真实DeepSeek与真实Host证据由主agent另行报告。

剩余边界：个人健康/Watch数据辅助咨询仍未接通；语义上下文只在当前会话缓存用户原话，没有持久化可编辑多轮候选草案/条件对象；新增自然语言计划或日程写入因缺个人储存资料外发授权闭环被阻断；普通确认不能替代专业审核。未在本子任务运行真人患者数据、Apple硬件或实际患者UI。
