# 康复 v2 与离线重任务：算力准入和释放

2026-10-11，实施基准 `5b42cb0`。本增量只改康复 v2 和独立研究工具；旧桌面 Runtime、前端、整个 Android、原权重和正常患者库不改。产品版本仍 0.20.0，已发布 APK 仍 0.2.1，v2 默认关闭。

## 1. 解决哪一个问题

不同进程原先分别限制自己的队列和作业数，离线训练仍可能与正式会话争用 CPU。现在同一 checkout 中已接入的入口共用一把 OS 字节范围锁：正式会话持有共享锁，离线重任务必须获得独占锁。双方均立即尝试，冲突返回明确错误，不等待、不自动排队、不结束别人的会话。

这是一层合作式准入，不是 CPU／RAM 配额、全机器调度器或医学判定。它不会提高关键点本身的定位准确率；作用是避免这些入口同时计算造成积压，并使释放边界可验证。

“非阻塞”指锁冲突时不等待；文件打开／文件系统／OS调用本身尚无独立硬截止，不据此宣称所有卡死已解决。

| 已有持有者 | 新正式会话／正式推理 | 新离线重任务 |
| --- | --- | --- |
| 无 | 允许尝试 | 允许尝试 |
| 正式共享锁 | 允许共享；宿主仍按原规则限制单活动会话 | 立即拒绝 |
| 离线独占锁 | 立即拒绝 | 立即拒绝 |

固定路径为 `.runtime/rehab_ml/run/compute-coordination.lock`，从源码 checkout 推导，不由 `REHAB_RUN_ROOT` 或任务输出位置推导。改变实验输出目录不能绕过容量。锁文件一直保留；内容、修改时间和 PID 均不作为持有证据，不能删除锁文件来“解卡”。多个 checkout 或机器之间不共享这一把锁。

## 2. 接通的入口和信息传递

| 入口 | 实际持有者 | 持有区间 | 返回或保存的信息 |
| --- | --- | --- | --- |
| v2 `SessionService.create` | 宿主 Runtime | 计划验证后、SQL create 前获取；运行／暂停／休息／收尾均保留 | `source.compute_execution_contract`；冲突时 HTTP 503，不创建 SQL 草稿 |
| 默认 `pose_process` | 每次实际原生推理子进程 | 解码／模型加载／推理／回复期间另持共享锁 | 有限资源错误经原有 JSON 通道回传；不写 SQL |
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

Windows 使用同步文件句柄、`LockFileEx` 的 `FAIL_IMMEDIATELY`，正式角色不设独占标志，heavy 角色设置独占标志，范围是偏移 0 的 1 字节；无需写入该字节。按实际错误区分锁冲突和不可用，显式 `UnlockFileEx` 后关闭句柄。共享重叠、越过 EOF 的范围及实际进程终止后的锁释放依据 [Microsoft LockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex)；解锁范围依据 [UnlockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-unlockfileex)，结构布局依据 [OVERLAPPED](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-overlapped)。

Unix 分支使用非阻塞 `flock(SH/EX)`，见 [Python 3.13 fcntl](https://docs.python.org/3.13/library/fcntl.html)。本轮实际 OS 测试在 Windows；没有把 Unix 实现存在写成 Linux 实机通过。

## 5. 复现与边界

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run\process-temp'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_resources.py
```

两条审计依次运行；不要并行运行互斥审计和模型测试，否则它们应当互相拒绝。专项预检发现已有接入的正式会话时直接退出，不帮用户停止会话、服务或相机。审计只用隔离 TEST 库和灰色工程图；原生优化／进程退出是真实执行，图像没有人，不产生真人准确度结论。

详见 [本机验收](../validation/REHAB_COMPUTE_COORDINATION_2026-10-11.md) 和 [机器摘要](../../reports/rehab_backend/resource_verification.json)。

尚未覆盖旧桌面／旧 live、其他业务作业队列、全部下载／预处理／评估／报告导出、独立 APK、其他 checkout、机器或 GPU 上的非合作进程。默认 v2 派生报告仍按原独立所属进程运行，本增量未给它添加准入延期；不能称为全产品算力协调已经完成。后续须继续实现报告延期及重建状态、全入口协调、同硬件同输入的负载对照和目标手机验证；不通过改保护基准、放宽计次条件或关闭用户窗口来完成。
