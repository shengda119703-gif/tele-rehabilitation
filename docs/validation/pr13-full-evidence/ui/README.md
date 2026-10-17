# PR #13 离线 UI 冒烟证据

2026-10-17，本次使用真实 ProductWindow、ProductBackend、Node 桥接与隔离 SQLite，模型和语音均关闭。资料属于 `SYNTHETIC-TEST-pr13-ui / SYNTHETIC / TEST`，不是患者资料。相机 Runtime 复用既有测试的 PassiveRuntime；没有打开摄像头或执行真人训练。

桌面：六个页面（首页、康复、健康、用药、家庭、康复管家）实际渲染与导航断言通过；离线聊天返回本地来源，未新增健康事件。`desktop-results.json` 保存结果。截图为原生 Qt offscreen 渲染：`desktop-home.png`、`desktop-rehab.png`、`desktop-assistant.png`、`desktop-offline-chat.png`。已目视复核康复页与聊天页：合成手工计划显示坐站 5 次 × 1 组，并明确“当前没有有效评估，请先评估或补测，再使用计划”；聊天正确标为未配置 DeepSeek、本地回复。

网页：真实共享后端已在本机 loopback 启动，浏览器工具尝试 Edge 返回 `Browser is not available: edge`，可用浏览器列表为 `[]`。因此网页 UI 状态为 **UNVERIFIED**，没有网页截图，没有将 HTTP 服务启动称为浏览器 UI 通过。具体结果见 `browser-results.json`。

复现入口：`tools/qa/pr13-ui.py --data-dir <独立合成目录> --output docs/validation/pr13-full-evidence/ui`。使用本次隔离 venv；加 `--serve --port 8768` 可启动真实共享网页测试服务器。运行日志和 SQLite 均保存在仓库外的任务 `work/` 目录，证据不包含配对码、API Key、Token 或真实健康资料。

这些仅证明离线展示、既有手工计划读取及适用性门禁；没有验收真实模型、Android 设备、新候选计划的专业审核与采用，也不表示自然语言计划已经写入患者 App。
