# 康复v2：异步结束的三个进程退出窗口

日期：2026-10-11。本轮基准`a9156c7622071bbf32db2551678481bc831775fc`，生产异步接口来自`04ab1ea`。对应后端任务书6.4–6.6、7、C15／C18／C23及P7。新增隔离验证工具与测试，不修改生产服务、动作算法、前端、整个Android、权重或正常用户库。

## 1. 验证哪个功能

用户结束训练后，需要能区分“结束请求已接收”和“训练事实已保存”。程序异常退出后，应找回已确认动作；没有确认的半次不能补算。同一次结束重试或换操作键，都不能重复产生事实和计划贡献。

原接口先保存冻结操作再返回202，后台另作最终事务。这次不改变它，而是让旧宿主在三个确定窗口真实退出，再使用原恢复路径对账。图中的SQL是同一份隔离库，不包含原产品JSON、录像job或手机IndexedDB。

```text
本人 + session + 冻结计划 + 逐次检查点
                 │
           原 finish HTTP API
                 │
        SQL冻结操作／接收边界 ── HTTP202
                 │                    ① 此时退出
           原后台 finalizer
                 │
        写最终快照／逐次／贡献           ② 事务未提交时退出
                 │
           同一SQL事务提交
                 │                    ③ 提交已成、HTTP回应未返回时退出
         唯一 canonical commit
                 │
    原恢复路径 → 查事实 → 原key／新别名重试 → 独立反馈
```

## 2. 三个窗口与期望结果

| 窗口 | 退出前独立SQL读取 | 退出后原恢复政策 | 结束请求重试 |
| --- | --- | --- | --- |
| `accepted_before_commit` | 202已返回；draft／finishing；操作回执finishing；0贡献 | 保留原检查点，终结为interrupted；未确认半次UNASSESSABLE | 返回新恢复生成的唯一canonical |
| `uncommitted_finalize` | 写入连接确实`in_transaction=true`；其他连接仍只见draft／finishing及0贡献 | 未提交写入不作为保存事实；按同一恢复政策终结 | 返回恢复canonical，不重复贡献 |
| `committed_before_http_reply` | finalized／ended；最终canonical与1贡献已可读；HTTP响应尚未返回 | 已提交事实与原user_stopped原因完全保留，不重新终结 | 返回原canonical，不另生成commit |

第二窗口在原`SessionRepository._save`执行后、原Storage调用返回提交前设置TEST屏障；不会用“刚发出结束请求”冒充正在事务内。第三窗口持有原请求返回，只在独立查询确见最终commit后设置屏障；不等于网络断连实测。

每个用例先建立1次确认动作和1个真实存在的未完成动作，再登记1条accepted但未处理的内部TEST证据行。它不是原生推理在途帧，不用它证明模型进程被宿主退出时的清理。原公开JPEG／任意关键点输入边界没有放宽。

## 3. 对账的算法与身份

设终结前已经持久化的确认集合为`R`，未确认部分为`u`：

```text
确认数量：       N_after = |R|，不把u补成完成动作
视觉事实校验：   commit.visual_snapshot_digest = digest(final_snapshot)
唯一贡献：       count(contribution where session_id=s) = 1
重试不增量：     commit(s, key₁) = commit(s, key₂) = canonical(s)
空自评：         pain=null，fatigue=null，不转成0
二次重开：       database_view_after_second_reopen = database_view_before
```

这些是工程不变量，不是医疗公式。TEST内部回放带SYNTHETIC来源，其贡献不具正式计划完成资格；工具只证明唯一贡献记录和最终事实的一致性，不宣称真人计划完成、剂量或继续资格。

对账同时检查：确认逐次原样保留；半次变UNASSESSABLE且current清空；逐次表等于最终快照；pending行结清为process_restart或finish_boundary_timeout；所有finish回执指向同一canonical；只有一个终结审计；换载荷409、恢复已终结会话409、另一个owner查询404；创建键重试仍是原session；null反馈重试只有1行且不改视觉事实；第二次独立Store／Service重开不再恢复或改变库。

## 4. 进程与测试边界

[async_recovery.py](../../tools/rehab_ml/async_recovery.py)为每窗口创建新TEST库及新宿主。父程序一直持有准确`Popen`句柄，在屏障处核对实际PID、存活和独立SQL状态后，只终止该句柄并等待实际非零退出。不会按进程名、旧PID文件或扫描结果结束用户服务。

Windows虚拟环境启动器可能有不同PID；本工具参照本机CPython `multiprocessing/popen_spawn_win32.py`，直接持有base interpreter并用`__PYVENV_LAUNCHER__`保留原venv初始化。屏障必须证明PID就是所持句柄，不能拿启动器退出冒充实际宿主退出。这是测试启动方式，不是生产原生worker重构。

旧宿主确实被强制退出；后续恢复发生在监督程序内新建的Storage、Service和原API生命周期，并非启动第二个真实socket服务器。使用原进程内ASGI路由，测试cookie仅供隔离owner。报告消费者预先退出，屏障还检查原生姿态／报告子进程均未启动。原库仍走原Owning-thread SQLite，不用另一套存储实现替代。

## 5. 复现与证据

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/async_recovery.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_async_recovery.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
```

[四项测试](../../tests/rehab_backend/test_async_recovery.py)包括三窗口真实退出、既有输出拒绝、路径／窗口拒绝和失败返回非零。专项核验器运行前声明4项测试＋3次工具重复；每次工具分别检验3个窗口，每窗口32项条件。日志、退出码、10份源码hash及每窗口独立SQL／回执／逐次details在忽略目录保留；Git只保存工程摘要，不包含真人数据或原片。

最终专项`async-recovery-verification-f00e75d2`退出0，3轮共9个窗口均通过，每个实际宿主退出码为1。具体命令、hash和早期工具失败见[本机验证](../validation/REHAB_ASYNC_RECOVERY_2026-10-11.md)及[汇总](../../reports/rehab_backend/async_recovery_verification.json)。不把32条件、9窗口和4项测试相加成真人或独立单元测试数量。

## 6. 仍未证明的事项

这次没有人体金标准、实际相机／手机、socket断网、物理断电、磁盘满、长时多客户端，也没有在原生推理／报告子进程活跃时强制退出宿主。不能据此宣称原生孤儿进程风险已解决、全部故障窗口完成，或模型准确性提高。随机物理故障、资源所有权和目标设备仍需分别验证。

产品0.20.0、既有APK0.2.1、v2默认关闭。前端、APK、旧live和原管家工具并未因本工程审计接通v2；完整后端任务仍局部完成。
