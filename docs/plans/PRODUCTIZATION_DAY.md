# 居家康复助手：正式产品边界与用户逻辑

2026-10-02；`codex/rehab-agent-stage1`；不合并 main。

## 阶段 1：归属与调用

`ankang/route1-health-agent/src/product/ProductService.ts` 是正式产品业务入口；领域实现保留原位，不复制。`scripts/product-local-store.cjs` 实现本地持久化端口；现有 `agent-bridge.cjs` 和 `bridges/ankang/client.py` 增加 product 操作；`app/product/backend.py` 在独立串行线程调用同一 bridge。康复仍由原 Python Runtime / Storage / CameraManager 负责，模型只使用原 rehab-model，不恢复旧 Python Agent。

| 保留能力 | 唯一业务实现 | 正式产品接口 |
| --- | --- | --- |
| Runtime、多轮、健康自报、隐私、不记录、纠正、家庭事实 | runtime/session、turn；engine/privacy、correction；pipeline/events | chat、snapshot |
| 基础 profile、当前状态、康复目标、联系人 | profile/ProfilePersistence + 产品资料；原 participant ID 对应 ownerId | profile.list/save、emergency.contacts |
| HealthEvent、健康指标、detection、Person Twin | pipeline/events；runtime/derive；personTwin/readPersonTwinProduct | health.record、snapshot |
| medication、今日用药、漏服、Care Tasks | MedicationService、medications、runtime/careTasks、原聊天漏服规则 | medication.save/status、task.status、chat |
| 家庭关系、绑定、共享、授权、家庭事实、摘要 | FamilyService / projection；healthHistory；dashboardStatus | family.invite/bind/grant/revoke/unbind/summary |
| 档案、附件（含图片和视频文件） | ArchiveService | archive.save/read |
| 图片识别与确认 | RealImageHealthParser、HttpVisionProvider、imageNormalizer、HealthEvent pipeline | image.parse/confirm；服务未配置时明确不可用 |
| notification、确认、审计 | NotificationService、notify、sharingAudit；产品宿主审计端口 | notification.plan/ack、snapshot |
| reports、trends、历史时间线 | healthHistory、metricTrend、engine/report；原康复 Storage/read tools | snapshot、lifecycle.export |
| 本地生命周期 | owner/mode 分区；真实本地文件端口；原康复 SQLite 独立保留 | lifecycle.export/clear |
| 品牌/icon | 原 MobileTabBar 的 SVG 图形；现有康复导航素材 | PySide6 原生图标资产 |

直接保留：以上业务规则和存储授权边界。保留能力但重写交互/文案：React 首页、聊天呈现、药物表单、档案、家庭摘要、任务和报告。淘汰出最终产品：固定假数据 seed、DemoImageHealthParser/MockVisionProvider、DeviceDebugPanel、React-only toast/布局、测试捷径和演示剧情；只从产品依赖分离，不删除源码。

保留但暂不启用：语音、Home Twin / Route2 / 3DGS、HealthKit、特殊硬件、跨设备同步及外部通知 transport。SOS 保留联系信息与原安全提示，不伪称已拨号、已通知或已送达。家庭绑定本轮是同一本机的关系与授权流程，不是云账号身份认证。Ankang 没有独立视频健康识别器；视频文件归附件，康复视频重放和摄像头继续复用原实现。

补充产品价值：私密/不记录模式、纠正回执、数据来源/时间、已绑定与已授权分离、通知失败台账、任务完成史、附件确认前不入健康指标、空数据未知状态、跨日任务和稳定用户身份。

持久化：产品数据在现有应用 data-dir 下的 product/，按稳定 ownerId / personal-demo 分区，原子替换并保留上一个文件备份；损坏文件读取失败，不静默重建。Care Tasks 的完成状态由宿主独立持久化并回放原 Runtime 更新接口；不改变原 Runtime 的 session-only 语义。清除仅处理本人健康聊天/附件/家庭/通知及其备份，不删除 profile/medication 或康复 SQLite。导出包括本人资料、健康事件、任务、报告和附件字节，不含 API Key。旧浏览器无可靠 owner 数据不静默认领。

## 阶段 2：用户逻辑

定位：康复训练 + 健康管理 + 用药 + 家庭照护 + Agent + Person Twin，统一为“居家康复助手”。

角色：本人（资料、健康、用药、评估、训练、共享许可的拥有者）；家属/照护者（经授权阅读摘要、确认通知和协助任务）；康复专业人员（沿用既有人工资料来源与报告协作，不新增账号/远程权限）。本机用户切换是资料上下文，不冒充安全账号登录。

主任务：完成今日康复；核对按医嘱填写的药物；记录身体变化；获取受限管家帮助；让获准家属知道需要关注的内容；回顾报告和历史。

一级导航固定为七项：**首页、AI 康复管家、康复、健康、用药、家庭、历史与报告**。通知与设置放顶部工具入口。康复内分评估、训练、身体档案、训练记录；健康内分当前状态/Person Twin、指标、健康档案/附件。Care Tasks 属于首页与相关页面，不独立一级页面。

关键路径：

1. 首次进入：选择已有康复用户或新建稳定 ID → 基础健康资料 → 当前状态/康复目标 → 可选家庭联系人 → 可选已有医嘱药物 → 保存本机 → 首页。未填可稍后补充，不自动创建正常健康状态、药物或训练计划。已有康复用户 ID 保持一致，不搬动旧记录。
2. 日常：首页查看真实任务/计划可用性 → 用药核对或 Care Task → 康复查看既有评估/自动计划 → 原确认流程与训练 → 原训练反馈及保存 → 首页刷新 → 历史查看结果。没有评估依据时先评估，不由 Agent 新造计划。
3. 健康管理：手动指标或管家健康自报 → 原隐私/主体/纠正规则 → HealthEvent → detection/Person Twin 重算 → 健康页与趋势/报告更新。图片先存附件；配置既有代理并获得本次上传许可后识别 → 展示候选 → 明确确认 → HealthEvent；不把未配置识别或 demo 结果称为真实识别。
4. 不适/特殊：自报 → 原 Agent 安全提示/核对回执 → 合法健康记录与任务 → 本人查看 → 绑定与共享许可核对 → 通知计划和实际渠道状态 → 家属确认。没有渠道时明确未送达。训练安全仍归原 Runtime，不能由聊天自动开始/结束/改处方。
5. 家庭：生成本机邀请码 → 明确绑定 → 单独授权 → 家属摘要按 projection 过滤 → 通知/确认/审计；撤销后当前摘要关闭，历史已发送事实不伪装撤回。绑定本身不授权。
6. 长期：原康复历史/同条件评估趋势 + 健康时间线/趋势 + 用药任务完成史 → 原周报聚合 → 导出本人报告/本地备份 → Person Twin 每次真实数据更新时重算。

数据流：participant ID = product ownerId；康复数据继续在 SQLite，健康事件/药物/家庭/附件在产品端口中分区。聊天和手动指标汇入原 HealthEvent；原 detection → findings → Person Twin / Care Tasks / 报告；家庭读数据必须经过 FamilyService projection；NotificationService 记录计划/渠道结果/确认。图片候选保持会话内，确认才持久化。页面只调用产品接口或原康复入口。

后台能力，不单独做页面：Runtime 队列/多轮上下文、detection、事件归一化、隐私门控、correction、通知去重与派发、存储端口、图片归一化、模型配置。Person Twin 以健康页状态卡呈现，不另建 3D 页面。模型 Key 保持隐藏开发者入口。

## 阶段 3：界面落地原则

原生 PySide6 产品外壳承载七页、顶部用户/通知/设置、首次建档。原 MainWindow 作为康复工作区嵌入，保留评估/训练/校准/保存/反馈门禁；不复制康复业务。产品 I/O 在独立线程，用户切换丢弃过时结果；进行中训练或待保存状态不允许离开监护页或切用户。所有页面明确显示数据不足/错误/未配置，禁止填充假临床数据。

| 已具现页面 | 实际后端 |
| --- | --- |
| 首页 | ProductService.snapshot；Care Tasks、真实已保存康复计划 read tools、药物与健康摘要 |
| AI 康复管家 | 原 AgentRuntime 多轮与 HealthEvent 规则；同一 rehab-model 和三个康复只读工具；本轮不记录 |
| 康复 | 原 MainWindow / Runtime / Storage / CameraManager：评估、训练、身体档案、历史、反馈 |
| 健康 | HealthEvent、detection、Person Twin、指标输入、ArchiveService 附件、原图片 parser 候选确认 |
| 用药 | MedicationService 增改停用、原 medication_check Care Task 完成状态、原漏服自报 |
| 家庭 | FamilyService 本机邀请/绑定/独立 consent/撤销/解绑、授权 projection 摘要、联系人 |
| 历史与报告 | healthHistory、metricTrend、周报、持久任务史、康复 read tools 与原历史/评估趋势入口、报告导出 |
| 顶部通知 | NotificationService 台账、未启用渠道结果、确认、共享审计 |
| 顶部设置 | profile、目标与状态、本人导出/范围清除、当前能力与数据位置 |

当前缺口：视觉细修；本机标准 .venv 安装；已有图片代理实际部署与真实图像验收；外部通知渠道；云家属身份与跨设备同步。没有新增临床规则、处方或实时硬件能力。康复完整历史/评估趋势继续通过已有入口查看，统一历史页中的康复摘要仅使用现有只读工具的最近记录，不声称已聚合所有旧评估。旧浏览器资料未自动迁移，避免没有身份依据的数据认领。
