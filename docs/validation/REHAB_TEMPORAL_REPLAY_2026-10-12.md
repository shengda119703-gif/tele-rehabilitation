# 原RGB到计次预测：本机实际记录

日期2026-10-12；基准`f113d9df887849f3a724797821b07d0231f80323`，分支`codex/backend-information-map`。按后端任务书10.4–10.6／15.2／P5推进；只增离线工具、TEST、聚合及必要文档。产品0.20.0、APK0.2.1、v2默认关闭，正式算法／规则／权重／正常库、UI／整个Android不改，不启停用户服务、摄像头或窗口。

## 已实际执行

`temporal-replay-audit-ed5fca84`使用原CC0 Mobi3.0／E01／AF／VFL固定队列的5人val及5人test；原14人train不重放。源24段680355016字节、划分和下载receipt两次核验，原标注包只读。左侧在推理前明确固定，是分析侧，不推断患侧，不用测试效果改侧别。

[聚合证据](../../reports/rehab_backend/temporal_replay_verification.json)所引私有summary SHA256为`5cc9060237f45c762fe4010eaae6baa86bc719bf5be363dfe360b38bcb8e6104`；正式原YOLO权重SHA仍`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`。

| 检查 | 实际结果 | 解释 |
| --- | --- | --- |
| CLI帮助及导出专项 | 退出0；13项TEST通过 | 确认时间／空边界／部分动作／失败null与既有预测schema；不是人体参考 |
| val原模型／原协议 | 5段，3688完整展示帧，466采样帧，462主指标可观察帧；CLI约64.763秒 | 保存完整trace、原结果和预测，不取最好片段 |
| test原模型／原协议 | 5段，5545完整展示帧，695采样帧，624主指标可观察帧；CLI约76.240秒 | 含解码／源核验耗时，不能当实时或手机性能 |
| 保存证据重放 | 10段全部一致 | 从保存原姿态重新走原adapter／engine，核对每帧指标、阶段、计次、事件、最终结果与采样完整性 |
| 资源与输入 | 原所属worker释放确认；33源码运行前后不变；原标注包全部文件不变 | 没有新权重、伪参与者、人工表预填、训练或正常历史写入 |

公共预测schema仍声明式`rehab-temporal-predictions-1`，但本次另有实际CLI日志、原模型／配置／实现SHA、私有逐帧trace和重放核对。它不是正式患者会话trace的通用导出器，也不是执行的密码学证明。

## 必须保留的负结果

10段全部停在WAIT_READY，准备基线均未建立，确认次数和三个已支持事件均为0。所有1161个采样帧的阶段清单有实际保存证据。没有把它改成演示成功；原准备／稳定／置信度／缺测／计次门未放宽。

这只能证明当前固定左侧、0.25秒采样和原默认准备规则下没有进入动作阶段，不能据此宣称真人完成0次、计次准确、规则稳健或确定的漏计原因。已有106到133度等投影变化也不能代替完整动作参考。后续需先用独立val参考区分取景、准备条件、采样和运动协议，再预声明优化；不能用固定test反复挑参数或较好侧别。

准备、峰区起止三个未实现导出为null；出程／回程／完成的空清单为[]，不是相位真值。输出PTS为当前滤波证据的确认帧，停留确认延迟不能反推成更早启动时刻。

## 开发测试与存储失败

新增9项保存证据TEST首次均在夹具写入时失败：本机C盘实际无可用空间，`OSError 28`，原工具输出`48cb2e`保留。未改源代码／空间门，显式使用D盘本轮隔离temp重跑9项，0.373秒、全部通过。涵盖文件改写、重算hash后的假计数／指标／模型、漏样本、未确认释放和旧源码。夹具均TEST空姿态，不是模型推理或人工真值；13＋9为不同专项，不冒充22份人体结果。

本机随后核对C盘0字节、E盘371019776字节、D盘16090411008字节；没有删用户文件、移动正常库或权重。默认E盘生产空间不足与此前490／旧手机7个507仍保留，不能用D盘通过说默认产品已恢复。

## 复现

本轮完整隔离回归已实际终止退出0：`D:/RehabBackendVerification/temporal-replay-full-20261012-a9309b72`新后端545项／209.476秒、原康复12项／0.087秒、旧手机网页19项／12.02秒与原1308保护全部通过。13＋9专项均为545子集，不重复累加。250相关源运行前后hash一致，原默认E盘失败summary和全部日志不变。

[完整聚合](../../reports/rehab_backend/storage_full_regression.json)引用的新summary SHA为`cf06e156c172f2eef441dd8cd04ccdbfc8e04b143abdc14bc8608fa1ccc96167`。whole_regression_passed=true只对应这次实际D盘隔离验证，default_product_storage_restored=false；原E盘490失败和上轮D盘523通过各自原run／日志／SHA保留，不混为本次计数。旧Starlette／httpx警告保留，没有升级依赖。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_temporal_replay.py --receipt '.runtime/rehab_ml/data/mobiphysio/3.0/rgb-e01-front-fl-9ac33275/download-a157e0e1.json' --pending-bundle '.runtime/rehab_ml/run/professional-annotation-audit-3581f13f/cohort/bundle.json'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_storage_recheck.py --suite full --failed-summary '.runtime/rehab_ml/run/verification-e8c8c33f/summary.json' --output-dir 'D:\RehabBackendVerification\temporal-replay-full-20261012-a9309b72'
```

回放工具每次生成新的专用输出，不复用或覆盖原run。上文完整回归D目录已使用，复现须另选新的明确子目录，不覆盖。一般测试须明确有空间的task TEMP／TMP；原32MB预检、解码／worker预算和生产空间门不变。逐帧骨架与原视频只在忽略目录，不上传。

## 未完成

发布前实际核对8份本轮命令日志、两份summary及283次源码指纹（专项33＋全量250，有重复，不称283个不同文件），不一致0。8份本次维护文档667个本地链接缺失0，git diff --check通过；280份既有用户文件hash不变，原任务书与1308保护基准hash保持，不重建清单、不把用户素材／CSV／脚本纳入提交。

真实专业GT仍0，本轮不执行独立准确性评价、不微调或启用候选、不宣称精度改善。两名独立标注者、第三人专业复核、对应坐站／深蹲真实参考、2D／visibility、真实提示效果和手机／LAN／TLS／长时／完整物理故障仍待；整个任务未完成。

方法和逐跳字段见[工作流](../development/REHAB_TEMPORAL_REPLAY.md)，完整实施仍按[A–E报告](../../reports/rehab_backend/IMPLEMENTATION_REPORT.md)保留各轮成功和失败，不混合不同环境／时点。
