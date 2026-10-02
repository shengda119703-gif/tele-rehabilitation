# 居家康复助手

**当前 main：正式 PySide6 居家康复助手产品基线（2026-10-02 Final Integration）。** 首页、AI 康复管家、康复、健康、用药、家庭、历史与报告及通知/设置，使用原康复 Runtime/SQLite 和 Ankang TypeScript ProductService，通过本机 Python/Node bridge 集成。Voice/sync/HealthKit/设备等外部接口已迁入，真实平台接线与验收仍按各模块限制执行。

**当前 `codex/product-ui-v1`：** 完成功能接线后开展[运行依赖与旧代码清理](docs/validation/REPOSITORY_CLEANUP_2026-10-02.md)。已移除无正式依赖的 Ankang React UI、浏览器 demo/设计演示、独立 Home Twin/Route2/3DGS 和旧独立 Assistant 验收窗口；保留业务/core、外部 adapters、原康复 UI/Runtime 与历史说明。完整迁移快照仍在 Git/stage1，空间文档集中到 `docs/archive/ankang-route2`。main 尚未包含本轮 UI 分支清理。

合并前[完整审计](docs/validation/FINAL_INTEGRATION_AUDIT_2026-10-02.md)、[逐文件对照表](docs/validation/FINAL_INTEGRATION_FILE_AUDIT_2026-10-02.csv)、[main 启动与集成验收](docs/validation/MAIN_INTEGRATION_ACCEPTANCE_2026-10-02.md)。后续 UI 在 `codex/product-ui-v1`，不直接在 main 进行大量视觉修改。

以下为保留的康复子系统说明。Windows 本地桌面程序，用普通摄像头或本地录像进行动作观察、评估记录和训练提示。当前 **0.18.0 自动康复闭环版** 会读取本人有效评估，自动汇总身体测试情况并生成每轮最多 4 项的基础活动安排，无需逐项填写动作、次数和组数；训练中继续计次、检查已设置目标与可见动作问题，结束后记录感受并推进下一项。现有 53 项动作和左右侧均已接入；明确疾病、术后方案和真人临床有效性仍不作承诺。

**本机启动：双击 [启动康复助手.cmd](启动康复助手.cmd)。** 第一次从 GitHub 获取源码的电脑，需要先准备运行环境，见下方安装命令。启动不会自动开启摄像头。

![原康复子系统身体部位导航参考，非当前正式产品首页](docs/images/home.png)

## 从哪里开始

1. 打开软件，选择或新建当前用户。
2. 点击“打开摄像头并测试”，检查画面后关闭测试。
3. 在身体评估中点击身体部位和动作；首次可从肩外展开始。
4. 打开正式预览，按该动作提示确认侧别、机位和所需起点，再开始评估。
5. 完成并保存，进入“训练中心”，点击“根据评估自动安排 / 继续训练”；核对当天适用条件后，按顺序完成每一项。

独立相机测试只检查画面，不做动作识别、不保存评估。动作分析采用“先选择动作，再观察对应过程”的方式。腕、踝和手指任务需要单独准备可选关键点环境。

双摄接好后点“刷新”，勾选“**双摄：正面＋侧面**”：上方选择正面相机，下方选择侧面相机，先测试两路画面。正式预览时需确认两路拍到同一人；所选动作自动使用对应主机位，另一机位记录辅助二维指标。详见[双摄使用与验收](docs/history/DUAL_CAMERA_V0_13.md)。

| 阅读入口 | 内容 |
| --- | --- |
| [银发健康守护](docs/history/SILVER_HEALTH_V0_16.md) | 新入口、双摄分工、活动 / 变化卡 / 家庭回应、手机演示与限制 |
| [使用指南](docs/USER_GUIDE.md) | 相机、评估、训练、保存与故障处理 |
| [当前交接与未完成目标](docs/HANDOFF.md) | 同学做到哪一步、哪些还没完成、继续需要什么 |
| [个人训练计划库](docs/history/TRAINING_PLAN_LIBRARY_V0_10.md) | 保存多项训练安排、重开复用、版本与验证 |
| [动作时间记录](docs/history/MOVEMENT_TIMING_V0_11.md) | 出程、峰区停留、回程与连续保持；人工安排和缺测处理 |
| [纵向历史](docs/history/LONGITUDINAL_HISTORY_V0_12.md) | 按原记录条件比较、查看曲线与缺失、导出同一快照 |
| [正侧面双摄](docs/history/DUAL_CAMERA_V0_13.md) | 两路选择、独立测量、配对、停止与本轮验证范围 |
| [长期目标续建](docs/plans/PRODUCT_CONTINUATION_2026-09-10.md) | 当前推进顺序和逐阶段验收状态 |
| [顺畅完成与引导计时](docs/history/SMOOTH_FLOW_V0_17.md) | 0.17.0 的流程排查、准备复用、引导计时与手动记次边界 |
| [自动评估到训练闭环](docs/history/AUTOMATIC_REHAB_V0_18.md) | 53 项动作接入、自动计划规则、官方来源、监督与安全边界 |
| [0.17.0 本机验收](docs/validation/SMOOTH_FLOW_V0_17_2026-09-12.md) | 本轮实际命令、测试计数与不能证明的内容 |
| [0.16 整理与验收](docs/validation/INTEGRATION_2026-09-12.md) | 0.16.0 压缩包校验、3 个新增提交、本机实际测试与备份位置 |
| [开发说明](docs/DEVELOPMENT.md) | 环境准备、代码结构、分批回归和提交 |
| [完整文档索引](docs/README.md) | 规格、历史计划、原始实施包和第三方来源 |

## 首次安装

要求 Windows x64 与 Python 3.13。在仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Rehab.ps1 -IncludeLandmarks
```

官方下载较慢时，可以明确选择镜像；可选组件的 wheel 仍核对官方 PyPI SHA256：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Rehab.ps1 -IncludeLandmarks -IndexUrl https://pypi.tuna.tsinghua.edu.cn/simple
```

主环境和可选关键点环境分别安装，模型来源与 hash 随代码记录。GitHub 不包含虚拟环境、模型二进制或个人数据库。

## 项目目录

```text
项目根目录/
├─ 启动康复助手.cmd             日常启动
├─ Start-Rehab.ps1              启动脚本
├─ Setup-Rehab.ps1              首次环境准备
├─ README.md / AGENTS.md        总说明与协作约定
├─ docs/                       使用、交接、开发、规格、历史和验收
├─ rehab_codex_single_camera_v2_1/
│  ├─ app/                     应用代码与原生界面
│  ├─ assets/ / configs/        资源、模型清单与规则
│  ├─ scripts/ / tests/         开发工具与自动测试
│  ├─ requirements*.txt        固定依赖与原始参考清单
│  └─ data/ / .venv*/ …        本机数据与环境，Git 忽略
└─ backups/                    原始压缩包和整理前备份，仅本地
```

应用目录保留历史名称以兼容既有环境和数据；当前版本由 `app/__init__.py` 定义。源代码保持一个 Git 仓库，同学的提交历史已连续接入。

## 当前验证范围

这是工程 Demo。软件测试、空白帧模型推理和合成流程能证明相应程序路径工作；真人识别准确度、实际相机长期表现和使用者操作验收仍需独立记录。53 项任务不等于全部关节已完成临床评估。

同一时刻只有一个活动场景。康复双摄观察同一人，其他场景和录像仍为单路；当前双摄按接收时间配对，输出独立二维投影。实际双相机、真人准确度、曝光同步与三维融合尚未验证，实际动作示范素材仍未补齐；完整待办见[交接清单](docs/HANDOFF.md)。
