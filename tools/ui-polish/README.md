# UI 环境工具

在仓库根目录运行。正式产品是 Qt；下列工具都不修改正式 UI。

## 一次环境准备

Node 包复用 `ankang/route1-health-agent/package-lock.json` 中的 Playwright 1.63.0。已有依赖不重装；新 checkout 可在该目录运行 `npm ci --ignore-scripts`，然后执行既有 bridge build。默认浏览器使用已安装的 Edge；Chrome 可设置 `UI_BROWSER_CHANNEL=chrome`。没有已安装浏览器时才用现有 Playwright CLI 安装浏览器。不要把浏览器可执行文件写入 Git。

优先用已具备依赖的项目 Python（通过 `capture-qt.ps1 -PythonPath ...`）。本机无可用 Qt 环境，故本轮建立根目录 `.venv-ui-polish`，仅用于隔离 TEST 视觉 QA：

```powershell
python -m venv .venv-ui-polish
./.venv-ui-polish/Scripts/python.exe -m pip install -r tools/ui-polish/requirements-qa.lock.txt
./.venv-ui-polish/Scripts/python.exe -m pip check
node ankang/route1-health-agent/scripts/build-agent-bridge.cjs
```

这是 Python 3.12 QA 环境，不含 YOLO/torch/ASR 权重，不代替 `Setup-Rehab.ps1` 的完整 Python 3.13 正式环境。不能据此宣称摄像头/真人训练通过。使用既有工具启动正式 ProductWindow/Runtime/ProductService，全部数据在临时目录。

## 可复用命令

```powershell
python .agents/skills/ui-ux-pro-max/scripts/search.py 'focus not obscured' --domain ux -n 2
python tools/ui-polish/verify-sources.py
python .agents/skills/ui-ux-pro-max/scripts/search.py 'rehabilitation elderly accessible' --design-system -p Ankang
node tools/ui-polish/discover-components.mjs all
node tools/ui-polish/discover-components.mjs tooltip
node tools/ui-polish/browser-smoke.cjs
node tools/ui-polish/inspect-web.cjs https://reactbits.dev/c/micro/warm-tooltip qa-output/ui-env/react-bits-preview
./tools/ui-polish/capture-qt.ps1 -Width 1440 -Theme light
./tools/ui-polish/capture-qt.ps1 -Width 1024 -Theme dark
```

知识检索不使用 `--persist`，避免擅自覆盖设计系统。确认本轮设计决策后才将设计系统保存到明确输出目录。所有工具输出默认 `qa-output`（Git 已忽略）。`discover-components` 只 fetch JSON，不 npm add、不执行 registry 源码；保留 catalog、完整 props/source、依赖和抓取时间。新候选可从 `https://reactbits.dev/r/registry.json` 读取目录，再审查 item。常见五类有快捷查询。

`browser-smoke` 使用临时 127.0.0.1 随机端口，验证三种 viewport、截图、按钮交互和 console/pageerror；关闭后释放 server/browser。它是 QA fixture，不是正式 Qt UI。`inspect-web` 对真实网页生成三种 viewport/正文/console 证据，不自动提交业务表单；网页检查应再基于可见结构实施 keyboard/hover/click 测试。Qt 产品没有浏览器 URL，使用 Qt 截图/QTest，不伪造为 web 产品。

## 证据和维护

打开实际 PNG 做像素审查，不能只读 observations.json。记录 screenshot 文件、logical size/DPR、主题、测试数据、发现/优先级/功能影响。选入 Git 的图只允许 TEST 内容。本机 Windows Computer Use `@oai/sky` 可通过现有 node_repl 使用；遵循安装插件的 SKILL.md/guidance/api。不要新造底层截图 helper。

Skills 位于 `.agents/skills`，无需用户级安装。`sources.lock.json` 记录 revision、许可和文件 SHA256（文本先归一化 CRLF→LF，与 Git 换行规则一致）。更新时：clone 到忽略的 `qa-output` → 查看 diff/许可/脚本 → 替换选定文件 → 重跑知识检索/registry/browser/Qt → 更新 hash 与报告 → 提交。禁止执行第三方一键安装脚本。Qt skill 本机已装的用户级原件保持不变；项目快照保证可移植。删除环境时仅移除已确认位于仓库内的 `.venv-ui-polish` 和本套 skills/tools/docs，并从 AGENTS.md 删除对应规则；不能删除正式数据或其他人的工作。

本会话新增 Skill 通过文件读取调用；新会话的自动发现依 Codex skill 扫描，AGENTS.md 提供显式读取兜底。不要声称热加载或跨机/browser 已永久生效。
