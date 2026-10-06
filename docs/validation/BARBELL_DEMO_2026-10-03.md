# 器械物理量 Demo：2026-10-03 本机验收

基线 `8f4f3c4`。修改仅在 `mobile_rehab/` 及文档，用户未提交的动作素材不纳入。范围 / 公式 / 使用条件见 [说明](../BARBELL_DEMO.md)。

## 自动化

执行：

```powershell
.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe -m pytest mobile_rehab/tests -q --disable-warnings --basetemp .runtime/barbell-tests-01
node --check mobile_rehab/static/barbell.js
node --check mobile_rehab/static/app.js
node --check mobile_rehab/static/fitness.js
```

**64 passed，1 warning，15.48 秒**；脚本语法检查通过。包括既有 47 项及本轮 17 项：无效 / 非有限 / 太短尺度校验、解析抛物线运动的速度 / 加速度 / F / P 校验、无质量不出 F / P、静止 / 无人 / 低帧率、缺测窗口、真实 OpenCV 模板跟踪、目标丢失后不重接、画面尺寸 / 纹理错误、模拟示例确定性与来源标签、真实录像适配器里的器械分析、API 标定保存 / 模式隔离 / 示例鉴权。

使用真实 MP4 解码与模板跟踪的集成样本是程序生成的测试标记，不是真人录像。另有既存真实 YOLO 无人录像回归，不以这些测试替代真人准确度证据。

原应用目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_app_controller.py tests/test_automatic_plans.py tests/test_automatic_runtime.py tests/test_product_catalog.py tests/test_product_navigation.py tests/test_product_body_overview.py tests/test_product_window.py -q --disable-warnings
```

**250 passed，4 subtests passed，149 warnings，20.03 秒**。不是全部历史测试总量。

## 浏览器与隔离

- 正式 `127.0.0.1:8765` 页面：健身入口 → 模拟示例成功，显示三次模拟上升，峰速约 0.76 m/s、峰值器械竖直外力估算约 479.2 N、峰值竖直功率估算约 307.4 W。明确显示非真人、模拟数据、不保存记录。
- 412×915 手机视口截图检查，卡片和数值无整页横向溢出。
- 单独在 `localhost:8766` 建立隔离服务与数据目录，使用独立主机名 Cookie，不复用正式用户身份。
- 从浏览器文件选择器加载带可见 SYNTHETIC TEST 标签的合成 WebM；开启器械分析，真正点击标尺两端与移动标记，输入 48 cm / 40 kg，勾选条件与上传授权。
- 经真实网页上传、队列、录像解码、YOLO、模板跟踪、物理分析，报告产生约 0.30 m/s 峰速、429.1 N 峰值器械外力估算、119.0 W 峰值器械功率估算；人体计次为 0，没有将标记移动伪装成人体动作。
- 峰速回看按钮将实际视频暂停到 1.50 秒；原视频保留测试标签。器械标记及轨迹以黄色在暂停帧单列。
- 页面未捕获脚本错误。临时服务 / 浏览器关闭，恢复浏览器视口，正式服务保持运行。临时数据均在 `.runtime/`，不提交 Git。

## 仍待实测

红米手机系统相机、真人杠铃负重录像、不同标尺 / 标记 / 光照 / 机位 / 遮挡、与编码器或测力台的误差对照未完成。不声明百分比准确率、肌肉测力或爆发力能力评级；相机静止 / 水平、标尺共面由用户确认，不假称自动验证。
