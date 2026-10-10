# 康复 v2 所属推理进程与诊断验收 · 2026-10-11

## 范围、复用和版本

按本机后端实施任务书，基准 `4d46061520427a59bf75d68305cb42042939faa9`，本文件所在交付提交为实际增量。保留原 VisionWorker／YOLO、EvidenceAdapter／EMA、GuidancePolicy、Storage owning thread、原计划及继续政策。新事实链仍是 opt-in，默认不启用；旧 `/api/live` 不自动保存。

本轮纳入既有未提交的 `pose_worker.py`／服务故障保护／17项隔离测试并重新验证，新增 `app/rehab_v2/telemetry.py`、诊断 API、9项测试、ASGI 性能 CLI。只改康复后端／工具／测试／报告／文档；整个 android_offline、正式网页／Qt UI、非康复、用户素材和正常患者库未改。未重启、关闭或重新部署原服务，未打开摄像头／麦克风；产品仍0.20.0、APK仍0.2.1，没有新安装包。

## 实现与不变量

| 问题 | 本轮实现 | 实际验证／边界 |
| --- | --- | --- |
| 推理线程硬挂起无法释放 | 一份准确所属 spawn Process；10秒握手、30秒首推理、5秒热推理；失败只清理该对象 | 真实挂起／退出／无握手、冷热不同预算与重建通过；OS Process.start 自身硬截止未验证 |
| 大图／回包阻塞 IPC | 父拥有4.5MiB共享区；JPEG≤512KiB、姿态JSON≤4MiB；通知≤4KiB | 500KiB输入、1MiB回包、容量／hash／ticket／Context／duration异常拒绝；本地可信子进程，不是恶意IPC隔离沙箱 |
| 不确认退出却重开 | 持有所属句柄并隔离，后续先重试释放 | 真实活子进程上受控阻止 terminate/kill 后保留，恢复操作才清理；不杀其他用户服务 |
| 暂停／结束晚结果污染 | 先检查控制／终结epoch才EMA；终结先保存事实再取消sid | 旧成功／失败不改变恢复上下文，不补次数／时间；冻结后的旧队列不再启动子进程 |
| 存储写入失败继续接帧 | 消费者退出，稳定 failure，拒绝新帧／新建 | 注入 OSError 后503、无假提交、重开interrupted；不等于真实磁盘满／损坏验收 |
| 报告线程仍占用SQLite时关闭 | 未确认则不释放库／lease，允许再次关闭 | 慢报告保持可查询；释放后关闭重试；真正硬挂起报告线程仍未隔离 |
| 没有分阶段诊断 | 服务端稳定trace_id＋认证diagnostics，固定数值／事件枚举 | 不含媒体／骨架／owner／原话／凭证，任意知道sid不能读；错误owner404、未登录401 |
| 诊断无限增长／伪造统计 | 每阶段512样本、事件总尾部128、固定阶段20个；累计计数独立于窗口分位数 | 700／1000事件、有界并发快照、未知／非有限值／动态键拒绝；重启统计不可用，不填0 |
| 检查点耗时冒充最终提交 | checkpoint_ms与final_commit_ms分开；关闭候选保持temporal_ms未知 | 重试结束仅一份正式提交；多次诊断不改变视觉快照／贡献 |

所有耗时为所属进程自身 perf_counter 差，宿主结果年龄／接收与处理率使用宿主 monotonic。没有子进程时钟与宿主相减，不把宿主接收说成曝光／客户端网络时间。`pose_result_age_ms` 在推理返回观察，`result_age_ms` 在完成检查点后观察。每个阶段分位数为保留窗口 nearest-rank，非整次全历史分位数；统计和即时 backlog／RSS 不是一份原子业务快照。JPEG会话没有录像job，job_id=null。

终结运行缓存最多32个（另有在途／当前对象）；淘汰只删诊断内存，正式SQL仍在。source.execution_trace_id随创建／重开保留，随机服务端字段不进入请求幂等摘要。诊断不参与任何动作／质量／计划判断。成功后传输共享区清零，失败先确认退出再关闭／unlink；不宣称存活模型内部RAM全部擦除。

## 本机实际验证

解释器：`rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe`，Python3.13.12；原 CPU YOLO11n-pose，ultralytics8.3.199，torch2.9.1+cpu、numpy2.2.6；没有升级依赖。所有测试库、原日志、临时媒体／输出位于忽略的 E盘 `.runtime/rehab_ml/run/`，不访问用户正常数据库。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m unittest -v test_telemetry
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py verify-sessions --database-mode isolated
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py benchmark-sessions --frames 12
```

首行实际使用临时命令环境 PYTHONPATH 指向 tests/rehab_backend、应用目录和仓库，9项通过；CLI／verify_all自行配置所需路径。会话CLI `replay-a339171a`：70项、53.656秒测试／54.270秒进程；日志SHA `23b0b008096925aa21d0ae4de9096db5af69074ef0c13ba745f4a300e9ccae6f`。70项为下面100项的子集，不累加。

末次完整 `verification-7ec35ad4`（[regression.json](../../reports/rehab_backend/regression.json)）：

| 组 | 实际结果 | 日志 SHA256 |
| --- | --- | --- |
| 新后端 | 100项通过，41.384秒测试／42.446秒进程 | `26edf5c8da50ed30a5c54b450f8b913b7c870ce7faa7ad0872de592629fd4a9c` |
| 旧康复 | 12项通过，0.088秒测试 | `08fbe870f346085a0f22fc43b802e62b0bbebf17efb3fe0533cd5415463801ba` |
| 旧手机接口 | 19项通过，12.93秒；1条既有Starlette/httpx弃用warning | `de1527d84c3831809ed7cb26a558cbaa170f1b631c3b5e924162784db4c92d6e` |
| 禁改范围 | 1308文件一致，changes为空 | `6d5f9c57ba17a1e2a439bf261f06d59cfc912dcb5c3bbcd179e8caa9ed0a81d6` |

保护基准SHA `75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`，未重建基准。前一次 `verification-0d415003` 也100／12／19通过；之后补取消／故障计数和对应断言，重新执行末次验证，不将先前运行当最后源码的证据。全程无新失败被忽略，已有warning未通过升级或改预期消除。

## 实跑性能与不能推出的结论

实际命令走认证ASGI HTTP、原CPU YOLO、规则和独立SQL；320×240无人白图、imgsz640、显式TEST计划，12帧逐次等结果后暂停／恢复，不打开相机。权重SHA `869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`。候选TCN关闭，动作确认0符合无人证据，不是准确率样本。

首次 `session-performance-7b603020`，随后补逐帧RSS／权重指纹后实际运行 `session-performance-a394a83e`；原始摘要SHA `be9f8dfa1f4c94f6a8d660a5283d09bc42fdc4f06831022b3a490e93177f8371`。该运行的冷首帧推理2035.68ms、含spawn／IPC的往返2286.91ms、宿主检查点完成年龄2316.51ms；11个热样本推理p95 40.87ms、往返p95 42.56ms、结果年龄p95 57.19ms。

ASGI HTTP暂停／恢复各12样本p95 17.78／13.58ms，低于事先200ms工程预算；状态查询245样本p95 2.77ms，诊断12样本p95 12.17ms。结束只1样本33.74ms、最终事务只1样本18.92ms，不称稳定分位数。最近帧后RSS：宿主63,356,928字节、所属推理319,066,112字节；这是采样值不是峰值。队列保留上限1，结束时持久pending为0。没有真实网络前段、手机、实际人群动作、多人压力、GPU／候选时序或全负载性能结论。旧IRDS微基准没有重跑。

性能摘要以 [session_performance.json](../../reports/rehab_backend/session_performance.json) 的末次实际 run 为准；补逐帧RSS的中间run为 `session-performance-65e98431`，随后补关闭证据才重跑上述末次run，原始目录与摘要仍保留。末次关闭确认 resources_released=true、pose_process_retained=false、两消费者alive=false；没有将未释放资源说成成功。冷／热分开，空图／夹具／未测范围保留。不能从这份性能报告推出角度、计次、提示或疾病准确率。新增命令 --help 正常，--frames 0 实际非零拒绝，不启动运行；该负向检查不是新增回归失败。

## 保留、交付及剩余目标

交付只暂存本轮所属文件。280份既有用户素材／README／任务书／CSV／导入脚本在交付前核对SHA并保留，不提交。模型权重、私人原片／骨架、环境、签名、数据和数据库按既有gitignore忽略。提交后核对origin/main完整SHA一致，维护桌面“安康康复（最新版本）”到Start-Rehab.ps1与实际`.venv/Scripts/pythonw.exe`，仅刷新Git版本描述，不关闭用户窗口；五页导航不变。

交付前实际核对6份文档的261个本地链接、连续表格列数和代码围栏均正常，Git空白检查与6份新增／改动Python语法检查通过。初次把280条指纹嵌入命令超过Windows长度限制，进程未创建；改用短命令枚举和调用侧对比后280份SHA一致、无新增／丢失，未因此改动用户文件。

完整任务仍为局部完成，后续继续：报告硬隔离、真实存储故障和负载压力、康复深蹲本人宿主计划绑定、同域RGB授权及专业独立可观察性／相位／提示标注、条件满足后的姿态微调／影子对照与目标手机实测。不重新定义总目标，也不因本轮工程回归通过而宣称P5／P6或整个任务完成。
