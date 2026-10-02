# PC 前端产品逻辑与正式产品接口覆盖审阅

后续完成状态：本文件保留前轮审阅的历史基线与当时差距。新的 [Product UI Functional Completion 验收](../validation/PRODUCT_UI_FUNCTIONAL_COMPLETION_2026-10-02.md) 已补全页面/二级页、详情、反馈、确认和原康复路由，并解决下方第8项 UI 历史截断：Agent 的3/6/5条工具限制不变，正式 UI 读取全量当前用户/来源/情境历史；引导计时记录仍不作为自动评估依据。外部接线、逐剂服药、临时/逐字段权限、日周排期等真实 backend 差距继续明确标记，不伪装完成。

审阅依据：用户提供的 `home_rehab_pc_frontend_product_logic.md`，以及 `shengda119703-gif/tele-rehabilitation` 实际源码。文档是审阅参考；示意数字、医学描述、未来功能及视觉实施顺序不自动成为已实现功能或执行授权。本轮按用户要求检查模块覆盖并补接既有接口，不进行视觉重设计、不扩 Agent 语义、不新增训练算法或数据库结构。

基线：main `fb113ff36b694e379548ded2b48137fca34581ae`、UI 分支 `1904654a3a00157daf395c0905fe0045c46b2e5f`。本轮开始时本地与 GitHub 三个已交付分支一致，工作区 clean。在 `codex/product-ui-v1` 开发，不改 main、不合并 stage1。GitHub 网页缓存仍展示旧康复 README，因此以 `git ls-remote` 确认的远端 SHA 与对应本地源码为准。

## 结论

文档七项一级模块齐全，但原 UI 缺少 Voice、设备 / HealthKit、同步等已保留能力的操作入口，也缺少全局助手、管家附件入口与数据参考范围。原银发窗口仍在代码中，但产品隐藏旧侧栏后入口消失。本轮已补接这些入口，统一记录支持筛选，健康和用药增加对应记录视图。

最终保留能力均有正式 UI 归属或复用原康复工作区入口。接口存在不等于外部平台实际可用；默认 Node / Windows 仍未注入语音和跨设备宿主。文档中超出已有业务接口的需求另列下表，不用示意卡片、模拟设备或静态成功提示掩盖。

## 模块覆盖表

下列 PySide6 路径相对 `rehab_codex_single_camera_v2_1/app/`。公共入口为 `ui/product_window.py`；本轮外部接口与全局助手控件在 `ui/product_interfaces.py`。产品请求统一经 `product/backend.py → bridges/ankang/client.py → ProductService`；原康复和银发继续经原 Runtime / command bus，不在页面直接操作底层库。

| 原有模块 / 能力 | 文档是否涵盖 | 正式 UI 位置与实际接口 | 本轮结果 / 边界 |
| --- | --- | --- | --- |
| 当前 participant、健康资料、康复目标 | 有 | 顶栏用户 / 新建用户；设置 → 编辑资料；康复 → 个人康复信息 | 原用户隔离与建档保留，两类档案职责不混写 |
| 首页康复、用药、Care Tasks、健康摘要 | 有 | 首页；snapshot、task.status；继续今日康复 → 原 training hub | 入口直达训练中心；不伪造今日次数、阶段天数或直接跳过训练确认 |
| Agent Runtime、多轮、understanding、detection | 有 | AI 康复管家；chat → 原 Runtime；健康关注摘要 | 原实现复用，不另写语义处理 |
| 自报、HealthEvent、纠正、不记录 / 私密意图 | 有 | 管家输入与不记录选项；健康记录 / 记录 | 增加记录 / 更正入口，仍由原 Runtime 解释和应用；不改事件 ID 或历史 |
| 全局 AI 辅助层 | 有 | 全局“问康复管家”按钮、Ctrl+J、右侧 dock | 新接同一 chat 会话；训练中不导航离开、不停止采集；不记录选项同步 |
| Agent 当前数据参考范围 | 有 | 管家页记录 / 计划 / 评估 / 训练 / 药物 / 今日任务范围摘要 | 新增真实 snapshot 计数；范围不等于每轮实际调用证据 |
| 原动作目录与 Body Profile | 部分 | 康复 → 身体评估、身体档案；原人体导航与动作搜索 | 原 53 项动作、左右侧和可比条件保留 |
| 单项 / 清单评估、结果 | 有 | 原 catalog / workspace / assessment batch / report | 保留原入口和数据，不改有效性规则 |
| 训练计划、计划库、自动计划 | 有 | 康复 → 训练中心；原 saved plan / automatic plan | 保留版本、评估依据、生成 / 顺序 / 适用性确认；合成演示仍非正式患者主流程 |
| 次数、组数、休息、暂停、实时监督 | 有 | 原训练 workspace | 保留真实测量与保存门禁，不新增自动写工具 |
| 引导计时、手动记次、大字指导 | 未明确 | 原 workspace / distance guidance | 入口保留；引导计时不冒充自动测量 |
| 训练反馈、训练进度 | 有 | 原训练结束反馈 / training hub；记录 → 康复筛选 | 新记录视图正确读取 summary.completed 和 training_feedback，不误读不存在的顶层 completed |
| CameraManager、摄像头测试、双摄、输入设置 | 部分 | 康复原输入设置；健康 → 设备 → 摄像头 / 回放设置 | 统一相机拥有者；UI 不自动开相机、不绕过来源与释放确认 |
| 录像回放 / 隐私暂停 | 部分 | 原输入 source 与 workspace | 原媒体时间、缺测与释放规则保留，无第二摄像头实现 |
| 银发活动任务、延期、拒绝、固定参考变化 | 文档漏列 | 康复 → 银发健康守护 | 恢复原 SilverDialog / Runtime 入口 |
| 银发家庭回应、照护整改、主动求助 | 文档漏列 | 家庭 → 活动照护 / 家庭回应 / 整改 | 恢复同一 SilverDialog；不把本机演示称为远程救援 |
| 活动、卧室 / 安全受控场景 | 文档漏列 | 银发健康守护内已有场景入口 | 仍逐场景切换，不假称全屋并行监测 |
| 当前健康状态 / Person Twin | 有 | 健康 → 状态与指标 | 用户标题改为“我的健康”；后台 Twin 投影不改 |
| 健康指标与自报记录 | 有 | 状态与指标 → 手动记录；健康记录 tab | 新增健康时间线；既有 measurement / observation / labResult 复用 |
| 健康档案、附件、图片 / 视频 / 报告 | 有 | 健康 → 健康档案与附件；管家 → 上传资料 | 新增管家入口复用 archive.save；默认私密，不自动给模型读取 |
| 图片识别 / 多模态候选确认 | 有 | 管家 / 档案 → 识别健康图片 → 健康档案候选确认 | 沿用 image.parse/confirm；识别返回后显示候选所在 tab；代理未配则说明不可用 |
| generic capture / video | 部分 | 图片视频附件；原相机 / 回放；已有 submit_capture / media.import 宿主接口 | UI 文件上传复用档案；不新增 Route2 采集或视频健康推理 |
| Voice / ASR / TTS | 有 | 管家 → 语音输入、朗读最近回复、停止语音；voice.input/output/cancel | 补入口与真实 status；默认 Windows 未接线，禁用并说明。ASR 当前无 no_record 参数，私密模式要求使用文字 |
| HealthKit 数据、权限、导入诊断 | 有 | 健康 → 设备 → Apple Health 导入 / 权限状态；healthkit.import/diagnostics | 补接口；日期范围可选；iPhone 请求权限，Windows 不模拟授权；实机未验收 |
| 通用设备：血压、静息心率、血氧、活动等 | 有 | 健康 → 设备 → 文件导入 / 已配置设备读取；device.import/pull | 补接口，JSON owner 必须匹配，使用原校验器和 HealthEvent / Twin 链；默认无真实设备 |
| 特殊硬件接口 / bridge | 有 | 健康 → 设备，共用注入的数据源和已保留 CaptureSource | 上游无独立雷达 / BLE / 串口驱动；不凭空新增厂商入口或宣称实机验收 |
| 跨设备 schema、收件、验证 / 冲突状态 | 有 | 设置 → 连接、状态、收取、发布、断开；sync.* | 补 UI，按实际宿主状态启用；接收后重新读取 snapshot；未应用数据不称为同步成功 |
| 药物档案、编辑、停用 / 恢复 | 有 | 用药；medication.save/status | 原实现保留 |
| 今日用药、漏服、用药历史 | 有 | 用药 → 今日核对 / 漏服 / 历史；task.status、chat、taskHistory | 新增历史 / 漏服视图，按既有 medicationMissed 标签分类；非逐药逐时点服药流水 |
| 家庭联系人、SOS | 有 | 家庭 → 联系人 / 紧急联系人；全局我需要帮助；emergency.contacts | 家庭页补明确入口；只有联系信息，没有自动拨号 / 发送 |
| 绑定、consent、privacy、sharing、撤销、family facts | 有 | 家庭授权 / 解绑 / 家属摘要；管家；设置 → 家庭共享 | 原 FamilyService 门禁保留；新增设置转入口；不把绑定当授权 |
| 统一历史、趋势、报告 / 导出 | 有 | 记录 → 全部 / 康复 / 健康 / 用药 / 评估；报告与趋势 | 新增筛选；健康趋势用原读模型；康复完整趋势 / 条件比较 / 报告仍可进入原历史 |
| NotificationService、ack、共享审计 | 有 | 顶栏通知 → 台账 / 确认 / 审计 | 单一通知规则，未新增另一套提醒后台 |
| webhook / push / channel 状态 | 有 | 设置通知状态 → 通知台账；notification.plan | 改为读取 extensions.status 的实际配置，接受 ≠ 送达，未配置也可建立本机台账 |
| 本地数据生命周期、备份、清除、SQLite | 文档未完整列出 | 设置 → 导出备份 / 明确范围清除；lifecycle.export/clear；原康复 storage | 保留，不扩清除范围，不提交用户数据库 |
| Python / Node bridge、rehab read tools、DeepSeek | 部分 | 管家 / 康复实际调用；Ctrl+Shift+D 开发者配置 | 已接 UI；无第二套模型 client，密钥仍在工作区外 |
| icons / assets / theme | 有 | 原 product_theme / assets / 原康复样式 | 本轮不美化、不新增素材 |
| Home Twin / Route2 / 3DGS 及依赖空间推理 | 不属于本轮目标 | 原始 reference 保留，正式 UI 不开启 | 明确继续延后，generic capture 不等于开启空间主流程 |

## 文档与现有后台的真实差距

这些差距不是本轮丢失了已有实现，也未被补成新的后台功能：

1. **逐药 / 每次服药核对**：现有 ProductService 按每日 medication_check task 记录。不能显示虚构的“药 A 08:00 已实际服用”或药物完成百分比。药物时间仍是已有自由文本。
2. **逐个家属、逐字段 / 临时授权**：当前一个 familyLink 与总体共享许可，加上既有私密记录 / family facts 语义。文档示意的多成员细粒度权限编辑尚无正式 ProductService 操作，UI 只呈现真实范围。
3. **AI 执行康复写操作 / 自动开始下一项**：rehab tools 仍只读。首页直达原训练中心，原确认、来源、适用性和保存门禁保留。不会从首页自动开启相机。
4. **统一 Today Tasks 和真实今日康复完成比例**：首页保留康复安排、用药任务及其他 Care Tasks，但没有跨域统一调度器；已保存计划数不能冒充今日计划完成数。没有依据时不显示计划第 18 天 / 2/4 等示意值。
5. **页面上下文进入模型**：侧栏显示当前页面，用同一 owner / scope；当前页面像素、控件状态和 82° 解读上下文未自动注入模型。这需要后续明确上下文合同，不在 UI 拼接隐含提示改变 Agent 行为。
6. **附件自动作为模型输入、拍照 / 实时录制健康资料**：当前上传存档及图片候选确认已有，视频用于档案与康复回放；没有视频健康 parser。UI 不另开摄像头或把档案上传等同多模态推理。
7. **语音、Sync 原生桌面宿主和外部配置表单**：本轮提供入口、真实状态与不可用原因，不实现新的 ASR / WebRTC。HealthKit / webhook 沿用已支持宿主环境配置，不在设置页保存服务 token。服务配置名见扩展验收文档。
8. **完整无限期统一时间线**：现有 snapshot 的康复读工具限制最新 3 项计划、6 项评估、5 条训练。记录页显示此读范围；完整历史和条件趋势仍进入原康复历史，不能称为已经统一全量加载。

## 设备文件格式（沿用现有 schema）

设备页显示当前用户编号，导入文件必须使用该编号。每条记录的 source、单位和指标也由原 Node 校验器核对；整批失败不写入健康事件。demo 只能进入 demo 档案。

```json
{
  "ownerId": "当前设备页显示的用户编号",
  "source": "device",
  "measurements": [{
    "id": "设备提供的稳定记录ID",
    "timestamp": "2026-10-02T08:00:00Z",
    "metric": "systolic",
    "value": 118,
    "unit": "mmHg",
    "source": "device",
    "visibility": "private"
  }]
}
```

这里是协议示例，不代表真实设备读数或默认用户数据。

## 验证与限制

- `tests/test_product_window.py` 与 `tests/test_product_navigation.py`：25 项通过。包含真实 Node bridge 的设备文件导入 / owner 拒收 / 持久化、默认外部能力不可用、用户切换清除、训练中全局助手同会话及不记录、漏服筛选、恢复银发入口、原康复导航 / 来源门禁。
- `npm run build:bridge`、`npm run typecheck` 通过。ProductService 仅补充 syncAvailable 配置状态，防止已配置但尚未连接的同步入口被错误禁用；没有新增同步协议或业务规则。
- `node --test tests/product-desktop.test.cjs tests/product-extensions.test.cjs`：12 项通过，覆盖原扩展协议、授权、验证、持久化和候选确认。
- 使用真实 Qt / ProductBackend / Node bridge 和隔离 TEST 档案生成并查看设备页、助手页、设置页与全局侧栏截图；修正侧栏初始宽度。截图和 TEST 数据位于 ignored `qa-output/ui-interfaces-20261002/`，不提交。
- 未连接真实相机、麦克风、iPhone、跨设备 peer、实体健康设备，未发送真实推送或调用 OCR / 真实 LLM。外部能力：接口已接 UI / 实机未验收。UI 端语音取消仍沿用串行请求协议，阻塞 ASR 的即时中断需原生宿主接线时确认。
- 初轮新增 UI 测试因 fixture 只等 snapshot、未等待新状态查询结束出现 2 项未执行预期操作；改为等待界面空闲后通过，没有放宽产品门禁或删除断言。

正式入口继续是 PySide6 ProductWindow。原 React / demo 仅作参考。后续视觉设计应使用本文覆盖表保留所有入口；文档差距需独立确认范围，不应被包装成已完成能力。
