# 康复 v2 与离线重任务：算力准入和释放

2026-10-11。第一版实施基准 `5b42cb0`；本轮基于 `863283a` 扩展为 `rehab-compute-coordination-2`／`rehab-report-process-2`。只改康复 v2 和独立研究工具；旧桌面 Runtime、前端、整个 Android、原权重和正常患者库不改。产品版本仍 0.20.0，已发布 APK 仍 0.2.1，v2 默认关闭。

## 1. 解决哪一个问题

不同进程原先分别限制自己的队列和作业数，离线训练仍可能与正式会话争用 CPU。现在同一 checkout 中已接入的入口共用两把 OS 字节范围锁：正式会话持有主锁共享句柄；离线重任务必须同时获得主锁和后台锁独占句柄；派生报告先短暂检查主锁，再仅持后台共享锁计算。锁冲突立即返回；训练／离线任务不自动排队，报告保留 durable pending 后再试，不结束别人的会话。

这是一层合作式准入，不是 CPU／RAM 配额、全机器调度器或医学判定。它不会提高关键点本身的定位准确率；作用是避免这些入口同时计算造成积压，并使释放边界可验证。

“非阻塞”指锁冲突时不等待；文件打开／文件系统／OS调用本身尚无独立硬截止，不据此宣称所有卡死已解决。

| 已有持有者 | 新正式会话／正式推理 | 新离线重任务 | 新报告 |
| --- | --- | --- | --- |
| 无 | 允许尝试 | 允许尝试 | 允许尝试 |
| 正式主共享锁 | 允许共享；宿主仍限制单活动会话 | 立即拒绝 | 延期，不序列化／启动报告 child |
| 离线主＋后台独占锁 | 立即拒绝 | 立即拒绝 | 延期 |
| 已准入报告后台共享锁 | 允许；同宿主请求取消其准确所属报告 | 立即拒绝，回滚本次主锁 | 允许共享；各宿主仍限单报告槽 |
| 报告短暂主锁预检 | 可能立即冲突，客户端可原键重试 | 可能立即冲突 | 可能延期 |

主锁固定为 `.runtime/rehab_ml/run/compute-coordination.lock`，后台锁在同目录为 `compute-coordination.lock.background`。从源码 checkout 推导，不由 `REHAB_RUN_ROOT` 或任务输出位置推导。改变输出目录不能绕过容量；后台锁冲突／打不开时回滚本次主锁。两文件一直保留，内容、修改时间和 PID 均不作为持有证据，不能删除锁文件来“解卡”。多个 checkout 或机器之间不共享这层锁。

## 2. 接通的入口和信息传递

| 入口 | 实际持有者 | 持有区间 | 返回或保存的信息 |
| --- | --- | --- | --- |
| v2 `SessionService.create` | 宿主 Runtime | 计划验证后、SQL create 前获取；运行／暂停／休息／收尾均保留 | `source.compute_execution_contract`；冲突时 HTTP 503，不创建 SQL 草稿 |
| 默认 `pose_process` | 每次实际原生推理子进程 | 解码／模型加载／推理／回复期间另持共享锁 | 有限资源错误经原有 JSON 通道回传；不写 SQL |
| 默认 v2 派生报告 | 宿主报告槽＋实际 report child | 宿主序列化／spawn／核对持后台共享；child 在收到请求后重新预检，再持后台共享到回复 | 原事实白名单／hash／身份／反馈revision；busy或已确认抢占只写pending，后台重建 |
| 可信本地 report callable | 实际调用进程 | 构建函数期间持后台共享 | 明示无硬取消；不作为公共接口配置 |
| `train-pose` | 实际 `pose_training.run_child` | 原请求路径校验后、训练体之前；直到返回／异常／退出 | 原 status／failure／provenance；原 pose 单作业锁同时保留 |
| IRDS `training.train` | 实际运行该同步训练函数的进程 | 加载／拟合／保存整个函数 | 原离线实验产物；不自动进入患者库或上线 |
| `smoke-pose-masked` | 实际 masked smoke 子进程 | 原生前向／反向／更新／重载全过程 | 原 TEST 工程验证产物 |
| `extract-mediapipe` | 实际 VIDEO 子进程 | 模型读取／解码／逐帧处理／结果全过程 | 原显式授权分析记录；不是 APK 现场验证 |
| `target_domain.extract_pose` | 实际授权回放进程 | YOLO 回放、分析、保存和关闭全过程 | 原离线分析结果；没有补训练授权 |
| `infer-pose-reference` | `offline_pose_process` 原生子进程 | 启动握手前获取；跨图片保留到该子进程退出 | 原参考预测；busy 握手为结构化错误，父进程确认释放 |

对应代码：[资源层](../../rehab_codex_single_camera_v2_1/app/rehab_v2/resources.py)、[正式宿主](../../mobile_rehab/rehab_v2/service.py)、[原生推理](../../mobile_rehab/rehab_v2/pose_worker.py)、[所属生命周期](../../mobile_rehab/rehab_v2/owned_worker.py)、[离线桥接](../../tools/rehab_ml/resource_gate.py)。资源层仅用标准库，不因获取锁导入 Qt、Torch 或模型。

两条信息链分别为：

```text
正式请求 → 幂等回执查找 → 现有计划／剂量核验
  → 共享准入 → 原 SQL 创建 → Runtime 持有共享句柄
  → 每帧原生子进程另持共享句柄 → 原规则／SQL／控制链
  → 最终事实确已提交 + 该 session 无在途工作 + 子进程未隔离
  → 释放宿主句柄 → 原派生报告继续独立处理

离线显式命令 → 原数据／权限检查（仍保持各工具自己的顺序）
  → 实际计算进程尝试独占准入 → 原模型计算／原产物
  → 退出／异常／准确所属取消 → OS 释放
  → 新正式请求可重新尝试；不自动补建此前被拒会话
```

已完成会话的幂等 create 重试是回执查询，先于准入，所以正在离线训练时仍能查到原会话，不重复创建或重新占用。正式 create 的锁失败与 SQL 创建失败不同：前者不生成草稿，后者释放本次句柄并保留原错误；不伪造成功回执。

### 2.1 为什么报告不能一直持有主锁

如果报告全程持有主独占锁，新训练会因为已有报告而被拒；若报告也用主共享锁，它就能在正式训练忙时继续进入。本轮将“是否可以开始”和“实际后台工作保护”拆开：report 获取主独占 → 获取后台共享 → 立即释放主锁 → 序列化／生成／核对 → 释放后台共享。默认child收到请求后再次做相同预检；宿主准入后若正式会话先进入，child返回busy、不生成报告，并保留健康空闲进程以复用。

因此正式会话不必等待已准入报告结束，重任务却不能在报告期间进入。短暂预检仍可能与create冲突；这不是严格优先级调度或所有调用的硬截止。多个宿主已有报告可短暂共存，只能取消本宿主准确所属进程，不能按PID列表结束其他服务。

### 2.2 派生状态与信息传递

```text
已finalized事实＋白名单快照＋当前feedback_revision
  → 单报告槽 → report准入
  → busy：按原反馈CAS写pending → deferred＋reason＋retry_after_s=0.5
  → 空闲：默认所属child → 原报告digest核对 → CAS写ready

同宿主新正式create确实成功
  → preempt_current仅设置取消事件，不在create等待或kill
  → 报告线程确认准确所属child退出／清理
  → report_worker_preempted → CAS pending → 正式会话结束后重建
```

| 路径 | 派生结果 | 不变的内容 |
| --- | --- | --- |
| 容量忙／已确认所属抢占 | `pending`，响应`deferred`，0.5秒有界重查 | 快照、次数、canonical_commit、唯一计划贡献 |
| 更高反馈revision先保存 | 原CAS拒绝，响应`pending_newer_feedback` | 新反馈和其待重建状态，不被旧ready／pending／failed覆盖 |
| 资源不可用／超时／其他失败 | `failed`，保留固定错误；可显式重建／重启对账 | 已保存训练事实；不可用不当成busy永久重试 |
| SQL派生写失败 | 错误可观察，不返回虚假已保存状态 | 原事实不回滚；数据库恢复后再查权威状态 |
| 实际退出未确认 | 原失败，不转成已抢占；宿主后台句柄保留 | 禁止离线重任务重入；同宿主新create拒绝预先已有隔离 |

自动消费者遇到容量忙／单槽忙／新反馈待处理即停止当前批次，不把16条pending循环空转；等待0.5秒或事件后再查。重启首次发现failed报告，容量忙时转pending，因此后续扫描和再次重启仍可找到。诊断新增固定`report_deferred`／`report_preempted`计数，不进入事实摘要。

无效create、SQL创建失败和历史幂等create不会触发抢占。可信本地callable没有原生硬取消，已进入时可能与新正式会话共存至返回；默认进程边界不扩展为所有第三方callable的截止保证。

## 3. 结束与故障：不能只看内存里的 ended

| 情况 | 行为 |
| --- | --- |
| pause／rest | 保留正式共享锁，避免恢复时已被后台重任务占用 |
| finish 已提交，但推理尚未实际返回 | 保留宿主锁；取消请求不是退出证据 |
| 晚到结果 | 仍按原 terminal epoch 丢弃，不改最终次数／快照／贡献 |
| 最终 SQL 提交失败 | `terminal_committed=false`，不因引擎已 ended 就释放；原故障继续返回 |
| 原生释放未确认／quarantined | 不释放宿主锁、不遗忘 Runtime；允许原准确句柄清理重试 |
| 正常关闭或强制宿主关闭 | 消费者／原生进程／本地报告写入已确认结束、Storage 关闭后再释放全部 Runtime 锁 |
| 进程实际崩溃 | OS 随句柄关闭释放；锁文件仍可存在，后续不按文件存在误判忙 |
| 锁文件打不开或 OS 调用异常 | `rehab_compute_resource_unavailable`，与容量冲突 `rehab_compute_resource_busy` 分开；失败时不继续计算 |

默认正式原生子进程保留自己的共享句柄，宿主进程崩溃时，正在进行的原生工作不会仅因父句柄消失而失去保护。离线参考推理采用另一固定本地 target，不能通过 HTTP 帧载荷选择角色。测试 `_path` 注入只是隔离 OS 测试，不作为接口或配置项开放。

## 4. OS 实现依据

Windows 对两文件分别使用同步、不可继承句柄与 `LockFileEx` 的 `FAIL_IMMEDIATELY`，范围是偏移0的1字节；角色共享／独占映射见上表，无需写该字节。按实际错误区分锁冲突和不可用，显式 `UnlockFileEx` 后关闭句柄。共享重叠、越过 EOF 的范围及实际进程终止后的锁释放依据 [Microsoft LockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex)；解锁范围依据 [UnlockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-unlockfileex)，结构布局依据 [OVERLAPPED](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-overlapped)。

Unix 分支使用非阻塞 `flock(SH/EX)`，见 [Python 3.13 fcntl](https://docs.python.org/3.13/library/fcntl.html)。本轮实际 OS 测试在 Windows；没有把 Unix 实现存在写成 Linux 实机通过。

## 5. 复现与边界

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run\process-temp'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_resources.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_report_resources.py
```

三条审计依次运行；不要并行运行互斥审计和模型测试，否则它们应当互相拒绝。专项预检发现已有接入的正式会话／报告时直接退出，不帮用户停止会话、服务或相机。只用隔离TEST库和工程输入；实际锁／原生优化／进程退出是真实执行，挂起是专用TEST target，不是实际模型死锁证据，也不产生真人准确度结论。

第一版结果保留 [原本机验收](../validation/REHAB_COMPUTE_COORDINATION_2026-10-11.md)；本轮报告增量见 [验收](../validation/REHAB_REPORT_COORDINATION_2026-10-11.md)。机器摘要为 [原生离线协调](../../reports/rehab_backend/resource_verification.json) 和 [报告专项](../../reports/rehab_backend/report_resource_verification.json)。

尚未覆盖旧桌面／旧live、其他业务作业队列、全部下载／预处理／评估／非v2报告导出、独立APK、其他checkout、机器或GPU非合作进程。已有旧版本运行进程只懂原单锁或没有锁，不能因源码更新就视为已接入双锁；原服务未重启。完整资源覆盖、同硬件同输入负载对照、目标手机仍待验证，不通过改保护基准、放宽计次条件或关闭用户窗口完成。
