# 康复v2显式评估与计划绑定：本机验收

日期：2026-10-11。开工提交`ab6931d318959231b91200360a24b1412d40019d`。任务书第3–6节要求的本人证据／明确安排／不可变事实继续接线，原产品0.20.0、APK0.2.1、v2默认关闭。前一文档轮是已完成的文档进展；本轮恢复实际后端实施，不将文档交付当全部实施完成。

## 1. 交付范围

新增 [BackendPlans](../../rehab_codex_single_camera_v2_1/app/rehab_v2/plans.py)和独立计划API；SessionService接入显式assessment、`v2plan-`解析、同宿主保存与创建序列化；宿主只在原opt-in块提供可信participant。覆盖肩外展、坐站、康复深蹲的左右侧，不更改原53项共享目录或健身协议。

本轮另补两项明确肩部质量限值的保存／冻结，复用原finite参数校验、必要点及持续超限规则。坐站／深蹲非null对应限值拒绝；未配置限值不生成，辅助点缺失不把主计次归零、也不伪造质量正常。不改原规则阈值、计次、目标达标和继续政策。

问题／字段／流程／SQL版本／接口及复现说明见 [工作流](../development/REHAB_BACKEND_PLANS.md)。原UI、整个Android、原权重、正常患者库、旧API及非康复业务不改。后端源码此次发布不表示正式页面或APK已经接入。

## 2. 专项实际结果

产品原Python环境运行：

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_backend_plans.py
```

末次`backend-plan-audit-2851010b`，19项通过、退出0；测试44.010秒，所属进程44.441秒。六份源码hash在开始／结束一致，报告`implementation_unchanged=true`。日志为`.runtime/rehab_ml/run/backend-plan-audit-2851010b/plans.txt`，SHA256：`ae0290911600a669db5b8e4b91f580438ceec97ee81be8d083c435ed475c5f08`。

| 验证责任 | 实际覆盖 |
| --- | --- |
| 三动作和左右 | 六种动作侧别各自assessment→plan→training完整一次→finish→明确自评；引用实际协议，不借旧动作别名 |
| 身份／作用域 | 宿主participant不等于HTTP owner；其他owner不能引用，切participant后旧评估／计划不再用于新本人 |
| 安排冻结 | 客户端新剂量、扶手／陪同及质量限值不覆盖保存条目；需要陪同仍检查明确确认 |
| 可测质量 | 主计次完整而两辅助指标缺失时为UNASSESSABLE；当前有效持续超限时保留肘与躯干两问题、限值和测值 |
| 输入参数 | 两限值复用finite／0–180有效域；bool、NaN、Inf、越界和字符串拒绝；不支持的动作拒绝非null限值，失败不写plan |
| 评估依据 | finalized／基线／完整观察／视觉digest／协议／时区／复核窗；更晚失败／草稿不回退旧成功 |
| 版本／幂等 | 同键原回执、异载荷冲突、丢创建响应并发、修改／归档冲突、事务回滚；已开始训练冻结不被编辑改写 |
| 继续与反馈 | 完整浅幅度和目标达标分开；新计划／revision不能清掉不适；未提交自评仍missing；追加自评不改视觉snapshot |
| 组次与存储 | 两组休息／恢复／重做准备；首次扩展一致备份、旧facts及user_version4保持 |
| 实际HTTP及原YOLO | 原宿主路由／认证／历史／提交／反馈；原YOLO对白色JPEG无人结果不能成为合格评估 |

证据来自隔离SYNTHETIC／TEST几何与HTTP，以及原YOLO的白色JPEG缺人拒绝。没有真人样本、临床精度或手机性能结论，没有训练模型；`clinical_accuracy=null`。

## 3. 完整回归

本轮另运行原`verify_all.py`，使用隔离数据库及原Python环境。实际`verification-3ce388f3`已取得退出0终态，报告`passed=true`：

| 命令 | 实际结果 | 进程耗时 | 日志SHA256 |
| --- | --- | ---: | --- |
| 新后端unittest | 322项，OK；测试自身165.046秒 | 167.958秒 | `651117f4421b70db482969d44308441203018b15d3bb3b504ee15db85966ee4b` |
| 原康复unittest | 12项，OK | 0.243秒 | `e4c361c646011848213770236330c2956752ec3a66d21aeeca515c17e9ca1c8c` |
| 原手机接口pytest | 19项，passed；保留既有Starlette/httpx弃用warning | 13.391秒 | `107d2cf69367a121883f348bf028546ddaef1851a7f3efaee84f89c104daa181` |
| 原保护基准核验 | 1308文件，变化0 | 5.145秒 | `a3cadc9e0110ec764275b812f35eb697d1ede0f1711d7b694a06eba9370944ad` |

四份日志分别是`.runtime/rehab_ml/run/verification-3ce388f3/{new_backend,legacy_rehab,legacy_mobile,scope}.txt`。公开摘要见 [regression.json](../../reports/rehab_backend/regression.json)与 [scope_verification.json](../../reports/rehab_backend/scope_verification.json)。19项计划专项已经包含在322项中，不另加一次。没有借此前318项或专项推算总数；新后端命令时间上限240秒，其他命令沿用150秒，这是运行器预算，不是放宽计次／数据／数值验收。

## 4. 历史失败与范围

最初显式计划专项`9316c072`两组用例曾在休息后继续送帧，真实引擎拒绝；修正TEST夹具在RESTING／COMPLETE停止送帧，没有弱化真实暂停／休息规则。早期同宿主报告预检短暂持主锁引起busy，测试只对实际busy有界重试，不绕过OS准入。原失败日志保留。

15项`4a829c6a`和17项`6db31744`为先前阶段；本轮扩充19项，不能将不同阶段相加。此前318／12／19完整回归属于`a171e3d9`，不代表本轮质量接线后已通过完整回归。

## 5. 保护与发布

开工及交付前按逐路径原hash核对280份用户图片／任务书／CSV／导入脚本，均变化0；本轮只认领已有10份未发布后端工作并新增质量接线及必要文档。用户文件不覆盖、不提交。1308保护基准SHA256为`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`，不重建；完整回归及交付前独立核验均变化0。六份源码与报告记录一致，五份命令日志hash一致；七份本轮文档410个本地链接无缺失、44个表格及74个围栏通过检查。该文档检查不代替工程或临床验证。

正式提交只使用本轮文件白名单，推送后核对origin/main与HEAD。按仓库约定刷新原桌面“安康康复（最新版本）”Git描述，使用原Start-Rehab.ps1和已验证pythonw.exe，保留E盘快捷方式目标，不启动应用或关闭旧窗口。

## 6. 尚未完成

没有真人同域训练授权／独立2D及visibility／专业动作参考，不启动伪造微调；不重跑IRDS固定test来调参。前端／APK、手机／全负载／物理故障、专门时间可比性契约、全部数据／性能审核和目标域候选收益仍未完成。整个任务书保持进行中；本轮完成安排绑定不能替代上述证据。
