# 康复合成视频离线实施入口

更新日期：2026-10-19。本文记录[实施方案](REHAB_SYNTHETIC_VIDEO_DATASET_PLAN.md)的工程接线，不代表方案全部完成、已取得人工标签或已改善真人表现。

首轮仍为肩外展正面专项：先4个来源组的12条流程调试片，再在独立来源划分冻结后开展正式60条。正式组按6/2/2拆分，目标36/12/12条。肘屈伸、坐位膝屈伸、坐站按原方案后续推进，不能把工程框架已支持等同于各动作数据已完成。侧面是不同可观察条件，应单独标视角、保留来源关联并检验；不得把另一个机位的答案补成当前机位可见事实。

## 当前工程组成

代码位于 `tools/rehab_ml/synthetic/`，与原专业MobiPhysio来源入口分离。

| 文件 | 已实现的工程行为 | 不构成的证据 |
| --- | --- | --- |
| `contracts.py` | `rehab_synthetic/v1`来源/母片/生成条件；人物、参考、运动源、派生ID与重复SHA的传递闭包；pilot仅train；正式10组6/2/2冻结；A–F生成目标槽位与60条人工筛片记录检查 | 目标槽位齐全不证明实际六类覆盖；声明身份和来源ID不能自动证明人员资格或素材许可 |
| `generation.py` | 本机已锁定LTX工作流、版本化提示词与conditioning缓存、来源记录、任务重连、原片与真实PTS索引；参考与动作生成分别记录 | 提示词要求“一次”、某侧或某类不是动作真值；原片生成成功不是人工筛查通过 |
| `video.py` | PyAV完整解码、packet/frame真实PTS对账、原图RGB指纹；约15Hz选择已到达原帧并记录年龄 | 通过解码不等于人体结构或动作正确 |
| `pose.py` | 同一原片、共享处理帧与指纹，分别导出YOLO17/MediaPipe33预测、置信度、缺测、轨迹、模型hash与耗时 | 模型骨骼不是人工关键点；两个后端不能把置信度直接平均成真值 |
| `temporal.py` | 因果特征、实际时间间隔/年龄/缺测、逐步5阶段TCN、未知与padding损失屏蔽、跨阶段计次候选、B0重放及独立后端训练入口 | TEST训练与小片段运行不等于目标域训练完成、手机实时效果或临床准确率 |
| `evaluation.py` | 固定队列B0/B2比较、计次和边界误差、缺输出与未知覆盖、逐片失败；保留分母 | 不能用自生成标签或反复调参后的留出片宣称独立测试提升 |
| `review.py` | 本机原片盲审页、实际PTS定位、空白人工表、来源筛查、独立mask、只增版本与合格参考加载 | 播放coverage和人工声明只能辅助记录，不能证明身份、全片观看或专业资格 |
| `experiment.py` | `validate / extract / train`；正式P0正面肩外展、来源划分与真实人工阶段参考门；独立CPU后端、固定预测、B0/B2报告 | 命令执行完成不等于整个方案验收；实际六类覆盖、独立真人表现另验 |
| `costs.py` | 同一任务句柄的真实Comfy事件计时，按执行窗对齐GPU/内存观测样本 | 观测极值不是连续峰值，不能凭总时长虚构采样/VAE各阶段时间 |
| `guidance.py` | 原生首帧I2V加同图末帧引导，AV采样后裁掉附加guide再解码；记录新工作流和派生关系 | 实验引导不保证单臂、回位或人体正确，不循环、倒放、拼接母片冒充动作 |
| `control.py` | 实际参考帧冻结预测→单臂刚性链OpenPose18控制视频；分组/seed决定时序；完整RGB/PTS/来源与轨迹SHA核验；当前仅收显式pilot/train来源 | 控制角度、时刻、目标类别不是成片标签；共享算法版本不作为共同来源 |
| `pose_guidance.py` | 固定19B姿态IC-LoRA、原生全帧guide、8步euler与采样后CropGuides；可选同图末帧参考用独立v2，默认v1不变；纯图与执行证据分开 | 本机一次运行不能证明任意分辨率/显存都支持，身体控制也不保证手指细节、动作精确或渐暗必消失 |
| `motion.py` | A/D/E兼容原轨迹，B较慢、C约两秒保持、F增加刚性前臂弯曲；来源组与seed决定指令 | 指令时刻和角度不是生成视频的阶段、次数或临床ROM |
| `formal_plan.py` | 12条已保存真实人审、正式10组6/2/2与60个请求槽位；不可覆盖冻结、来源注册图、跨字段别名/实际资产SHA/父链泄漏预检 | 冻结不等于质量通过、实际六类覆盖或训练就绪；排除片仍保留未知 |
| `formal_control.py` | 读取真实冻结授权，参考原片/PNG/冻结YOLO帧0绑定，A–F控制逐帧实际RGB/PTS重算，seed来自冻结槽位 | 支持正式来源校验不代表已生成正式人物视频；旧pilot控制入口仍保持原限制 |
| `formal_generation.py` | 单作业正式参考/动作入口、模板与实际执行图分别hash、仅声明位置晚绑定、生成前来源注册、模型和实现字节检查、持久任务恢复 | 当前实际人审为0，尚未在本机冻结或运行正式60条；不自动接受、标注或训练 |
| `endpoint.py` | 同组pilot/train D原片实际帧→不同末图条件；独立新版本并继承父片/控制来源，原片保留 | 帧中姿态是AI条件，不是人工GT；不同末图是否消除黑尾须实际试验 |

正式产品姿态权重、动作状态机、计次、剂量、患者历史、APK、云端与Qt UI不因上述离线工具而替换或启用候选权重。GPU模型服务仍运行于独立生成环境；姿态控制校验客户端使用已有产品Python的CPU OpenCV/PyAV，未给产品环境安装生成模型或更换依赖。生成与模型训练分时执行。

## 本机位置与命令

运行数据根目录：`E:/ai-video-lab/datasets/rehab_synthetic_v1/`。原片、权重、骨骼、环境和日志不提交Git；仓库只保存代码、方法、配置、数据/模型卡及可公开聚合结果。

版本化数据卡、标签合同、分组/生成协议和预先声明的TCN参数分别在 `configs/rehab_ml/synthetic_data_card.json`、`synthetic_label_spec.json`、`synthetic_protocol.json`、`synthetic_tcn.json`。模型权重另按本机锁与实际SHA核验；数据卡不授予模型或素材的再分发权。

在仓库根目录运行；先确认实际解释器环境。以下命令不把现成体育片导入训练：

```powershell
# 查看当前生成/审核入口，不开始生成。
& 'E:/ai-video-lab/.venv/Scripts/python.exe' -X utf8 -m tools.rehab_ml.synthetic.generation --help

# 初始化目录及空清单，不生成或标注。
& 'E:/ai-video-lab/.venv/Scripts/python.exe' -X utf8 -m tools.rehab_ml.synthetic.generation init

# 启动仅127.0.0.1的本机人工审核页；Ctrl+C结束。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m tools.rehab_ml.synthetic.review 'E:/ai-video-lab/datasets/rehab_synthetic_v1' --port 8190

# 等价的生成器审核子命令。
& 'E:/ai-video-lab/.venv/Scripts/python.exe' -X utf8 -m tools.rehab_ml.synthetic.generation review --root 'E:/ai-video-lab/datasets/rehab_synthetic_v1' --port 8190

# 仅输出未观看、无签名、次数未知的空白表，不写人工参考。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m tools.rehab_ml.synthetic.review 'E:/ai-video-lab/datasets/rehab_synthetic_v1' --prepare

# 仅工程测试；不读取真实人工标签、不启用模型。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests/rehab_backend -p 'test_synthetic_*.py'

# 验证实际原片、PTS及已保存的人工资格；空清单会明确报告0片。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m tools.rehab_ml.synthetic.experiment validate

# 原始预测工程提取；指定单片避免无意处理后来追加的整批。
# 此处side只是预先声明的分析条件，不是实际侧别真值。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m tools.rehab_ml.synthetic.experiment extract --run-id extract_new_id --samples rehab_pilot02_A_v1_ref1f15112a17c0 --backend all --baseline-side left

# 尚不具备真实60条人工参考时会拒绝，不能通过工程绕过开关训练。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m tools.rehab_ml.synthetic.experiment train --run-id phase_new_id --backend all --config configs/rehab_ml/synthetic_tcn.json
```

参考图和pilot生成通过 `generation references` / `generation pilot`，参数以该入口`--help`及运行清单为准。首次先核验模型锁，参考图出现脚部/头部裁切等问题应记录失败并更换新的attempt，不能覆盖原片或直接放行到动作生成。提示词变更需要新版本与缓存键。不得在未通过构图/结构检查前批量生成所有动作。

姿态控制是另一个有独立SHA的新试验，不修改原生成权重锁。新增[19B姿态IC-LoRA](https://huggingface.co/Lightricks/LTX-2-19b-IC-LoRA-Pose-Control)，revision `ecdabfb03acd2e807c90ea260ccc136140e7ac80`，654,465,256字节，SHA256 `61816bf0985d4470c456160deec65df69188ae45d553e5aa8f1252fc543bc8aa`；独立本机锁为 `E:/ai-video-lab/control-models.lock.json`。其Community License不是无限制OSI许可；本轮为离线、非商业、非临床工程研究，不据此宣称商业训练或再分发许可。嵌入的2026-01-05条款、下载回执与官方两阶段工作流均单独保留。本机采用单阶段640×384，未执行官方第二阶段放大精修。

已取得实际参考YOLO输出及结构筛查后，可用以下入口生成独立控制视频，再一条一条提交；receipt必须在同一数据根目录，且组、场景、参考图SHA、模型SHA、全部真实帧校验一致。控制器目前拒绝formal/val/test来源，不能把留出参考重标成pilot/train。

```powershell
# 仅渲染控制指令；--pose必须来自实际参考片，不能用动作片的首帧预测顶替。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m tools.rehab_ml.synthetic.control --pose '<实际参考pose.json>' --reference-record '<实际参考侧车.json>' --output-dir '<新的控制目录>' --seed 2026101902 --scenarios A D E

# GPU服务仍是8188独立环境；以下只是使用已有CPU依赖的校验/API客户端。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m tools.rehab_ml.synthetic.generation pilot --groups pilot02 --scenarios A --pose-control 'E:/ai-video-lab/datasets/rehab_synthetic_v1/controllers/pilot02-body18-control-v1-A/A/receipt.json'

# 同一控制/seed/文本的新试验：追加同参考图到末帧，独立_endref名称。
# 仅允许A/E，D保持抬臂时不能用垂臂原图作为末帧条件。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m tools.rehab_ml.synthetic.generation pilot --groups pilot02 --scenarios E --pose-control 'E:/ai-video-lab/datasets/rehab_synthetic_v1/controllers/pilot02-body18-control-v1-DE/E/receipt.json' --pose-end-reference
```

HTTP400正文和任务句柄会保存。ACK丢失、超时或失败都不能自动重发同一个生成任务；先查看已有句柄和错误。完成后再次核验控制输入，生成清单去重来源token并保留每个不同实际来源。

## 正式来源入口与保持动作的独立末图试验

`generation.py`和`control.py`保持pilot/train限定。正式任务另走`formal_generation.py`与`formal_control.py`，不能把旧片的stage改为formal。正式计划的12个调试片ID必须来自4组各A/D/E；每条需已有真实操作者完整观看、保存最终接受/排除决定并绑定原片SHA和实际PTS。接受片还需可用的单侧阶段或次数参考；排除片允许标签未知，须保留理由。所有排除不被解释为生成方法合格；冻结报告始终保留`workflow_readiness='unproven'`和`training_ready=False`，正式训练仍有其独立60条阶段监督门。

草稿的请求JSON含`cohort12`、10组`profiles`、`group_splits`和`generation_recipe`，结构以`formal_plan.draft_formal_plan`为准。`formal_generation.build_generation_recipe`创建固定模板；其config另绑定参考模板、姿态LoRA回执及实际实现文件SHA。组、参考、identity/lineage、实际PNG/原片/pose/控制轨迹SHA以及父链共同建立来源图；全局算法和模型版本不作为来源边。所有旧pilot attempt和未选参考也纳入调试来源污染检查。模板SHA与实际替换文件名、seed后的执行图SHA分开记录。模型、配置、实现、已冻结人审或来源变化均需停止核对，不能静默重建冻结记录。

```powershell
# 只创建草稿，不生成、不标注；request须显式指定来源和配方。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -m tools.rehab_ml.synthetic.formal_generation draft --root 'E:/ai-video-lab/datasets/rehab_synthetic_v1' --request '<计划请求JSON>'

# 真实12条人审不足时拒绝；不绕过此门去调用GPU。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -m tools.rehab_ml.synthetic.formal_generation freeze --root 'E:/ai-video-lab/datasets/rehab_synthetic_v1' --plan 'manifests/formal-plan-draft.json'

# 只有已有冻结、真实正式参考帧0预测时才渲染控制；不启动GPU。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -m tools.rehab_ml.synthetic.formal_control --root '<数据根目录>' --pose '<参考pose.json>' --reference-record '<正式参考记录>' --output-dir '<全新控制目录>' --scenarios A B C D E F

# 查看单作业参考/动作/结构筛查参数；无自动60条提交。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -m tools.rehab_ml.synthetic.formal_generation motion --help

# D末图是保持姿势的实际RGB帧，不能换成双臂垂下的初始图。
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -m tools.rehab_ml.synthetic.endpoint validate --endpoint-receipt '<同组D保持帧的不可覆盖收据>' --pose-control '<同一个D控制收据>'
```

正式参考另存在`references/formal/`，结构筛查保存独立收据而不改原参考记录。正式控制按各槽位seed渲染，补片attempt使用`rehab_formal_attempt_seed/v1`确定性派生并保持来源组/划分；失败与旧attempt不删除。A/B/C/E/F目前请求全帧pose加同图末帧，D请求pose-only，这只是冻结配方能力，未证明各类成片可靠。D不同保持末图仍是独立pilot试验；本机新人物已出现D黑尾，因此不能以旧人物D成功直接扩量。

本机已保存只读可核对草稿`manifests/formal-plan-draft-v1/{request.json,generation-config.json,plan.json}`，plan SHA `d1f8df27a860cdc776178fac1020c3f9e60f7f70837b3fcfcf0f457d549c93ea`；10个新的虚拟人物描述尚未渲染，6/2/2和60槽位仅为请求。`readiness-at-014-raw.json`记录当时尚缺5条所选调试片；后续可追加新时点快照，不覆盖旧草稿、不创建真实freeze。来源独立性须在实际素材/注册图出现后检查，不能从描述不同直接断言。

最新候选选择另存`manifests/formal-plan-draft-v2/{request.json,plan.json,selection-replacement.json}`，plan SHA `068a51176a202819e60f04da291ccc151d92b8570c2c37db49ba4acd3ad3119c`。仅把旧pilot04 D换成其不同保持末图的新版本，v1和全部旧片保留；配方/人物/拆分请求不改，正式D仍是未证明可靠的pose-only。采用新末图方法须另版本配方和冻结，不能直接套用pilot收据。12条候选已实际生成，`formal_generation freeze`在v1/19片和v2/20片时点均实际返回2、`all_twelve_require_saved_human_full_video_review`，未创建冻结文件。收据为`reports/formal-freeze-readiness-at-019-raw-v1.json`、`formal-freeze-readiness-at-020-raw-v2.json`，不是模拟拒绝或实际正式生成成功。

## 原片与人工参考合同

母片清单为 `manifests/dataset.json`。样本包含sample/source/reference组、lineage、固定split、pilot/formal、动作/实际侧别/视角、原片SHA/尺寸/帧数、timeline路径及SHA、生成模型/工作流/提示词hash与seed。实际侧别未知时保持unknown，不能把生成器请求的左侧直接填为人工确认。

`contracts.load_manifest`默认核对原片与PTS索引SHA，并重新完整解码实际时间轴。`verify_files=False`只用于结构检查，不能据此宣称媒体验证通过。纯函数`validate_manifest`接受已加载timeline用于一致性检查；正式完整性应显式设置`require_formal_complete=True`，pending和excluded不计合格60条。

`freeze_splits`创建正式10组6/2/2冻结记录；应把该记录与事先确定的来源分组方法保留。工具检查记录自洽，不能凭可重算的hash独立证明历史上从未改过拆分。来源证据与版本历史仍须保存。

实际工程标签由真实操作者完整观看后填写：

1. 浏览器打开本轮审核服务`http://127.0.0.1:8191/`，选择匿名队列中的原片；端口变化以新队列回执为准。旧8190仅保留原页面。页面不显示生成目标类别、提示词、骨骼或次数预测。
2. 完整观看，必要时用上一帧/下一帧/滑条按实际PTS定位。填写本人标识，主动选择人工来源与实际解剖侧。次数开始为空，确认0次也必须实际清点。
3. 标可确认阶段区间；逐次边界使用`ready / outbound / endpoint_or_hold / return / rest_or_other`。未知保持null和false mask，不能用休息类填满未知。
4. 大于0的可确认次数须有对应逐次完成记录；肩外展完整往返要求明确五个边界。幅度小和过程未完成分开，不自动用健康人幅度阈值定错。
5. 原片通过需实际人工完整观看声明；肢体增生、融化、跳切、穿模等排除并说明原因。两项非临床图像事件“肘部弯曲”“躯干侧倾”各自填写可评价性、出现/未出现/未知及实际PTS区间；未知不等于未出现，不可评价也不监督为未出现。专业临床质量仍未知。
6. 保存会另建不可覆盖版本，不重写生成清单。播放coverage只保存为辅助声明，`reviewer_identity_is_verified`始终为false。AI草稿可保存，但不能批准原片、不能进入训练。

审核记录保存到`annotations/review-versions/<sample_id的SHA256>/<时间及唯一版本>.json`。版本绑定原片/PTS索引SHA、人工annotation SHA、`source_patch`及工程资格结果。`review.load_reviewed(root)`在内存把最新明确决定应用到完整队列，返回manifest、timelines、annotations与eligible_annotations；不会覆盖生成器正在追加的清单。后续训练应调用该接口及`contracts.validate_annotation`，不能只按文件名收集所有JSON作为标签。

当前运行的新审核入口为 `http://127.0.0.1:8191/`；旧8190服务与用户页面未关闭。标签合同v2和数据卡v2的独立外部快照在 `manifests/protocol-configs-v2/`，旧 `protocol-configs/` v1副本未改。旧quality空列表仍表示所有这些观察未知，不能迁移成“未出现”。每份新审核版本绑定合同SHA，服务中途合同变化会拒绝继续写混合版本。

本轮选定12条的匿名队列另存`reports/pilot12-review-queue-v2/`：片段6、8、9、10、12、13、14、15、16、17、18、20。导出器对8191当前GET媒体实际字节计算SHA，再匹配原片，不向审片者输出目标类别、提示词或预测；没有填入身份、观看声明、次数或发送审核POST。v1片段19为旧pilot04 D，仍保留；v2用新片段20替换。token仅绑定当前服务，重启须另导新队列，不能覆盖旧队列或用户未保存内容。实际操作者可接受或排除，排除可保留未知，不要求12条全通过；这些记录仍不是临床专业资格证明。

2026-10-19用户另请助手完成所需标注，并明确此前“看过都可以”仅指6条体育视频。因此另建`reports/ai-assisted-annotations-v1/`，不把该对话声明填为肩外展人审。4份逐片AI提案记录全241帧联系表、真正查看过的原尺寸帧、原片/PTS/RGB/SHA与阶段证据；归一化标签在`normalized-labels-v2.json`，校验在`validation-v2.json`。可见计次提议为4条完整往返各1次、4条抬起保持但未返回、4条静止；不由请求类别、B0或骨架时刻生成标签。阶段内部可确认区间和过渡候选范围分别保存，解剖左右侧未独立确认，细微屈肘不能区分投影/合成轮廓时保持未知。

逐片严格合同AI草稿另存`annotations/ai-drafts/pilot12-v1/`，`reviewer_role='ai_draft'`，人工观看声明false，来源仍pending，临床质量未知。原提案如果只确认整个往返但未选齐五个确切边界，严格导出将该完成/次数监督保留unknown，不取候选范围中点补值；原AI可见计次提议单列保留。已有明确AI候选单帧仍保留其不确定范围和非人工来源，不能称独立真值。查看页`点这里_康复AI辅助标注.html`可按实际PTS跳段和前后帧核对、导出JSON，只供AI辅助复核，不提交人工审核，不等于独立盲审。正式12片人审门、60条及训练门未被绕过。

本批12条严格合同均通过结构校验、资格均false；全部2892帧实际重解码的PTS/RGB与已发表timeline逐字段一致。归一化v2 SHA `35c9c56aca6a813a7e9f2a5c133323b043714d5ba278221a7c6339e854720519`，原4份提案未覆盖。片段10/17的精确完成边界不足，严格count保持null，其余10条strict count已知仍仅为AI提议。校验v1误把计划自身`plan_sha256`字段纳入合同摘要；v2排除该字段后与实际计划/盲审队列的`068a5117…3119c`完全一致，旧版与`correction_receipt`保留，这不是源计划变化。

查看页用本机隔离Chrome headless实际检查12条640×384原片加载、241/30秒时长与原PTS跳转，桌面及412px窄屏无横向溢出、控制台异常0。首次截图加载指示尚未消失，另用`requestVideoFrameCallback`确认0.033333秒和0秒帧已呈现、readyState=4并等浏览器指示消退后重截；最终可视检查见`viewer-qa-v3/{qa.json,desktop.png,mobile.png}`。本轮无新模型推理/GPU生成、无产品依赖或正式UI变更；此前264项工程测试结果保留，不把本轮12份数据校验混算为新测试数量。

专业临床质量需另取得两名独立标注者与第三人专业复核及真实资格依据；本地网页没有创造这些人员或授权。独立真人测试参考也不能照着本模型的阶段、次数或骨骼填写。原MobiPhysio导入器保持其原来源资格，不将合成视频改名伪装为公开数据集。

## 双后端、训练与比较的调用顺序

CLI按上述顺序执行；下列Python API可用于进一步审计绑定关系。正式训练命令必须先取得合格原片和真实人工参考：

1. `video.probe_video(video,timeline_path=...)`保存完整原始PTS；`create_frame_manifest(video,...,sampling_hz=15)`创建共同原帧清单。
2. `pose.extract_pose(video,frame_manifest,output_dir,sample_id=...,backend='yolo17')`与`backend='mediapipe33'`分别运行，使用不同输出目录。
3. `review.load_reviewed(root)`取得实际人工合格参考；每个时序record明确绑定sample、timeline、共同frame_manifest、单一backend的pose、人工annotation、固定split及实际side。
4. 冻结B0配置并`temporal.replay_baseline`；两个后端分别`temporal.train`、`predict_run`。归一化只从train拟合、仅val选型/早停、未知和padding不进损失。`engineering_test=True`只允许显式TEST来源，不可改名成为研究结果。
5. `evaluation.compare`比较同一固定队列B0/B2，保留缺输出和未知分母，输出逐片误差。边界容差预先声明，默认工程容差不当临床标准。
6. 模型与阈值冻结后，再另用公开真人独立测试参考；如果真人数据需要调参，须另设开发集并保留最终未触碰测试集。没有真人测试时只报告合成域结论。

训练前卸载ComfyUI视频模型，先检查磁盘、显存与内存预算。原YOLO/MediaPipe权重保持官方冻结；只有错误分析证明定位瓶颈且取得独立人工关键点后，才另立姿态微调实验。

## 当前验证与未完成事项

最新实际验证为20条人物原片、4个pilot来源组件，全部SHA及真实PTS通过，全部pending；`eligible_annotations=0`、`accepted_formal_count=0`、`training_performed=false`。4组各A/D/E的所选12条人物调试片均已生成并完成全241帧AI及双CPU121/121、0失败检查；实际输入PTS/RGB/JPEG一致。它们均为原生640×384、241帧、30fps；AI/模型诊断不是人工GT或临床准确率。实际CLI报告`reports/pilot-validate-cohort12-repaired-v2.json`，当前选片与历史attempt分开保留，不把20片当20个独立来源。

最终12片证据索引为`reports/pilot12-evidence-index-v2.json`，文件SHA `cc610310488bbfac91e59498391efd7305655c33e0394e7b23c612a1dfc9596b`。它严格读取v2选片，逐片绑定原片SHA、实际run/result、AI报告SHA、双CPU pose/model及共享PTS/RGB/JPEG，另保留历史bad variant和validate/cost/freeze拒绝/匿名队列原件SHA。完整重解码后实读人工版本0、latest human_operator 0、eligible 0；这份AI证据索引不创建或替代人工参考。

完整35个Comfy任务均有成功执行事件：20动作、6参考、9文本条件。动作实际执行129.156–306.182秒，均值255.633秒；观察窗口均值263.791秒；参考实际执行均值84.689秒。成本快照`reports/costs-20261019-cohort12-repaired-v2.json`保留逐任务窗口与采样数；完整模型SHA核验的额外CPU时间不在Comfy执行窗内，采样/VAE各阶段时间未知，观测极值不作连续峰值。

以下保留较早时点的验证记录。197项工程测试曾使用本机产品解释器通过，耗时8.555秒；不能当作数据条数或临床标签数量。新增官方工作流测试第一次因Windows默认GBK读取UTF-8文档而真实失败，显式UTF-8读取后整套通过。审核测试用临时真实9帧小视频与显式TEST记录，不写入真实数据根目录。9片时点的实际CLI报告eligible_annotations=0、accepted_formal_count=0、training_performed=false；它们仍为同一pilot02来源组，不能当9个独立人物。

审核页另以本机已安装Chrome headless、全新临时profile运行工程浏览器QA：桌面1440×1120、窄屏412×1000，实际片单/原片加载与真实视频播放均核对。明亮5:3测试片在Chrome报告videoWidth=160、videoHeight=96，requestVideoFrameCallback确认帧已呈现，timeupdate各2次、currentTime从0增长到约0.56秒，media error=null、seeking=false；画布读取到实际绿色帧像素。CSS object-fit=contain且aspect-ratio=160/96。空白次数/身份/来源选择、未勾选人工观看、未保存参考均保留；JavaScript控制台异常0，两尺寸无横向溢出。截图与原始结果仅留本机忽略目录`.runtime/rehab_ml/review-ui-qa/`，不属于真实人工全片审核或动作验收。

截至本文记录：**没有真实人工审核记录、正式60条肩外展合格集、目标域B0/B2训练与独立真人效果比较的完成证据**。原有正面/侧面六条深蹲、步行、硬拉成片是此前工程演示，未取得本方案人工GT，不能计入肩外展训练集。各参考图、pilot候选与GPU任务状态应查本机当前任务句柄、原片与清单；本文不将“已排队”或“有视频文件”写成“已合格”。

下一道真实验收门槛是可用参考构图、12条调试片的完整筛片及真实工程阶段/次数标注。满足后才能更新正式来源分组、生成60条候选并按实际合格/排除记录补齐；人审未完成时可以完善工具，不能伪造人工身份或模型改进结果。

独立正式生成入口已补代码与隔离工程验证，但实际人审为0，未创建真实正式冻结，也没有开始正式60条。现有pilot入口仍仅4组和train；新正式入口须逐次核验冻结来源、真实模型/配置/实现字节与已保存人审，再提交单作业。不能把接口、请求槽位或工程测试成功写成正式样本完成。

还须在扩量前冻结“实际覆盖”的事实标准：`scenario`仅为生成目标；完整/慢速/保持/部分/无关/可观察变化可能重叠，不能把目标A–F的槽位当作六类实际标签。当前训练报告明确标记 `requested_generation_targets_only` 和 `observed_scenario_coverage='not_established_by_this_command'`；命令完成仅指该流水线执行。F类两项可观察变化的独立可评价性/时段入口已补，实际人工记录仍为0，不宣称覆盖已完成。双侧事实允许归档，但未拆成明确单侧参考前不能进入此单侧TCN。

## 已取得的本机真实运行证据

- 新5模块及独立测试加入后，全部264项专项测试在本机产品Python（未强制UTF-8模式）完整通过，181.748秒，日志`E:/ai-video-lab/synthetic-tests-20261019-formal-endpoint-all-v2.log`。前一轮263过、1项TEST临时目录长短名转换错误，旧失败日志保留；修正测试中的规范化路径后完整重跑。覆盖真实媒体RGB/PTS、未知/人审门、来源闭包、实际首图/缓存采样中变化拒绝发布、注册历史回滚、任务缺失/失败不重投，以及默认旧图不变。
- 扩到pilot01 A/D/E、pilot03 A/E的15片时点仍只有3个来源组件，全部pending；CLI完整SHA/PTS核验为`reports/pilot-validate-expansion-endphoto-v1.json`，合格人工参考和正式样本均0。pilot01 A/E原墙patch首末降约0.688%/0.747%，pilot03 A/E约0.231%/0.0818%；AI全241帧未见明显黑尾，双后端各121/121、0失败。同一D纯姿态方法在pilot01首199.39→末55.85（降71.99%），故暂停原自动队列；提示/骨架/旧人物成功不能替代新人物实测。
- 不同末图D实际另取旧pilot01 D frame150，真实PTS76800×1/15360=5.000秒，原始RGB未编辑，PNG SHA `a2c8b23d63b4d5e6320e43c73190d7f3438ee4f8fb96ae51487cf18ef68b4e73`。只增加LoadImage37并接node36，仍63→31→241；原片和条件父链全部保留，新原片属于同pilot01/train。新执行Comfy280.724秒、观察285.349秒；56个GPU观测最高5063MiB/90°C，92个内存观测最高17.17GiB服务RSS、最低3.00GiB物理和13.17GiB提交空间，非连续峰值。整进程还含前后完整权重SHA核验，这段不包含在Comfy执行窗；成本快照`reports/costs-20261019-expansion-endphoto-v1.json`保留当时另一个未完成任务，未把其部分窗口算资源。新D已发布并通过完整原片验证，AI初筛仍保持部分抬臂、末帧明亮，实际完整诊断单独保留，不据此改GT或宣称通用黑尾修复。
- 新D完整诊断已完成，双后端各121/121、0失败、单轨迹、实际输入PTS/RGB/JPEG一致。模型命名左臂YOLO11.19→39.32峰→38.57°末、MP10.23→37.06→36.64°末；B0均预测0，骨段相邻变化超过25%为0。AI全241与原尺寸0/90/240确认保持、镜头稳、头鞋完整、未见黑闪；手指偏软仍保留。同旧D ROI的新原RGB首199.10→末199.89（+0.396%），全程198.25075–200.77037，最暗frame4/0.133秒，没有该区域先黑后亮的证据。报告`reports/assistant-visual-screen/pilot01-D-distinct-endphoto-v1/AI-diagnostic-summary.json`与`old-vs-distinct-endphoto-fixed-wall-comparison-v1.json`，不转成人工标签或准确率。
- 后续pilot03 D、pilot04 A/E也实际生成并全241帧AI检查；双CPU各121/121、0失败、输入PTS/RGB/JPEG一致、单轨迹、相邻骨段变化超过25%为0。pilot03 D保持且墙首末降约0.134%，04 A/E约0.699%/0.457%；B0对D/E均预测0、对A预测1，不作实际计次。报告在`reports/assistant-visual-screen/remaining-pose-pilot-v2/pilot03-D-v1/`及`pilot04-{A,E}-v1/`；03D实际run是`audit-pilot03-D-cpu-v1`，以`actual-run-binding.json`为准，不用早先未启动的计划ID。
- pilot04 D纯姿态候选实际全片保持，但固定墙首72.126→末41.592（降42.3345%）；旧raw SHA `8ba38f56432d93392b2edb6a5945bb8d84cb120b2ff5eedcd16398dbbe17b308`保留。另取同片frame120、真实PTS61440×1/15360=4.000秒的未编辑RGB为末图，PNG SHA `4d3d5c2370ae75d41266c4814ef284f84c31a468debd1514f278ac4acd354359`，收据`conditioning-endpoints/pilot04-D-hold-frame120-v1/endpoint.json`。新raw SHA `b798422cfa8e75d0756fd4ca57dd2f6ef508dba9dcd8eccfe44aaa8203943df1`，仍同pilot04/train；实际Comfy267.122秒、观察270.400秒，53个GPU样本最高5064MiB/91°C，87个内存样本最高17.17GiB服务RSS、最低3.12GiB物理/13.97GiB提交空间，非连续峰值。
- pilot04新D实际run `audit-pilot04-D-endphoto-cpu-v1`，双CPU各121/121、0失败、单轨迹、实际PTS/RGB/JPEG/inferenceRGB一致。AI全241帧及原尺寸0/90/240仍见部分抬臂保持至末，无回程，未见原明显黑尾或明显肢体增失；手指偏软/张开及脚靠近底边仍保留。相同墙ROI首72.181→末68.412（降5.2222%），全片最小67.9955在frame130/4.333秒，最大72.6224在frame17/0.5667秒，因此是改善，不能称恒亮。YOLO命名左上臂9.369→35.274峰→33.848°末，MP11.739→35.719→34.954°末，B0均预测0；不作GT或临床ROM。完整报告`reports/assistant-visual-screen/remaining-pose-pilot-v2/pilot04-D-endphoto-v1/AI-diagnostic-summary.json`，SHA `392748ece6c1c643d7e2502d83151dcdf4dc1d3b156abadb81ffc5d476f7f234`。

- 五个生成模型文件已按原锁完整重算SHA，回执在本机 `manifests/model-verification.json`。四条97帧参考片均完整生成；助手首帧构图筛查拒绝了裁脚的pilot01和手臂已抬起的pilot03。这个筛查不是人工完整观看。
- 四条参考片Comfy实际执行82.193–88.169秒，均值84.43秒；执行窗内采样到最高5707MiB显存、17.09GiB服务RSS，最低可用物理内存3.22GiB。采样/VAE阶段耗时未知，温度和完整样本数留在 `reports/costs-20261019-first-references.json`，不把这些观测值称为连续峰值。
- 静止参考片实际97帧→共享49帧，两个CPU后端49/49检出且原PTS/RGB与推理输入像素一致。第一条真实动作片241帧→共享121帧，YOLO17/MediaPipe33均121/121检出、0推理失败，实际耗时8.995/8.047秒，模型hash和两端实际JPEG输入均对账；两条B0在预声明分析左侧下输出0。没有人工真值，不能算准确率或漏计率。
- 动作预检v1曾因生成环境PyAV19.0.1与产品16.0.1版本字段导致整个timeline文档hash不同而真实拒绝。frames/v2保留原文档hash，另加全部PTS/像素/几何/流原点的语义指纹；全媒体证据严格相同时才允许跨解码器版本。旧失败run和v1共享文件保留，实际成功回执为 `reports/pose-preflight/pilot02-action-preflight-v2-audit.json`。
- 第一条请求A完整抬放的候选在助手抽帧中实际双臂抬高并保持，未见要求的回程，部分手部靠近上边界。请求D的候选在抽帧中为画面左侧手臂抬起后保持。它们仍为pending，不按提示词补次数、左右或完整标签。抽帧不是完整人审；提示词遵从失败与实际可用阶段数据分开记录。
- 此前体育正/侧面六条成片本轮只读重验：均305帧、1280×720、30fps、真实PTS严格1/30秒，SHA与原交付回执一致。它们有已记录的轻微模糊、局部补背景纹理等瑕疵；不是本训练集或同步双机位。
- 同seed、同文本、同参考图的末帧引导A试验已实际完成，原生241帧、30fps，无循环/倒放/插帧，Comfy执行129.156秒。助手抽帧看见双臂抬起再放回；中段推近镜头且下肢出框，因此不能宣称达到单臂、固定机位或合格源片要求。E候选末段明显变暗，也留待实际人审。这一路径保留4条历史候选，不直接扩正式60条。
- 首条全帧姿态控制A候选已在原4070 Laptop 8188MiB显存机器上实际完成：Comfy250.100秒、观察总时长255.461秒，原生640×384、241帧、30fps。执行窗50个GPU样本观察最高5102MiB、90°C；81个内存样本观察最高17.13GiB服务RSS、最低3.75GiB可用物理内存和14.9GiB可用提交空间。这些是采样极值，非连续峰值；纯图合同的默认“未验证”不被改写，独立单次本机执行证据见 `reports/pose-preflight/pilot02-pose-local-execution-v1.json`。
- 此A片241帧全解码并由助手查看全帧联系表，双CPU姿态121/121检出、0推理失败、单轨迹、输入PTS/RGB完全对账。模型命名左臂上臂投影：YOLO约17.53→67.25→17.88°、MediaPipe约12.35→68.93→12.92°；右臂基本静止。两条冻结B0输出1次，只是预测，不是准确率。控制命令峰79.08°与成片预测峰67–69°不同，不能把控制值当作成片标签。未见明显推拉/跳切/肢体增生；手指偏软、鞋底接近画幅下缘、末尾墙面固定区域亮度下降约35%，均作为AI筛查瑕疵保留。完整筛查报告在 `reports/assistant-visual-screen/pilot02-pose-A-v1/`；不等于真实人审。
- 实际双后端入口首次拒绝新A片的重复 `reference_video` 来源token；保留失败run、元数据修复前后完整快照及变更回执 `manifests/metadata-corrections/pose-A-lineage-dedup-v1/`，仅去除完全相同token，来源集合/原片/PTS/标签未变。修复后CLI实际验证5条原片通过；新生成器和回归测试防止重复再现。
- pilot01/pilot03已另生成wide-v2参考attempt2，原失败参考未覆盖。助手首帧看见全身和双臂垂下；pilot03新图鞋底仍只有约2–3px边距，保留风险，不算最终人审通过。连同pilot02/pilot04，4组实际参考CPU YOLO均49/49检出，12条程序控制视频已独立逐帧验证PTS/RGB与刚性轨迹，4组未共享来源token。这里的12条是骨架指令，不是12条合格人物视频；来源审查侧车的前后快照与CPU报告均保留。
- 新8191实际v2审核页另以独立临时Chrome只读验证：5条匿名片单，姿态控制A片媒体SHA与原片一致，640×384、8.033秒实际呈现，逐帧PTS定位误差小于1微秒。两观察项全部unknown/mask=false，身份/角色/次数空且未勾观看，POST与控制台异常均0。证据在本机`.runtime/rehab_ml/review-ui-qa/qa-actual-pose-v2.json`及`actual-pose-v2-desktop.png`；未产生人审记录。
- 姿态控制D/E也已实际完成，Comfy分别283.181/288.373秒；全部原生640×384/241帧/30fps。双CPU后端各121/121检出、0失败、实际帧像素一致。D模型左上臂YOLO约16.98→34.69峰→34.51°末，实际保持而无回程，背景亮度下降约2.4%；E双臂基本静止，腕点最大偏移约3.33px，但7–8秒明显渐暗，墙面固定区域均值约122.08→24.37（约80%下降）。两条B0均预测0次，不是人工真值。E存在明显场景捷径风险，未按这条路径直接扩批。原报告及D联系表初版画布裁切错误的修正回执全部保留，见 `reports/assistant-visual-screen/pilot02-pose-{D,E}-v1/`。
- A/D/E三条骨架试片完成后，CLI验证7条原片及真实PTS/SHA全部通过，人工/正式合格数仍0；它们均来自同1个pilot02来源组，不能当7个独立来源。报告 `reports/pilot-validate-pose-ADE-v1.json` 与 `reports/costs-20261019-pose-ADE-v1.json` 记录这一时点。下一试验仅增加原生末帧参考约束检验渐暗，未预先宣称有效。
- 为检验E黑尾，独立v2在全帧姿态guide后追加同参考PNG到frame240；原31视频latent＋31姿态guide＋1末图＝63，使用最新条件在Separate VIDEO后裁去32份guide，回到31→241帧。纯图v1 golden SHA未变；本机原生源码的独立CPU张量复核（VAE形状stub，无模型）与实际提交图核验在 `reports/pose-preflight/native-pose-endref-chain-v1/`。如果Crop误接旧34条件会残留1份guide，回归测试明确拒绝这一连线。
- 新E末图试验实际成功，原生241帧、640×384/30fps，观察总时长270.512秒。同一人物、seed、文本和骨架指令，仅增末图条件。全241帧AI筛查未见黑尾、切镜或新增肢体，双后端121/121检出、0失败、B0均预测0；腕点最大偏移约2.78px。固定同一墙patch的原RGB首尾均值122.97→121.90（下降约0.87%），旧E为122.08→24.37（下降约80.04%）；没有做亮度归一化。该结果是单次AI诊断，不能当人工GT、通用因果保证或人物结构合格证明。脚靠近下缘、手指细节软仍保留。报告在 `reports/assistant-visual-screen/pilot02-pose-E-endref-v1/`；现有人物原片8条，仍同1个来源组，人体A抬放的末图变体另做实际试验，不能用静止成功证明动态也成功。
- 新E该固定patch全部241帧均值范围121.90–124.20（最暗frame240/8.000秒，最亮frame70/2.333秒），没有这个区域先变暗再回亮的证据；不据此排除其他局部闪烁。Comfy实际执行263.718秒；执行窗53个GPU样本观察最高5095MiB，86个内存样本最低3.37GiB可用物理、13.16GiB可用提交空间，非连续峰值。此v2在本机一次实际完成的证据另存成本报告和提交图，不把纯图合同的默认未验证字段改成普遍支持声明。
- 动态A的末图变体也实际完成，Comfy272.985秒、观察总时长285.454秒，原生241帧。双后端121/121检出、0失败、实际像素一致；模型命名左臂YOLO约16.79→66.48峰→17.28°末、MediaPipe约12.26→69.02峰→12.82°末，两条B0均预测1次。AI全241帧仍看见单臂抬放、对侧基本静止，无明显推近、切镜、新增肢体或黑闪；手指偏软、脚贴底风险保留。相同固定wall patch全部241帧范围121.83–124.06，首122.82→末121.83（降约0.81%），旧A首末降约34.72%。这里只比较实际观察，不把同seed等同于不同latent形状下的逐元素相同噪声，也不宣称通用因果效应。报告 `reports/assistant-visual-screen/pilot02-pose-A-endref-v1/`；整批9条SHA/PTS验证为 `reports/pilot-validate-pose-endrefs-v1.json`，成本为 `reports/costs-20261019-pose-endrefs-v1.json`。其余3组9个目标槽位使用A/E末图v2、D纯姿态v1条件继续pilot，不据此跳过实际筛查/人审或开始正式60条。
- 实际8190审核页以全新Chrome临时profile只读核验：片单4条，前三条均真实呈现640×384、241帧、8.033秒，真实PTS定位误差小于1微秒，无媒体/控制台错误；未填身份或次数，未勾观看，未发审核POST。证据留在本机`.runtime/rehab_ml/review-ui-qa/qa-actual-pilot.json`及`actual-pilot-desktop.png`。新增片后的旧token保留；该浏览器验证不是人审或动作验收。
