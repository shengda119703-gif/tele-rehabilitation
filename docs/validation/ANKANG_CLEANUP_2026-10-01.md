# 恢复 main 康复基线与安康 core 盘点：清理报告

日期：2026-10-01（Asia/Hong_Kong）。目标仓库 `shengda119703-gif/tele-rehabilitation`，持续分支 `codex/rehab-agent-stage1`。本轮没有 merge main，没有进入 B，没有连接 bridge、Home Twin 或修改康复算法/UI。

## 基准、历史与工作区检查

开始时工作区 clean，本地 HEAD 与 GitHub 同名分支一致：`e4e8a9510d519c93c8cae698cad06f18840d563e`。已 fetch/ls-remote 核实当前 main：`2ebc388d4160d647456487007670d89f02f80914`；它是 HEAD 的祖先，开始时 ahead 13 / behind 0。因此本次 `main...HEAD` 与直接 main→HEAD 的文件差异基准一致。

实际工作副本为 `C:\Users\Sophie\SynologyDrive\大学\学习\比赛+课题\康复\tele-rehabilitation`。检查了 tracked 差异、未跟踪文件、忽略的依赖/缓存以及提交历史；开始时没有用户未提交改动。保留工作副本里的本地 node_modules、构建/测试输出及被忽略的 `backups/incoming`，它们不是 tracked 源码。本轮测试新输出放在外层 `.runtime/ankang-cleanup/`。没有删除外层旧交付文档、A3 资料、本机旧 `_ui_review_repo` 或只读原安康项目，也没有修改用户数据库。

分支历史审计覆盖从 main 后的全部 13 提交：`a693f09`（0.19 入口）、`3af5bad`（对话适配）、`e08c890`（DeepSeek）、`656fcb4`（回复恢复）、`155f228`（上下文）、`3fc02a1`（变化解释）、`76cd66a`（分支约定）、`fcbf65b`（隐私/迁移）、`f0840fd`（A1）、`2645659`（UI）、`ac1642c`（A2）、`dae638d`（A3）、`e4e8a95`（上游导入）。清理覆盖完整分支增量，不只是名字含 A1/A2/A3 的文件。

## 第一提交：严格恢复 tracked tree

清理提交：**`ee3ebaca69541ebc66cd29236b2d34cc073aade0`**，标题 `chore: remove abandoned python agent experiments`。

以 Git tree/blob 而非文件名为准，共审计非 ankang 变化 **49 个**：7 个 main 已存在文件精确恢复，42 个分支新增文件删除。执行的是对这 49 个经验证的仓库内路径 `git restore --source=<main SHA> --staged --worktree`；没有覆盖/删除其它路径，没有修改 ankang，没有重写历史。

特殊项说明：

- `agent_privacy.py`、`rehab_agent.py`、相关 UI/QA/测试在 main 均不存在，因此按分支新增删除；没有因名称相似删除 main 原有银发模块。
- runtime、main_window、workspace、版本号恢复原 blob，Agent import、runtime command 接线和入口按钮随之撤销；应用版本回到 main 的 **0.18.3**。
- 根 `AGENTS.md` 也精确恢复，因此它包含 main 的历史仓库名称 `nishaoxin/health-care-software`。这不改变真实 `origin`；用户本轮明确指定的 tele-rehabilitation 与开发分支优先，未切换仓库或 main。
- 上轮 `docs/validation/ANKANG_UPSTREAM_IMPORT_2026-10-01.md` 虽然不是 Python 试验，仍是非 ankang 分支新增；为满足第一提交的严格 tree 目标一并删除。它可在 [导入提交的历史文件](https://github.com/shengda119703-gif/tele-rehabilitation/blob/e4e8a9510d519c93c8cae698cad06f18840d563e/docs/validation/ANKANG_UPSTREAM_IMPORT_2026-10-01.md) 查看。`ankang/UPSTREAM.md` 原内容及其中历史相对链接未改写；该旧链接当前不再有工作树目标，这是严格保持 ankang 原样的已知文档限制。

### 清理前 main...HEAD 的全部非 ankang changed files

M=main 已存在且被分支修改；A=仅分支新增。下表最后一列由逐路径 Git log 取得，便于追溯，不是按文件名推断归属。

| 路径 | 清理前 main→HEAD 状态 | 清理动作 | 本分支最早涉及提交 |
| --- | --- | --- | --- |
| `AGENTS.md` | M | 恢复 main blob `4cfaadadcf64` | `76cd66a` |
| `docs/HANDOFF.md` | M | 恢复 main blob `6b89864e8bac` | `a693f09` |
| `docs/history/AGENT_PROGRESS_V0_22.md` | A | 删除分支新增 | `3fc02a1` |
| `docs/history/ANKANG_CONVERSATION_V0_20.md` | A | 删除分支新增 | `3af5bad` |
| `docs/history/CHANGELOG.md` | M | 恢复 main blob `fc4b4a89c0d6` | `a693f09` |
| `docs/history/DEEPSEEK_REHAB_AGENT_V0_21.md` | A | 删除分支新增 | `e08c890` |
| `docs/history/REHAB_AGENT_STAGE1_V0_19.md` | A | 删除分支新增 | `a693f09` |
| `docs/plans/AGENT_STAGE_A_UI_AND_DATA.md` | A | 删除分支新增 | `f0840fd` |
| `docs/plans/ANKANG_AGENT_MIGRATION_AND_UI.md` | A | 删除分支新增 | `fcbf65b` |
| `docs/validation/AGENT_STAGE_A2_2026-09-29.md` | A | 删除分支新增 | `ac1642c` |
| `docs/validation/AGENT_STAGE_A3_2026-09-30.md` | A | 删除分支新增 | `dae638d` |
| `docs/validation/AGENT_STAGE_A_2026-09-29.md` | A | 删除分支新增 | `f0840fd` |
| `docs/validation/AGENT_STAGE_A_UI_2026-09-29.md` | A | 删除分支新增 | `2645659` |
| `docs/validation/ANKANG_AGENT_PRIVACY_V0_22_1_2026-09-28.md` | A | 删除分支新增 | `fcbf65b` |
| `docs/validation/ANKANG_CONVERSATION_2026-09-28.md` | A | 删除分支新增 | `3af5bad` |
| `docs/validation/ANKANG_UPSTREAM_IMPORT_2026-10-01.md` | A | 删除分支新增 | `e4e8a95` |
| `docs/validation/DEEPSEEK_REHAB_AGENT_2026-09-28.md` | A | 删除分支新增 | `e08c890` |
| `docs/validation/REHAB_AGENT_STAGE1_2026-09-28.md` | A | 删除分支新增 | `a693f09` |
| `rehab_codex_single_camera_v2_1/app/__init__.py` | M | 恢复 main blob `041797a583c2` | `a693f09` |
| `rehab_codex_single_camera_v2_1/app/agent_conversation.py` | A | 删除分支新增 | `3af5bad` |
| `rehab_codex_single_camera_v2_1/app/agent_extraction.py` | A | 删除分支新增 | `ac1642c` |
| `rehab_codex_single_camera_v2_1/app/agent_grounding.py` | A | 删除分支新增 | `dae638d` |
| `rehab_codex_single_camera_v2_1/app/agent_privacy.py` | A | 删除分支新增 | `fcbf65b` |
| `rehab_codex_single_camera_v2_1/app/agent_state.py` | A | 删除分支新增 | `dae638d` |
| `rehab_codex_single_camera_v2_1/app/agent_statements.py` | A | 删除分支新增 | `f0840fd` |
| `rehab_codex_single_camera_v2_1/app/rehab_agent.py` | A | 删除分支新增 | `a693f09` |
| `rehab_codex_single_camera_v2_1/app/runtime.py` | M | 恢复 main blob `2abc219679d3` | `a693f09` |
| `rehab_codex_single_camera_v2_1/app/ui/agent_presentation.py` | A | 删除分支新增 | `2645659` |
| `rehab_codex_single_camera_v2_1/app/ui/main_window.py` | M | 恢复 main blob `b714d3fe2e39` | `a693f09` |
| `rehab_codex_single_camera_v2_1/app/ui/rehab_agent.py` | A | 删除分支新增 | `a693f09` |
| `rehab_codex_single_camera_v2_1/app/ui/workspace.py` | M | 恢复 main blob `c0e1cc3ba833` | `a693f09` |
| `rehab_codex_single_camera_v2_1/scripts/qa_agent_conversation.py` | A | 删除分支新增 | `3af5bad` |
| `rehab_codex_single_camera_v2_1/scripts/qa_agent_semantics_live.py` | A | 删除分支新增 | `dae638d` |
| `rehab_codex_single_camera_v2_1/scripts/qa_agent_statements.py` | A | 删除分支新增 | `f0840fd` |
| `rehab_codex_single_camera_v2_1/scripts/qa_deepseek_agent.py` | A | 删除分支新增 | `e08c890` |
| `rehab_codex_single_camera_v2_1/scripts/qa_rehab_agent.py` | A | 删除分支新增 | `a693f09` |
| `rehab_codex_single_camera_v2_1/tests/statement_fixtures.py` | A | 删除分支新增 | `ac1642c` |
| `rehab_codex_single_camera_v2_1/tests/test_agent_a3.py` | A | 删除分支新增 | `dae638d` |
| `rehab_codex_single_camera_v2_1/tests/test_agent_conversation.py` | A | 删除分支新增 | `3af5bad` |
| `rehab_codex_single_camera_v2_1/tests/test_agent_conversation_ui.py` | A | 删除分支新增 | `3af5bad` |
| `rehab_codex_single_camera_v2_1/tests/test_agent_dialog_interaction_ui.py` | A | 删除分支新增 | `2645659` |
| `rehab_codex_single_camera_v2_1/tests/test_agent_extraction.py` | A | 删除分支新增 | `ac1642c` |
| `rehab_codex_single_camera_v2_1/tests/test_agent_statements.py` | A | 删除分支新增 | `f0840fd` |
| `rehab_codex_single_camera_v2_1/tests/test_agent_statements_runtime.py` | A | 删除分支新增 | `f0840fd` |
| `rehab_codex_single_camera_v2_1/tests/test_agent_statements_ui.py` | A | 删除分支新增 | `f0840fd` |
| `rehab_codex_single_camera_v2_1/tests/test_rehab_agent.py` | A | 删除分支新增 | `a693f09` |
| `rehab_codex_single_camera_v2_1/tests/test_rehab_agent_runtime.py` | A | 删除分支新增 | `a693f09` |
| `rehab_codex_single_camera_v2_1/tests/test_rehab_agent_ui.py` | A | 删除分支新增 | `a693f09` |
| `打开康复管家.cmd` | A | 删除分支新增 | `76cd66a` |


### 精确一致性验证

| 项目 | 实际结果 |
| --- | --- |
| main tracked 文件 | **292 个全部保留**，内容及模式与当前 main 一致 |
| 第一提交 `ankang/` 外 diff main | **空** |
| 第一提交 `ankang/` diff 导入提交 | **空**，含 UPSTREAM.md、所有 upstream 文件 |
| 完整 ankang tree SHA | `1e3d7c2533554e45f120699892552a3939cf690a`，与 e4e8a95 完全一致 |
| 第一提交根 tree SHA | `cab7fc2199eeb0a833a5c39eea3e5c47421a56ea` |
| Python 生产/测试残留引用扫描 | `agent_conversation/extraction/grounding/state/statements/privacy`、`rehab_agent`、`agent_presentation`、`康复管家` 在现有应用目录 tracked 文件中无匹配 |
| 第一提交后的工作区 | clean；相对 main ahead **14** / behind **0** |

复核命令（不做 merge）：

```sh
git diff --exit-code 2ebc388d4160d647456487007670d89f02f80914 ee3ebaca69541ebc66cd29236b2d34cc073aade0 -- . ':!ankang'
git diff --exit-code e4e8a9510d519c93c8cae698cad06f18840d563e ee3ebaca69541ebc66cd29236b2d34cc073aade0 -- ankang
git rev-parse ee3ebaca69541ebc66cd29236b2d34cc073aade0:ankang
```

## main 原康复启动与回归实际结果

使用 main 原 `scripts/check_project.py`、原 pytest 文件和 `python -m app.main`，没有修改测试或生产代码。临时测试环境为现有隔离 Python **3.12.14**；main 安装文档推荐 Python **3.13**，本轮未宣称完成 3.13 全新安装验证，也没有安装大模型/YOLO 权重。此新工作副本没有独立 `.venv`，原 `Start-Rehab.ps1` 仍会要求先 Setup；本轮用显式 Python 路径验证相同 `app.main` 入口。

起初 pytest 在收集前遇到缺 pygments；仅在工作区外层临时目录补装 `pygments 2.21.0`、`colorama 0.4.6`、main 指定的 `opencv-python 4.12.0.88`，不改 requirements。随后沙箱读该临时目录受限，改为有权限的环境；用户 site-packages 自动注入 xonsh 插件又触发 `NoConsoleScreenBufferError`，最终以 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 隔离无关插件。上述初始化失败不是项目测试断言失败，日志均保留。

有效回归命令：设 `PYTHONPATH=<工作区>/.runtime/ankang-cleanup/python-deps`、`PYTHONUTF8=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，运行 `python scripts/check_project.py --suite all --timeout 300 --output <独立日志目录>`。该 main runner 在一个真实缺模型失败处停止，随后用原 pytest 命令运行剩余三个文件，未重复计算已通过测试。

| 原测试组/文件 | 结果 |
| --- | --- |
| core，45 文件 | 1008 passed，另 4 subtests passed |
| ui，23 文件 | 408 passed |
| test_app_joint_expansion_flow | 18 passed，3 skipped（可选模型未准备） |
| test_app_landmarks | 177 passed，3 skipped（可选 runtime/models 未准备） |
| test_app_runtime_integration | 2 passed，1 skipped（官方模型未准备） |
| test_app_source_integration | 1 passed |
| test_app_vision_integration | 1 passed，1 skipped（权重/视觉依赖未准备） |
| test_camera_test_integration | 3 passed |
| test_dual_runtime_integration | 5 passed |
| test_dual_vision_integration | **1 failed**：`app/vision.py:36` 抛“尚未配置本地 YOLO11n-pose 权重，程序不会自动下载” |
| 剩余 guided_runtime / model_paths / quiet_runtime | 合计 6 passed，6 skipped（可选已验证 runtime/models 未准备） |
| 总计，79 文件 / 1644 主测试 | **1629 passed、14 skipped、1 failed**，另 **4 subtests passed** |

唯一项目断言执行失败来自 main 本就要求的本地权重缺失；该测试及 vision.py 与 main blob 完全相同，未归因为代码清理回归。模型相关跳过不等于模型功能已验证。没有为了通过去修改/跳过/放宽失败测试，也没有复制用户数据或自动下载模型。完整回归不是全绿。

离屏启动：在独立临时数据目录执行原 `python -m app.main --data-dir ... --screenshot ...`，退出 0；已查看截图，身体评估/训练/档案/历史/银发入口正常显示，底部 0.18.3，无康复管家按钮，相机未打开。仅证明软件入口可启动，不代表实机摄像头或模型准确度验收。

文档检查：原 `scripts/check_docs.py` 检查 255 个相对链接，发现 1 个失效链接：`ankang/UPSTREAM.md` 指向已按严格清理要求删除的旧导入报告 `docs/validation/ANKANG_UPSTREAM_IMPORT_2026-10-01.md`。为保证 ankang 快照不变，本轮没有修改该链接；旧报告仍可从导入提交历史查看。两份新增文档未报告失效链接。

## 第二提交与交付口径

第二提交标题为 `docs: define imported ankang agent core boundary`，只新增：

- [core 边界盘点](../plans/ANKANG_CORE_BOUNDARY.md)；
- 本清理报告。

因此最终状态是 **main 全部原内容 + 未改动的 ankang + 用户本轮要求的两份新文档**。第一提交严格满足“非 ankang tracked tree 与 main 一致”；第二提交之后，两份文档是明确、唯一的非 ankang 差异，不能把最终 tree 说成除了 ankang 毫无差异。没有恢复已删除的 A1–A3 文档、入口或 Python 实现。

本报告记录的清理后分支 SHA 是 `ee3ebaca69541ebc66cd29236b2d34cc073aade0`。包含本报告的第二提交本身无法在其内容中写入自身完整 SHA；**最终完整 SHA 以交付答复和同分支 `git rev-parse HEAD` 为准**，以下命令可核对两个提交、远端、ahead/behind 与 clean 状态。完成第二提交后预期相对 main 为 ahead 15 / behind 0，交付时须实查。

```sh
git log -2 --format='%H %s'
git ls-remote origin refs/heads/codex/rehab-agent-stage1 refs/heads/main
git rev-list --left-right --count origin/main...HEAD
git status --porcelain
git diff --name-status origin/main HEAD -- . ':!ankang'
git diff --exit-code e4e8a9510d519c93c8cae698cad06f18840d563e HEAD -- ankang
```

本轮到此停止，等待用户审核后才讨论 core 抽取或分批裁剪。
