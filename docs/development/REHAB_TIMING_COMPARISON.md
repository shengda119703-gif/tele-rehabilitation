# 康复v2：逐次时间上下文与只读历史比较

日期：2026-10-11。实施基准`fc8ba23`；源码以本文件所在提交为准。只补康复后端，产品0.20.0、APK0.2.1、界面和原模型不变；v2仍默认关闭。对应任务书6.6的“比较条件与证据身份分开”及15节确定性验收，不是临床疗效评价。

## 1. 为什么角度契约不足以比较时间

出程、停留、回程和目标保持使用不同的事件边界。目标角度、时间安排、起点、输入时钟或分段算法改变，即使结果单位都是秒，也不宜直接解释为变快或保持更久。以前的角度比较没有覆盖这些条件；现在增加独立时间契约，不修改原角度契约、计次、剂量、继续政策或10字段报告。

| 时间字段 | 现有算法及本次比较对象 | 缺失时的处理 |
| --- | --- | --- |
| `outbound_s` | 肩／深蹲完整周期后的峰区分段；坐站为实际观测到的起身阶段 | 没有有效边界为null，不补零 |
| `endpoint_dwell_s` | 肩／深蹲峰区停留；坐站站位停留 | 未形成完整可观测区间不比较 |
| `return_s` | 实际回位／回坐阶段 | 坐站只站起就结束，没有回坐值 |
| `target_hold_s` | 规定目标下最长连续有效保持；坐站沿现有站位范围 | 部分观察的保持仅为已见下界，不当作完整保持时长 |

主计次、目标达标、时间达标和质量状态继续分开。坐站在站起确认时计一次，不等回坐才能保存一次；回坐只扩展尚未终结的时间草稿。

## 2. 从当前帧到历史比较的信息传递

1. 原协议引擎核对当前骨架、模型、尺寸、时钟、epoch、人物和有效关节，建立实际准备基线。
2. 每次动作开始时冻结`movement_timing.comparison_context`，不等整组结束才取最后一份基线。
3. 原时间算法继续收集当前有效观测，保留first／latest及坐站阶段的seq、source_epoch和time_s引用；缺口仍打断保持。
4. 原事务保存逐次事实、最终snapshot、canonical_commit、视觉digest和唯一计划贡献；新context随原时间字段保存，不新增历史表。
5. 比较接口在原Storage owning thread的同一次只读事务读取两份本人记录，核对终结状态和canonical视觉digest。
6. 四项时间分别核对语义契约、有效完整次、缺测和条件一致性，再输出中位数差；不回写任何测量、回执、贡献、自评或报告。

实现：[逐次冻结](../../rehab_codex_single_camera_v2_1/app/rehab_v2/engine.py)、[原时间封套](../../rehab_codex_single_camera_v2_1/app/rehab_v2/timing.py)、[比较器](../../rehab_codex_single_camera_v2_1/app/rehab_v2/timing_comparison.py)、[服务](../../mobile_rehab/rehab_v2/service.py)、[API](../../mobile_rehab/rehab_v2/api.py)。

`source_ref`是输入来源名称，`source_epoch`是会话证据世代，二者不互换。现有engine.signature首项是source_ref；新冻结函数显式接收真实source_epoch。证据seq／时间必须有限、非负且按序；跨组重新准备可有新calibration_epoch，但不能借新编号改写旧次的起点。

## 3. 固定版本、条件与身份

原算法版本保持`observed-timing-1`，原v2时间封套保持`rehab-observed-timing-2`。新增逐次上下文`rehab-timing-context-1`，只读比较输出`rehab-timing-comparison-1`，未更改算法门槛。

| 契约内容 | 比较时的作用 |
| --- | --- |
| participant、assessment／training、source_kind、usage_context | 不混人、用途或来源情境；owner认证仍是访问边界 |
| 冻结protocol全文 | 包含动作、侧别、view、指标、单位、参考和阶段定义 |
| schema、model_manifest、原像素坐标、预处理版本、frame_size、time_basis | 不将换模型、分辨率、滤波或时钟的数据直接相减 |
| 逐次baseline的raw_value／unit／reference | 起点变化保留为条件变化，不能仅删除基线字段使其可比 |
| ready_s／dwell_s／max_gap_s／max_age_ms／return_tolerance_deg／turn_delta_deg | 原六项时间相关工程参数，冻结并核对与本次计划一致 |
| target_angle_deg和五项timing_plan | 目标或时间安排变化不解释为同条件能力变化 |
| use_of_hands／needs_companion；训练次数、组数、休息 | 核对已记录安排，不声称摄像头验证了实际扶手受力或陪同情况 |
| 原时间版本、algorithm_version、method、phase_timing_mode及保持锚点 | 不混峰区分段、站位分段或不同保持定义 |

具体session／commit、source_ref、source_epoch、calibration_epoch、帧seq和实际时间另保留为证据身份，不加入语义契约digest。新录像、新job编号或重新准备的编号本身不使记录不可比；起点数值、处理方式和目标等实际条件改变仍不可比。

当前只接受`mapped_source_seconds`与`opencv_media_pts`比较；二者彼此不同。`nominal_video_seconds`虽可被原引擎读取，但不是已验证的源时钟，本比较器不会提升为实测时间。公共JPEG路径的mapped时间来自宿主单调接收时间，不是手机曝光时间或已扣除网络延迟；本功能没有补做跨设备时钟标定。

assessment未记录的陪同／扶手状态不补成正常。相同的“未知”只代表记录口径相同，不证明身体环境相同。整体输出始终`clinical_comparable=false`，不以此给疾病、疗效或身体能力结论。

## 4. 比较公式与分母

每项时间独立统计`attempts`、`complete_repetitions`、`valid_complete_repetitions`、`excluded_repetitions`、排除原因计数、有效中位数和不同条件数量。所有attempt都留在分母中；不把缺测、未完成或未知改成零。

```text
V_m = {完整次中，契约有效、该时间有效且有限非负的 d_m}
median_m = median(V_m)，若V_m为空则为null
Δ_m = median_m(右会话) − median_m(左会话)

只有两边各自条件单一、条件相同且所有完整次的该时间有效，才输出Δ_m。
不完整尝试仍展示分母和原因；不按两个独立会话的rep_index逐次配对。
target_hold另要求cycle_complete=true且partial_observation=false。
```

零秒若是有效观测值仍保留为零；bool、负值、null、NaN、Infinity或不能表示为有限时间的巨大整数都不能进入统计。数值变化仅是描述性差值，没有显著性检验，也没有“越快越好”的评分。

若一份记录有两种起点／模型／条件，返回`heterogeneous_recorded_conditions`，不先把多种条件揉成一条中位数改善结论。若有完整次缺测则为`incomplete_timing_coverage`。条件不同给`changed_fields`；旧记录缺新context给排除原因，保持原记录不补写。无足够有效时间，两侧统计及Δ保持null。

## 5. 独立API与原事实不变

仅显式`create_app(..., rehab_v2=True)`注册：

```http
POST /api/rehab/v2/timing-comparisons
Content-Type: application/json
X-Rehab-Client: mobile-v1
```

下面是请求字段示例，不是患者记录；同时需要原配对认证cookie。

```json
{"left_session_id":"owned-finalized-left","right_session_id":"owned-finalized-right"}
```

严格只接受两个不同的字符串ID，沿用128字符ID限制、有界JSON和8并发短路径门控；两次读取必须都属于认证owner。未配对为401，另一个owner的ID为404，错误载荷／相同ID为400，草稿或视觉digest不一致为409。不把错误返回当作已完成比较。

响应含四项时间的比较状态／理由／changed_fields／左右分母／中位数／条件digest／差值，以及各自session_id、commit_id和visual_snapshot_digest。固定边界为`read_only=true`、`frontend_not_connected=true`、`improvement_assessed=false`、`significance_assessed=false`、`sampling_invariance_validated=false`。读取不驱动新的推理、报告、计划或数据库迁移。

## 6. 验证与优化下一步

专项使用E盘独立TEST数据库和固定证据，另通过实际宿主认证／公共JPEG接口，几何由明确TEST provider提供；不是真人动作或相机准确性。对应18项：[测试](../../tests/rehab_backend/test_timing_comparison.py)、[专项命令](../../tools/rehab_ml/verify_timing_comparison.py)。真实run、原失败、完整旧流程回归及hash见 [本机验收](../validation/REHAB_TIMING_COMPARISON_2026-10-11.md)。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_timing_comparison.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_backend_plans.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
```

下一步应取得独立相位／事件时间参考，用同一输入做采样率、丢帧、网络接收抖动和准备姿势的敏感性实验；报告边界时间误差、有效覆盖及分层结果。手机实机、曝光时钟同步、真人计时金标准、临床最小有意义变化及完整压力仍未验证。不能靠降低完整性要求或回填旧记录来制造改善；整个后端任务书仍未全部完成。
