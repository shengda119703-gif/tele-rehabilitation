# 项目协作约定

## Git 提交与上传

- 本项目的 GitHub 仓库为 https://github.com/nishaoxin/health-care-software ，远端名称为 `origin`，当前主分支为 `main`。
- 用户要求：每次完成本项目更新，都要在适当验证后提交本次改动，并推送到上述仓库的对应分支。此要求同样适用于文档和配置更新。
- 推送后核对远端分支与本地提交一致。推送失败时说明实际原因，不把本地提交称为已上传。
- 遵循已有 `.gitignore`，保留本地环境、模型权重、用户数据和运行日志的忽略规则。

## 应用开发

先读 `docs/HANDOFF.md` 了解当前版本、已验证内容和未完成目标。修改 `rehab_codex_single_camera_v2_1/` 中的内容时，继续遵循该目录的 `AGENTS.md` 与 `docs/specifications/SOFTWARE_SPEC.md`。

项目文档集中放在 `docs/`；版本历史与旧验收记录分别放在 `docs/history/`、`docs/validation/`，不能把旧测试计数或同学电脑上的环境描述当作本机最新结果。原实施包文档在 `docs/archive/original-v2.1/`。

应用目录名称保留以兼容现有独立环境和数据位置。外来整包先放入 `backups/incoming/` 并记录 SHA256，再检查 Git 历史和未提交改动；不把压缩包中的 `.git`、虚拟环境或个人数据库直接覆盖到当前项目。
