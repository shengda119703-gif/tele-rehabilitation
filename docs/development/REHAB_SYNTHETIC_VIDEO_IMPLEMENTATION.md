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
| `pose_guidance.py` | 固定19B姿态IC-LoRA、原生全帧guide、8步euler与采样后CropGuides；纯图构建及本机执行证据分开 | 本机一次运行不能证明任意分辨率/显存都支持，身体控制也不保证手指细节或动作精确 |

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
```

HTTP400正文和任务句柄会保存。ACK丢失、超时或失败都不能自动重发同一个生成任务；先查看已有句柄和错误。完成后再次核验控制输入，生成清单去重来源token并保留每个不同实际来源。

## 原片与人工参考合同

母片清单为 `manifests/dataset.json`。样本包含sample/source/reference组、lineage、固定split、pilot/formal、动作/实际侧别/视角、原片SHA/尺寸/帧数、timeline路径及SHA、生成模型/工作流/提示词hash与seed。实际侧别未知时保持unknown，不能把生成器请求的左侧直接填为人工确认。

`contracts.load_manifest`默认核对原片与PTS索引SHA，并重新完整解码实际时间轴。`verify_files=False`只用于结构检查，不能据此宣称媒体验证通过。纯函数`validate_manifest`接受已加载timeline用于一致性检查；正式完整性应显式设置`require_formal_complete=True`，pending和excluded不计合格60条。

`freeze_splits`创建正式10组6/2/2冻结记录；应把该记录与事先确定的来源分组方法保留。工具检查记录自洽，不能凭可重算的hash独立证明历史上从未改过拆分。来源证据与版本历史仍须保存。

实际工程标签由真实操作者完整观看后填写：

1. 浏览器打开命令输出的`http://127.0.0.1:8190/`，选择随机opaque编号的原片。页面不显示生成目标类别、提示词、骨骼或次数预测。
2. 完整观看，必要时用上一帧/下一帧/滑条按实际PTS定位。填写本人标识，主动选择人工来源与实际解剖侧。次数开始为空，确认0次也必须实际清点。
3. 标可确认阶段区间；逐次边界使用`ready / outbound / endpoint_or_hold / return / rest_or_other`。未知保持null和false mask，不能用休息类填满未知。
4. 大于0的可确认次数须有对应逐次完成记录；肩外展完整往返要求明确五个边界。幅度小和过程未完成分开，不自动用健康人幅度阈值定错。
5. 原片通过需实际人工完整观看声明；肢体增生、融化、跳切、穿模等排除并说明原因。两项非临床图像事件“肘部弯曲”“躯干侧倾”各自填写可评价性、出现/未出现/未知及实际PTS区间；未知不等于未出现，不可评价也不监督为未出现。专业临床质量仍未知。
6. 保存会另建不可覆盖版本，不重写生成清单。播放coverage只保存为辅助声明，`reviewer_identity_is_verified`始终为false。AI草稿可保存，但不能批准原片、不能进入训练。

审核记录保存到`annotations/review-versions/<sample_id的SHA256>/<时间及唯一版本>.json`。版本绑定原片/PTS索引SHA、人工annotation SHA、`source_patch`及工程资格结果。`review.load_reviewed(root)`在内存把最新明确决定应用到完整队列，返回manifest、timelines、annotations与eligible_annotations；不会覆盖生成器正在追加的清单。后续训练应调用该接口及`contracts.validate_annotation`，不能只按文件名收集所有JSON作为标签。

当前运行的新审核入口为 `http://127.0.0.1:8191/`；旧8190服务与用户页面未关闭。标签合同v2和数据卡v2的独立外部快照在 `manifests/protocol-configs-v2/`，旧 `protocol-configs/` v1副本未改。旧quality空列表仍表示所有这些观察未知，不能迁移成“未出现”。每份新审核版本绑定合同SHA，服务中途合同变化会拒绝继续写混合版本。

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

合成专项183项工程测试已使用本机产品解释器通过，耗时11.364秒；不能当作数据条数或临床标签数量。新增官方工作流测试第一次因Windows默认GBK读取UTF-8文档而真实失败，显式UTF-8读取后整套通过。审核测试用临时真实9帧小视频与显式TEST记录，不写入真实数据根目录。实际5条原片另以CLI完整验证PTS/SHA，报告eligible_annotations=0、accepted_formal_count=0、training_performed=false。

审核页另以本机已安装Chrome headless、全新临时profile运行工程浏览器QA：桌面1440×1120、窄屏412×1000，实际片单/原片加载与真实视频播放均核对。明亮5:3测试片在Chrome报告videoWidth=160、videoHeight=96，requestVideoFrameCallback确认帧已呈现，timeupdate各2次、currentTime从0增长到约0.56秒，media error=null、seeking=false；画布读取到实际绿色帧像素。CSS object-fit=contain且aspect-ratio=160/96。空白次数/身份/来源选择、未勾选人工观看、未保存参考均保留；JavaScript控制台异常0，两尺寸无横向溢出。截图与原始结果仅留本机忽略目录`.runtime/rehab_ml/review-ui-qa/`，不属于真实人工全片审核或动作验收。

截至本文记录：**没有真实人工审核记录、正式60条肩外展合格集、目标域B0/B2训练与独立真人效果比较的完成证据**。原有正面/侧面六条深蹲、步行、硬拉成片是此前工程演示，未取得本方案人工GT，不能计入肩外展训练集。各参考图、pilot候选与GPU任务状态应查本机当前任务句柄、原片与清单；本文不将“已排队”或“有视频文件”写成“已合格”。

下一道真实验收门槛是可用参考构图、12条调试片的完整筛片及真实工程阶段/次数标注。满足后才能更新正式来源分组、生成60条候选并按实际合格/排除记录补齐；人审未完成时可以完善工具，不能伪造人工身份或模型改进结果。

还须在扩量前冻结“实际覆盖”的事实标准：`scenario`仅为生成目标；完整/慢速/保持/部分/无关/可观察变化可能重叠，不能把目标A–F的槽位当作六类实际标签。当前训练报告明确标记 `requested_generation_targets_only` 和 `observed_scenario_coverage='not_established_by_this_command'`；命令完成仅指该流水线执行。F类两项可观察变化的独立可评价性/时段入口已补，实际人工记录仍为0，不宣称覆盖已完成。双侧事实允许归档，但未拆成明确单侧参考前不能进入此单侧TCN。

## 已取得的本机真实运行证据

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
- 实际8190审核页以全新Chrome临时profile只读核验：片单4条，前三条均真实呈现640×384、241帧、8.033秒，真实PTS定位误差小于1微秒，无媒体/控制台错误；未填身份或次数，未勾观看，未发审核POST。证据留在本机`.runtime/rehab_ml/review-ui-qa/qa-actual-pilot.json`及`actual-pilot-desktop.png`。新增片后的旧token保留；该浏览器验证不是人审或动作验收。
