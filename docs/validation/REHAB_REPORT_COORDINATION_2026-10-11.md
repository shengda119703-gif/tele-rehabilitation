# 康复 v2 报告延期与所属抢占：本机验收

2026-10-11，基于`863283a1cb253550124ffe8c3206d19cf2521b36`继续任务书第6–7节。实施为`rehab-compute-coordination-2`与`rehab-report-process-2`，以本文件所在交付提交为准。只改v2后端／隔离工具／测试／文档；旧UI、整个Android、原模型、正常库和非康复业务不动，不启停用户服务或相机。

## 1. 末次实际结果

Windows、原`.venv/Scripts/python.exe`，临时文件和TEST数据库仅用E盘忽略目录；没有安装／升级依赖。复现命令见 [资源工作流](../development/REHAB_COMPUTE_COORDINATION.md)。

| 检查 | 实际结果 | 范围 |
| --- | --- | --- |
| 新后端完整回归 | `verification-a380a260`，269项，102.586秒，外层105.359秒，退出0 | 本轮18项增量＝4项锁＋14项报告准入；含全部原子集 |
| 原康复回归 | 12项，0.092秒，外层0.243秒，退出0 | 不是全UI或真人验收 |
| 原手机回归 | 19项，12.79秒，外层13.319秒，退出0 | 原Starlette/httpx warning保留，未改依赖 |
| 原保护基准 | 1308份SHA256一致，变化0，退出0 | 清单未重建，hash仍为`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742` |
| 资源＋报告专项 | `report-resource-audit-5d0a9f94`，57项，44.511秒，外层44.804秒，退出0 | 25项资源＋14项准入＋18项原隔离，为269项子集，不另累计 |

专项 [机器摘要](../../reports/rehab_backend/report_resource_verification.json) 保存10份实际源码SHA、测试日志SHA以及以下独立原生路径。完整日志指针和SHA见 [regression.json](../../reports/rehab_backend/regression.json)。

| 原生审计路径 | 实际观测 |
| --- | --- |
| 正式共享句柄阻止报告 | 实际OS锁持有时，响应`deferred / rehab_compute_resource_busy / retry_after_s=0.5`，child不存在，已提交1次、事实digest不变 |
| 释放后默认报告 | 实际默认report child生成ready，事实digest仍`361ae73763d389697f9ff5169357777d1fb542c603297bdcb180c33ff94e9389` |
| 新正式会话请求抢占 | 内部TEST create为21.0825ms；不是网络或p95。准确所属报告PID14280退出码-15、confirmed=true，4MiB共享区已unlink，报告CAS为pending |
| 已确认抢占后重建 | 改回默认report target，在新正式会话结束后ready；事实digest仍`21b074e437b8142169e3653e7a0c2e75f544859c9a97afe9d7e80096201e6e6a` |
| 失败报告重启遇到heavy | 真正独占OS锁期间，重开隔离库后failed转pending，durable work存在，不spawn；释放后ready，事实digest不变 |

挂起来自专用TEST target，进程和终止是真实执行，但不是实际模型／报告死锁。上述事实均为`SYNTHETIC / TEST`；没有处理新真人媒体或产生临床准确度。正式默认报告预算仍握手10秒、工作5秒、terminate/kill各1秒；专项正常报告用2秒、挂起30秒、释放0.5秒，均明确留在摘要，不冒充默认性能。

双锁改动后另实际运行原离线审计`resource-audit-4f2f9ba6`，见 [当前机器摘要](../../reports/rehab_backend/resource_verification.json)：正式持有时训练child退出1／busy／checkpoint不存在（0.1585秒）；真实原YOLO AdamW一步、epoch1 validation活进程时新create拒绝0.6763ms；准确所属取消之后child退出1／确认退出／last保留／result不存在（4.5535秒）。40次内部pause/resume为p50 11.268ms、p95 13.155ms、最大13.9501ms，不是网络或压力对照。原参考YOLO跨图片持锁、64×64无人JPEG0人、冷推理2025.054ms、关闭确实退出。原权重SHA仍`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`；实际优化只用无人TEST工程图，不叫真人微调。

## 2. 验证了哪些故障和竞态

- 两文件真实OS互斥：formal/heavy拒绝新report、已准入report可共享后台且允许formal进入、heavy后台失败回滚主锁、真实report child `os._exit(31)`后重新准入、陈旧文件不冒充活任务。
- 实际后台路径被目录占据时打开失败，返回unavailable并回滚主锁；不是容量忙。Windows实测，不把Unix代码存在称为Linux验证。
- 宿主准入／spawn后正式先进入：真实默认child重新预检，回复busy，保留健康空闲child；下一次可复用原PID。
- 同宿主新create成功只请求取消，不在控制路径等待kill；无效请求和历史幂等create不抢占。未确认退出时保留实际宿主后台句柄，阻止heavy；预先已隔离时拒绝新create且不写草稿。
- 活动／pause正式保护、16条durable backlog的有界重查；资源忙不变failed，不在16行上空转。重启首次failed在busy时转pending，后续恢复不丢待办。
- 更高反馈revision先保存时，旧报告pending CAS不能覆盖；快照／回执／唯一贡献不变。资源unavailable为failed，不伪装成busy反复自动重试。
- 派生SQL写错误仍返回可观察故障，不虚报pending已保存；本地callable持后台锁至返回，契约明确无硬取消。

SQL错误、terminate/kill不执行和隔离状态部分为明确受控注入；真实锁、目录打开失败、默认child和退出另列。没有物理磁盘满、断电、设备或完整压力实测。

首轮54项定向测试有1项失败：自动消费者先占报告单槽，手动反馈CAS测试得到`running`而未执行目标交错。测试在创建事实前屏蔽自动work扫描，只隔离该测试路径，不改生产单槽、反馈语义或CAS。修正后14项准入、57项专项及269项完整回归实际通过；失败不计为通过。

## 3. 未覆盖和交付边界

两锁是同checkout、已接入进程的合作式准入，不是系统CPU/RAM配额。短暂主锁预检可能拒绝同时来的正式create；OS打开、Process.start、宿主序列化／内容核对没有独立硬截止。其他宿主已准入报告及可信callable不可被本宿主硬取消，旧版本已运行进程并不自动升级双锁。

旧桌面／旧live／APK／非v2报告导出、全部预处理／评估／其他checkout与机器仍未完整协调。真人授权RGB、独立参考／专业标签、目标手机／同硬件全负载／物理故障、显式resume和康复深蹲正式宿主计划仍待完成。报告延期提高工程隔离和可恢复性，不证明点级、计次或医学准确率提高。

产品0.20.0、APK0.2.1、v2默认关闭；桌面入口仍“安康康复（最新版本）”，首页／康复／健康／用药／家庭导航不变。提交后仅刷新Git描述，不打开新应用或关闭用户未保存窗口。用户动作图／说明／CSV／任务书／导入脚本不纳入本次提交；最终只读hash复核记录于交接。

交付阶段实际复核280份用户文件（276张PNG＋README／CSV／任务书／导入脚本），按绝对路径＋SHA256排序的聚合hash前后均为`97cf4c7f1279b90bfffc3f08e3e1003b73cabf83de7b4bece743d446ebe23b99`，变化0。该快照始于本实施阶段，不冒称上一会话开工状态。两份专项摘要的23次源码hash检查、完整／报告／原生7份日志hash均一致；7份本轮说明／索引的517个本地链接目标存在、表格列数一致、围栏闭合、Git空白检查通过。原1308保护在全部原生审计后再次核验，变化0，基准未改。
