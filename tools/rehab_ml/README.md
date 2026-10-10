# 康复后端与离线实验入口

本目录不修改正式客户端、前端或非康复业务。重实验、原始数据、权重、私人录像结果和测试数据库默认放在仓库忽略的 `.runtime/rehab_ml/{data,run,model}`。可以设置任务专用的 `REHAB_DATA_ROOT`、`REHAB_RUN_ROOT`、`REHAB_MODEL_ROOT`。产品环境不得为了训练整体升级。

## 实际入口

产品后端解释器：`rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe`。

离线训练解释器：`.runtime/rehab_ml/venv/Scripts/python.exe`。本机训练环境继承系统 site-packages，实际版本与 GPU 见实验 `environment.lock.txt`、`provenance.json`，不能当成产品环境。迁移到其他机器应依据该锁文件建立独立环境。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py --help
& '.\.runtime\rehab_ml\venv\Scripts\python.exe' -X utf8 tools/rehab_ml/run_minimal.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/verify_all.py
```

`run_minimal` 真正下载/校验 IRDS、适配、按人划分、生成特征、训练基线与 TCN、用明确 run ID 评估和执行协议/会话回归。重复运行只复用已校验的原始包，不悄悄复用旧训练权重。它不是 APK 构建或模型上线命令。

`inventory` 只在开工时建立保护基准，禁止重建基准掩盖改动；结束运行 `verify-scope`。`verify_all` 为每次 pytest 分配全新的专用目录，不清理用户数据；记录实际命令、退出码和日志 hash。

## 正式会话的后端接入

原 `mobile_rehab.server.create_app` 增加显式关键字 `rehab_v2=True`，默认关闭；该参数启用认证后的 `/api/rehab/v2/sessions` 生命周期。原 `/api/live` 和其删除仍是预览，不保存训练历史。新事实库为宿主数据目录的 `rehab-v2.sqlite3`，复用现有 `Storage` owning thread 和备份机制，和原病人库分开。

创建需要本人身份、consent、创建幂等键、现有本人计划 ID/revision/entry_key 和明确机位；计划、剂量、节奏和原证据引用由宿主解析并冻结，客户端不能随意伪造处方。自动计划复用原继续资格；已有手动计划还需 `training_plan_confirmed=true`，计划要求陪同时需 `companion_confirmed=true`。实际输入必须匹配计划的 `LIVE_CAMERA/SELF_USE` scope，原录像计划不能改名使用。帧仅支持受限 JPEG，由原 YOLO 后端推理。任意关键点 JSON 输入被拒绝；确定性回放仅内部 `internal_replay=True` 并标记 TEST/SYNTHETIC。

三动作协议内部均可运行，当前宿主计划适配仅肩外展与坐站，不能把旧动作别名冒充康复深蹲。新增 `GET /api/rehab/v2/sessions` 为本人最终历史，`GET /api/rehab/v2/plans/{plan_id}` 查询本人计划、唯一贡献、进度与继续状态。namespace 2 的贡献与最终事实在同一事务提交；v1 升级前备份，保留原回执和视觉快照。最新尝试按提交 ordinal 取值，跨计划版本的不适反馈仍参与原政策校验。只给原政策生成临时视图，不往旧库写伪测量。前端、APK、旧历史页面和 `/api/plan` 未接入；旧继续资格与剂量规则未改，本轮没有重新部署原运行服务。

显式 `timing_plan` 复用原 `movement_timing.py`，分别记录出程、峰区／站位停留、回程、最长连续目标保持及 `MET/NOT_MET/UNASSESSABLE/NOT_SET`。v2 封套版本 `rehab-observed-timing-2`，写明原算法版本、time_basis 和证据 seq/epoch。保持只用当前连续有效观测；缺测、暂停、丢帧、换人和长间隔不能补时间。肩／深蹲的峰区分段是完整往返后的回顾计算，不冒充实时相位。坐站在站起时计一次，后续回坐仅更新尚未终结草稿的时间字段；已确认计次和最终回执不允许重写。节奏是否达标不修改计次、组数或原完成政策。

结束请求冻结接收高水位，最多等待 2 秒保留的在途帧，然后原子保存逐次事实/快照/回执。派生报告异步生成，重启可对账；报告失败不回滚事实。未填感受为 null/missing，追加反馈独立 revision。默认最多一个正式活动会话、一个待处理帧槽、8 个并发控制请求；20 分钟时间上限、24,000 接收帧上限。推理/报告线程若挂起，关闭会明确拒绝宣称资源释放，尚无硬隔离进程超时杀除。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py verify-sessions --database-mode isolated
```

2026-10-11 该命令实际运行 44 项会话／贡献／时间／HTTP 测试；完整 `verify_all` 运行 74 项新后端、12 项旧康复、19 项旧手机测试及 1308 文件保护核验。44 项是 74 项的子集，不累加。实际日志与边界见 [本轮验收](../../docs/validation/REHAB_V2_TIMING_PROGRESS_2026-10-11.md)。这些是隔离工程测试，不是临床准确率或手机实机验收。

## 实验边界

IRDS 整次正误标签只训练 Kinect 三维肩外展质量候选。坐站、康复深蹲、相位、身体部位错误和提示时机没有对应独立标签。`compare` 比較明确指定的冻结测试预测；模型/领域/协议匹配失败回退规则，绝不自动启用。

`extract-pose --video ... --exercise ... --side ... --analysis-consent yes` 使用原采集进程和真实 YOLO，保存私人骨架与新旧协议结果，不授予训练权限，也不把规则自身输出当真值。视频路径、私人骨架不上传 Git。

`build-pose-dataset` / `train-pose` 当前只有资格检查和明确非零拒绝，不是已完成的姿态微调器。需要核实 RGB 数据授权、专业独立标注、2D 关节和可见性 mask 才能继续；缺标关节不能写成负例。条件依赖见实施报告。

## 骨架审核图

图形导出复用本机 scientific-visualization skill 的帮助脚本。在其他机器重做此图，需要安装该skill并将 `REHAB_VISUAL_SKILL_ROOT` 设为对应根目录；未安装时明确拒绝，不影响数据训练或正式产品。已有PNG/SVG/原值JSON可直接查看。

工具不覆盖已有审核产物。重做时传入 `--output-dir .runtime/rehab_ml/run/新审核目录`，选择尚不存在的文件目标。

`visual-audit` 用公开 CC BY 4.0 IRDS 中排序第一条有效样本的中间帧，导出原始 X-Y / Z-Y 投影。蓝圆为 Tracked、橙三角为 Inferred、黑叉为 NotTracked；后两者不是有效观测。连线仅使用两端均 Tracked 的点。编号、全名、坐标与状态在配套 JSON；Z-Y 投影重叠是真实投影的遮挡，不表示同一关节。不是临床图或产品页面。

图表流程采用 scientific-visualization 的原值保留、缺失标记、冗余符号、元数据与人工查看要求。参考：Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. arXiv 最新记录 v2（2026-09-02），[DOI](https://doi.org/10.48550/arXiv.2609.00065)，2026-10-11 核验。它是图表流程来源，不是模型有效性证据。
