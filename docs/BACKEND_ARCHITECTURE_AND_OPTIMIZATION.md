# 后端功能、算法与数据流梳理

> 用途：供团队讨论准确性、可靠性和下一轮后端重构。本文不是路演宣传稿，也不是医疗操作指南。
>
> 代码基准：2026-10-11，本机 `main` / `c965ef2`；业务源码基准 `a1e7daa`，电脑端与托管手机后端 0.20.0。现有 APK 安装包仍为 0.2.1，不能把新版源码已接入理解为安装包已更新。
>
> 本轮只读代码、整理文档；未修改 UI、算法、业务规则、个人数据库或安装包。下文的“当前实现”来自源码，“已复现”来自注明日期的验收，“建议”尚未实现。

## 1. 先看结论

项目已经有三条可以串起来的业务链：

1. **动作链**：摄像头／录像 → 关键点 → 二维测量 → 动作状态与计次 → 评估汇总 → 训练建议与计划 → 训练记录、感受与进度。
2. **健康链**：手动、对话、设备适配或确认后的图片数据 → 健康事件 → 每日指标与个人基线 → 趋势／风险规则 → 管家回复、家庭摘要与通知账本。
3. **照护链**：既有药物与训练安排 → 查询或调度提议 → 明确确认 → 原业务校验与幂等写入 → 回执。

但这三条链不是一个统一数据库、一个模型或一套完全一致的跨端算法。最值得先解决的是：

- 手机与电脑的计次、起点、幅度统计、训练剂量和器械求导规则不同，同一录像可能得到不同结果。
- 几何量经常是“画面中的角度”，不是临床解剖关节角。错误的机位、参考轴和起点，会产生稳定但有偏的数值。
- 健康记录中的人物、否定、日期、来源和权限，可能比换视觉模型更直接地影响后续决策。
- 串行队列、超时后的写入、多个存储之间的非原子提交，是“界面没反应”“失败后重试重复”的重要排查方向。
- 已有回归测试证明部分规则和接口可运行；尚不能证明真人动作角度、跌倒或疾病风险的准确率。

建议阅读顺序：第 2–3 节看架构与信息如何流动，第 4–11 节查具体功能，第 12–15 节制定优化与验证方案。

## 2. 三种运行方式：代码复用，不等于能力相同

| 运行方式 | 计算在哪里 | 主要入口／服务 | 视觉与业务 | 数据归属 |
| --- | --- | --- | --- | --- |
| 电脑正式程序 | 本机 Python、Node 进程 | `Start-Rehab.ps1` → `app.main` → `ProductWindow` | Python Runtime／场景引擎；TypeScript ProductService／AgentRuntime | 康复 SQLite、日常业务 SQLite、产品 JSON 文件等 |
| 电脑托管的手机网页 | 手机采集；电脑分析与存储 | `mobile_rehab/server.py`、PhoneHost、统一网页与 `/capture` | 录像作业调用 Python；健康业务通过绑定档案调用 ProductBackend | 绑定档案的产品数据、录像作业；共享模式下读写同一康复库，但来源情境仍隔离 |
| 独立 Android APK | 手机 WebView／WASM／Java | `MainActivity.java`、本地 API 适配层 | MediaPipe CPU 模型；独立 JavaScript 动作引擎；捆绑 ProductService | 手机 JSON 状态、IndexedDB 文件、原生私有连接信息 |
| APK 的可选云端辅助 | 电脑或服务器 | `mobile_rehab/phone_cloud.py` | 私有文字备份、按类别共享家庭摘要 | 独立 `phone-cloud.sqlite3`，不打开电脑患者库 |

重要边界：

- 托管网页并不在手机上跑 Python；独立 APK 也不自动调用电脑的视觉引擎。
- 电脑演示“云端”时，托管分析服务与 APK 的备份服务仍是两种不同职责。
- 云端辅助不等于已完成跨网络视频分析、患者库同步或医生工作站。
- 共享的是一部分产品领域代码和动作目录；不能将不同引擎的结果不加条件地混合比较。
- 本轮没有验证新的相机、手环、红米实机、联网模型或公网连接；接口存在和硬件实测应分开报告。

主要代码：[Runtime](../rehab_codex_single_camera_v2_1/app/runtime.py)、[托管服务](../mobile_rehab/server.py)、[统一产品绑定](../mobile_rehab/unified.py)、[手机本地分析](../android_offline/web/motion.js)、[云端辅助](../mobile_rehab/phone_cloud.py)。

## 3. 功能之间传什么信息

### 3.1 总体数据流

```text
电脑相机／录像                    手机上传录像                   APK 本机录像
      │                               │                             │
FramePacket                     上传作业 job                    媒体时间采样
      │                               │                             │
VisionWorker / LandmarkBackend  隔离 Python 分析进程            MediaPipe WASM Worker
      │                               │                             │
PoseFrame → PoseAnalyzer         复用动作／健身／体态引擎         LocalEngine
      │                               │                             │
Observation → 场景／动作状态机         result.json                本地 job.result
      │                               │                             │
不可变 session / repetitions ──→ 历史／身体汇总／训练建议 ←──────────┘
      │                               │
计划 ID + revision + entry_key ──→ 训练执行 → 感受 → 计划进度
      │
只读康复工具／产品快照 ──────────→ 智能康复管家

对话／手动／设备／图片确认 → HealthEvent → 日指标 → 基线与 Finding
                                                   │
                                           管家／任务／家庭通知

药物原说明 + 日常安排 → CareWorkflow → 明确确认 → 业务写入 + Receipt
```

这里有两个不同的“身体汇总”：康复身体汇总记录各动作／侧别的观察；健康 PersonTwin 汇总指标趋势、主诉和个人风险背景。它们目前不是一个统一、可用于疾病诊断的生理模型。

### 3.2 关键对象与消费者

| 对象 | 关键字段 | 由谁产生 | 谁使用／为什么不能丢 |
| --- | --- | --- | --- |
| `Context` | generation、scene_id、source_ref、source_kind、usage_context、run_id、epoch | Runtime／场景控制器 | 采集、推理、控制器；阻止旧结果污染新任务 |
| `FramePacket` | seq、time_s、received_monotonic、captured_utc、image、time_basis、帧率、双摄配对 | SourceWorker | 推理、时间门控、双摄；区分媒体时间与处理耗时 |
| `PoseFrame` | people、xy、conf、track_key、size、schema_id、坐标空间、关键点顺序、模型清单、backend | 视觉后端 | PoseAnalyzer；保证不同骨架不会被当成同一种 |
| `Observation` | 指标、valid／reason、track_key、status、原始中心／bbox、time_s | PoseAnalyzer | 动作、日常活动、卧室、安全引擎 |
| `Metric` | value、valid、reason | 几何计算 | 下游不能把缺测 `null` 当成 0°或正常 |
| `session` | 档案、来源情境、配置快照、算法契约、汇总、逐次结果、条件、结束原因 | 场景控制器／分析器 | 历史、报告、自动计划、纵向比较 |
| 康复身体汇总 | exercise_id + side、最新 session、观察幅度、有效比例、状态 | assessment | 自动建议、训练参考、只读管家工具 |
| 计划／条目 | plan_id、revision、entry_key、动作、侧别、剂量、目标、证据指纹 | automatic_plans／training_plans | 上传校验、训练绑定、进度、改期 |
| 训练感受 | pain、fatigue、reason、notes、record_origin=self_report | 用户反馈 | 下一项资格、计划继续；不是视觉推断 |
| `HealthEvent` | id、type、timestamp、source、metric／value／unit 或主诉、visibility、metadata | 产品事件管道 | 持久化、每日物化、检测、管家与共享 |
| `Finding` | ruleId、severity、evidence、score、signalKeys、familyEligible | DetectionEngine | 建议和通知；score 不是患病概率 |
| `CareWorkflow`／`Receipt` | requestId、scope、期限、步骤、原事实校验、确认凭证、幂等键、提交回执 | CareCoordinator／宿主 | 确认、恢复、审计；提议不是已执行 |

视觉对象定义见 [domain.py](../rehab_codex_single_camera_v2_1/app/domain.py)，健康事件见 [events.ts](../ankang/route1-health-agent/src/pipeline/events.ts)。

### 3.3 必须继续保持的身份和语义隔离

1. `participant_id / ownerId` 表示档案；`track_key` 只是会话内的视觉跟踪，不是人脸认证。
2. `source_kind` 区分实时、录像、合成输入；`usage_context` 区分自主使用、受控演示、测试。产品侧另有 `dataMode`，不能省略映射。
3. 当前电脑版实时与手机上传录像即使属于同一人，也不能自动共用所有训练资格和历史比较条件。
4. 观测完成、幅度达标、质量可评价、训练计划完成是四个不同概念，不能只保留一个 `success`。
5. 本人自述、设备采样、视觉观测、导入资料、测试 fixture 应保留不同来源。现有 TEST 林女士数据不是算法准确度验证集。

### 3.4 两条具体链路的关联键

以一次肩外展评估接训练为例，不能只传“肩外展 80°”：

| 阶段 | 必须传到下一阶段的信息 | 关联方式 |
| --- | --- | --- |
| 选动作／输入 | participant、exercise_id、side、view、source_kind、usage_context | 创建当前 Context 与配置 |
| 逐帧测量 | time_s、模型／骨架／坐标、主指标 valid／reason、焦点 | 建立当前会话中的连续证据 |
| 保存评估 | session ID、结束时间、测量契约、范围、有效率、完整次数、条件快照 | 身体汇总按动作 + 侧别取最新证据 |
| 生成建议 | 原 session ID／指纹、participant 指纹、规则版本、筛查、剂量和目标 | 不能仅从最终范围数字重建原证据 |
| 保存计划 | plan ID、revision、条目 key、冻结评估引用 | 当前条目与后续训练一一绑定 |
| 训练／反馈 | 原计划版本／条目引用、训练 session、完成与质量字段、自评 | 计算进度、阻止跳项或不适后继续 |
| 历史／管家 | 受作用域限制的记录和计划快照 | 只读解释，不新增一次测量或训练 |

以“本人某时已服药”接逐次记录为例：原话 → 人物／时间／状态解析 → 匹配已保存 medId 与当天 time → pending workflow → 明确确认 → 再核对药物原说明与原逐次状态 → `medId|date|time` 业务事实与同事务 receipt → 页面／管家查询实际提交。任一环节存在歧义，不应通过猜药名、猜时间或猜对象补齐。

## 4. 采集、双摄、模型和测量

### 4.1 视频输入与生命周期

| 功能 | 当前实现 | 输出／下游 | 准确性或可靠性影响 |
| --- | --- | --- | --- |
| 相机枚举与记忆 | 设备 path + 显式后端定位，index 只用于本次解析；DSHOW／MSMF 不混用 | 本次输入配置 → CameraManager | 热插拔、同名相机可能改变定位，不能静默切相机 |
| 阻塞采集隔离 | VideoCapture 由所属子进程创建；结束后确认释放 | 新 FramePacket／状态消息 | 防止 read 卡住整个 UI；换源仍需完成旧生命周期 |
| 实时低延迟 | 容量 1 的最新帧槽，旧帧可被覆盖 | 最新帧 → VisionWorker | 保实时性，但高速短事件可能丢失，不能用标称帧率推导精确时长 |
| 录像分析 | OpenCV 媒体 PTS，逐帧 ack；不以推理耗时充当录像时间 | 原录像时间轴 → 状态机 | 分析慢不应改变动作速度；PTS 不单调会中止 |
| 手机 MP4 首帧兼容 | 只允许跳过最多 4 个首部、[-0.25, 0) 秒的负 PTS 帧，并记录原因 | 后续真实 PTS、跳帧证据 | 不修补录像中途断时，不伪造帧时间 |
| 上下文门控 | Context 完全匹配，seq 与 time_s 严格增加 | 当前任务有效结果 | 防止模式切换后的旧骨架／旧信号进入新会话 |
| 网络相机 | 电脑配置白名单 RTSP，FFmpeg TCP 测试／短时录制 | 录制文件 → 原上传分析链 | 没有 ONVIF 自动发现或全天连续监控 |

RTSP 当前限私有 IPv4 地址，配置最多 8 路；录制 5–60 秒，缩放不超过 1280、重采样 15 fps，时间基础标为 `ffmpeg_resampled_15fps`。这是输入兼容方案，不是原始高帧率器械分析。见 [source_worker.py](../rehab_codex_single_camera_v2_1/app/source_worker.py)、[network.py](../mobile_rehab/network.py)。

### 4.2 双摄：当前是两路二维观察

流程：两台不同设备 → 各自采集、时间门控 → 每路最多缓存 4 帧 → 选择接收时间最近的可用帧 → 独立推理／跟踪／测量 → 主视图驱动动作，辅助视图提供额外指标。

默认配对接收时间差不超过 0.12 秒，最大帧龄 3 秒；配对帧只能消费一次。两路推理在同一视觉 worker 内依次进行，第二路有独立 YOLO 模型／跟踪状态；主路可按动作选择扩展后端。

辅助指标包括正面肩线倾角、躯干相对骨盆偏斜、侧面躯干倾角。主指标可用时，辅助几何量缺测不应被当成整次动作无效；双路取流错误和几何缺测是不同层级的问题。

未实现：曝光硬同步、内外参标定、极线匹配、跨镜头身份认证、三角化三维重建。因此不能拼接两路像素坐标计算一个“三维关节角”，也不能把接收时间差称为曝光时间差。

优化顺序：先量化帧时差与双视图有效覆盖，再处理跨视图身份和外参。只有明确需求和校准数据后才做三维；不是先换成一个“融合模型”。见 [dual_camera.py](../rehab_codex_single_camera_v2_1/app/dual_camera.py)、[dual_view.py](../rehab_codex_single_camera_v2_1/app/dual_view.py)。

### 4.3 关键点模型与后端差异

| 后端 | 当前方法 | 可提供的点 | 边界 |
| --- | --- | --- | --- |
| 电脑 YOLO | 本地 YOLO11n-pose，imgsz 640，检测阈值 0.35，ByteTrack；下游常用置信度门槛 0.5 | COCO17：鼻、眼、耳、肩、肘、腕、髋、膝、踝 | 没有手指、足跟、足尖、ASIS／PSIS、C7 等解剖标志 |
| 电脑扩展 MediaPipe | 独立 `.venv-landmarks` 进程；Pose／Hands／组合腕部后端；握手、模型 SHA256 与骨架契约校验 | Pose33、Hand21；腕组合骨架 | 需已准备的独立环境与权重；桌面扩展会话连续性为时空近邻，不是实名身份 |
| APK MediaPipe | 本地 WASM CPU，VIDEO 模式，Pose33 单人、Hand21 单手；SIMD 失败可切无 SIMD | 身体、足部、手指 | 不使用电脑 ByteTrack；只处理模型选中的单目标，需避免参与者替换 |

模型清单和 SHA256 校验主要防止加载错模型／错骨架，并不能证明模型在老人、助行器、遮挡和异常姿势下准确。电脑扩展后端目前标注 IMAGE 检测模式，与 APK 的 VIDEO 时序模式也不同。

主要代码：[vision.py](../rehab_codex_single_camera_v2_1/app/vision.py)、[landmark_backend.py](../rehab_codex_single_camera_v2_1/app/landmark_backend.py)、[APK worker](../android_offline/web/worker.js)。

### 4.4 人物选择、去噪与有效性

电脑康复 PoseAnalyzer 当前：优先已有轨迹；否则近邻延续；初次选最大 bbox 面积，中心距离作平局条件。焦点变化会重新建立测量基线。旁人入镜可以忽略，不等于识别出了“正确患者”。

关键点依次检查：骨架／坐标／顺序 → 有限值 → 画内与置信度 → 跳变 → 平滑 → 每个指标必要点 → 几何长度。默认单点跳变超过画面对角线的 0.35 会无效；部分手部测量需连续稳定约 0.15 秒。

电脑坐标采用因果指数平滑：

```text
Δt = 当前有效时间 - 上次有效时间
α = 1 - exp(-Δt / τ)，默认 τ = 0.12 s
p̂_t = α · p_t + (1-α) · p̂_(t-1)
```

超过连续性间隔或焦点改变时重置；不跨缺测区间补点。原始髋中心在相应场景中仍保留，不全都使用平滑坐标。

优化重点：固定与自适应平滑的抖动／滞后对比、分辨率归一化的最小骨段长度、左右点置信度、旁人抢占率、非平面运动标记。阈值 0.5 或一条稳定曲线都不是角度误差的保证。

见 [quality.py](../rehab_codex_single_camera_v2_1/app/quality.py)。

### 4.5 现有几何公式与参考轴

通用三点夹角，关节 B、两端 A/C：

```text
u = A - B，v = C - B
φ = acos(clamp((u·v)/(|u||v|), -1, 1)) × 180/π
有符号相对角 = atan2(u_x v_y - u_y v_x, u·v) × 180/π
方向性动作幅度 = sign × wrap(raw_angle - baseline_angle)
wrap 将差值映射到 [-180°, 180°]
```

| 指标 | 实际参考 | 不能误解成什么 |
| --- | --- | --- |
| 肘／膝康复屈曲 | `180° - 三点内角` | 与健身模块直接使用内角的数值方向不同 |
| 肩外展／前屈抬举 | 上臂相对固定画面竖直轴；具体方向按动作契约 | 不是肩胛参与已扣除的盂肱关节角，也不需要统一强加髋点 |
| 肩后伸／内收回落 | 有符号画面参考与当前舒适起点，按契约观察方向 | 内收回落不是肩水平内收或完整临床内收检查 |
| 髋外展／内收 | 双髋建立骨盆轴／法线，所测大腿投影 | 不是髋旋转；骨盆出平面会改变结果 |
| 髋前屈／后伸 | 所测侧肩—髋与髋—膝相对角 | 躯干与骨盆运动可能混入 |
| 头颈侧屈 | 双眼连线相对双肩连线 | 头颈整体投影，不是某节颈椎活动度 |
| 头颈前屈／后伸 | 同侧耳—眼连线相对画面水平轴，扣舒适起点 | 不要求髋；机位改变、转头、眼耳遮挡仍影响结果 |
| 躯干侧屈 | 肩髋中线相对骨盆参考轴；有起点处理 | 不是单独腰椎角；会混入整体代偿 |
| 躯干前屈／后伸 | 所测侧髋—肩相对画面竖直，扣起点 | 不是逐节脊柱角，也不是骨盆前倾测量 |
| 腕屈伸／偏移 | 前臂与手部参考线，身体腕与手腕做空间匹配 | 不测腕旋转、关节稳定性；短线与遮挡误差大 |
| 踝背屈／跖屈 | 膝、足跟、足尖方向 | 不测内翻／外翻、足弓与距下关节 |
| 手指屈伸 | 对应三个手部关键点；非拇指 MCP 的近端参考含腕点 | 模型点不是触诊到的骨性关节中心，MCP 近似尤其明显 |

电脑方向性指标当前由首次有效原始值建立基线，首次约 5°偏移确定方向符号。错的初始姿势或第一段运动会污染后续，但输出仍可能很平稳。这是应优先验证的误差来源。

见 [geometry.py](../rehab_codex_single_camera_v2_1/app/geometry.py)、[axial_geometry.py](../rehab_codex_single_camera_v2_1/app/axial_geometry.py)、[动作契约](../rehab_codex_single_camera_v2_1/app/exercises.py)。

## 5. 康复：评估、计划、执行和历史

### 5.1 动作目录及实际覆盖

当前目录 53 项：25 项非手指动作 + 28 项手指动作。左右各一项记录槽位形成 106 个槽位，不是 106 种独立动作。

| 分类 | 动作 | 项数 | 当前模型／性质 |
| --- | --- | --- | --- |
| 肩 | 外展、前屈、后伸、内收回落 | 4 | YOLO；二维整体参考 |
| 肘 | 屈曲、伸展 | 2 | YOLO |
| 膝／功能 | 坐站、膝伸展、膝屈曲 | 3 | YOLO；坐站有独立电脑状态机 |
| 髋 | 外展、内收、前屈、后伸 | 4 | YOLO |
| 腕 | 屈曲、伸展、桡偏、尺偏 | 4 | 扩展组合；实验性观察 |
| 踝 | 背屈、跖屈 | 2 | Pose33；实验性观察 |
| 头颈 | 侧屈、前屈、后伸 | 3 | YOLO；实验性整体投影 |
| 躯干 | 侧屈、前屈、后伸 | 3 | YOLO；实验性整体投影 |
| 手指 | 拇指 MCP／IP，其他四指 MCP／PIP／DIP，各屈伸 | 28 | Hand21；实验性观察 |

未覆盖的动作／标志：肩轴向旋转、水平内外收；前臂旋前旋后；髋旋转；踝内外翻；拇指 CMC／对掌和手指外展；足趾；逐节脊柱和旋转；ASIS／PSIS、C7、肩胛精细标志。当前不由视觉直接测肌力、疼痛、关节稳定性或疾病。

### 5.2 自动计次与质量判断

电脑普通动作：

```text
WAIT_READY → REST → RAISING → PEAK_OR_HOLD → LOWERING → REST
  起点确认      离开起点      已取得动作证据       返回后记完整一次
```

默认准备连续约 1 秒；离开起点差值约 10°，驻留约 0.18 秒；回到起点通常在 5°带内。使用中位数窗口记录角度证据；无效点、焦点变更和长断流会中断半次动作，不把缺测区间补成完整往返。

`completion_status` 判断往返；`target_status` 判断已确认的幅度目标；`observation_status` 和 `metric_validity` 判断证据完整性。它们都进入逐次结果，不互相替代。

电脑坐站：

```text
SEATED_READY → RISING → STANDING_REACHED → LOWERING → SEATED_READY
                             │                          │
                          站起记一次                 坐回才能重置
```

未提供显式坐／站校准时，当前实现会把首次有效姿势当作提示中的坐姿，派生站姿阈值：膝屈曲减少约 65°、髋中心向上约 0.18 个图像高度。若首帧实际上站着，会建立错误参考。该规则不是标准五次坐站或 30 秒坐站量表的完整实现。

肩部质量提示当前仅在相应动作阶段检查已设置的肘屈曲／躯干限值；超限连续约 0.5 秒才报问题，反馈有冷却。未设置限值时不能宣称全面自动纠错；没有经验证的全身质量评分模型。

代码：[rehab.py](../rehab_codex_single_camera_v2_1/app/rehab.py)、[movement_timing.py](../rehab_codex_single_camera_v2_1/app/movement_timing.py)。

### 5.3 节奏与“下一步提示”

- 逐次记录出程、端点驻留、回程；离线端点时间基于连续峰值角度带，默认约 3°。缺少连续样本、边界未观察或出现断流，时长保留缺测原因。
- 实时保持时间需要连续达到对应目标；分开的两段不能累加成一次保持。
- GuidancePolicy 用已经确认的状态生成下一步动作指令，包含 observed_phase 与 cue_key；它不是测量引擎。
- 当前呈现策略对短缺测先安静恢复；约 1.5 秒后才提示调整，后续重复提示延后；累计长缺测可提供引导计时路线。
- 引导计时、人工标注和自动观察是不同证据类型。让流程可继续，不等于缺失的角度被补测成功。

优化提示时应改状态证据／相位稳定性，不能仅把提示文字强行切到“下一步”。见 [guidance.py](../rehab_codex_single_camera_v2_1/app/guidance.py)、[guided.py](../rehab_codex_single_camera_v2_1/app/guided.py)。

### 5.4 评估汇总：选最新证据，而不是最好成绩

`assessment.py` 按当前档案、来源与使用情境筛选结束的自动评估，按动作 + 侧别取最新记录。最新失败不能悄悄回退到过去的成功记录。

输出含 ASSESSED／UNAVAILABLE／NOT_ASSESSED、记录 ID、可见幅度、有效观察比例、完整次数、问题及条件。保存的训练参考冻结当时证据；之后重新评估不会偷偷改旧训练的参考。

批量评估另维护 batch 的 revision、顺序、跳过和完成信息。该汇总不自动知道病种、疼痛或医学禁忌，也不把空白槽位补为正常。

代码：[assessment.py](../rehab_codex_single_camera_v2_1/app/assessment.py)、[assessment_batches.py](../rehab_codex_single_camera_v2_1/app/assessment_batches.py)。

### 5.5 自动建议与保存计划

当前自动建议是版本化规则 `general-activity-rules-1`，不是学习型处方模型。9 项动作关联公开基础活动材料，其他动作基于一般活动原则作个人范围适配；不能说全部 53 项都已有病种专属指南映射。

电脑版主要输入／门槛：

- 当前档案限制与基础活动筛查；站立支持、陪同等条件按适用项确认。
- 同作用域的最新评估，结束状态合格；不超过 7 天、不在未来。
- 有效观察比例至少 0.8，至少 1 个完整动作，测量契约与现版本一致。
- 近期训练的疼痛、明显疲劳或不适结束会阻止自动继续；没有替用户代填反馈。

幅度目标计算：

```text
观测范围 [low, high]
增大型指标：target = low + 0.8 × (high-low)
减小型指标：target = high - 0.8 × (high-low)
```

幅度小于约 15°、超出有效角度域或不在本人范围时不给目标；肩前屈／外展目标有 90°上限；坐站不套角度目标。最多 4 条，优先未训练项，再按坐位／站位和目录排序。默认每项 1 组，次数 `min(5, 已观察完整次数)`，休息 60 秒。

保存内容包括 rule version、participant／proposal 指纹、原评估 ID／证据指纹、目标和剂量、筛查及条目身份。开始使用时重新校验，筛查有效期约 24 小时；按原计划版本与顺序推进。计划可人工编排、修订、归档和恢复，旧记录继续绑定旧版本。

不能据此宣称自动诊断、完整个体化病种康复处方或自动加量。改进应从“专业人员确认的病种模板 + 可解释准入／剂量规则 + 反馈停止条件”开始。

代码：[automatic_plans.py](../rehab_codex_single_camera_v2_1/app/automatic_plans.py)、[training_plans.py](../rehab_codex_single_camera_v2_1/app/training_plans.py)。

### 5.6 训练执行、感受与进度

电脑版 TrainingEngine：ACTIVE／RECOVERY／RESTING／PAUSED／COMPLETE／FINISHED；组间休息、暂停不进入角度证据和计次。恢复时重置运动连续性，坐站需观察坐回再结束恢复阶段。

训练记录 → 原计划 ID／revision／entry → 是否完成组数／次数与可观察目标 → 用户疼痛、疲劳、结束原因 → 下一项资格。疼痛与疲劳是 0–10 整数自评或空值，不由摄像头生成。

一个录像 job 处于 done、做满次数、达到幅度或计划可继续，都不是同一个判定。调度改期也只修改既有安排，不启动训练、不改处方。

尤其要注意当前实现：电脑版 `plan_completed` 按组数是否完成计算，`program_progress` 的 done 主要检查这个字段、自动观察模式与结束状态，并不把所有幅度／质量类别再作为完成的硬门槛。质量另行报告，感受另行阻止继续。APK 的完成／继续逻辑又有目标、有效率和感受条件。若产品需求是“高质量完成才推进”，需要明确修改和测试这层资格规则，不能仅靠已有质量报告宣称它已做到。

代码：[training.py](../rehab_codex_single_camera_v2_1/app/training.py)。

### 5.7 历史、报告、纵向比较

输出可包括 HTML 结果摘要／报告、JSON、逐次 CSV、指标 JSONL、双摄 CSV、身体汇总和纵向图。它们从保存的快照派生；缺测显示空值与原因，导出前检查快照一致性。

当前严格比较会检查人、来源情境、动作侧别、子模式、模型／骨架、图像尺寸、机位、ROI、基线、目标／节奏、预处理和双摄条件。不同／未知条件断开曲线，不自动宣称改善。

注意：录像 job 的 source_ref 可能每次不同，基线又是每次实测值，严格签名很容易令新录像“不可比较”。这是可靠但不够好用的现有策略。建议区分“采集条件签名”和“本次测量证据签名”，逐指标规定可比较层级，而不是删除全部条件。

代码：[longitudinal.py](../rehab_codex_single_camera_v2_1/app/longitudinal.py)、[reports.py](../rehab_codex_single_camera_v2_1/app/reports.py)。

## 6. 健身、器械运动与体态

### 6.1 八种健身动作

当前由用户选择动作，不是模型自动识别动作类别。算法为关键点几何 + 专用阈值往返状态机。

| 动作 | 主指标 | 电脑 start → turn 阈值（内角 °） | 附加观察 |
| --- | --- | --- | --- |
| 深蹲 | 膝内角 | 155 → 105 | 髋、躯干、髋膝相对高度 |
| 硬拉 | 髋内角 | 115 → 155 | 膝、躯干 |
| 卧推 | 肘内角 | 150 → 105 | 上臂方向 |
| 划船 | 肘内角 | 150 → 85 | 躯干变化 |
| 过顶推举 | 肘内角 | 100 → 155 | 上臂、躯干 |
| 弯举 | 肘内角 | 150 → 75 | 上臂摆动 |
| 俯卧撑 | 肘内角 | 150 → 100 | 肩—髋—踝身体线 |
| 分腿蹲 | 膝内角 | 150 → 110 | 髋、躯干 |

电脑健身角度 EMA 默认 τ=0.1 秒，缺口上限约 0.3 秒，返回驻留约 0.18 秒。归一化进度：

```text
p = (angle - start_angle) / (turn_angle - start_angle)
p ≤ 0：返回带；p > 0.08：开始离开；p ≥ 1：到达转折目标
转折目标有连续证据，随后回到返回带 → 完整一次
未到达转折即返回 → 部分动作，不等同完整
```

结果包括角度覆盖、幅度、起点／转折／回位关键帧、出程／回程时间、平均角速度和节奏变异。三次以上节奏 CV 为持续时间总体标准差除以均值。划船躯干变化约 15°、弯举上臂变化约 20°有规则提示，但不等于完整的健身技术评分或肌肉激活分析。

APK 深蹲在膝数据少于一半、髋数据至少 80% 时，可改用实际观察到的髋往返，记录 `observed-hip-no-knee`；不能据此报告膝角或膝部深度。

代码：[fitness.py](../mobile_rehab/fitness.py)、[fitness_analyzer.py](../mobile_rehab/fitness_analyzer.py)、[APK fitnessResult](../android_offline/web/motion.js)。

### 6.2 杠铃速度、外力与功率

电脑链路：用户标定参考线与跟踪点 → 图像模板跟踪 → 像素转米 → 局部拟合求导 → 自由重量外力／功率 → 连续上升段逐次汇总。

```text
s = 参考真实长度 L / 参考像素长度 d_px       （m/pixel）
h(t) = [y(0) - y(t)] × s                    （向上为正）
局部拟合 h(t_i+τ) ≈ aτ² + bτ + c
v(t_i) = b，a_vertical(t_i) = 2a
F(t) = m × [g + a_vertical(t)]，g = 9.80665 m/s²
P(t) = F(t) × v(t)
平均上升速度 = Δh / Δt
末次相对最佳速度损失 = 100 × [1 - v_mean,last / v_mean,best]
```

电脑版限制／有效性：

- 参考点间距至少 30 像素，真实长度 0.05–3 米；已知质量可为空，有值时须在有效范围。
- 固定相机、近似同平面、自由重量等条件需确认。把质量填成 20 kg 不能替代空间标定。
- 灰度模板 NCC 至少 0.7，另有歧义检查；低分、时间缺口 >0.15 秒或尺寸变化会停止轨迹，不猜测重接。
- 局部时间窗 ±0.18 秒，至少 7 个样本，边界不算。加速度还要求局部约 20 Hz 及残差 RMSE≤0.01 米；因此速度可用并不代表加速度／力／功率可用。
- 上升段 v>0.05 m/s，至少 4 个样本、持续≥0.2 秒、位移≥0.04 米；边界未观察的段不能充当完整逐次表现。

APK 不是该实现的直译：固定窗口模板搜索，NCC≥0.75；断跟后可尝试后续帧；选最长连续轨迹，五点中位数平滑，再对位置与速度分别做局部线性回归求导。没有电脑版同样的 20 Hz／二次拟合残差准入条件，输出契约为 `android-free-weight-2d-1`。

APK 录像初始抽样间隔 0.12 秒（约 8.3 Hz），CPU 慢时可增为 0.18／0.24 秒；这会平滑快速峰值并放大导数可信度问题。不能把“手机能输出功率字段”理解为通过了电脑版精度门槛。电脑 RTSP 录制 15 fps 也与上述加速度门槛不匹配。

当前 F 是所跟踪自由重量的竖直外力，P 是对应平面运动功率；不是肌肉真实发力、人体总爆发力、关节力矩或肌电。优化时优先用已知轨迹、已知标尺和参考速度设备验证；必要时给器械单独保留高频追踪，姿态可以继续低频。

代码：[Python barbell](../mobile_rehab/barbell.py)、[APK barbell](../android_offline/web/barbell.js)、[APK 汇总](../android_offline/web/motion.js)。

### 6.3 正面／侧面体态

电脑体态：选定人物 → 有效点 → 连续片段 → 各指标中位数／MAD／覆盖率。每指标需至少 10 点、持续至少 2 秒；间隔 >0.5 秒分段，不把不同人的片段合并。

| 视图 | 当前输出 | 方法 |
| --- | --- | --- |
| 正面 | 肩线倾角、髋线倾角 | `atan2(abs(Δy), abs(Δx))`，相对画面水平 |
| 正面 | 躯干偏离竖直 | 肩中点—髋中点方向 |
| 侧面 | 耳肩水平偏移百分比 | `100 × abs(耳_x-肩_x) / 肩髋长度` |
| 侧面 | 躯干倾角、膝内角 | 线方向与三点角度 |

耳肩偏移为绝对值，没有可靠区分前后方向；膝内角没有独立过伸诊断。缺少 ASIS／PSIS 就没有真实骨盆前倾角，缺少 C7 也不是标准耳—C7 颅椎角。

当前没有人体围度／体脂率、逐节脊柱形态、肌少症或骨质疏松预测。长期变化可以作为未来研究输入，但必须另做参考测量与结局验证，不可从现有二维体态字段直接生成疾病结论。

代码：[posture.py](../mobile_rehab/posture.py)、[posture_analyzer.py](../mobile_rehab/posture_analyzer.py)。

## 7. 日常活动、卧室、安全和银龄支持

这些是电脑 Python 的独立场景能力，不代表 APK 已有同样的全天监控。Runtime 当前一次运行一个主要场景，也不是把康复、步态、睡眠和跌倒同时并行计算。

| 功能 | 输入与当前规则 | 输出与消费者 | 关键边界 |
| --- | --- | --- | --- |
| 坐姿／站姿／移动 | 髋中心、膝屈曲、躯干倾角、场景 ROI | 状态与连续有效活动区间 → 会话／报告 | 缺人／遮挡不计活动时长 |
| 行走观察 | 约 2.5 秒内水平移动，站姿条件，左右踝相对变化至少两次交替 | WALKING 或 VISIBLE_MOVING | 是规则状态，不输出可靠的米／秒步速、步长、步态疾病分类 |
| 久坐提醒与活动任务 | 连续有效坐姿，默认久坐阈值 2700 秒；显式目标 | OFFERED／ACCEPTED／ACTIVE／COMPLETED 等任务 | 用户自报完成与视觉验证分开，非自动医疗剂量 |
| 卧室状态／离床观察 | bed／bed_edge／exit ROI，倾角、膝、髋位置；先站起再到出口 | 床内可见、床沿坐、站起、离床事件 | 无人不等于离床；被子遮挡不能推断睡眠／夜尿 |
| 安全疑似低位事件 | 髋中心相对初始躯干尺度的下降速度、躯干倾角／bbox、floor ROI | OPEN → ACK → RESOLVED 事件 | 不是经训练验证的跌倒预测器 |
| 银龄支持与变化卡 | 固定条件下的历史变化、授权、反馈、支持请求 | 独立 SilverStore，人工回应与审计 | 不另开相机；可选队列不应干扰核心测量 |

安全引擎默认下降速度阈值约 0.35 个基准躯干长度／秒；低位倾角≥60°或 bbox 横宽比>1.2，连续约 2 秒建立事件，床／椅／沙发排除区不能混为地面。恢复正常连续约 2 秒解除重复触发锁，但不自动解决原警报；停止流也不替人 ACK。

优化应统计每小时误报、真事件漏报、不同场景覆盖和报警延迟；仅以“某录像触发了 OPEN”验收不足。被动连续监测还需后台生命周期、长期功耗、隐私、设备离线和响应闭环。

代码：[activity.py](../rehab_codex_single_camera_v2_1/app/activity.py)、[bedroom.py](../rehab_codex_single_camera_v2_1/app/bedroom.py)、[safety.py](../rehab_codex_single_camera_v2_1/app/safety.py)、[silver_service.py](../rehab_codex_single_camera_v2_1/app/silver_service.py)、[change_cards.py](../rehab_codex_single_camera_v2_1/app/change_cards.py)。

## 8. 健康事件、个人基线与趋势检测

### 8.1 指标进入系统的入口

当前 10 类：步数、步行速度、睡眠时长、夜间醒来次数、静息心率、体重、血氧、收缩压、舒张压、血糖。它们可以由不同输入路径进入，但摄像头并未自动产出全部指标。

```text
手动数值 ──────────────┐
本人对话中的可接受事实 ─┤
设备／HealthKit 适配 ───┼→ 有限值／单位／时间／来源校验 → HealthEvent
确认后的图片候选值 ────┤                                 │
合法的资料／数据导入 ───┘                                 ↓
                                        去重、持久化、按日物化
                                                         ↓
                                        基线／Finding／PersonTwin
```

HealthKit 适配器有用户匹配、授权状态、样本新鲜度、单位、时间、source 和 confidence 校验；这不等于红米 APK 已有各品牌手环 Bluetooth 驱动。`device.import/pull` 也需对应真实适配器配置。不同来源的值目前可能进入同一趋势序列，建议保留设备与采样条件分层。

### 8.2 去重、每日取值与时间问题

健康事件按稳定 ID 去重；对话同日同事实还有语义去重。原读数保留，每日同指标通常取最新时间戳值，不是平均值。

日期型主诉物化时会生成当日 `12:00:00` 时间；这只是兼容日期的表示，不能当作实际发病／讲话时间。部分日期归组使用 ISO 字符串日期片段，宿主“今天”使用当地时区，两者需要专门验证跨午夜、UTC 偏移与历史输入。

对血压还应保留同次收缩压／舒张压的配对身份；不宜将当天两个不同测次的极值描述为一组真实读数。

代码：[normalize.ts](../ankang/route1-health-agent/src/data/normalize.ts)、[events.ts](../ankang/route1-health-agent/src/pipeline/events.ts)、[HealthKitDeviceAdapter.ts](../ankang/route1-health-agent/src/adapters/HealthKitDeviceAdapter.ts)。

### 8.3 当前个人基线公式

当前检测配置：个人基线窗口默认 14 天，排除最近 3 天；至少 5 个有效日点。近期默认 3 天，检测至少需要 2 个日点。

```text
μ_base = Σx_i / N
σ_base = sqrt[Σ(x_i-μ_base)² / N]             （总体标准差）
μ_recent = 近期有效日值均值
bad_delta = d × (μ_recent-μ_base)
bad_ratio = bad_delta / |μ_base|
z_bad = bad_delta / max(σ_base, metric_min_sd)
d：该指标预设的不利变化方向，升高不利为 +1，降低不利为 -1
```

零基线、有效点不足时不生成相应变化信号。最小标准差是防止稳定序列的微小差异产生巨大 z 值的工程参数，例如步数 250、步速 0.05、心率 3；不是人群医学正常范围。

当前均值／标准差易受离群值和设备来源切换影响；不同人的稳定基线也未必健康。应分别处理“个体变化”和“绝对安全阈值”，不要只看 z 值。

### 8.4 DetectionEngine 和 PersonTwin

| 模块 | 当前逻辑 | 输出／信息传递 |
| --- | --- | --- |
| 指标变化规则 | 步数、步速、睡眠、心率、血氧、血糖的方向性变化比例 | Finding 的证据、严重度、分数 |
| 情境规则 | 夜醒较基线增加、短期体重上升与水肿、疲劳主诉 | 建议与可授权的家庭信息 |
| 多信号融合 | 活动、症状、体重／睡眠、生命指标四类，每类最多记一项；达到 3 类升为 alert | 类别计分，不是概率模型 |
| 安全规则 | 当日血压、血氧、心率、血糖极端值；胸痛／神经症状／本人已发生跌倒等 | 优先级较高的提醒／照护路径 |
| 去重与排序 | 同 Finding ID 取较强证据，urgent → alert → watch → info | 管家先处理高优先级 |
| PersonTwin | 步数、步速、睡眠、夜醒的基线／近期趋势，个人行动风险背景、主诉与 Finding | 可解释摘要，不是人体数字孪生仿真 |

PersonTwin 当前趋势变化比例约 ±15%，而检测的指标阈值不同；PersonTwin 对近期覆盖的门槛也并非与 Detection 完全一致。应统一“多少数据足以说趋势变化”的口径。

安全规则内确有血压、血氧、心率、血糖常量，但这些是当前代码触发条件，不是已经经过本项目临床验证的阈值。优化需要审查适用人群、量测可靠性、测次配对、症状状态和动作；本文不据此给出个人治疗建议。

还需验证：情境／融合读取 `hadTag`，与安全读取 `hadOccurredObservation` 的状态过滤不同。否定、假设或不确定主诉是否会进入某些提醒，需要针对性测试；这里列为代码审查候选，不宣称已复现所有误报。

代码：[baseline.ts](../ankang/route1-health-agent/src/engine/baseline.ts)、[detect.ts](../ankang/route1-health-agent/src/engine/detect.ts)、[signals.ts](../ankang/route1-health-agent/src/engine/detection/signals.ts)、[fusion.ts](../ankang/route1-health-agent/src/engine/detection/fusion.ts)、[safety.ts](../ankang/route1-health-agent/src/engine/detection/safety.ts)、[personTwin.ts](../ankang/route1-health-agent/src/engine/personTwin.ts)。

## 9. 智能康复管家、语音、图片和资料

### 9.1 产品服务与管家链路

ProductService 统一档案、健康记录、检测、对话、药物、任务、家庭、资料、通知和扩展接口。桌面／托管网页经 Python ProductBackend 调用 Node JSON 行协议；每次请求与工具调用绑定 session 和当前档案，不让浏览器任意指定其他患者。

管家处理大致链路：

```text
文字／语音草稿
 → 人物 + 时间 + 已发生／否定／假设／不确定 + 更正／隐私理解
 → 接受的本人事实／单独处理的家庭事实
 → HealthEvent 与原事实更正
 → 基线、Finding、任务、授权状态重算
 → 本地规则回复，或允许情况下调用配置的语言模型
 → 保存回执、当前快照、受权限限制的家庭输出
```

`understanding.ts` 与 `elderTurn.ts` 有主语、指代、否定、时间和更正逻辑；不是只抽关键词。可选 LLM 理解有结构校验、限时与隐私条件；没有模型配置时仍有本地规则路径。LLM 不应直接写测量值、处方或替用户确认。

康复信息通过只读工具 `rehab.get_training_plan`、`rehab.get_recent_assessments`、`rehab.get_training_history` 进入管家；宿主约束 owner、来源情境，只允许动作／关节过滤。空结果不能让模型补造历史，也不因工具查询生成新的 HealthEvent。

APK 的本地 ProductService 配置并未提供与电脑相同的全部可选端口；展示本地康复快照，不等于已接通电脑联网模型的所有工具路径。

代码：[ProductService.ts](../ankang/route1-health-agent/src/product/ProductService.ts)、[elderTurn.ts](../ankang/route1-health-agent/src/engine/elderTurn.ts)、[understanding.ts](../ankang/route1-health-agent/src/engine/understanding.ts)、[llmUnderstanding.ts](../ankang/route1-health-agent/src/engine/llmUnderstanding.ts)、[rehab_read_tools.py](../rehab_codex_single_camera_v2_1/app/rehab_read_tools.py)。

### 9.2 语音

| 路径 | 当前实现 | 下游／边界 |
| --- | --- | --- |
| 电脑／托管语音 | 本地 faster-whisper，模型资源显式准备；手机 worker 用 base、CPU int8、中文、VAD | 转写草稿，不直接当已确认健康事实；错误仍由理解层处理 |
| 手机网页录音 | 有大小／时长／进程时限；只在授权采集后上传 | 电脑处理，不是网页自带离线 ASR |
| APK 语音 | Android 31+ 且设备有 on-device recognition 服务才启用本地识别 | 不具备时保留文字／键盘；不是所有 Android 都能离线识别 |
| 播报／取消 | 通过已配置 voice port；宿主取消、生命周期和旧请求隔离 | 有接口不等于 APK 已捆绑全部原生播报能力 |

优化应测“转写错误造成的语义动作错误”，不只测字错率；数字、药名、人名、上午／下午尤其需要确认草稿。见 [native_voice.py](../rehab_codex_single_camera_v2_1/app/product/native_voice.py)、[voice_worker.py](../mobile_rehab/voice_worker.py)。

### 9.3 OCR、健康图片与资料存档

本地 OCR 和结构化健康图片解析是两条不同路径：

```text
图像 → RapidOCR / APK Tesseract → 文字草稿（不自动入健康库）

图像 + 明确同意 + 已配置视觉服务
 → RealImageHealthParser / HttpVisionProvider
 → 待确认指标候选 → 用户确认／修改
 → HealthEvent（保留原候选及复核元数据）
```

电脑 OCR 为本地 ONNX，限制图像像素、尺寸、行数与置信度；显式禁止自动网络下载。APK 有本地 Tesseract 资源。结构化解析服务是可选配置，不应把 OCR 得到一串字符直接视为准确的血压／检验指标。

资料可导入图片、PDF、文本等，按 owner／dataMode 存原件与元信息、回收站、恢复和导出。视频存档不等于管家能直接理解医学视频；动作录像应走动作分析 job。

代码：[ocr_worker.py](../mobile_rehab/ocr_worker.py)、[APK ocr.js](../android_offline/web/ocr.js)、[RealImageHealthParser.ts](../ankang/route1-health-agent/src/adapters/RealImageHealthParser.ts)、[ArchiveService.ts](../ankang/route1-health-agent/src/archive/ArchiveService.ts)。

## 10. 用药、调度、家庭和云端

### 10.1 用药和日常安排

- 药物保存名称、原说明与状态；逐次记录用 `medId|date|time` 定位 taken／skipped／unrecorded。
- “未记录”不等于漏服；“已服用”来自用户记录，不是摄像头证明吞服。
- 训练安排引用既有计划及 revision；安排时间和训练是否完成分开保存。
- 管家可查询原用药／安排，不能决定处方、剂量、加药或给药。
- 原日常任务可记录、反馈和恢复；紧急联系人接口提供联系信息，不自动拨打急救或完成救援。

代码：[daily_store.py](../rehab_codex_single_camera_v2_1/app/product/daily_store.py)、[medicationCare.ts](../ankang/route1-health-agent/src/engine/medicationCare.ts)。

### 10.2 新照护调度：明确确认与幂等

```text
care.overview / care.next：读取本人原事实，不改业务

care.prepare
 → 读药物、逐次状态、训练安排和计划版本
 → 解析或接收明确意图
 → 生成 awaiting_confirmation / needs_clarification 提议
 → 不写服药或改期事实

care.confirm（正确 workflow + token + confirmed:true）
 → owner / 来源 / 情境 / 15分钟期限核对
 → 重新读取原事实，校验 expected evidence
 → 按步骤执行允许的原业务操作
 → 同事务保存业务变化与幂等 receipt
 → 完整／部分成功／失败，重复确认可找回既有回执
```

当前支持指定服药记录、既有训练改期；工作流最多 4 步，注册表有 200 个工作流／1000 个回执上限。部分步骤已成功后，不假装全失败并重做成功步骤；也不回滚已经成立的业务事实。

宿主 DailyStore 使用 `BEGIN IMMEDIATE`，业务写入和回执原子保存。可执行提议含确认凭证、期望事实和签名；状态查询／导出会限制这些敏感执行字段。

**未接通**：正式前端确认卡片仍待接入，单发“确认”不执行。这不是仅靠调度算法存在就能完成的用户链路。

**已复现语义缺陷**：2026-10-10／11 黑箱中，具名第三人或朋友的改期被绑定本人；“上午16:00”未澄清；“中午四点”变成 04:00；“已服用两倍剂量”缩成按原说明的普通服药记录。需修人物、时间与剂量理解，不能由幂等事务补救错误意图。

代码：[CareCoordinator.ts](../ankang/route1-health-agent/src/care/CareCoordinator.ts)、[care_host.py](../rehab_codex_single_camera_v2_1/app/product/care_host.py)；证据见 [独立黑箱报告](validation/ANKANG_CARE_BLACKBOX_2026-10-10.md)。

### 10.3 家庭关系、摘要、共享与通知

| 功能 | 当前方法／传递内容 | 尚不能混为一谈 |
| --- | --- | --- |
| 本地家庭 | 邀请、绑定、分类授权／撤销，按类别投影可见记录 | 本地关系不代表外部账号或异地送达 |
| 家庭摘要 | 只读获准的健康／康复／用药近况；不暴露其他人的整个快照 | 摘要不是原始患者数据库复制 |
| 旧网页照护分享 | 限定范围的分享 token、读取／备注、撤销 | 与统一家庭状态、APK 云端关系不是同一个存储 |
| 通知 | Finding → 权限校验 → 通知账本 → 渠道投递／回执 | pending、accepted、sent、delivered、failed、unavailable 必须区分 |
| 跨设备适配／同步 | PeerJS 等可选端口、owner／relationship 校验、受限摘要／同意信息 | 有协议代码不代表公网可用或完成全量原事件同步 |
| APK 辅助云端 | Bearer token、设备注册、15 分钟家庭邀请码、health／rehab／medication 授权摘要 | 不自动合并电脑库，不运行全部手机视觉分析 |
| 文字备份 | 版本 2、digest、revision 冲突检查、相同内容幂等 | 不包含录像／资料原件，不等于完整系统镜像 |

通知账本用于追踪状态、去重和恢复；只有真正返回送达证据才可算 delivered。没有外部渠道时不能把本地提示写成家属已收到。语音／视频通话、家属实时喊话、运营级报警中心并未形成当前完整接通能力。

代码：[NotificationService.ts](../ankang/route1-health-agent/src/notification/NotificationService.ts)、[sync/protocol.ts](../ankang/route1-health-agent/src/sync/protocol.ts)、[care.py](../mobile_rehab/care.py)、[phone_cloud.py](../mobile_rehab/phone_cloud.py)。

## 11. 持久化、进程、超时和安全

### 11.1 数据到底保存在哪

| 存储 | 主要内容 | 可靠性机制／边界 |
| --- | --- | --- |
| `home_rehab.sqlite3`，schema 4 | sessions、config_snapshots、repetitions、activity_intervals、tasks、events、scene_profiles、devices、audit、participants、assessment_batches、training_plans | 每个 Storage 实例单写入线程；事务、版本校验、已知迁移前备份；多个进程仍需 SQLite 锁协调 |
| `product_daily.sqlite3` | 日常 data、audit、care_receipts | owner 隔离、显式事务与幂等；并非全部产品事实库 |
| `product/profiles` 与 `product/records` JSON | 档案、健康事件、产品状态、资料、关系、通知、调度注册表等 | key 哈希文件名，信封版本／key 检查，临时文件替换、旧 `.bak`，短暂 Windows 占用重试 |
| `silver_support.sqlite3` | 银龄授权、请求、反馈与审计 | scope + kind + id、revision；不自动并入主健康事件 |
| 手机托管 jobs 目录 | 上传文件、任务状态、progress、result／error JSON | 限额、状态恢复、子进程；和康复 SQLite 不在同一事务 |
| APK JSON 状态／IndexedDB | 档案、健康与业务状态、jobs／plans；录像与资料文件 | 本地持久化、失败提示、备份／恢复；两种存储之间不是单个 SQL 事务 |
| APK 原生私有配置 | 云端地址、设备凭证等 | 不向普通页面任意暴露原生连接能力 |
| `phone-cloud.sqlite3` | devices、invites、links、backups | token 哈希、owner 隔离、类别权限、备份 digest／revision |

RawFrame 不保存为康复会话数据；姿态保存受同意控制。用户同意保留的手机录像文件与去标识会话导出是另一种数据，不要混称“所有数据都匿名”。

JSON 原子替换可降低半写文件风险，但没有跨文件事务，也不是加密或全球多写者互斥。SQLite 的“一个实例单写入”不等于“整个系统只有一个写入进程”。

产品 `lifecycle.clear` 清理指定产品健康／任务／关系／通知等范围，不应宣称抹掉全部患者数据：原档案／药物及权威康复库等存在不同清理边界。导出与清除应明确清单、来源、文件和备份留存。

代码：[storage.py](../rehab_codex_single_camera_v2_1/app/storage.py)、[product-local-store.cjs](../ankang/route1-health-agent/scripts/product-local-store.cjs)、[APK store.js](../android_offline/web/store.js)、[backup.py](../mobile_rehab/backup.py)。

### 11.2 进程与任务可靠性

| 环节 | 当前调度／限制 | 风险与应测内容 |
| --- | --- | --- |
| Python 实时 Runtime | 相机子进程、视觉 worker、当前场景门控、可选任务队列 | 输入断流／推理错误／保存失败有不同恢复边界 |
| ProductBackend | 一个 worker 串行处理；jobs／results 是无界 Queue | 慢模型／语音可挡住其他产品请求，积压缺少全局上限 |
| Python → Node bridge | UTF-8 JSON 行，请求与 tool_result 配对；session 校验；Node 请求串行 | 本身依赖上层串行使用，不能随意并发复用同一 stdout |
| 产品超时 | ProductBackend 默认 165 秒，bridge 150 秒 | 尚未开始的取消可跳过；已经开始的写入不一定被 HTTP 超时取消 |
| 康复 Storage | 写入线程、future 等待与 SQLite busy_timeout | 超时不是可靠的“未写入”证明，重试前应查提交状态 |
| 托管统一产品请求 | 有界并发入口，绑定档案／会话撤销 | 入口限流不等于底层队列完全有界 |
| 录像 job | 一个分析 executor；每人一个活动任务，全局最多三个；分析子进程时限 600 秒 | 崩溃后活动任务标失败；保存成功但 result 未成可能需要对账 |
| 上传约束 | 单文件 256 MB、总量 2 GB、剩余空间检查；分析录像时长约 120 秒 | 内容长度、格式、解码、尺寸、资源限额不能只由 UI 保证 |
| APK 本地分析 | 一个活动分析，worker init／frame 超时，生命周期暂停释放 | 降采样、熄屏／后台、内存与存储不足需真实设备验收 |

建议为每条请求贯穿 `trace_id + owner + job/session/request_id + algorithm_contract`；记录排队时间、解码、推理、规则处理、持久化、总延迟和取消状态。正常日志不要存原始健康对话或凭证。

### 11.3 当前安全机制与未覆盖部分

- 托管网页有连接码／签名 cookie、HttpOnly／SameSite、请求头约束、部分限流、CSP 与禁止缓存；绑定后不能随意改 owner。
- APK 特权 API 只给可信 appassets 本地 origin；外部／file／content 导航受限，SSL 错误不放行，原生云端路径与 URL 受限。
- 云端辅助做 Bearer token 哈希、请求大小、设备归属、授权类别和备份 revision 检查。
- 这些机制适合当前受控演示与局域网边界，不等于完成公网生产级账户、安全审计、密钥轮换、数据加密、保留策略和灾备。
- 不能通过取消所有有效性检查来“提高准确率”。可以非阻塞提示，但结果必须保留缺测／中断／无法评价。

### 11.4 后端接口／操作查找表

这是定位入口的索引，不是所有接口参数的替代规范；不同宿主会做额外绑定、白名单或本地适配。

| 业务 | 当前入口／操作族 | 接到哪里 |
| --- | --- | --- |
| 档案、总快照与能力 | `profile.list/save`、`snapshot`、`capabilities`、`extensions.status` | ProductService、产品存储；participants 为康复独立档案域 |
| 健康与对话 | `health.record`、`chat` | 事件管道、AgentRuntime、检测与持久化 |
| 康复评估、计划与上传 | `/api/jobs`、`/api/body`、计划相关路由；Runtime 场景命令 | 录像分析、assessment／automatic_plans／training_plans |
| 实时指导 | `/api/live`、`/api/live/{id}/frame`、删除 live | 独立实时 worker；当前不等于保存了正式评估历史 |
| 管家康复查询 | `rehab.get_training_plan/recent_assessments/training_history` | 受范围限制的只读康复宿主工具 |
| 药物与安排 | `medication.save/status`、`daily.*`、`task.status` | 药物产品域、宿主 DailyStore、任务状态 |
| 照护调度 | `care.overview/next/prepare/status/confirm/cancel` | CareCoordinator 与宿主允许的原业务写入 |
| 资料与健康图片 | `media.import`、`archive.save/read/trash/restore/trash.list`、`image.parse/confirm` | 原件与元信息存档、可选视觉解析及确认 |
| 语音 | `voice.input/output/cancel`；电脑另有输入草稿转写操作 | 配置的 voice port／原生宿主；未配置不执行 |
| 设备数据 | `device.import/pull`、`healthkit.import/diagnostics` | 有效指标归一化、设备适配器 |
| 家庭／通知 | `family.invite/bind/grant/revoke/unbind/summary`、`notification.plan/ack` | 关系、分类投影、通知账本与渠道 |
| 同步与生命周期 | `sync.status/start/poll/publish/close`、`lifecycle.export/clear` | 可选同步协议、产品范围导出／清除 |
| 联系信息 | `emergency.contacts` | 联系人／建议联系路径，不等于自动通话 |
| APK 云端辅助 | `/v1/enroll/summary/family/backup/device` 等 | 独立设备、关系、摘要与文字备份库 |

空间家庭孪生、route2 spatial modeling、3D Gaussian Splatting 当前在 ProductService 中属于 retainedDisabled，不能作为正在运行的后端能力。旧分支／演示服务的同名功能，也不能自动视为正式五页和 APK 均已接入。

## 12. 需要重点统一的跨端算法口径

| 项目 | 电脑 Python | 独立 APK JavaScript | 优化建议 |
| --- | --- | --- | --- |
| 骨架／追踪 | YOLO17 或扩展 MediaPipe；不同追踪方法 | MediaPipe33／21 单目标 | 保存 backend、schema 与身份连续性，不仅存动作名称 |
| 方向基线 | 首个有效值及首次约 5°运动决定符号 | 连续≥5 样本、约≥0.8 秒、范围≤6°稳定参考；录像可两遍扫描 | 明确舒适起点 protocol，规定 live／replay 是否允许未来信息 |
| 平滑与幅度 | 坐标 EMA、角度窗口中位数证据 | 普通动作无同样 EMA，min／max 直接受原样本影响 | 用同一录制与关键点序列比较；统一稳健幅度定义 |
| 普通计次 | 专用准备／离开／回位状态与阈值 | 通用约 15°偏移、驻留／返回规则 | 共享动作契约与状态规范，而非只共享目录 |
| 坐站 | 到站起记一次；坐回重置 | 通用往返计次，非同一坐站专用逻辑 | 首先统一“一个完成动作”的定义 |
| 自动剂量 | min(5, 完整次数)，1 组、休息 60 秒 | 观察≥3 次时减 1 次作储备，休息 30 秒等本地规则 | 同版本规则库或显式 host-specific 契约 |
| 器械求导 | 时间窗二次拟合、频率／残差门槛、断跟停止 | 中位数后两次线性求导，无同样准入 | 保留算法版本，不混用峰值；为低频结果单独评质量 |
| 体态汇总 | 连续片段中位数、MAD、覆盖 | 本地片段／中位数逻辑，输出不完全相同 | 统一片段选择、统计和缺测字段 |
| 训练继续资格 | 计划版本、原证据、筛查与感受；质量独立报告，并非全面完成硬门槛 | 本地 planProgress 的有效率／目标完成／感受规则 | 共用资格测试向量，逐条件对齐 |
| 来源存储 | LIVE／REPLAY 与 SQLite／产品作用域 | PHONE_LOCAL 与本地状态／云端摘要 | 定义正式转换规则，不假定字段同名即等价 |

准确性优化建议先建立跨端测试向量：输入相同关键点和时间，比较同一 metric、phase、rep、quality、plan eligibility。再输入真实录像比较模型差异。否则两种误差混在一起，无法判断究竟是模型还是规则。

## 13. 问题清单：复现、代码风险与未接通要分开

### 13.1 已复现／已记录的阻断项

| 优先级 | 问题 | 证据／影响 | 下一步 |
| --- | --- | --- | --- |
| P0 | 调度把第三人／朋友语义当本人 | 69 项真实 HTTP 黑箱中的失败组 | 统一主语理解，未知人物只能澄清；确认页也显示对象 |
| P0 | 时间矛盾／歧义未澄清 | 上午16:00、中午四点 | 规范时间 AST：日期、时段、小时、歧义；先验证再生成动作 |
| P0 | 倍量服药被压成普通服药 | 已服用两倍剂量 | 保存原事实语义，异常剂量禁止走普通服药快捷写入 |
| P0 | 调度前端确认未接通 | HANDOFF 明确待实现 | 不是本轮任务；后续接卡片、状态查询与回执，不能绕过确认 |
| P0 | 曾出现 SQLite malformed | 同步目录黑箱中断，本机隔离运行未复现 | 单独复制／只读检查、确认使用者、迁移／备份／文件同步／中断写入；根因未定 |
| P1 | APK 源码／资源与旧安装包不同步 | 0.20 源码，APK 仍 0.2.1 | 构建清单标明源码 hash、模型／规则／资源版本，重新验收安装包 |

### 13.2 源码可见差异／风险候选，需专测后定论

- 首有效值／第一段运动决定基线；坐站首帧假定为坐姿：做错误起始姿势、镜头转动和第一段反向运动测试。
- 身体中心、最大面积或模型单目标不是真身份：加入陪同者穿越、遮挡后换人、多人相同服装测试。
- 屏幕轴与固定像素长度影响机位／距离：测相机倾斜、左右镜像、不同分辨率、远近和出平面角。
- Android 低频器械曲线与电脑版高频门槛不一致：比较采样 30／20／15／8／5 Hz 的速度、加速度和峰值误差。
- 原始极值与稳健幅度、不同端坐站计次和剂量不一致：做同视频／同关键点的差分测试。
- `hadTag` 对主诉状态的使用、每日时区、同次血压配对、PersonTwin 覆盖口径：写最小反例测试，避免推断成已复现缺陷。
- 家庭规则使用多条证据时，应验证极端私密读数是否被可共享普通读数“带出”；按证据逐条权限审查，不只检查最终一句文案。
- 无界队列、超时后仍写入、多文件与 job／SQLite 非原子提交：注入丢响应、硬盘满、进程退出和重复请求，对账是否只出现一份事实。
- 严格比较签名包含 job／基线细节：统计可比较率，再做分层协议；不可直接放宽所有字段。

### 13.3 已有接口或规划，但没有完整验证链

未配置视觉图片服务／联网模型／设备端口／外部通知／同步服务时，相应扩展只能报告 unavailable 或未连接。未形成完整能力的还有：全天多场景被动监控、真实步态参数与疾病结局模型、围度／体脂、通话喊话、自动医生处方、全量跨端患者库合并、运营级救援。

这些要按“输入来源 → 算法／规则 → 证据 → 存储 → 人工响应 → 结果反馈”逐项建设，不能仅靠新增一个 UI 入口或一个字段完成。

## 14. 从后端入手的优化路线

### P0：先保证数据与动作不会用错人、错时间、错事实

1. 建立统一语义命令：subject、claim_status、event_time、原话、指代依据、ambiguity、dose_deviation。普通健康事件与 CareCoordinator 都消费它，避免两套解析各自猜。
2. 为副作用操作统一 request_id、提交状态查询和幂等键。HTTP 超时返回“不确定／待查询”，不能等价于未提交。
3. 修已复现人物／时间／倍量反例；保存更正、取消、部分失败的审计。只读查询、健康记录、训练安排、处方边界不混用。
4. 把数据库损坏独立排查；不操作正常库强行迁移，不宣称隔离测试通过就根因已消失。

主要修改位置（后续实施）：understanding／CareCoordinator、care_host／DailyStore、ProductBackend、Storage。验收：已失败的 5 类语义在直接提议与实际聊天均通过，并保留原并发／幂等／部分失败测试。

### P1：统一算法契约与质量证据

1. 给每个指标定义 metric_id、参考轴、方向、单位、必要点、机位、最小骨段长度、滤波版本、起点与完成定义。
2. 将普通动作、坐站、健身、体态、器械各自的状态规范和共享测试数据版本化。不能为一致性把不同物理含义的角度硬合并。
3. 把观测质量拆成连续时长、覆盖率、轨迹连续性、关键点几何、采样频率、机位可信度、校准质量。模型 confidence 只是其中一个输入。
4. 幅度／峰值采用经过验证的稳健统计；原始数值仍保存可追溯。对低帧率器械结果限制输出等级，而不是填出缺失导数。
5. 输出统一 missing_reason、quality_grade、algorithm_contract 与 provenance。质量等级规则需通过验证，不先任意给所有结果打分。

主要位置：quality／rehab／movement_timing／fitness／posture／barbell；APK engine／motion／barbell。验收：跨端同输入结果差异有明确契约解释，不能出现相同标签实际含义不同。

### P1：建立离线回放与误差评估工具

建议新建独立验证数据集，不改患者业务逻辑：

```text
原片 hash + 脱敏录制编号 + 真实时间轴 + 录制条件
 → 模型关键点快照（记录模型版本）
 → 可重复规则回放（无需再次开相机）
 → 人工／仪器参考标签
 → 每动作／端／机位／人群的误差与失败报告
```

真实动作标注至少包含开始、端点、返回、遮挡／离框、参与者替换和结束；不只给一个总次数。先用已有肩外展／深蹲视频跑链路，再补全腿可见、错误动作、连续半次和异常输入。fixture 专门测规则，不替代真人标签。

### P2：在准确数据上改计划与趋势

- 训练建议按专业人员审核的适用人群／动作模板扩展；从本人可观察范围、动作质量、感受与计划履行产生解释，不让模型自由生成剂量。
- 基线用来源分层、异常值处理、覆盖门槛与稳定窗口；比较均值、稳健中位数／MAD 等方法后再替换。
- 变化检测区分绝对安全风险与相对个人变化；通知可做持续证据和冷却，不压掉紧急规则。
- 日常／步态先验证米制标定、轨迹、步事件和低帧率误差，再研究风险预测。预测需长期随访结局，不只用当前规则分数作标签。

### P2：性能与工程可靠性

- 产品慢任务与短查询分队列，设置容量、超时、取消与优先级；所有写操作仍有串行／事务保护，不盲目增加线程。
- 录像作业做幂等输入指纹、阶段检查点、SQLite／result 文件对账和可恢复提交。
- 双摄记录配对质量与推理延迟，避免某一路慢导致两路过期；是否并行由实测 CPU／GPU 与内存决定。
- 手机把低频姿态、器械追踪、OCR、语音分配性能预算；缩分辨率与缩采样分别记录，保持原媒体时间。
- 构建产物保存 app、Git、规则、模型、骨架、资源清单；自检信息应来自当前运行产物，不只来自仓库版本号。

## 15. 怎样证明优化有效

### 15.1 各功能的参考标准与指标

以下是验证方案，不是本项目已达到的数值或临床金标准声明。

| 功能 | 适合的参考 | 主要指标 | 常见错误验收 |
| --- | --- | --- | --- |
| 二维关键点 | 同步帧人工可见点标注／经过验证的参考系统 | 归一化点误差、漏点、左右混淆、换人率 | 只看骨架画得顺畅 |
| 二维投影角 | 同平面视频人工几何标注；若主张临床 ROM，另需专业量角／测量协议 | MAE、偏差、误差分布、重复测量一致性、有效覆盖 | 不同定义的角度直接比较 |
| 计次与相位 | 人工逐次起点／端点／回位标签，双人复核 | 次数误差、漏／多计、相位时间误差、半次误算 | 有总次数就算通过 |
| 保持／节奏 | 原视频时间轴的连续人工标签 | 时间 MAE、断流后的错误累计、低频偏差 | 用处理耗时对照动作时间 |
| 器械速度／功率 | 已知标尺与运动轨迹、可靠参考速度／力学设备 | 位移／速度／加速度误差、峰值偏差、跟踪失败率 | 填质量后能出功率就成功 |
| 体态 | 明确标志与机位的专业参考测量 | 系统偏差、重复性、最小可分辨变化、有效率 | 用模型点代替未提供的解剖点 |
| 跌倒／卧室事件 | 标注行为视频与场景真事件日志 | 召回、每小时误报、报警延迟、离线覆盖 | 只测摔倒样例，不测正常躺下 |
| 趋势／风险 | 审核的事件标签、长期结局／专业评审 | 灵敏度／特异度、校准、提前量、每人报警负担 | 把规则 score 当概率或病名 |
| 对话／调度 | 人物、状态、时间、对象、剂量、授权与目标操作的标准答案 | 事实 precision／recall、误写率、澄清率、完成率 | 只看回答语气像真人 |
| 计划 | 适用人群与专业人员审核的模板／病例 | 准入一致性、证据完整性、剂量审查、反馈停止率 | 计划生成了就叫指南级处方 |
| 存储／接口 | 故障注入与可核对提交日志 | 重复事实、丢失、恢复、跨人泄露、超时后的状态一致性 | happy-path 单元测试全绿 |

应按动作、手机型号、视图、距离、光线、衣着、辅助器具、遮挡和参与者分层报告；同一人的不同片段不跨训练／验证集合泄漏。优先报告覆盖和无法评价比例，避免只在最好片段算准确率。

### 15.2 建议的第一轮验收包

1. 肩外展：完整往返、半次、起点抬高、躯干倾斜、短遮挡、陪同者穿越。
2. 坐站：先坐／先站、没坐回、扶椅、遮挡、暂停恢复；逐端比较完成定义。
3. 深蹲：全腿、踝裁切、髋也裁切、侧位／斜位、快速与慢速；区分髋回退与膝测量。
4. 器械：固定标尺轨迹与 30→5 Hz 降采样，质量为空／20 kg、错标尺、断跟、背景同纹理。
5. 健康语义：本人／第三人、否定／假设／历史、午夜时区、指标更正、私密极值与共享普通值混合。
6. 调度：五类已失败输入、过期、对象变化、重复确认、丢回执、部分成功与存储失败。
7. 恢复：录像解码失败、磁盘满、权限变化、后台／熄屏、进程被终止；重开后核对真实提交状态。

每一项保存输入 hash、预期、实际、版本和失败原因；准确性目标在参考标签完成后确定，不在尚无标注时承诺 95% 等数字。

### 15.3 现有验证能证明什么

2026-10-11 的既有验证记录：Agent 431 项、产品扩展 16 项、Python 回归 324 项、Android Node 66 项通过；真实 HTTP 调度黑箱 69 项中 59 通过／10 失败，应用启动和隔离页面查看有证据。

这些是**上一轮有日期的验证**，本轮文档工作未重新运行全部测试。它们不能替代真人角度／器械精度、疾病预测、公网、手环、相机和红米实机验收。细节见 [本机同步验证](validation/GITHUB_SYNC_2026-10-11.md)。

相关测试目录：

- [电脑后端 tests](../rehab_codex_single_camera_v2_1/tests/)：动作、关键点、双摄、控制器、存储、计划、训练、历史、管家宿主。
- [托管手机 tests](../mobile_rehab/tests/)：上传／解码、健身、体态、器械、统一绑定、云端与健康链路。
- [APK tests](../android_offline/tests/)：本地引擎、器械、状态、Care、备份与适配。
- [Agent tests](../ankang/route1-health-agent/tests/)：理解、检测、隐私、持久化、设备、通知、调度与只读康复工具。

## 16. 技术依据和后续维护

- [Ultralytics 官方姿态任务说明](https://docs.ultralytics.com/tasks/pose/)：关键点输出与坐标语义；本项目仍用本地固定的 YOLO11 资源，不因官方文档新型号而自动升级。
- [MediaPipe Pose Landmarker 官方说明](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)：33 点、图像坐标及运行模式；SDK 有 world coordinates 不代表本项目已验证三维临床测量。
- [SQLite 官方事务说明](https://www.sqlite.org/lang_transaction.html)：写事务与锁的基础；本项目需另验证多进程和跨文件业务一致性。
- [Kinovea 标定说明](https://www.kinovea.org/help/en/measurement/calibration.html)：平面视频标定的参考条件；这里用于说明标尺与成像平面限制，不背书本项目误差。
- [现有医学与商业论证](plans/ANKANG_MEDICAL_EVIDENCE_2026-10-10.md)：已核对证据及人群、应用边界；不可将外部研究效果当成本项目效果。
- [软件规格](specifications/SOFTWARE_SPEC.md)、[HANDOFF](HANDOFF.md)：正式契约与当前交付状态；旧规格与现有实现冲突时应记录差异，不把旧要求当已实现。

后续每次改动后端，应同步四项：**算法契约、数据来源／传递关系、跨端差异、实测证据**。如果只改模型或阈值而没有更新这四项，下一轮很难判断结果变化来自真实改善还是口径变化。
