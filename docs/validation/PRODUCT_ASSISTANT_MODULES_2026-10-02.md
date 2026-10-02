# AI 康复管家模块化验收

分支 `codex/product-ui-v1`，基线 `08cee3671176cb46384b58d5666be91c54a841c7`。针对用户反馈“语音入口不明显、页面太复杂”，本轮先完成管家模块首页与独立子页面；首页/康复等进一步调整留待下一步。

沿用 [Fluent 设计系统](../plans/PRODUCT_UI_FLUENT_BASELINE_2026-10-02.md)、[PC 产品覆盖审阅](../plans/PRODUCT_UI_COVERAGE_REVIEW_2026-10-02.md)和[功能完成/按钮审计](PRODUCT_UI_FUNCTIONAL_COMPLETION_2026-10-02.md)。只改 Qt 页面组织和导航，不改 Agent、ProductService、训练算法、数据库、依赖或色系。

## 用户页面与实际动作

| 入口/页面 | 用户操作 | 实际动作与反馈 |
| --- | --- | --- |
| 管家首页 | 开始对话、语音交流、资料与图片、我的康复记录 | 四张整卡为原生 QCommandLinkButton，点击或键盘进入对应模块，显示真实能力与当前范围摘要 |
| 对话 | 历史、输入、发送、三个推荐问题、本轮不记录 | 原 `_send_chat` → ProductBackend → bridge → Runtime；成功/失败/pending 与隐私规则保留 |
| 输入区 | 添加资料、语音输入、查看参考资料 | 导航至模块；语音按钮带麦克风图标且入口可见，点击不开始假录音、不假装识别成功 |
| 资料与图片 | 上传资料/图片/视频、识别健康图片、查看健康档案 | 原 `_add_attachment` / `_parse_image` → `archive.save` / `image.parse`；成功后原流程进入健康档案。未配置识别时禁用；上传不自动作为模型上下文 |
| 语音交流 | 语音输入、朗读最近回复、停止语音、文字输入 | 原 `voice.input` / `voice.output` / `voice.cancel` 与确认保留；`extensions.status` 判定能力。当前桌面未接入服务，三项实际操作禁用并给出原因 |
| 康复记录与参考资料 | 用户数据范围、去康复页面、清空/新会话状态 | 复用原参考摘要和康复跳转；没有 reset-chat 接口，原新会话继续禁用，不用清除全部数据代替 |
| 各模块返回 | 返回上一模块或管家首页 | 显式导航历史；原聊天、输入、隐私控件只有一份，返回不丢草稿 |
| 全局问管家 | 侧栏、关闭、原用户及会话 | 原 dock / Ctrl+J 保留，打开/关闭不改变当前模块或页面；不自动注入页面上下文 |

一级导航仍为首页、AI 康复管家、康复、健康、用药、家庭、记录。通知/用户/设置及原康复工作区不变。本轮没有新增 Python package 或后台能力。

## 按钮契约与隔离

116 个已发布产品按钮 ID/文字/action target 保留，原侧栏发送额外纳入验收，共 117 个原控件。新增 **13 个纯页面导航控件**，总计 130 个标记按钮，全部有 clicked 连接，新增全部分类 B。见 [新增导航 CSV](PRODUCT_ASSISTANT_NAV_BUTTONS_2026-10-02.csv)，旧审计保留作历史证据。

切换 participant 仍执行原清空/异步范围核对：会话和草稿清除、模块返回首页、参考摘要重读。测试先真实保存前用户对话，再切换第二用户，确认新 snapshot 无前用户聊天，主对话和全局侧栏均无旧内容。空会话保留可理解的 empty state 提示。

private-turn 仍不支持语音写入，原入口阻止并提示使用文字输入；未改变录音隐私/确认规则。新增“语音输入”是进入状态页的导航入口，不能等同于录音能力已完成。

## 实际 Qt 截图

使用正式 ProductWindow、原 Runtime、真实 ProductBackend/Node bridge，临时 SYNTHETIC/TEST 用户、真实保存计划/药物/健康记录与基础对话。模型禁用，不读取正式用户数据、Key 或设备。截图来自 QWidget.grab，不是 Web/mock 图。

| 截图 | 说明 |
| --- | --- |
| [模块首页](images/product-assistant-modules/assistant.png) | 四个可点击入口，其余工具不堆在首屏 |
| [对话](images/product-assistant-modules/assistant-conversation.png) | 原聊天、推荐问题、输入与可见语音入口 |
| [语音状态](images/product-assistant-modules/assistant-voice.png) | 当前平台未接入、原操作禁用、能回文字输入 |
| [资料与图片](images/product-assistant-modules/assistant-materials.png) | 上传主操作、识别禁用与档案路径 |
| [参考资料](images/product-assistant-modules/assistant-reference.png) | 原用户数据范围和康复入口保留 |
| [1024 窄窗对话](images/product-assistant-modules/assistant-conversation-1024.png) | 发送与输入在首屏内 |
| [真实校验错误](images/product-assistant-modules/error.png) | ProductService 拒收无效指标，保留错误反馈；不是 ASR/网络实机测试 |

Windows 原生 Qt 1440×940 和 1024×768 客户区，实际系统 DPR 1.5。两个尺寸下首页及四个管家模块无横向溢出，四模块无需外层纵向滚动，对话发送在首屏。原康复工作区窄窗 2px 滚动兼容边界不变。

截图发现通用 QSS min-height 覆盖模块卡片程序尺寸，已用集中 module_minimum / spacing 别名修正；资料上传突出，档案查看后置。最新截图未见明显中文截断、输入挤压或左导航漂移。没有删除按钮/状态/提示以缩小布局。

全部 QA 图片/JSON 位于 ignored `qa-output/assistant-modules`，仅提交上述 TEST 图片及导航 CSV；临时数据库/运行输出不入 Git。复现工具：`tools/validate_product_visual.py --phase assistant-modules --width 1024 --height 768`，设置 `QT_QPA_PLATFORM=windows`、`QT_SCALE_FACTOR=1` 使用系统 DPI。

## 针对性回归

`test_product_assistant.py`（4）、`test_product_visual.py`（4）、`test_product_window.py`（9）、`test_product_completion.py`（8）：**25 项通过，73.42 秒**。

- 模块卡片键盘操作/返回、同一组件和草稿保留、真实 bridge 发送、全局侧栏关闭、语音未配置/隐私拒绝、participant 切换、资料到档案。
- 既有七条用户路径的软件闭环、药物/家庭/通知、原康复保存/报告/反馈与导航、重复提交、真实校验失败、禁用/确认。
- 原发布按钮契约、最小 1024×720 输入/发送可见、键盘焦点、浅/暗状态对比、主题切换不改数据/动作。

初次完整回归为 24 项通过/1 项布局断言失败，单独复验通过；原康复概览收起后的 Qt 嵌套布局有延迟事件，测试改为等待实际尺寸变化，原“工作区可视高度增加”断言完整保留，生产康复代码不改。最终完整 25 项通过。

没有连接实体麦克风/ASR/TTS、相机或外部平台，不宣称真实设备验收。真正的 Windows 录音/识别宿主接线仍待后续明确安排。

`git diff --check` 通过；无秘密、用户库、运行输出或依赖目录入提交。仅 commit/push UI 分支，不 merge main；stage1 引用/历史保留。到 AI 模块化为止，停止等待下一步。
