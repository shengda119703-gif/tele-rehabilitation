# 康复v2连续JPEG输入、并发控制与持久化核对

日期：2026-10-11。对应后端任务书6.4、6.6、7、15.3的C14–C16／C19／C23及P7。只新增工程验收工具，不改生产模型、阈值、正式业务或客户端。实际结果见[本机验收](../validation/REHAB_SESSION_LOAD_2026-10-11.md)。

## 1. 为什么另做一次负载测试

原[会话微基准](../../tools/rehab_ml/session_benchmark.py)每次送帧后等待处理完才继续。它能测单帧和空闲控制，但没有持续输入产生的槽覆盖与控制竞争。本工具不等待每次推理完成，使用真实认证ASGI接口和默认所属YOLO进程；不是注入假的视觉provider。

测试入口是新建FastAPI应用，不开监听端口，不访问8765／1396，不打开相机，不关闭用户窗口。SQLite库、完整请求日志及逐帧审计在新建的忽略run目录；身份、手动安排和输入均明确为TEST工程对象。白色320×240 JPEG没有人，不能用来评价关节误差、计次召回、质量识别或医疗结果。

## 2. 固定负载与信息链

[session_load_audit.py](../../tools/rehab_ml/session_load_audit.py)在发请求前写`predeclared.json`，冻结源码／原权重hash、环境、`backend.yaml`预算和工作量。

1. 同一创建载荷重复调用，检查session ID一致；发送一张冷启动图并等待真实模型处理。
2. 单生产者持续尝试160帧，目标请求间隔12.5毫秒，不等视觉结果；每个HTTP请求仍等待自己的接收响应。实际速率受请求耗时限制，不声称80 FPS摄像头或80 FPS模型。
3. 并行查询状态与诊断；执行6对暂停／恢复，每次使用当前revision。暂停／finishing／ended期间新增帧的`409 session_not_accepting_frames`属于规定拒绝，必须单独统计，不能当已接收或已处理。
4. 完成6对控制、生产者至少尝试100帧后，发送4个同key同载荷的并发finish。记录此时生产者是否已经结束、在途／保留／durable pending观测；不假定一定命中在途。
5. 继续跑完已声明的生产者；同key重试、换key重试、同key改载荷、commit查询分别检查。旧revision不应拒绝合法幂等重试；改载荷必须冲突。
6. 明确提交`pain=null／fatigue=null`并重复请求，检查一次feedback revision、缺值不补零、视觉事实及唯一贡献不变。
7. 等待所属帧任务结清，比对冻结后的快照和逐帧审计。关闭所属服务后，再用独立只读SQLite连接核对正式事实及贡献，显式关闭连接。

这里的四个结束请求属于同一个操作，不是四次独立训练；每轮只有一份最终事务。报告可以异步变化，因此冻结比较只排除报告／诊断状态，不排除视觉snapshot、接收／处理边界、丢弃区间、terminal epoch和贡献。

## 3. 核对规则

| 问题 | 实际核对 |
| --- | --- |
| 高水位以下是不是都处理过 | 按SQLite逐帧状态对账；`accepted_last_seq`不作为有效帧数量 |
| 成功接收响应会不会丢记录 | HTTP200帧seq集合与审计行集合完全一致，processed_count按processed行计数 |
| 最新帧槽有没有无限积压 | 记录max_retained_queue_depth、latest_replaced和in-flight；槽容量仍为1，不将正在推理的一帧算作槽内帧 |
| 暂停后旧结果会不会污染 | 控制事件增量保存，旧epoch丢弃原因入审计；本次无人输入不得出现视觉确认次数 |
| 丢弃／超时是否解释清楚 | dropped／unprocessed／failed帧与明确区间及reason对账；终结后不留accepted pending行 |
| 并发／丢回执重试会不会重复 | canonical receipt相同；一条finalize审计、一条贡献、独立重开也各一行 |
| 结束后新帧或反馈是否改变事实 | 视觉snapshot与原回执、逐帧状态、贡献保持；反馈独立revision |
| 关闭是否只是假装释放 | 所属推理进程不再保留、两消费者退出、resources_released为真 |

诊断的队列、在途和SQL pending不是一个原子业务快照，采样中可能处于不同瞬间。最终对账依靠稳定终态的SQLite行，不用某次诊断数值推断未处理帧全部有效。

## 4. 延迟、失败与复现

预算从[backend.yaml](../../configs/rehab_ml/backend.yaml)读取，控制p95为预先200毫秒。暂停／恢复／finish分别统计；任何超预算或事实检查失败，CLI返回非零，保留已执行结果。每轮只有6次暂停、6次恢复、4个同操作finish，不能宣称统计稳定或全负载性能已验证。最终事务只有1次，保留单次耗时，不将它当独立重复的p95证据。

冷启动单帧与热处理分开；状态查询另给连续阶段`load_http`，避免冷启动等待期间的大量空闲查询稀释压力时延。`result_age_ms`包含本宿主定义的接收至持久化处理耗时，不包含手机曝光和网络前段。RSS只是周期观测，不是峰值、GPU显存或手机功耗。候选TCN未启用，其阶段为null而非0毫秒。

从仓库根执行：

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py benchmark-session-load
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_session_load.py
```

`verify_session_load.py`先保存三次重复计划，再运行7项核对算术测试及3次同负载原YOLO实验，逐命令保存stdout／stderr、退出码、耗时和hash。每次从自己的子进程JSON获取明确run ID，不读“最新目录”；中途失败就保留失败并停止，不能挑最好一次覆盖它。源文件变化拒绝总验收。

结果：`reports/rehab_backend/session_load.json`是最近单次；`session_load_verification.json`关联三轮、日志与每轮独立summary／details。早期开发试跑保留在各自run，不混作当前源码的验证。原[单生产者基准](../../reports/rehab_backend/session_performance.json)不被覆盖。

## 5. 尚未覆盖

此检查是短时、有界、进程内HTTP、单活动会话工程压力，不能替代网络、多手机、长时间运行、冷启动期间并发控制、真实摄像头／手机解码、真人动作、独立专业参考或物理故障。完整任务仍需这些证据；本工具不打开生产开关或改变已有历史。
