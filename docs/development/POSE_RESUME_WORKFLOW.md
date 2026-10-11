# 离线姿态训练：显式续训与数值执行契约

这是后端任务书第7节、12.1–12.3的增量。只作用于独立离线工具，不修改正式推理、UI、APK、原权重或正常用户库。真人训练仍须满足 [监督资格](POSE_FINETUNING_WORKFLOW.md)；工程恢复可用不等于真人准确性提高。

## 1. 恢复什么、不恢复什么

`train-pose --config <新配置> --resume-run <已中止的所属输出目录>`从**最后一个完成验证并提交的epoch边界**恢复。未完成epoch重新执行，不从一半batch继续；这是同一冻结实验的继续，不是另调参数的warm-start。

允许改变新输出目录和本次等待预算，其他算法配置、参考清单、划分、原模型、实现SHA及数值环境须一致。新输出必须不存在且位于专用忽略data/run根；旧run只读。无manifest的旧检查点不自动迁移。

以下情况在创建输出／spawn前拒绝：

| 条件 | 理由 |
| --- | --- |
| 已有result、model-card、test-started或测试目录 | 不通过续训反复打开固定测试集 |
| 无有效已验证边界、检查点超64MiB、路径／hash不符 | 不猜测哪个last可用或加载任意文件 |
| 配置、数据、划分或训练权限改变 | 不把不同实验拼成一次训练 |
| 源状态不明确，且无实际所属异常退出回执 | 陈旧training状态不是已退出证明 |
| v2正式会话或其他已协调重任务持锁 | 不关闭用户任务、不抢占他人的计算 |

恢复子进程再次核验，父预检不能替代真实计算进程的检查／OS锁。记录异常退出回执的request路径、实际命令、非零整数退出码、所属退出确认、源码和child.log SHA；回执或文件在预检后改变则拒绝。

## 2. 一次安全边界的信息

```text
train各batch → 有限梯度／更新 → 本epoch last
  → 独立val → best／patience → history
  → 新的交替resume检查点 → 原子manifest指针（提交点）

中断／已确认所属异常退出
  → 锁与资格／来源预检 → 新run → weights_only重载
  → 模型＋优化器＋RNG＋选模状态 → 下一epoch
```

`resume-a.pt`、`resume-b.pt`交替写入；先原子落完整新文件，再原子替换`resume-manifest.json`。指针写失败时旧指向仍有效。best权重嵌入恢复包，不依赖可能已经改写的best.pt。这不是断电／磁盘介质故障保证。

| 恢复包内容 | 下游消费者／校验 |
| --- | --- |
| 模型state_dict、优化器step／一阶与二阶动量、param_groups | 严格键／形状／dtype／有限性与当前组比较，再恢复真实优化器 |
| Torch CPU及CUDA RNG、NumPy RNG、全局及局部Python RNG | 所有初始化完成后恢复；下一次shuffle和增广继续原序列 |
| 已验证history、best_score／epoch、bad_epochs | 从历史重新推导选模与patience，不能绕过已经早停 |
| 内嵌best状态和digest | 新run另存继承best，之后选择仍只用val |
| 初始参数digest、原模型val摘要 | 保留实验起点；恢复不重新选另一份基线 |
| 数据／配置／原权重／实现SHA、数值环境 | 包、manifest、源请求和新配置一致；算法变更不能沿用旧包 |

本次`train-order.jsonl`只记新尝试；`history.json`带继承来源。`optimizer_steps`为实验累计，`current_attempt_optimizer_steps`为本尝试实际执行，不能混成重复训练量。

## 3. CPU数值策略及公式

仅恢复随机种子仍不足以证明原生计算逐位一致。本机早期实验中，输入、全部前向输出及各层输出反向梯度相同，三层卷积的权重梯度不同；进一步修复后还有原AdamW动量微差。这些失败没有按容差改判通过。

当前 [CPU数值实现](../../tools/rehab_ml/pose_cpu_gradients.py)使用三个明确版本。与Torch默认AdamW／其他硬件不保证逐位相同，不能拿新的工程验证证明旧配置也通过。

### 3.0 SiLU中间精度

版本`cpu_silu_fp64_intermediate_v1`，公式仍为`SiLU(x)=x·sigmoid(x)`。仅在拥有的训练模型上下文中，将输入转double完成原SiLU及其反向，再返回float32；上下文结束移除全部钩子，原heldout／生产推理仍用原激活。多批次定位中有一处conv wrapper前向微差，随后梯度最大差约1.46×10⁻¹¹；最终状态虽然一致，严格日志验收仍判失败，未删除这一反例。

### 3.1 卷积权重梯度

版本`fp64_conv_weight_accumulation_v1`。设输入展开矩阵为`X_b`，该层输出的反向梯度为`D_b`，对每个group：

```text
∂L/∂W = Σ_b D_b · X_bᵀ
G64 ← 0
按固定batch样本顺序：G64 ← G64 + matmul(float64(D_b), float64(X_b)ᵀ)
G32 ← float32(G64)  # 返回参数本身的float32梯度
```

这是重新计算解析梯度的累加精度，不是对原梯度或检查点截位凑相等。卷积前向、卷积输入／bias梯度、损失、分配与标签仍走原float32；SiLU按上述独立策略提高中间精度。unfold一次只展开一个样本，避免同时建立整个batch的double展开副本；这不是完整峰值内存承诺。

挂钩只属于该训练模型、该batch；验证前和异常退出路径均移除。推理／冻结卷积不重算。对非CPU float32、非zero padding或同一层无backward而重复forward明确拒绝；不复用陈旧输入。数学对照含group／stride／padding／dilation，原架构原生案例另验。

### 3.2 显式CPU AdamW

版本`cpu_adamw_fp64_intermediates_fp32_state_v2`。`CPUAdamW`继承Torch AdamW的状态／参数组格式，动量与参数存储仍为float32；计算每项动量和参数更新时使用明确分开的float64中间运算，再各自转换一次：

```text
m_t = β₁m_(t−1) + (1−β₁)g_t
v_t = β₂v_(t−1) + (1−β₂)g_t²
m̂_t = m_t/(1−β₁ᵗ)；v̂_t = v_t/(1−β₂ᵗ)
θ_t = (1−lr·wd)θ_(t−1) − lr·m̂_t/(sqrt(v̂_t)+ε)
```

乘法、加法、除法和最终减法分开执行，不使用lerp／addcmul／addcdiv的float32融合舍入路径；保持AdamW含义，但不声称与默认Torch的每个bit相同，也不是全double模型。没有梯度的参数不更新／衰减；整次更新先检查所有梯度，后面的无效梯度不能使前面的参数已经更新。当前不支持closure、稀疏、AMSGrad、maximize或capturable等非本配置策略。

剪裁仍固定参数顺序、float64范数，参数／动量本身为float32。优化器恢复张量另作原值clone，不舍入。CUDA仍为原Torch AdamW且显式关闭foreach／fused；本机CPU验收不能作为CUDA、手机或跨硬件恢复验证。

这些策略记录在`training_numerical_environment`、模型卡与恢复包中；MKL／OpenMP相关环境字段也绑定。源码／策略改变时旧包拒绝续训，不能悄悄切换数学后端。

## 4. 原生验收方式

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_pose_resume.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_pose_resume.py --multibatch
```

两次各新建TEST实验：不中断3epoch、完成epoch1后的明确取消及恢复、完成测试后恢复拒绝、epoch2首个实际优化步骤之后`os._exit(27)`及实际父回执／恢复。均要求源run无修改，最终模型／优化器／组逐位一致，恢复后的顺序、变换、loss、剪裁前后梯度digest及范数相同。

第二个案例使用5张train图、batch2、每epoch3步（末批1张）、160像素、4线程；第一案例128像素、2线程、每epoch1步。不是全部1–4线程、1–8 batch、64–640图或所有CPU的证明。原配置等待／释放、早停、权限拒绝另由`verify_pose_training.py`复验。

实际结果、失败阶段和限制见 [本机验收](../validation/REHAB_POSE_RESUME_2026-10-11.md)。TEST图只有几何／色块工程参考，无真人；PCK和覆盖0、误差null，不把原生优化／恢复通过称为准确率提高。新模型永不自动接入产品，`product_enabled=false`／`deployment_eligible=false`不变。
