# 下架功能统一远端归档

统一恢复入口：远端分支 `archive/retired-features`，基准 `2f52d6298df70d871a93f4848540202b1c182f62`。这个完整快照同时保留报告识字、图片解析与OCR依赖，以及Agent模块查询/导航、照护代操作、确认/回执UI及原测试。此前的OCR归档分支仍保留，统一入口优先用本分支。

main的报告原件上传下载和手动页面继续使用；下架的是识字与Agent操作接线。旧数据不删除。main仍保留历史通用Runtime及领域兼容类型，正式ProductService统一走康复只读问答；不以隐藏按钮充当关闭业务操作，care.*请求明确拒绝。

恢复时使用独立检出，先评估与当前main的差异，不能直接整分支覆盖main：

```powershell
git fetch origin archive/retired-features
git worktree add ../retired-features-history origin/archive/retired-features
```

后续需要恢复哪部分，就从此快照及相应历史提交选择性整合、重新验证。归档分支不是当前可直接发布的新版本。

2026-10-14 患者管理控制台界面下架：旧版保存于远端 `archive/patient-console-20261014`，提交 `4652ef22472f3e53aa282ac721051f553513c874`。这是界面恢复快照；医患聊天、同步队列、授权与计划核验继续使用。main 只保留新的“联系康复医师”患者入口和独立“医生工作台”，不并列保留旧控制台页面。

同时下架依赖旧患者控制台的 `verify_qt_cloud.py`、`verify_workbench_native.py` 和直接操作公网 TEST 账号的 `cloud_service/tests/verify_public_portal.cjs`，均可从上述快照恢复。当前验收使用回环限定的 `verify_patient_qt.py`、`verify_patient_portal.cjs`、`verify_patient_contact.cjs` 与适配后的 `verify_workbench_browser.cjs`。

2026-10-14 简化医生工作台：上一版复杂界面及生成演示患者／模拟费用的 `tools/cloud/serve_contact_acceptance.py` 保存在远端 `archive/complex-care-ui-20261014`，提交 `ba859d88b79f64797c7dbb33ebf4096c4b8f31df`。main 下架该启动器和医生首页的重复看板、队列／日历、候选流程展示；原权限、消息、计划 API 保留。用户本地预览改用 `serve_local_workbench.py`，不创建任何患者、报告、消息或模型回执。
