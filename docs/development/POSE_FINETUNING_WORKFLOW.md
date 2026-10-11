# 康复 RGB 姿态训练：数据资格、训练循环与独立评价

任务书12.1–12.3的后续实施，最终复验基于`7647037`。`train-pose`不再只有全局拒绝占位，而是一个有条件的离线多轮训练器。原YOLO11n-pose、Ultralytics8.3.199和双层masked loss保持；不安装／升级库，不改UI、APK、正常数据库或正式模型。

## 1. 数据进入训练前

输入是 [RGB独立参考清单](POSE_REFERENCE_WORKFLOW.md)，不是现有模型输出或患者历史。实际检查包括：

| 检查 | 不满足时 |
| --- | --- |
| analysis和training均明确授权，核对授权材料引用／SHA／verified_by | 在创建输出和子进程前拒绝 |
| RGB原图尺寸／SHA、帧序／来源时间、人体框与COCO17独立标注对齐 | 拒绝转换或训练；不自动修标签 |
| 可靠定位、已复核不可定位、未标点分别编码，标注者与复核者不同 | 不把模型confidence当visibility或未标点当负例 |
| 按人、原录像和原图隔离train／val／test，额外防止身份大小写绕过 | 拒绝训练；不重新划分以凑高分 |
| 每个split确有可定位参考点 | 不用空监督或不存在点产生完美分数 |
| 原图不超过1920×1080；原有清单≤4000样本／512MiB图像预算 | 超出时拒绝，不偷偷缩小参考图 |
| research必须RESEARCH且human独立来源；engineering_test必须TEST且synthetic_fixture | 两种模式不能混用，工程测试不授予真人资格 |

权限材料哈希与复核声明是可追查输入，不是程序对法律、标注质量或医学效度的独立认证。原权重的上游训练参与者不能被本项目排除证明；报告保留此限制。目前实际没有新增合格真人RGB与专业标签，仍为`blocked_missing_supervision`，IRDS三维整次标签不满足这条RGB监督。

research在任何优化步骤前，先用原模型对验证集实际推理并评价。若按冻结PCK标准原模型已全部通过，则拒绝该轮微调，避免只有规则问题却宣称要训练姿态。数据定义和专业质量仍须审核，PCK门槛本身不是医学标准。

## 2. 配置与可运行入口

[配置模板](../../configs/rehab_ml/pose_finetune_template.json)为严格版本化JSON；reference和output_dir空值是未填写，不是可运行数据。填写后另存到专用忽略实验目录，路径相对该配置文件解析。未知选项、非有限值、布尔冒充数值或越界值均拒绝。

| 参数 | 支持范围／含义 |
| --- | --- |
| device | 显式cpu或cuda:0；CUDA不可用拒绝，不静默换设备 |
| image_size／batch_size | 64–640、32倍数／1–8；训练图分辨率，不是临床精度 |
| max_epochs／patience | 1–100／1–max_epochs；验证集决定早停 |
| optimizer | AdamW；learning_rate 1e-7–0.01，weight_decay 0–0.01 |
| clip_norm／freeze_first_layers | 有界梯度剪裁／冻结前若干层，保留pose head；原DFL投影仍固定 |
| brightness／contrast | 0–0.2；仅训练集颜色增广，逐批记录实际随机值 |
| confidence_min | 0.5–1；原Keypoints会清零低于0.5的坐标，不能降低门槛后把这些0当已观察点 |
| pck_threshold | 0.001–1；人体框对角线归一距离，默认0.05，是工程比较口径 |
| threads／timeout_s | 1–4／10–7200秒；最大等待，不表示OS创建硬截止 |

实际入口：

```powershell
# 用明确标记的工程数据核验完整接线，不进行真人训练
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_pose_training.py
```

资格满足后的命令为`train-pose --config <填写后的JSON>`；取消为`cancel-pose-training --run-dir <该次输出目录>`。这两处尖括号是待填写参数，不列入已执行记录。默认产品解释器原环境原版本，不为了CUDA安装新依赖。

## 3. 从样本到模型包

```text
冻结配置／参考清单／按人划分
  → 原YOLO验证集基线与问题门控（优化之前）
  → train内部打乱 → 小批次 → 实际整数resize／letterbox
  → 仅train颜色增广 → 原检测＋双层masked pose loss
  → AdamW／有限梯度检查／剪裁 → epoch末last检查点
  → 原框辅助匹配的val独立评价 → 保存best／早停
  → 冻结best选择 → weights_only严格重载
  → 原模型与best各测test一次 → 结果／模型卡／状态
```

图像的实际整数宽高resize比例分别用于框和关节，不能用理想单一比例代替整数缩放；未标点与已复核不可定位点仅有数值占位0，各自mask不同。没有左右翻转、几何旋转、遮挡、伪标签或随意变速；以后加这些增广须同时验证标签变换。

坐标监督`c_j=m_j∧(v_j>0)`，objectness监督`o_j=m_j`，仍使用 [双层损失](POSE_DUAL_MASKED_LOSS.md)的有效槽归一。检测／DFL／TAL和五项gain不改变。人体框来自独立全身框，当前参考格式每张样本一个目标对象；有其他未标人物的训练素材还须审核，不能据此声称密集多人训练已支持。

只train进入梯度、颜色增广和优化器。被冻结层的参数和BatchNorm缓冲均保持，原DFL分布投影不更新。每批检查有限梯度和参数，损失不有限时不执行下一步；原模型文件在结束时再次核对。

## 4. 为什么不是用训练损失选最好模型

单点归一距离为`e_j=||p_j−q_j||₂／人体框对角线`；有效独立定位参考总数为`N_ref`。缺测点仍留在分母：

```text
coverage = N_covered / N_ref
PCK_all  = count(covered 且 e_j ≤ threshold) / N_ref
best_key = (PCK_all, coverage)  # 按顺序比较；同分保留较早checkpoint
```

不采用只在已检测点中计算的高分作为第一选模目标，也不以低训练loss选择模型。验证集每轮用于选模，测试集直到best冻结才使用。少量验证集和反复外部选实验仍可能过拟合，工程工具无法替代合理的独立实验设计。

验证和测试复用原YOLO的JPEG95输入、640图、track(conf=0.35)与每图重置跟踪，按独立框IoU≥0.5唯一匹配。操作的是训练模型副本，推理的层融合不得改变训练中的权重／BatchNorm。它是逐图、参考框辅助的评价，不证明无人辅助连续跟踪、计次、临床ROM或手机性能；冷加载／跟踪耗时也不能直接当实时p95。

## 5. 产物、取消和恢复边界

所有输出必须新建在专用忽略data/run根下，不能覆盖已有实验、原数据、患者库或正式权重。

内部子进程入口也先解析路径：请求必须是专用根下某次输出的`request.json`，检查在获取OS锁之前执行。失败记录只写通过该路径检查的run；范围外请求或错误文件名不在调用者文件旁新增／覆盖`failure.json`或`status.json`。实际子进程反例验证了范围外请求、失败和状态文件的hash不变；这不是对任意文件系统竞态的通用沙箱保证。

| 产物 | 作用 |
| --- | --- |
| request.json／resolved-config.json／resource-budget.json | 冻结请求、参数／源码输入指纹、初始空间与资源预算 |
| status.json／child.log／provenance.json | 阶段、epoch／step、实际命令、退出与日志hash；状态文件不单独证明进程存活 |
| train-order.jsonl／history.json | 实际训练样本与颜色变换、五项loss／梯度、验证选模过程；私人资料不提交Git |
| last.pt／best.pt | 原架构state_dict、优化器状态、Torch RNG、参考／配置hash；每份≤64MiB，原子替换本次自己的文件 |
| baseline-val、val-epoch-*、baseline-test、candidate-test | 帧对齐预测、缺测覆盖、误差和分组参考评价 |
| result.json／model-card.json | 最佳模型、真正轮数／步骤、原模型比较、域／split／来源／许可、禁止用途与未测范围 |
| cancel.request／failure.json | 明确取消请求或失败；部分检查点保留，不制造成功结果 |

真实训练子进程保留原pose容量1的非阻塞OS锁，并新增同checkout的重任务独占准入；v2正式会话的共享锁存在时直接拒绝。两把锁均在实际child持有，不仅由父进程预检。锁文件存在不代表进程运行，进程实际退出后OS释放；再次启动不按陈旧文件判运行。临时目录、库配置均在E盘专属输出中，设置offline／禁止自动安装，不打开相机或修改原服务。实现与实际双向拒绝／退出测试见 [资源准入](REHAB_COMPUTE_COORDINATION.md)。

取消请求只写本次冻结run下的标志，即使外部原配置已删除也可请求；请求响应不声称退出。子进程在批次／阶段／持出图之间检查，原生计算不可立即合作中断时仍受父进程最大等待约束。超时或Ctrl+C只释放准确所属句柄，未确认退出不报成功；初始建进程、hash、文件系统与native调用本身不保证独立OS硬截止。

最后检查点包含恢复材料，但本轮没有自动resume或接续失败实验；需后续核对配置、RNG、数据和split后另实现显式恢复。磁盘空间是保守预估，不是配额、物理磁盘满、断电或介质故障验收。新增互斥只覆盖v2与已接入的研究入口，不覆盖旧桌面／旧live／APK／其他checkout和全部报告作业，仍不能称全产品调度完成。

## 6. 已验证与未完成

[本机验收](../validation/REHAB_POSE_TRAINING_2026-10-11.md)区分单测、实际多轮原YOLO、实际早停／取消和缺权限拒绝。现有真人片训练权限false，没有借它们补标签。TEST工程图有合成定位参考，但不含人；覆盖与PCK为0、误差null是正常结果，不改参考或门槛制造收益。

工程实现可进入下一次合格RGB实验；真人微调规模、精度提升、动作计数／指导收益、目标手机、完整负载／物理故障、康复深蹲宿主计划与候选部署验收仍未完成。新模型包始终`product_enabled=false`、`deployment_eligible=false`，不接UI或APK、不重算旧历史。
