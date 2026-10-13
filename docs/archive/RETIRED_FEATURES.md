# 下架功能统一远端归档

统一恢复入口：远端分支 `archive/retired-features`，基准 `2f52d6298df70d871a93f4848540202b1c182f62`。这个完整快照同时保留报告识字、图片解析与OCR依赖，以及Agent模块查询/导航、照护代操作、确认/回执UI及原测试。此前的OCR归档分支仍保留，统一入口优先用本分支。

main的报告原件上传下载和手动页面继续使用；下架的是识字与Agent操作接线。旧数据不删除。main仍保留历史通用Runtime及领域兼容类型，正式ProductService统一走康复只读问答；不以隐藏按钮充当关闭业务操作，care.*请求明确拒绝。

恢复时使用独立检出，先评估与当前main的差异，不能直接整分支覆盖main：

```powershell
git fetch origin archive/retired-features
git worktree add ../retired-features-history origin/archive/retired-features
```

后续需要恢复哪部分，就从此快照及相应历史提交选择性整合、重新验证。归档分支不是当前可直接发布的新版本。
