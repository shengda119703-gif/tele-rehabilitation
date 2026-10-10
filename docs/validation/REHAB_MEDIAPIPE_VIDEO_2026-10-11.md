# MediaPipe VIDEO 与原 YOLO：本机实际对照

2026-10-11（Asia/Shanghai），基准`bf698a3be2e7b6a94d174b41716cd8ae8ae95e34`。对应任务书12.4：无法取得APK实际关键点时，用同权重Python VIDEO近似；不是移动端改版。产品0.20.0、APK0.2.1、v2默认关闭，正式UI／整个Android／原模型／非康复／正常数据库不变。

## 1. 完成了什么

新增`extract-mediapipe-video`、`compare-video-pose`及真实两视频验证脚本，新增17项测试。原YOLO离线提取仅补解码BGR SHA和原片运行后hash核对，不改几何、阈值或计次；MP复用原EvidenceAdapter／ProtocolEngine，不往患者历史写测试事实。

本地full.task SHA`5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`，9,398,198字节，与Android本机build文件相同。MP Python1.0.1／OpenCV5.0.0／numpy2.5.3与APK JS0.10.32仍不同，未在红米／伙伴手机执行；不把build校验扩成已安装APK校验。VIDEO／CPU／单人及三个0.5设置来自原worker，原IMAGE组件不改。

保留原33点visibility／presence／图像z；像素轴分别按原宽高恢复，world不进入几何。原PTS不以wall clock替换；最多4个初始负preroll可单列跳过，流内倒退／非有限／毫秒冲突拒绝。比较先核对原视频SHA、动作／侧、时间、尺寸、原BGR SHA，再按关节名映射，不按不同数组下标拼接。

## 2. 实际运行

产品解释器和依赖不升级；C盘满，TEMP／TMP／日志／私有骨架均在E盘忽略目录。没有清理用户文件、开相机、启动或重启正式服务。实际总入口从项目根运行：

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run\process-temp'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_mediapipe_video.py --shoulder-video 'E:\game\test video\肩外展.mp4' --squat-video 'E:\game\test video\深蹲.mp4' --analysis-consent yes
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
```

原片属于之前明确分析授权范围，本轮仍training_authorized=false，不当专业标签或训练资料。原图和逐帧关键点不发布Git。新SDK／运行模式依据 [官方Python说明](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)，平台差异另见 [Web说明](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/web_js)。

### 完整回归：verification-b2b7fc2e

| 范围 | 实际结果／命令耗时 | 日志SHA256 |
| --- | --- | --- |
| 新后端 | 177项／92.079秒；命令93.294秒、exit0 | `5b29432646e1c74c9490e26c78797963f0c9a203b30f8073b9685203276e2ff5` |
| 旧康复 | 12项／0.091秒；命令0.253秒、exit0 | `e4c361c646011848213770236330c2956752ec3a66d21aeeca515c17e9ca1c8c` |
| 旧手机 | 19项／13.05秒；命令13.578秒、exit0，既有1条warning | `e210361f8e115d26ceeb07ba03dbe111df4262b7a52f38fc5d4034e8fa84b739` |
| 保护 | 1308文件、changes=[]；命令5.247秒、exit0 | `8d858a68e246d8a128b60189ee3375723c3a78d8e236f94729944fc7ff1f3fca` |

17项MP、30项关键点工具、12项存储和18项报告专测包含于177项，不相加。旧会话CLI、IRDS训练、全UI／Android／Agent和性能benchmark未重跑。日志与实际argv见 [regression.json](../../reports/rehab_backend/regression.json)。

### 原片对照：mediapipe-audit-97d814f4

7条真实CLI均exit0，17项专项3.129秒，是177项子集。每段新YOLO提取、MP提取、比较顺序执行；整个验证与完整回归同时运行，耗时不能当公平速度优劣。完整聚合／源码SHA／模型／SDK／原片SHA见 [mediapipe_video_verification.json](../../reports/rehab_backend/mediapipe_video_verification.json)。

| 步骤 | 命令耗时 | 日志SHA256 |
| --- | ---: | --- |
| unit | 3.337秒 | `eea9a9801d6cfbddcdc3b6b1d9cf162340f94c0da15365ab0bff607e39122774` |
| shoulder_yolo | 25.907秒 | `e57895dd7207f8faf6267fc6c337f8d2f09c8dc80ba8b9a055c2bd65dfc5a624` |
| shoulder_mediapipe | 16.385秒 | `ad8560797bbe2210c69bfd82dc50502dbb68a7a1f5b2ba44bab8ac8ae2a83507` |
| shoulder_compare | 0.253秒 | `3f5d22f34ece32292fc97a8faf0f4ac48cc6e519dec40e6d6ab1d4678450862c` |
| squat_yolo | 24.817秒 | `b97680e49f565d958a65216ec1df1712fe21e59f514340a3b669456f66e5d43a` |
| squat_mediapipe | 15.879秒 | `086aaa63b3bb7fe683ca7c46b6ccfa1ccbea3b7933fc42309d87affcba02288f` |
| squat_compare | 0.218秒 | `953e367916680be85a3b85706717be104580360f172dab6b8844f182df4de2ac` |

## 3. 真实输入结果与解释

| 原片／指标 | YOLO | MP Python VIDEO | 核验范围 |
| --- | --- | --- | --- |
| 肩外展输入 | 443帧 | 444帧 | 443共享帧的PTS与BGR SHA完全一致；MP 1个首帧未配对 |
| 肩主抬举有效覆盖，共享帧 | 434／443 | 424／443 | 各端当前有效指标；MP完整输入为425／444 |
| 肩主角度模型差异 | 424共同有效帧 | 平均4.491°，p95 10.405° | 两模型差异，不是相对临床真值MAE |
| 深蹲输入 | 429帧 | 430帧 | 429共享帧的PTS与BGR SHA一致；MP 1首帧未配对 |
| 膝主角度有效覆盖，共享帧 | 48／429 | 0／429 | 没有共同有效角度，差异null，不补0 |
| 新协议确认次数，两片 | 均0 | 均0 | 稳定准备／有效腿部证据等未支持完整确认；不是计次准确率 |

两种模型在该肩外展片中都有较高主指标覆盖，但MP没有解决该深蹲片缺测；不能只根据单片换模型或降低观测门槛。模型差异说明需要专业参考确定误差来源，不能把模型相互接近或影像流畅当成功。两个引擎各自处理额外首帧、EMA历史、空间焦点和SDK内部tracking，数值并非只有网络权重这一变量。

视频SHA分别`97a9fa1b9f06de6482c06c109f40bc4e6e1681f53dde6fd7f478b5ac59405e0d`与`c384d08c0bc64d12939940e85b1f62b4ae29d470d27d0695054d786873779c95`。本轮原YOLO仍用原权重`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`，不改原阈值／规则，不以结果反向调参。

## 4. 验证用例与未完成边界

17项包括原PTS／负preroll、非有限／倒退／重复／毫秒冲突、非方形轴／原presence与visibility／图像z、单人33点、空间ID失效、模型／SDK实际核对、权限／文件／等待上限、像素与时间配对、SHA／原几何／领域拒绝、缺点不补0，以及准确所属对象的超时／取消／释放未确认。

其中3项取消／超时用受控Popen对象，说明调用路径，**没有制造真实原生死锁**；真实白色TEST AVI烟测实际解码4帧、加载MP full.task，0可观测／0次且所属退出确认。真人部分另为两段原片真实原生推理；没有将TEST白图当真人数据。OS Popen创建、hash／序列化并无单独硬截止，物理介质和全部进程故障仍待测。

保护基准SHA`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`不重建；1308保护文件一致，另核对本轮开始280份用户素材／CSV／说明／任务书／导入脚本不改、不提交。原片不覆盖，所有请求、33点和源图只在忽略目录。

仍缺：专业真值／训练权限、RGB姿态微调、按人独立目标域准确性、APK真实导出／红米执行、全负载／物理故障、适用康复深蹲宿主计划。现有计划库无独立康复深蹲，不把膝屈曲或健身动作改名、不新增资格规则／处方。v2继续默认关闭，未接正式五页或APK。具体数据流、公式与使用见 [VIDEO工作流](../development/MEDIAPIPE_VIDEO_AUDIT.md)。
