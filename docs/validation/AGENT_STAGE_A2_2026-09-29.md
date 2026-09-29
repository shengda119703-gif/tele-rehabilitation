# A2 开放词汇自报抽取验收 · 0.24.0

日期：2026-09-29。基线：本地与远端一致的 `26456590fa6f40299e565e804da07ca55e6c469a`（0.23.1），开始时工作区干净。持续分支 `codex/rehab-agent-stage1`；停在 A2，不进入 B，不合并 main。

## 实际做成的闭环

连接并授权 DeepSeek → 本轮原话受限抽取 → 本机验证完整引用和语义维度 → 展示通用自述及逐条待确认按钮 → 明确确认 → SilverStore 本机保存与真实回执 → 查看原自报 / 选择更正 → 确认撤回并保留审计。

这次删除了 `app/agent_statements.py` 的 `SYMPTOMS` 常量、`parse_statements` 函数及其症状匹配/肯否例外、词表驱动更正定位。没有增加发烧/咳嗽等医学关键词例外。`app/rehab_agent.py` 原有只读康复安全提醒的有界意图规则没有修改，不能生成结构化自报或写库；不把它当成模型失败后的自报理解回退。

新增 `app/agent_extraction.py`：模型只能返回 subject/time_scope/statement_type/concept/polarity/certainty/raw_text/evidence_span 八个字段；未知表达可用 other。所有 concept 必须逐字来自完整原文分句，程度、条件、否定等不能被裁掉。subject/time_scope/肯否/假设/不确定由本机语法重新核对，未覆盖或冲突时拒绝保存候选。额外字段、编造医学概念、残缺 evidence、重复候选、超长或过多内容均拒绝。保存前重新验证原话，不只信缓存 admissible。

## 保留的安全机制

- 确认按钮与不可伪造的当前会话 action token；新回合、清空、关闭令旧候选失效，模型失败同样使旧 token 失效。
- scope 绑定及跨用户/来源/情境隔离；revision 冲突拒绝，不覆盖并发更新。
- SilverStore 原有事务与审计；SELF_REPORTED / AGENT_USER_STATEMENT、来源消息、原话、明确同意及回执。
- 撤回仅作用于选中的自报，旧 claim 不改写，追加 correction 与 revision；临床评估和摄像头数据未修改。
- 旧 symptom 记录兼容读取/撤回，不迁移或伪补新提取字段；新记录不要求 symptom。
- 隐私门禁优先：不记录、不告诉家人、告诉家人仍不调用模型。告诉家人只导航已有共享设置，NOT_CONNECTED 不变。
- 原 Enter/Return 事件消费、非默认按钮、连续输入、请求/写入防重入与关闭门禁保持。

## 模型与失败处理

抽取只发送 system 规则与本轮 user 原话，不附对话历史、已保存自报、原始数据库或摄像头画面。复用现有 DeepSeek 官方 HTTPS、配置同意、超时、响应长度限制与脱敏错误；API Key 仅在现有运行内存配置中。

未配置、服务异常、超时或非法 JSON：主回复明确“结构化自报理解暂不可用”，无候选、无写入；不会偷偷走旧症状表。普通本地康复查询继续可用，真实查询结果仍可显示。引用/字段/维度核对失败：明确追问，无候选。空 statements 回到普通对话通道，不创建自报。

调用失败也可能已经发送本轮文字，privacy_status.network 保守标 may_have_been_sent；未配置、隐私保护与本机查看/确认保存/撤回标 not_sent。family 始终 not_shared。所有结构化回合 shareable=false，不加入后续可发送的聊天历史。

## UI 实际变化

仍是现有 PySide6 弹窗，主回答、短标签、待确认原话、真实保存/撤回回执、详情折叠保持。新记录与按钮使用通用 concept，否定表达主回答直接引用原话，避免机械拼成“没有没胃口”。顶部和连接说明明确“DeepSeek 抽取 · 本机核对”及不可用状态；不再把联网抽取标成“本机结构化 · 未联网”。七个数据合同字段未删除。没有新页面、React、任务执行或第二套共享能力。

## 本次验证

- 相关回归 **243 项通过，21.18 秒**。最后只调整 Runtime 失败回合的重复显示后，补跑相关 Runtime **3 项通过，1.29 秒**（属于上述集合，不能叠加成 246 项）。
- Qt offscreen QA **23 个截图场景通过**：连续三轮真实 QTest Return、不关闭/不重发、确认保存、定向撤回、隐私，以及开放词汇和未配置状态。检查了开放自述、歧义追问、未配置页面的原生截图，无遮挡或假回执。
- 测试模型响应为明确标注的合成 provider fixtures；使用真实 validator、Runtime 队列、临时 SilverStore 和 Qt 控件。不是旧词表模拟生产理解，也不表示真实 DeepSeek 语义质量已经实测。
- 没有使用真人资料、个人数据库或真实 API Key，没有联网调用模型或打开摄像头。未进行真人/真实 DeepSeek 人工验收。

在应用目录运行：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -p no:cacheprovider tests/test_agent_extraction.py tests/test_agent_statements.py tests/test_agent_statements_runtime.py tests/test_agent_statements_ui.py tests/test_agent_dialog_interaction_ui.py tests/test_agent_conversation.py tests/test_agent_conversation_ui.py tests/test_rehab_agent.py tests/test_rehab_agent_ui.py tests/test_rehab_agent_runtime.py tests/test_silver_support.py tests/test_silver_ui.py tests/test_product_navigation.py -q
python scripts/qa_agent_statements.py --output <本机验收输出目录>
```

本机使用现有 `.agent-test-env`。截图与临时工作脚本放在用户新“康复”目录的 `.runtime/a2/` 及 `.runtime/a2-*.py`，不进入 Git。

## 人工验收单与准确的预期

先重启 0.24.0，用非真人测试文字；需要新增自报时在软件内连接 DeepSeek。测试后可撤回合成自报。不要用患者资料做联网验收。

| 输入 / 操作 | 正确预期 |
| --- | --- |
| 我今天发烧 / 我今天咳嗽 | 模型提取并通过本机核对后出现待确认；点击前没有保存 |
| 我今天睡不好 / 我今天胃口不好 / 我今天睡得很差 | 忠实原文，无医学诊断，可使用 other 待确认 |
| 我今天心情差 / 我今天头有点沉 | 保留通用 concept 和程度，不能补病因或严重程度 |
| 我今天没胃口 | 当前本机对否定构词的语义仍保守：追问换说法，不提供保存按钮；“我今天胃口不好”可保存 |
| 昨天摔了一跤 | 主体未知，追问本人还是家人；不默认本人 |
| 我昨天摔了一跤 | 可待确认，保存为 past 并保留昨天日期，不能变为当前不适 |
| 妈妈今天发烧 | family，无本人保存按钮 |
| 如果明天发烧 | 假设/将来，且主体未明，无本人保存按钮 |
| 我今天没有咳嗽 | 否定，无不适保存按钮 |
| 我头有点沉 | 时间未明，只追问时间，不默认现在 |
| 我今天头晕，我今天腿疼 | 两个独立确认；保存一条不会自动保存另一条 |
| 我刚才说错了，没有头晕 | 只列出对应上一条自报供撤回，仍须逐条确认，不修改另一条或评估 |
| 连续三轮 Enter | 一轮一次发送、清空输入、窗口不关；回复后可继续 |
| 不要记录，我今天发烧 | 不联网、不保存，隐私说明醒目 |
| 告诉家人我今天发烧 | 未发送，只提供已有共享设置入口 |
| 断开模型后再自述 / 配错模型配置 | 明确不可用，无保存按钮；评估/计划/历史本机查询仍可用 |
| 保存后重开查看并撤回 | 同 scope 可见，清楚回执，revision 增加、原话/审计保留 |

## 已知限制与下一步

开放词汇不等于任意语法都能核对。当前 validator 保留通用人物、时间和否定/不确定性语法门槛；复杂跨分句、转述、复合时间、否定构词可能需要重新说完整句子，不跨轮擅自补人/时间。通用“…不好”质量表达可以接受，其他含没/不/无的肯定含义不按医学词汇设置例外。模型漏提取或误分类可能造成拒绝/追问，实际接受率尚需真实服务验收。

本阶段没有训练执行、康复算法修改、处方、临床进步判断、个人状态推断、语音、真实家属发送或 Home Twin。没有真实物品位置数据仍未知。用户验收 A2 后再决定下一步，不自动进入 B。

## 实际修改文件

应用：app/agent_extraction.py（新增）、app/agent_statements.py、app/runtime.py、app/ui/rehab_agent.py、app/__init__.py。

测试与 QA：tests/test_agent_extraction.py（新增）、tests/statement_fixtures.py（新增合成 provider 响应）、tests/test_agent_statements.py、tests/test_agent_statements_runtime.py、tests/test_agent_statements_ui.py、tests/test_agent_dialog_interaction_ui.py、scripts/qa_agent_statements.py。

文档：docs/HANDOFF.md、docs/history/CHANGELOG.md、docs/plans/ANKANG_AGENT_MIGRATION_AND_UI.md、docs/plans/AGENT_STAGE_A_UI_AND_DATA.md、两份历史 A 验收的版本提示，以及本 A2 验收单。
