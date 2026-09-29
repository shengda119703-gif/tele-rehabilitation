# A 阶段软件验证与人工验收单

后续 0.23.1 的 Enter 退出修复、精简显示与最新验证见 [UI 修补验收](AGENT_STAGE_A_UI_2026-09-29.md)；本页保留 0.23.0 后端闭环结果。

日期：2026-09-29；版本：0.23.0；分支：`codex/rehab-agent-stage1`。

## 起点与验证范围

实际目标目录为项目目录下的 `_ui_review_repo`，原安康目录 `_fdu_hackthon_review` 只读。开始时工作区干净，本地 HEAD 与远端分支均为 `fcbf65b850d54b656479eb5d6e50cf6b896fb2b6`（0.22.1）。HANDOFF 旧的“仅本机/尚未上传”表述不代表此基线状态。

使用已有 `.agent-test-env`，未安装依赖，未使用个人数据库或 API Key。首次 pytest 因用户环境自动注册的 xonsh 插件缺少控制台而未能启动；尝试禁止 user-site 后发现现有 pygments 位于该环境，亦未能启动。最终仅设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，保留已安装依赖；禁用 cacheprovider 避免旧缓存目录权限警告。以上启动失败不计为通过测试。

最终相关回归：**171 项通过，17.53 秒**。范围包括新结构化解析/事务/后台/UI，原 Agent 对话/查询/UI/运行时，银发存储与 UI，主导航、自动计划、训练与用户范围。未声称运行全仓库全部测试。

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:QT_QPA_PLATFORM='offscreen'
& '..\..\.agent-test-env\Scripts\python.exe' -m pytest -p no:cacheprovider `
  tests/test_agent_statements.py tests/test_agent_statements_runtime.py tests/test_agent_statements_ui.py `
  tests/test_agent_conversation.py tests/test_agent_conversation_ui.py `
  tests/test_rehab_agent.py tests/test_rehab_agent_ui.py tests/test_rehab_agent_runtime.py `
  tests/test_silver_support.py tests/test_silver_ui.py tests/test_product_navigation.py `
  tests/test_automatic_runtime.py tests/test_training_runtime.py tests/test_participant_runtime.py -q
```

`scripts/qa_agent_statements.py` 使用真正本机解析、SilverStore 与 PySide6 控件，在临时 SYNTHETIC/TEST 范围完成输入→确认→保存→定向撤回→重开，未调用模型或相机。输出 `qa-output/agent-statements/01-confirm.png` 至 `04-reopened.png`；显式加载本机中文字体后逐页检查，确认中文可读。修复了 Qt 延迟删除期间旧操作按钮仍显示的问题。截图和临时数据库不提交。

针对改动文件的 compileall 和 `git diff --check` 通过。文档检查共核对 195 个相对链接，0 个无效。

## 自动化已覆盖

- 本人/家人、现在/过去/将来、发生/否定/假设/不确定；问句、引述、恢复、混合时间、双重否定不直接接纳。
- 未确认无自报入库；明确按钮保存，有来源、日期、范围、同意信息和回执。
- 同一消息多症状只撤回被指明的一条；保留另一条及原始 claim、更正来源轨迹。
- 上一句无可接纳事实时，不回退撤回更早自报；取消、旧 token、重复确认和跨用户拒绝；翻页可直接选第五条，不必先撤回前四条。
- 存储异常不报成功；revision 冲突不覆盖；清空后无“刚才”记忆，但已保存自报可重开。
- 真实 Runtime 队列闭环后，原评估内容逐项相等、训练计划不变、相机未打开；未创建家庭请求和银发 feedback。
- 原有对话、导航、计划、银发功能相关回归保持通过。

## 请在软件中人工验收（尚未替用户验收）

用合适的测试用户/演示情境；不要为验收假装自己或家人真的不适。打开“康复管家”，这些自述操作不需要 DeepSeek Key。

| 步骤 | 输入/操作 | 应看到 |
| --- | --- | --- |
| 1 | 连续输入“昨天妈妈头晕”“我今天没头晕”“我刚才说错了” | 家人过去 / 本人否定分别显示；没有本人当前不适记录、没有保存或错误撤回 |
| 2 | 输入“我今天头晕，我今天腿疼” | 两条待确认自报，显示人物、时间和原话；尚未保存 |
| 3 | 点击“取消待确认操作”，再点“查看自报记录” | 没有本次新记录 |
| 4 | 重输步骤 2，逐条点“确认保存” | 每条获得“已保存到本机”回执与记录号，未分享家属 |
| 5 | 输入“我刚才说错了，没有头晕” | 只出现头晕的撤回确认，不自动改库；点确认后头晕已撤回，腿疼保留 |
| 6 | 清空/关闭后重新打开，查看自报记录 | 保存和撤回状态可重开；“刚才说错了”不借旧窗口记忆擅自撤回 |
| 7 | 输入“我昨天头晕”“如果我今天头晕”“我今天可能头晕”“头晕” | 只有明确本人过去事实可提出保存，过去不标当前；其余解释或追问，无保存按钮 |
| 8 | 输入“不记录，我今天头晕”“别告诉家人，我今天头晕”“告诉家人我今天头晕” | 隐私状态独立；无自报保存。第三句只提供既有共享设置入口，明确未发送 |
| 9 | 查看原评估/训练页面 | 原始评估与计划未被自报或更正改写 |

需要用户判断：人物/时间文案是否易懂；主回答、依据、回执、隐私、确认按钮是否清楚；长对话滚动是否方便。当前只完成原生最小界面，用户可据 [页面与数据合同](../plans/AGENT_STAGE_A_UI_AND_DATA.md) 继续参与 UI 设计。

## 尚未验收或未完成

没有真人准确度、真实硬件、真实 DeepSeek 新联通或远程送达验收。本阶段是有限自述闭环，不能宣称任意口语/健康数值都能自动提取。B～D 阶段任务、个人状态、语音、远程家庭协同和 Home Twin 未实现；在用户人工验收 A 后再继续。
