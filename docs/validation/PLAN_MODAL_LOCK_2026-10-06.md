# 计划页面导致 Windows 主窗口不可操作：诊断与修复

2026-10-06，分支 `codex/product-ui-v1`。用户报告生成计划页面无法操作且标题栏无法关闭。此前把 Windows Responding=True 当作没有卡住，判断不成立。

## 现场与原因

现场 pythonw PID 19636：主线程处于 `app.exec()`，Runtime、SQLite、vision、product 后台线程处于正常等待；未见 AI 推理、相机或数据库占用 UI 线程的证据。只读取线程栈，不导出局部变量或患者数据。user32.IsWindowEnabled 对主窗口返回 False，说明 Windows 禁用了该窗口的输入。Responding=True 仅表示消息循环仍运行。

旧 MainWindow 先以 WindowModal 显示 AutomaticPlanDialog / PlanLibraryDialog，产品五页界面随后直接将可见对话框改为 NonModal、Widget 并重新挂到康复页。窗口形态改变时父窗口仍保留原生模态锁；activeModalWidget 已为空，却未收到 WindowUnblocked。于是内容仍可渲染，但鼠标及标题栏关闭不起作用。

隔离原生 Windows 窗口复现：原顺序收到 WindowBlocked，主窗口 native_enabled=False，程序化返回后仍 False；先隐藏对话框再改变形态，收到 WindowBlocked 和 WindowUnblocked，主窗口 native_enabled=True，返回后仍 True。官方 [QWidget.windowModality 文档](https://doc.qt.io/qt-6/qwidget.html#windowModality-prop) 要求可见窗口更改模态属性时先隐藏再显示。

## 修改

`ProductExperience._embed_plan_dialog` 在改变 modality / flags / parent 前执行 `dialog.hide()`。先释放旧模态窗口的父锁，再作为页内组件显示。原独立模态入口保留；不全局关闭模态、不修改医疗门禁、Runtime、API、数据结构或保存/退出保护。

新增原生 Windows 回归，覆盖两类计划对话框各两次打开/返回，直接断言 IsWindowEnabled、activeModalWidget 和成对 WindowBlocked / WindowUnblocked。offscreen 平台明确跳过，不能冒充 Windows 输入验收。

原真实 Runtime 验收工具增加两类编辑页及返回后的原生输入检查，并通过正式关闭请求等待 shutdown_done / 窗口隐藏 / Runtime 线程退出；成功路径不使用 _allow_close 测试绕过。

## 本轮结果

- `QT_QPA_PLATFORM=windows python -m pytest tests/test_product_plan_modality.py -q -x`：2 passed，7.79 秒。
- `python tools/validate_plan_experience.py`：1440/1024 宽、浅/深色四组全部 PASS；真实 Runtime 保存计划、日期安排、无有效评估生成页、返回、正常退出及线程结束通过。使用隔离 TEST 档案和 SYNTHETIC / TEST 来源，未打开真人相机或读取用户数据库。
- 生成 12 张原生窗口截图，实际查看 1440 浅色无评估页面，布局与用户报障页面一致；本轮只修窗口生命周期，不重做视觉。
- 新增测试初稿失败：PassiveRuntime 无命令回执且父页面恢复 enabled 比 busy 清零晚一轮。修正测试发送模拟 command_done 并等待控件可用后通过；没有因此修改业务逻辑。四组真实 Runtime 本轮首次运行即通过。
- `git diff --check` 通过。没有修改 Node/bridge，本轮没有重新运行其 build 或整个历史测试全集。此前 build 记录不作为本轮新结果。

## 为什么原验收漏掉

程序化 QPushButton.click() / 直接调用方法绕过原生输入入口；截图、无横向溢出、主循环 Responding=True 也无法证明窗口可供用户操作。之前四组流程只验证了业务回执，没有断言原生 enabled。本轮补齐这一层。不能宣称此前窗口可操作验收已覆盖此问题。

## 旧进程与入口

修复不会热更新现场 PID 19636。诊断期间保留旧窗口和用户资料，未强制终止。用户可通过任务管理器“详细信息”按 PID 定位该旧 pythonw 进程结束后，再从桌面 `安康康复（最新版本）.lnk` 启动；强制结束会丢失未保存的界面草稿。快捷方式提交后更新版本描述。未对所有其他旧模态窗口组合做穷尽证明。

诊断工具 py-spy 0.4.2 来自官方 PyPI，仅安装在现有本机隔离 Python 环境，不加入产品依赖。
