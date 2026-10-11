# 文档索引

当前电脑／托管网页主线为 **0.20.0 安康双端整合**，既有独立 APK 为 **0.2.1**；康复 v2 后端为默认关闭的 opt-in 增量，并非已接入正式五页或 APK。先读 [当前交接](HANDOFF.md) 与 [全后端功能、算法及数据流](BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md)。原双端设计见 [整合说明](plans/UNIFIED_PRODUCT_2026-10-06.md)，本机 0.20.0 核对见 [同步验证](validation/GITHUB_SYNC_2026-10-11.md)。以下规格和历史报告保留以供追溯，不能作为当前入口或本轮测试结果。

| 文档 | 内容 |
| --- | --- |
| [后端功能与技术实现阅读版](后端功能与技术实现梳理.md) | 当前逐功能输入／算法／公式／输出／消费者、真实字段交接、代码入口与优化闭环；本轮仅文档 |
| [后端阅读版当前核对](validation/BACKEND_OVERVIEW_CURRENT_2026-10-11.md) | d5c351f 基准、已提交／工作区区别、文档验证、保留文件与未重跑范围 |
| [后端阅读版此前核对](validation/BACKEND_OVERVIEW_2026-10-11.md) | d0b21d2 阶段的文档检查与当时边界，不作为当前实现验收 |
| [后端功能、算法与数据流梳理](BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md) | 三端后端域、公式／状态、逐跳信息与代码；3.7–3.8为真实字段／统计口径，22–23为优化影响及验收 |
| [部分标注的双层masked loss](development/POSE_DUAL_MASKED_LOSS.md) | 坐标／objectness分别监督、TAL标签身份、实际原YOLO梯度／更新／重载；不是正式微调 |
| [双层masked loss本机验收](validation/REHAB_POSE_MASKED_LOSS_2026-10-11.md) | 23项专项、TEST原生烟测、失败与重跑证据、完整回归和未测范围 |
| [手机姿态输入VIDEO工作流](development/MEDIAPIPE_VIDEO_AUDIT.md) | 同模型Python近似、33点原语义、源时间／像素配对与模型差异；不修改APK |
| [MediaPipe VIDEO本机验收](validation/REHAB_MEDIAPIPE_VIDEO_2026-10-11.md) | 两段真实分析授权录像、7条CLI、17项子集及177／12／19回归；不是准确率或手机性能 |
| [RGB 关键点参考与评估工作流](development/POSE_REFERENCE_WORKFLOW.md) | 权限／独立标点、缺标mask、YOLO导出、原模型预测、逐关节误差与覆盖公式；不代表微调完成 |
| [RGB 关键点工具验收](validation/REHAB_POSE_TOOLS_2026-10-11.md) | 160／12／19回归、30项工具子集、7条CLI及本机YOLO格式解析；夹具与真人证据区别 |
| [康复 v2 原生存储验收](validation/REHAB_V2_NATIVE_STORAGE_2026-10-11.md) | 实际SQLite只读／锁／容量／损坏副本、幂等重试与备份恢复；130／100项工程范围与物理故障区别 |
| [后端字段与数据契约核对](validation/BACKEND_FIELD_CONTRACTS_2026-10-11.md) | 本轮仅文档；真实字段、分母／完成口径、既有检查结果、保护范围与保留文件 |
| [后端文档与优化依赖核对](validation/BACKEND_MAP_OPTIMIZATION_2026-10-11.md) | 此前仅文档、已提交／工作区区别、日志指纹、保护范围与文档检查 |
| [后端文档此前源码核对](validation/BACKEND_MAP_CURRENT_2026-10-11.md) | 历史文档交付、当时已提交状态、现存日志指纹与文档检查 |
| [后端文档此次核对](validation/BACKEND_MAP_REFRESH_2026-10-11.md) | 已提交与工作区状态区分、日志指纹、文档验证及未测范围 |
| [康复 v2 进程与诊断验收](validation/REHAB_V2_ISOLATION_TELEMETRY_2026-10-11.md) | 所属 YOLO 进程、取消／故障保护、有界 trace 及实际 ASGI 性能 |
| [康复 v2 时间与贡献验收](validation/REHAB_V2_TIMING_PROGRESS_2026-10-11.md) | 已提交后端的时间测量、唯一计划贡献、历史及工程验证 |
| [自动评估到训练闭环](history/AUTOMATIC_REHAB_V0_18.md) | 53 项动作接入、自动身体汇总、计划来源、顺序监督及边界 |
| [0.18.0 本机验收](validation/AUTOMATIC_REHAB_V0_18_2026-09-12.md) | 本轮完整回归、界面证据和未完成真人 / 临床验证 |
| [顺畅完成与引导计时](history/SMOOTH_FLOW_V0_17.md) | 本轮排查到的问题、准备复用规则、引导计时与手动记次边界 |
| [0.17.0 本机验收](validation/SMOOTH_FLOW_V0_17_2026-09-12.md) | 本轮实际命令、计数、改过的既有契约与不能证明的内容 |
| [银发健康守护说明](history/SILVER_HEALTH_V0_16.md) | 计划映射、使用步骤、算法来源、双摄与家庭协同边界 |
| [本次整理与本机验收](validation/INTEGRATION_2026-09-12.md) | 0.16.0 压缩包来源、提交关系、备份位置及当前电脑复核结果 |
| [同学的银发增量验收](validation/SILVER_HEALTH_V0_16_2026-09-12.md) | 包内原验收记录；其环境和运行路径属于同学电脑 |
| [使用指南](USER_GUIDE.md) | 启动、相机测试、评估、训练、报告和常见问题 |
| [当前交接与待办](HANDOFF.md) | 实际功能、未完成目标、下一步所需条件 |
| [开发说明](DEVELOPMENT.md) | 环境、代码结构、测试和提交方式 |
| [9 月 10 日首次整理](validation/INTEGRATION_2026-09-10.md) | 旧压缩包来源、12 个提交、目录迁移及当时的本机结果 |
| [计划库功能与验收](history/TRAINING_PLAN_LIBRARY_V0_10.md) | 个人多项计划、重开复用、数据迁移与本轮验证 |
| [动作时间与验收](history/MOVEMENT_TIMING_V0_11.md) | 独立时间证据、目标、原生指导、报告与导出 |
| [纵向历史与验收](history/LONGITUDINAL_HISTORY_V0_12.md) | 记录条件核对、原生曲线、缺失保留与一致导出 |
| [双摄使用与验收](history/DUAL_CAMERA_V0_13.md) | 正侧面选择、双画面、独立模型、来源和停止契约 |
| [双版本融合验收](validation/MERGE_V0_15_2026-09-12.md) | 两版取舍、统一操作流程与本轮本机验证 |
| [逐步引导与结果解读](validation/JOURNEY_RESULTS_2026-09-11.md) | 本地分支原操作流程、髋点解释与报告 |
| [提示降噪与逐项有效性](history/QUIET_GUIDANCE_V0_14.md) | GitHub 分支原提示策略、倒计时和双摄门槛 |
| [双摄实施计划](plans/DUAL_CAMERA_2026-09-10.md) | 明确范围、完成状态与尚未接入的硬件验收 |
| [真实验收入口与内容清单](validation/ACCEPTANCE_READINESS_2026-09-10.md) | 53 项内容实查、空样本模板、输入检查和未验证依赖 |
| [长期目标续建](plans/PRODUCT_CONTINUATION_2026-09-10.md) | 当前阶段、后续节奏与趋势工作及验收条件 |

| 分类 | 内容 |
| --- | --- |
| [软件规范](specifications/SOFTWARE_SPEC.md) | v2.1 原规则和同学已记录的后续范围增补 |
| [产品意图](specifications/PRODUCT_INTENT.md) | 原实现目标与功能取舍；当前范围以交接清单为准 |
| [版本变更](history/CHANGELOG.md) | 原始变更记录及各阶段扩展 |
| [原产品持续计划](plans/PRODUCT_COMPLETION_PLAN.md) | 未全部完成的长期目标，保留阶段过程 |
| [原关节扩展计划](plans/JOINT_EXPANSION_PLAN.md) | 原始范围、验收方法和研究边界 |
| [历史验收记录](validation/HISTORY_WINDOWS.md) | 导入前各阶段记录，包含不同电脑上的运行结果 |
| [固定回归说明](development/REGRESSION_CASES.md) | 原回归类别；当前完整执行方式见开发说明 |
| [第三方来源](dependencies/THIRD_PARTY_NOTICES.md) | 代码、模型、依赖和素材来源 |
| [原始实施包](archive/original-v2.1/README.md) | 2026-09-06 的任务书、原始校验表和参考测试资料 |

历史测试输出中的 109、1089、1102、1450 等数量属于各自阶段；0.15 / 0.16 包内验收也属于同学当时的运行。当前版本、已提交与工作区最新核对以 [HANDOFF](HANDOFF.md) 及其有日期的验证记录为准。0.17 和 [9 月 12 日整合验收](validation/INTEGRATION_2026-09-12.md) 继续作为历史记录，不能把各次结果相加，也不能将接口回归数称为真人准确率。
