# A3 架构替换验收 · 0.25.0

日期：2026-09-30。开始时分支 `codex/rehab-agent-stage1`，HEAD 与 origin 同为 `ac1642c833e41bfd33e26533971757594f988aec`（0.24.0），工作区干净。本次停在 A3，不进入 B，不合并 main。最终提交 SHA 以交付消息和远端核对结果为准。

## 完成与删除

- 完全重写 `app/agent_extraction.py`：单轮词汇抽取改为有界上下文 Semantic Interpreter；闭合 JSON 输出，拒绝重复字段，复用 DeepSeek 官方地址/授权/超时/错误脱敏通道。
- 重写 `app/agent_statements.py`：移除本机语义路由和重解析，改为已核验解释驱动的候选/确认执行。删除 FAMILY、TIMES、HYPOTHETICAL、UNCERTAIN、MENTION、NEGATION、`_dimensions()`、`validate_statements()`、`revalidate_claim()` 和 CORRECTION 正则；不再提供这些兼容生产路径。
- 新增 `app/agent_grounding.py`（机械引用核验）、`app/agent_state.py`（6 条用户消息 / 12 个解释事件、焦点、epoch）。A2 已删除的 SYMPTOMS/parse_statements 不回归。
- 复用 conversation_id、scope、opaque action token、逐条明确确认、revision/乐观并发、SilverStore、SELF_REPORTED 隔离、撤回审计与 receipt；增加封存候选内容校验和关系目标版本校验。
- 原联网前隐私否决、康复只读业务规则保留，不承担自报中文语义理解。测试中的中文例句只用于显式模型 fixture；生产没有新增医疗词表或更正/改善表达分支。

完整 schema、Validator 检查/非职责、状态生命周期和 UI 接口见 [A3 数据合同](../plans/AGENT_STAGE_A_UI_AND_DATA.md)。模型输出 dialogue_act、raw_text、subject、time_reference、proposition、certainty、context_refs、relation 和 evidence_span；本机添加报告时间/ID/版本。命题只许原话引用，raw_text 权威，解释不是临床事实。

correction → corrects → 对明确引用的旧 SELF_REPORTED 逐条确认撤回；旧 claim 保留，追加 corrections 审计。state_change → updates → 新建后续状态，旧记录和原 revision 不变。后续状态可记录症状否定，但不能改成肯定不适或撤回历史。同轮先前/当前两条可建立向前索引关系。旧 A1/A2 数据无迁移，可用本机记录列表读/撤回，claim 不改写。

## 自动回归：212 passed

最终执行：212 项通过，22.78 秒。首次新增 A3 测试先因缺失新模块失败，再接入实现；最终覆盖 14 个测试文件。使用项目既有隔离 Python，禁用自动加载第三方 pytest 插件，Qt offscreen，无真实摄像头或个人数据库。沙箱不能完整读取隔离环境依赖，因此实际成功运行使用同一环境的授权执行。

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONIOENCODING='utf-8'
& '..\..\.agent-test-env\Scripts\python.exe' -m pytest -p no:cacheprovider tests/test_agent_a3.py tests/test_agent_extraction.py tests/test_agent_statements.py tests/test_agent_statements_runtime.py tests/test_agent_statements_ui.py tests/test_agent_dialog_interaction_ui.py tests/test_agent_conversation.py tests/test_agent_conversation_ui.py tests/test_rehab_agent.py tests/test_rehab_agent_ui.py tests/test_rehab_agent_runtime.py tests/test_silver_support.py tests/test_silver_ui.py tests/test_product_navigation.py -q
```

从应用目录执行。新增/迁移测试不是声称 fake 模型能证明 DeepSeek 的真实泛化：同语义多表述由显式注入的模型标签驱动，用于证明生产没有词面特判、关系和执行政策稳定。

| 覆盖 | 验证结果 |
| --- | --- |
| 开放表达及多语言/任意命题 | 不依赖症状词表；字面引用支持即可进入结构化核验 |
| 更正/状态变化语义等价类 | 多种表述对应相同 dialogue_act/relation；变化不撤回，指定更正才提议撤回 |
| 40 组生成文本不变量 | 没有确认数据库不变；上下文始终有界 |
| schema/凭空诊断/额外 action/重复字段/过深或错误 JSON | 拒绝或不可用，无候选、无写入 |
| 引用不存在、已失效、清空、跨窗口、跨人/来源/情境 | 拒绝旧引用与 token；真实 runtime 队列验证同 ID reset 与 scope mismatch |
| 未确认、取消、token 篡改、UI 返回对象篡改、revision 冲突 | 不覆盖、不越权；失败回执不伪造成功 |
| A1/A2 原始记录读取和撤回 | 不改旧 claim；审计保留；原临床库未被改写 |
| 本机只读/无配置/隐私/旧康复与银发 UI 回归 | 仍可用；不回退自报词表；隐私请求无远程送达声明 |
| Qt Return/Enter 与 scope 切换 | 真正 QTest.keyClick；连续三轮窗口可见、一次一发、忙碌不重入；切换 scope 清除窗口记忆 |

## Qt offscreen QA：16 个场景通过

`scripts/qa_agent_statements.py` 使用合成模型响应、临时 SilverStore、真实原生 QWidget/按钮/按键。不是实时 DeepSeek 验收。最终运行输出 `PASS: 16 native screenshots`。

本机截图：`C:\Users\Sophie\SynologyDrive\大学\学习\比赛+课题\康复\.runtime\a3\screenshots`。截图/合成测试库不上传 Git。已检查开放表达、后续状态、定向更正和历史显示，无另建空页面。

场景：家人/否定/时间未知三轮 Enter；开放表达待确认；保存旧事件；状态变化提议并保存，断言旧记录完全不变；更正提议并撤回旧事件，断言新后续事件仍 ACTIVE；清空后旧引用失效；不记录/告诉家人；无模型；读取关系与撤回历史。

```powershell
& '..\..\.agent-test-env\Scripts\python.exe' scripts/qa_agent_statements.py --output '<本机忽略目录>'
```

## 真实 DeepSeek 与用户人工验收：未完成

已提供 `scripts/qa_agent_semantics_live.py --live`，使用合成文字、每组独立 conversation，不写数据库、不打开摄像头。三组语义各三种表述，核对实际 dialogue_act/关系；更正和状态变化的前置事件也由真实服务解释。只有指定 --live 且本机配置 DEEPSEEK_API_KEY 才调用真实服务；报告不含 Key 或服务原始响应。

本次已尝试启动 live 验收，环境未配置 DEEPSEEK_API_KEY，脚本明确 NOT RUN，未发请求。没有读取或上传 UI 保存的个人密钥，也没有把 fixture 测试说成服务已联通。请在应用原“连接 DeepSeek”入口本机填写配置并授权；不需要把 Key 发到聊天里。

人工路径仍为原桌面快捷方式或仓库根 `打开康复管家.cmd`。重启后核对 0.25.0 → 主窗口右上角“康复管家”。建议使用专门测试用户，不修改真实临床资料。模型可能输出不合规 schema，届时应追问/不可用而非生成保存按钮；实际质量不足时留在 A3 修正模型协议，不加中文例句分支。

| 人工输入/操作（均为合成验收文字） | 应看到的结果 |
| --- | --- |
| 昨天妈妈头晕；妈妈今天发烧 | family/past 或 current，无本人保存按钮 |
| 我今天没头晕；我今天没有咳嗽 | negated，不当不适保存 |
| 我头晕 | 时间 unknown，只追问时间 |
| 我今天发烧；我今天咳嗽；我今天睡不好；我今天没胃口；我今天心情差；我今天头有点沉 | 忠实命题、时间和原话；没有确认不写入，不新增诊断/病因 |
| 我昨天摔了一跤；如果明天发烧 | 前者 past 可逐条确认；后者 hypothetical/future 不保存为已发生 |
| 我今天头晕，我今天腿疼 | 独立候选逐条确认，保存一条不连带保存另一条 |
| 保存“我刚才发烧”后说“现在已经好了”及其同义表达 | state_change/updates，新后续状态确认，旧记录仍有效 |
| 对上述旧记录说“我刚才说错了，其实没有发烧”及其同义表达 | correction/corrects，核对关联原话后单独确认撤回，不能误撤另一个事件 |
| 清空/关闭重开后引用“刚才” | 旧 ref 不可用，不跳到旧数据库记录；可通过查看记录显式选择 |
| 连续三轮 Enter，保存/撤回后再次 Enter | 窗口不关闭，一次一发；写入忙碌不重复 |
| 不要记录，我今天头晕；告诉家人我今天头晕 | 隐私提示清楚；不自动保存；后者仅共享设置导航，未发送 |

## 交付范围和仍缺什么

代码改动：agent_extraction、agent_statements、新增 agent_grounding/agent_state、runtime 会话生命周期、rehab_agent/main_window 必需 UI 接线与版本；新增 live QA、更新离屏 QA 和相关测试。交接、迁移计划、数据合同、变更记录及本验收单同步更新。

机械 Validator 不能证明标签的语义蕴涵正确；真正的理解质量、延迟、费用及多轮真实服务行为尚待上表人工验收。这是当前明确未完成项，不能宣称“安康 Agent 全部完成”。B 任务闭环、个人状态、真实家属通知、语音、Home Twin 均未实现；未修改康复动作算法、训练执行或摄像头权限。等待用户验收，不继续下一阶段。
