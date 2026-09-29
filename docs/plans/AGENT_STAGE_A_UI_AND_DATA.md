# A 阶段：结构化自述与定向更正（A2 / 0.24.0）

更新：2026-09-29。持续开发分支：`codex/rehab-agent-stage1`。本阶段提供可人工验收的最小完整闭环；不表示安康 Agent 全部完成。验收前不继续 B 阶段。

## 软件里的实际路径

打开原有“康复管家”弹窗 → 输入自述 → 查看原话解析 → 点击具体“确认保存” → 获得本机回执 → “查看自报记录”重开 → 选择具体记录确认撤回。

A2 的新自报需要先连接并同意使用 DeepSeek：仅本轮原话发送到受限抽取器，再由本机 validator 核对，明确确认后保存。已保存自报的查看/撤回不需要联网。一般聊天和康复查询继续复用原通道；结构化自报不进入后续可联网对话历史。未修改康复动作、评估、计划或摄像头算法。

未配置、模型服务失败或格式异常时明确说明结构化理解不可用，不回退症状词表。普通本地康复查询仍可用；校验失败会追问，不提供保存按钮。详见 [A2 验收](../validation/AGENT_STAGE_A2_2026-09-29.md)。

## 0.23.1 显示修补

普通无写入回合改为针对性主回答 + 简短人物/时间/自述标签；未保存回执和完整隐私说明默认折叠到“查看详细信息”。实际 saved/retracted/discarded/cancelled 回执、待确认原话及明确隐私请求仍突出显示。记录 ID/revision 保留在后台及详情中。五类语义与字段保持分开，只有 presentation 改变。

输入框 Return/Enter 每次只发送一次，事件不会继续触发 Dialog 默认按钮；静态和动态按钮均关闭默认属性，请求/写入中 Enter 不重入。详见 [0.23.1 验收记录](../validation/AGENT_STAGE_A_UI_2026-09-29.md)。

## 页面与接口（供共同做 UI）

保留现有 PySide6 `RehabAgentDialog`，没有新建 React 页面或另一套事项库。五类内容可以分别设计样式，但不能合并含义：

| 区域 | 后台字段 | 当前显示与操作规则 |
| --- | --- | --- |
| 主回答 | `main_text`（兼容旧字段 `text`）、`source_label`、`mode_label` | “康复管家”回答；顶部显示本机理解 / 模型模式。不要把它当执行回执 |
| 依据 | `understanding[]`、`evidence_summary`；原查询沿用 `local_text`、`evidence[]` | 自述默认用短标签显示人物、时间及肯否，完整解析可展开；原评估显示“本机记录与规则核对”。自述解析不是摄像头测量 |
| 自报 / 记录回执 | `receipt.status/text/record_id/revision/source_message_id`、`record_summary` | 实际写操作醒目显示；未保存/只读状态默认放详情；保存成功才有数据库版本与记录号 |
| 隐私与执行状态 | `privacy_status.network/family`、`privacy_notice`、`delivery_status` | 明确隐私请求醒目显示；联网抽取在详情标 `may_have_been_sent/not_shared`；本机查看/保存/撤回标 `not_sent/not_shared`；远程始终 `NOT_CONNECTED`。普通模型回合保守标为 `may_have_been_sent`，不假称未联网 |
| 待确认操作 | `proposed_actions[]` | 每项有 `id/label/summary/operation/requires_confirmation`。显示原话、通用 concept 与时间；按钮逐条确认，每页最多显示 4 项，可切换页面选择后面的记录，无需执行其他记录。原页面只读跳转仍使用 `actions[]` |

`receipt.status`：`not_saved`、`saved`、`retracted`、`discarded`、`cancelled`、`read`。错误通过原有 `error` 通道显示“本轮未完成”，不制造成功回执；失败后可以重新查看实际记录再操作。

`proposed_actions.operation` 仅 `save` / `retract`。UI 回传本机生成的不透明 action ID；不回传可任意修改的事实，也不能执行模型生成的命令。`cancel` 清除当前待确认项。新文字、清空、关闭或更换窗口使旧确认失效。

后台命令继续使用现有异步可选服务队列：

```text
rehab_agent(operation='turn', conversation_id, scope, text, request_id, history, config)
rehab_agent(operation='act', conversation_id, scope, action_id, request_id)
rehab_agent(operation='reset', conversation_id)
```

同一 conversation ID 绑定同一个用户 / 输入来源 / 使用情境。UI 与后台均检查范围，后台再核对记录 revision。一次确认只处理一个自报；重复、过期或其他窗口的 token 不能写入。写入处理中暂不允许关闭弹窗或清空，以便显示真实回执。

## 自报数据与摄像头事实分开

复用 `SilverStore` 的 `silver_support.sqlite3`，新增记录类别 `agent_self_report`，不增加数据库 schema 版本，不改临床数据库，不将自报写入原评估或训练反馈。

每条记录包含：

- `scope`：participant_id / source_kind / usage_context；来源情境保留，不能把 SYNTHETIC/TEST 当真人资料。
- `evidence_method=SELF_REPORTED`、`origin=AGENT_USER_STATEMENT`、`shared=false`。
- `claim`：`subject/time_scope/statement_type/concept/polarity/certainty/raw_text/evidence_span` 八个经本机校验的提取字段；另有本机生成的 ID、来源消息/完整原话、原始时间表达、可明确的事件日期、发生状态、接收时间、`extraction_version=grounded-statements-2`。新记录不含必需的 `symptom` 字段；旧记录只读兼容，撤回不改写旧 claim。
- `source_message_id`：对应本轮消息；一轮多条事实共享来源消息 ID，但各有独立记录 ID。
- `consent`：明确按钮、确认时间、action ID；即使文字里说“请记录”，仍须核对具体按钮。
- `status=ACTIVE/RETRACTED`、`revision`、`corrections[]`：撤回保留原 claim，追加更正消息 ID、已确认的更正原话/操作来源和时间；沿用 SilverStore 审计及乐观版本校验。

原银发家庭快照不会读取这个新类别，所以已有共享授权也不会自动泄露这些自报。A 阶段没有创建家庭请求、通知或第二套任务；“告诉家人”继续只导航到已有共享设置。

## 接纳与更正边界

生产自报路径已删除 `SYMPTOMS` 与 `parse_statements`，不按疾病或症状名单决定能否抽取。DeepSeek 只输出闭合 JSON schema，`statement_type` 为 symptom/event/feeling/other，未知表达可为 other。`concept` 必须是连续原话，保留程度词；`raw_text=evidence_span` 必须是包含人物、时间、肯否/条件的完整原文分句。模型不能生成来源、ID、日期、admissible、操作或回执。

本机检查字段集合/枚举/长度、完整分句、原文匹配、重复项、人物与时间、否定/假设/不确定、被省略的限定内容及 model 越权字段。不能把主体/时间藏进 concept，也不能只截出症状而丢掉“没有/如果/可能”。整个批次有一项校验失败就不生成保存操作；保存时再次从原话重新核对。

这是开放词汇抽取加保守语法校验，并非已证明支持任意口语或通用医学理解。人物/时间无法核对、复杂跨分句、省略、转述与条件歧义会追问。尤其 concept 内含“没/不/无”的肯定含义目前不做医学词汇例外（仅识别通用“…不好”质量表达，并仍检查其余否定）：如“我今天没胃口”需换说法，“我今天胃口不好”可待确认保存。过去日期仅解析已有明确时间锚点，不补猜。

只有明确本人、明确今天/现在或过去、肯定发生的陈述才可提出保存；家人、否定、假设、将来及未知人物/时间不入本人事实。过去事件保留 `past`，不能当成本人当前不适。未知历史日期保持 null，不补造具体日期；“昨天/前天”等按该回合本机日期解析。当前不适不构成诊断或训练许可。

“我刚才说错了”只找紧邻上一条文字消息的可接纳自述；更正文字包含上一条 concept 的原文时只选对应事实；否则逐条列出上一条可更正候选供选择，不跳过否定/家人/闲聊去撤回更早记录。多条候选必须逐条核对。较早自报通过“查看自报记录”按原话选中，当前展示最近 30 条（含撤回）。更正路径是撤回旧自报 → 用户重新陈述 → 再确认保存，不能直接把新值覆盖到旧记录，更不能改写摄像头评估。

对话最多临时显示最近 20 条；模型历史仍最多 6 轮且过滤自报与隐私回合。清空/关闭销毁临时对话、上句定位及待确认操作，已确认保存的本机自报保留。关闭后没有“刚才”记忆；可从查看记录开始。

## A2 模型接口与失败状态

`extract_statements(text, message_id, config, now=None, transport=None)` 仅发送 system 规则和本轮 user 原话，不附历史、数据库或旧自报。复用官方 HTTPS 地址白名单、用户同意、有限超时/响应长度及脱敏错误的现有通道。

`extraction_status=unavailable` 表示未配置/调用失败；`needs_clarification` 表示本机核对失败；均无新候选、无写入，并清除前一轮待确认令牌。空 statements 转回原对话通道，也不生成自报。既有七个页面字段保持完整。网络调用失败保守标 may_have_been_sent，不能说未发送；确认保存/撤回不再次发送模型。

## 未实现

B 阶段任务闭环、C 阶段个人状态与真正家庭协同、D 阶段语音和 Home Twin 仍待后续。没有真实远程通知或物品位置库，不能把本机保存说成家属收到，也不能生成房间位置或路线。本阶段自报尚不参与自动计划、临床判断或个人状态推断。
