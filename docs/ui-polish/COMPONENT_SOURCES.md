# Component procurement — SEARCH BEFORE INVENT

常见 primitive 自行实现前，先查当前 widgets/composites 和成熟 registry。记录至少一个候选或真实无匹配证据。避免为了原创重新造更弱的控件。React Bits 不强制使用，Qt 原生行为优先；不得因此更换框架、添加 WebView 或修改业务状态。

## React Bits 实际通路

- 官方 [目录](https://reactbits.dev/r/registry.json) 是 shadcn registry，当前读取到 852 个 variant items。
- item URL：`https://reactbits.dev/r/{Component}-TS-CSS.json`。JSON 含 description/dependencies/registryDependencies/files；files.content 含完整源码，可提取 TypeScript props。
- 本项目 `node tools/ui-polish/discover-components.mjs <query>` 是只读访问器，五类有语义别名，其他查询搜索完整 index 后读取最多 8 个 TS-CSS 候选。输出到忽略的 QA 目录，不执行源码。
- [官方 MCP 指南](https://reactbits.dev/get-started/mcp) 推荐 shadcn MCP；registry 模板为 `https://reactbits.dev/r/{name}.json`。不存在本轮已验证的独立 React Bits MCP 服务。本轮选择同一官方 registry 直接读取：没有新增 npm/MCP 服务，也不需要 Codex 重启和项目 React 配置；这已提供结构化 component discovery。
- [shadcn MCP](https://ui.shadcn.com/docs/mcp) 是未来需要 agent 原生 registry tools 时的可选桥梁。本轮没有声称 MCP 已连接，未运行未知第三方 MCP wrapper。
- shadcn/jsrepo CLI、JS/TS × CSS/Tailwind 四种 variant 均在官方 README/docs 存在。CLI 命令只作为未来网页项目的安装资料，本轮未向产品安装任何组件。
- 页面有 Preview/Code/Copy for AI/Props/Dependencies；已真实渲染 Warm Tooltip 预览。Copy for AI 是网页复制入口，registry 更适合确定性读取。本轮无需剪贴板权限。
- [Pro](https://reactbits.dev/pro) 提供 App UI/blocks/templates/Agent Kit 等付费资源，页面标有少量 Free 项，不代表全套免费。未下载付费内容或绕过限制。

## 五个 discovery 实测候选

| Primitive / 名称 | 实际用途与交互 | registry dependencies（当前 TS-CSS） | relevant props | demo |
| --- | --- | --- | --- | --- |
| Tooltip / Warm Tooltip | 首次延迟弹出；group warm window 内相邻提示立即打开；位置移动/可选 lean；触摸长按、键盘 focus/Escape | react-dom ^19.0.0，motion ^12.23.12 | content, shortcut, children, side, delay, warmWindow, popDuration, disabled；group travel/lean | [预览](https://reactbits.dev/c/micro/warm-tooltip) |
| Segmented control / Rubber Segment | 点击弹性 thumb；可拖动/甩动跨 slots；controlled value/onChange | motion ^12.23.12 | items, value, defaultValue, onChange, equalSlots, stretch, squash, draggable, disabled | [预览](https://reactbits.dev/c/micro/rubber-segment) |
| Select / Glide Select | 菜单从 chip 角落出现；hover highlight 在行间移动并记住重入位置 | @hugeicons/react ^1.1.10、core-free-icons ^4.3.3 | options, value, onChange, placement, align, rememberPosition, popDuration, glideDuration, disabled | [预览](https://reactbits.dev/c/micro/glide-select) |
| AI input / Prompt Bar | sources/commands/model 选择；附件/听写 callbacks；可发送时按钮激活，busy 变 stop | motion ^12.23.12 + 两个 Hugeicons 包 | sources, commands, models, busy, onSend, onStop, onAttach, onDictate, maxRows | [预览](https://reactbits.dev/c/micro/prompt-bar) |
| Navigation / Branched Menu | section 展开为树干/曲线分支；accent 沿路径移动到选择项 | 两个 Hugeicons 包 | items, defaultOpen, defaultActive, onSelect, onToggle, indent, rowHeight, drawDuration, foldDuration | [预览](https://reactbits.dev/c/micro/branched-menu) |

上述五项均已在线读取完整 JSON、源码与 props；行为来自源码和 registry 描述。Warm Tooltip 的浏览器 demo 另有三尺寸截图、hover 显示 Bold/快捷键和 focus/Escape 关闭实测；其他四项未做端到端交互。registry 精确依赖比页面只显示主要 npm 依赖更完整。每轮采购应重新查询，不能以这张表代替未来网络验证。

源码获取示例：[WarmTooltip TS-CSS JSON](https://reactbits.dev/r/WarmTooltip-TS-CSS.json)。未来 React 项目安装形式 `npx shadcn add https://reactbits.dev/r/WarmTooltip-TS-CSS.json`；本轮未执行。当前 Qt 项目应先比较 `QToolTip`、`QComboBox`、`QButtonGroup`、`QMenu`、Qt dialogs/tab controls 和现有 product_widgets，选择保持信号/键盘契约的 native adaptation。Prompt Bar 不意味着后端已具备所有模型/听写/stop 能力。

## 其他来源

| 来源 | 用法与兼容性 | 许可/限制 |
| --- | --- | --- |
| [Qt Widgets](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/index.html) | 本产品首选原生 primitives；既有 `app/ui/product_widgets.py` 和 theme 的行为需保留 | Qt/PySide 许可随实际发行包审查；本轮仅使用已锁的测试依赖 |
| [Fluent 2](https://fluent2.microsoft.design/) / 本地 pyside skill | token、density、状态、布局及 Qt mappings | vendored skill MIT；微软 token/icons notices 随包保留 |
| [shadcn registry](https://ui.shadcn.com/docs/registry) | 未来真实 React 目标的组件发现；不赋予 Qt 直接兼容性 | 单独检查每个 registry item 的来源/许可；不要把全部第三方 registry 都当 MIT |

React Bits [LICENSE.md](https://github.com/DavidHDev/react-bits/blob/ca44b3f9ee180676a06d7de8ec6bea84cddff85b/LICENSE.md) 为 MIT + Commons Clause，允许作为应用/产品的一部分使用，限制单独或打包转售/再分发组件本身，包括 port。不是纯 MIT，也不能将本次 discovery 当作可发布 Qt port library 的授权。组件源码仅保留在本机忽略目录，版本控制只提交工具、事实目录和规则。
