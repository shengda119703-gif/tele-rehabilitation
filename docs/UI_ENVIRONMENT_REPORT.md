# UI_ENVIRONMENT_REPORT

审计/实测日期：2026-10-05（Asia/Hong_Kong）。范围：`tele-rehabilitation` 当前 `codex/product-ui-v1`。本轮只建立 UI Polish / Visual Design 环境，**没有编辑正式 UI、QSS/CSS、业务、Runtime、API 或数据模型，没有安装组件到产品页面**。开始时工作区已有其他会话的未提交产品/测试改动，执行中还有并发写入/提交，测试看到的是当时 working tree，不是纯 HEAD；本轮提交不包含这些文件。

## Installed / Configured

- 项目 `.agents/skills/`：`ui-polish` 工作流、`ui-ux-pro-max` 离线知识检索、`frontend-design` 审美规则、已有 `pyside6-fluent-ui` 的项目快照。
- 根 `AGENTS.md` 增加 UI Polish 触发规则；工作区上层 `康复/AGENTS.md` 增加项目定位/同样触发入口（上层文件不在本 Git 仓库，未上传；项目内完整规则可独立使用）。
- `tools/ui-polish/`：只读 React Bits registry discovery、Playwright/Edge 三尺寸 smoke、真实网页截图/console 工具、Qt capture wrapper、QA 依赖锁、来源/hash 清单及维护说明。
- `.venv-ui-polish/`：本机新建、Git 忽略、项目专属 QA 环境。系统 Python 与用户级 Codex Skill/MCP 配置没有改变。Qt 官方既有 UI 截图工具直接复用，不另造产品截图框架。
- 文档：本报告、`docs/ui-polish/WORKFLOW.md`、`COMPONENT_SOURCES.md`、精选 TEST 截图及 smoke 证据。没有新增产品 runtime dependency；原 package.json/package-lock 未修改。

### 实际环境清单

| 项目 | 审计结果 |
| --- | --- |
| Codex | 桌面会话，PowerShell，配置 model 为 gpt-6.1-sol；普通工程执行可用 |
| 正式界面 | PySide6 Qt Widgets `ProductWindow`，Python；不是 React/Next/Vite 网站 |
| 后端 | Ankang Node/TypeScript Runtime/ProductService，经现有 bridge 接 Qt |
| 包管理 | 后端 npm；声明 npm@10.9.2，实机 npm 11.19.0 / Node 24.20.0；TypeScript 声明 ~5.6.3 |
| 前端框架/CSS | 正式产品无 React/Next/Vite/Tailwind；Qt QPalette/QSS/theme 与既有 widgets。归档 demo 不等于正式页面 |
| Python | 系统 3.12.10 无 PySide6；标准 `.venv` 缺失。本轮隔离 QA 为 Python 3.12.10 + PySide6 Essentials 6.11.2，pip check 通过；不称完整 Python 3.13 正式环境 |
| 已有 Skills | 本会话目录含 pyside6-fluent-ui、skill-creator、computer-use、OpenAI Docs、各类 artifact/app skills；设计主选 pyside，其余泛用 skills 不重复安装 |
| AGENTS | 项目根与应用目录均已读取；HANDOFF 明确正式 Qt 产品和当前分支；仅新增基础设施规则 |
| MCP | 用户配置 server 名称只有 node_repl；已有桌面/app connectors 为会话工具。未发现已连接 React Bits/shadcn/Playwright MCP。未输出凭据或原始敏感配置 |
| Windows computer use | 已读取现有插件 skill/guidance/api/confirmation；`@oai/sky` 初始化、list_apps/list_windows 成功。Qt 截图主路径用项目既有工具，不操作其他用户窗口 |
| Playwright | 后端已有 1.63.0；默认 Chromium headless executable 缺失，初次 launch FAIL；改复用已安装 Edge 154.0.4258.53 后 launch PASS |
| 外网/GitHub | 官方网页、React Bits registry fetch、GitHub ls-remote/clone/raw 固定提交访问 PASS；GitHub 公共 API rate limit 403，改 git/raw 取证 |
| 本地运行/截图 | 正式 ProductWindow 在 Windows platform/DPR 1.5 运行；1440×940 light 与 1024×940 dark 各 44 PNG；全部九主页面 horizontalOverflow=0 |

## Skills

| Skill | 来源/版本/许可 | 位置、选择原因与触发 |
| --- | --- | --- |
| ui-polish | 本项目原创 | `.agents/skills/ui-polish/`；统一冻结/采购/验收；“进入 UI polish mode”或明确纯视觉请求 |
| ui-ux-pro-max | [nextlevelbuilder](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/477bcb28c9812b385cb51a4605ddf30d7b2266e2)，上游最新提交 2026-10-03，MIT | `.agents/skills/ui-ux-pro-max/`；BM25 Python + CSV，实际增加离线知识而不只是 prompt。手动渲染 Codex template，复制数据与生产脚本，未执行 CLI installer。由 polish 的设计阶段调用或显式点名 |
| frontend-design | [Anthropic](https://github.com/anthropics/skills/tree/8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4/skills/frontend-design)，仓库最新提交 2026-09-28，Apache-2.0 | `.agents/skills/frontend-design/`，原文/许可保留；明确审美方向/反模板规则，属于 guidance，不带浏览器工具。用于 taste 阶段；不让新奇字体/营销文案覆盖医疗/银发可读性 |
| pyside6-fluent-ui | 本机此前安装的 0.7.0-rc.1，source manifest 更新 2026-07-15，MIT + 微软 notices | `.agents/skills/pyside6-fluent-ui/`；与真实 Qt 栈吻合，含 references、token resources、templates、验证资料；polish 的 Qt 设计/实现/审查阶段读取。未联网证明存在更近期发布，不把 rc 当稳定 release |

上述文件均可 Git 跟踪、移植；源 revision/hash 在 `tools/ui-polish/sources.lock.json`，第三方许可证随目录保留。用户级原 pyside skill 在 `C:/Users/Sophie/.codex/skills/pyside6-fluent-ui`，本轮没有改它。移除本套环境不会移除用户原件。更新/移除方法见工具 README。

上游 `design_system.py` 仅规范化尾随空白以通过 diff check，记录在 manifest；逻辑未改。Git 原 `**/data/` 忽略规则会遮蔽知识 CSV，已加精确的 `.agents/skills/ui-ux-pro-max/data/` 例外；患者/运行 data 继续忽略。验证全部 110 个 Skill 来源文件均进入提交，不会交付空知识库。

新建 Skills 本会话通过直接读取运行；新会话自动扫描/热加载未做独立验收，根 AGENTS.md 提供显式文件读取兜底。[官方 Skills 指南](https://developers.openai.com/codex/skills) 支持项目级技能机制；不能将文件存在等同于 UI 中已经自动列出。

### 调研后未安装的方案

| 候选 | 真实检查与取舍 |
| --- | --- |
| [PGraeff frontend-design-pro](https://github.com/PGraeff/frontend-design-pro-agent-skill) | 固定 HEAD `6555e72…`，最新提交 2026-07-19，Apache-2.0；读取 skill/文件树，含 Python 检索与知识，兼容 portable skill。与已选 pro-max + frontend-design 重叠，触发较广；本轮不叠装，避免重复/冲突；未运行 install.ps1/sh |
| [Vercel web-design-guidelines](https://github.com/vercel-labs/agent-skills/tree/063bee94c3f4df8453406c830b0a7df0f2860278/skills/web-design-guidelines) | 仓库最新提交 2026-08-28，skill 主要是 fetch 最新 web rule 的薄 wrapper，没有 screenshot 工具。HTML/ARIA/URL 等规则不能直接作为 Qt 契约；当前无正式 web 页面，未安装。所检文件树未见 LICENSE、package.json 未声明 license，不冒称纯 MIT |
| [OpenAI playwright skill](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/playwright) | 仓库最新提交 2026-06-23，Apache-2.0；读取 skill，CLI-first，依赖 shell wrapper/npx playwright-cli。现有 Node Playwright 能直接跑 Edge，额外 CLI 不增加本任务能力，故不安装 |
| React Bits 第三方 MCP wrapper | 优先官方 registry 与官方推荐 shadcn MCP；不机械安装不明 wrapper、不给 repo 额外运行权限 |
| shadcn MCP / React 组件库 | 确认官方 MCP 支持 registry search/view/install；正式产品 Qt 不需要 components.json、React deps 或新长期服务，使用同一 registry 的直接只读通路；不是声称 MCP 已安装 |

## Component Sources

重点通路是 **React Bits registry JSON → description/dependencies/source/props → demo → Qt 兼容性决策**。执行 `node tools/ui-polish/discover-components.mjs all` 已取得 Warm Tooltip、Rubber Segment、Glide Select、Prompt Bar、Branched Menu 的真实 JSON；全部有完整源码、用途、交互描述、依赖、安装来源、TypeScript props 和 demo URL。又以 `toast` 搜索完整 registry，找到 SwipeToast，证明并非只写死五个名字。

详情、命令、候选表和其他 Qt/Fluent/shadcn 来源见 [COMPONENT_SOURCES.md](ui-polish/COMPONENT_SOURCES.md)。React Bits 官方支持 shadcn/jsrepo CLI、Copy for AI 与 registry；其 MCP 指南推荐 shadcn MCP，没有本轮已测试的独立 React Bits server。App UI/blocks/Agent Kit 等主要为付费 Pro，本轮未采购。免费源码 MIT + Commons Clause，不能当作无限制 MIT 或发布组件 port library 的许可。

Warm Tooltip demo 另经 Edge 实测：hover 出现 Bold/快捷键，focus + Escape 后 tooltip 消失，并打开截图检查。其他四项行为依据完整源码/registry，没有声称逐项 demo 交互通过。

## Visual Review

正式产品闭环：CODE → `capture-qt.ps1` 启动实际 ProductWindow/Runtime/ProductService + 临时 SYNTHETIC/TEST 数据 → Windows Qt 渲染 → `QWidget.grab` PNG → `view_image` 像素审阅 →（未来授权时）修改 presentation → 同参数重跑 → 现有功能回归。

本轮使用既有 `validate_product_visual.py --phase ux-audit`。它调用真实服务及 Qt/QTest，含 tab 点击、焦点、hover、错误请求、返回/模块导航；有些路径通过既有 widget callback 驱动，**不是完整 OS 鼠标黑箱回归**。没有打开相机/麦克风/LLM，没有改患者库。1440×940 light 与 1024×940 dark 的 logical size、DPR=1.5、字体和 overflow 均写入 observations。原训练工作区仍有正常纵向滚动，不把滚动当作失败。

浏览器通路：现有 Playwright → Edge → 127.0.0.1 临时 QA fixture → desktop/tablet/mobile → 点击/console/pageerror/screenshot → 关闭资源。另 `inspect-web.cjs` 可打开真实 web 页面/视觉参考。**Qt 正式产品没有 browser URL**；本地 fixture 验证的是浏览器能力，不是把 Qt 产品网页化。没有为了满足 web 清单而创建假的产品网页。

本机完整证据：`qa-output/ui-env/qt`（88 PNG）、`browser`（3 PNG + results）、`discovery`、`discovery-toast`、`react-bits-preview`（三尺寸网页 + tooltip-open）、`design-knowledge-smoke.txt`。精选 TEST 图在 `docs/ui-polish/evidence/`。

精选像素证据：[首页宽窗浅色](ui-polish/evidence/home-desktop-light.png)、[管家宽窗浅色](ui-polish/evidence/assistant-desktop-light.png)、[健康宽窗浅色](ui-polish/evidence/health-desktop-light.png)、[首页窄窗深色](ui-polish/evidence/home-narrow-dark.png)、[管家窄窗深色](ui-polish/evidence/assistant-narrow-dark.png)、[原康复工作区窄窗深色](ui-polish/evidence/rehab-workspace-narrow-dark.png)。

### 实际看到的问题（只记录，未修）

| 页面/证据 | 观察 | 后续建议 |
| --- | --- | --- |
| 首页 light/窄窗 dark | “需要你确认”与今日概况任务/用药信息重复；待确认卡内部留白较多；窄窗训练计划需在较低位置阅读 | 优先整理主行动/次要摘要密度，保留全部按钮和安全说明 |
| AI 康复管家 | 全局页名和内层“康复管家”标题重复；能力说明、澄清状态、记录结果入口视觉竞争；浅色用户消息矩形较宽，聊天与输入区之间较大空白 | 比较 Prompt Bar 的信息分组，保留记录授权/忙碌/停止等现有语义；空白可能是底部固定 composer 的合理取舍，先对长对话复核 |
| 健康页 | 无完整数据时多次“资料不足”；摘要、近期指标与下方大空白的间距偏松 | 凝聚空态/摘要层级，不能编造健康判断或删除缺测标识 |
| 原康复工作区 dark | 外层深色产品与内层浅色原工作区、紫色身体导航形成明显主题断层 | 单独列为未来主题适配范围，先冻结训练/相机/确认/错误与数据契约；本轮不修 |

这只是环境 smoke 的初步视觉发现，不是完整 accessibility、motion、所有功能验收，不宣称当前 UI 已 polish 合格。

## UI Polish Mode

以后“进入 UI polish mode”会读取项目 Skill，先冻结功能并截图，再定 typography/spacing/palette/density/surface/radius/motion/iconography；把页面拆成 primitives，查成熟来源后决定复用/适配；只改 presentation，实际截图复审与针对性回归后迭代。允许必要 layout/widget/DOM 重组，不改变产品功能含义。无 card soup、无无意义模板装饰、焦点/contrast/状态/响应式与原有流程都是验收条件；build/test PASS 不是视觉 PASS。

知识库 smoke 的设计系统生成命令确实可运行，但返回 Trust & Authority/Conversion、Contact Sales/hero 等营销结构，**语义不适合本桌面康复产品，已拒绝采用**。Skill 已加入这项候选审查约束；本轮没有写产品 token 或重设设计方向。

## Smoke Test

| 检查 | 结果 | 证据/边界 |
| --- | --- | --- |
| 1. Design skill 可读取/调用 | PASS | 四个 SKILL frontmatter validator PASS；BM25 focus 查询返回实际 CSV；data validator 验证 12 domains/22 stacks/ui-reasoning；design-system 生成可运行但营销 pattern 被拒；110 文件来源 hash 校验 |
| 2. React Bits discovery | PASS | 五项 JSON/source/props/依赖；完整目录 query toast 找到 SwipeToast；Warm Tooltip hover/Escape 实测 |
| 3. Browser automation 启动 | PASS（替代后） | 原默认 Chromium FAIL 已记录；现有 Edge launch PASS，无新浏览器下载 |
| 4. 当前产品可运行 | PASS，限定 QA | 实际 Qt ProductWindow + 真实 Runtime/bridge/ProductService，临时 TEST 数据；不代表完整带权重训练 |
| 5. 浏览器访问当前产品 | N/A | 正式 Qt 无 URL；本地 127.0.0.1 QA 页面访问 PASS，未误报为正式产品 |
| 6. Screenshot | PASS | Qt 88 PNG；browser 3 viewport；React Bits reference 三尺寸与 tooltip-open |
| 7. 基于 screenshot 审查 | PASS | 实际打开首页/管家/健康浅色及首页/管家/原工作区窄窗深色、React Bits preview；精选图可复查 |
| 8. 识别现有 UI 问题 | PASS | 上表四页观察；没有修复 |
| Desktop viewport | PASS | web 1440×940；Qt 1440×940 |
| Tablet/mobile viewport | PASS，web 能力 | fixture 768×1024/390×844；Qt 产品没有已验收 tablet/mobile UI |
| Console/pageerror 收集 | PASS（收集能力） | fixture 三尺寸 errors=[]；React Bits 预览有 connection closed/403，因此外部页面零错误验收 FAIL，保留原记录 |
| Qt errors/交互 | PASS，限定 smoke | 两次 capture 退出 0，无捕获到的新 Qt traceback；九页无横向 overflow、composer/返回 assertions PASS；非全量黑箱 |
| 本轮 UI 修改禁止 | PASS（本轮提交范围） | 只提交 skills/tools/docs/AGENTS/ignore；其他会话变化独立保留 |

## Project Changes

版本控制改动仅：`AGENTS.md`、`.gitignore`、`.agents/skills/{ui-polish,ui-ux-pro-max,frontend-design,pyside6-fluent-ui}/`、`tools/ui-polish/`、`docs/UI_ENVIRONMENT_REPORT.md`、`docs/ui-polish/`。仓库外新增上层 `康复/AGENTS.md` 为本工作区定位入口。`.venv-ui-polish` 和 `qa-output/ui-env` 为本机忽略的依赖/证据/调研 clone，不提交第三方 `.git`、下载组件源码或数据库。

本轮没有 stage/commit 用户或其他会话的 product/backend、native_voice、voice_transcribe、product UI、测试和既有工具变更。没有改 main、没有 merge。

## Risks

- React 组件不能直接放入 Qt；必须逐项评估适配成本、keyboard/focus、reduced motion、授权和业务语义，不新增 web runtime。
- React Bits Commons Clause 限制组件本身再分发/port，Pro 内容未授权；不要发布复制组件的独立库。
- pyside skill 为 rc snapshot；pro-max 搜索结果可偏营销/web，已明确候选审查。Skill 文件可含执行建议，本轮先审查来源/脚本，未执行未知 installer。
- registry 会变；抓取时间/source/hash 可复查，更新仍需重新 smoke。demo 外部资源失败未被忽略。
- Windows DPI、Qt 最小宽度和字体与 web viewport 不同，不能拿 browser mobile PASS 代替 Qt 可用性。
- 同步目录/并发会话的 working tree 可能变化；本轮仅拥有环境文件，截图基线不保证等于单一 Git commit。

## Missing Capabilities

- 无正式 web target，因此“浏览器打开 Qt 产品”不适用；原生链路已替代。移动端正式 UI、真人训练/摄像头/语音、完整带权重 Python 3.13 环境不在本轮验收。
- 没有新增/连接 shadcn MCP，结构化 registry 已直接跑通。需要 MCP 专用 tools 时再以固定版本审查官方桥梁；当前不必引入服务来重复 fetch。
- 没有证明新会话自动 skill 扫描/热加载；AGENTS 文件读取兜底已建立。
- 尚未完成所有视图、状态、对比度实测、屏幕阅读器、OS Snap、高 DPI 全矩阵；未来按 polish 范围补足。

## Recommended Next Step

下一轮从 **首页 → 今日恢复** 开始，先拿本轮首页宽/窄图做功能冻结与视觉基线，减少重复摘要、明确下一步，不触动自动计划/医疗判断。之后处理 AI composer 信息层级，再单独协调原训练工作区的主题断层。本轮到环境交付为止，没有开始以上美化。
