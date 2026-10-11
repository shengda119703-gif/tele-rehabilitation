# 康复v2短时连续输入与并发控制：本机验收

日期：2026-10-11。实施基准`bead4d37aeecc7cef495e477586416cf7d744869`；工具源码以本记录所在提交为准。任务书6.4／6.6／7／15／P7的增量，不是完整任务完成或新客户端上线。

## 1. 实际修改与范围

新增[连续输入工具](../../tools/rehab_ml/session_load_audit.py)、[有界核验器](../../tools/rehab_ml/verify_session_load.py)、[7项工具测试](../../tests/rehab_backend/test_session_load_audit.py)，CLI加入`benchmark-session-load`。补[工作流](../development/REHAB_SESSION_LOAD.md)、索引、交接和[实施报告B3.11](../../reports/rehab_backend/IMPLEMENTATION_REPORT.md)。

未修改SessionService、API、协议／计次、原姿态模型／权重、生产参数／剂量、前端、整个Android、正常数据库或非康复业务。新建TEST应用、所属推理／报告进程和隔离库；不开网络端口、相机或用户窗口。工程白图／手动安排不是专业参考或真实患者轨迹，不写正常历史。

## 2. 真实命令与环境

产品环境Python3.13.12、torch2.9.1、Ultralytics8.3.199、CPU、原YOLO11n-pose／imgsz640。原权重SHA256为`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`，未升级依赖或训练模型。正式v2仍默认关闭，候选TCN未启用。

从仓库根运行：

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_session_load.py
```

最终专项`session-load-verification-d0c856cf`：7项算术／冻结投影测试，0.207秒命令退出0；3个原YOLO／真实ASGI子命令分别5.686／5.918／5.792秒，全部退出0。每轮发送1张冷启动图＋160次持续请求；目标80Hz，实际生产者耗时2.099／2.348／2.240秒，不能声称实现80FPS推理。

先保存三次计划再执行，不挑最好运行。完整命令／stdout与stderr日志hash、源码hash、每轮summary及details路径见[专项汇总](../../reports/rehab_backend/session_load_verification.json)。[单次摘要](../../reports/rehab_backend/session_load.json)只代表末轮，不覆盖原单帧基准。详情在忽略run中的独立SQLite和JSON，未纳入Git。

## 3. 接收、排队与冻结证据

| 独立run | HTTP200接收 | HTTP409规定拒绝 | SQL已处理 | SQL丢弃 | 槽覆盖 | 控制epoch丢弃 |
| --- | --- | --- | --- | --- | --- | --- |
| session-load-34b1275b | 58 | 103 | 25 | 33 | 23 | 10 |
| session-load-2e98475a | 67 | 94 | 30 | 37 | 27 | 10 |
| session-load-f5e113bb | 63 | 98 | 28 | 35 | 25 | 10 |

409仅接受`session_not_accepting_frames`这一预声明拒绝；暂停及终止以后不受理新帧。HTTP200集合与逐帧SQL集合完全一致；SQL处理＋丢弃等于已接收，没有pending、未解释或failed行。高水位不被当作处理帧数；丢弃reason与区间对账。三轮都实际发生槽覆盖，最大保留深度1。

三轮开始finish时生产者均未结束、均有真实推理在途；durable pending观测为1／2／2。诊断字段不是原子快照，不能根据某次retained=0推断没有其他已接收待处理帧。收尾后所有帧结清。

各轮31项事实核对全部为真：创建幂等、4个并发finish回执一致、同／换key重试、改载荷冲突、commit查询、冻结视觉／帧审计、6对控制增量、反馈重试只写一次、空自评不补零、独立只读重开一致、唯一最终事实及贡献、所属进程／线程释放。31是工具条件数，不是31项独立真人测试，也不将3轮累加为93名或93个单元测试。

每轮仅一条会话、一条finalize审计、一份计划贡献、一份canonical commit；4个结束响应是同一操作的相关样本。无人物输入确认次数为0，只证明没有凭空制造事实，不证明真人计次准确。补自评保留null，feedback revision=1且视觉digest不变。关闭后所属推理进程不保留，两消费者退出，resources_released为真；独立SQLite读连接显式关闭。

## 4. 延迟结果与门槛

预算在运行前由[backend.yaml](../../configs/rehab_ml/backend.yaml)固定为控制p95≤200毫秒。未改预算、工作量、原算法或阈值来通过。

| run后缀 | pause HTTP p95 ms | resume HTTP p95 ms | finish HTTP p95 ms | 连续阶段state p95 ms | 热YOLO p95 ms | 热结果年龄p95 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 34b1275b | 43.52 | 20.68 | 141.83 | 22.76 | 43.72 | 92.68 |
| 2e98475a | 44.69 | 16.91 | 144.41 | 20.28 | 40.87 | 88.48 |
| f5e113bb | 39.64 | 16.48 | 139.64 | 18.89 | 40.15 | 90.08 |

冷启动原YOLO进程往返分别2275.90／2261.03／2253.64毫秒；不得混入热样本或隐去。暂停／恢复每轮各6样本，finish每轮4个同操作相关请求；最近秩p95在小样本下接近最大值，不能证明稳定人群／全天性能。最终事务每轮仅1次，原值保留在各自诊断。

state采用`load_http`，不借冷启动等待期间的大量空闲查询压低负载p95。结果年龄仅指本宿主接收至处理／持久化边界，没有曝光时间或网络前段；RSS是周期观测而非峰值。时序候选未运行，耗时为null，不声称20毫秒模型预算在本次得到验证。

## 5. 完整回归与保护

`verification-6077fb98`实际退出0：364项新后端／178.073秒测试、12项原康复／0.086秒、19项原手机接口／12.96秒。7项新工具测试是364子集，不额外累计。命令耗时为181.242／0.235／13.556秒；scope命令5.275秒。原Starlette/httpx弃用warning保留，不为去掉warning升级产品依赖。

[回归报告](../../reports/rehab_backend/regression.json)保留四个命令、日志hash和终态；[范围结果](../../reports/rehab_backend/scope_verification.json)核对原1308份保护条目，变化0。保护基准SHA256保持`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`，没有重建。开工280份既有用户图片、CSV、任务书和导入脚本逐路径保留，排除本轮提交；交付前另核对当前状态与hash。

三轮工具测量前后9份源码／配置／原权重hash一致；核验器4份实现hash一致。早期`session-load-7c05d163`及`session-load-verification-d8a96e07／88d1dff4`也成功，留在忽略run；随后只补冷热HTTP拆分、送帧在途观测及只读连接显式关闭，再按相同负载重验。它们不代替最终源码证据，不删除或改写失败来选最好结果。本轮没有声称旧试跑有另存完整命令日志；最终核验器日志已实际保存。

交付前实际复核：280份开工文件的Git状态及SHA256变化0；8份命令日志、6份私有summary／details及4组实现hash无差异。六份本轮文档270个本地链接存在、9张表格列数一致、代码围栏配对；Git空白检查通过。改动清单恰为14份工具／测试／报告／必要文档，原280份不暂存。

## 6. 尚未完成与交付边界

这是约2秒持续请求、单活动会话、进程内ASGI的有界工程压力。没有公网／局域网延迟、多手机、长时内存／功耗、冷启动期间并发控制、物理故障、摄像头、手机实机或真人准确率；没有独立专业参考、合格RGB监督，不完成P5／P6或完整P7。

本轮只提交后端工具／测试／报告／必要文档；产品0.20.0、既有APK0.2.1、前端及首页／康复／健康／用药／家庭导航不变，v2仍默认关闭。推送核对origin/main后，用原脚本刷新桌面“安康康复（最新版本）”Git描述，保留原Start-Rehab.ps1、已验证pythonw.exe及原链接目标，不关闭旧窗口。整个任务继续进行。
