# 后端阅读版：全功能交接与可靠性优化核对

日期：2026-10-11，Asia/Shanghai。已提交源码基准：`cec4dcb55850dff09579be6b1d5da952b489a6b9`。

## 本次交付

按用户请求整理 [后端功能与技术实现梳理](../后端功能与技术实现梳理.md)，沿用全功能总表、逐功能技术方法／公式／输出／消费者、真实字段、函数入口和误差评价。新增：

- 1.3：算法结果、业务事实、派生展示及不同后端的分界。
- 3.4：归属、输入、定义、时间、可测性、依据、保存、权限的逐跳信息。
- 15.4：超时、录像／APK中断、v2提交／报告／自评、照护回执和训练中断的恢复对象。
- 25：错误定位到优化实验、经验可信度评价、下游对照产物和建议推进顺序。

本次只有阅读版、README索引、HANDOFF新增段落和本记录四份文档。没有实现新算法、修改业务／UI／Android、运行训练／推理／完整业务回归、分析私人录像、操作正常患者库、构建APK或启停服务／相机。第22、25节中的候选公式和实验是供团队选择的后续方案，不是假称当前已经实施的能力。

## 源码与状态对照

| 范围 | 核对依据 | 本次明确的边界 |
| --- | --- | --- |
| 输入与视觉 | domain.py、quality.py、vision.py；PacketGate、PoseFrame、Metric、焦点与EMA | 人物轨迹不当身份；源时间与处理耗时分开；手部点不伪造confidence |
| 评估与计划 | assessment.py、automatic_plans.py、training.py、joint_calibration.py | 最新评估、范围和工程准入、冻结依据、组次／质量／自评分开 |
| 健身／体态 | fitness.py、posture.py、barbell.py及APK对应实现 | 二维几何和标定器械估计分别说明；手机采样及算法不等同电脑 |
| 健康与管家 | events.ts、baseline.ts、detect.ts、ProductBackend、既有照护黑箱记录 | 归属／时间／否定／单位先于统计；事件、摘要和回执不是同一层事实 |
| v2提交与资源 | resources.py、SessionService.create／rebuild_report、SessionRepository.finalize／feedback／report_state／report_work | 已提交双锁准入、默认报告延期／所属抢占、反馈CAS和唯一贡献；不推广到全产品 |
| 跨端版本 | app/__init__.py、AndroidManifest.xml、android_offline/package.json、motion.js／engine.js／local-api.js／worker.js | 电脑0.20.0、既有APK0.2.1；源码、安装包和运行服务分开 |
| 离线研究 | 已有pose训练工作流；当前工作区pose_resume.py／pose_training.py／cli.py及既有报告 | 条件式训练器已提交；显式续训为未完成工作区增量，不捎带发布 |

续训只读证据：`reports/rehab_backend/pose_resume_verification.json`，run `pose-resume-audit-02c46238`，`passed=false`，失败为 `native_resume_not_equal_to_uninterrupted_optimizer_and_order`。报告中的45项单元检查和实际续训命令退出0，不改变该总判定。本次不重跑、不修改其源码或报告，也不将工程夹具结果写成真人精度。

## 文档与保护检查

本次检查仅核对文档结构、源码定位、功能目录及文件保护，不进行完整运行验收。实际结果如下；任何历史回归计数都不作本次重跑。

| 检查 | 实际结果 |
| --- | --- |
| 功能总表 | 34项主要后端能力 |
| 阅读版结构 | 26张表格列数一致，44个代码围栏标记闭合 |
| 四份文档本地链接 | 阅读版166、README58、HANDOFF67、本记录1，共292个，缺失0 |
| 文档Git空白 | 本次四份文档差异检查通过 |
| 本机只读目录导入 | Python3.13.12，产品0.20.0；康复53、健身8、体态2；不加载模型、不启动应用 |
| 原保护文件 | 1308份SHA256重算，变化0，原manifest未重建 |
| 开工既有改动复核 | 286份数量与聚合SHA256前后一致，变化0；未捎带提交 |

只读导入使用原`.venv/Scripts/python.exe -X utf8 -B`、`PYTHONDONTWRITEBYTECODE=1`和E盘临时目录。结构检查直接读取四份Markdown，核对表格、围栏与相对路径；保护检查只读重算已有manifest的1308份文件。没有安装依赖或下载模型，没有产生新的业务／训练验收结果。

保护基准：`reports/rehab_backend/protected_files.json`，SHA256 `75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`，未重建。当前实际重算1308份文件，变化0。

开工工作区快照包含286份既有改动：用户素材／任务书／CSV／脚本和未完成续训增量。按仓库相对路径排序、以UTF-8 `路径|SHA256`逐行拼接的聚合SHA256为 `55778acf6b0a9c86c5cb77669975aedf7df007818af50d66f3e3e78bcb284004`。本次新增四份文档不在该快照内；交付前只复核这些原文件，不重建原保护基准、不清理实验目录。

## 仍需独立验收

真人训练权限／独立标注／专业参考、候选同域收益、续训一致性与故障恢复、康复深蹲正式宿主计划、原业务与v2适配、全部入口资源协调、目标手机／长时负载／物理故障、真实家庭渠道等仍未完成。存在源码、单元测试通过、两模型一致或录像能回放，不替代这些证据。

本次文档单独提交并推送origin/main；核对远端SHA。桌面入口继续使用原 `Start-Rehab.ps1`、本机验证的 `.venv/Scripts/pythonw.exe` 和现有E盘恢复目标，仅刷新Git版本描述，不启动或关闭用户应用窗口。
