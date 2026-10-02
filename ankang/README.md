# Ankang 正式产品内核

当前目录保留正式 PySide6 居家康复助手使用的 TypeScript Agent Runtime、ProductService、业务服务、ports/adapters、Python/Node 桥接及外部 HealthKit companion。正式入口为仓库根的 `启动康复助手.cmd`，不启动 React/Vite。

`route1-health-agent/src/runtime` 是 Agent 内核；`src/product` 聚合用药、照护圈、共享、健康档案、通知、历史/趋势与扩展能力。`scripts/agent-bridge.cjs` 与 `bridges/ankang/client.py` 连接正式桌面产品。浏览器 Voice/PeerJS 等 adapter 是保留的外部宿主接口，Windows 未配置时不会伪装可用。

2026-10-02 在 `codex/product-ui-v1` 清理不参与正式运行的 React UI/hooks、浏览器 demo/验收、旧设计演示和独立 Home Twin/Route2/3DGS。Route2 的硬件中立 capture 契约已原样迁到 `app/product/capture_contracts.py`；空间架构文档在 [历史归档](../docs/archive/ankang-route2/README.md)。

参见[清理与依赖审计](../docs/validation/REPOSITORY_CLEANUP_2026-10-02.md)和[原始来源](UPSTREAM.md)。完整原实现可从 `codex/rehab-agent-stage1`（`4b2d108a3003d84c89ac42da25580017d5b1de17`）恢复；本轮不改 main/stage1，不增加业务能力。
