# Product UI v1：Pre-UI 盘点（2026-10-02）

本文为首次 Pre-UI 基线盘点。随后用户授权审阅产品逻辑并补齐 UI 接口；最新页面与完整能力归属见 [UI 覆盖审阅](PRODUCT_UI_COVERAGE_REVIEW_2026-10-02.md)。下文“仅文档 / 未改代码”描述的是首次盘点时的状态。

UI分支：codex/product-ui-v1，从已推送并通过验收的main `fb113ff36b694e379548ded2b48137fca34581ae` 创建。该分支当前只新增本文档；未改UI代码、assets、theme、后台功能或Agent语义。等待用户下一轮视觉设计要求。

## 页面结构

正式入口：app/main.py → app/ui/product_window.py。以下路径相对rehab_codex_single_camera_v2_1；ProductService路径相对ankang/route1-health-agent。左侧7项主导航，顶部当前用户/新建用户/通知/设置；底部“我需要帮助”。正式外壳1440×940，最小1180×780，侧栏216px。

| 页面 | 当前结构/控件 | 实际业务来源 | 当前截图 |
| --- | --- | --- | --- |
| 首页 | 日期/目标hero；康复、用药、待办、记录4卡；计划表、待办确认、健康摘要 | ProductService.snapshot + rehab read tools | home.png |
| AI康复管家 | 状态文字、QTextBrowser聊天、3个快捷问题、QPlainTextEdit输入、不记录开关、发送 | ProductService.chat → Runtime/rehab-model/read tools | assistant.png |
| 康复 | 身体评估/训练中心/身体档案/康复记录；个人康复信息；嵌入原MainWindow | 原Runtime/command bus/CameraManager/SQLite | rehab.png |
| 健康 | 状态与指标tab：Twin摘要/concerns、指标表和手动录入；档案与附件tab：文件表、图片候选确认 | snapshot、health.record、ArchiveService、image.parse/confirm | health.png（第一tab） |
| 用药 | 结构化药物表、添加/编辑/停用恢复；今日核对与记录漏服 | MedicationService、Care Tasks、原漏服理解 | medication.png |
| 家庭 | 联系人；本机邀请码绑定；授权/撤销/解绑；家属摘要 | FamilyService、projection、family.summary | family.png |
| 历史与报告 | 统一历史tab；报告与趋势tab；原康复历史入口、报告导出 | healthHistory、report/metricTrend、原康复history | history.png（第一tab） |
| 通知 | 台账表、建立台账、确认所选、共享审计 | NotificationService和本机audit | notifications.png |
| 设置 | 健康资料/目标、本机目录、备份/限定清除、能力说明 | ProductService和local lifecycle | settings.png |

其他既有窗口：首次健康建档、药物编辑、联系人/健康资料、本人清除确认、图片/附件选择与导出、SOS联系信息；康复侧participant、评估清单、计划库、automatic plan、反馈、报告/历史、输入设置、相机测试及远距离指导。隐藏开发者Key入口Ctrl+Shift+D，沿用遮蔽/工作区外存储，不改为正式主导航。

康复处于CONNECTING/PREVIEW/ONLINE/SAVE_FAILED时，离开其页面仍受业务门禁；UI阶段不能为导航顺畅而取消结束/保存/输入释放或误认任务结束。

## icon / assets

正式应用assets当前tracked共18份：

- assets/ui/ankang：9个24×24 SVG（home、assistant、health、medication、messages、profile、report、space、tasks）；统一无填充，描边#285e52、宽1.8、圆端/圆接。7项导航实际使用home/assistant/tasks/health/medication/profile/report，QIcon显示20px。messages/space保留，不据此恢复空间产品功能。
- assets/ui/check.svg、chevron.svg：原康复控件图标。
- assets/navigation/body-front-v1.png及README：原身体部位导航，插图与部分标注仍带紫色；保留语义和关节交互。
- assets/audio/alert.wav、cue.wav：原声音提示，非新增音效。
- assets/exercise-guides/README.md：素材合同。当前没有tracked的逐动作示范图片/视频；缺图文字继续诚实显示，不能将人体导航插图当动作示范。
- assets/models/manifest.json、landmarks-manifest.json：模型来源/合同；模型权重为外部运行依赖，不作为UI资源，不入Git。

ankang/route1-health-agent/design-demos的HTML/PNG、React组件/CSS，以及docs/images中的旧康复截图均是reference/history，不是当前PySide6实现或当前首页截图。下一轮不从参考截图推断业务已实现。

## theme / style

- app/ui/product_theme.py：PRODUCT_STYLE，当前绿白视觉；背景#f4f7f5、主色#285e52、正文#243b34、次要文字#708177/#768980、卡片白底与#e1e9e4边界；Microsoft YaHei UI；正文14px、导航15px、标题26px、section18px、数据值23px；卡片半径14/16px、按钮8/10px。
- app/ui/theme.py：原康复原生QSS，原基调紫色、正文15px及大量专属objectName；正式外壳以rehab_product_style重映射其颜色，没有替换几何/业务。
- app/main.py：Fusion、Microsoft YaHei UI 10pt，离屏QA补载Windows中文字体。原控件、HTML富文本、QTableWidget/QTextBrowser、内联style、图像资产并非全都受一份QSS控制。
- app/ui/product_dialogs.py及原ui/dialogs.py等：原生对话框与输入控件，尚未进行统一视觉修整。本轮不改。

## 当前截图与可见问题（观察，尚未设计）

本轮从main完全相同的产品代码，用真实ProductWindow/Runtime/Node bridge、隔离SYNTHETIC MAIN TEST资料生成并查看9页截图，1440×940。路径：qa-output/pre-ui-20261002/{home,assistant,rehab,health,medication,family,history,notifications,settings}.png；overview.png为本机9页联系表。截图、生成脚本和TEST库都是ignored QA产物，未commit、未push，非遗漏产品成果。

| 观察位置 | 当前可见问题/待设计范围 | 需要保持的边界 |
| --- | --- | --- |
| 全局 | 顶部用户框固定宽度，较长SYNTHETIC名称被截断；字号/按钮/次要说明的密度不一致 | 不改变owner切换/隔离 |
| 首页 | 空计划仍呈现大块空表，待办确认区域也占较大面积；hero和摘要层级可再统一 | 空数据仍明确未知/未记录 |
| 管家 | 大面积空聊天框，状态说明很小；快捷问题/输入/发送层级有待统一 | 不改对话语义、主回复/回执/隐私及no_record |
| 康复 | 外壳绿色与人体图/局部标注紫色并存；产品与旧工作区有两层标题/工具导航 | 身体部位/侧别/动作、相机状态及训练门禁保持 |
| 健康 | Twin目前以多项文字字段呈现，concerns/指标空表占空间；两个tabs的阅读节奏有待统一 | 不把未知显示正常；图片仍先候选后确认 |
| 用药 | 无药物时保留大空表；新增/编辑/停用按钮主次需统一 | 不改变药物状态、历史及每日任务规则 |
| 家庭 | 绑定、授权和解绑并列，流程层级需要视觉整理；空摘要框较大 | 绑定不等于授权，撤销始终有效 |
| 历史/通知 | 空表和审计块占大面积，健康历史与康复历史路径并存 | 保留来源/缺测、台账接受/送达/确认的区别 |
| 设置 | 全路径开发信息较长，能力说明偏技术文字；备份与限定清除层级待整理 | 不能隐藏真实保存/配置/不可用状态 |
| 配置相关提示 | 家庭/通知页使用“本轮/当前未启用”静态说明；未来UI应核对实际extensions.status与配置一致性 | 不提前宣称Voice/WebRTC/HealthKit/外部渠道在线 |

本轮尚未做：其他窗口/第二tab逐个截图、1180×780和高DPI/远距离可读性、真实用户操作评测。原React手机语音对话框首屏布局失败已记录于扩展验收，保留作参考；不以它作为PySide6本次启动失败，也不在本轮修React UI。

## 后续工作入口

当前已经可以进入UI阶段。下一轮按用户提供的视觉要求工作，只改现有产品呈现、图标/资产与必要交互表达；不扩后台功能、不引入第二套Agent、不改相机/训练/数据授权语义。此次只完成盘点，到此停止。main基线、stage1和完整验收见docs/validation/MAIN_INTEGRATION_ACCEPTANCE_2026-10-02.md。
