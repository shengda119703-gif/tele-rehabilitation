# 计次／相位评价与外盘完整回归：本机记录

日期2026-10-12，实施基准`101c69f309909a74cdd3c0da470064faeeff4a24`，分支`codex/backend-information-map`。任务书10.4–10.6／13／15.2／P5／P7；只改离线康复工具、后端测试及必要文档。产品0.20.0、APK0.2.1、v2默认关闭；不启停用户服务、相机或窗口，不改变正式算法、规则、权重、正常库、UI或整个Android。

## 已实际执行

专项run：`temporal-evaluation-audit-8badfb07`。[聚合证据](../../reports/rehab_backend/temporal_evaluation_verification.json)，私有summary SHA256为`95045e5bda49e5ea9299db6bbf30c30fe0ca6e5f96375aad0168f9512656439c`。

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| evaluate-annotations／外盘full帮助 | 退出0 | 有明确路径和split；full／subset分开 |
| TEST指标与资格专项 | 33项、0.292秒、退出0 | 有序最优一对一、穷举对照、逐任务mask、未知／缺预测、明确0、完整队列、当前复核／输入变化及全套四组契约 |
| 实际24份待标包评价 | 退出1，blocked_missing_independent_professional_supervision | 实际重新核对原源／PTS和双人表，不读取不存在的预测，未创建evaluation目录 |
| 原标注包 | 全部文件hash不变 | bundle仍bb3a57bdd0717bb971309005c7b360b5f2f58c1e6a3d1b5e07acc419c8c8df45；0真值 |
| 禁改范围 | 原1308变化0 | baseline仍75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742，未重建 |

开发时首轮28项通过；增加5项后首次33项有1个失败：TEST中修改reference也同时改了mock audit共享的label对象，未形成预期的“旧复核／新参考”差异。改为独立深拷贝夹具后33项通过，再由上文专项保存完整日志与源SHA；没有为此放宽生产资格校验。开发失败见本轮原工具输出`0f863d`，不是人体或真实导入结果。各轮测试不累加。

## 完整回归

使用真实有空间的D盘新目录`D:/RehabBackendVerification/temporal-full-20261012-45ade789`，不复用上轮子集。通过`--suite full`执行新后端完整发现、旧康复、旧手机及1308保护四组，与默认verify_all共享同一命令清单。实际终止退出0：新后端523项／204.622秒、原康复12项／0.087秒、旧手机19项／12.42秒及1308保护全部通过；523包含33专项，不重复累加。旧Starlette／httpx警告保留，不升级产品依赖。

[完整聚合](../../reports/rehab_backend/storage_full_regression.json)引用原summary，SHA256为`150c4b9abba050f0c67b980f87550ef93d066fc33c2aab9365eda075bb6e38ae`；全部相关源码运行前后指纹一致，原失败summary与日志不变。whole_regression_passed=true仅对应这次外盘完整隔离工程验证，default_product_storage_restored=false，clinical_accuracy=null。所有命令原日志及SHA保存，不用此前30／19的子集结果代替。

原E盘`verification-e8c8c33f`完整490项／4空间错误、旧手机19项／7个507仍保留为失败，[原聚合](../../reports/rehab_backend/regression.json)不改。D盘只是本次隔离测试产物位置，没有清理文件、修改空间门、搬动原视频／权重／正常库或恢复默认E盘容量。原30／19子集证据也不覆盖本次完整结果。

## 复现

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_temporal_evaluation.py --pending-bundle '.runtime\rehab_ml\run\professional-annotation-audit-3581f13f\cohort\bundle.json'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_storage_recheck.py --suite full --failed-summary '.runtime\rehab_ml\run\verification-e8c8c33f\summary.json' --output-dir 'D:\RehabBackendVerification\temporal-full-20261012-45ade789'
```

第二个目录已使用，复现必须另选明确新的外盘TEST子目录，不得覆盖。专项每命令60秒，全套新后端240秒、其余150秒。观测等待超时不代表运行停止，不启动第二份重复任务。

## 尚未证明的能力

发布前核对9份实际命令日志、两个summary及252次源码hash（包括专项6份与全套246份，重复不算不同文件），不一致0；7份本次维护文档647个本地链接，缺失0，git diff --check通过。原280份用户文件hash全部一致，不纳入提交；原E盘失败聚合和上一轮子集报告也无diff。原1308保护与baseline保持，不以重建清单掩盖变化。

当前0份真实专业GT，没有人体角度／计次／相位精度结果；TEST的部分合格reference和预测只证明数学／信息链。后端预测manifest目前是声明式导出，尚未接正式trace自动导出；不能证明原YOLO／服务实际执行或实际盲法。没有二维点／visibility微调、同步外部物理参考、质量分类／提示干预效果、受试者bootstrap置信区间、手机／LAN／TLS、长时及全部物理故障新增验收。候选保持关闭，整个任务未完成。实现及分母说明见[工作流](../development/REHAB_TEMPORAL_EVALUATION.md)。
