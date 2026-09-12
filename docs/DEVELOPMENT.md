# 开发与验证

所有源码在 `rehab_codex_single_camera_v2_1/`。保留这个目录名称以兼容现有环境和数据；它不是应用版本号。版本由 `app/__init__.py` 定义，侧栏复用同一值。

## 安装与启动

Windows x64，Python 3.13。首次从 GitHub 获取后，在仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Rehab.ps1 -IncludeLandmarks
# 明确选择镜像时：
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Rehab.ps1 -IncludeLandmarks -IndexUrl https://pypi.tuna.tsinghua.edu.cn/simple
```

省略 `-IncludeLandmarks` 只准备主环境；腕、踝和手指任务还需要可选环境。普通启动不联网安装依赖、不下载模型、不自动采集。启动使用根目录 `启动康复助手.cmd` 或 `Start-Rehab.ps1`。

主依赖固定在 `requirements.lock.txt`。可选环境使用 `requirements.landmarks.lock.txt`，先下载 wheel、核对官方 PyPI SHA256，再从本地文件安装；两套环境不混装 OpenCV。模型分别由两个准备脚本校验来源清单与 hash。

## 代码层次

| 位置 | 责任 |
| --- | --- |
| `app/camera_manager.py`、`source_worker.py` | 唯一采集入口、设备解析、帧时间、停止释放 |
| `app/dual_camera.py`、`dual_view.py` | 正侧面设备角色、单次使用的接收配对、辅助测量记录和逐路条件 |
| `app/vision.py`、`landmark_backend.py`、`landmark_process.py` | 主姿态模型及同图像的可选关键点进程 |
| `app/exercises.py`、`quality.py`、`joint_calibration.py`、`axial_geometry.py` | 动作定义、逐指标可见性、校准、二维几何 |
| `app/rehab.py`、`training.py`、`assessment.py` | 动作过程、组次执行和评估汇总 |
| `app/runtime.py`、`scene_controller.py` | 命令、生命周期、开始门禁、配置快照、保存恢复 |
| `app/guidance.py`、`measurement_guidance.py` | 独立于数据门槛的显示缓冲、单一指导、逐点调整提示和可选的继续建议 |
| `app/guided.py` | 引导计时的固定提示节奏与 `GuidedEngine`；不推断阶段、次数或目标 |
| `app/journey.py`、`app/ui/journey.py` | 康复与配套场景的步骤序列、完成小结和下一步入口 |
| `app/storage.py`、`participants.py`、`assessment_batches.py`、`reports.py` | 本地数据库、个人档案、评估清单和导出 |
| `app/training_plans.py`、`app/ui/plan_library.py` | 个人多项目计划、持久化白名单、版本 / 范围门禁和原生编辑器 |
| `app/automatic_plans.py`、`app/ui/automatic_plans.py` | 评估驱动的基础活动安排、来源 / 适用性快照、顺序执行与自动计划页面 |
| `app/ui/` | 原生界面、身体导航、相机测试、大字指导 |

## 自动测试

在应用目录执行；测试使用临时数据库与明确合成输入。模型和回放集成也只验证软件接入，不证明真人准确度。

```powershell
Set-Location .\rehab_codex_single_camera_v2_1
.\.venv\Scripts\python.exe scripts\check_project.py --list
.\.venv\Scripts\python.exe scripts\check_project.py
# 按改动范围选择一组：
.\.venv\Scripts\python.exe scripts\check_project.py --suite core
.\.venv\Scripts\python.exe scripts\check_project.py --suite ui
.\.venv\Scripts\python.exe scripts\check_project.py --suite integration
```

完整模式按互不重复的文件组执行：业务、界面、逐文件集成。分组先认 `integration` / `landmarks`，再按名称中的独立词 `ui`、`product`、`guides`、`hub` 归入界面组；这修正了此前把 `quiet`、`guidance` 中的字母误判成界面文件的问题。集成文件独立进程运行，避免 Qt、模型和多进程状态互相影响。默认每批最多 300 秒；失败或超时保留日志并停止后续批次。超时只停止本次测试子进程树，不结束其他正在运行的软件。

日志、JUnit 和 JSON 汇总默认放在 `.runtime/checks/时间/`。可用 `--output` 指定一个尚不存在的新目录。汇总中的 JUnit `tests` 可能包含 pytest 子测试，报告主测试数量和子测试时应按 pytest 原文说明，不重复相加。

只进行收集、未选择、跳过与测试通过要区分。可选模型缺失导致的跳过不能写成该模型已接通。普通 `python -m pytest tests -q` 仍可使用；如果组合运行出现问题，保留失败证据再按文件定位，不反复补跑后只挑成功数字。

## 界面与文档检查

```powershell
.\.venv\Scripts\python.exe scripts\qa_body_camera_ui.py --output qa-output\current-body
.\.venv\Scripts\python.exe scripts\qa_neck_shoulder.py
.\.venv\Scripts\python.exe scripts\qa_training.py
.\.venv\Scripts\python.exe scripts\qa_plan_library.py
.\.venv\Scripts\python.exe scripts\qa_movement_timing.py --output qa-output\timing-review
.\.venv\Scripts\python.exe scripts\qa_longitudinal.py --output qa-output\history-review
.\.venv\Scripts\python.exe scripts\qa_dual_camera.py --output qa-output\dual-camera-review
.\.venv\Scripts\python.exe scripts\qa_automatic_plans.py
.\.venv\Scripts\python.exe scripts\qa_quiet_guidance.py --output qa-output\quiet-guidance-review
.\.venv\Scripts\python.exe scripts\qa_smooth_flow.py --output qa-output\smooth-flow-review
.\.venv\Scripts\python.exe scripts\audit_readiness.py --output .runtime\readiness-review
.\.venv\Scripts\python.exe scripts\check_docs.py
.\.venv\Scripts\python.exe -m compileall -q app scripts tests
```

这些界面脚本渲染应用自身，不截图用户桌面、不打开相机。真实启动检查可以显式选择独立目录：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m app.main --data-dir qa-output\startup-check --screenshot qa-output\startup.png
Remove-Item Env:QT_QPA_PLATFORM
```

最后一行只清除本次 shell 的环境变量。真实摄像头验收从软件的相机测试入口由使用者开始，独立记录设备和验证范围。

双摄也提供显式选择设备的本地检查脚本：先 `scripts\check_dual_camera.py --list --output .runtime\pair-enumeration` 只枚举，再按当次输出提供 `--frontal-index` 与 `--sagittal-index`。由 CameraManager 打开、采样并释放后重新打开，不加载模型或保存图像；完整命令和证据范围见[双摄说明](history/DUAL_CAMERA_V0_13.md)。

## 数据、提交与交接

数据库升级前备份；测试使用临时数据，不能覆盖真人历史。虚拟环境、模型二进制、日志、原始整包、个人数据与 QA 临时文件均不提交。

每次完成代码、配置或文档更新，运行适合的检查后提交并推送 `origin` 对应分支，再用 `git ls-remote origin refs/heads/main` 等核对远端 SHA。当前主分支为 `main`。未完成目标更新到[交接清单](HANDOFF.md)，运行证据写到 `docs/validation/`，阶段说明放到 `docs/history/`。
