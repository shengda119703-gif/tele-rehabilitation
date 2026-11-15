# macOS 竖屏桌面入口

2026-11-15：新增 `mobile_rehab.portrait`，桌面业务仍为 0.25.2；本地启动器 revision 1。

## 使用

双击桌面 **安康康复（竖屏版）.app**。默认内容区 430 × 860 逻辑像素，高度随当前屏幕缩小；最小 360 × 600，可拖动调整。底部导航为首页、康复、健康、用药、家人。首次使用复用原有建档表单；不生成演示患者，已有多个档案时明确选择本人。

竖屏入口复用 `mobile_rehab/static/unified.html` 和正式 `ProductBackend`，不重写规则、计划和存储。手机界面的“电脑端指引”仍保留原语义。需要原生实时评估及正式训练时，从 macOS 顶部菜单 **工作区 → 打开完整电脑端（实时评估与训练）** 切换。存在录像分析或实时指导时先结束当前任务。切换关闭本次本机服务、释放数据库锁后启动原 `app.main`；返回竖屏入口可关闭完整电脑端，再双击桌面图标。

数据位于原应用的 `rehab_codex_single_camera_v2_1/data/`，与完整电脑端共用。两种窗口使用同一 `application.lock`，不可同时写同一档案。只监听 `127.0.0.1` 随机端口，不开启局域网共享；通过既有 `/api/pair` 获取绑定本人的 HttpOnly cookie，保留原认证及请求校验。关闭窗口撤销连接并停止本次服务。摄像头和麦克风只在用户主动操作并许可后使用。

## 本地生成

先准备项目 Python 环境、Node 22+ 和已编译的 TypeScript bridge。除原应用/手机后端依赖外，竖屏宿主需要 `PySide6.QtWebEngineWidgets`；生成图标使用 Pillow。然后在仓库根目录运行：

```sh
.venv/bin/python tools/macos/create_app.py --destination "$HOME/Desktop"
```

可用 `--python` 和 `--node` 明确指定实际环境。生成的 `.app` 是本机启动器，引用当前仓库和已安装环境，并非可直接拷给其他电脑的独立安装包。勿移动或删除其引用的仓库/环境。日志位于仓库 `.runtime/portrait.log`，数据、日志、权重和环境均不提交。

## 本机验证

Apple Silicon；Python 3.13.9、Qt/PySide6 6.9.2、Node 24.19.0。项目 `.venv` 复用已安装的 Anaconda 依赖，仅在项目环境补齐 `lap==0.5.12` 和 `cv2-enumerate-cameras==1.3.3` 及其 macOS 依赖；未修改 Anaconda 主环境。官方 YOLO11n-pose 权重与现有 manifest SHA256 一致。

- TypeScript `npm run build:bridge` 成功。
- `mobile_rehab/tests/test_unified.py` 与 `test_mobile.py`：28 项通过，包含真实模型处理空白录像、保存来源隔离和鉴权。
- 隔离 TEST 档案运行真实 Qt 竖屏窗口，逐页检查五个路由：viewport 与 document width 均为 430，无页面横向溢出，底部五项导航可用；截取并人工检查页面图片。
- 核对窗口关闭后释放应用锁；修正 WebEngine page/profile 释放顺序。
- 首次建档表单在 430 × 690 下截图检查；原生完整电脑端使用隔离目录成功启动并截图退出，未自动打开摄像头。

原网页组件有内联 style 被既有 CSP 拒绝的日志，保留原 CSP；本轮未修改业务网页样式。上述测试不代表真人动作准确度、临床效果、云端部署或全部手机硬件验收。可选腕踝/手指关键点环境和本地语音未安装，本机未配置云账号与外部问答模型。
