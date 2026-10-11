# 康复v2：显式评估、已有安排与训练绑定

日期：2026-10-11。实施基准`ab6931d`，协议`rehab-protocol-2.0`，安排政策`rehab-explicit-plan-1`。本轮只实现康复后端；产品0.20.0、独立APK0.2.1和所有界面不改，v2仍须由宿主显式启用。

## 1. 解决的问题与范围

原宿主保存计划适配只覆盖肩外展和坐站，不能把原膝屈曲或健身深蹲换名称接成康复深蹲。本增量给三项v2协议增加自己的评估和显式安排入口；左右侧分别引用证据。次数、组数、目标、休息、时间及扶手／陪同来自已明确的安排，系统不自动生成剂量，不认定临床适用。

| 动作 | 机位与主指标 | 可选质量条件 |
| --- | --- | --- |
| `shoulder_abduction` | frontal；上臂相对图像垂直的二维抬举角，主测量仅需所测肩／肘 | 显式肘屈曲／躯干倾斜限值；各自必要点独立 |
| `sit_to_stand` | sagittal；`180°−膝内角`，连续坐姿准备，站起确认，坐回重装 | 沿用时间／扶手条件；不套肩部质量限值，不冒充标准量表 |
| `rehab_squat` | sagittal；`180°−膝内角`，站姿准备，有证据转折和完整回位 | 浅幅度完整往返与目标达标分开；不套健身固定深度或肩部质量限值 |

代码：[plans.py](../../rehab_codex_single_camera_v2_1/app/rehab_v2/plans.py)、[协议](../../rehab_codex_single_camera_v2_1/app/rehab_v2/protocols.py)、[组次](../../rehab_codex_single_camera_v2_1/app/rehab_v2/rounds.py)。原53项共享目录、健身、旧计划、前端和Android保持只读。

## 2. 后端信息链

```text
认证owner＋宿主可信participant＋来源情境
 → 明确动作／侧别／view／同意／创建操作键
 → v2 assessment → 当前JPEG观测 → finish权威提交
 → assessment_reference：session／commit／视觉digest／协议digest／测量契约
 → 已明确安排＋本人动作条目＋设置
 → 当前plan＋不可变revision＋操作回执（同事务）
 → 使用时核对当前依据、revision、next_key、自评和明确确认
 → 冻结本次设置 → v2动作／组次／休息／暂停恢复
 → 最终事实＋唯一贡献 → 独立自评 → 派生报告／计划进度
```

owner是认证作用域，不是相机track；participant由宿主提供，不接受客户端自行指定另一个人。实际宿主沿用绑定档案；正式输入为LIVE_CAMERA／SELF_USE，内部回放为SYNTHETIC／TEST。知道session或plan ID不获得访问权。

评估不是训练剂量。只有同owner／participant／来源／情境／动作／侧别、已finalized、结束为completed或user_stopped、有准备基线且至少一次完整观察的评估可以引用。核对视觉digest、当前协议和带时区提交时间；7天是工程复核窗，不是临床有效期。同范围最新创建评估即使失败或未结束，也不会退回旧成功。

## 3. 接口与参数

以下路径均在显式`create_app(..., rehab_v2=True)`下注册，沿用认证、有界JSON及服务并发门控；不启动新服务作为交付步骤。

| 接口 | 责任 |
| --- | --- |
| `POST /api/rehab/v2/sessions` | assessment明确动作，training引用已保存计划；两种用途分开 |
| `POST /api/rehab/v2/plans` | 保存显式安排，返回`v2plan-` ID与revision |
| `GET /api/rehab/v2/plans?limit=20` | 本人列表，limit为1–100，包含归档计划，不混旧计划 |
| `GET /api/rehab/v2/plans/{id}` | 本人计划、进度、支持范围及继续状态 |
| `POST /api/rehab/v2/plans/{id}/revise` | 全量新安排、expected_revision及新操作键 |
| `POST /api/rehab/v2/plans/{id}/archive` | 操作键及expected_revision，追加归档版本 |

其余帧、pause、resume、finish、commit、feedback、history沿用v2会话接口。帧端只接受限额JPEG；内部关键点证据不能作为公共API提交。

### 创建评估请求

下面仅为接口字段示例，不是已执行命令或患者数据。

```json
{
  "idempotency_key": "assessment-operation",
  "consent": true,
  "submode": "assessment",
  "exercise_id": "shoulder_abduction",
  "side": "right",
  "view": "frontal"
}
```

assessment严格只接受这六个字段。finish完成后才引用其真实session_id；预览和未结束草稿不能替代评估。

### 安排字段

顶层为`idempotency_key/name/items/arrangement`；`arrangement.reference`与`confirmed=true`记录使用者声明，保存`evidence_kind=self_report`、`independently_verified=false`。不是系统认证的专业处方。每项为`exercise_id/side/assessment_session_id/settings`，1–6项，同一动作侧别不重复。

settings接受九类字段：

- 必填：`target_reps`、`target_sets`、明确布尔`needs_companion`、`use_of_hands`。
- 可选：`target_angle_deg`、`rest_between_sets_s`、`timing_plan`。
- 可选肩部质量限值：`allowed_elbow_flexion_deg`、`allowed_trunk_tilt_deg`，由原参数校验检查有限数值和0–180度范围。该范围是字段有效域，不是患者正常值。

扶手状态沿用`not_recorded/allowed/not_allowed/used_hands`；不从腕点位置推断实际受力。质量限值不配置时为null，不自动给统一标准。坐站／深蹲不支持对应肩部metric，非null限值以`unsupported_explicit_quality_constraint`拒绝。原ready／dwell／缺口等协议参数不允许借保存计划白名单覆盖。

### 启动训练与冻结

请求提供`plan_id/expected_plan_revision/entry_key/view/consent/idempotency_key/training_plan_confirmed=true`；已保存安排要求陪同时还需`companion_confirmed=true`。动作、剂量、质量和时间取当前保存条目，再冻结实际原工程默认值；客户端附加另一套剂量或限值不能覆盖保存条目。

主动作完成、个人目标达标、可观察质量和继续资格分开。肩肘可见而腕／髋缺失时可保留主计次；已配置的质量项因缺证据为UNASSESSABLE，不补成正常。现有持续超限规则可同时保留两项问题，一次只输出当前最高优先级指导。反馈缺失仍为null／missing；完成后不代填零。

## 4. 保存、重试与继续

`rehab_v2_plan_meta`单独版本1；原`user_version=4`、已有v2 meta2不改。首次扩展先用SQLite Backup API保留一致`.before-explicit-plans-<uuid>.bak`。追加以下表：

| 表 | 保存事实 |
| --- | --- |
| `rehab_v2_plans` | 当前本人计划快照与revision |
| `rehab_v2_plan_revisions` | 不可变历史版本 |
| `rehab_v2_plan_operations` | owner＋operation_key唯一回执与规范载荷digest |

同一原Storage owning thread，BEGIN IMMEDIATE事务内核对评估／版本并保存三类记录。相同键／相同载荷先返回原回执；不同载荷冲突；失败回滚三类记录。修改与归档都检查当前revision，归档后不新开训练。已开始训练保留原冻结快照，后来编辑不会回写旧视觉事实。

进度复用唯一贡献与原继续政策。只允许当前next_key；新版或新计划不能清掉同范围较新不适／疲劳／缺失自评。报告失败可重建，不增加第二份训练事实。结果仍注明`frontend_not_connected=true`、`clinical_suitability_assessed=false`，旧`/api/plan`、原历史页和APK不自动替换成新路径。

## 5. 复现与未完成项

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_backend_plans.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
```

专项使用独立TEST数据库／几何／HTTP及原YOLO空图拒绝；并非真人准确率。实际run、次数、源码／日志hash及旧失败见 [本轮验收](../validation/REHAB_BACKEND_PLANS_2026-10-11.md)。正常患者库、原权重、服务／相机和用户窗口不动。

仍需合法同域RGB与独立专业参考、真实动作误差／覆盖与指导评价、目标手机、完整负载／物理故障、后续客户端适配。此阶段完成安排绑定不等于整个任务书完成，也不自动启用任何研究候选。
