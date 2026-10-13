# 说明与 Android 旧 UI 清理记录

日期：2026-10-13；main基准 `48e94e58ccf260bd560f6ed4c67731e58e347380`；分支 `codex/docs-legacy-cleanup-20261013`。

## 改动与恢复

当前交接收为版本、入口、数据归属和未完成项；原完整记录与索引分别移入 `docs/history/HANDOFF_SNAPSHOT_2026-10-13.md` 和 `docs/history/DOCUMENT_INDEX_2026-10-13.md`，保留全部历史阶段，修复移动后的相对链接。根README修正main电脑0.23.1、Android0.3.1／code5；两份后端资料保留正文、数值和各自基准，增加历史标记。

三份被正式打包排除的旧UI和两份读取旧UI的测试已从当前目录撤出，完整原件保存于远端 `archive/pre-docs-legacy-cleanup-20261013`，指向上述基准。详见[退役索引与恢复命令](../archive/android-legacy-ui-20261013/README.md)。新备份测试使用正式store.js；新视频测试检查正式motion.js。旧UI的reducedPlan不移植到当前代码，旧数据迁移保留。

## 本机实际检查

- Node源码专项：**45通过、0失败**，包含6项当前备份／视频、5项barbell、34项网页专项。旧7项UI测试退役，不与旧54项比较或累计。
- 正式打包输入对照：web／static除三份显式忽略的旧UI外，共 **31** 个文件的Git内容hash与基准一致（Git会规范化Windows换行）；资源准备、TS打包、manifest和正式业务源码未改。这是源码／输入核对，不是APK资源或安装验收。
- 新交接／索引／归档的本地文档链接检查；移动文档原有可达链接保留。
- 提交前执行git diff --check；推送后核对远端清理提交与归档基准。

复现命令：

```powershell
node --test android_offline/tests/backup-current.test.cjs android_offline/tests/video-current.test.cjs android_offline/tests/barbell.test.cjs mobile_rehab/tests/test_extensions_ui.cjs mobile_rehab/tests/test_product_ui.cjs mobile_rehab/tests/test_ui_copy.cjs mobile_rehab/tests/test_ui_presentation.cjs
git diff --check
```

## 保留与限制

业务、版本、算法、旧数据迁移、模型、许可证和用户数据均保留；前端／云端活跃分支及旧远端版本保留，未合并或部署服务。重复截图本轮保留。旧后端protected_files.json按原基准保留，仍记录退役路径；不重建历史hash来伪装旧验收有效。

本机是新克隆，无已验证应用环境／APK／桥接生成物；未重建APK、未验证Qt或实体手机。本次没有产品版本更新，不把桌面最新入口改指向缺少运行环境的新克隆。
