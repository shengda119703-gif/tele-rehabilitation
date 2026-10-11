# 康复后端实施与真实训练：阶段记录与增量交付

日期：2026-10-11（Asia/Shanghai）。第一阶段实施基准：`b6d22fc392915738401fe6e14d9cc32b877a5acc`，提交`1463929`；所属推理／诊断`129e5cb`，报告隔离`06366bd`，时间／贡献`23696de`，原生存储`a9e31cc`，关键点工具`bf698a3`，VIDEO对照`d0b21d2`，双层masked loss`d5c351f`。本轮条件式多轮训练最终实施／复验基准`7647037c956f3bcef6a0486b797ab9f667820879`，以本文件所在交付提交为准。任务依据：本机`docs/安康康复训练后端实施与训练任务书.md`。产品仍0.20.0、APK0.2.1，协议`rehab-protocol-2.0`，不是新客户端发布。

结论：P0–P4 的核心链路与一部分 P7 已实际完成。下载了真实获许可数据，训练了两个真实模型，也发现候选没有优于简单基线。正式会话为独立 opt-in 后端，尚未成为现有 UI/APK 的正式路径。P5 只有两段分析授权录像回放，缺独立参考标注；P6已有条件式多轮姿态训练器，但没有合格真人微调或产品影子上线。整个任务未完成，不能据此宣称真人准确度提高。

已有增量接通唯一贡献、最终历史、原继续政策、冻结计划、显式时间、所属推理／报告、原生SQLite故障边界、关键点工具、同权重Python VIDEO及双层masked loss。本轮新增真正多轮优化、train增广、val选模／早停、冻结best后的test、检查点／模型卡、状态／取消，并修复内部失败写入边界。最新完整 **230项新后端、12项旧康复、19项旧手机通过**，1308保护文件一致；30项训练专测是230项子集。实际run／SHA／失败及限制见 [多轮训练验收](../../docs/validation/REHAB_POSE_TRAINING_2026-10-11.md)。此前200项双层损失、177项VIDEO、160项工具、存储、报告、推理与时间验收保留历史不累加；本轮未重跑IRDS训练、真人原片、会话CLI或性能benchmark。没有真人微调或准确性改善结论。

## A. 实际完成情况

| 工作 | 状态 | 实际证据 | 剩余限制 |
| --- | --- | --- | --- |
| P0 盘点与保护 | done | [开工清单](../rehab_backend_inventory.md)、[1308 文件基准](protected_files.json)、[末次 hash 核验](scope_verification.json) | 仅本轮范围；不代表其他会话或临床验收 |
| P1 三动作后端协议 | done（工程定义） | `app/rehab_v2/protocols.py`、`engine.py`、`rounds.py`；15 项协议回放及几何契约测试 | 定义是二维投影和训练观察，不是解剖 ROM 金标准；实际机位仍由计划给出 |
| P2 正式会话与幂等 | partial | 230项新后端回归，含原生SQLite12项；真实YOLO/JPEG、报告挂起／退出、释放重试、反馈CAS与HTTP | 旧页面未接入，深蹲尚无宿主兼容计划；物理存储故障与完整压力验收待做 |
| P3 IRDS 下载与适配 | done | 198,985,485 字节骨架 ZIP、1974 字节 readme；CRC/MD5/SHA 校验；534 条/29 人，532 训练资格、2 隔离 | Kinect25 三维肩外展，不是手机 RGB、坐站或深蹲标签 |
| P4 模型训练 | done（离线实验） | [实验包摘要](experiment_summary.json)，两次完整训练链结果；检查点、验证/测试预测和锁文件均存在于忽略目录 | TCN 测试 macro-F1 低于 logistic；只整次正误，不可作为相位/提示/诊断 |
| P5 真人目标域验证 | partial | [此前回放](target_replay_summary.json)、[上轮两原片YOLO／MP](mediapipe_video_verification.json)，443／429帧时间＋解码像素配对 | 新协议均0确认次数；无专业真值，不能计算计次准确率或以模型一致性证明正确 |
| P6 姿态微调 | partial；真人训练缺资格 | 转换／独立评估、双层loss、[多轮训练及真实工程验证](pose_training_verification.json)、[监督资格记录](pose_supervision_blocker.json) | train颜色增广／多轮／val选模已实现；缺合法真人RGB／独立参考／同集原误差基线与真人候选对照，不自动上线 |
| 候选后端接入 | offline / off | [冻结模型对照](model_comparison.json)，Kinect 匹配返回非权威候选，RGB 被拒绝 | 未在实际服务加载新权重，没有正式质量判断/提示接管 |
| P7 回归与交付 | partial | [回归日志与hash](regression.json)、原生SQLite故障、[历史实际会话性能](session_performance.json)、[历史CPU微基准](performance.json)、本报告与复现工具 | 无人空图负载、ASGI而非公网；尚缺真人、实机、全负载及物理存储故障 |
| 禁改范围 | pass | 1308 个 protected 文件 SHA256 一致；唯一现有业务文件改动为 `mobile_rehab/server.py` 的 opt-in 康复入口 | 用户本来未提交的动作图片、脚本、CSV、任务书仍原样保留、不纳入本次提交 |

## B. 修改清单：问题、实现与验证

### B1. 动作、观测、组次与提示

新增 `rehab_codex_single_camera_v2_1/app/rehab_v2/`：`__init__.py`、`protocols.py`、`evidence.py`、`engine.py`、`rounds.py`、`cues.py`、`temporal.py`、`sessions.py`、`compatibility.py`，本次补 `progress.py`、`timing.py`。

| 问题 | 实现 | 新行为 | 验证 |
| --- | --- | --- | --- |
| 肩主角度受腕/髋缺失阻断 | 复用 PoseAnalyzer 的肩肘图像垂直角；可选质量指标独立 mask | 肩肘有效可测；腕缺失肘质量 unknown，髋缺失不补造躯干质量 | C01 |
| 稳定站姿被当坐姿基线 | 协议起点同时要求姿势和持续稳定，坐站以膝屈曲观察坐姿 | 站着进入不计起立；站立后必须再观察坐回才能重装下一次 | C04/C05 |
| 遮挡/旧帧/预测补次 | 每指标 observed/computed/age/joints/kind；源 epoch、单调 seq/time、模型/几何契约门控 | 缺测不累积保持；隐藏转折只能 partial/UNASSESSABLE；预测不授权确认 | C02/C03/C08/C09 |
| 恢复后平滑器被旧结果污染 | 姿态推理与 EMA 分离；检查控制 epoch 后才更新 EMA，恢复重置滤波；gap边界沿用计划 | 暂停期间返回的旧推理不会更新相位、次数或平滑状态 | C08 慢推理故障注入 |
| 深蹲以髋高度替代膝角 | 直接采用 `180°−膝内角`；没有髋/膝/踝时该指标不可用 | 浅屈膝完成次数与个人幅度目标分开，非健身深度分数 | C06 |
| 组次/休息与视觉次数混在一起 | TrainingRounds 只编排明示的 reps/sets/rest，不生成新剂量 | 坐站到站立计次，但坐回后才结束组；休息/暂停不计；恢复核对给定休息 | C10 |
| 历史错误不断触发提示 | 当前有效质量约束与已完成次的历史问题分离，复用原 GuidancePolicy | 一条当前事件，证据引用、相位/epoch/TTL、取消；动作改善后旧纠正取消 | C11；取消/发出写审计 |
| 新视频被当作不能比较 | compatibility 与具体 evidence_fingerprint 分开 | 新 session/job/source identity 本身不阻断绝对投影角比较；相对幅度仍保留基线条件 | `test_contracts.py` |
| 明确节奏安排被 v2 拒绝 | 复用原 MovementTiming 和 timing_for_plan，加版本／时间基准／证据封套 | 出程、回程、保持与计次独立；缺测不补时间，完整往返后才做峰区分段 | `test_timing.py` 12 项，含持久化 |
| 坐站回坐时间未同步逐次表 | 同事务同步草稿时间扩展，同时校验已确认计次事实不可改 | 站起仍计一次；坐回时间在终结前补齐，终结后快照／回执不重写 | 时间持久化、重开、篡改回滚测试 |
| 覆盖新待处理帧污染较早在途帧 | 丢帧按 seq 前缀兑现，期间隐藏实时保持提示 | 旧有效帧可处理，下一幸存帧不得跨丢帧累计保持；隐藏转折不补次 | latest-frame replacement 时间回放 |

没有改原 `runtime.py`、`quality.py`、`rehab.py`、`training.py`、`guidance.py`、`storage.py` 或域对象。新路径组合原组件；旧引擎保持原结果。没有增加处方、继续资格或训练剂量决策。

### B2. 会话与数据库

新增 `mobile_rehab/rehab_v2/{__init__,api,service}.py`。现有 `server.py` 只在显式 v2 块增加安装、计划解析／查询及关闭回收；默认不启用。新宿主解析现有本人自动或手动保存计划的 ID、revision、entry_key、证据引用和已有资格，不接受用户关键点来伪造相机观测。手动计划复用 prepare_training_plan／validate_saved_binding，要求 training_plan_confirmed；安排要求陪同时另需 companion_confirmed，不让请求覆盖原剂量／节奏。

新增 namespace 表：`rehab_v2_meta/sessions/operations/frames/repetitions/audit/feedback/reports`，本次加 `rehab_v2_plan_contributions`，namespace 从 1 迁移到 2。使用原 Storage 的数据库 owning thread；原 `PRAGMA user_version=4` 不改。迁移前用 SQLite backup 保留一致副本；v1 最终事实回填贡献但不重写原回执／视觉快照。实际宿主 v2 使用独立 `rehab-v2.sqlite3`，不把测试写进正常患者库。

事实链：认证本人 → 查创建幂等记录 → 核验现有计划/明示剂量与节奏 → 冻结计划与来源 → JPEG原模型推理 → 逐次检查点及时间更新 → 控制 revision → 冻结接收边界 → 有界收尾 → 单事务最终逐次事实/快照/回执/唯一贡献 → 独立派生报告 → 追加反馈及审计 → 本人最终历史／原政策进度查询。

- 创建、frame event/seq、操作键和 repetition index 有 SQL 唯一性；同键改载荷冲突。已提交/正在执行的重复请求先查回执，再检查新前置条件。
- 并发不同 finish key 只能得到一个 commit_id；accepted/processed/persisted seq 分开，丢帧/超时未处理逐项记证据，terminal 之后晚结果不修改快照。
- 逐次确认增量保存；实际子进程 `os._exit(27)` 后重开保留1确认次，未确认半次保留为无法评价并终结 interrupted，不能 resume 已 finalized。
- 解码/推理异常明确保存 frame failed，终结input_failed，而非永远留在准备中。持久化自身不可用不能保证写下失败事实；本轮原生SQLite故障退出消费者并保留固定运行态故障，物理介质故障仍待验收。
- 报告生成异步，不延迟最终回执；pending/failed 可在重启对账。反馈 revision CAS 防止旧报告覆盖新反馈。报告失败不会倒退已保存事实。
- feedback missing/null 保持缺失；自报不会改原视觉快照，反馈追加不重复增加执行量。
- 本次新回执标记 `unique_v2_contribution_committed`；唯一贡献与最终事实同事务，故障注入证明贡献失败一起回滚。旧回执保留其原标记。本人最终历史按 ordinal 游标分页，单页 1–100；计划查询只取当前版本最新条目尝试，并在同人／来源／情境／动作／侧别范围读取跨计划反馈。复用 `general-activity-rules-1`，不写旧测量，不把 v2 质量解释成旧 ROM。现有历史页面和 `/api/plan` 仍未接入。

### B2.1 最新所属推理进程与诊断（本轮）

新增 `mobile_rehab/rehab_v2/pose_worker.py`，只复用原 VisionWorker／YOLO 的解码和推理，宿主仍负责时间、EMA、状态机、SQL 和原继续政策。512 KiB JPEG + 4 MiB 姿态 JSON 的共享内存只由父进程拥有；≤4 KiB 的管道通知不传外部 Python 对象。父进程核对载荷 hash、ticket、完整 Context、seq、源时间和有限耗时，再检查控制／终结 epoch，才处理 EMA。启动握手／冷推理／热推理预算 10／30／5 秒；只释放准确所属对象，未确认退出时隔离并保留清理句柄，不能另起泄漏进程。成功后清空传输区，失败后确认退出再清理；不宣称存活模型 RAM 全部擦除。Process.start 本身尚未有 OS 级硬截止。

帧消费者因持久化故障退出后，来源运行态failure可查，新帧／新建返回503，不能虚构失败已保存。终结先保存事实，再取消该sid在途推理；旧失败不能结束恢复后的新control_epoch。关闭若资源仍未确认释放则明确失败，后续可再关闭，不提前释放lease。本次默认报告隔离见B2.2；可信本地callable仍为线程，真实磁盘满／损坏尚未完成，OSError注入仅证明对应故障路径。

新增 `app/rehab_v2/telemetry.py` 与认证诊断路由。服务端 trace_id 放入 source 元数据，创建重试／重开稳定，不加入客户端幂等摘要；JPEG 会话 `job_id=null`。每个固定阶段保留 512 个耗时、事件尾部 128 条；计数累计，分位数为保留窗口 nearest-rank。队列／解码／推理／IPC往返／特征／规则／指导／检查点／控制／最终提交／报告／结果年龄分别统计，旧 commit_ms 数组只是检查点兼容，不称最终提交。关闭候选不伪造 temporal 耗时，未知 RSS／重启统计保持 null。只有所属会话鉴权后可读，不含原媒体、骨架、用户原话、owner 或凭证；诊断不参与测量、计划或最终事实摘要。

新增 `tests/rehab_backend/test_isolation.py`（17 项）、`test_telemetry.py`（9 项），扩展真实 JPEG 与身份 HTTP 测试，CLI 会话集纳入两者。新增 `tools/rehab_ml/session_benchmark.py`／`benchmark-sessions` 和 [性能摘要](session_performance.json)。实际测试覆盖真实所属挂起／退出、共享区容量与 hash、取消后不重开旧帧、释放未确认后重试、失败检查点拒收、报告慢任务不阻断控制、统计有界／并发／未知和正式事实不变。

### B2.2 本次默认派生报告所属进程

新增 `app/rehab_v2/reporting.py`、`mobile_rehab/rehab_v2/report_worker.py`与共用`owned_worker.py`。报告保持原10字段，不接LLM／新处方／新质量规则。仅已finalized的本人白名单快照进入单槽；2 MiB输入＋2 MiB响应、≤4 KiB通知，默认握手10秒／工作5秒／terminate及kill各等待1秒。子进程无相机／SQL，宿主校验SHA、ticket、sid、反馈revision类型和值、输入hash、有限compute_ms及原事实报告digest，再用旧反馈CAS提交。初始实际执行契约写入source；本地callable钩子明确为trusted_local_callable且无硬取消，不作为公共请求配置。

报告超时／退出只写派生失败；事实、canonical_commit、唯一贡献不变。重试／重开可重建；busy返回running且不写失败。共享区成功后清空，失败确认所属退出后清理，释放未确认保留句柄和存储lease并允许重试关闭。SQL派生写失败在backend_execution／diagnostics可查，pending保持可恢复，不能声称故障已保存。新增report_compute_ms、report_roundtrip_ms及report_timeout／cancelled／busy；整次report_ms还包含宿主核对和写入。RSS只对本sid实际在途报告读取，空闲／未知为null。

18项专测包括纯默认构建和传输复用、容量／身份／内容篡改、真挂起与退出、超时取消、清理未确认、关闭释放与重开补建、反馈CAS、并发busy、鉴权、草稿拒绝、本地钩子关闭失败和受控SQL错误。没有真实磁盘故障、真人准确性、手机或全负载证明；OS Process.start本身与宿主序列化／纯核对没有单独硬截止，不称整个报告链绝对实时。

### B2.3 本轮原生 SQLite 故障边界

新增`RehabStorageBoundary`，只适配原Storage owning thread，不加连接／队列／写入器。初始化后busy_timeout250ms，按实际sqlite_errorcode分类容量、只读、锁、损坏、I/O及打不开；原业务约束和SQL代码错误不转换。固定HTTP503附不确定提交语义，无SQL／私密路径／伪回执；恢复后查commit再用原键重试。损坏原件保留，不自动重建。检查点存储失败与input_failed分开，停止消费者且确认所属资源释放；最后观察故障只在运行态，不冒充数据库健康或已保存。

12项实际SQLite测试使用E盘小型TEST库：mode=ro／query_only、外部BEGIN IMMEDIATE写锁、max_page_count与256KiB事务内分配、损坏副本文件头、SQLite Backup API恢复到新路径。验证最终事实／报告／贡献事务回滚、控制和反馈不推进、恢复后幂等重试、派生报告重建、损坏文件不覆盖、检查点失败拒收及HTTP边界。物理磁盘没有被占满，NOTADB副本不是B-tree或介质损坏，已知备份不恢复未存在事实；IOERR／CANTOPEN本轮没有硬件故障实测。

此前同代码完整130／12／19项及CLI100项日志已核对，本轮另存储12项／12.689秒通过。命令、初期游标清理失败及fetchone修复、日志SHA和范围见 [存储验收](../../docs/validation/REHAB_V2_NATIVE_STORAGE_2026-10-11.md)。正式UI／APK／旧Storage实现／非康复不改，v2默认关闭。SQLite锁等待预算不等于整个请求、Future或初始化硬截止。

### B3. 数据与实验工具（第一阶段，保留）

新增 `tools/rehab_ml/`：common、inventory、download、data、features、models、training、benchmark、target_domain、model_registry、visual_audit、crash_probe、summarize_target、run_minimal、verify_all、cli及README。新增 `configs/rehab_ml/{datasets,baseline,tcn,backend}.yaml` 和 `annotation-template.json`。

新增 `tests/rehab_backend/{test_protocols,test_sessions,test_api,test_contracts,test_ml}.py`，本次补 `test_progress.py`、`test_timing.py`。报告为本目录及 `reports/rehab_backend_inventory.md`，交接更新在 `docs/HANDOFF.md`。

下载器校验固定版本/字节/MD5，.part续传，206核对偏移；200不追加旧片段，完整损坏文件隔离，最终原子更名。ZIP检查目录穿越、链接、体积/文件数、压缩比、Windows保留名及大小写别名，CRC实际通过。原始数据/模型不提交Git。

标注模板分开物理完成、可观察完成、阶段、错误、提示机会、专业复核、训练授权和各任务mask；unknown没有被编码为正确或负例。第一阶段姿态CLI只有资格检查；本轮转换、旧模型预测与独立误差评估已实际实现，见B3.1，`train-pose`仍明确拒绝且不算完整训练链。

### B3.1 RGB 关键点转换与独立参考评估（bf698a3交付）

新增`pose_dataset.py`、`pose_inference.py`、`verify_pose_tools.py`、30项`test_pose_dataset.py`和`pose-reference-template.json`；扩展CLI／target_domain监督记录，不改正式运行路径。参考清单校验权限文件、原图hash／尺寸／EXIF、COCO17左右顺序、匿名人／录制／帧／时间、独立人工复核与完整人体框；人员、录制和同图hash不能跨train／val／test。输出只新建于忽略的实验data／run目录，不覆盖已有产物。

`build-pose-dataset --reference`分别导出masked原值及坐标／objectness双mask，或完整17点的YOLO标签＋YAML＋provenance。锁定Ultralytics8.3.199的loss表明未标点写0仍进入objectness BCE，所以部分标注拒绝stock YOLO格式，不补零或筛走缺标样本；明确不可定位的人工0另行处理。三份TEST导出通过该版本`verify_image_label`真实解析，前后hash一致；格式通过不授予训练资格。

`infer-pose-reference`复用原manifest／权重hash、所属spawn YOLO／CPU640／容量和取消机制，不接相机或SQL。原图不缩放，但明确重编码quality95 JPEG，两个hash分别保存；按参考框唯一IoU匹配，不匹配或多候选不产有效点。每张图重置context，不是连续tracker或无辅助端到端验收。

`evaluate-pose`核对清单／图片／人物／录制／帧序／源时间及预测格式；像素欧氏误差和bbox对角线归一误差只对有效覆盖点计算，缺预测仍计覆盖／PCK_all分母；空参考或空覆盖保持null。输出逐关节／人／动作／视角／visibility分层、逐点证据、疑似左右交换及有限样本roundtrip分位数；不是角度金标准或疾病判断。候选声明不能用test训练／选模，但不证明第三方预训练无重叠。

专项`pose-tools-57a19221`实际跑30项与7条CLI，包括原模型无人图，覆盖0、误差null，缺标／缺资格训练按预期拒绝。公式、命令及验收见 [工作流](../../docs/development/POSE_REFERENCE_WORKFLOW.md) 和 [本轮验收](../../docs/validation/REHAB_POSE_TOOLS_2026-10-11.md)。夹具明确SYNTHETIC／TEST；私人录像没有训练许可，IRDS不是RGB参考，没有新增真人精度或真实微调结果。

### B3.2 Python MediaPipe VIDEO 输入近似（d0b21d2交付）

新增`mediapipe_video.py`、`pose_video_compare.py`、`verify_mediapipe_video.py`及17项测试。新增CLI默认只离线处理明确授权文件；现有landmark环境子进程加载原full.task，VIDEO／CPU／单人／原三个0.5阈值；原IMAGE组件、APK与产品依赖不改。原文件hash在开始／结束核对，恒定原尺寸、原PTS、解码BGR SHA、33点visibility／presence／图像z保留；world不进入几何。仅原有限几何适配，不增加剂量／质量／诊断政策。

单个所属对象默认等180秒，超时／取消对准确对象terminate／kill各等2秒，释放未确认失败；OS Popen创建无独立硬截止。17项覆盖源时间、原像素／骨架、置信语义、缺失、配对、领域与受控取消，以及真实4帧白色TEST视频加载／退出。受控Popen不是原生死锁，白图不是真人。全过程不接摄像头／SQL／前端。

真实两原片重新用原YOLO与MP处理；同视频、动作／侧、PTS、尺寸、BGR SHA通过后，按解剖关节名比较共享点和过滤后的投影角。肩443共享帧（MP额外1首帧）、共同有效424帧的主角差均值4.491°／p95 10.405°；深蹲429共享帧，YOLO48有效／MP0，不产角差数值。两模型新协议次数均0，没有真值、训练或准确度结论。SDK与解码／内部tracking不同，不以运行耗时写速度提升；详见 [工作流](../../docs/development/MEDIAPIPE_VIDEO_AUDIT.md) 及 [验收](../../docs/validation/REHAB_MEDIAPIPE_VIDEO_2026-10-11.md)。

### B3.3 部分关节标注的双层损失与原 YOLO 工程烟测

任务书12.2新增`pose_masked_loss.py`、`pose_masked_smoke.py`、`verify_pose_masked_loss.py`和CLI`smoke-pose-masked`。锁定本机Ultralytics8.3.199及原loss.py hash；继承原检测、DFL、gain和TaskAlignedAssigner，不修改安装库。坐标mask为明确已标且visibility>0，objectness mask为明确已标；未标点不作负例，已复核无法定位点仍监督objectness。按同图GT ordinal取得同一对象标签／mask，拒绝越界和非法数值；空监督为连图零损失，失败清空mask，并发同实例拒绝。

原生烟测只接受有training权限的TEST工程参考，每次新建所属进程／忽略输出，只train图进入张量，resize／letterbox使用实际整数尺寸及轴比例同时变换框和关节。真实原YOLO在CPU、128像素、2线程运行前向／TAL／反向／SGD一步，然后保存新的TEST检查点并严格重载；原权重前后hash不变。默认所属等待120秒，取消只操作准确所属句柄；OS创建和文件读取不是硬截止，释放未确认不报成功。

末次`pose-masked-audit-d8188b3a`：23项单测和3条CLI按预期退出0／0／1。原YOLO实际分配10前景anchor；未标输出梯度0，已复核缺失点objectness仍有梯度；更新参数digest变化，重载最大输出差0。受控取消、真实原生正常退出和真人训练分开，失败run保留。公式、原值、hash、原生与受控证据见 [工作流](../../docs/development/POSE_DUAL_MASKED_LOSS.md) 与 [验收](../../docs/validation/REHAB_POSE_MASKED_LOSS_2026-10-11.md)。

本节历史一步烟测不是完整训练器，后续多轮实现见B3.4。没有新增真人RGB监督、专业投影或同集微调对照。`train-pose`的缺资格拒绝仍在；TEST权重`fixture_only=true`、`product_enabled=false`，不接产品／APK。

### B3.4 条件式多轮姿态训练、验证选模与取消

新增`pose_training.py`、`verify_pose_training.py`、严格JSON配置模板、`train-pose --config`和`cancel-pose-training --run-dir`；30项训练测试。资格检查在创建输出和子进程前完成，research只接受独立human／RESEARCH，TEST夹具不授予真人训练资格。按人／录制／图像隔离train／val／test，初始空间预算、图像大小、线程、batch、epoch和时间均有上限。

训练保持原YOLO检测／TAL／双层masked loss，train-only亮度／对比度、实际整数resize／letterbox、AdamW、梯度clip和冻结层／BN核验。每轮使用模型副本评val，按全部定位参考PCK优先、覆盖次优选best／早停；best严格重载并冻结后才评test，不以test选模。last／best、优化器／RNG、顺序／变换、环境／输入hash和模型卡另存，原模型不覆盖，候选不自动启用。

专项`pose-training-audit-6c350f29`实际原YOLO两轮两步、最多4轮时第2轮早停、无training权限拒绝及所属活子进程取消均通过。取消后last保留、result不存在、实际退出确认；取消响应本身仍exit_confirmed=false。子进程请求及异常写入只允许专用忽略根下的`request.json`，路径／名称在OS锁前检查；实际范围外CLI返回1且邻近三份文件hash不变。OS锁只限制离线pose容量1，不冒充全产品活动训练互斥。

本轮真实工程图为无人灰色TEST图，覆盖／PCK0、误差null，没有真人准确率／临床收益。公式、配置、真实命令、失败和hash见 [工作流](../../docs/development/POSE_FINETUNING_WORKFLOW.md)、[验收](../../docs/validation/REHAB_POSE_TRAINING_2026-10-11.md) 和 [摘要](pose_training_verification.json)。

## C. 数据与训练事实

### C1. 实际下载、许可与映射

IRDS 官方固定记录 [Zenodo 4610859](https://zenodo.org/records/4610859)，版本2.0.1。数据许可依据是作者原始数据描述的明确 Dataset License CC BY 4.0，不是仅看到论文开放获取；[描述论文 DOI](https://doi.org/10.3390/data6050046)。署名：Miron, A.; Sadawi, N.; Ismail, W.; Hussain, H.; Grosan, C. *IntelliRehabDS (IRDS)*, Data 2021, 6, 46。

| 文件 | 字节 | SHA256 |
| --- | ---: | --- |
| readme.txt | 1,974 | `c22584330c29d32b712e5b32e96fa842243540c37a5583a6f0a2de28ddb27bc6` |
| SkeletonData.zip | 198,985,485 | `a5fa88829f8538d415e0f0a24d5cdf473a006e23cba5d845ed0f0176cb6c8106` |

MD5分别为 `655525729cd70a00ae5b6863e98141d3` 和 `c243bcdbd1492e4928032e158accdd29`；ZIP 5185成员，实际全包CRC检查通过。未下载41GB深度图。

只取动作4/5。25关节名字/顺序来自官方 readme，逐帧核对 Simplified 与 RawData 命名关节的XYZ/TrackingState。Tracked、Inferred、NotTracked分别保留；没有假设其等于模型置信度。名义30Hz不冒充已验证曝光时间，原timestamp header保留但单位未核验。

样本534/29人：正449、误83、无法归类2；532可训练，2隔离。没有把坐姿/轮椅采集标签误当“坐站动作”。534条姿势分布：chair175、stand258、wheelchair66、Stand-frame10、sit25。整次标签正确1→class0、错误2→class1、3→未知，不生成相位、身体部位错误、提示机会或临床严重度。

数据指纹 `7ce09eae40508843179123bfef632d8b83cf5db72889eb67fb1a10b36c8bb0f5`；特征指纹 `f3188bede2e3ee4f2a90bd9c1166fcd1a1c8006069c9bf40bbab6bd9881c4959`。

![公开IRDS单帧原始相机X-Y与Z-Y投影；编号对应配套JSON；推断或未跟踪点不连成有效证据](figures/kinect_mapping.png)

配套[坐标/命名/状态原值](figures/kinect_mapping_source.json)、[SVG](figures/kinect_mapping.svg)、[导出参数](figures/kinect_mapping.export.json)。选取规则是样本ID排序第一条有效样本中间帧，没有筛选“最好看”的姿势；未平滑，仅正交投影。编号局部重叠尤其Z-Y属于审核图限制，全名和数值以JSON为准。图仅供开发核对，不能证明三维/左右映射已获专业验收或充当产品示范。PNG实际1800×1080、150dpi、白背景RGBA，符号/颜色冗余；已人工查看和元数据筛查，未声称期刊或完整无障碍认证。

REHAB24-6 未下载：学术/非营利资格待确认。MobiPhysio/SUMediPose 官方Dataverse元数据本机403，不能绕过登录或假定产品许可。KERAAL、Fit3D、QEVD按本次任务的许可/动作条件排除，不下载第三方镜像。

### C2. 人员先划分、再特征

seed20261011；17/6/6人，310/131/91条。正/误分别 train269/41、val97/34、test83/8；不切窗跨人泄漏，不用测试集调参。划分SHA `854f5791d7dcbfabdb2be89d81b7e1497b61053118900ba0669f7dc833c2fa28`。

- train：103,302,101,105,306,307,106,301,215,201,210,203,211,212,213,204,217。
- val：303,305,104,205,206,202。
- test：304,102,107,214,216,209。

特征版本 `kinect25-shoulder-causal20hz-1`，128维：当前帧肩中心/肩宽归一3D坐标、后向差分速度、观测/速度/状态已知mask、原TrackingState、局部角度+mask、结果年龄/新鲜度、侧别。20Hz向下因果取样、不插值、不用未来极值或整段归一统计；单条9–253步。标准化仅在训练集合拟合。整段统计/mean pooling只在整次结束后使用，不注册成实时阶段模型。

### C3. 实际训练与独立预测

产品环境 Python3.13.12 / torch2.9.1+cpu / numpy2.2.6 / PySide6 6.11.2，未升级。独立训练环境 `.runtime/rehab_ml/venv` 实际继承基础site-packages：torch2.11.0+cu128、numpy2.4.4；NVIDIA RTX4070 Laptop 8GiB 可用。系统依赖锁和训练代码hash在各run的 `provenance.json/environment.lock.txt`，未将依赖混同产品运行环境。

实际最小完整链命令（已经执行；训练后不自动上线）：

```powershell
& '.\.runtime\rehab_ml\venv\Scripts\python.exe' -X utf8 tools/rehab_ml/run_minimal.py
```

它记录了resolve→fetch→verify→prepare→split→features→baseline/TCN真实训练→val/test明确run评估→协议/会话检查。开工环境检查另见inventory；本次运行后的脚本补入doctor步骤，尚未为这一小改动再重复训练。每个阶段实际输出与耗时见[完整实验摘要](experiment_summary.json)。更早两次单独训练保留，完整链重复训练得到相同检查点hash；不是拷贝一个下载模型冒充训练。

| 项目 | Logistic基线 | 因果TCN候选 |
| --- | --- | --- |
| run ID | `20261010T185211Z-logistic_regression-c78b48c6` | `20261010T185214Z-causal_tcn-84cbc486` |
| 检查点SHA | `ed8ca32d15f15615dfc83ec782beafbebe1c4218c27456521a3540bf1a0c694d` | `ef76c10bf543999fe18eb84d5e340f6335cba6b84037ee4cf17233e4d7d14b8b` |
| 训练设备/耗时 | NumPy CPU / 0.873秒 | CUDA / 11.301秒，峰值94,780,416字节 |
| 选中epoch /停止 | 17 / early stop77 | 11 / early stop21 |
| val macro-F1 | 0.6375 | 0.6572 |
| test macro-F1 | 0.6341 | 0.5444 |
| test balanced accuracy | 0.8675 | 0.5384 |
| 错误动作precision / recall | 0.2667 / 1.0000 | 0.2000 / 0.1250 |
| test混淆矩阵（行真值，列预测；正/误） | [[61,22],[0,8]] | [[79,4],[7,1]] |
| 95%按人bootstrap macro-F1区间 | [0.4125,0.7390] | [0.4246,1.0000] |

基线使用整段mean/std/min/max/median/p90/首末差/时长的标准化L2 logistic；TCN为64通道、4残差块、每块2卷积、kernel3/dilation1/2/4/8、left padding、逐时刻LayerNorm、dropout0.1，感受野61步、108226参数；mask mean后整次head。AdamW lr0.001/wd0.0001、batch16、max60/patience10、clip1；类别权重仅train计算[0.5762,3.7805]，固定概率阈值0.5，不用test调阈值。

候选不优：TCN漏掉7/8错误条；基线虽然找到8/8错误条，但把22/83正确条误报为错误。测试只有6人、8条错误，区间很宽，还有病种/姿势与label相关性。这些不是手机准确率或临床能力。多数类“全正确”也可获91.21%准确率而错误召回0，因此不以普通accuracy宣传成绩。

模型、实际val/test逐条预测、混淆矩阵、分人/队列/姿势结果和500次按人bootstrap在 `.runtime/rehab_ml/run/<明确runID>/`；模型副本在 `.runtime/rehab_ml/model/<runID>/`。公共摘要保留实际hash，二进制和原始骨架包继续忽略。完整模型卡只有肩外展整次正误任务，Kinect3D、25关节、明确特征/协议、CCBY署名，`product_enabled=false`。

## D. 后端验证与回退

### D1. 最新工具／存储／报告／推理回归及历史记录

最新产品环境完整回归`verification-b4bcb387`为230／12／19项，保护1308文件一致；包含30项训练、23项双层损失、17项VIDEO、30项关键点、12项存储与18项报告。本轮专项`pose-training-audit-6c350f29`30项与五条实际命令见 [验收](../../docs/validation/REHAB_POSE_TRAINING_2026-10-11.md)。此前227项工作区试验、200项双层损失、177项VIDEO／两原片／7条CLI、160项工具／30项专项、130项／存储复验／会话100项保留各自历史，不称本轮新重跑或相加。原生SQLite、真实OS故障、受控异常注入、空图／真人无标注回放分别说明，工程通过不等于准确率。

历史时间／贡献曾运行`verification-3b62b733`，74项新后端、12项旧康复、19项旧手机通过，会话CLI44项为74项子集；详见 [当时验收](../../docs/validation/REHAB_V2_TIMING_PROGRESS_2026-10-11.md)。[regression.json](regression.json)记录本轮230／12／19项；[session_verification.json](session_verification.json)保留此前100项，不称本轮重跑。历史49／61项不代替它们。手机与HTTP测试仍有既有Starlette/httpx弃用warning，未升级依赖。没有借用交接中324项计数，本轮未跑全UI／Android／照护回归。

确定性覆盖：C01肩腕缺测，C02短gap不累积保持，C03隐藏转折，C04站姿进入，C05坐站rearm，C06真膝角，C07左右/水平镜像/等比例分辨率及契约变化，C08乱序/epoch/年龄/慢推理污染，C09换人，C10组休息，C11提示TTL/当前纠正，C12因果特征与70前缀TCN未来扰动，C13缓存隔离，C14–16持久幂等，C17报告失败，C18真实退出恢复，C19未知感受，C21跨域拒绝，C22无标签零梯度，C23接收/丢帧/超时收尾边界。

C20禁改范围以独立文件保护命令核验，不混入74项计数。新增测试覆盖贡献迁移／回滚／范围／游标、反馈跨计划版本、手动计划原保存绑定和显式时间连续性。C07尚不覆盖任意相机旋转/剪裁/非等比例拉伸；显示镜像不会换解剖侧，外部未经声明的视频翻转或实质机位变化不能自动宣称等价。未知设备时钟、全部动作、人群真实误差与跨端重启仍未验收。

最初工具测试的失败也保留：unittest从根目录找不到app（补子进程PYTHONPATH）；默认宿主探路被旧X-Rehab-Client保护403（正确加header并检查路由确实未注册）；异步报告刚提交状态仍pending（测试等待最终派生状态）；崩溃半次只输入一帧、实际尚未形成半次（改为6帧并断言current真实存在）。没有把这些失败计为通过，末次证据才是本轮结果。

### D2. 真实录像回放并非准确率验收

使用已有本机两段录像，显式analysis-consent，原 SourceWorker + VisionWorker/YOLO。首次提取工具使用preview Context导致一帧后暂停；修复为明确run_id，未改原采集组件。后续成功读取443/429帧，手机视频首个负PTS只按原兼容逻辑跳过一帧，原媒体PTS保留。

肩外展：434/443主指标可观测（97.97%），新协议0确认/旧引擎2；新协议未取得默认1秒稳定起始姿势基线。深蹲：48/429膝主指标可观测（11.19%），新协议0；没有把健身髋代理当康复膝角。结果说明流程能运行但这些片不能支持新协议完成验收；不反向调起点阈值以强行适配这两段，没有人工计次/专业金标准，accuracy保留null。

私人RGB及逐帧骨架仅在忽略目录，Git只提交无身份图像/关键点的[统计摘要](target_replay_summary.json)。训练权限为false，未进入IRDS训练集；没有把用户自拍视频假称专业标注。

### D3. 性能、资源与故障边界

训练环境CPU、4线程、真实IRDS一条51步×128特征、10warmup+100次整次特征/TCN；预先设定20ms预算：特征p95 0.792ms、TCN2.281ms、总3.058ms。80次隔离数据库pause/resume控制p95 17.408ms，预先200ms预算。RSS534,720,512字节。明确run和所有统计见[performance.json](performance.json)。

这是CPU微基准，不包含手机、相机解码/YOLO、网络、多客户、与正式训练并发。真实录像逐帧包含原YOLO的时间只作为离线记录，不能等同实时直播采样/手机FPS。结束有2秒收尾例外，不用pause/resume的p95冒充finish或整个系统p95。实时服务单活动会话/最新帧槽1/并发控制8/24,000帧/20分钟上限；队列覆盖和终止丢帧记录可复核。

最新增量补齐会话级 trace、有界阶段统计和默认 YOLO 所属推理进程。实跑 `benchmark-sessions --frames 12` 的 `session-performance-a394a83e`：CPU／imgsz640／原权重 SHA `869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`；12 张320×240无人JPEG，单生产者等结果后控制。冷推理 2035.68 ms、进程往返 2286.91 ms；11 次热推理 p95 40.87 ms、热宿主结果年龄 p95 57.19 ms；暂停／恢复 ASGI HTTP p95 17.78／13.58 ms，结束仅 1 次 33.74 ms，最终事务仅 1 次 18.92 ms，不能将单样本称稳定 p95。最近帧后观测 RSS：宿主63,356,928字节、所属推理319,066,112字节，不是峰值。统计、原始摘要 SHA 和排除项见 [session_performance.json](session_performance.json)。

此历史实跑不是摄像头／网络／手机／真人运动／并发压力；关闭候选TCN，没有测新质量头。采样率只描述宿主接收／处理，trace尚非全产品跨任务分布式追踪。默认报告已为所属进程，可信本地callable仍无硬取消；本轮SQL容量／只读／锁／TEST损坏副本与明确备份恢复已验证，不能扩大为物理磁盘满／介质损坏／断电或自动修库。OS创建硬截止、用户负载压力仍未完成。之前照护库异常不属于本轮已修复事项。整个任务继续局部完成。

### D4. 关闭与历史比较

正式前端和旧live未更改，也未重启原服务。使用默认 `create_app(..., rehab_v2=False)` 即不安装新入口、不初始化v2库；已有新事实库保留，不删除。候选默认无生产加载；ShadowSequence research_mode默认false，Kinect模型不得接YOLO/MediaPipe。`backend.yaml`是实验/开关声明，不会单凭改YAML自动上线；实际宿主入口参数才是启用条件。

未改现有权重，可始终使用原YOLO及旧规则；本轮无ONNX导出、产品质量头、提示模型或APK替换。新v2数据、旧康复/健身session及Kinect整次标签有不同protocol/source/domain/reference，不能混拼纵向曲线。比较契约单独核对指标、单位、参考、来源情境、机位、侧、schema/model/time/preprocess；具体证据指纹始终另存。二维投影角能工程比较不表示解剖ROM可比。

## E. 后续依赖与下一阶段

1. 首先补资格：REHAB24-6学术/非营利身份或其他正式RGB授权资料；MobiPhysio/SUMediPose官方访问和许可条款核验。未回答资格问题前不接受条款、不绕过受限访问，也不默认购买数据/GPU。
2. 采集三动作目标域素材：规范准备→动作→回位，肩肘/髋膝踝依动作可见；另有遮挡、旁人、换人、站姿进入坐站、可接受扶手和异常动作。独立专业人员标注物理/可观察完成、相位、错误/许可变式、提示窗口并复核；需明确训练与分享授权。不能只给模型现有结果当标签。
3. 再训练真实RGB域的质量/相位任务，比较旧EMA/规则、版本化规则、简单基线、因果候选四组；动作计数仍由观察规则确认。今后的模型改进先由新验证集/交叉验证确定，不用当前固定test反复调参。
4. 独立参考转换、原模型预测与误差／覆盖、双层masked loss、多轮／train颜色增广／val选模和工程更新／重载已完成。真实姿态微调仍须合法真人2D关节／visibility、独立划分与原误差基线；专业标定投影及候选同集真人实验尚未完成，不用TEST工程更新代替。恢复材料已存但自动resume未实现。
5. 后端继续完善：康复深蹲的版本化本人计划绑定；v2 时间结果的专门比较契约、完整故障/容量压力与任务硬隔离、时间/坐标契约更细的审核、医疗参考误差及不同来源的可比性验证。唯一贡献和后端历史／进度已实现，但旧页面／APK未连接；不能用新增 API 通过代替跨端上线。客户端/前端仍不在本轮范围。

### 实际复现入口

历史IRDS训练配置是`configs/rehab_ml/baseline.yaml`和`tcn.yaml`；本轮多轮姿态模板为`configs/rehab_ml/pose_finetune_template.json`，专项命令自动在新忽略run生成TEST配置。下列命令含历史复现入口，不表示本轮全部重跑；本轮实际为`verify_pose_training.py`和`verify_all.py`，从仓库根执行：

```powershell
& '.\.runtime\rehab_ml\venv\Scripts\python.exe' -X utf8 tools/rehab_ml/run_minimal.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_pose_training.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py verify-sessions --database-mode isolated
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py benchmark-sessions --frames 12
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py compare --suite rehab_core --baseline 20261010T185211Z-logistic_regression-c78b48c6 --candidate 20261010T185214Z-causal_tcn-84cbc486
& '.\.runtime\rehab_ml\venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py benchmark --run-id 20261010T185214Z-causal_tcn-84cbc486
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py verify-scope --baseline reports/rehab_backend/protected_files.json
```

公开数据来自[IRDS官方记录](https://zenodo.org/records/4610859)与[数据描述论文](https://doi.org/10.3390/data6050046)。图表流程采用scientific-visualization的原值、缺失、冗余编码及人工审核要求；参考 Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026), *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*, [DOI](https://doi.org/10.48550/arXiv.2609.00065)，2026-10-11核验最新v2（2026-09-02）。这些引用是数据/流程来源，不能替代本项目有效性验证。
