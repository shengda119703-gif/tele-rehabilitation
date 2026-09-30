# A 阶段 UI 与数据合同（A3 / 0.25.0）

更新：2026-09-30。分支 `codex/rehab-agent-stage1`。本合同取代 A1/A2 对本机语义解析和单轮抽取的描述；停在 A3，真实 DeepSeek 和用户人工验收尚未完成。详见 [验收单](../validation/AGENT_STAGE_A3_2026-09-30.md)。

## 页面入口与五类显示

沿用原桌面启动器 → 主窗口右上角“康复管家” → “连接 DeepSeek”配置并授权 → 输入原话 → 核对解释与逐条确认 → 本机回执。“查看自报记录”是明确的本机 UI 命令，不需要模型，也不向模型发送已保存记录。保留 PySide6 弹窗，没有 React 新前端或整套重设计。

| 区域 | 字段 | 显示规则 |
| --- | --- | --- |
| 主回答 | `main_text`、兼容 `text`、`source_label`、`mode_label` | 模型语义解释不是临床结论；缺人物/时间分别追问对应项 |
| 依据 | `understanding[]`、`evidence_summary`；原查询的 `local_text/evidence[]` | 默认短标签；保留完整原话、命题、模型解释、关系与来源；与摄像头依据分开 |
| 记录回执 | `receipt.status/text/record_id/revision/source_message_id`、`record_summary` | saved/retracted/discarded/cancelled 醒目显示；未保存默认折叠；ID/revision 留在回执详情和记录列表 |
| 隐私与送达 | `privacy_status`、`privacy_notice`、`delivery_status` | 明确隐私请求突出；普通回合详情说明本轮及有限近期上下文可能已发送；本机保存/撤回不再联网；远程仍 NOT_CONNECTED |
| 待确认操作 | `proposed_actions[]` | 每项 `id/label/summary/operation/requires_confirmation`；显示命题与时间、完整原话和关联原话；逐条确认；每页最多 4 项 |

Return/Enter 消费事件、关闭按钮默认行为、请求/写入忙碌门禁沿用 0.23.1 修复。点击确认只回传本机不透明 token，不能回传修改后的事实或模型命令。新输入会清除旧候选；取消只清除待确认，不删除保存历史。写入期间通常阻止关闭/清空以展示真实回执；scope 变化强制失效 UI 上下文，已派发的确认仍受原 scope 约束。

## 三层职责

`agent_extraction.interpret(turn, state, config, transport=None)` 调用 DeepSeek，负责全部自报自然语言语义判断。`agent_grounding.validate_interpretation(payload, turn, state)` 只做机械核验。`agent_statements.StatementSession` 根据已核验枚举决定是否能提供本机候选，并执行显式确认后的操作。

已删除旧 `SYMPTOMS/parse_statements` 路径（A2 删除），A3 进一步删除 FAMILY、TIMES、HYPOTHETICAL、UNCERTAIN、MENTION、NEGATION、`_dimensions()`、旧 `validate_statements()`、`revalidate_claim()` 与 CORRECTION 更正路由。不保留兼容调用来重判中文。未知词无需本机注册。

已有 `parse_privacy_intent` 保留为联网前隐私否决，不决定自报人物、时间、肯否或关系。原康复只读查询与安全业务规则继续保留；本轮不替换康复规则引擎。

## Semantic Interpreter 输出 schema

所有对象拒绝 schema 之外字段。顶层为 `dialogue_act` 和最多 8 条 `statements`；问答/请求/闲聊输出空列表，不生成自报。

```text
dialogue_act: new_report | follow_up | state_change | correction |
              question | request | chat | clarification
statements[]:
  raw_text: 本轮完整输入，逐字相等
  evidence_span: 本轮输入中的连续引用
  subject: {value: self|family|other|unknown, source: SOURCE|null}
  time_reference: {value: current|past|future|unknown, source: SOURCE|null}
  proposition: {text: 连续原话引用, polarity: affirmed|negated|hypothetical,
                source: SOURCE}
  certainty: certain|uncertain
  context_refs: [{kind: message|event, id: 已提供且未失效的 ID}]
  relation: {type: none|elaborates|updates|corrects,
             target: null|{kind: event, id: ID}|{kind: statement, id: 更早条目索引}}

SOURCE: {kind: current|message|event, id: "current"|真实 ID, quote: 连续原话}
```

subject/time 的 unknown 可无 source；非 unknown 必须有引用。proposition.text 必须等于 source.quote。引用旧消息/事件必须同时列于 context_refs。同轮条目关系只准向前引用已验证条目，不允许前向或循环。correction 只能指向已存在 event，不使用同轮索引。

本机追加 `id/source_message_id/reported_at/conversation_id/interpretation_version=semantic-interpreter-3`，将 relation 解析成 `{type,target_event_id}`，保留 `context_evidence` 与 `target_snapshot`。模型无权生成 ID、action、token、保存、通知、回执或版本号。raw_text 是权威来源；interpretation 是可供本人核对的模型解释，不是临床事实。不自动推断公历日期、病因、严重程度、诊断或健康数值。

## Grounding Validator：检查与非职责

检查精确字段集、枚举/类型/长度、重复项、当前原话相等、evidence 和 source 的逐字来源、context_ref 在本 conversation/scope 内存在且仍有效。检查继承事件的 subject/time 枚举与已验证值一致、关系目标存在、dialogue_act 与关系类型相容。命题必须逐字引用当前或有效上下文，不能添加无来源的疾病、数字或限定文字。

它不分析中文、不根据否定词/时间词/亲属词重算语义，不做医学诊断或语义蕴涵证明。若模型把真实引用配上错误标签，机械核验无法证明该标签正确；原话及解释必须供用户核对，真实服务质量须另行验收。该限制不能靠加入表达特判隐藏。

执行层另外检查 scope/conversation_id/epoch、opaque token、确认内容摘要、目标 revision 与 SELF_REPORTED 来源。没有明确按钮确认就不写库；版本冲突报错，不覆盖。模型不能直接调用 SilverStore。

## Conversation State 与关系

每个 scope/conversation_id 独立 `ConversationState`，最多 6 条近期用户消息和 12 个已核验解释事件，有 message/event ID、焦点及关系。事件随来源消息淘汰而失效。仅发送有界 packet；不会加载完整数据库、旧病史、临床行、action token 或用户标识到解释器。失败回合可留原话用于下一轮说明，但没有已核验事件。

清空/关闭、切换 participant_id/source_kind/usage_context、更换窗口或后台会话淘汰时，清除 pending、事件、焦点、消息并更新 epoch。旧引用与 token 无效。已保存数据不删；重新打开可以本机查看/撤回，旧记录不会自动注入模型上下文。已撤回或 revision 改变的事件在后续调用前失效。

| dialogue_act / relation | 操作政策 |
| --- | --- |
| new_report / none | 本人、明确 current/past、certain、affirmed 才提议保存 |
| follow_up / elaborates | 有效引用补充内容，同样逐条确认保存 |
| clarification / none 或 elaborates | 仅满足保存政策才给按钮 |
| state_change / 至少一条 updates | 新增后续状态，绝不撤回旧事件；明确的 negated 后续状态也可保存，保留 polarity，不变成本人当前不适 |
| correction / corrects | 明确引用可撤回的本人自报，certain 且非 hypothetical 才提议撤回；确认后保留原 claim，追加审计 |

家人、未知人物/时间、future、uncertain、hypothetical 不写成本人当前不适。普通 negated 新自述不按不适保存。过去保存为 past。更正未保存事件得到 discarded 回执，不虚构数据库变更。若后续状态指向尚未保存的上下文事件，保留事件 ID 和原话快照；该 ID 不冒充已存在数据库行。

## 持久化与旧记录兼容

继续 SilverStore 的 `agent_self_report`，无 schema 迁移；SELF_REPORTED / AGENT_USER_STATEMENT，shared=false、remote_delivery=NOT_CONNECTED。记录含 claim、source_message_id、relations、consent（明确按钮/时间/token）、ACTIVE/RETRACTED、revision、corrections[]；引用快照保留来源以供审计。

新数据围绕 raw_text、reported_at、dialogue_act、subject、time_reference、proposition、certainty、context_refs、interpretation_version。UI 不要求 symptom/concept。旧 A1 symptom 和 A2 concept 仅用于只读兼容展示；撤回复制原 claim、不重新解析、不转换旧语义，仅更新 status/revision 并追加更正审计。自报不进入摄像头/临床库、处方或自动计划；原银发家庭快照不读取此类别。

后台队列接口保留并新增显式 list：

```text
rehab_agent(operation='turn', conversation_id, scope, text, request_id, history, config)
rehab_agent(operation='list', conversation_id, scope, request_id)
rehab_agent(operation='act', conversation_id, scope, action_id, request_id)
rehab_agent(operation='reset', conversation_id)
```

## 失败与边界

未配置/服务失败/JSON 解析失败：`extraction_status=unavailable`。schema/引用核验失败：`needs_clarification`。均无新保存或撤回候选，清除上一轮待确认；提示结构化理解暂不可用或重新说明。普通本地康复查询仍可用，不回退旧医疗词表。模型调用一旦尝试，隐私保守标 may_have_been_sent；本机 list/act 标 not_sent，家属始终 not_shared。

本轮没有 B 任务闭环、真实家属发送、语音、Person Twin 或 Home Twin；没有真实物品库就未知。不把本机保存当送达，不把状态改善当临床康复进步。
