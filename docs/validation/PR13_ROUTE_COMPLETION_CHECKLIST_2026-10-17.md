# PR #13 统一语义分流：剩余闭环验收清单

状态：待独立复核；不得以代码提交或云端 CI 代替全链路 PASS。保持 Draft、默认关闭、不修改 main、不部署。

## 目标链路

用户输入 -> LLM 统一语义 JSON -> 原有安全处理 -> 程序路由
- chat：普通聊天
- health：一般健康咨询
- rehab：康复工具规划、知识/本人数据、规则算法、候选方案验证
- records/module：本人记录读取与已接通的应用操作
- other：超范围、未接通操作、临床升级提示

复合意图：rehab_question + program_operation -> 康复分析 -> 验证 -> 计划变更预览 -> 用户确认 -> 宿主真实回执。显式诊断/处方请求不得绕开现有安全及临床边界。

## 必须独立验证

1. TypeScript：`npm run ci`、`npm test`、`npm run test:product`，并单独运行全部 semantic、rehab-workflow、rehab-program-operations、scope-fallback 测试。
2. Python：`pytest rehab_codex_single_camera_v2_1/tests/test_rehab_operation_tools.py -q`，再运行原有宿主/数据库范围回归。
3. 真实 DeepSeek：验证五类路由、多意图、否定、跨轮澄清、隐私、证据及 JSON 格式。记录真实模型调用次数、模型标识与脱敏 trace。
4. 安全：胸痛等既有急症规则必须优先；不能将需要诊断/处方的请求直接转成执行计划；普通头晕/健康知识不应一律被转为医生建议。
5. 工具与个人数据：确认本人 scope、来源与 usage_context；个人数据不应绕过授权外发模型，读取失败不可补造回执。
6. 程序操作：preview 不得写数据；后续“确认”才 commit；取消/超时/离题应使 pending 失效；expected_revision 冲突必须拒绝；未接通操作不得声称成功；真实 SQLite 使用 SYNTHETIC/TEST 数据并检查前后变更范围。
7. UI：桌面、配对手机、Android 独立版与网页入口，分别明确 PASS/FAIL/UNVERIFIED；不得由 Node 模拟入口代替真机。
8. 验证结果应逐项标记 PASS/FAIL/UNVERIFIED，提供复现命令及证据；失败时不放宽权限或医疗规则来骗过测试。

## 目前的关键风险点

- 第一层 Johnson 的 `events`、`relations` 是新必需字段，旧 Mock/真实模型用例需要适配，不能凭以前的测试计数宣称兼容。
- 早期康复流程偏向“候选计划”，纯动作解释不应被误转为生成计划。
- 混合康复+程序操作应在原有安全判断、诊断边界、个人数据权限之后执行。
- 临床升级不是“已联系医生”；`other` 不是自动建议就医；超出功能范围与缺少知识库资料不是同一个问题。
- 一旦候选计划验证为 `needs_review`，不得仅因用户回复“好”就按正式训练处方采用。
- 未接通的预约/外部提醒/医生消息功能不能伪造成功。

## 当前验收边界

本文件与新增代码仅作为开发分支的目标实现。尚无本轮全量 TypeScript、Python、真实模型、GUI/真机验收回执。保留 Draft 和默认关闭。
