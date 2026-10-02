# Repository Cleanup / Legacy Audit — 2026-10-02

本轮在 `codex/product-ui-v1` 收口运行结构。未改视觉、Agent 语义、业务规则、数据库 schema 或训练算法；未合并 main。起点 `9cc09d9e45e94d3fd25d9b5097f6c1ce2e137393`，起始工作区 clean。main 仍为 `fb113ff36b694e379548ded2b48137fca34581ae`，stage1 仍为 `4b2d108a3003d84c89ac42da25580017d5b1de17`。

## 正式运行依赖

```text
启动康复助手.cmd → Start-Rehab.ps1
  ├─ build-agent-bridge.cjs → tsconfig.bridge.json → .bridge-build（生成文件）
  └─ run_app.py → app.main → ProductWindow
       ├─ ProductCompletion / ProductInterfaces / ProductDialogs / widgets/theme
       ├─ ProductRehabWindow → MainWindow / workspace / 原康复 UI
       │    └─ Runtime → command bus / Controller / CameraManager
       │         → 原 assessment / Body Profile / exercises / plans / training
       │         → history / feedback / reports / SQLite
       │         → silver / local family response / 隔离 family demo
       │         → 可选 landmark_backend → 独立 landmark_process
       └─ ProductBackend（后台串行队列）
            ├─ RehabReadTools → 原 SQLite（当前用户/来源/情境）
            ├─ app.product.capture → capture_contracts → 既有 media.import/Archive
            └─ bridges.ankang.client → Node agent-bridge.cjs
                 ├─ ProductLocalStore（本地用户数据，不入 Git）
                 ├─ rehab-model.cjs → DeepSeek adapter / Python rehab tools
                 ├─ ProductService → AgentRuntime / engine / HealthEvent / Twin
                 │    → MedicationService / FamilyService / ProfilePersistence
                 │    → ArchiveService / NotificationService / reports / history
                 └─ ports / 可选 adapters
                      → voice ASR/TTS / sync schema+validation+PeerJS
                      → HealthKit HTTP + native-ios companion
                      → generic device / webhook delivery / image vision provider
```

[清理前源码依赖边](REPOSITORY_RUNTIME_DEPENDENCIES_BEFORE_CLEANUP_2026-10-02.csv)与[清理后源码依赖边](REPOSITORY_RUNTIME_DEPENDENCIES_2026-10-02.csv)区分 Python imports、按路径加载、子进程、Node require、TS imports/type imports。最终保守闭包：85 个 Python 文件、75 个 TypeScript 文件、569 条边。Python 包括正式入口、延迟 import、可选 landmark 子进程及 retained capture 接口；TS 包括 bridge 编译根和明确保留的外部 adapters。它们不是所有模块都在 Windows 默认启动时执行的计数。单独 Agent Runtime 的实际 TS 闭包为 35 个源文件，无 React、TSX、平台 UI、PeerJS 或 Home Twin import。

关键发现：`app/product/capture.py` 曾按路径加载 `ankang/route2-home-3d/backend/capture.py`。空间推理本身没有依赖，但这个通用 CaptureFile/CaptureBatch/CaptureSource/BrowserUploadCaptureSource 有正式用途。因此原文件逐字迁入 `app/product/capture_contracts.py`（迁入时 SHA256 一致），原 wrapper 改成普通相对 import，保留 `ProductBackend.submit_capture → media.import → ArchiveService`，没有重写第二套 capture 实现。

## 分类与处置

删除前已向用户输出分类清单；[逐文件审计 CSV](REPOSITORY_CLEANUP_FILE_AUDIT_2026-10-02.csv)覆盖起点全部 757 个 tracked 文件。三类初始计数：PRODUCTION 213、REFERENCE 535、DEAD/GENERATED 9。`formal_dependency` 是清理前保守源文件闭包，不能把它当作控件实际可达性或临床验收；旧助手仅有隐藏 sidebar/生命周期构造依赖，已先拆除该路径再删除。

| 范围 | 分类 | 本轮处置 |
| --- | --- | --- |
| 根启动/安装脚本、run_app/main、依赖清单 | PRODUCTION | 保留；Node build 改为正式 bridge，移除 Vite 入口 |
| app/ui/product_*、ProductBackend、bridge、rehab tools | PRODUCTION | 保留完整正式七页、顶栏和全局管家 |
| app/ui/main_window、workspace、assessment/body/training/plan/history/report/camera/silver/family | PRODUCTION | 保留；它们仍被 ProductRehabWindow/Runtime 使用，名称旧并不等于死代码 |
| 原康复 app、模型清单、配置、字体/图标/动作资源 | PRODUCTION | 保留；原动作/双摄/自动计划/回放/反馈/银发能力不删除 |
| TS runtime/product/engine/types/pipeline/业务 services | PRODUCTION | 保留，不复制业务逻辑、不优化语义 |
| Voice、Sync、HealthKit、通知、设备、image adapters，native-ios | PRODUCTION（可选宿主） | 保留协议、权限/导入接口、验证、mock 支持；默认未配置不等于可用 |
| Route2 backend/capture.py | PRODUCTION | 原样迁出到 app/product/capture_contracts.py |
| React App/main、components/hooks、CSS、Vite/config/index | REFERENCE | 删除 UI 与浏览器配置；保留仍被 core/adapter/tests 使用的 TS 模块 |
| BrowserAttachmentPort + demoArchives | REFERENCE | 删除旧展示/演示附件 adapter；正式 ProductLocalStore/ArchiveService 不变 |
| route1 agent-tools/HomeTwin*、HomeSafety*、空间 demo 与专用 tests | REFERENCE | 删除；这些未进入 AgentRuntime/ProductService 正式操作路径 |
| route2 backend/pipeline/semantic/web/3DGS 实现及空间专用 tests | REFERENCE | 从 UI 分支移除，正式产品不再按路径依赖 Route2 |
| Route2 架构、角色、capture、pipeline、QA 文档 | REFERENCE | 16 份说明归档至 docs/archive/ankang-route2，不丢历史成果 |
| design-demos HTML/scripts、p0-blackbox、React browser tests/helpers | REFERENCE | 删除；保留 design-spec/direction-approved 等设计说明 |
| 旧设计演示 PNG | DEAD/GENERATED | 删除 9 个 tracked 截图产物 |
| 嵌套 ankang/.github/workflows | REFERENCE | 删除只属于导入快照的 React/Route2 发布/CI，未影响根 CI |
| app/ui/ankang_assistant.py 与专用 test/smoke 脚本 | REFERENCE | 删除旧独立验收窗口与隐藏 sidebar 接线；当前一级管家/全局对话和开发者设置保留 |
| 原 demo_training_plan、silver/family_demo、原受控观察模块 | PRODUCTION / 隔离验证支持 | 仍有 Runtime/UI 命令依赖，保留 SYNTHETIC/TEST 隔离边界，正式产品不出现假摄像头 |
| tests/fixtures/legacyReactOrchestration.ts | REFERENCE | 保留无 React import 的业务 parity 夹具，不是第二套生产 Agent |
| 独立 browser storage、parser mocks、retry 等纯业务支持 | REFERENCE | 被业务回归/可复用接口引用，保留，不挂成第二个正式入口 |
| docs/plans/validation/specifications/history、源头记录、QA/scripts | REFERENCE / 维护支持 | 保留；9 个旧源码 Markdown 链接改为 stage1 固定 SHA 链接 |

共撤出 206 个旧路径：189 个参考/产物文件删除、16 份 Markdown 归档、1 份 capture 契约原样迁入。所有撤出路径均逐项核实存在于 stage1。旧 UI 不移动到另一个可执行入口；Git/stage1 保留原文件版本。当前 main/stage1 并未被本轮清理改变。

## 无重复生产实现及废弃 Agent

- 正式 Agent 路径只有 TypeScript AgentRuntime；未发现 A1/A2/A3 的 Python 可执行实现或 import。历史文档/标题的 A1 字样不代表实现恢复。
- 旧 AssistantWorker/AssistantDialog 已删除，正式对话只经 ProductBackend/ProductService；DeepSeekDeveloperDialog 仍是当前设置页的实际配置入口。
- MedicationService、FamilyService、ArchiveService、NotificationService 的同一份业务实现继续复用。React hooks 不再存在；两个业务测试改从 Runtime/FamilyService 直接导入原转导出的同一函数。
- 原康复 Runtime 与 Ankang AgentRuntime 分别处理训练执行和健康管理；原银发本地支持/隔离手机演示与 Ankang 照护圈的数据域不同，不把它们机械合并或删除。
- `types.ts` 中旧记录的 `toolTarget.source = route2-home-twin` 字段与 ProductService 的 disabled capability 标记继续保留兼容，不构成空间 API 调用或 runtime dependency。

## 本地内容和生成文件

本轮开始没有未提交/untracked 产品成果。[本地 ignored 分类表](REPOSITORY_CLEANUP_LOCAL_AUDIT_2026-10-02.csv)区分依赖/参考归档、生成文件与受保护的本机环境/资料模式。依赖、构建输出、截图、Python caches、qa-output 和 backups 为 ignored 内容；没有删除 backups/原始归档、本机环境、权重、用户 SQLite、配置或 secrets。未知/用户资料不按目录名推断为可删。旧 React dist 与旧 TypeScript test build/tsbuildinfo 在确认绝对目标位于本包后清理，测试从干净输出重新编译；bridge builder 每次清空 `.bridge-build` 再生成，防止旧模块继续留在可执行输出。新截图/验收辅助脚本仅留在 ignored qa-output。

参考 `.env.example` / `.env.hardware.example` 是旧浏览器占位配置，保留为历史参考，正式桌面不读取 VITE_*。真实桌面端点由 Node 进程的 ANKANG_* / HEALTHKIT_* 环境及开发者设置注入。无真实 iPhone、服务或硬件时，本轮仅证明接口/模块保留，未做实机验收。

## 针对性验证

本机本轮实际解释器：Node `v24.20.0`、Python `3.12.14`（临时测试环境，已装 PySide6）；这是下列结果的环境记录，不改安装脚本既有的 Python 3.13 要求。

- `npm run build`：全量保留 TS typecheck + 从干净 `.bridge-build` 构建通过。
- `tsc -p tsconfig.test.json`：保留全部 TS 业务/回归源编译通过；没有依赖被删除 hooks 的残余测试。
- Node `product-desktop` / `product-extensions`：12 passed（实际 ProductService、本地持久化、药物/家庭/隐私、图片确认、设备、HealthKit、通知、sync、voice 与媒体协议）。
- Node runtime/dependencies/rehab-tools/family-handshake/care-tasks：34 passed；清空 `.test-build` 后编译再验同样通过，非旧产物结果。
- Python/Qt：52 passed / 70.77s。文件范围 `test_product_window`、`test_product_completion`、`test_product_navigation`、`test_rehab_read_tools`、`test_product_capture`、`test_training_ui`、`test_training_runtime`、`test_deepseek_developer`。真实 bridge 三个康复问题与 scope 隔离保留；新的 capture 测试验证视频协议字节经正式 backend 进入已有私密档案、不推断 HealthEvent，以及大小变化拒绝入库。
- 实际 ProductWindow + Runtime + Node 后端，隔离 TEST 资料，逐页/页签/原康复 workspace、计划、银发/全局管家打开通过。44 张截图与盘点在 ignored `qa-output/cleanup-20261002`：489 次产品控件观察、192 次原功能观察，是多个页面状态的观察数，不是新增按钮数；首页截图另经人工查看确认实际渲染。
- `npm run security:check`、tracked 源文件明显密钥模式与禁入文件核对通过；无 secrets、个人数据库、环境或构建产物进入 Git。最终 569 条源码依赖边无缺失目标、无 React/Route2/旧助手依赖。`git diff --check` 通过；最终文档检查 303 个相对链接、0 个失效。

上述是软件路径验收，不宣称摄像头训练、ASR/TTS、iPhone HealthKit、远程同步、真实 push/webhook 或实体设备实机通过。清理后停止，等待用户下一步要求。
