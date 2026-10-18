# 第三方来源与许可记录

本文件记录实际使用资源，不表示取得了额外商业授权。源代码同步到 GitHub；模型二进制、虚拟环境、个人数据和原始整包不随仓库上传。下方带日期的说明保留当时的来源与验证范围。

## 2026-10-19 离线姿态控制渲染

`tools/rehab_ml/synthetic/control.py` 的身体骨架配色、连线和栅格化改编自 Fannovel16/comfyui_controlnet_aux 的 [dwpose/util.py](https://github.com/Fannovel16/comfyui_controlnet_aux/blob/a587a4c1594524c1d2de5cd1a86cd868ff448e1c/src/custom_controlnet_aux/dwpose/util.py)，固定commit `a587a4c1594524c1d2de5cd1a86cd868ff448e1c`。上游仓库[Apache-2.0许可](https://github.com/Fannovel16/comfyui_controlnet_aux/blob/a587a4c1594524c1d2de5cd1a86cd868ff448e1c/LICENSE.txt)原文副本在 [licenses/comfyui_controlnet_aux-Apache-2.0.txt](licenses/comfyui_controlnet_aux-Apache-2.0.txt)。改动包括命名关节/原像素坐标、单臂刚性命令轨迹、CPU RGB绘制及来源/真实PTS/全帧指纹校验；没有导入或分发该上游姿态检测权重。

新增LTX-2姿态控制权重仅在本机单独下载，使用其Community License，不能用上述渲染代码的Apache-2.0替代模型许可。模型revision/SHA、研究用途和分发边界见[合成数据卡](../../configs/rehab_ml/synthetic_data_card.json)及[实施记录](../development/REHAB_SYNTHETIC_VIDEO_IMPLEMENTATION.md)；本轮不把模型、视频或人工参考上传Git。

2026-09-10 整理时，在当前电脑重新准备了可选独立环境：19 个 wheel 通过官方 PyPI SHA256 核对，记录见 [扩展依赖校验](LANDMARK_DEPENDENCY_MANIFEST.json)。两个 `.task` 模型从清单中的 Google 官方端点取得并核对 SHA256；原有 YOLO 权重和主环境保留。详细执行范围见 [本次验收](../validation/INTEGRATION_2026-09-10.md)。

## 2026-09-08 可选关键点组件增补

| 对象 | 本机来源 / 版本 | 许可与分发边界 |
|---|---|---|
| MediaPipe 代码 / Python wheel | 官方 PyPI，1.0.1 Windows x64；独立 `.venv-landmarks` | [官方代码许可证](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE) 为 Apache-2.0，另有附带文件通知；不能据此推定所有外部权重/数据的许可 |
| Pose Landmarker full / Hand Landmarker bundle | Google 官方 `storage.googleapis.com/mediapipe-models/` 固定 `/float16/1/` 端点 | 只在本机下载，未将权重打包进 Git；URL、尺寸、SHA256 在 `assets/models/landmarks-manifest.json`。当前记录未单独确证权重再分发条款，商用或打包分发前必须核查模型卡与相应许可，不能以代码许可代替 |
| 扩展环境的 NumPy / OpenCV contrib / 其他 wheel | 官方 PyPI；完整版本见 `requirements.landmarks.lock.txt` | 安装包保留各自 LICENSE / NOTICE；没有修改原 YOLO 环境的 NumPy/OpenCV |
| 模型训练图像、测试人体照片、患者录像 | 本次未下载或分发 | 模型的训练背景不构成对其训练数据的授权；本次新增测试仅使用人工构造点及纯色视频 |

MediaPipe wheel SHA256：`96dc9de6bd04a6315ef424fda5c48e0929f2d78317295e75bc32c0bceeab517b`（官方 PyPI 的 1.0.1 `py3-none-win_amd64`）。模型参考：[Pose 官方说明](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)、[Hand 官方说明](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)。这些来源不提供本应用的康复/临床准确性认证。

以下为原环境来源记录，继续保留。

| 资源 | 本次实际版本 / 来源 | 许可记录与范围 |
|---|---|---|
| Ultralytics | 8.3.199，PyPI 官方发行内容 | 官方为 AGPL-3.0 / Enterprise 路线；未声称拥有 Enterprise 授权 |
| YOLO11n-pose | 官方 ultralytics/assets v8.3.0 发行附件 | 同上；精确地址、hash、骨架契约在 assets/models/manifest.json |
| PyTorch / torchvision | 2.9.1 / 0.24.1；本机 torch 报告 2.9.1+cpu，CUDA build 为 None | BSD 类许可；实际 wheel 元数据见依赖清单 |
| Qt for Python / PySide6 | Essentials 6.11.2 + shiboken6 6.11.2 | 使用 Qt Widgets 子集；按实际模块核查 LGPLv3 / GPLv3 / 商业路线 |
| OpenCV | opencv-python 4.12.0.88 | 主项目 Apache-2.0；wheel 中附带组件也有各自许可 |
| 摄像头枚举 | cv2-enumerate-cameras 1.3.3 | 项目 MIT 许可，按官方仓库显式配对 backend + index |
| NumPy / PyYAML / pytest 等 | requirements.lock.txt 中固定版本 | 安装 wheel 的官方来源、hash、许可元数据分别记录 |
| 本地提示音 / 图标 | 本次自行生成的非语言 WAV 和 SVG | 无第三方录音、照片或图标素材；提示音不含医疗语音 |
| 字体 | Windows 系统已有 Microsoft YaHei / Segoe UI | 运行时引用；未把系统字体复制或分发进项目 |
| 测试视频 | 测试时用代码生成纯色图像并编码为临时 AVI | 明确合成内容；不属于真实人体动作验证 |
| 人体录像 / 数据集 / 示范视频 | 未提供、未下载、未打包 | 没有患者录像或公开研究数据授权的推定 |

依赖通过清华 PyPI 镜像取得以改善下载速度，随后将 **44 个 wheel 的 SHA256 与官方 pypi.org 发行元数据逐一核对**。核对程序为 `scripts/verify_wheels.py`，逐文件记录在 `DEPENDENCY_MANIFEST.json`。模型直接来自官方 GitHub 发行附件，独立核对 hash。

官方参考：

- [Ultralytics YOLO11 与模型文件名](https://docs.ultralytics.com/models/yolo11/)
- [姿态输出与 COCO17 定义](https://docs.ultralytics.com/tasks/pose/)
- [跟踪接口](https://docs.ultralytics.com/modes/track/)
- [Ultralytics 许可](https://www.ultralytics.com/license)
- [Qt for Python 许可](https://doc.qt.io/qtforpython-6/licenses.html)
- [Qt 工作线程](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html)
- [PyTorch 安装选择器](https://pytorch.org/get-started/locally/)
- [cv2-enumerate-cameras 官方仓库](https://github.com/lukehugh/cv2_enumerate_cameras)

Ultralytics 的代码、权重以及其训练数据背景是不同的权利对象；资源名称出现在任务书中不等于取得使用许可。未来分发或商用前，需要按实际组合履行第三方义务并确定本项目自身的分发许可。
