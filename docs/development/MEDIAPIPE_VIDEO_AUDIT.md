# 手机姿态输入的 Python VIDEO 近似对照

本工具落实后端任务书12.4，不修改整个Android目录，不替换APK模型，也不接相机、SQL或正式界面。它在已有独立landmark环境里用同权重模型处理分析授权录像，再与原YOLO输出对照；不是手机实际推理、独立参考误差或姿态微调。实现：[mediapipe_video.py](../../tools/rehab_ml/mediapipe_video.py)、[pose_video_compare.py](../../tools/rehab_ml/pose_video_compare.py)。

## 1. 已核对的运行条件

本机原模型与Android本机build目录的`pose_landmarker_full.task`均为SHA256`5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`，9,398,198字节。原官方来源／版本在`assets/models/landmarks-manifest.json`；不下载或覆盖权重。本地build相同不证明伙伴手机已安装的APK也相同。

Python MediaPipe1.0.1／OpenCV5.0.0／numpy2.5.3来自原`.venv-landmarks`；产品环境和依赖不升级。APK锁定JavaScript`@mediapipe/tasks-vision`0.10.32，WebAssembly／WebView与Python平台不是同一SDK。

设置参照原`android_offline/web/worker.js`：VIDEO、CPU、num_poses=1，detection／presence／tracking阈值均0.5。原电脑LandmarkBackend继续使用IMAGE，本轮没有把它改成有隐藏历史的VIDEO。VIDEO需逐帧递增毫秒时间，相关官方接口见 [Python说明](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python) 与 [Web说明](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/web_js)。设置对齐不证明两平台结果、性能或预处理完全相同。

## 2. 信息怎样传递

| 环节 | 输入／门控 | 输出／消费者 |
| --- | --- | --- |
| 文件与权限 | 明确analysis-consent、现有视频文件、≤256MiB、限定三动作／侧别 | 私有request：原路径、原视频SHA、动作和侧别；不会授予training许可 |
| 所属子进程 | 既有landmark解释器，原manifest／权重核验；不安装依赖 | 所属Popen对象、私有日志；默认180秒工作等待，准确对象terminate／kill各等2秒 |
| 解码和时钟 | ≤15000声明帧、≤120秒、≤1920×1080像素总量、恒定原尺寸、BGR三通道 | 原媒体PTS、解码序号与BGR字节SHA；不缩放、镜像或伪造曝光时间 |
| VIDEO模型 | RGB由原BGR通道交换得到，round(PTS×1000)递增时间；模型输入字节已校验 | 原33点、visibility、presence、图像z；world估计不进入几何或金标准 |
| 后端适配 | 原像素x／y、解剖顺序、当前置信与画内条件；仅空间连续性 | 原PoseFrame → EvidenceAdapter → ProtocolEngine；保留独立缺测／次数／目标 |
| 同帧对照 | 同录像SHA、动作／侧、schema／尺寸、时间与解码像素hash；不按数组序号硬拼 | 配对／未配对帧、共同有效点数、两模型数值差异；没有真值时accuracy保持null |

原图归一坐标恢复为`x_px=x_norm×width`、`y_px=y_norm×height`。只为复用原后端门控计算`conf=min(presence,visibility)`，同时保留两个原值；它不是YOLO confidence同口径的校准概率。图像z不和米制world坐标混合。point-derived bbox只用于模型输出／空间连续性，不冒充人工全身框。

离线metric的processing_age=0表示按录像源时间回放，不是实测实时延迟为0。默认协议机位是算法适用条件，不证明录像机位经过人工／专业确认。空间ID在缺人、长gap或明显位置跳变后失效，不称人脸或生物身份。

## 3. 时间和缺失不怎样“修复”

保留`source_time_s`原值，API毫秒为`round(source_time_s×1000)`。只允许初始最多4个`[-0.25,0)`秒的preroll被明确跳过；非有限、负的流内时间、倒退／重复或毫秒量化冲突均失败，不用推理耗时或+1ms补点。实际解码帧数须等于声明帧数，提前读失败不当完成。

原YOLO产品OpenCV4环境与本机OpenCV5会对这两段MP4首帧暴露不同PTS。比较工具按微秒时间键找到候选，再检查误差≤1µs及原BGR SHA完全一致；即使时间一样，只要像素或尺寸不同就拒绝。未配对首帧单独计数，不删去后假称全样本一样。它只比较共享帧，两个引擎各自的EMA／准备历史仍可能因额外首帧而不同。

坐标对照按COCO17关节名称映射到MediaPipe33，不按下标截前17点。仅当前两端均有效、置信门控通过且画内的点计算`d_j=||p_yolo−p_mp||₂`；点缺失不填0差异。两端当前指标均有效才计算`Δθ=|θ_yolo−θ_mp|`。记录共同有效样本数、各端覆盖分子和共享帧分母，均值／p95为空时为null。两模型一致可能一起错，差异也不能说明哪一个是对的。

## 4. 使用命令

文件和动作参数由明确分析授权者提供。以下新输出目录不能已有；只能放在独立data／run根，默认忽略的`.runtime/rehab_ml/`。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py extract-mediapipe-video --video '授权录像.mp4' --exercise shoulder_abduction --side left --analysis-consent yes
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py compare-video-pose --yolo-result '.runtime/rehab_ml/run/明确YOLO/result.json' --mediapipe-result '.runtime/rehab_ml/run/明确MP/result.json' --output-dir '.runtime/rehab_ml/run/新同帧比较'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_mediapipe_video.py --shoulder-video '授权肩外展.mp4' --squat-video '授权深蹲.mp4' --analysis-consent yes
```

父进程、解码／模型、对照各自失败时非零退出；不将部分JSONL称为完成的结果。超时／取消只清理准确所属对象，不按进程名称扫杀；释放未确认明确失败，不假称资源已释放。OS Popen创建、文件hash与宿主序列化没有独立硬截止，这不是正式实时会话替代。17项专项中的超时／取消是受控Popen故障路径，原生模型／解码烟测是明确白色TEST视频；二者不是同一种证据。

私有视频、33点、请求原路径、日志和逐帧hash只留在忽略目录。Git报告仅聚合范围、SHA、覆盖和算法差异。没有新增训练许可、疾病、临床ROM、计次准确率或目标手机FPS结论。真实对照及最新回归见 [本轮验收](../validation/REHAB_MEDIAPIPE_VIDEO_2026-10-11.md)；缺少的专业参考仍按原任务书推进。
