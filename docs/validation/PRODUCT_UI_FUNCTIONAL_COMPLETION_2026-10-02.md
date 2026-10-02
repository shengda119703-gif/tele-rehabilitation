# Product UI Functional Completion 验收与完整能力归属

本轮在 `codex/product-ui-v1` 完成产品逻辑接线，起点为 `5a17d4bcf00e2180b890206e5f2c572ba92ba477`。main 保持 `fb113ff36b694e379548ded2b48137fca34581ae`，stage1 保持 `4b2d108a3003d84c89ac42da25580017d5b1de17`。最终交付 SHA 见本轮 Git 提交和交付汇报，不在提交自身内自引用。

依据：用户的《居家康复助手前端产品逻辑（PC端）》、[前轮覆盖审阅](../plans/PRODUCT_UI_COVERAGE_REVIEW_2026-10-02.md)及现有仓库实际实现。参考文档的示意数据、未来功能不作为实际后台能力。本轮没有改变主题、颜色、图标或品牌，没有修改 Agent 语义、训练算法、数据库结构或引入新云服务。正式入口仍是 `run_app.py / app.main → ProductWindow`。

## 页面、按钮、实际动作与反馈

产品操作经 `ProductBackend` 的串行工作线程调用现有 `bridges/ankang/client.py → ProductService`；原康复与银发继续经原 Runtime / command bus。文件读写也在工作线程中完成，不在 Qt 主线程读取附件或导出备份。下表的内部名称仅用于开发审计，不作为普通用户页面名称。

| 一级页面/入口 | 二级页面 | 主要新增或保留按钮 | backend / action | 用户反馈 |
| --- | --- | --- | --- | --- |
| 首页 | 今日控制台、下一项训练、今日任务、健康摘要 | 继续训练、查看今日任务、查看用药、查看健康状态、问康复管家、查看训练计划、确认完成、暂不处理、建立/编辑资料、管家摘要 | 原训练中心/计划库/自动计划；页面跳转或侧栏；task.status；profile.save | 明确空状态、当前真实完成次数、下一项及累计进度；无日排期时说明；任务成功/失败后刷新 |
| AI 康复管家 | 对话、参考数据、附件、语音 | 发送、推荐问题、添加附件、识别图片、语音输入、朗读、停止语音、去康复页面、清空/新会话 | chat；archive.save；image.parse；voice.input/output/cancel；页面跳转 | 同一 owner/scope/会话；有配置才启用外部能力；真实回复或错误；新会话明确禁用 |
| 康复 | 今日训练、康复评估、训练计划、康复进度 | 继续训练、查看动作、开始训练、新评估、评估详情、身体档案、计划库、自动安排、计划详情、训练详情/反馈、评估变化/完整历史、报告、个人康复信息、银发健康守护、收起/展开概览、返回首页 | 原训练/评估工作区、Runtime.start、body_profile、training_plans、automatic_proposal/accept/prepare、report、training_review/save_training_feedback、history、SilverDialog | 保留输入/评估依据/计划确认/保存门禁；没有来源或计划时不假启动；原结果/错误；最小窗口可收起概览留出操作空间 |
| 健康 | 当前状态、健康记录、健康档案、设备 | 手动记录、记录感受/更正、分类、详情、基础资料、添加资料/图片/视频、导出附件、图片识别/确认、连接/导入、设备文件导入、已配置设备读取、Apple Health 导入/诊断、查看数据、刷新状态、摄像头/回放设置 | health.record、chat；HealthEvent/twin/detection 只读投影；archive.save/read；image.parse/confirm；device.import/pull；healthkit.import/diagnostics；extensions.status；原输入设置 | 用户可读摘要及时间线；不显示 Twin JSON；文件用户/单位/来源校验失败不写入；附件保存不等于识别；设备状态真实 |
| 用药 | 今日用药、我的药物、用药历史、漏服记录 | 今日详情、本人确认今日用药已核对、记录漏服、逐剂标记（禁用）、新增/编辑/查看、停用/恢复、历史/漏服详情、返回首页 | medication.save/status；task.status；chat；既有药物/任务/事件只读模型 | 按已有医嘱信息；停用需确认；写成功后刷新；无药/无历史明确提示；不虚构逐剂服药记录 |
| 家庭 | 我的照护圈、成员详情、当前允许查看范围、家属摘要、共享记录；原活动照护/家庭回应窗口 | 查看成员、编辑联系人、SOS、邀请码、绑定、允许长期共享、撤销、解绑、刷新家属摘要、共享记录、临时/逐字段授权（禁用）、银发家庭回应 | profile.save；emergency.contacts；family.invite/bind/grant/revoke/unbind/summary；原 Runtime.silver | 绑定与授权分开；共享/撤销/解绑先确认；私密信息不进摘要；只显示联系电话，无自动拨号/救援成功 |
| 记录 | 统一历史、报告与趋势；分类为全部/康复/健康/用药/评估 | 分类、详情、趋势、报告、导出筛选记录、导出健康报告、原完整康复历史 | full scoped rehab UI readers、HealthEvent/taskHistory；原 longitudinal_history/report；health report/trends；ui.file.write；原 export/export_longitudinal_history | 所选康复记录进入原报告/可比条件趋势；健康进入原健康报告；失败不补曲线、不声称临床改善；导出完成/失败有回执 |
| 顶栏通知 | 全部、未确认、已确认、通知详情、共享记录 | 建立台账、确认所选通知、打开通知、进入对应业务 | notification.plan/ack；既有 NotificationService 台账及审计；健康/用药跳转 | 有时间、类型、确认状态和渠道状态；建立台账前确认外部发送；未配置渠道明确不可用；接受不等于送达 |
| 顶栏设置 | 个人资料、数据与隐私、家庭共享、设备与同步、通知、开发者设置 | 编辑资料、本人备份、清除本人数据、家庭共享、同步连接/状态/收取/发布/断开、设备页、刷新连接状态、通知页、开发者配置、返回首页 | profile.save；lifecycle.export/clear；sync.start/status/poll/publish/close；extensions.status；已有工作区外 DeepSeek 配置 | 清除前确认并列明范围；保留药物档案及原康复记录；未配置远程连接不启用同步；发布共享数据须确认 |
| 全局 | 不离开当前页的管家侧栏；Ctrl+J | 问康复管家、发送、本轮不记录、关闭 | 同一 chat；原不记录合同；QDockWidget 关闭 | 保留当前页面/采集；两处隐私选项同步；当前页面内容尚未自动进入模型，不伪造上下文注入 |

所有普通页面具有读取中、空数据、错误、成功、条件未满足的状态反馈。写操作在本机队列中执行，UI 禁用重复提交；未选记录有选择提示。跳转保持可返回，回来重新读取。切换用户拒绝在操作/采集中执行，并清空旧任务、健康视图、聊天、未发送草稿、识别候选和详情窗口；原报告窗口也关闭。嵌入的旧历史/报告拒绝不同用户、来源、情境的数据。

## 按钮逐项审计

- [正式产品按钮清单](PRODUCT_UI_BUTTON_AUDIT_2026-10-02.csv)：116 个静态用户按钮，489 次页面/二级页可见观察，逐个列出页面、A/B/C/D、动作和反馈。默认无配置时 C 明确列出原因；同一按钮在数据或配置变化后可转为 A/D。
- [原康复及银发按钮清单](PRODUCT_UI_ORIGINAL_BUTTON_AUDIT_2026-10-02.csv)：165 个页面/按钮组合，192 次可见观察，包含目录、实际评估/训练工作区、身体档案、历史、计划库、自动计划及银发四个页签。每个观察按钮的 clicked 均有实际连接；不能只凭连接数宣称业务可用，配合原回归与下列实际路径验证。原未选报告和银发忙碌/空选项的静默返回已补成提示。

动态详情和表单的按钮另有明确合同：

| 动态窗口 | 用户按钮 | 分类及实际动作/反馈 |
| --- | --- | --- |
| 个人健康资料 | 保存资料、取消 | A：profile.save，真实保存后刷新或错误；B：取消回原页 |
| 药物资料 | 保存、取消 | A：medication.save，新增/编辑共用既有 ID/模型；B：取消回原页 |
| 通用详情 | 关闭 | B：关闭详情回原页面；新开详情先关闭旧详情 |
| 附件详情 | 导出所选附件 | A：archive.read 后工作线程写文件，成功/失败回执 |
| 家庭成员详情 | 允许长期共享、撤销共享、修改联系人、查看家属摘要 | D：确认后 family.grant/revoke；A：profile.save/family.summary，真实结果/错误 |
| 健康记录详情 | 在管家中更正记录 | B：进入已有管家，不直接更改事件 |
| 康复记录详情 | 查看原报告/测量条件/反馈 | B/A：原 Runtime.report → 原报告及训练反馈 |
| 原报告 | 填写训练感受、导出 HTML/JSON/CSV、返回 | A：training_review、export；B：关闭报告；实际路径验证 |
| 原训练反馈 | 保存感受、无疼痛且不疲劳的本人快捷确认、暂不填写 | A：save_training_feedback，明确本人输入；失败保留原填写且不改测量；B：取消；保存中禁止关闭/重复写 |
| 通知详情 | 进入对应业务、本人确认已查看 | B：健康/用药；A：notification.ack，真实回执 |
| 设备连接说明 | 设备文件导入、摄像头/回放设置 | D：文件导入确认及既有校验；B：原输入设置 |
| 原计划编辑/自动安排/评估清单 | 保存、接受/准备、跳过/结束、取消 | 原 save_training_plan、accept_automatic_plan、prepare_automatic_item、create/change_assessment_batch；保留原验证与错误反馈，不复制业务规则 |
| 开发者配置 | 保存/取消及已有凭据管理 | 沿用工作区外配置；重新连接现有 bridge；不把 Key 放入产品档案或 Git |

本轮未发现仍然没有接线、只有 console 行为或伪成功的正式产品控件。连接审计不等于每个硬件控件的实机操作验收，外部限制见下表。

## 七条连续路径的实际验证

| 路径 | 结果与证据 |
| --- | --- |
| 1 首页 → 继续训练 → 完成 → 反馈 → 首页 | **软件分段闭环通过，实机未验收。** 原 SceneController 在 SYNTHETIC/TEST 中完成评估依据和一次真实引擎训练并保存；同一测量记录经实际 Runtime/报告窗口进入反馈 UI，保存本人 pain=0，再回首页重新读到反馈。测量 summary 未改变。产品中合成来源仍不能打开假相机，不宣称从首页完成了真人摄像头训练。|
| 2 首页 → 今日用药 → 详情 → 返回 | 真实 medication.save 后今日表格可选/开详情，关闭并回首页；无药时无假数据。|
| 3 首页 → 管家 → 查询今天训练 → 康复 | 实际 chat/Node Runtime，显示对话；没有模型配置时明确提示康复查询尚未配置；“去康复页面”进入真实训练中心。不把缺配置的模型查询记为真实 LLM 工具成功。|
| 4 健康 → 添加资料 → 档案 | 实际 archive.save/read，用 TEST 文件存档，进入档案、开详情、导出后字节一致。|
| 5 家庭 → 成员 → 查看/修改允许查看 | 实际联系人保存、邀请码/绑定、family.grant/revoke、成员详情，验证 projection 真正变化；取消敏感确认不提交。|
| 6 记录 → 康复筛选 → 详情 → 趋势/报告 | 隔离库 8 条训练；Agent 工具仍限 5 条而 UI 全部 8 条。所选记录实际打开原 LongitudinalDialog 及 Runtime.report；导出文本一致。另测 9 条同动作历史评估含引导计时：全量显示但引导记录不成为自动评估依据。|
| 7 通知 → 打开 → 对应业务 | 实际检测、通知台账与 notification.ack；确认筛选有效；详情可关闭，跳转健康/用药并可返回。没有外部渠道时台账不可用状态不被称为发送成功。|

## 原康复与 Ankang 保留能力归属

| 正式保留能力 | 页面 → 用户入口 | 最终业务位置 / 边界 |
| --- | --- | --- |
| participant、Body Profile、53 项动作、单项/清单评估、测量条件 | 当前用户、康复信息、评估/身体档案/详情/动作目录 | 原 Storage、assessment、exercise registry、assessment batches；不改测量算法 |
| CameraManager、单/双摄、测试、回放、缺测/隐私暂停 | 康复输入设置、设备页、原工作区 | 原统一相机拥有者；点击才开启；不提交用户视频 |
| 人工/自动计划、版本/归档、接受/准备、训练计数、休息/暂停/恢复、引导计时、大字指导 | 康复四页签 → 原计划及训练工作区 | 原 training_plans/automatic_plans/SceneController/Runtime；不恢复 A1/A2/A3，不允许合成演示真人训练 |
| progress、训练反馈、康复 history/report、条件比较、SQLite、保存失败恢复 | 康复进度/记录/原报告 | 原 read models/report/export/retry；新的 UI 只读适配保留全量当前范围，不改变 Agent 3/6/5 条限制 |
| 银发活动、固定参考变化、家庭回应、整改、主动求助、本机语音 | 康复/家庭 → 银发健康守护四个页签 | 原 SilverStore/Runtime/Qt 语音；本机角色/演示不等于可信远端家庭或救援 |
| Agent Runtime、多轮、understanding/self-report、HealthEvent、correction | 管家/全局侧栏/健康记录详情 | 同一 Node Runtime/bridge，不新建语义规则；rehab tools 仍只读 |
| detection、Person Twin、健康摘要与趋势 | 首页/健康当前状态/记录趋势 | 原推导及读模型，用户可读投影，不暴露 Twin JSON |
| privacy、consent、sharing、Care Tasks、family facts | 管家不记录、家庭允许查看/共享记录、首页任务 | 原隐私/授权/任务规则；“家人近况”等用户词汇；不复制通知业务规则 |
| medication、今日核对、漏服、历史 | 用药四页签 | 原 MedicationService/task.status/medicationMissed；不虚构逐剂流水 |
| family contacts、SOS、binding、sharing/projection | 我的照护圈/成员详情/共享记录 | 原 FamilyService；只有当前一个绑定关系及整体许可，无新增账号系统 |
| archive、attachments、image/video/multimodal/capture | 健康档案、管家资料/图片入口、设备/原回放 | 原 Archive/media/image ports；视频可存档/回放，没有视频健康识别；采集宿主接口与特殊硬件共用既有边界 |
| notification、external webhook/push/channel | 顶栏通知/设置通知 | 原 NotificationService/ChannelPort；配置状态、台账及确认，不称无配置为成功推送 |
| reports/trends/history/local lifecycle | 记录/设置数据与隐私 | 原 read reports/trends、lifecycle.export/clear；清除范围保持原合同 |
| Voice/ASR/TTS | 管家语音控件；原银发本机提示 | 产品 voice ports 已接 UI，默认桌面未注入；原 Qt 本机提示继续保留 |
| Cross-device Sync/schema/冲突验证 | 设置设备与同步 | 原 sync adapters/schema；未配置远程宿主禁用，未应用数据不称为成功同步 |
| HealthKit/权限/导入/mock | 健康设备 → Apple Health 导入/诊断 | 原健康数据源端口；由 iPhone 授权，Windows 不模拟 iOS |
| generic device/hardware | 健康设备 → 文件导入/已配置来源/查看数据 | 原 device.import/pull 校验，进入 HealthEvent/Twin；没有独立厂商驱动不伪装已连接 |
| Python/Node bridge、rehab-model、DeepSeek、ProductService | 管家/各业务动作/开发者设置 | 原桥与读工具，不新增模型 client；配置及运行数据不入 Git |
| React/reference、Home Twin/Route2/3DGS | 源码参考；不作为正式产品入口 | 继续分离保留；空间建模延后，不阻塞当前 UI |

除明确延后的空间建模线外，现有正式保留能力均有 UI 归属，包括原文档没有细写的银发、引导计时、大字指导、条件比较、数据生命周期与外部来源接口。“有归属”包含明确禁用/待接入，并不等于所有外部能力已验收。

## 明确禁用或未验收的能力

| 功能 | UI 状态 | 后续缺项 |
| --- | --- | --- |
| 管家语音识别/输出 | 默认禁用，显示平台未接入；有真实 voice port 才启用 | 原生麦克风/ASR/TTS 宿主；语音不记录和即时取消合同仍需宿主验收 |
| 图片识别 | 未配置服务时禁用，附件存档可用 | 原识别代理/OCR、多模态服务及真实图片验收；识别后仍需本人确认 |
| 新会话/仅清空聊天 | 明确禁用，说明当前无独立 reset-chat 接口 | 已有 Runtime 暂无该写操作；不改为偷偷清空全部健康数据 |
| 逐药逐剂已服用 | 明确禁用，保留每日核对 | backend 暂无逐剂流水写接口 |
| 多成员、逐字段、临时共享 | 明确禁用/说明，仅支持现有总体共享与私密记录 | 正式权限模型/写接口；原银发共享规则分别保留，不与 Ankang 许可混写 |
| HealthKit | 默认未配置，Windows 无 iOS 授权；接入后有导入/诊断 | iPhone 权限、移动桥、真实样本及外部服务 |
| 通用健康设备/特殊硬件 | 文件导入已可用；读取未配置来源禁用；特殊硬件显示无独立厂商驱动 | 实体设备、数据源配置及驱动/协议实测 |
| Cross-device Sync | 默认接口支持但未配置，动作禁用 | 可信远程身份/设备、transport 宿主和真实收发/冲突验收 |
| 外部通知 | 本机台账可用，渠道未配置明确标记 | 真实 webhook/push 服务与实际送达验证 |
| 摄像头训练/双摄/回放 | 原路径保留、现有门禁有效；只枚举不自动采集 | 本轮未打开摄像头或进行真人/双摄/真实媒体测量验收 |
| 视频健康推理、附件自动进入模型、页面上下文自动注入 | 页面明确说明当前范围 | 当前 backend 没有这些正式合同；不为 UI 新增大后台 |
| 今日/每周计划排期与精确计划完成率 | 显示实际今日完成次数、保存计划累计状态，并说明没有日/周排期 | 现有计划没有排期接口；不把累计进度冒充今日比例 |

## 本轮验证证据

1. **48 项针对性测试通过**，83.53 秒：`test_product_completion.py`、`test_product_window.py`、`test_rehab_read_tools.py`、`test_product_navigation.py`、`test_training_ui.py`、`test_training_runtime.py`。使用隔离 ASCII 临时目录和 offscreen Qt；真实 Node 子进程、ProductService、本机持久化读写。最后补充原报告空选项、银发共享确认和忙碌反馈，另 2 项及最终 1 项针对性复验均通过（复验不是新增测试数量）。
2. 新增/覆盖：七路径、无模型配置的诚实状态、保存失败/导出失败、重复写拦截、当前 owner/scope 拒收、草稿与原报告关闭、全量当前范围训练/评估、引导记录不冒充评估、最小尺寸概览收起、正式按钮分类与原按钮接线。没有删断言或用假成功替代服务。
3. **真实 Qt 事件循环启动检查通过**：实际 ProductWindow + 原 Runtime + Node ProductBackend，隔离 TEST 用户；1440×940 与 1180×780 所有页面保持尺寸，各二级页及原计划/银发可打开；查看首页、训练、设置等截图。初始截图脚本手动 pump/QTest 等待使后台首次 cv2 导入不能及时完成，改用真实 QEventLoop 后启动通过，没有移除实际枚举或把 Runtime.busy 清零。
4. QA 截图、观察 JSON、生成脚本与测试数据留在 ignored `rehab_codex_single_camera_v2_1/qa-output/ui-completion-20261002/`，不提交个人数据库或测试产物；CSV 是不含健康用户数据的可审阅控件清单。图像仅检查布局可达性，不开展视觉美化。
5. 本轮未改 TypeScript/Agent 业务，Python 测试实际运行现有 Node bridge；不重复全部历史或 Node 大回归。未请求真实 DeepSeek/OCR、麦克风、iPhone、远程 peer、实体健康设备或真实通知送达。
6. `git diff --check` 通过；tracked 文件未发现 `.env`、`deepseek.json`、SQLite、依赖环境或测试输出。只将应用源码、针对性测试和本报告/控件清单纳入 UI 分支；main 与 stage1 不变。

结论：当前保留的本机软件能力已接入可操作产品路径，外部缺配置/缺平台能力有明确归属与原因。真实硬件和外部服务仍需要独立验收。本轮交付后停止，统一视觉美化等待下一轮要求。
