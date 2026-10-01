# 安康原项目快照来源

- Upstream repository: https://github.com/JerryFreeman333/fdu-hackthon
- Imported upstream commit SHA: `cbdc8f33a1cf3993b1f49a7b3046ceda1932c39b`
- Import date: **2026-10-01**（Asia/Hong_Kong）
- 状态：**第一阶段为原样快照，尚未裁剪/集成**。
- 目标分支：`codex/rehab-agent-stage1`；导入前 HEAD：`dae638d26dcbd887fef70734a1480f45825ab5fa`。

## 导入范围与完整性

从已核实的上游 Git 提交导出，而非复制旧工作区或重新实现 Agent。363 个上游受版本控制文件全部保留：`route1-health-agent/` 243 个，`route2-home-3d/` 109 个，`docs/` 3 个，`.github/` 6 个，根 `README.md` 与 `.gitignore` 各 1 个。导入文件逐一与上游 Git blob SHA-1 核对，原始内容一致；本文件为迁移新增说明。

上游 `.github/`、README、忽略文件保留在本目录，未覆盖目标仓库根文件。嵌套 `.github/workflows/` 仅作为上游快照保留，不会自动成为目标仓库根 CI。

未复制原仓库 `.git`、`node_modules`、真实 `.env`、API Key/secrets、构建缓存、本地测试输出或用户数据。上游已跟踪的 `.env.example`、`.env.hardware.example` 是占位配置，保留；已跟踪的设计参考图片、演示源码及 JSON 夹具同样保留，它们不是本机用户数据。未按文件名裁剪任何上游文件。

导入归档暂存于目标工作副本被忽略的 `backups/incoming/ankang-cbdc8f3.zip`，不提交。归档 SHA-256：`f44ee67fe70d7ebc6d5a6e4964aab87783ab030a76deed326f7d94ff42329dc4`。导出关闭 Windows 自动换行转换，以保持 blob 内容一致。

## 验证

使用原 `package-lock.json`；Node 22.14.0（上游 CI 使用 Node 22，engines 要求 >=22）、npm 10.9.2（原 `packageManager`）。实际结果见 [原样快照验收](../docs/validation/ANKANG_UPSTREAM_IMPORT_2026-10-01.md)。依赖、浏览器、日志、测试截图及构建产物仅用于本地验证，不提交。

## 后续原则（本轮不执行）

暂停 A1/A2/A3 Python Agent 重实现，不进入 B。以本快照中的原 TypeScript Agent 作为后续正式基线；本次尚未切换现有康复应用的生产入口。

等待用户确认后，先做依赖/功能盘点，再区分 Agent core 必须保留、康复可能复用、明确无关可删除三类。任何删除分批进行，每批重新运行原 Agent 测试；不得凭文件名或感觉大规模删除。

保留原 0.19–0.25 Python Agent 文件；待原 TypeScript Agent 在目标仓库原样跑通后，再决定哪些 Python 文件退出生产路径。不接 Home Twin、不重做 UI、不修改康复动作算法、不 merge main。
