# 后端功能、算法与数据流梳理

> 用途：供团队讨论准确性、可靠性和下一轮后端重构。本文不是路演宣传稿，也不是医疗操作指南。
>
> 核对日期：2026-10-11。当前源码包含 `129e5cb` 的所属推理／诊断、`4c48195` 的全后端文档，以及相对于 `4c48195` 的本文件所在提交：默认派生报告所属进程与关闭保护。电脑端与托管手机产品版本为 0.20.0，现有 APK 安装包为 0.2.1。第 4–15 节描述原产品路径；第 17 节说明默认关闭的康复 v2 与研究模型；第 18–21 节用于定位代码、设计优化和追查信息传递。
>
> `4c48195` 是只整理文档的历史交付；本次沿后端任务书落实报告隔离，不改正式 UI、模型、APK、原服务或正常用户数据。旧性能报告保留运行当时的基准，不倒改实验版本。下文的“源码实现”“工程测试通过”“用户端已接通”“真人准确性已验证”是四种不同结论。历史 [文档核对](validation/BACKEND_MAP_CURRENT_2026-10-11.md) 与 [推理／诊断验收](validation/REHAB_V2_ISOLATION_TELEMETRY_2026-10-11.md) 保留；最新范围见 [报告隔离验收](validation/REHAB_V2_REPORT_ISOLATION_2026-10-11.md)。后端实施总任务仍未整体完成。

### 快速阅读

| 你要弄清什么 | 从哪里读 |
| --- | --- |
| 整个后端有哪些功能、分别在哪个端运行 | 第 1–2 节的功能目录和三端对照 |
| 一个功能的结果怎样进入另一个功能 | [第 3 节：对象与调用链](#backend-data-flow)、[第 21 节：逐跳交接与错误传播](#backend-handoffs) |
| 视频怎样变成角度、次数、节奏、功率和体态 | [第 4–7 节：视觉与动作](#backend-vision) |
| 健康指标怎样进入管家、用药和家庭 | [第 8–10 节：健康与照护](#backend-health) |
| 结果保存在哪里，超时、重试和崩溃怎么办 | [第 11 节：持久化与任务](#backend-storage) |
| 新后端做到哪一步，模型是否已上线 | [第 17 节：康复 v2 和离线模型](#backend-v2) |
| 先优化什么，用什么数据证明有效 | [第 18–20 节：实验与代码导航](#backend-optimization) |

每个功能尽量按“输入 → 技术方法／公式 → 输出 → 下游 → 实现位置 → 边界／验证”阅读。源码阈值是当前工程规则，不是临床金标准；建议公式和未来方案另行标明。

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

建议阅读顺序：第 2–3 节看架构与信息如何流动，第 4–11 节查具体功能，第 12–15 节查跨端差异和验证方案，第 17 节看 v2 后端，第 18–20 节选择实验、定位代码和判断优化效果。文中的功能按业务能力划分，不把每个内部辅助函数都列为一个产品功能。

### 1.1 功能查找与相互依赖

| 功能域 | 输入 | 核心处理 | 主要输出／流向 | 详见 |
| --- | --- | --- | --- | --- |
| 相机、录像、网络输入 | 设备、文件、RTSP、同意与输入条件 | 采集隔离、时钟检查、帧队列、生命周期 | FramePacket → 视觉 | 4.1 |
| 双摄辅助观察 | 两路帧与各自时钟、设备身份 | 接收时间配对、独立二维推理与测量 | 主指标 + 辅助质量指标 | 4.2 |
| 身体／手部关键点 | 图像、模型与骨架契约 | YOLO／MediaPipe、追踪、焦点选择 | PoseFrame → 逐指标几何 | 4.3–4.5 |
| 康复评估与汇总 | 有效指标、时间、动作／侧别 | 相位、计次、幅度、结束状态 | session → 身体汇总 → 建议 | 5.1–5.4 |
| 建议、计划、训练、反馈 | 原评估、筛查、规则、计划版本、自评 | 规则准入、冻结参考、组次／休息、继续资格 | 训练事实、进度、下一项 | 5.5–5.7、17 |
| 健身动作与器械 | 关键点、选定动作、标尺、器械轨迹／质量 | 往返规则、模板跟踪、拟合求导与力学计算 | 次数、节奏、速度／力／功率 | 6.1–6.2 |
| 体态 | 固定机位的可见标志点 | 分段、角度、偏移、中位数与覆盖 | 体态观察报告 | 6.3 |
| 活动、卧室与安全 | 关键点、ROI、连续状态 | 坐站／移动／离床／低位事件规则 | 区间、任务、警报与人工响应 | 7 |
| 健康指标、趋势、个人基线 | 本人事实、手动值、有效设备／图片输入 | 归一、去重、按日物化、基线与规则检测 | HealthEvent → Finding／PersonTwin | 8 |
| 管家、语音、图片和资料 | 文字／语音草稿、受权快照、图像／文件 | 理解、本地规则／可选模型、OCR、确认、存档 | 回复、获准记录、只读康复解释 | 9 |
| 用药、安排和照护调度 | 原说明、日常事实、明确意图、确认 | 对象／时间解析、事实复核、幂等业务提交 | 逐次记录、改期与回执 | 10.1–10.2 |
| 家庭、通知、同步和备份 | 分类授权、关系、可共享摘要／文字状态 | 权限投影、去重、投递状态、digest／revision | 摘要、通知账本、辅助云端备份 | 10.3 |
| 存储、任务、安全和导出 | 所有上游对象、提交请求与身份 | 事务、队列、审计、范围约束、派生报告 | 可追溯历史与可恢复提交 | 11 |
| 离线训练与模型评价 | 有许可的数据、独立标签、冻结划分 | 特征、基线／TCN训练、明确 run 评估、领域门控 | 研究模型卡与验证报告；不自动上线 | 17.7–17.9 |

其中最重要的依赖是：**输入与身份正确 → 指标含义正确 → 相位／计次可信 → 评估可用 → 计划有依据 → 训练事实只提交一次 → 反馈与进度一致**。上游出错，下游增加规则或换语言模型不能自动补救。

### 1.2 这份文档怎样用于优化

| 你遇到的现象 | 先看哪一层 | 不宜先做什么 |
| --- | --- | --- |
| 骨架抖动、左右混淆、被旁人抢占 | 4.3–4.4 的模型、骨架契约与焦点 | 直接调计次阈值掩盖点错误 |
| 骨架看起来对，但角度偏大／偏小 | 4.5 的参考轴、机位、基线 | 将模型 confidence 当角度误差保证 |
| 次数漏记、半次也算、提示慢一拍 | 5.2–5.3、17.2–17.5 的相位和时间 | 只改提示文字或取消全部证据检查 |
| 评估有结果，计划却不可用 | 5.4–5.6、17.6 的来源、筛查和版本绑定 | 回退过去最好成绩或自动代填自评 |
| 返回失败，重试后重复／进度不一致 | 11、17.5–17.6 的提交与回执 | 把 HTTP 超时直接当成未保存 |
| 手机、电脑对同一视频结果不同 | 2、12 的模型和规则差异 | 混拼两个端的角度与功率曲线 |
| 管家记错对象、时间或药物情况 | 8–10 的语义、事件与确认 | 用更自然的回答掩盖错误事实 |

每项优化最好一次只改变一层，保存对照版本和同一组独立输入。先定位错误，再选择滤波、状态机、模型或持久化的改动；第 20 节给出最小实验记录。

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

<a id="backend-data-flow"></a>

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

### 3.5 原产品实际调用链：从文件定位到结果

下面是职责顺序，不是声称所有调用都在同一进程或同一事务。

```text
电脑实时康复
  runtime.py / scene_controller.py：选场景、本人、动作、机位和运行上下文
    → camera_manager.py / source_worker.py：所属采集进程、FramePacket
    → vision.py / landmark_backend.py：PoseFrame
    → quality.py / geometry.py / axial_geometry.py：Observation、逐指标 valid/reason
    → rehab.py / training.py / movement_timing.py：相位、次数、组次、时间
    → guidance.py：下一步指令，不能反向修改观测事实
    → storage.py：session、逐次、配置与算法快照
    → assessment.py：本人／来源／情境下各动作侧别的最新评估
    → automatic_plans.py / training_plans.py：建议、保存和使用校验
    → 训练记录 + 自评 → program_progress / 下一项资格

电脑托管手机录像
  server.py：认证、上传、创建 job、绑定当前档案
    → 分析子进程 analyzer.py
       ├─康复：复用原 CameraManager / SceneController / Storage
       ├─健身：fitness_analyzer.py → fitness.py；可选 barbell.py
       └─体态：posture_analyzer.py → posture.py
    → result.json / error.json + job 状态
    → 普通历史与报告；康复可另引用 SQLite session_id

独立 APK
  local-api.js：适配原页面操作
    → worker.js：本地 MediaPipe 关键点
    → engine.js / motion.js：手机动作／训练／健身／体态规则
    → store.js：本地业务状态与媒体持久化
    → 按需通过原生受限连接 → phone_cloud.py：摘要／文字备份
```

关键差别：康复录像可能同时生成 SQLite 事实和作业 `result.json`；健身／体态作业不因此变成一份康复评估。APK 的本地报告也不会自动进入电脑患者库。判断“全部保存成功”必须核对对应路径的权威记录，而不是只看一个通用 `done`。

### 3.6 健康、康复和管家在哪里相接，哪里没有自动相接

| 上游 → 下游 | 当前传递内容 | 当前没有做的自动推断 |
| --- | --- | --- |
| 康复历史／计划 → 管家 | 受 owner、来源与情境限制的只读工具结果 | 不因查询制造新的测量或训练完成事实 |
| 健康对话 → 健康趋势 | 经理解接受的事实、来源、日期、状态和权限 | 不把所有聊天句子都当本人已发生事实 |
| 健康档案 → 康复计划 | 本人限制、已确认筛查等原计划输入 | PersonTwin／Finding 不自动变成病种诊断、禁忌或新剂量 |
| 训练自评 → 下一项资格 | 已保存的疼痛／疲劳／不适结束与计划版本 | 摄像头不代填疼痛；空值不当作 0 |
| 调度 → 训练 | 既有计划的安排日期／时间 | 改期不启动训练、不改目标、不改变原评估 |
| 健康／康复／用药 → 家庭 | 分类授权后投影的摘要、真实可见状态 | 不把整库或私密原话直接外发 |

因此，后续若要做“长期步态变化调整康复安排”，需要新增并审核一条明确的决策链：有效步态事件 → 变化证据 → 专业适用条件 → 原计划审核／调整。现在不能从一个风险分数直接跳到加量或治疗方案。

<a id="backend-vision"></a>

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

<a id="backend-health"></a>

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

<a id="backend-storage"></a>

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

### 11.2.1 六种状态不能合并成“成功”

| 状态 | 它实际证明什么 | 它不证明什么 |
| --- | --- | --- |
| 请求已接收／帧 accepted | 身份、格式和接收记录通过该入口校验 | 图像已被模型处理、动作已被确认 |
| 帧 processed | 对应帧已完成该后端处理和检查点 | 每个关节都可测、整次动作已经完成 |
| 动作 completed | 按当前版本规则取得了完整动作证据 | 幅度／节奏全部达标、没有代偿 |
| session finalized／canonical commit | 权威最终事实及该路径要求的事务已提交 | 派生报告、家庭通知已送达 |
| report ready | 报告由已保存结果派生成功 | 测量具备临床准确度 |
| plan complete／next eligible | 对应计划版本和继续规则的条件成立 | 已诊断恢复、可以自动增加剂量 |

原路径与 v2 的字段名称不同，不能把此表当成已经统一的枚举。该表用于设计接口适配和对账：保存链路失败时，必须说明停在哪一层，不能让页面自己猜。

### 11.2.2 哪些地方有事务，哪些地方还需要对账

| 边界 | 当前保证 | 发生中断后应查什么 |
| --- | --- | --- |
| 原康复 Storage 内的会话保存 | 同一 SQLite owning thread 的对应事务 | session、逐次、配置快照是否一起存在 |
| v2 最终事实 → 唯一计划贡献 | 同事务，终结重试找回 canonical commit | commit_id、snapshot digest、contribution 及 ordinal |
| DailyStore 业务变化 → Care 回执 | 宿主业务提交与 receipt 同事务 | 原事实、逐步回执，不能重做已成功步骤 |
| SQLite 会话 → 上传作业 result 文件 | 不是跨文件原子事务 | job 引用的 session_id、文件内容与实际库状态 |
| 产品不同 JSON 文件之间 | 每文件替换／备份，不是跨文件事务 | 各 key 的版本、原事实和派生状态是否一致 |
| APK 业务 JSON → IndexedDB 原件 | 不是单个 SQL 事务 | 记录是否可读、原文件是否存在、是否成为孤儿 |
| 本地通知账本 → 外部渠道 | 渠道状态与回执分阶段 | 本地 pending 与外部 delivered，是否有真实送达证据 |

建议后续建立“权威事实 → 可重建派生物”的对账器，而不是让报表、页面缓存和队列都成为独立事实源。当前 v2 派生报告已经部分遵循这个模式；不能据此说整个项目都已实现事务性 outbox 或恰好一次外部投递。

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

2026-10-11 的原产品验证记录：Agent 431 项、产品扩展 16 项、Python 回归 324 项、Android Node 66 项通过；真实 HTTP 调度黑箱 69 项中 59 通过／10 失败，应用启动和隔离页面查看有证据。

新增 v2 第一阶段记录为新后端 49 项、旧康复 12 项、旧手机接口 19 项通过；文档核对期间曾记录未提交增量的 61 项。最新完整运行 `verification-3b62b733` 为新后端 74 项、旧康复 12 项、旧手机接口 19 项通过，包含历史／贡献、显式时间安排与手动计划绑定；独立会话 CLI 44 项是其中子集。1308 个受保护文件与原基准 hash 相同。详见 [实施报告](../reports/rehab_backend/IMPLEMENTATION_REPORT.md) 和 [最新验收](validation/REHAB_V2_TIMING_PROGRESS_2026-10-11.md)。

上段数量指`23696de`的时间／贡献范围。随后`129e5cb`的交付实际运行100项后端、12项旧康复、19项旧手机及1308文件保护检查；会话CLI为其中70项，见历史 [进程与诊断验收](validation/REHAB_V2_ISOLATION_TELEMETRY_2026-10-11.md)。`4c48195`文档交付只复核既存日志，本次报告隔离则重新运行118／12／19项、1308保护核验及会话88项子集，见 [报告隔离验收](validation/REHAB_V2_REPORT_ISOLATION_2026-10-11.md)。18项报告专测包含在118项中。大量输入仍为夹具，真实YOLO接口使用无人白图，不能当真人准确性数据。

以上是有日期和范围的验证，本轮没有重跑全部产品／Android／Agent 回归。它们不能替代真人角度／器械精度、疾病预测、公网、手环、相机和红米实机验收，也不能互相累加成一个“总准确率”。原产品细节见 [本机同步验证](validation/GITHUB_SYNC_2026-10-11.md)。

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

<a id="backend-v2"></a>

## 17. 新增康复 v2：协议、正式事实与离线模型

### 17.1 先区分三个状态

| 内容 | 当前状态 | 用户端状态 |
| --- | --- | --- |
| 三动作协议、指标级证据、组次、提示事件、正式会话和离线训练 | 第一阶段 `1463929`；推理／诊断 `129e5cb`，报告见17.5.3；默认不启用 | 未接正式页面／APK；原用户路径不替换 |
| v2 分页历史、唯一计划贡献、同事务保存、跨计划版本的反馈继续校验 | 已提交 `23696de`；74 项新后端回归覆盖该版本 | 仅后端 opt-in 路径，尚未接页面 |
| 出程／回程／保持时间、原手动保存计划绑定 | 已提交 `23696de`；复用原时间算法和保存契约，不新增剂量 | 仅 v2 API；不改变旧客户端报告 |
| 默认 YOLO 所属子进程、共享内存、失败拒收与关闭重试 | 已提交 `129e5cb`；见 17.5.1 | 仅 opt-in 后端，不启用或重启原服务 |
| 有界 trace／阶段统计／诊断接口和 ASGI 性能命令 | 已提交 `129e5cb`；见 17.5.2 | 不参与测量事实；无手机／真人／压力结论 |
| 默认派生报告所属进程、取消／超时／重建与事实核对 | 本文件所在提交；见17.5.3 | 后台线程只调度；可信本地 callable 测试钩子仍不可硬取消 |
| 全 53 动作迁移、手机 RGB 域质量模型、姿态模型微调、通用训练处方 | 未完成 | 不能作为当前可演示功能 |

`create_app(..., rehab_v2=True)` 才安装新 API 并初始化新库；默认 `False`。YAML 的开关声明不能单独启动服务，本文也没有启动／切换服务。原 `/api/live` 仍是实时预览，删除预览不自动新增正式记录。

这里的版本化后端不是“换了一个更准确的视觉模型”：仍复用原 PoseAnalyzer 和因果 EMA；新增的是证据与状态规则、可靠提交和研究验证链。

### 17.2 三个试点的协议和完成含义

协议版本 `rehab-protocol-2.0`，只包含以下动作，不将健身深蹲直接当康复深蹲。

| 试点 | 主指标／必要点 | 机位与准备姿势 | 确认完成的证据 | 独立边界 |
| --- | --- | --- | --- | --- |
| 肩外展 | 上臂相对画面竖直的抬举角；所测侧肩、肘 | 正面；舒适垂臂，默认抬举角≤20° | 观察到离开、转折、返回起点带 | 腕／髋缺失不否定主计次；肘屈／躯干代偿可能无法评价 |
| 坐站 | `180°−髋膝踝内角` 的膝屈曲 | 侧面；先观察坐姿，默认膝屈≥60° | 膝屈≤25°并有连续证据时确认站起；坐回才重新允许下一次 | 站姿进入不补一次；完成一组需要观察坐回；不是标准椅站临床测试 |
| 康复深蹲 | 同定义膝屈曲；所测侧髋、膝、踝 | 侧面；先观察站姿，默认膝屈≤25° | 观察到屈膝离开、转折、站姿返回 | 不用健身髋代理补膝；不硬套健身深度；宿主计划兼容仍待补 |

默认连续准备 1 秒、准备窗口角度极差≤5°；确认驻留 0.18 秒、最长证据间隔 0.5 秒、结果年龄上限 500 ms。肩／深蹲默认离开幅度至少 10°，坐站至少 15°；转折相对本次峰值回落至少 5°；返回容差默认 8°。这些是源码中的工程默认参数，不是经验证的所有患者正常阈值，计划冻结时会保存实际使用值。

坐站相对幅度 `baseline_knee_flexion−current_knee_flexion`，肩／深蹲相对幅度 `current_metric−baseline_metric`。起点采用连续准备观测的中位数，不再无条件用第一帧建起点。不同动作的相对幅度和绝对角仍分开。

关键代码：[protocols.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/protocols.py)、[engine.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/engine.py)、[rounds.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/rounds.py)。

### 17.3 逐指标证据，不再只有一项“整个画面有效”

新 `MetricEvidence` 传递：`value、unit、valid、reason、evidence_kind、observed_at_s、computed_at_s、age_ms、required_joints`。

```text
可用于计次的指标证据
 = 有效且有限的数值
 ∧ evidence_kind 属于 observed / filtered
 ∧ 必要点、单位、观测时间与动作契约一致
 ∧ 0 ≤ age_ms ≤ 当前计划允许年龄
 ∧ computed_at_s - observed_at_s = age_ms / 1000
 ∧ 当前帧、参与者、来源 epoch 与序列正确
```

`filtered` 仍必须来自当前有效观测，不是用旧值顶替缺帧。`predicted`、过期值和缓存旧值不能确认次数、保持时长、计划完成或继续资格。主指标可用、辅助质量指标缺失时，允许计次但质量可为 `UNASSESSABLE`，不能给“无代偿”的结论。

每次结果分别保留：

- `completion_status`：完整／部分／无法评价。
- `target_status`：未设置／达标／未达标／未知。
- `quality_status + quality_assessable`：已观察问题／配置范围内未观察问题／无法评价。
- `plan_complete`：明确组次是否完成，独立于上述质量结论。

质量规则仅检查实际配置的肘屈／躯干倾斜上限；未配置或无法观察不等于一套完整临床质量评分。不能用这四个结果中的任何一个代替其余三个。

代码：[evidence.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/evidence.py)。

### 17.4 时间、缺测和过期结果怎样影响动作

```text
有效准备 → 建立 baseline / calibration_epoch
  → 连续离开 → 观察转折 → 连续返回 → 确认一次
         │             │
         └─短缺测───────┘：保留有限上下文，清空连续驻留，不累积缺测时长
               │
               ├─恢复后转折可能藏在缺口：无法评价，不猜完整次数
               └─长缺口／换人／模型或尺寸契约变化：恢复／重新准备

暂停／结束 → 清空旧提示和运动连续性
晚到推理 → 先核对 control_epoch / terminal_epoch，再进入 EMA 与规则
```

正式 JPEG 路径使用服务器同一进程的接收单调时间：`source_time_s = received_monotonic−session_started_monotonic`；处理年龄为该帧收到后至当前处理的间隔。它不是手机曝光时间，因此当前网络抖动会影响运动时间观察，不能用于声称曝光同步或高精度远程速度。录像回放仍可使用原媒体时间；两者的 `time_basis` 不同，必须记录。

这是下一轮准确性优化的重点：如果需要跨设备采集时钟，先定义时间映射／不确定度、缓冲上限和重连 epoch，不能直接相减手机与电脑的 monotonic，也不能只接受客户端随意填的时间。

#### 17.4.1 节奏与保持怎样计算、怎样保存

提交 `23696de` 接通原 [movement_timing.py](../rehab_codex_single_camera_v2_1/app/movement_timing.py)，未修改原算法；新 [timing.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/timing.py) 加入 `rehab-observed-timing-2` 封套、原算法版本 `observed-timing-1`、time_basis、样本数与首末／站起／开始回坐／坐回证据引用。计划只消费已明确保存的 `outbound_min_s/max_s、return_min_s/max_s、hold_min_s`，缺失不自动填训练要求。

```text
肩／康复深蹲：仅完整、连续观察的往返结束后
  z_i = 当前主角度                          动作增大方向为正
  m_i = median(z_i-1, z_i, z_i+1)           三样本中位数，时间仍取 t_i
  B = {i : m_i ≥ max(m) - 3°}              必须是一个连续峰区
  T_out  = t_B首 - t_首有效样本
  T_peak = t_B末 - t_B首
  T_back = t_末有效样本 - t_B末

坐站：协议连续确认站位，随后观察开始回坐和坐姿重装
  T_rise = t_站起确认 - t_本次首有效样本
  T_stand = t_开始回坐 - t_站起确认
  T_lower = t_坐回确认 - t_开始回坐

实时目标保持：当前样本达目标且连续有效
  H_live = t_当前 - t_本段首次达目标
  H_record = max(每一段已观察连续保持时间)   不把多个短段相加
```

三样本中位数含后一条样本，所以峰区公式只做**结束后回顾分段**；实时保持和提示不使用它。肩／深蹲至少 5 个样本，首末不能仍在峰区，多峰不合并；无锚点、边界未观察或区间跨缺测时输出 `null + reason`，不能补零。保持以首末样本时间差计，不按帧数乘采样周期：例如间隔 0.05 秒的 10 个观测只覆盖 0.45 秒。

肩／深蹲保持锚点是已保存的投影角目标；坐站锚点是 v2 协议站位膝屈范围，不冒充旧个体髋／膝校准或临床站立平衡。计划给出的上下界逐项判断 `MET/NOT_MET/UNASSESSABLE/NOT_SET`。缺测时已经观察到的最长保持段仍保留；若不足目标且观察不完整，则无法评价，不能认定患者没做到。时间结果独立于确认次数和组次，`count_gate=false`。

暂停、无效／预测／过期指标、丢帧或换人会中断连续保持。在途旧帧与被覆盖的较新待处理帧按序列前缀处理：不倒过来否定旧帧，但下一幸存帧不得跨丢帧续保持；丢帧待兑现期间不发保持提示。坐站站起时先保存一次，草稿期间补齐后续回坐时间；逐次表、快照、回执和重开查询一致，终结后不能再写计次或时间。实际原片／临床时间误差仍待独立验收。

### 17.5 指导事件、训练与正式提交如何串联

提示包包含 `cue_id、session_id、exercise_id、side、calibration_epoch、evidence_refs、observed_phase、valid_phases、priority、expires_at_source_s、ttl_after_emission_ms、instruction`。默认有效 2 秒；相位改变、暂停、缺测、结束或校准 epoch 改变时取消。普通重复动作提示冷却约 2 秒，姿势纠正使用计划参数，默认 8 秒。该层复用 GuidancePolicy，不播放语音，也不让语言模型另起一套计次／质量规则。

训练只消费**已经明确提供的** `target_reps、target_sets、rest_between_sets_s`，不生成新剂量。计次达到一组后进入休息／下一组；坐站先回到可观察坐姿。重新开始下一组要满足原休息安排；休息和暂停不进入动作证据。

```text
身份认证 + 同意 + 创建幂等键
 → 宿主解析本人计划 ID / revision / entry_key / 原证据引用
 → 冻结计划、工程参数、协议、来源与 scope
 → JPEG → 原 YOLO → MetricEvidence → 协议／组次 → cue
 → 确认次数 checkpoint
 → finish 冻结接收高水位 → 有界收尾
 → 一个事务：最终逐次事实（含时间）+ 快照 + canonical commit + 唯一计划贡献 + 审计
 → 异步派生报告
 → 追加自评 feedback（独立 revision，不改视觉事实）
```

默认一个正式活动会话、一个待处理帧槽、8 个并发控制请求；接收上限 24,000 帧、会话上限 20 分钟。JPEG 每帧≤512 KiB、面积≤1920×1080、最短边≥32；只接图像，不接外部任意关键点。内部确定性回放单独标记 TEST／SYNTHETIC。

收尾最多等待 2 秒，不无限等慢推理；接收、处理、保存序列分开，覆盖／未处理帧记录原因。相同请求键与相同载荷返回旧回执，同键换载荷冲突。结束后的晚结果不改最终快照；报告失败不撤销已经提交的训练事实。

持久库采用独立 `rehab-v2.sqlite3`，复用原 Storage 的 owning thread；原 SQLite `user_version=4` 不变，v2 namespace 单独迁移和备份。v2 第一阶段 namespace 为 1，`23696de` 的贡献扩展为 2。真实进程退出后保留已确认次数，未确认动作不补完整；重开终结为 interrupted，清空实时保持，不自动恢复一段无法保证连续性的动作。

代码：[service.py](../mobile_rehab/rehab_v2/service.py)、[sessions.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/sessions.py)、[cues.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/cues.py)。`23696de` 的推理／报告为线程；`129e5cb` 默认推理改为以下所属子进程。本次默认报告也改为所属进程（17.5.3），调度及 SQL 仍在宿主线程；真实磁盘满与损坏恢复尚未完整验收。

#### 17.5.1 所属推理进程与故障保护

最初文档任务只读取工作区实现；随后按实施任务书验证并提交为 `129e5cb`。实现为 [pose_worker.py](../mobile_rehab/rehab_v2/pose_worker.py)，服务／测试同步；下述数值来自类默认值，不是 YAML 会自动加载的运行设置。

```text
宿主会话：owner / session / source_epoch / control_epoch / seq / 源时间
  → 有界 JPEG 共享缓冲区 + 小型 JSON 通知
  → 一份所属 spawn 子进程：解码 → 原 VisionWorker / YOLO
  → 有界 JSON 姿态共享缓冲区 + 长度／SHA256 通知
  → 宿主核对 ticket、Context、seq、源时间和载荷
  → 再核对控制／结束 epoch → EMA → MetricEvidence → 状态机 → 保存
```

| 项目 | 当前已提交实现 | 不能扩大成的保证 |
| --- | --- | --- |
| 资源职责 | 子进程只解码、推理；宿主持有业务状态、时钟、EMA 和数据库 | 没有将所有慢业务或全部产品进程隔离 |
| 传输容量 | JPEG 512 KiB；姿态 JSON 4 MiB；总共享内存 4.5 MiB；通知≤4 KiB | 不是整个模型内存或服务总内存只有 4.5 MiB |
| 超时预算 | 启动握手 10 s，首个冷推理 30 s，热推理 5 s；终止／强杀各等待 1 s | 握手预算从 Process.start 返回后计；未证明 OS 创建调用本身有硬截止 |
| 时间契约 | 子进程报告自身阶段耗时；证据源时间与年龄由宿主负责 | 不相减两个进程时钟，不把接收时间说成曝光时间 |
| 超时／退出 | 终止准确的所属 Process 并确认退出，失败原因保留；后续新任务可重建 | 不杀其他服务，不宣称错误动作已经完成 |
| 清理 | 成功调用后清空传输缓冲；失败时确认退出后关闭共享内存／管道 | 不宣称成功存活模型内部的全部 RAM 都被逐字节清零 |
| 未确认释放 | 保留所属句柄、隔离资源，重试释放前不另起一份泄漏的进程 | 没有“返回关闭成功但旧进程还活着”的承诺 |
| 持久化故障 | 帧消费者失败后记录运行态 failure，拒绝新帧／新建，返回 backend_execution | 失效数据库中的故障记录不保证已保存；不把草稿说成最终提交 |
| 暂停／结束 | 晚结果先核对 epoch；结束先保存不可变事实，再取消当前 sid 的在途推理 | 不让旧失败终止已经恢复的新控制上下文 |
| 关闭重试 | 未确认释放不关闭仍可能被使用的存储；资源后来释放后可再次关闭 | 可信本地 callable 钩子不能硬强杀；实际磁盘满／损坏还待测 |

17 项推理隔离测试是 `129e5cb` 交付时100项后端回归的子集，本次18项报告隔离测试另见17.5.3。它们说明指定工程场景，不能证明真人、手机长运行、未知原生死锁或真实硬盘故障全部可靠。OS 创建硬截止、用户负载压力与真实存储故障验收仍缺。

#### 17.5.2 有界诊断、阶段耗时与实际性能

认证查询 `/api/rehab/v2/sessions/{sid}/diagnostics` 只输出本会话诊断。服务端生成 source.execution_trace_id，幂等创建和重开保持同一值；JPEG 正式会话没有录像 job，job_id 为 null。trace 不是 owner／患者身份，不含图像、骨架或原话，也不进入计次／计划判断。代码：[telemetry.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/telemetry.py)。

队列、解码、原 YOLO、进程往返、特征、规则、指导、检查点、控制、最终事务、报告分别计时；pose_result_age_ms 为推理返回年龄，result_age_ms 为完成检查点后年龄，均从宿主接收时间算，不冒充曝光／互联网时延。未执行时为 null；TCN 关闭不报 0 ms。累计计数与保留窗口分位数分开，每阶段 512 个数值、事件总尾部128条，nearest-rank p50／p95；接收／处理率是宿主实际速率，不是相机FPS。队列／在途／SQL待处理和RSS为即时观测，不是业务事务快照或峰值内存。

终结缓存最多保留32个运行对象（另有在途／当前对象）；重启或淘汰后只保留 SQL 中 trace_id，返回 available=false，不从历史编造统计。诊断读取不改变不可变训练事实；9 项测试覆盖固定枚举、数值有限性、并发、有界窗口、未知状态、鉴权、慢报告、队列覆盖和旧 epoch。

新 [实际会话性能命令](../tools/rehab_ml/session_benchmark.py) 使用隔离 ASGI／认证／原YOLO／SQL和12张无人白色JPEG，不开相机，单生产者等结果后暂停／恢复。末次 `session-performance-a394a83e`：冷往返2286.91 ms，热推理p95 40.87 ms、宿主结果年龄p95 57.19 ms；控制HTTP p95 17.78／13.58 ms。原始值与SHA见 [session_performance.json](../reports/rehab_backend/session_performance.json)。候选未执行；没有多人压力、真实直播、手机或准确率结论；结束／最终事务只有各1样本，不能说稳定p95。

#### 17.5.3 默认派生报告：有界进程、不可变事实与反馈 CAS

代码：[reporting.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/reporting.py)、[report_worker.py](../mobile_rehab/rehab_v2/report_worker.py)、[owned_worker.py](../mobile_rehab/rehab_v2/owned_worker.py)。纯报告构建函数保留原10个输出字段；进程生命周期与姿态推理共用，不接新模型或诊断规则。

```text
已 finalized 的本人会话快照
 → 单报告槽（忙时返回 running，不排队、不写失败）
 → 白名单 JSON 输入 + 长度／SHA256／ticket／sid／feedback_revision
 → 所属 spawn 进程：纯派生报告（无数据库、相机、LLM）
 → 宿主核对返回身份、耗时、内容与原始事实
 → report_state 的 feedback_revision CAS
 → ready / failed / pending_newer_feedback；原最终快照／回执／贡献不改
```

| 项目 | 实际实现 | 边界 |
| --- | --- | --- |
| 输入 | sid、source_epoch、frozen_plan、source、snapshot、end_reason、feedback_status、feedback_revision | 不传认证凭证、顶层owner或commit；已有冻结计划可能包含本人参考元数据，不能称完全匿名 |
| 容量／并发 | 输入2 MiB、响应2 MiB、总共享内存4 MiB；管道通知≤4 KiB；并发1；SQL最多取16待办 | 是传输上限，不是宿主／子进程总RSS；超过容量只令报告失败 |
| 默认预算 | 握手10秒、报告等待5秒、terminate／kill各等1秒 | Process.start自身无OS硬截止；JSON序列化／宿主纯核对有容量上限但无独立硬截止 |
| 权威核对 | hash、ticket、sid、反馈revision（含类型）、输入hash、有限compute_ms；完整报告digest对照纯原事实 | 子进程不能凭改次数、来源、计划或证据指纹获得写入资格 |
| 反馈竞争 | SQL写报告时重查feedback_revision；旧结果被标记superseded，下一轮生成新反馈报告 | 不重写视觉事实，不重复增加执行量 |
| 超时／退出／关闭 | 只终止准确所属对象、确认退出、清零共享区、关闭／unlink；失败后可新建重试 | 释放未确认保留句柄和数据库lease，后续可再次close；不杀用户旧窗口 |
| 报告存储失败 | backend_execution／diagnostics可查固定故障码；pending留待重试 | 故障库本身无法写入时不声称failed已经持久化；当前只是OSError受控注入 |
| 诊断 | report_ms为宿主整次构建／核对／写入；另列子进程report_compute_ms及不含首次握手的report_roundtrip_ms | 未运行保持null；报告RSS只在本sid在途时读，不把空闲共享进程归属给别的会话 |
| 可信本地钩子 | 显式report_builder callable仍为trusted_local_callable，单槽且声明无硬取消 | 不是HTTP字段；若挂起，close明确失败并保留存储，不宣称它已进程隔离 |

18项专测实际覆盖默认构建、共享区复用清空、真挂起／退出、容量／身份／事实篡改、取消、释放重试、重开补建、反馈CAS和派生写入故障。只有工程可靠性边界，不是准确率提高、手机实机或全负载结论；命令与日志见 [报告隔离验收](validation/REHAB_V2_REPORT_ISOLATION_2026-10-11.md)。

### 17.6 本次增量：事实怎样贡献到历史和计划

以下已包含在提交 `23696de`，不是原页面已经可见的行为。

新增 `rehab_v2_plan_contributions`，一条最终事实按 `session_id + plan_id + plan_revision + entry_key` 唯一关联。贡献和最终事实在同一事务中保存；写贡献失败会一起回滚，不出现“训练保存了但计划凭空完成”。贡献保存实际来源、scope、原计划引用 digest、视觉快照 digest、完成次数／组数、完成状态和排除原因。

历史按数据库提交 `ordinal` 做有界游标分页；未提交草稿不出现在最终历史中。最新尝试不靠系统 UTC 或 UUID 排序，系统时间回退不会令旧成功掩盖新中断。反馈追加有自己的 revision，不回写原视觉快照／提交回执。

传给旧计划规则的是专门的临时政策视图，不是往旧库伪造一条测量。继续复用 `general-activity-rules-1`，不改剂量、不将新逐次质量强塞旧角度规则。计划完成只绑定当前版本的条目；疼痛／疲劳核查还读取同本人、同来源情境、同动作／侧别的最新贡献，不能靠换一个 plan ID 清掉之前的不适反馈。

当前宿主要求匹配的 `LIVE_CAMERA / SELF_USE` 计划与明确机位，不将原 `REPLAY_FILE` 计划改名充当相机计划。自动安排复用原 `validate_automatic_use`；原手动保存计划需 `training_plan_confirmed=true`，要求陪同时另需 `companion_confirmed=true`。`prepare_training_plan / validate_saved_binding` 复核保存的原条目、评估契约和 reference；请求不能覆盖剂量或节奏。计划查询返回 `manual_confirmation_required`。现有宿主适配肩外展／坐站；康复深蹲兼容计划未补。坐站旧非空角度目标与 v2 相对减少量定义不同，仍拒绝；明确节奏安排现已接通 17.4.1 的原时间算法。

| API | 功能 | 信息边界 |
| --- | --- | --- |
| `POST /api/rehab/v2/sessions` | 创建与冻结 | 本人计划、同意、幂等；宿主解析，不相信任意处方 |
| `POST /api/rehab/v2/sessions/{sid}/frames` | 接收 JPEG 帧 | event ID、seq、图像 hash；当前本人／会话 |
| `POST .../{sid}/pause`、`resume`、`finish` | 控制与收尾 | operation key、expected revision；重试先查已有结果 |
| `GET .../{sid}`、`GET .../{sid}/commit` | 会话与权威提交查询 | 报告可 pending；提交不能因此当失败 |
| `POST .../{sid}/feedback` | 追加疼痛／疲劳等自评 | 独立 revision；null 不代填 0 |
| `GET /api/rehab/v2/sessions` | 最终历史 | 当前本人、limit 1–100、before 游标；不是旧评估历史 |
| `GET /api/rehab/v2/plans/{plan_id}` | 计划／进度查询 | 当前本人／版本、支持情况、blocked／next_key／manual_confirmation_required |

增量主要文件为 `app/rehab_v2/progress.py`、`timing.py`、`sessions.py`、`mobile_rehab/rehab_v2/{api,service}.py` 及宿主 `server.py` 的显式启用块。正式页面、APK、旧历史和旧 `/api/plan` 没有改为调用它们。

### 17.7 已有离线训练链及每段输出

新增工具入口 [tools/rehab_ml](../tools/rehab_ml/README.md)，产品环境与训练环境分开；不为训练升级产品依赖。原始数据、权重、私人录像和测试库在忽略的 `.runtime/rehab_ml/{data,run,model}`，不提交 Git。

```text
官方数据元信息 + 许可资格
 → 固定版本下载／字节与 MD5、SHA256、ZIP 安全校验
 → 命名关节、坐标、TrackingState 和整次标签适配
 → 数据 manifest / fingerprint / unknown 隔离
 → 先按人划分 train / val / test（再提取样本特征）
 → 因果特征 + 明确 mask / feature fingerprint
 → 简单 logistic 基线 / 因果 TCN 真正训练
 → val 选模型 → 明确 run ID 的冻结 test 预测
 → 分人／姿势／队列结果 + 混淆矩阵 + bootstrap 区间
 → 模型卡、依赖锁、检查点 hash、领域与上线门控
```

下载失败、许可资格缺失、骨架不匹配、标签未知都不能降格成“有效正确样本”。标签模板区分物理完成、可观察完成、阶段、错误、提示机会、专业复核、训练授权和任务 mask；现有实际训练数据没有其中所有标签，所以相应模型头禁用。

当前实际数据仅 IRDS 2.0.1 的 Kinect25 三维骨架肩外展相关动作：534 条／29 人，532 可训练、2 未知隔离；正确 449、错误 83。按人 17／6／6 分组，样本 train 310、val 131、test 91。它不是手机 RGB 2D，也不提供坐站、康复深蹲或独立相位／提示机会标签。

数据资格和实验原始证据见 [第一阶段实施报告](../reports/rehab_backend/IMPLEMENTATION_REPORT.md)、[完整实验摘要](../reports/rehab_backend/experiment_summary.json)。REHAB24-6 的学术／非营利资格待确认，其他部分官方数据访问尚未成功；未绕过许可或拿不明第三方镜像训练。

### 17.8 特征、基线与 TCN 的实际算法

特征版本 `kinect25-shoulder-causal20hz-1`，128 维，包含当前帧肩中心／肩宽归一坐标、后向差分速度、观测／速度 mask、TrackingState、左右肩角与 mask、取样年龄／新鲜度、侧别。

```text
root_t = (left_shoulder_t + right_shoulder_t) / 2
scale_t = ||left_shoulder_t - right_shoulder_t||
q_j,t = (p_j,t - root_t) / scale_t
v_j,t = (q_j,t - q_j,t-1) / Δt             仅两帧均有效时
缺测特征数值置 0，同时 mask=0              不是实际观察值为 0
```

20 Hz 网格向下取最近历史样本，不用未来插值。IRDS 原时间以名义 30 Hz 表示，不冒充已核验曝光时钟。骨架观测 mask 保留官方 Tracked／Inferred／NotTracked 区别，不能将它们当成 YOLO confidence。

| 模型 | 输入与方法 | 可以输出什么 | 不可以输出什么 |
| --- | --- | --- | --- |
| Logistic 基线 | 整段 mean／std／min／max／median／p90／首末差／时长；train-only 标准化、L2 分类 | 动作结束后的整次正误分类 | 实时相位、代偿部位、测量角度、处方 |
| 因果 TCN | 64 通道；4 残差块；每块 2 卷积，kernel 3、dilation 1／2／4／8；左填充、逐时刻 LayerNorm、dropout 0.1 | 整次结束后 masked mean + 二分类 head | 因卷积因果就自动称为实时提示模型；当前 head 仍需要整段 |

TCN 感受野 `R = 1 + 2×(3−1)×(1+2+4+8) = 61` 步。20 Hz 名义采样下，最远历史跨度为 60 个间隔，即约 3 秒；完整序列 head 仍在结束后聚合，不使用未来样本来做实时决策。损失为有独立标签样本的加权交叉熵，`label_mask=0` 不参与损失，全部缺标时为连接计算图的零损失，不把未知当正常。

训练采用 AdamW；标准化、类别权重只在 train 上计算，模型选择用 val，不拿 test 调阈值。源码见 [features.py](../tools/rehab_ml/features.py)、[models.py](../tools/rehab_ml/models.py)、[training.py](../tools/rehab_ml/training.py)。

### 17.9 实验结果、回退与尚未解决的问题

| 模型／明确 run | test macro-F1 | 正／误混淆矩阵（行真值、列预测） | 错误动作召回 | 判断 |
| --- | --- | --- | --- | --- |
| Logistic：`20261010T185211Z-logistic_regression-c78b48c6` | 0.6341 | `[[61,22],[0,8]]` | 1.0000 | 误报正确动作较多，不是已上线准确模型 |
| TCN：`20261010T185214Z-causal_tcn-84cbc486` | 0.5444 | `[[79,4],[7,1]]` | 0.1250 | 未优于基线，保持关闭 |

测试只有 6 人、8 条错误动作，不能拿上述结果承诺老人／手机准确率。候选模型卡按 input domain、骨架、坐标、feature、动作、侧别、机位、协议与许可逐项匹配；不匹配回退规则。ShadowSequence 默认 research-only，预测不能改计次、进度、继续资格、剂量和当前提示。

现有两段私人录像的真实回放：肩外展 443 帧、主指标可观测 434 帧，新协议 0 次／旧引擎 2 次；深蹲 429 帧、膝主指标可观测 48 帧，新协议 0 次。前者缺默认稳定准备段，后者大部分腿部证据不可用；这说明验证必须覆盖准备／视野条件，不能把“工具跑完”当成“自动计次已准确”。没有独立专业参考标签，准确率仍未知，也未授予这些录像训练权限。

姿态微调命令 `build-pose-dataset / train-pose` 当前只是资格检查与明确拒绝，不是完整微调实现。下一步需要与产品同域的授权 RGB、可见关节标注、专业动作／变式标签和独立人员测试集。

比较契约现已区分“指标含义是否兼容”和“本次证据身份 fingerprint”；但仅是二维投影的工程比较，不是临床 ROM 一致性证据。任意相机旋转、裁切、非等比例拉伸、跨端或解剖参考改变仍需单独验证。代码：[temporal.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/temporal.py)、[compatibility.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/compatibility.py)。

<a id="backend-optimization"></a>

## 18. 你下一轮可以怎样从算法入手

### 18.1 不先换模型，先确定错误发生在哪一层

同一段原片建议保存三条并行结果：`原模型关键点 → 旧规则`、`原模型关键点 → v2规则`、`参考关键点 → v2规则`。其中参考点必须来自独立人工标注／适合该指标的参考测量，不是把旧模型输出改名。

- 后两条都错：优先查指标定义、机位、时间或动作协议。
- 参考点规则正确，模型点规则错误：优先查姿态模型、焦点和可见性。
- 计次正确，角度偏差大：优先查参考轴、起点、相机方向与二维投影。
- 最终数字正确，历史／计划不一致：优先查绑定、事务、版本、反馈和回执。
- 离线正确、实时错误：优先查队列覆盖、时间映射、晚结果和性能预算。

这样能避免为起点或提交问题训练一个更大模型。

### 18.2 第一轮实验清单

以下均为建议，不是已修改的参数。先冻结预期与测试集，再改算法；不要反复用已有两段录像调到“看上去正确”。

| 顺序 | 假设／要改什么 | 最小独立输入 | 评价与决策依据 | 主要位置 |
| --- | --- | --- | --- | --- |
| 1 | 准备段导致漏计；完善稳定起点和恢复提示，保留无准备结果的真实限制 | 完整准备、无准备、起点高抬、首段反向、先站坐站 | 准备成功率／耗时、第一下漏计、错误起点接受率 | protocol／engine／cue |
| 2 | EMA 滞后影响端点与提示；比较原 EMA、自适应因果滤波、无滤波 | 慢／快动作、短遮挡、已知时间轴及标注端点 | 点／角 MAE、相位延迟、抖动、缺测后错误累计 | quality／EvidenceAdapter |
| 3 | 图像参考轴在机位变化下有偏；完善机位与参考可信度 | 同动作不同相机倾角／距离／出平面角，独立几何标注 | 系统偏差、重复性、覆盖、拒绝率；不能只比均值 | geometry／契约／comparison |
| 4 | 当前焦点会被旁人替换；明确身份连续性与重建规则 | 陪同者穿越、遮挡换人、重新入镜、相似服装 | 抢占率、错误合并次数、恢复时间 | PoseAnalyzer／track／epoch |
| 5 | 单目 2D 质量需专业标签；规则／简单模型／TCN 同域比较 | 授权 RGB + 合法扶手／代偿／正常变式 + 独立复核 | 分人、动作与变式的 recall／precision、覆盖、误提示负担 | features／训练／model card |
| 6 | 手机低频器械不能稳定估计导数；速度追踪与姿态分预算 | 已知标尺轨迹与 30／20／15／8／5 Hz 降采样 | 速度／加速度／峰值误差、可用率、功耗；低频可只报速度 | barbell，独立 APK 后续适配 |
| 7 | 正确结果可能重复／丢失；验证所有持久化和恢复边界 | 丢响应、重复结束、暂停中推理返回、硬退出、磁盘满 | 事实恰好一份、报告可重建、进度不超记、未提交可查询 | sessions／jobs／Storage |
| 8 | 计划和趋势可能消费错来源或未知值；统一输入语义 | 同本人多来源、最新失败、自评缺失、跨午夜、换计划 | 来源隔离、不得补零／回退旧好成绩、继续资格一致 | assessment／plan／events |

### 18.3 一份实验最少交付什么

1. 问题与假设：例如“在同平面快速肩外展中，滤波延迟增加回位时间误差”。
2. 冻结输入：原片／标注 hash、本人脱敏 ID、机位、帧时间、动作变式、授权用途。
3. 对照版本：模型 hash、骨架／坐标、规则／特征版本、所有参数、采样／降级方式。
4. 独立划分：先按人划分；同人的相近视频和切窗不能分散到 train／test。
5. 多维结果：数值误差 + 可用覆盖 + 漏／多计 + 延迟 + 误提示；报告失败样本，不能只保留成功片。
6. 上线决定：达到预先约定的工程／专业审核条件才灰度启用，保留旧路径和回退；不能以单次演示成功取代验证。

对当前项目，我建议首先做**准备／恢复证据、参考轴与时间、正式事实的绑定／提交**；再基于授权同域数据优化姿态和质量模型。管家与健康趋势的语义问题单独修复，不与视觉模型训练混成一个“整体准确率”。

## 19. 代码导航：具体优化应该从哪里动手

这里列的是后端职责入口，不要求重写全部文件。最新所属进程和诊断单列在 17.5.1–17.5.2；其他位置保留原职责。页面如何显示不属于本轮范围。

### 19.1 视觉、动作和训练

| 功能／层 | 主要实现位置 | 输入 → 输出 | 改动时必须一起核对 |
| --- | --- | --- | --- |
| 输入时钟／帧连续性 | [source_worker.py](../rehab_codex_single_camera_v2_1/app/source_worker.py)、[domain.py](../rehab_codex_single_camera_v2_1/app/domain.py) | 设备／文件 → 带 Context、seq、time_basis 的 FramePacket | 原媒体时间、断流、负首帧兼容、上下文，不用推理耗时替代源时间 |
| 相机释放／双摄配对 | [camera_manager.py](../rehab_codex_single_camera_v2_1/app/camera_manager.py)、[dual_camera.py](../rehab_codex_single_camera_v2_1/app/dual_camera.py) | 两路独立帧 → 有配对质量的主／辅输入 | 设备身份、一次消费、接收时差、旧所属进程退出 |
| 模型推理／骨架契约 | [vision.py](../rehab_codex_single_camera_v2_1/app/vision.py)、[landmark_backend.py](../rehab_codex_single_camera_v2_1/app/landmark_backend.py)、[landmark_schemas.py](../rehab_codex_single_camera_v2_1/app/landmark_schemas.py) | 图像 → 点／置信度／跟踪／模型和坐标契约 | 模型 hash、关节顺序、左右侧、坐标、不同后端域，不只替换权重 |
| 焦点／滤波／可观测性 | [quality.py](../rehab_codex_single_camera_v2_1/app/quality.py) | PoseFrame → Observation | 换人重置、跳变、缺测不补、滤波滞后和辅助指标独立性 |
| 测量公式／动作参考 | [geometry.py](../rehab_codex_single_camera_v2_1/app/geometry.py)、[axial_geometry.py](../rehab_codex_single_camera_v2_1/app/axial_geometry.py)、[exercises.py](../rehab_codex_single_camera_v2_1/app/exercises.py) | 可见必要点 + 起点 → 指标 value／valid／reason | 内角／屈曲区别、参考轴、baseline、方向和 measurement version |
| 旧相位／计次 | [rehab.py](../rehab_codex_single_camera_v2_1/app/rehab.py) | 连续 Observation → 相位、完成次、部分次 | 准备、阈值滞回、驻留、半次、坐站重装和失踪转折 |
| 旧训练／时间／提示 | [training.py](../rehab_codex_single_camera_v2_1/app/training.py)、[movement_timing.py](../rehab_codex_single_camera_v2_1/app/movement_timing.py)、[guidance.py](../rehab_codex_single_camera_v2_1/app/guidance.py) | 动作证据 + 明确计划 → 组次／节奏／下一步 | 时间因果性、暂停、连续保持、提示取消，不能新增剂量 |
| 会话编排 | [runtime.py](../rehab_codex_single_camera_v2_1/app/runtime.py)、[scene_controller.py](../rehab_codex_single_camera_v2_1/app/scene_controller.py) | 控制命令 + 观测 → 当前场景与保存请求 | 一次主要场景、Context、未保存结果、停止与生命周期 |
| 评估／建议／计划 | [assessment.py](../rehab_codex_single_camera_v2_1/app/assessment.py)、[automatic_plans.py](../rehab_codex_single_camera_v2_1/app/automatic_plans.py)、[training_plans.py](../rehab_codex_single_camera_v2_1/app/training_plans.py) | 最新同作用域评估 + 条件 → 版本化建议／计划／继续资格 | 最新失败、7 天证据、筛查、自评、原 reference、revision 和顺序 |
| 历史可比性／导出 | [longitudinal.py](../rehab_codex_single_camera_v2_1/app/longitudinal.py)、[reports.py](../rehab_codex_single_camera_v2_1/app/reports.py) | 保存快照 → 比较、图表、文件 | 未知条件、具体证据与含义契约分开、缺测断线和导出一致性 |
| v2 证据／协议／组次 | [evidence.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/evidence.py)、[engine.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/engine.py)、[rounds.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/rounds.py) | 有时钟与来源的指标 → 三动作确认／组次 | observed／predicted 区别、准备姿势、epoch、age、缺口和质量独立 |
| v2 正式事实／贡献 | [sessions.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/sessions.py)、[progress.py](../rehab_codex_single_camera_v2_1/app/rehab_v2/progress.py)、[service.py](../mobile_rehab/rehab_v2/service.py) | 幂等操作 + 冻结计划 → 权威事实／贡献／自评／报告 | 相同键冲突、CAS、同事务、晚结果、报告可重建；最新进程／诊断见 17.5.1–17.5.2 |
| 托管录像／作业 | [server.py](../mobile_rehab/server.py)、[analyzer.py](../mobile_rehab/analyzer.py) | 认证上传 → 子进程分析 → job 与 result／error | owner、限额、来源、SQLite／文件对账、进程超时和失败重试 |
| 健身动作 | [fitness.py](../mobile_rehab/fitness.py)、[fitness_analyzer.py](../mobile_rehab/fitness_analyzer.py) | 所选动作 + 关键点 → 往返、节奏、附加观察 | 固定动作阈值、局部遮挡、半次与完整次、不是肌肉发力 |
| 器械运动学 | [barbell.py](../mobile_rehab/barbell.py) | 标尺／跟踪点／质量 + 录像 → 轨迹、导数、外力、功率 | 同平面、采样频率、求导窗口、残差、断跟；质量不代替标尺 |
| 体态 | [posture.py](../mobile_rehab/posture.py)、[posture_analyzer.py](../mobile_rehab/posture_analyzer.py) | 固定视图 + 连续关键点 → 中位数／MAD／覆盖 | 无人／换人片段、解剖标志缺失、异常方向和专业参考 |
| 活动／卧室／安全 | [activity.py](../rehab_codex_single_camera_v2_1/app/activity.py)、[bedroom.py](../rehab_codex_single_camera_v2_1/app/bedroom.py)、[safety.py](../rehab_codex_single_camera_v2_1/app/safety.py) | ROI + 当前可见动作 → 状态、事件、人工响应 | 不可见不算正常，卧床与跌倒区分、误报负担、未解决警报 |
| 银龄支持 | [silver_service.py](../rehab_codex_single_camera_v2_1/app/silver_service.py)、[silver_store.py](../rehab_codex_single_camera_v2_1/app/silver_store.py)、[change_cards.py](../rehab_codex_single_camera_v2_1/app/change_cards.py) | 受权的冻结记录 → 支持／变化卡／人工反馈 | 有界可选任务、作用域、独立存储、不占相机或制造医疗结论 |

### 19.2 健康、管家、调度、手机与基础设施

| 功能／层 | 主要实现位置 | 输入 → 输出 | 改动时必须一起核对 |
| --- | --- | --- | --- |
| 产品统一入口 | [ProductService.ts](../ankang/route1-health-agent/src/product/ProductService.ts) | operation + owner + input → 产品事实与快照 | 当前档案、dataMode、权限、未配置端口 unavailable |
| 对话运行／语义 | [session.ts（AgentRuntime）](../ankang/route1-health-agent/src/runtime/session.ts)、[understanding.ts](../ankang/route1-health-agent/src/engine/understanding.ts)、[elderTurn.ts](../ankang/route1-health-agent/src/engine/elderTurn.ts) | 原话 + 已有上下文 → 接受事实、澄清、回复 | 主语、否定、假设、日期、更正、隐私；调度已复现反例 |
| 事件归一／每日数据 | [events.ts](../ankang/route1-health-agent/src/pipeline/events.ts)、[normalize.ts](../ankang/route1-health-agent/src/data/normalize.ts) | 有来源的事实 → HealthEvent／每日值 | 稳定 ID、单位、UTC／当地日、测次配对、重复与更正 |
| 基线／检测／个人摘要 | [baseline.ts](../ankang/route1-health-agent/src/engine/baseline.ts)、[detect.ts](../ankang/route1-health-agent/src/engine/detect.ts)、[personTwin.ts](../ankang/route1-health-agent/src/engine/personTwin.ts) | 日数据 + 主诉 → baseline／Finding／PersonTwin | 覆盖、来源切换、异常值、状态过滤；score 不冒充概率 |
| 康复只读接入管家 | [rehab_read_tools.py](../rehab_codex_single_camera_v2_1/app/rehab_read_tools.py) | 宿主 scope + 查询 → 已有评估／训练／计划 | owner、source_kind、usage_context、数量边界、不新增事实 |
| 用药／安排／照护协调 | [CareCoordinator.ts](../ankang/route1-health-agent/src/care/CareCoordinator.ts)、[care_host.py](../rehab_codex_single_camera_v2_1/app/product/care_host.py)、[daily_store.py](../rehab_codex_single_camera_v2_1/app/product/daily_store.py) | 原事实 + 明确确认 → 允许写入及逐步回执 | 药物原说明、第三人、歧义时间、倍量、期限、版本及原子幂等 |
| Python／Node 串行桥接 | [backend.py](../rehab_codex_single_camera_v2_1/app/product/backend.py)、[client.py](../bridges/ankang/client.py) | 宿主请求 → JSON 行消息／工具回执 → 结果 | 私有回执队列、超时后核对、无界积压、慢任务阻塞 |
| 语音／OCR | [native_voice.py](../rehab_codex_single_camera_v2_1/app/product/native_voice.py)、[voice_worker.py](../mobile_rehab/voice_worker.py)、[ocr_worker.py](../mobile_rehab/ocr_worker.py) | 受权音频／图片 → 草稿 | 数字／药名错误、大小／时限、本地资源、草稿不等于确认事实 |
| 图片结构化／资料 | [RealImageHealthParser.ts](../ankang/route1-health-agent/src/adapters/RealImageHealthParser.ts)、[ArchiveService.ts](../ankang/route1-health-agent/src/archive/ArchiveService.ts) | 图片服务候选／原件 → 待确认指标／存档 | 同意、原候选、确认来源、owner、文件与记录一致性 |
| 家庭／通知／同步 | [NotificationService.ts](../ankang/route1-health-agent/src/notification/NotificationService.ts)、[sync/protocol.ts](../ankang/route1-health-agent/src/sync/protocol.ts)、[phone_cloud.py](../mobile_rehab/phone_cloud.py) | 分类授权 + 摘要 → 可共享视图／账本／备份 | 不混合三套关系存储、撤销、外发真实回执、digest 与 revision |
| 独立手机算法 | [engine.js](../android_offline/web/engine.js)、[motion.js](../android_offline/web/motion.js)、[barbell.js](../android_offline/web/barbell.js) | MediaPipe + 原媒体时间 → 本地动作／训练／器械报告 | 低频降级、和电脑不同的计次／剂量／求导契约 |
| 独立手机适配／原生 | [local-api.js](../android_offline/web/local-api.js)、[store.js](../android_offline/web/store.js)、[MainActivity.java](../android_offline/src/cn/tele/rehabilitation/offline/MainActivity.java) | 原页面 API → 手机本地状态／媒体／受限原生操作 | 包内实际资源、可信 origin、熄屏／后台、文件持久化和原生超时 |
| 研究训练工具 | [README](../tools/rehab_ml/README.md)、[features.py](../tools/rehab_ml/features.py)、[models.py](../tools/rehab_ml/models.py)、[training.py](../tools/rehab_ml/training.py) | 有许可数据 + 独立标签 → 明确 run 与模型卡 | 分人划分、train-only 标准化、test 不调参、Kinect／RGB 不跨域 |

本轮没有将这些模块合并或统一。建议先建立共享契约和测试向量，再决定哪些计算真正需要共享实现；网络、数据库、手机算力边界不能靠统一函数名消失。

## 20. 给下一轮算法优化留一套判断方法

### 20.1 分开看五类准确性

| 层级 | 问题 | 最小参考材料 | 应报告什么 |
| --- | --- | --- | --- |
| 感知 | 点是否落在正确人和正确位置 | 独立可见点／人物标注 | 点误差、漏点、错人、左右错误、有效覆盖 |
| 测量 | 点变成的角／距离是否是想测的量 | 相同定义与机位的几何／专业参考 | MAE、偏差、重复性、机位依赖；缺测单列 |
| 时间与动作 | 何时离开／到达／回位，算不算一次 | 逐次时间边界和完整／半次标签 | 漏／多计、边界时间误差、错误恢复和提示延迟 |
| 业务判断 | 该证据能否进入汇总／计划／提醒 | 审核过的输入条件与预期决策 | 错准入、错拒绝、解释依据、继续资格和授权一致性 |
| 事实可靠性 | 正确结果是否只保存一次、能否重开 | 事务、回执和故障日志 | 丢失、重复、跨人污染、恢复、派生物不一致 |

五类不能平均成一个“系统准确率”。例如点误差降低，但换人次数增加，整体风险可能更大；只减少警告也可能只是降低有效性要求。

### 20.2 建议的评价公式，不是当前已算出的成绩

以下用于下一轮评测。`ŷ` 是后端输出，`y` 是独立参考；单位必须与被评价指标一致，缺测不得补为 0 后加入误差。

```text
误差 e_i = ŷ_i - y_i
MAE = mean(|e_i|)
Bias = mean(e_i)
RMSE = sqrt(mean(e_i²))

覆盖率 = 输出可评价结果的参考样本数 / 具备参考标签的全部纳入样本数
  同时报告：未输出原因、不同机位／人群的覆盖；不能只报有效片段误差

逐次事件匹配：先冻结动作定义和允许时间误差，按时间一对一匹配
  TP：匹配上的真实完整次
  FP：多计或把半次当完整
  FN：漏掉真实完整次
Precision = TP / (TP+FP)
Recall = TP / (TP+FN)
F1 = 2TP / (2TP+FP+FN)
  分母为 0 时注明无可评价样本，不自动记满分

相位边界时间误差 = 输出边界源时间 - 参考边界源时间
误报警负担 = 误报警次数 / 有效监测小时
  另报离线／无人覆盖时间，不能用大量未监测时长稀释误报

重复提交率 = 额外产生的同一业务事实数 / 被测试的逻辑操作数
丢失率 = 未能查回的已确认提交事实数 / 已确认提交事实数
  原本未确认成功的草稿不计为“已提交丢失”，要另列提交不确定状态
```

绝对误差、覆盖、事件匹配和存储一致性分别统计。对于角度和力学量，还要比较不同速度／机位下的偏差；对长期风险模型，需要真实结局及独立队列，现有规则的分数不能自作训练真值。

### 20.3 每个实验保留这些信息就能追查结果

下面是一份实验模板，不是现有患者记录，也不是当前全部后端对象已经采用的统一 schema。

```yaml
experiment_id: <独立实验编号>
question: <明确到一层，例如“快动作 EMA 延迟是否导致端点时间偏晚”>
scope:
  host: <desktop / hosted_web / apk>
  exercise: <动作与变式>
  view: <实际机位与采集条件>
inputs:
  consent_scope: <允许分析 / 训练 / 分享的具体用途>
  media_sha256: <原片或授权数据指纹>
  reference_sha256: <独立标注或仪器参考指纹>
  participant_split: <按人冻结的 train / val / test>
versions:
  git: <完整源码提交>
  model_and_schema: <权重指纹、关节顺序、坐标定义>
  measurement_and_protocol: <参考轴、基线、完成规则>
  filter_and_sampling: <滤波参数、时间基准、降级档位>
comparison:
  baseline: <原参数 / 原规则>
  candidate: <只改变的内容>
  predeclared_metrics: <误差、覆盖、漏多计、延迟、失败等>
results:
  numeric: <分层结果，未知保持空值>
  failures: <所有失败样本与原因，不删掉坏片>
decision:
  enabled: false
  rationale: <是否满足预先约定条件，是否需要专业复核>
  rollback: <原版本和切回办法>
```

第一轮不必大规模训练：先把肩外展、坐站、康复深蹲的准备、完整／半次、遮挡、换人、暂停和保存链跑成可重复的后端用例。确认参考定义、数据和时间可信后，再比较自适应滤波或同域质量模型。这比先扩大模型、然后凭几个成功演示调整阈值更容易判断真实改善。

<a id="backend-handoffs"></a>

## 21. 优化时逐跳追查：信息怎样接上、错误怎样传下去

这一节把前面的模块串成可检查的交接表。表中的现有链路来自源码；“建议增加”没有被本轮实现。不要仅凭最终页面的一个数值反推上游全部正确。

### 21.1 康复链：每一跳需要交接什么

| 交接 | 实际传递的信息 | 下游怎样使用 | 信息错误／缺失会造成什么 |
| --- | --- | --- | --- |
| 档案／输入配置 → 采集 | participant、动作、侧别、机位、来源／情境、Context | 决定当前测谁、测什么、哪个输入可以进入当前任务 | 同名动作但不同人／侧别；旧画面被当新任务 |
| 采集 → 姿态 | 帧 seq、源时间／time_basis、接收时刻、图像尺寸、Context、原图 | 解码、模型推理、跟踪；原时间供动作节奏使用 | 用处理耗时当动作时间；尺寸／镜像变化而契约未变 |
| 姿态 → 指标 | 当前人的点／置信度、track_key、骨架与模型、坐标／预处理契约 | 焦点延续、因果滤波、必要点检查、几何公式 | 错人、左右错误、点序错误，仍可能输出平稳角度 |
| 指标 → 协议 | value／unit、valid／reason、观测时刻、年龄、必要点与来源 | 准备、起点、离开、转折、返回；质量与主计次分别处理 | 把缺测补 0°、把预测当观测、跨缺口累积驻留 |
| 协议 → 指导 | 已确认相位、下一步指令、校准 epoch、证据引用、有效期 | 告诉用户接下来做什么；阶段变化后取消旧提示 | 当前状态描述冒充下一步；旧提示继续播报 |
| 协议／训练 → 持久化 | 已确认逐次、部分次、幅度／节奏／质量、冻结配置／计划、结束原因 | 原路径保存 session；v2 保存正式事实与唯一贡献 | 内存计次与历史不同；同一训练重试后重复贡献 |
| 保存评估 → 身体汇总 | 同本人／来源／情境的最新结束评估、动作侧别、契约和状态 | 判断该槽位已评估／不可用／尚未评估 | 挑最好成绩，或把最新失败回退为旧成功 |
| 汇总／筛查 → 建议与计划 | 原评估引用、有效覆盖、观察次数、本人限制、筛查与规则版本 | 原规则决定是否给建议、范围内目标、组次和休息 | 一项角度被误当病种诊断；忽略适用条件而给训练 |
| 保存计划 → 训练 | plan_id／revision／entry_key、冻结参考、剂量／节奏、明确确认 | 原绑定校验和训练执行；v2 宿主目前只接肩外展／坐站 | 修改计划后，旧结果被错误算入新版本；深蹲协议存在但计划入口不支持 |
| 训练事实＋自评 → 进度／下一项 | 原计划引用、完成组次、来源、独立疼痛／疲劳反馈、最新尝试 | 原完成与继续规则；v2 唯一贡献按 ordinal 查询 | 漏自评当 0；换计划绕过不适；质量与完成含义混淆 |
| 历史／计划 → 报告／管家 | 保存快照、证据指纹、可比较契约、受权只读范围 | 派生报告与已有事实解释 | 报告失败被误当训练没保存；模型补造不存在的历史 |

原调用位置见 3.5／19.1；v2 的逐帧检查顺序和提交边界见 17.3–17.6。v2 的事实／报告不会自动进入原评估汇总或正式管家工具；需要独立的适配与验收，不能在图中画一条箭头就当已接通。

### 21.2 不同输出需要不同证据，不能共用一个“有效率”

| 想输出的结果 | 最少需要什么 | 当前应保留的限制 |
| --- | --- | --- |
| v2 肩外展主角度／计次 | 所测侧肩、肘的当前有效观测，合法起点与连续往返 | 髋缺失不否定主计次；不是完整临床肩 ROM |
| 肩部肘屈／躯干代偿 | 对应额外必要点、明确配置的限值与连续观测 | 腕／髋缺失只能让对应质量无法评价，不能报告“没有代偿” |
| 坐站或康复深蹲的膝主指标 | 同侧髋、膝、踝及正确视图、准备／完成协议 | 这些髋点参与三点膝角，不能和肩动作的多余前置条件一起删掉 |
| 连续保持／出回程时间 | 正确源时钟、已观察锚点、连续有效区间 | 缺测／暂停／丢帧不补时间；峰区回顾不等于实时保持 |
| 杠铃速度 | 连续器械轨迹、同平面标尺、可靠帧时间和拟合支持 | 人体关键点清楚不等于杠铃被正确追踪 |
| 杠铃加速度／外力／功率 | 上述条件＋足够求导采样与残差、质量和自由重量条件 | 低频／未标定时不可用；电脑与 APK 门槛不同 |
| 健康趋势 | 合法本人事实、正确时间／单位／来源、足够有效日覆盖 | 检测分数不是患病概率，设备切换可能造成假趋势 |
| 计划可继续 | 正式计划版本、适用证据、原资格规则和实际自评 | 摄像头不能生成疼痛、替代临床诊断或自行加量 |

优化后应同时看“有效片段误差”和“全部纳入输入的可用覆盖”。有效率升高可能只是条件放宽；误差变小也可能只是拒绝了更多难样本。两者不能分开评价。

### 21.3 v2 控制、计算和保存的先后关系

下表只描述当前默认 JPEG 后端，不套用到原 Runtime 或 APK。

| 阶段 | 宿主实际行为 | 为什么这样安排 |
| --- | --- | --- |
| 创建 | 先查幂等请求，再校验同意／容量／本人计划，冻结参数和 source_epoch | 重试找回旧结果，不重新发明一份计划 |
| 接收 | 验证 JPEG 和当前会话；保存 accepted 序列；最多保留一个待处理帧 | 接收与处理分开；旧帧覆盖也留下原因 |
| 推理前 | 核对最终状态、control_epoch／terminal_epoch | 已结束或已过控制边界的待处理帧不能继续消费 |
| 推理 | 所属进程只做解码／原 YOLO，返回绑定 ticket／Context／seq／源时间的姿态 | 子进程不持有数据库或训练业务状态 |
| 推理后 | 宿主再次核对最终状态与 epoch，之后才运行 EvidenceAdapter／EMA | 暂停／恢复期间的晚结果不污染新滤波状态 |
| 规则与检查点 | 指标证据 → 协议／组次 → cue → SQL checkpoint | processed 和内存计次必须有对应保存路径；诊断与证据分开 |
| 结束 | 冻结接收高水位，最多等待 2 秒收尾，保存最终事务后取消所属在途推理 | 慢推理不无限挡住结束；晚返回不能改最终事实 |
| 报告／反馈 | 默认所属进程只构建派生报告；宿主核对事实／身份，写入时校验独立反馈revision | 老报告不能覆盖较新反馈；失败不撤销最终训练 |
| 关闭 | 请求所属推理／报告停止，等待消费者与准确所属进程退出；未确认保留存储／lease供重试 | 不在还可能写SQL或本地构建函数未返回时假称资源已释放 |

本次默认报告已采用17.5.3的有界所属进程；调度线程和SQL权威不移入子进程。显式本地callable钩子仍不能硬强杀；真实磁盘满／损坏、OS创建硬截止与压力测试仍待做，不因报告隔离而声称整套系统都已可靠。

### 21.4 健康与照护链：别让语义错误变成可靠保存的错误事实

| 交接 | 必须一起传的信息 | 当前实现／需要专测的点 |
| --- | --- | --- |
| 原输入 → 理解 | 本人／第三人、已发生／否定／假设、时间、更正、隐私意图 | 本地理解与可选 LLM；人物、歧义时间、倍量已有黑箱反例 |
| 理解／设备／确认图片 → HealthEvent | 类型、值与单位、稳定 ID、来源、时间、可见性和复核元数据 | 不把 OCR 草稿、未知时间、未确认候选直接当事实 |
| 事件 → 每日值／基线 | 原读数、日归组、同测次身份、覆盖与来源 | 当前多数日值取最新；时区、血压配对和来源混合需专测 |
| 基线／症状 → Finding | 规则版本、变化方向、有效窗口、证据 ID、严重度 | 不把类别计分变成患病概率；主诉状态过滤需对照 |
| Finding／记录 → 家庭输出 | 每条证据的分类授权、关系状态、可共享摘要 | 本地可见、已投递和真正送达分别记录；不给整库 |
| 原药物／安排 → 调度提议 | 本人 scope、对象／时间、期望原事实、期限、请求身份 | prepare 不写业务；语义判断和业务提交是两层 |
| 明确确认 → 宿主事实＋回执 | workflow／确认凭证、仍有效的原事实、幂等键、逐步结果 | 同事务防重复；事务正确不能修正上游认错人／时间 |

一个后端可以做到“提交可靠”，同时“提交内容错误”。所以用药／调度优化要单独测误写、澄清和错误对象，不能用幂等测试通过来替代语义正确性。当前正式前端的调度确认卡片也尚未接通。

### 21.5 建议建立的最小诊断账本

以下是优化时建议采集的字段，不是宣称整个项目已有统一日志系统。现有 v2 已有有界会话诊断；原 Runtime、上传作业、产品桥接与 APK 仍要分别核对。

| 账本 | 建议保留什么 | 能回答的问题 |
| --- | --- | --- |
| 输入身份与契约 | 脱敏记录 ID、scope、模型／骨架／坐标、机位、时间基础、采样档位 | 这次是否与上次测同一类量，跨端是否可比较 |
| 逐指标有效性 | 主／辅助指标、有效样本数、连续片段、缺测原因计数、年龄分布 | 是模型漏点、必要点错误、过期，还是规则拒绝 |
| 状态边界 | seq／源时间、准备／校准／相位、缺口、换人、控制 epoch | 为什么少计第一下、为何半次不算、何时应该提示下一步 |
| 提交与派生 | operation key的安全引用、权威 receipt／digest、报告状态、反馈 revision、贡献引用 | 是否已保存、能否重试、报告／进度为何不一致 |
| 性能与生命周期 | 排队／解码／推理／规则／提交耗时，丢帧、backlog、资源释放确认 | 准确性下降是否来自低频、过期、积压或失效消费者 |

正常诊断不要存凭证、原图、完整骨架、原始私密对话。实验原片／标注需另有授权与受限存储，不能因“便于调试”全塞日志。现有 v2 的 diagnostics 是运行态有界统计，重启后可能不可用；权威历史应查 SQL commit，而不是统计缓存。

### 21.6 讨论优化时，可以先回答这六个问题

1. 你要改善的具体输出是什么：点、角、次数、节奏、质量、计划资格、语义或提交？不要只写“提高准确率”。
2. 该输出真正依赖哪些点、时间和业务事实？先按 21.1／21.2 把多余依赖与必要依赖分开。
3. 参考答案从哪里来，是否和输出同定义、同单位、同机位？是否允许分析／训练，是否独立复核？
4. 错误出在模型还是规则？使用 18.1 的三条回放链，保留未知和坏样本。
5. 更改一层后，下游旧记录、计划、提示和跨端比较还能否按原含义使用？必要时升级契约，不回写旧事实。
6. 是否同时改善误差、覆盖、延迟和故障恢复？先写验收指标与回退条件，再调整阈值或训练模型。

优先级建议仍是：输入／身份／时间 → 指标与准备协议 → 计次／提示 → 可靠提交／计划绑定 → 授权同域数据与质量模型。健康和照护的语义错误另列工作流处理；本轮没有实施这些建议。
