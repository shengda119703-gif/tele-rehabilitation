# 康复 v2 原生 SQLite 故障边界验收

日期：2026-10-11（Asia/Shanghai）。本轮基准`98e1c18`；此前报告隔离实现`06366bd`。本记录和实现随本轮提交发布，不倒改之前文档交付或历史验收。产品0.20.0、APK0.2.1、v2默认关闭。

## 1. 实现和权威边界

新增`app/rehab_v2/storage_boundary.py`与`tests/rehab_backend/test_storage_faults.py`，接入v2 service／API和会话CLI。原`app/storage.py`、正式UI、整个Android、其他业务、权重、训练剂量及继续政策不改；未重启原服务、打开相机或写正常患者库。

适配器复用原Storage连接、owning thread、队列、事务和rollback。按异常实际`sqlite_errorcode`低8位分类扩展码，只转换FULL／READONLY／BUSY／LOCKED／CORRUPT／NOTADB／IOERR／CANTOPEN；约束冲突、SQL错误、无对应原生码的异常保持原义。v2初始化后设置`busy_timeout=250`并在owning thread内消费PRAGMA游标，避免游标跨线程残留。

HTTP `SessionError`仅对该故障增加`storage_fault`元数据，固定503码为`formal_store_capacity/readonly/busy/corrupt/io/unavailable`。不输出原SQL、私密路径或伪回执。`commit_state=not_confirmed_by_this_error`不是“肯定未提交”，恢复后应查commit并以原幂等键重试。损坏库不自动删除、修复或建空库。

回调在原SQL工作rollback并返回错误之后执行；`last_storage_fault`只在进程内保存最后观察信息，不证明当前健康或已持久化。检查点故障停止帧消费者、确认所属推理资源释放并拒收后续工作，不写成input_failed；恢复存储后仍需重开服务对账。报告写失败保留pending，最终事实／回执／唯一贡献不倒退；反馈写失败不改变视觉事实或反馈revision。

## 2. 12 项真实 SQLite 专测

所有数据库和损坏副本位于E盘忽略的`.runtime/rehab_ml/run/`专用临时目录。测试动作是内部TEST骨架，JPEG为白图夹具，不是患者临床验收。

| 用例 | 实际条件与断言 |
| --- | --- |
| 只读连接 | `mode=ro`触发READONLY8；写失败、原库hash不变 |
| 控制只读 | query_only触发8；RAM／SQL revision不推进，恢复后原pause键重试只执行一次 |
| 最终事务容量限制 | max_page_count及事务内256KiB TEST触发器触发FULL13；最终事实、报告、唯一贡献一起回滚，恢复后原finish键仅一份贡献 |
| 外部写锁 | 独立TEST连接BEGIN IMMEDIATE触发BUSY5；250ms锁预算，单次断言小于1.2秒；快照不变且同键可重试 |
| 业务／代码错误 | UNIQUE约束和错误列名保留sqlite原异常，不写成存储不可用 |
| 感受只读 | 反馈写入8；视觉事实、回执和贡献不变、feedback_revision不推进；恢复可重试 |
| 报告只读 | 本地调度钩子开启query_only，实际派生SQL写入8；pending保留，恢复后重建不重计 |
| 损坏副本打开 | 修改TEST备份文件头触发NOTADB26；两次打开均拒绝、故障原件hash不变、lease释放 |
| 明确备份恢复 | SQLite Backup API将已知一致备份恢复到新TEST路径；原备份hash不变，仅已有检查点恢复并终结interrupted，一份回执／贡献 |
| 在途检查点只读 | 实际所属spawn夹具推理期间开启query_only；持久处理数0、无回执、input_failed0、background_failure1、所属资源确认释放；恢复后不自动复活消费者 |
| HTTP只读创建 | 原生8返回固定503和不确定提交语义，无路径／SQL／伪回执；恢复同创建键返回唯一session |
| HTTP锁与提交查询 | 外部锁返回503；commit查询仍显示receipt null、revision0；释放后原控制键200且幂等 |

FULL由SQLite页容量限制产生，**没有填满真实磁盘**。mode=ro／query_only不替代全部Windows ACL；TEST文件头损坏不等同B-tree、断电或介质故障。恢复是已知备份到新路径，不覆盖故障原件，不创造备份之后丢失的测量。IOERR／CANTOPEN有分类实现，本轮没有故障硬件实测。

## 3. 实际执行和日志

此前同一代码状态已完成完整回归与会话CLI；本轮重新核对现存日志SHA并单独复验12项存储测试。完整／会话记录纳入本轮发布，不把之前文档任务称为新实施。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py verify-sessions --database-mode isolated
$env:PYTHONPATH='E:\game\health-care-software-main\tests\rehab_backend;E:\game\health-care-software-main\rehab_codex_single_camera_v2_1;E:\game\health-care-software-main'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B -m unittest -v test_storage_faults
```

| 运行 | 结果 | 实际耗时／记录 |
| --- | --- | --- |
| verification-1d000563/new_backend | 130项通过，exit0 | unittest79.393秒、命令80.468秒；其中12项存储及18项报告测试 |
| 同run旧康复 | 12项通过，exit0 | unittest0.095秒、命令0.257秒 |
| 同run旧手机 | 19项通过，exit0 | pytest12.87秒、命令13.406秒；既有1项Starlette/httpx弃用warning |
| 同run保护检查 | 1308文件一致，exit0 | 命令5.290秒；changes空 |
| replay-2167d5a9/sessions | 100项通过，exit0 | unittest82.646秒、命令83.272秒；是130项子集，不相加 |
| 本轮单独存储复验 | 12项通过，exit0 | unittest12.689秒；工具会话91235，未另生成持久日志 |

完整摘要见[regression.json](../../reports/rehab_backend/regression.json)，会话入口见[session_verification.json](../../reports/rehab_backend/session_verification.json)。现存日志SHA256本轮重新计算一致：

| E盘忽略目录内日志 | SHA256 |
| --- | --- |
| verification-1d000563/new_backend.txt | `c19d6c9883c6d3d30d61611c316f963fe7892606adea8aac0e9382bd73c850d1` |
| verification-1d000563/legacy_rehab.txt | `e8a0c1d8219e5bc513e11ea1e4b50cbd9be043a753db0e058e010f976c7cf62e` |
| verification-1d000563/legacy_mobile.txt | `808379affbd78fc54899d5791aab112877280e225075056d2a90f1adff253e32` |
| verification-1d000563/scope.txt | `7e77cc8e762b73a6f9343321acd5c2f2ebfbea1202d4460b9e80e10b03b4b6e8` |
| replay-2167d5a9/sessions.txt | `e97c209a9307264c90005e2dbe4c28faeb701297fce4e865b7f17adaa40495e4` |

早期专项曾因PRAGMA返回游标未在owning thread消费导致Windows测试文件清理失败；修复为fetchone后复验通过，没有修改断言掩盖。早期CLI省略必须的`--database-mode isolated`被参数检查拒绝；上述明确参数的运行通过。历史错误不计为成功，也不代表业务数据损坏。

## 4. 保留与后续

提交前核对1308 protected hash及280份用户未提交素材／说明／CSV／任务书／导入脚本；不重建保护基准，不stage用户路径。仅提交本轮明确的v2实现、测试、CLI、工程摘要和说明。桌面快捷方式继续指向已验证产品环境，提交后只刷新Git描述，不关闭旧窗口。

本轮没有重新训练IRDS、重放私人录像、运行手机／临床／全UI测试，也没有改变原模型、规则阈值、剂量或正式路径。物理磁盘满／介质故障、未知原生死锁、OS创建硬截止、持续压力、深蹲宿主计划和目标RGB专业参考仍待完成。SQLite250ms只限该连接初始化之后的锁等待，不限Storage初始化、Future等待或整个HTTP耗时。整个任务保持进行中。
