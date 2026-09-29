# A 阶段 UI / Enter 修补验收 · 0.23.1

日期：2026-09-29。分支：`codex/rehab-agent-stage1`。仅修补 A 阶段，未进入 B，未合并 main。

## 起点与真实根因

开始时本地 HEAD 与远端都是 `f0840fd0cfa03c25ad0c902bad40e04830dae80b`（0.23.0）。工作区已有两份被移至新“康复”文件夹的文档，以及上轮启动器 CRLF 修复的本机状态。两份新目录文档经比对与已提交版本一致；保留新目录文件，并恢复仓库中的版本管理副本与相对链接，没有丢弃用户内容。

在原版 `RehabAgentDialog` 上运行真实 `QTest.keyClick(input, Qt.Key_Return)`，用临时子类跟踪 `QDialog.keyPressEvent`，结果：

1. 初始所有 QPushButton 的 `autoDefault=True`，输入框有焦点。
2. QLineEdit 发出 `returnPressed`，调用 `ask()`，只发送一次并清空输入。
3. `ask()` 禁用输入、询问和其他快捷按钮；焦点转给仍可用的“返回原页面”，该按钮变为 `isDefault=True`。
4. 同一个 Return（16777220）继续传到 QDialog，触发该默认按钮的 `clicked`，随后发出 `finished(0)`；窗口 `isVisible=False`。

因此不是后端请求导致关闭，而是输入处理期间焦点/默认按钮变化，加上同一按键继续传播造成的误点击。此结论来自 Qt 事件实测。

修复：统一创建按钮时显式关闭 autoDefault/default（含设置、快捷入口、动态确认、翻页、返回）；输入框单独消费 Return/小键盘 Enter，忽略自动重复；Dialog 层吞掉残留 Enter，避免禁用输入期间按键触发导航或写入。回复后焦点回输入框。明确点击返回和正常关闭仍可使用，写入中仍保留原有关闭门禁。

## 显示变化与数据合同

后端仍提供 `main_text / understanding / evidence_summary / receipt / privacy_status / proposed_actions / delivery_status`；UI 保存完整原始结果，新增纯显示适配层，不改接纳或存储。

| 内容 | 默认显示 |
| --- | --- |
| 家人、否定、假设、不确定、人物/时间未知 | 根据已知维度作针对性回答；短灰色标签概括人物、时间、症状与肯否 |
| “我头晕” | 仅追问现在还是过去；不提供保存按钮 |
| 明确本人已发生自报 | 复述自述，逐条显示原话与确认按钮，仍不自动写入 |
| saved / retracted / discarded / cancelled | 明显显示真实操作回执；记录 ID / revision 默认移到详情 |
| 普通无写入回合 | 不再展开“未写入自报记录”或整段隐私说明 |
| 明确“不记录 / 不分享 / 告诉家人” | 隐私与送达说明继续突出显示；共享仅原设置入口 |
| 查看详细信息 | 展开原依据、完整回执、记录 ID / revision、隐私及送达状态；纯显示操作，无保存/分享副作用 |

有限规则仅负责已有语法；未知人物和时间不补猜。逐函数 AST 对比确认 `parse_statements`、`act`、`propose`、`result` 与基线 f0840fd 完全一致。

## 本次实际软件验证

最终相关回归 **182 项通过，31.68 秒**。新增 `test_agent_dialog_interaction_ui.py` 共 22 个测试用例（含参数化），涵盖：

- Return 与小键盘 Enter 连续三轮、每轮一次请求、输入清空、窗口不关。
- 同步和异步回复；故意把返回按钮设为默认按钮后的防误触。
- 请求中、写入中、空输入和自动重复按键不重发、不确认、不关闭。
- 所有静态/动态/设置按钮的默认属性；明确鼠标点击仍能返回。
- 针对性回复、未保存回合精简显示、详情展开、原数据不被 presentation 修改。
- 保存、撤回、取消、撤销未保存自述回执可见，敏感元数据默认不突出；明确隐私请求保持醒目。

首次专项运行有两处测试不匹配：旧测试仍要求每轮展开五大块；新增测试在窗口尚未处理显示事件时断言焦点。更新旧显示断言，并在新窗口处理 Qt 显示事件后检查焦点，最终全部通过；没有放宽业务断言。

在应用目录执行：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONIOENCODING='utf-8'
& '..\..\.agent-test-env\Scripts\python.exe' -m pytest -p no:cacheprovider `
  tests/test_agent_dialog_interaction_ui.py tests/test_agent_statements.py `
  tests/test_agent_statements_runtime.py tests/test_agent_statements_ui.py `
  tests/test_agent_conversation.py tests/test_agent_conversation_ui.py `
  tests/test_rehab_agent.py tests/test_rehab_agent_ui.py tests/test_rehab_agent_runtime.py `
  tests/test_silver_support.py tests/test_silver_ui.py tests/test_product_navigation.py -q
& '..\..\.agent-test-env\Scripts\python.exe' scripts/qa_agent_statements.py --output <本机验收输出目录>
```

Qt offscreen QA 使用真实控件、真实按键、延迟回调、临时 SilverStore，并输出 10 张原生截图，已逐页查看。所有数据属于 SYNTHETIC/TEST；未用真实 Key、个人数据库、摄像头或家庭通知。截图位于用户新“康复”目录的 `.runtime/a-ui-repair/screenshots`，不上传。针对改动文件的 compileall 与 `git diff --check` 通过。

## 用户人工复验（等待用户）

先关闭已打开的旧版窗口，再从桌面“康复管家验收版”启动，核对主窗口版本 0.23.1；不需要配置 DeepSeek 即可测试自报。

1. 在管家输入“昨天妈妈头晕”，按 Enter：只有一条发送，窗口保持，回答是妈妈昨天的情况，短标签“家人 · 昨天 · 头晕”。
2. 接着输入“我今天没头晕”，按 Enter：明确是否定，不记录成不适。
3. 接着输入“我头晕”，按 Enter：只追问现在/过去，没有保存按钮；连续三轮窗口不关闭。
4. 输入“我今天头晕”：出现单条确认；输入“我今天头晕，我今天腿疼”：出现两条独立确认。
5. 保存头晕那条：明确显示已保存到本机回执；点击详情能查记录号/版本。
6. 输入“我刚才说错了，没有头晕”，确认撤回：明确显示撤回回执，原评估不变。
7. 输入“不要记录，我今天头晕”：隐私说明突出、无保存按钮。
8. 输入“告诉家人我今天头晕”：明确未发送，仅提供既有家庭共享设置入口。
9. 请求/写入处理中连续 Enter 不重复执行；鼠标明确点击“返回原页面”仍可关闭。

仍待用户真实键盘/输入法人工验收。未进行真人临床、真实模型新联通或远程送达验收；B 阶段、训练执行扩展、Home Twin、语音和真实家属发送均未实现，本轮结束后停止等待反馈。
