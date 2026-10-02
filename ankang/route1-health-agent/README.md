# Ankang Runtime / ProductService

正式产品为 PySide6 居家康复助手。本目录提供 TypeScript 业务内核与 Node 桥接，不再提供 React/Vite 页面或 `npm run dev` 入口。

```powershell
npm ci --no-audit --no-fund
npm run build
npm run test:product
```

日常启动从仓库根执行 `Start-Rehab.ps1` 或双击 `启动康复助手.cmd`。启动脚本会构建 `.bridge-build`，桌面 ProductBackend 经 JSON stdin/stdout 调用 `scripts/agent-bridge.cjs`。构建先清空本包的生成目录，避免已删除源码留下旧的可执行产物。

| 正式边界 | 位置 |
| --- | --- |
| Agent Runtime、multi-turn、rehab read tools | `src/runtime`、`src/engine`、`scripts/rehab-model.cjs` |
| 产品业务聚合 | `src/product/ProductService.ts` |
| 用药、家庭/共享、档案、通知、Person Twin | `src/medication`、`src/family`、`src/profile`、`src/archive`、`src/notification`、`src/personTwin` |
| HealthEvent 与设备数据 | `src/pipeline`、`src/types.ts`、`src/adapters` |
| Voice、同步、HealthKit、外部通知与图像接口 | `src/product/ExtensionPorts.ts`、`src/sync`、`src/adapters` |
| 本地产品数据存储 | `scripts/product-local-store.cjs` |
| 可选外部桥接 | `scripts/healthkit-bridge.mjs`、`scripts/local-llm-proxy.mjs`、`native-ios` |
| 验证与历史参考 | `tests`、`docs`、`design-demos/design-spec.md`、历史 Markdown |

Voice/PeerJS 的浏览器 adapter 不等于 Windows 已完成语音或远程同步接线。HealthKit 由 iOS companion 请求权限，Windows 只接外部健康数据；真实 iPhone、远端可信身份、通知服务或硬件未配置时显示不可用。保留 mock 与业务回归夹具，不将其作为真人数据或生产 fallback。

`npm run typecheck` 检查保留的全部 TypeScript；`npm test` 运行业务回归；`npm run test:product` 运行正式产品/扩展集成；`npm run test:healthkit` 验证外部桥接协议。Playwright 仍供原康复银发隔离手机联动的验证脚本使用。React/Vite 及其专用测试已移除。

旧 UI、空间建模和演示源码可从 `codex/rehab-agent-stage1` 恢复。源头、分类及保留限制见[上游来源](../UPSTREAM.md)与[本轮清理审计](../../docs/validation/REPOSITORY_CLEANUP_2026-10-02.md)。
