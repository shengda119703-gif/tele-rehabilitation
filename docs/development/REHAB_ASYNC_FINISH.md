# 康复v2：结束接收与最终保存分离

日期：2026-10-11。实施基准`17a0827c9468949ffe029356f7c5b76bfd8bd774`。对应任务书6.4、6.5、6.6、7及C15／C16／C19／C23。只改默认关闭的康复v2后端和工程验证工具，不改原`/api/live`、前端、整个Android、动作规则、原权重或正常用户库。

## 1. 实测问题

此前持续输入工具先等待首帧完成，再测控制。因此其约140毫秒finish不能说明冷启动期间的结束速度。新增[冷启动审计](../../tools/rehab_ml/session_cold_audit.py)在真正所属原YOLO进程存活、首个native ticket已发出、`warm=false`且尚无已处理帧时发暂停、恢复和四个同操作finish。

未改服务前的`session-cold-a2227f99`发现：暂停16.47毫秒、恢复16.89毫秒，finish四个相关请求p95 **2040.33毫秒**，超过已有200毫秒预算。逐帧／事实对账通过，但性能总验收失败；[原始失败摘要](../../reports/rehab_backend/session_cold_before.json)保留，不能用后来的成功覆盖。

原因是HTTP直接调用阻塞的`SessionService.finish`。它冻结后要等边界内推理和保留帧，最多2秒；线程隔离避免阻塞事件循环，但并没有让这个HTTP请求本身尽快响应。

## 2. 新接口语义

`POST /api/rehab/v2/sessions/{sid}/finish`沿用原请求、鉴权、幂等摘要和revision规则，新增两种明确结果：

| 响应 | 含义 | 接下来读取什么 |
| --- | --- | --- |
| HTTP202，`status=finishing` | 接收边界和本次操作已写SQL；不是最终训练事实，不含commit_id | 同本人`GET /sessions/{sid}/commit` |
| HTTP200，`status=finalized` | 返回原唯一canonical commit；重复调用不新增事实 | 可查询事实、贡献和独立反馈 |
| 409冲突 | 同key异摘要、首次revision等实际不满足 | 不换key强行绕过；核对原载荷和状态 |
| 503消费者／队列不可用 | 此次未安排新的后台任务 | 查询commit和状态，恢复后用原key、原载荷重试 |

202体只含`status`、`session_id`、`accepted_last_seq`。后者是接收高水位，不是有效帧数。处理中查询仍有`persistence_state=draft`、`receipt=null`；保存事务成功后才有`receipt.status=finalized`。报告完成不作为事实保存的前提，反馈仍要等最终事实。

不能收到202就显示“已保存”、开始后续剂量或补填自评。本轮没有改客户端；后续连接新接口时必须实现这个协议。原产品路径及独立APK不会因为此改动自动采用它。

## 3. 信息和所有权怎样传递

1. `request_finish`先核对本人、key和载荷摘要。已终结的同key重试优先返回回执，不重新用已改变的revision拒绝。
2. 持有短控制锁与运行锁，由原`SessionRepository.freeze`在SQL中保存`run_state=finishing`、固定`finish_last_seq`、原结束原因和操作receipt。持久化成功后才进入队列或返回。
3. 宿主只有一个finalize消费者、容量1保留槽、按session去重的在途集合。相同操作处理中重试直接返回其SQL回执；别的key关联同一冻结事实，不另开任务。
4. 所属后台线程调用原`_finish`：保持原2秒收尾上限、finish_lock、control epoch和terminal epoch。没有减小等待时间、取消可解释的收尾或放宽视觉门槛来改善HTTP数字。
5. 原最终事务同时保存快照、逐次、未处理区间、终态、canonical commit和唯一贡献；每个关联finish操作的回执都更新为相同commit。晚到结果不能重写它。
6. 事务失败不产生成功回执。运行查询增加`finish_consumer_alive`和`finish_failure`，只属执行诊断，不进入视觉事实。已冻结操作保留；所属尝试退出后，相同key重试可重新排一次。
7. 关闭时停止接新操作，等待所属帧、finalize和报告消费者实际退出，再关闭SQLite／宿主锁。不能把发出停止请求当作释放。突然崩溃仍走原`recover_unfinished`，未终结会话按原政策恢复为interrupted，不重新打开已finalized记录。

内部`finish`保留阻塞的完整回执语义，供已有测试、回放和关机收尾调用。HTTP不再走它的等待路径。执行诊断的`finish_request_ms`和本轮HTTP耗时说明接收请求；真正最终事务仍单列`final_commit_ms`。关机内部调用仍可能记录长时延，不用它与短HTTP请求混算。

## 4. 验证方法和复现

[八项新测试](../../tests/rehab_backend/test_async_finish.py)用可控所属任务检查：持久化先于工作／202、处理中并发去重、key冲突／别的本人拒绝、坏revision不冻结、消费者退出不冻结、保存失败重试、关机实际join、最终200／空自评。它们是工程测试，不是人体真值。

[verify_session_cold.py](../../tools/rehab_ml/verify_session_cold.py)在运行前登记3次原模型重复，每轮使用新的隔离库和新的所属进程。状态或锁文件不证明进程在工作；工具同时核对actual process.is_alive、首个native ticket、在途seq、warm状态及SQL处理数。每轮保存source／weight hash、声明预算、HTTP原时延、逐帧审计、快照、回执、独立只读重开及退出结果。

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py benchmark-session-cold
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_session_cold.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_session_load.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
```

CLI失败返回非零；不得将超预算、无真实冷ticket或无最终回执当作通过。连续负载工具和原单帧微基准现在显式查询最终commit，不将202体拿来检查贡献或反馈；原工作量、200毫秒预算、模型和算法不变。

## 5. 能证明什么，不能证明什么

冷启动三轮`session-cold-verification-d7229cf9`八项测试与三个原模型实验退出0。finish p95为14.72／17.08／15.29毫秒，而从请求至查到最终事实仍为2048.51／2056.24／2057.44毫秒。**改善的是接收响应，不是YOLO启动或最终保存速度。** 每轮只有4个同操作请求、1次最终事务，不能把这些相关样本当作统计稳定的长期性能。

三个原模型实验均有1帧超时未处理，明确保存为`unprocessed/finish_boundary_timeout`；不填成有效帧、0°或动作次数。每轮23个事实／边界检查通过，无人白色JPEG始终0确认次。模型、规则、预算和处理范围没有为通过而改变。

只覆盖本机CPU／短时／单活动会话／进程内ASGI。网络前段、手机、实际相机、真人独立参考、长时压力和随机物理故障尚未验收。数据／专业标签缺口仍在，完整后端任务未完成。当前准确性候选仍关闭，产品0.20.0、APK0.2.1、五页导航不变。
