# 康复 v2 时间、唯一贡献与原计划绑定验收

日期：2026-10-11，Asia/Shanghai。上轮提交 `64b0b158fccfac695de04405eac7493b72261a9f`；本次交付以本文件所在 Git 提交为准。遵循后端实施任务书，产品仍 0.20.0、APK 0.2.1、协议 `rehab-protocol-2.0`。本轮不改 UI、Android、非康复、原处方／剂量／继续政策或用户数据。

## 1. 实际变化与信息链

```text
本人身份／同意／幂等键
 → 原保存计划 ID + revision + entry_key + 原评估 reference
 → 原自动资格或手动计划确认；已有陪同要求；输入 scope／机位复核
 → 冻结原目标／剂量／timing_plan + v2 工程参数
 → 原 YOLO + 当前逐指标证据
 → v2 计次／组次，原 MovementTiming + v2 来源封套，限时下一步提示
 → 草稿逐次检查点（坐站站起确认后，只可补观察时间）
 → 有界 finish
 → 同一事务：逐次表 + 最终快照 + 唯一回执 + 唯一计划贡献 + 审计
 → 异步报告；追加反馈 revision
 → 本人最终历史／当前版本进度 + 跨计划版本的同 scope 反馈资格
```

- `progress.py` 定义 `rehab-plan-contribution-1`。SQL 唯一键防止同一事实重复贡献；事实／贡献任一保存失败一起回滚。namespace 1→2 前 SQLite backup；旧最终回执与视觉快照不重写。
- 历史按提交 ordinal 分页，`limit=1..100`、本人 finalized cursor；计划只选当前版本每条目最新尝试，最多106条；同scope最新动作／侧反馈最多6条。UTC回退或 UUID排序不让旧成功遮住新中断；owner／来源／情境隔离。
- 临时政策视图只供原 `program_progress / validate_automatic_use` 读取，不写旧患者测量，不把新质量字段解释成旧角度或疗效。跨计划版本的不适仍参与原政策校验；自评缺失不填0。
- 手动保存计划复用原 `prepare_training_plan / validate_saved_binding`，需要 `training_plan_confirmed=true`；安排要求陪同时另需 `companion_confirmed=true`。创建前失败不保存空会话。客户端伪造target_reps／timing_plan不能替换原保存安排。
- 宿主仅肩外展与坐站；康复深蹲内部协议／时间可运行，但宿主兼容计划未完成。坐站旧非空角度目标定义不同仍拒绝。相机入口要求匹配 LIVE_CAMERA/SELF_USE 与明确机位；录像计划不能改名。

## 2. 时间含义与计次保护

新 `timing.py` 封套版本 `rehab-observed-timing-2`，复用未修改的原 `observed-timing-1`。原字段 `outbound_min_s/max_s、return_min_s/max_s、hold_min_s` 仅消费保存安排；校验有限0–300秒／null、下界≤上界、保持锚点及旧坐站下降节奏冲突，不产生新的处方。

| 结果 | 算法／观察条件 | 缺测和边界 |
| --- | --- | --- |
| 肩／深蹲出程、峰区、回程 | 完整观察后，三样本中位数的单个连续峰区≥峰值−3°；边界时间差 | 至少5样本，首末不能仍在峰区；多峰、缺测、边界未观察为null+reason |
| 坐站站起／站位／回坐 | 本次首观测→站位确认→开始回坐→坐姿重新确认 | 站起计一次；未观察回坐不能补下降时间；不是标准椅站临床时间 |
| 目标保持 | 当前有效观测的单个连续达目标时间；记录最长一段 | 无锚点null；缺测／暂停／丢帧重置实时计时，不累计多个短段 |
| 节奏结果 | 对原保存上下界逐项 MET／NOT_MET／UNASSESSABLE／NOT_SET | 不覆盖幅度、质量、确认次数或组次；部分观察不足不判患者未做到 |

峰区中位数含后一个样本，仅为结束后的回顾算法；当前保持和提示不借用它。10个间隔0.05秒的有效观测覆盖9个间隔，即0.45秒，不是0.5秒。坐站保持锚点为v2站位膝屈范围，不假称旧髋／膝个体校准。

JPEG time_basis仍是服务器接收单调时间，不是手机曝光时间；网络抖动会影响观察时长。封套保留原算法、time_basis、样本数、首末／站起／开始回坐／坐回的seq与source_epoch。录像、接收时钟、Kinect名义采样不可混称同一金标准，时间结果的专门跨来源比较契约尚未完成。

覆盖待处理新帧时，按seq前缀在下一幸存帧断开保持，不追溯污染较早的在途有效帧；待兑现丢帧期间隐藏实时保持提示。丢帧之后若仍观察到合法转折／返回，可保留确认次数但相应时间无法评价；恢复时直接跨过隐藏转折则不能补次数。

逐次表旧 INSERT OR IGNORE 会冻结坐站站起时的缺失回坐时间。本次 `_sync_repetitions` 在原事务内允许终结前时间字段扩展，并校验重复index、已有次消失、总计不一致或已确认非时间字段改变；失败回滚。结束／重开后不允许回写最终事实，避免第二个计次事件或快照分叉。

## 3. 本机实际命令与输出

产品解释器：`E:/game/health-care-software-main/rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe`。独立临时库和测试输出在忽略的E盘`.runtime/rehab_ml/run`；没有写正常用户库或启动用户相机。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py verify-sessions --database-mode isolated
```

完整运行目录 `verification-3b62b733`，退出码全部0；[regression.json](../../reports/rehab_backend/regression.json)保留实际参数、耗时、日志路径和摘要。

| 运行项 | 实际结果 | 日志SHA256 |
| --- | --- | --- |
| 新后端 unittest discover | 74项通过，20.357秒测试／21.452秒进程 | `401fac089c869c400a96021deb9c2839a4d6bd7a57bb5ee4ff65db6e129ad81f` |
| 原康复 test_app_rehab | 12项通过 | `d02a26e84c4b111c1022056c665d6658871a3550921b524b210bb8e790a5c375` |
| 原手机 test_mobile | 19项通过，1条既有Starlette/httpx弃用warning | `d737db09fa34b92605ad9d3a11f526eef3d9501d8ce9bb1ed1b52eefd0af1cbd` |
| protected文件核验 | 1308项一致，changes=[] | `f35c96d12e48a998286cfbd0b2bf7ed70c9a1a4f60946a67fc9704b8a847bdf0` |
| verify-sessions，replay-c09bc19e | 44项通过，31.968秒测试／32.890秒命令 | `a869b4310c96f6325d984f26aa4f9883043bb88fa609f18b105763b3d6c2cbae` |

44项是74项子集，不累加。[session_verification.json](../../reports/rehab_backend/session_verification.json)保存具体四模块参数。此前49／61项分别是第一阶段和未提交阶段的记录，不代替本次结果，也不借用原产品324项或Android66项来宣称本轮已测。

另以只读导入确认产品Python 3.13.12／PySide6 6.11.2，未升级依赖或打开应用窗口。五份变更文档的本地链接与代码块闭合检查通过，后端总览26张表、验收2张表、实施报告4张表的列数一致；`git diff --check`通过。这些是文档／环境核验，不计入74项测试。

时间模块12项含目标/别名校验、合法往返、未达节奏仍计次、因果保持与下一步提示、遮挡/预测/过期拒绝、暂停/长间隔/换人/尺寸变化、站起即结束、深蹲共享提示、latest-frame前缀、坐站草稿更新/重开/单一贡献、崩溃恢复不补回坐、已确认计次篡改回滚。HTTP新增手动计划用原Storage和原保存计划，独立TEST上下文；白色JPEG经原YOLO不检测出人，不以此证明真人计次准确率。

## 4. 失败与修复记录

1. 前阶段增加显式submode检查后，崩溃探针原fixture缺submode，曾使回归失败；明确assessment后恢复。本次保留[失败报告](../../reports/rehab_backend/regression_before_mode_fix.json)，不把失败计为通过。
2. 时间测试首轮11项，4项失败：三项复现逐次表不更新／缺确认事实保护；一项误将10样本时长写为0.5秒。实现草稿同步保护，并按9间隔修正断言。下一轮10通过／1失败为测试期待的错误码与先触发的count_mismatch不同；分开测试两个独立保护，随后11项通过。
3. 增加丢帧前缀测试后12项中1项失败：恢复后仍观察到合法转折的动作可以计次，不能断言一定为0。拆成“已观察转折可计但时间无法评价”与“跨隐藏转折不可计”，最新完整74项已覆盖通过。这是纠正验收预期，不是放开隐藏证据规则。
4. 独立CLI首次漏传必需的`--database-mode isolated`，参数解析退出2，未运行测试；补参数后44项退出0。没有把命令调用失败当测试成功。

早期聚焦输出来自工具会话，最新完整日志保存在上述目录并记录SHA。未重跑训练、两段私人原片或完整产品／UI／APK验收。

## 5. 剩余边界与入口

- 默认`create_app(..., rehab_v2=False)`不装新入口；本轮未启用／重启用户服务。原`/api/live`删除仍只删除预览；原`/api/plan`、旧历史、五页和APK不改。
- 推理／报告仍为线程；硬挂起隔离、磁盘满／真实损坏与容量压力、完整端到端trace未完成。时间专项可比性、曝光时钟与临床参考误差、专业RGB／动作标注、姿态微调和实机验证未完成。
- 原数据训练候选仍默认关闭；Kinect25不能跨接手机RGB。测试只能证明隔离工程契约，不证明临床疗效／时间精度或任务书全部完成。
- 用户动作图片、exercise-guides/README改动、导入脚本／CSV及本机任务书保留，不纳入本轮提交。环境、权重、录像、测试库与日志遵循已有ignore。
- 桌面“安康康复（最新版本）”在提交后刷新描述，仍指向当前仓库Start-Rehab.ps1与已验证pythonw。页面导航仍首页／康复／健康／用药／家庭；客户端版本仍0.20.0，APK0.2.1，本次只是后端增量。

功能全景、公式及优化实验见[后端梳理](../BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md)；阶段事实见[实施报告](../../reports/rehab_backend/IMPLEMENTATION_REPORT.md)。
