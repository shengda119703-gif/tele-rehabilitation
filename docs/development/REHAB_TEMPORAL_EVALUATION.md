# 独立标注到计次、相位评价

范围：任务书10.4–10.6、13、15.2及P5／P7。只增加离线康复评价，支持已有三个协议的参考字段；不改前端、整个Android、正式计次规则、权重、剂量或患者库。当前真实标注仍为0；工具测试通过不是人体准确性证明。

## 输入到输出的职责

| 步骤 | 实际入口 | 交接内容 |
| --- | --- | --- |
| 独立参考 | `import-annotations` | 专业复核后的`rehab-reviewed-temporal-reference-1`，包含完整原队列、已批准标签、pending／excluded、来源和固定人群划分 |
| 再核验 | `temporal_evaluation.verified_reference` | 回到原bundle、回执、源文件、真实PTS、A／B及第三人复核；参考内容、表单SHA和分歧处理必须仍相符 |
| 后端预测 | `rehab-temporal-predictions-1` | 明确val／test全队列，逐样本原片SHA、协议、侧别、split与时间基础，独立计数和逐边界事件可用性 |
| 逐任务比较 | `score_sample`／`match_events` | 已知可观察计数误差；按同种边界一对一匹配；未知、缺预测和无法评价分别保留 |
| 汇总 | `aggregate`／`evaluate-annotations` | 全队列及标签／预测覆盖、每人结果、计数误差、边界召回／精确率、匹配时间误差与未支持指标 |

参考和预测是不同文件及不同来源。预测manifest的origin必须为`declared_backend_export`，声明没有用参考生成预测，并给出实现／模型／配置SHA。**这是可核对的声明，不证明实际运行、人员盲法或专业资格**。新增[原RGB实际回放](REHAB_TEMPORAL_REPLAY.md)可生成这一文件，并另存原YOLO／原协议trace与重放核对；还没有正式患者会话trace的通用适配器。不能把任意JSON结果称为已跑过真实后端。

## 预测文件契约

manifest字段：schema_version、origin、reference_used_for_predictions、implementation_sha256、model_sha256、config_sha256、samples。

每个样本字段：sample_id、video_sha256、exercise_id、side、protocol_version、split、time_basis、status、completed_count、boundary_events。

- samples必须按参考队列中的原顺序包含所选split全部样本，包括没有标签或后端失败的录像，不能只提交成功样本。
- source、协议、split和时间基础必须一致；已标样本的测试侧别必须一致。没有GT的样本不猜侧别。
- status为completed／failed／unavailable。失败或无法分析时计数为null，全部边界为null；不能填0或空列表表示成功看完。
- completed_count是独立输出的可观察完整次数，允许null。它不是身体实际执行量或达标量。
- boundary_events有准备确认、出程开始、端点开始、端点结束、回程开始、结束六个独立键。每键null表示此项预测不可用；空列表表示预测器在已分析条件下没有输出该边界。
- 事件有唯一event_id、time_s和evidence_kind；仅接受observed／filtered。predicted／reference不能作为已观察事件。
- 时间必须处于原真实PTS表中（0.0002秒解码舍入容差）、有限且有序；不接受标称FPS时间轴、推理耗时或不同来源时钟。

输出保留输入SHA和policy SHA。评估前后重新核对文件与专业参考，改变上游表单必须重新复核／导入。已有输出目录不可覆盖，失败非零；不读取“最新目录”。

## 算法与分母

### 计数

只有`observable_count_mask=true`的独立全片清点参考进入计数评价。默认count=null／mask=false不是0。

```text
signed_error = N_prediction − N_reference
overcount = max(signed_error, 0)
undercount = max(−signed_error, 0)
count_MAE = mean(abs(signed_error))，仅对有参考且预测可用的录像
prediction_coverage = 可用计数预测录像数 / 已知计数参考录像数
reference_coverage = 已知计数参考录像数 / 所选split完整原队列录像数
```

同时报告缺预测数、完整原队列数、批准参考数、待标／排除ID和每人结果。缺预测不补成0误差；MAE无可评价输入时为null，不能用0宣称完美。

### 边界匹配

默认容差0.25秒是预先声明的工程起点，不是临床标准；必须在看独立测试结果前确定，并随policy保存hash。不能反复用固定test选容差。

对每个样本的每种边界分别做有序一对一匹配：先最大化匹配数，再在匹配数相同的方案中最小化绝对时间误差之和。动态规划评分为`(匹配数, −绝对误差总和)`，使用前缀递推；不会用一个预测匹配多个参考，也不跨边界类型。相邻事件只用最近点贪心可能漏掉合法配对，TEST中同时与小规模穷举最优方案对照。

```text
TP = 匹配数
FN = 已知参考边界数 − TP（预测缺失时已知参考仍保留）
FP = 未匹配预测数，仅在该边界的参考清单完整已知时
unassessable = 未匹配预测数，若存在未标边界或没有相位参考清单
recall = TP / (TP + FN)
precision_on_assessable = TP / (TP + FP)
precision_lower_bound = TP / (TP + FP + unassessable)
time_error = prediction_time − reference_time，仅匹配事件
```

缺标的边界不作为FN或负例；不完整参考下的未匹配预测也不冒充FP。精确率必须和unassessable、保守下界及覆盖一起读，否则会因未知样本多而显得偏高。分母为0时指标为null。

时间误差报告均值绝对误差、中位绝对误差、方向偏差及线性插值p95。每位参与者单独汇总；不把同一人的数千帧当独立病例计算置信区间。此版没有受试者bootstrap置信区间，也不评价物理／可观察完成混淆、二维点、质量分类、提示效果、疾病、剂量或手机性能；这些不是已完成能力。

## 实际命令

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py evaluate-annotations --help
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_storage_recheck.py --help
```

真正评价时须提供明确的已复核reference.json、独立后端预测manifest、split和新的专用输出目录。现有24份未标包不能充当reference；`temporal-evaluation-audit-8badfb07`实际验证其在读取任何虚构预测之前被拒绝，没有生成评价结果。见[本机验收](../validation/REHAB_TEMPORAL_EVALUATION_2026-10-12.md)。

## 完整回归与存储

`verify_storage_recheck.py`保留默认subset，另增`--suite full`：完整复用`verify_all.regression_cases`的新后端、旧康复、旧手机和保护四组，不用子集代替全套。必须绑定明确原失败summary和新的外盘TEST目录，真实容量至少1GiB。运行和模型／临时测试产物只在新目录，原数据、正常库和产品默认路径不搬动；全套与子集公开报告分别保存。

新后端最多240秒、其他组150秒；通过观察超时不能启动第二个重复任务。工具保存原失败summary／日志指纹、实际容量、全部相关源文件运行前后SHA和新日志。外盘全套即使通过，`default_product_storage_restored`仍为false，不能称E盘默认上传恢复。当前没有清理用户文件或降低生产空间门。
