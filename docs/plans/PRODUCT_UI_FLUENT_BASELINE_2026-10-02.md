# PySide6 核心页面视觉基准

范围：`codex/product-ui-v1` 的首页、AI 康复管家和康复概览。七项一级导航、顶栏、全局问管家及全部业务接口保持现状；健康、用药、家庭、记录不做布局或视觉迁移。原康复工作区保留自身样式与所有门禁，通过滚动容器适配窄窗口。

依据：PC 端前端产品逻辑、[覆盖审阅](PRODUCT_UI_COVERAGE_REVIEW_2026-10-02.md)、[功能完成及按钮审计](../validation/PRODUCT_UI_FUNCTIONAL_COMPLETION_2026-10-02.md)、[清理审计](../validation/REPOSITORY_CLEANUP_2026-10-02.md)。文档中的未来功能建议不作为本轮新增后台能力。

## 改造前实际 Qt 审计

首页五个入口同等强调，空计划表占据上半页，下一步与摘要不突出。AI 页面说明、设备操作和大聊天区纵向堆叠，输入框在首屏之外。康复概览与原工作区争夺高度，页签和主要操作不明显。旧主题仅提供部分 hover，focus/pressed、失败与禁用状态视觉不统一。以旧阶段真实 Qt 截图及当前 Widgets 源码对照确认，而非使用 React 截图或示例工程。

## Skill 与依赖

`pyside6-fluent-ui` 是 [MIT Codex skill 和原生 Qt 设计参考](https://github.com/ejacques11/pyside6-fluent-ui)，不是本次需要 pip 安装的 UI 库。安装在 `C:/Users/Sophie/.codex/skills/pyside6-fluent-ui`；完整阅读说明及 Fluent 原则、token、Qt styling、组件、状态、可访问性、验证和迁移参考。采用 Audit → Infrastructure → Migration 流程。

已审阅版本 `0.7.0-rc.1`，上游 SHA `4538e312ee9abde4b77d041d59a5392aa7d43188`。其示例接受 PySide6 >= 6.5，本机已有 PySide6 6.11.2；实际测试使用 Python 3.12.14/Node 24.20.0，不修改项目已有版本约束。只引入 token 快照、Qt alias map、来源清单及完整许可证；不引入示例 UI、组件运行库、React、WebView、PyQt、QML 或 frameless shell。requirements/锁文件不变。

微软 [Fluent tokens](https://fluent2.microsoft.design/design-tokens) 与 [布局原则](https://fluent2.microsoft.design/layout) 用于语义层级、留白和控件状态。中性色解析自固定快照，绿色品牌及状态色是项目自身别名；不复制 Sword/Windows Settings 等具体品牌画面。来源及许可证见 `rehab_codex_single_camera_v2_1/assets/ui/fluent/README.md`。

## Design System

| 层 | 统一实现 |
| --- | --- |
| Typography | `product_theme.TYPE`：Display 28/700、Section 20/600、Card 16/600、Body 14、Secondary 14、Caption 12；新页面通过 `fluentType` 使用，不自行写字号 |
| Spacing | `SPACING`：4、8、12、16、24、32；布局留白由集中别名消费 |
| Radius | `RADIUS`：控件 6、卡片 12、主行动区域 16 |
| Buttons | 原 QPushButton 加 `fluentAppearance`：primary / secondary / ghost / danger；hover、pressed、focus、disabled；不替换信号或 action ID |
| Cards | `core_card` 提供普通信息、主行动、大/小数据和状态区域；`empty_state` 提供空态；保留原卡片对象名，标题不再统一为大号绿字 |
| Status | success / warning / danger / info / disabled；明确文字与原因，不仅靠颜色；真实响应失败用 danger，成功响应用 success |
| Form | 原生输入、combo、checkbox（包括已有隐私开关）；统一边框、focus、disabled、输入验证标记与 placeholder palette；不另造 toggle 模型 |
| Feedback | 现有后台 pending、空态文字、成功/错误回执、禁用原因和 QMessageBox 确认继续复用；相同回执避免在三个核心页重复显示 |
| Theme owner | `ProductTheme` 一个顶层 owner，保留旧 `PRODUCT_STYLE`，追加生成的 scoped QSS，核心控件使用 QPalette；旧页面/原训练工作区为明确兼容边界 |
| Icons | 继续统一使用现有 `assets/ui/ankang` SVG 家族；不增加图标库，不改品牌资产 |

默认产品为浅色。dark 与传入系统 palette 的 high-contrast 是三个迁移区域的验证入口，不是全软件暗色功能，也不声称完成 OS 高对比自动识别或全部旧窗的暗色适配。没有新增主题切换业务入口或动画。

## 三个页面

- 首页：欢迎/目标 → 下一项训练和唯一主 CTA → 今日四类状态 → 任务与健康/管家摘要 → 保存计划。累计进度取原计划 `progress.completed/total`；今日次数仍来自实际当天完成的记录，不制造日排期或康复改善比例。
- 管家：保留原 QTextBrowser、输入框和发送动作；用户与管家有明确姓名/时间/背景层级。参考资料与附件/语音放入可滚动工具列，推荐问题保持原 chat 动作；1024×720 输入及发送可见。语音/识别/新会话仍按原条件禁用，不模拟上下文注入。
- 康复：四页签以选中下划线与标题层级区分；继续训练、新评估、自动安排各在自身页签突出。表格保留原模型和选择动作，累计进度复用原读数据。原摄像头、双摄、回放、身体档案、计划库、自动计划、训练反馈、报告、银发入口不删、不重写；窄窗口通过原工作区滚动访问，收起概览增大可视区域。

按钮审计中的 116 个 action ID/文字/target 完全保留；已存在但旧 CSV 未抓到的侧栏 `dockSend` 同时验收（总共 117 个标记控件）。将旧自动编号固化为 published ID，避免重排父子布局使自动化 ID 漂移。所有按钮仍为原生 QPushButton，原 signal/slot、backend、disabled/confirmation、owner/scope 与任务线程保持不变。

截图、测试、已知边界见[本轮验收](../validation/PRODUCT_UI_VISUAL_BASELINE_2026-10-02.md)。本轮到三个页面基准为止，下一轮等待视觉方向审阅。
