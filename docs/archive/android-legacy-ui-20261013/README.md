# 已退役的 Android 0.1 UI 和旧测试

归档基准：`48e94e58ccf260bd560f6ed4c67731e58e347380`；远端快照分支：`archive/pre-docs-legacy-cleanup-20261013`。

这三个 UI 文件已由 `android_offline/tools/prepare_assets.py` 明确排除，正式 UI 来自 `mobile_rehab/static/`。两份旧测试只读取旧 app.js，不代表正式 APK。文件从当前开发目录撤出，原文由 Git 归档保存，不删除远端历史版本或用户数据。

| 原路径 | 处置／替代 |
| --- | --- |
| android_offline/web/app.js | 正式呈现使用统一网页，存储／分析使用 store.js 和 motion.js |
| android_offline/web/index.html | 正式首页由 unified.html 生成，capture 页继续保留 |
| android_offline/web/style.css | 正式 static 样式保留 |
| android_offline/tests/backup.test.cjs | 当前备份契约改测 store.js；旧 reducedPlan 属于退役 UI，不移植旧语义 |
| android_offline/tests/video.test.cjs | 解码等待／失败／取消改测 motion.js；原生 insets 和 worker 资源检查继续保留 |

恢复某个旧文件（在仓库根执行，先检查本地同路径改动）：

```powershell
git restore --source=48e94e58ccf260bd560f6ed4c67731e58e347380 -- android_offline/web/app.js
```

旧测试需要同基准旧 UI／引擎，完整复现实验应在归档快照的独立检出执行，不混入当前测试清单。旧数据迁移仍在正式 store.js，未退役。`reports/rehab_backend/protected_files.json` 是旧后端验收快照，保留旧文件 hash；不得重写成当前清理验收。
