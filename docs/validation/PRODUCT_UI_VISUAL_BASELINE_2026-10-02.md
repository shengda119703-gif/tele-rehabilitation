# 三个核心页面 Fluent 视觉基准验收

分支：`codex/product-ui-v1`。基线：`28e412666427f4728ae41252b8646d9fe727e8fa`。
对应[设计系统与审计](../plans/PRODUCT_UI_FLUENT_BASELINE_2026-10-02.md)。本轮只提交 UI/资源来源、针对性验证工具、测试和文档；不 merge main，不推进其他四页美化。

## 交付与不变项

| 页面 | 本轮视觉变化 | 保留的真实行为 |
| --- | --- | --- |
| 首页 | 欢迎/目标、突出下一项及“继续训练”、较小今日数据卡、任务与健康/管家摘要、保存计划后置；实际累计进度条 | 原继续/计划/任务状态/用药/健康/管家/个人资料按钮；使用现有 snapshot，无假数据或日排期 |
| AI 康复管家 | 明确区分双方消息、当前能力状态、对话/输入主列、推荐问题、可滚动参考与工具列 | 发送/不记录、全局侧栏及关闭、上传/识别、语音/停止、去康复、新会话禁用；原 Agent bridge 和 owner/scope，不自动注入页面/附件 |
| 康复 | 四页签选中层级、真实累计进度、各页主行动、较安静的表格；原工作区滚动适配与概览收起 | 今日训练、原评估、Body Profile、动作目录、摄像头/双摄/回放、计划库/自动计划/接受/准备、训练/反馈/历史/报告、银发入口全部保留 |

原 116 个按钮 ID/文字/target 与 CSV 完全一致；原侧栏发送 `dockSend` 额外检查，共 117 个带 action 标记的原生按钮，均有 clicked 信号连接。没有新建 backend、改 Runtime/Agent 规则/算法/数据库 schema、删除原功能或改变 confirmation、disabled、participant 隔离条件。其他四页布局原样保留；公共回执增加明确成功/错误颜色，仍显示真实结果。

`pyside6-fluent-ui` 已作为 Codex skill 安装、阅读；不是 pip UI dependency。仅使用其 MIT 设计指南和有许可证/来源的固定 token 数据。项目 requirements、原 PySide6/Qt Widgets 栈保持不变。浅色为产品默认；暗色及显式 high-contrast palette 为核心组件验证路径，不新增全软件主题功能。

## 实际 Qt 截图

以下均为实际 ProductWindow、原 Runtime、ProductBackend/Node bridge 的 QWidget.grab，使用临时 SYNTHETIC/TEST 用户、既有自动计划生成器、药物/健康存储和真实基础管家回复。没有使用 AI 绘图、HTML mock 或伪造成功。Windows 原生插件实际启动，系统 DPR=1.5；1440×940 逻辑客户区输出 2160×1410 PNG。

| 证据 | 说明 |
| --- | --- |
| [首页](images/product-ui-fluent-v1/home.png) | 下一步 CTA、真实计划/任务/药物状态与摘要 |
| [AI 康复管家](images/product-ui-fluent-v1/assistant.png) | 双方消息、输入/发送、状态与真实禁用工具 |
| [康复](images/product-ui-fluent-v1/rehab.png) | 今日训练概览、页签、原工作区 |
| [评估页签](images/product-ui-fluent-v1/rehab-1.png) | SYNTHETIC/TEST 评估历史与原评估入口 |
| [收起后的原工作区](images/product-ui-fluent-v1/rehab-workspace.png) | 原控件未替换，滚动访问不被概览阻挡 |
| [1024 宽 AI 页](images/product-ui-fluent-v1/assistant-1024.png) | 输入与发送在首屏可见，工具列可独立滚动 |
| [错误样式](images/product-ui-fluent-v1/error.png) | 临时 TEST 档案向真实 ProductService 提交无效指标，原校验器拒收并由 UI 展示失败；不是模拟外部网络故障 |

全部 QA 图片/观察 JSON 留在 ignored `qa-output/fluent-v1`；仅上表经审阅、明确 TEST 的文档插图纳入 Git。临时数据库、运行状态、模型配置、cache 不提交。

## 尺寸与 DPI

| 平台 | 逻辑尺寸 | 实际 DPR | 结果 |
| --- | --- | --- | --- |
| Windows native Qt | 1440×940 | 1.5（真实系统值） | 三页启动/截图，输入首屏可见、核心区域无横向溢出 |
| Windows native Qt | 1024×768 | 1.5（真实系统值） | 首页/AI 无横向溢出；AI 发送首屏可见；原工作区有 2px 可滚动范围 |
| Qt offscreen | 1024×720、1024×768 | 1.0 | 最小窗口尺寸保持，AI 输入/发送可见；原工作区 4px 可滚动范围 |
| Qt offscreen | 1024×768 | 1.25 | 无核心页面横向溢出、字体/按钮可读 |
| Qt offscreen | 1280×800 | 1.5 | 三页无横向溢出，输入/发送可见 |
| Qt offscreen | 1920×1080 | 2.0 | 三页尺寸正确、无横向溢出，实际 PNG 为 3840×2160 |
| Qt offscreen dark | 1440×940 | 1.0 | 核心区域正文、对话和禁用状态可读；旧 shell/工作区仍为浅色兼容边界 |

已逐张检查真实图片：改前 AI 输入位于首屏之外，改后最小窗口仍可发送；调整推荐问题为单行，避免多行挤压；卡片改为顶部对齐，避免标签被高度拉开；正文及状态对比度检查发现浅色 disabled text 不足 4.5 后加深；暗色 placeholder 使用统一 palette。页签、主 CTA、中文标题和按钮未见明显截断，左导航稳定。较长正文按原生换行/滚动显示。少数任务标题沿用原业务字符串中的装饰 emoji，其字体回退未作为新图标系统重写。

实际 Windows 高 DPI 启动已验收；125%/150%/200% 是独立 Qt 进程的缩放验证，不等于验收所有多显示器切换、系统高对比自动检测或所有旧窗口的暗色主题。原训练区小幅横向滚动是保留其最小控件布局的兼容边界，不用裁剪/删除控件消除滚动条。

## 针对性回归

运行 `test_product_window.py`、`test_product_completion.py`、`test_product_visual.py`、`test_product_navigation.py`、`test_training_ui.py`：**44 项通过，67.00 秒**。最后调色板/字号作用域及恢复原设备页布局后，视觉测试和设备文件真实导入再复核 **5 项通过**（属于上述测试的重复复核，不增加总数量）。

- 首页按钮/跳转、AI 发送通过真实 bridge、全局问管家及关闭不丢当前页面、康复导航/训练准备/评估路径、返回首页。
- 既有七条用户路径的软件闭环全部通过；包括合成控制器训练保存 → 原报告 → 本人反馈 → 首页，不声称相机真人训练已验收。
- participant 切换清除聊天/草稿/报告/新进度条、来源/使用情境门禁、重复提交、原异步 pending、真实失败提示、disabled/确认、无模型配置状态。
- 116 个已发布按钮契约及已有 dockSend、native clicked 连接、最小窗口、输入与按钮键盘焦点、主题切换不改 action/数据、HTML 转义。
- 浅/暗色正文、次要正文、主按钮、disabled 文字及四类状态前景/背景至少 4.5:1；显式 high-contrast palette 能应用且不改变功能，状态仍有文字。

最初试跑发现滚动容器错误引用 `NoFrame`，修正为 `QFrame.NoFrame`；保留滚动兼容边界后，将旧“原内容高度增大”断言改为“原工作区可视高度增大”，没有删门禁、假成功或弱化用户路径断言。

复现：已有开发环境内 `python -m pytest ... -q`；截图工具为 `rehab_codex_single_camera_v2_1/tools/validate_product_visual.py`，参数 `--width` / `--height` / `--theme`，支持独立进程 `QT_SCALE_FACTOR` 和 `QT_QPA_PLATFORM=windows`。工具仅使用临时目录，关闭后清理，不触碰正式用户数据。没有 UI runtime dependency 增量。

本轮未连接真实摄像头、麦克风/ASR/TTS、iPhone、远程 peer、实体健康设备、OCR/外部模型或推送渠道。接口及原门禁保留，外部能力继续明确“接口已接 UI / 实机未验收”。

## Git 与停止边界

检查只包含 UI 源码、资源许可证、测试、截图工具和本轮文档插图；无 .env、API Key、deepseek.json、SQLite、node_modules、.venv、build/runtime 输出。`git diff --check` 通过。main 与 stage1 引用未修改。本轮提交推送后停止，等待三个基准页视觉审阅；不自动迁移健康、用药、家庭、记录。
