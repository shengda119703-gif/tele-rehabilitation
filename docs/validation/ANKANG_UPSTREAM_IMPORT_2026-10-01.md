# 原安康完整快照导入验收

日期：2026-10-01（Asia/Hong_Kong）。本轮只做上游快照迁入与原项目验证。暂停 A1/A2/A3 自研 Agent 路线，不进入 B、不接 Home Twin、不改 UI/康复动作算法、不删除上游或 Python Agent、不 merge main。

## 来源及范围

- 上游：`JerryFreeman333/fdu-hackthon`，GitHub `main` 已用 `git ls-remote` 核实为 `cbdc8f33a1cf3993b1f49a7b3046ceda1932c39b`。
- 目标：`shengda119703-gif/tele-rehabilitation`，`codex/rehab-agent-stage1` 导入前本地及远端 HEAD 均为 `dae638d26dcbd887fef70734a1480f45825ab5fa`。
- 目标 `origin/main`：`2ebc388d4160d647456487007670d89f02f80914`；导入前 ahead 12 / behind 0。
- 本机只读原项目实际在 `C:\Users\Sophie\.codex\.chatgpt-projects\g-p-6aa7c931ae7081919e73c0e8b21d2fc3\_fdu_hackthon_review`，HEAD 为较旧的 `5df927143e72e650476ef2bb32f776d5ff3329fc`。未改动它；从远端取得上述最新提交后导出。
- 本轮独立工作副本：`C:\Users\Sophie\SynologyDrive\大学\学习\比赛+课题\康复\tele-rehabilitation`，仍使用同一开发分支。旧 `_ui_review_repo` 未修改。

```text
ankang/
├── .github/workflows/     6 个上游文件（仅快照，不作为根 CI 启用）
├── .gitignore            原上游文件
├── README.md             原上游文件
├── docs/                 3 个上游文件
├── route1-health-agent/  243 个上游文件
├── route2-home-3d/       109 个上游文件
└── UPSTREAM.md           本轮新增来源及后续边界说明
```

上游全部 363 个文件逐一按 Git blob SHA-1 比较，内容一致；暂存区同时检查文件模式与 blob，363/363 一致。原 TypeScript 生产代码、测试、配置、锁文件没有重写、修补或翻译。目标根 `data/` 忽略规则会忽略上游演示源码/夹具，因此按上游精确清单纳入，不改目标根 `.gitignore`。

上游与目标暂存树的以下目录 Git tree SHA 也完全一致（同时覆盖内容、路径及文件模式）：

| 子目录 | 两边相同的 tree SHA |
| --- | --- |
| `route1-health-agent` | `79aa25e130197857a3ecbb047c0efcedbfce782a` |
| `route2-home-3d` | `4c05927db243d36b5f029faf53d1d11d7d4309af` |
| `docs` | `2659bff46592bd82c23ca878de862dfb36b4cdee` |
| `.github` | `f6522786c890e4496dc29b735a40e11db7075b30` |

没有复制上游 `.git`、已安装依赖、真实环境文件/密钥、用户数据、构建缓存、本地测试输出。上游跟踪的配置示例、合成演示数据、设计参考图片全部保留。导出归档及其 SHA-256 见 [UPSTREAM.md](../../ankang/UPSTREAM.md)。

## 原样运行环境

Windows x64；Node **22.14.0**；npm **10.9.2**。符合上游 CI 的 Node 22、`engines.node >=22`、`engines.npm >=10.9`，并精确匹配 `packageManager: npm@10.9.2`。Node 官网下载连接失败后，通过 npm registry 安装独立 `node-win-x64@22.14.0` 与 `npm@10.9.2` 工具，不改系统环境。原两个 package-lock.json 均保持原 blob。

完整本地日志、运行器和工具位于工作区 `.runtime/ankang-validation/`，不提交依赖或输出。实际 npm 脚本在 `ankang/route1-health-agent` 内运行。

## 核心实际结果

| 命令 | 结果 |
| --- | --- |
| `npm ci` | 通过；按原锁文件安装 78 个包；网络曾重置，重试后完成 |
| `npm run typecheck` | 通过 |
| `npm test` | **378 tests / 378 pass / 0 fail / 0 skip**，5 suites；顶层 TAP 编号 371，含子测试总数 378 |
| `npm run build` | 通过；155 modules。首次沙箱执行因 esbuild 访问上层目录被拒绝失败，授权环境下原命令重跑通过，未修改代码 |
| `npm run security:check` | 通过；未发现明显硬编码 API Key 或私钥 |
| `npm run test:healthkit` | 桥接场景通过；适配器 **10/10** 通过 |

上游 README 的“324 个单测 / 6 个 Playwright 黑盒”是历史描述，不能作为当前结果。本提交实际有 70 个 TypeScript 单测文件，原 npm test 执行得到上表的 378 项；package.json 有 8 个 `test:browser*` 脚本。HealthKit 的独立 10 项不混入 378 项计数。

原安装附带 audit 提示 **2 项依赖漏洞：vite high、esbuild moderate**，只读 `npm audit --json` 已核实。未执行 audit fix，未改锁文件。`security:check` 通过仅说明其密钥模式检查通过，不等于依赖无漏洞。

## 浏览器与其他验证

使用原锁定 Playwright **1.63.0** 及其 Chromium **153.0.8010.12 / revision 1243**。原 `package.json` 的 8 组浏览器脚本全部退出 0，共 **71/71 个脚本显式检查通过**：

| 原命令 | 通过检查数 |
| --- | --- |
| `npm run test:browser` | 16/16 |
| `npm run test:browser:sos` | 4/4 |
| `npm run test:browser:onboarding` | 10/10 |
| `npm run test:browser:webhook` | 9/9 |
| `npm run test:browser:notif` | 6/6 |
| `npm run test:browser:cross-device` | 6/6 |
| `npm run test:browser:binding` | 10/10 |
| `npm run test:browser:crosstab` | 10/10 |

补充运行 4 个未加入上述 npm 脚本链的现有 Route 1 浏览器脚本。独立本机 preview 在 5173 启动，源码没有改动：

| 脚本 | 导入副本结果 | 独立上游复核与归因 |
| --- | --- | --- |
| `demo-filled-browser.test.mjs` | 通过 | 演示数据、档案、药物与个人模式隔离 |
| `family-management-browser.test.mjs` | 失败：第 63 行旧文案等待超时 | 独立上游相同失败。上游 `FamilyDashboard.tsx` 已区分“未绑定”和“已绑定但未授权”，脚本仍期待前者旧文案；属于上游测试预期滞后 |
| `four-tab-flow.test.mjs` | 失败：第 21 行等待“我是老人”按钮超时 | 独立上游相同失败。当前上游 `FirstRunGate.tsx` 使用“我为自己使用”，脚本仍按旧首启文案定位；属于上游测试预期滞后 |
| `voice-dialog-browser.test.mjs` | 失败：第 26 行“取消按钮应在手机首屏内”断言 | 独立上游相同失败；当前 Windows/Chromium 390×844 环境的上游 UI/测试问题，未进一步改动或判定跨平台范围 |

为排除搬运影响，在本轮新克隆的 `.runtime/ankang-upstream`（同一 SHA，非用户只读原项目）复用同一份锁定 node_modules，通过目录 junction 提供依赖，原样重新 build，再运行上述 3 个失败脚本；失败点全部一致。复核后上游工作树无受版本控制文件修改，导入区 363 个文件仍逐字节匹配上游。没有通过修改生产代码、测试选择器或断言来变绿。**完整测试集合并非全绿**，应保留上述失败作为后续基线记录。

独立 `p0-blackbox` 使用其原 package-lock.json 执行 npm ci 成功（2 个包，audit 0）。原 `npm run blackbox` 在 Windows 启动 Vite 时即报 `spawn npm ENOENT`：脚本直接 spawn `npm`，未适配 Windows `.cmd`，且使用 URL pathname 作为路径。**9 个场景未执行**；属于上游测试入口的平台兼容限制，不是搬运内容丢失。本轮不修改该脚本或生产代码来消除失败。

真实 LLM、真实 HealthKit/iPhone、真实推送服务及硬件没有配置，未声称通过现场验证；自动化中的 mock、合成数据和浏览器权限模拟不代表真实服务。Route 2 只原样保存，不运行接入/建模流程；`home-capture-browser.test.mjs` 面向 5174 的 Route 2，不在本轮 Route 1 独立验证范围。

## 完整性与下一步边界

本轮只新增 `ankang/` 和本验收文档；既有康复 Python 项目及根 README/.github/.gitignore 未修改，既有生产路径未切换。导入后仍需用户确认，再开始依赖/功能盘点。后续按 Agent core、康复可能复用、明确无关分类；删除分批进行，每批重跑原 Agent 测试。0.19–0.25 Python Agent 保留，退出生产路径的决定留待后续。
