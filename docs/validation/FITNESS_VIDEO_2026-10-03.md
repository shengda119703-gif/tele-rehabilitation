# 手机健身录像分析：2026-10-03 本机验证

基于上一轮手机网页提交 `704fdec`，本轮只修改根目录 `mobile_rehab/` 与相关文档。没有覆盖用户动作素材，也没有修改原桌面康复核心。范围见 [功能说明](../FITNESS_VIDEO.md)。

## 自动化结果

在当前电脑已有 `rehab_codex_single_camera_v2_1/.venv` 执行：

```powershell
.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe -m pytest mobile_rehab/tests -q --disable-warnings --basetemp .runtime/fitness-tests-05
node --check mobile_rehab/static/app.js
node --check mobile_rehab/static/fitness.js
```

最终 **47 passed，1 warning，13.17 秒**；两个脚本语法检查成功。测试中：

- 8 项动作、左右两侧，各两次合成往返的计次 / 阶段时序。
- 每项主指标缺测不跨前后半段拼接；时间间隔、参与者 ID、上下文变化、骨架定义、非递增时间检查。
- 无人、静止、从半程开始、低置信度、非有限坐标、退化几何；卧推不要求髋部，也不输出无关下肢指标。
- 真实录像读取适配器 + 测试替身关键点，生成完整计次与归一化关键时刻。
- 真实本机 YOLO + 黑色无人 MP4，结果 0 次、没有虚构角度或康复数据库；原康复无人模型链路仍通过。
- 8 项目录、跨动作类别拒绝、任务分发、轻量历史、健身结果不进入康复计划 / 反馈接口。
- 既有手机授权、上传 / 队列、隔离与康复评估 → 自动计划 → 训练测试保留。

在原应用目录执行以下回归：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_app_controller.py tests/test_automatic_plans.py tests/test_automatic_runtime.py tests/test_product_catalog.py tests/test_product_navigation.py tests/test_product_body_overview.py tests/test_product_window.py -q --disable-warnings
```

结果 **250 passed，4 subtests passed，148 warnings，22.35 秒**。这是本轮所选回归范围，不声称重新跑了所有历史完整测试。

## 实际浏览器操作

正式服务 `127.0.0.1:8765` / 局域网监听：

1. 页面加载独立“健身分析”入口，8 项卡片与具体动作拍摄指导可见；卧推指导只要求肩、肘、腕。
2. 412×915 手机尺寸下检查首页、卡片及底部 5 项导航，无整页横向溢出。
3. 从真实文件选择器上传本轮生成的无人物黑色测试录像，勾选上传授权后走实际队列和本机模型；卧推报告显示 0 次 / 0% 观察占比 / 未测得，不填造假角度。
4. “我的记录”展示健身与康复类别，健身筛选只显示健身任务；返回身体评估后原肩部目录正常。
5. 浏览器没有捕获到本轮页面脚本错误。

另用 `127.0.0.1:8766` 临时只读页面，载入实际适配器测试产物，并将报告标题显著标为“合成测试 · 深蹲（非真人）”。不连接用户数据库、不向正式队列写入合成成功数据：

- 验证 1 次往返、逐次时间、角曲线、指标覆盖、关键时刻按钮。
- 修复坐标轴 SVG 默认填充造成的黑色三角遮挡，最终轴样式为 `fill:none`。
- OpenCV 生成的 MPEG-4 Part 2 测试视频在该浏览器不能播放；改用同帧数 / 同尺寸的黑色 VP8 WebM 测试回看。正式页面补充浏览器解码失败说明，建议后续使用普通 H.264 / AVC。
- 按“峰值 2.7s”后实际视频 `currentTime=2.7`、暂停、就绪状态 4；画面显示归一化关键点叠加。
- 验证后关闭临时页和只读服务，恢复浏览器尺寸；正式网页仍保持运行。

临时截图 / 测试产物仅在被忽略的 `.runtime/`，不提交用户数据、视频、连接码、数据库或模型。正式浏览器记录中本轮新增的卧推 0 次记录来自黑色测试录像，不是真人训练表现。

## 未声称完成的验证

- 8 项真人训练、不同体型 / 动作变式 / 负重 / 遮挡的准确率和逐帧人工标注误差。
- 红米 K60 Ultra 真机拍摄 / 上传、不同录像编码、长期多人并发及外网部署。
- 自动动作类别识别、机位验证、器械跟踪或物理力学测量。
- 疾病康复处方或临床有效性。计次规则不构成动作合格标准，未计完整不等于动作错误。
