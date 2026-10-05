# 项目协作约定

## UI Polish Mode

当用户说“进入 UI polish mode”或明确请求纯视觉打磨，先读取 `.agents/skills/ui-polish/SKILL.md`，执行其功能冻结、截图审查、设计系统、组件采购、呈现实现与回归闭环。项目正式 UI 是 PySide6/Qt Widgets；React Bits 是组件发现与交互参考，不能因此引入 React 或重写产品。业务/API/Runtime/数据/医疗/Agent/路由和状态语义冻结。常见 UI primitive 必须 SEARCH BEFORE INVENT。构建通过不能代替实际截图审查。环境配置/审计请求不授权修改正式 UI。

Skills 固定在 `.agents/skills/`，依赖来源和 hash 在 `tools/ui-polish/sources.lock.json`。新会话未自动列出 skill 时，依此规则显式读取文件。操作命令、维护方法和已验证边界见 `docs/ui-polish/WORKFLOW.md` 和 `docs/UI_ENVIRONMENT_REPORT.md`。保留其他会话正在修改的文件，只提交本轮自己负责的文件。

## Git 提交与上传

- 每次完成版本更新，维护桌面 `安康康复（最新版本）.lnk`，使用 `New-RehabDesktopShortcut.ps1` 指向当前仓库的 `Start-Rehab.ps1` 和本机实际已验证的 Python 环境；提交后更新快捷方式版本描述。交付时明确告知桌面入口、页面导航及版本号。不要关闭用户尚未保存的旧窗口。

- 本项目的 GitHub 仓库为 https://github.com/shengda119703-gif/tele-rehabilitation ，远端名称为 `origin`，当前主分支为 `main`。
- 用户要求：每次完成本项目更新，都要在适当验证后提交本次改动，并推送到上述仓库的对应分支。此要求同样适用于文档和配置更新。
- 推送后核对远端分支与本地提交一致。推送失败时说明实际原因，不把本地提交称为已上传。
- 遵循已有 `.gitignore`，保留本地环境、模型权重、用户数据和运行日志的忽略规则。

## 应用开发

先读 `docs/HANDOFF.md` 了解当前版本、已验证内容和未完成目标。修改 `rehab_codex_single_camera_v2_1/` 中的内容时，继续遵循该目录的 `AGENTS.md` 与 `docs/specifications/SOFTWARE_SPEC.md`。

项目文档集中放在 `docs/`；版本历史与旧验收记录分别放在 `docs/history/`、`docs/validation/`，不能把旧测试计数或同学电脑上的环境描述当作本机最新结果。原实施包文档在 `docs/archive/original-v2.1/`。

应用目录名称保留以兼容现有独立环境和数据位置。外来整包先放入 `backups/incoming/` 并记录 SHA256，再检查 Git 历史和未提交改动；不把压缩包中的 `.git`、虚拟环境或个人数据库直接覆盖到当前项目。
