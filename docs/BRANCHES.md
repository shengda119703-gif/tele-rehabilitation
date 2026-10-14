# 当前主线与旧版本

日常拉取、运行和交付统一使用 **`main`**。简洁工作台已通过 PR #8 合并，功能基准为 `ff037ba450ea2a2e5a0b4e4674553c0970b44afd`。当前版本及入口见[当前交接](HANDOFF.md)，最新界面见[简洁工作台验收](validation/SIMPLE_WORKBENCH_2026-10-14.md)。源码合并不等于公网服务器已更新。

## 仍在开发的分支

下列分支含未合并提交，继续保留；它们不是另一套正式发布版本。分支会变化，整合前重新比较与 main 的差异。

| 分支 | 内容 |
| --- | --- |
| `codex/automatic-motion-calibration` | 动作校准开发 |
| `codex/backend-information-map` | 后端信息梳理 |
| `codex/frontend-flow-optimization` | 前端与跟练增量 |
| `codex/unified-cloud-service` | 云端开发；main 已选择性复用医患协作所需部分 |
| `codex/wearable-health-integration` | 可穿戴设备接入 |

## 远端恢复快照

`archive/` 仅用于恢复和对照，不作为启动或交付入口。不要将整个旧分支覆盖 main。旧 Agent、报告 OCR 等下架功能优先从[统一退役索引](archive/RETIRED_FEATURES.md)查找。

| 归档分支 | 保存内容 |
| --- | --- |
| `archive/retired-features` | 旧 Agent 与报告 OCR 的统一恢复入口 |
| `archive/complex-care-ui-20261014` | 简化前的复杂工作台与演示启动器 |
| `archive/patient-console-20261014` | 已下架的患者管理控制台 |
| `archive/pre-docs-legacy-cleanup-20261013` | 文档与 Android 旧 UI 清理前快照 |
| `archive/pre-report-ocr-retirement-20261013` | 报告 OCR 退役前快照 |
| `archive/pre-unified-desktop-20261006` | 双端整理前桌面快照 |
| `archive/pre-unified-mobile-20261006` | 双端整理前手机快照 |

## 已合并分支的清理记录

2026-10-14 清理以下 10 个远端旧开发分支。清理前逐一确认其提交已包含在 main 中，且仓库没有打开的 PR；删除的只是冗余分支名称，提交和合并历史继续保留。未重写 main 历史，未删除未合并的队友工作。

| 原分支 | 可恢复提交 |
| --- | --- |
| `codex/docs-legacy-cleanup-20261013` | `c60d54ce73269e3e2cfd6535c3e328680657fbbe` |
| `codex/full-rehab-library-20261013` | `32a7a22c7e3552517d11f7689ad32f84886af804` |
| `codex/patient-doctor-entries-20261014` | `cd249e5286673c3269929cf32c27c2682678b38e` |
| `codex/product-ui-v1` | `f54935b59d273a9722c6ed08d682a21e5810c440` |
| `codex/rehab-agent-stage1` | `4b2d108a3003d84c89ac42da25580017d5b1de17` |
| `codex/rehab-beta-collaboration-20261013` | `52c27aabd250ea2e679c49051113e8000f477baf` |
| `codex/report-manual-entry-20261013` | `24d8fb2e17fb95b5a8627e9bf452fa843c06942d` |
| `codex/simple-care-workbench-20261014` | `e6c5ab1ce572543fb46ccfbf4059b570c09258dc` |
| `codex/simple-rehab-assistant-20261013` | `9b62cda3d1e379d18337fc6dff7763a48d2fd8da` |
| `codex/workbench-20261013` | `e5359ba0518a23df070c566413fdb7e460ff3fae` |

例如查看简化前后的原开发提交，可在独立目录检出：

```powershell
git fetch origin main
git worktree add --detach ../tele-rehabilitation-history e6c5ab1ce572543fb46ccfbf4059b570c09258dc
```

历史文档中的旧分支名、版本号和测试数只说明当时状态。当前入口统一从仓库首页和[文档索引](README.md)阅读，不逐篇改写旧验收证据。根目录的测试档案启动器已移至 `tools/ui-polish/打开林女士测试档案.cmd`，仅供开发测试，正式使用从 `启动康复助手.cmd` 进入。
