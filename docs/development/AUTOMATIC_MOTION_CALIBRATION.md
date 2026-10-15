# 自动轨迹与免标点分析

版本：电脑 0.23.3、APK 0.3.3/code33，合同 `automatic-motion-1`。

## 用户流程

健身动作 → 拍摄或选择录像 → 分析 → 报告／原片回看 → 历史与备份。

删除原器械三点标定表单、参考距离、重量填写和标定确认。自动轨迹分析是默认分支，失败不清除人体分析，也不要求用户重新标点。当前 UI 的布局、字体、主题和动作库不重做。原拍摄／上传授权、已采用安排、支撑／陪同、真实感受、存储核对与医疗剂量规则没有用“自动化”代替。

## 两端接线

| 信息 | 电脑／云端演示服务 | 手机本地 APK |
| --- | --- | --- |
| 输入 | 原 CameraManager 的录像帧、媒体 PTS | 原视频 seek、ImageBitmap、媒体时间 |
| 人体观测 | 原 YOLO COCO17 PoseFrame | 原 MediaPipe PoseLandmarker，CPU Worker |
| 自动轨迹 | `mobile_rehab/automatic_motion.py` | `mobile_rehab/static/automatic-motion.js`，随 Worker 预装 |
| 合并 | 原 FitnessEngine 结果 + 独立 `barbell` + `equipment_analysis` | 原 LocalEngine 结果 + 相同自动轨迹合同 |
| 保存 | 原 job/result 路由与历史 | 原 PhoneStore、IndexedDB 录像、原备份 |

使用原视觉模型，不新增权重、不下载运行时模型。圆形器械候选是几何检测，不是训练过的杠铃语义模型。

## 自动选择与回退

1. 在最长边不超过约 240 像素的画面内进行梯度圆检测；Python 用 OpenCV HoughCircles，JS 用受限梯度投票。圆周 24 方位边缘支持至少 70%，排除鼻点邻近候选；人体手腕可见时约束候选距离。
2. 候选连续三帧的中心／半径相容才锁定。圆轨迹观测覆盖至少一半输入帧，且足够帧能连续求导，才优先选器械。短暂背景圆不会盖过手腕。
3. 两侧手腕独立保留，自动取覆盖更完整的一侧；不在同一条轨迹中拼接左右手。默认同等覆盖时优先原测试侧。
4. 手腕可见但器械不可用时，按可见躯干长度、肩宽或画面高度归一化。不要求用户暴露髋部、不要求量距离或输入身高；这些尺度仅是相对单位。
5. 均缺测时保留动作分析和未取得连续轨迹状态。未知量为 null，不制造零速度／功率或补齐轨迹。

这些判定在后台执行，不弹确认，不把轨迹识别失败升级为整段录像失败。

## 尺度、速度和功率

圆形候选采用明确的先验直径 D=0.45 m，并非从单目图像测得的真实规格：

`κ = D/(2 r_px)`；`h(t) = [y_origin - y(t)] κ`。

手腕分支 `h_rel(t)=[y_origin-y_wrist(t)]/L_px`，L 为冻结的可见人体／画面尺度，单位为“躯干长度/s”“肩宽/s”或“画面高度/s”。不能把这些数值标为 m/s、N、W。

分段窗口拟合 `h(t+τ)=c0+c1τ+c2τ²`：速度 `v=c1`、加速度 `a=2c2`。使用中心窗口，至少五个真实样本；窗口随 .08→.18→.24 秒降采样自适应，仍用原媒体时间，而不是处理耗时。加速度残差门槛仅是数值稳定处理，不是临床合格线。

只有器械先验尺度分支提供 `P_lift/m = g max(v,0)`（W/kg），这是竖直重力抬升分量。自动分支不推断负重：`mass_kg`、`force_n`、`power_w` 保持 null。不声称人体真实肌肉力量、真实总机械功率或已识别杠铃重量。

检测圆尺寸变化、手机降分辨率、参与者身份变化（电脑端）、手腕突跳、遮挡或媒体时间缺口 >0.3 秒时分段重置，不跨缺口求导／计完整上升段。完整上升段和解剖动作往返次数是独立字段，不能替代康复训练完成量。

## 报告与兼容

`barbell.automatic=true`；`measurement` 保存 target_kind、target_source、scale_source、unit、approximate、mass_kg；series 保存实际时间及缺测；summary 保存连续跟踪和上升段指标。原旧标点报告与旧 X-Fitness-Calibration 合同仅为兼容历史／接口保留，当前界面不再生成标点请求。

报告直接展示实际目标（左／右手腕或器械）、速度曲线、上升片段和最快时刻回看；测量说明折叠。手机回放使用 `data-local-video-src` 后解析本机 Blob，避免媒体标签提前向不存在的电脑 API 请求录像。

## 边界与后续

这是低操作成本的自动近似轨迹方案，尚不能可靠识别所有圆盘、哑铃、绳索或深度视角。45 cm 先验不适合所有器械；角度偏斜、背景圆、相机移动会产生误差。未来可训练器械分割／关键点模型并结合器械档案，但不能因此要求当前用户补点才能继续。

原解剖动作计次、处方资格和医学阈值不改。完整人体入镜不足时，报告仍可返回轨迹，但不能将手腕上升段冒充完整深蹲。两个平台模型与采样不同，数值不要求相同，不拿覆盖率当准确率。

几何检测依据：[OpenCV 官方 Hough Circle Transform](https://docs.opencv.org/4.13.0/d4/d70/tutorial_hough_circle.html)。人体推理复用仓库原模型清单；本轮没有新训练或准确率验证。

## 开发验证

```powershell
node --test mobile_rehab/tests/*.cjs android_offline/tests/*.cjs
& rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe -X utf8 -B -m pytest mobile_rehab/tests android_offline/tests/test_packaging.py -q
node tools/verify_automatic_motion.cjs VIDEO NEW_PRIVATE_DIRECTORY
& rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe -X utf8 -B tools/verify_automatic_motion.py --video VIDEO --output NEW_PRIVATE_DIRECTORY
```

需先依原脚本准备桥接、APK 资源和当前发布包。录像验证创建独立私有目录，不能使用正式患者库，也不回填用户历史。
