# macOS 竖屏桌面入口

2026-11-17：修复桌面启动；桌面业务仍为 0.25.2，本地原生启动器 revision 2。2026-11-15 的 revision 1 仅验证过直接运行，缺少 LaunchServices 验收。

## 使用

双击桌面 **安康康复（竖屏版）.app**。默认内容区 430 × 860 逻辑像素，高度随当前屏幕缩小；最小 360 × 600，可拖动调整。底部导航为首页、康复、健康、用药、家人。首次使用复用原有建档表单；不生成演示患者，已有多个档案时明确选择本人。

竖屏入口复用 `mobile_rehab/static/unified.html` 和正式 `ProductBackend`，不重写规则、计划和存储。手机界面的“电脑端指引”仍保留原语义。需要原生实时评估及正式训练时，从 macOS 顶部菜单 **工作区 → 打开完整电脑端（实时评估与训练）** 切换。存在录像分析或实时指导时先结束当前任务。切换关闭本次本机服务、释放数据库锁后启动原 `app.main`；返回竖屏入口可关闭完整电脑端，再双击桌面图标。

程序安装在 `~/Applications/安康康复（竖屏版）.app`，桌面同名入口链接到该应用。运行文件位于 `~/Library/Application Support/AnkangPortrait/`，避免桌面启动时卡在访问文稿目录中的项目文件。数据位于该安装目录的 `rehab_codex_single_camera_v2_1/data/`，与安装后的完整电脑端共用。首次安装复制原档案并保留原件，后续安装不覆盖已经迁入的档案；仓库原数据目录与安装后的数据目录不自动同步。

两种窗口使用同一 `application.lock`，不可同时写同一档案。只监听 `127.0.0.1` 随机端口，不开启局域网共享；通过既有 `/api/pair` 获取绑定本人的 HttpOnly cookie，保留原认证及请求校验。关闭窗口撤销连接并停止本次服务。摄像头和麦克风只在用户主动操作并许可后使用。

## 本地生成

先准备项目 `.venv`、Node 22+、已编译的 TypeScript bridge 和 Xcode Command Line Tools。除原应用/手机后端依赖外，竖屏宿主需要 `PySide6.QtWebEngineWidgets`；生成图标使用 Pillow。然后在仓库根目录运行：

```sh
.venv/bin/python tools/macos/install.py
```

安装器复制运行文件和环境到本机目录，用 `launcher.m` 编译原生 Mach-O 入口，进行本机签名，再维护桌面链接。旧桌面应用保存在安装目录 `backups/`。不会移除 quarantine 或修改系统安全设置。

开发用的 `create_app.py` 可用 `--project-root`、`--python` 和 `--node` 指定实际环境。应用仍复用本机的 Anaconda 基础依赖和 Node，并非可直接拷给其他电脑的独立安装包；保留这些本机依赖。启动日志位于 `~/Library/Application Support/AnkangPortrait/.runtime/portrait.log`。数据、日志、权重和环境均不提交。

## 本机验证

Apple Silicon；Python 3.13.9、Qt/PySide6 6.9.2、Node 24.19.0。项目 `.venv` 复用已安装的 Anaconda 依赖，仅在项目环境补齐 `lap==0.5.12` 和 `cv2-enumerate-cameras==1.3.3` 及其 macOS 依赖；未修改 Anaconda 主环境。官方 YOLO11n-pose 权重与现有 manifest SHA256 一致。

- TypeScript `npm run build:bridge` 成功。
- `mobile_rehab/tests/test_unified.py` 与 `test_mobile.py`：28 项通过，包含真实模型处理空白录像、保存来源隔离和鉴权。
- 隔离 TEST 档案运行真实 Qt 竖屏窗口，逐页检查五个路由：viewport 与 document width 均为 430，无页面横向溢出，底部五项导航可用；截取并人工检查页面图片。
- 核对窗口关闭后释放应用锁；修正 WebEngine page/profile 释放顺序。
- 首次建档表单在 430 × 690 下截图检查；原生完整电脑端使用隔离目录成功启动并截图退出，未自动打开摄像头。

2026-11-17 启动修复新增验收：

- 系统启动请求能发出，但旧入口没有进入 Python；原生诊断采样进一步定位到启动器在文稿项目的日志文件 `freopen/open` 中阻塞。运行文件迁入本机 Application Support 后，启动日志和 Python 入口均正常。
- 安装后的原生应用 `codesign --verify --strict` 通过。
- 经桌面同名入口实际执行 `open -W -n`（LaunchServices），使用隔离 TEST 档案运行真实 Qt 窗口并截图：`ready=true`、5 项导航、430 × 860、窗口可见，随后正常退出。此项补齐此前仅直接执行的验收缺口。
- 首次迁入的 4 个现有数据文件逐个 SHA256 一致，旧目录原件保留。

原网页组件有内联 style 被既有 CSP 拒绝的日志，保留原 CSP；本轮未修改业务网页样式。上述测试不代表真人动作准确度、临床效果、云端部署或全部手机硬件验收。可选腕踝/手指关键点环境和本地语音未安装，本机未配置云账号与外部问答模型。
