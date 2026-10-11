# 康复v2异步结束：本机验证记录

日期：2026-10-11；实施基准`17a0827c9468949ffe029356f7c5b76bfd8bd774`。正式源码以本文所在提交为准，具体源码／权重／命令日志hash在关联JSON中。对应任务书6.4–6.6／7／15的C15、C16、C19、C23及独立P7。

## 1. 本次真正改变的行为

原HTTP finish等有界推理收尾；现在先持久化原SQL freeze，返回HTTP202／finishing，再由一个所属finalize线程完成原事务。最终receipt未产生时commit仍null；同key合法重试不重复排任务，已终结返回HTTP200及原canonical。原key异载荷仍409，别的本人不能读写；失败不生成成功回执，原键可在所属尝试结束后重排。

保留2秒收尾、原权重／CPU／imgsz640、相位／计次／质量／null自评、最终事实与贡献同事务、晚到结果排除、内部阻塞finish和原live语义。添加关闭join与执行故障状态，不把202当保存成功。方法见[工作流](../development/REHAB_ASYNC_FINISH.md)。

不改任何页面、整个Android、原生产规则、正常库或非康复业务，不启停用户服务／相机、不关闭旧窗口。隔离TEST身份、手动安排和白色320×240 JPEG没有人体；不评价角度误差、动作准确率或临床收益。

## 2. 修复前失败保留

`session-cold-a2227f99`在原所属进程存活、首native ticket已发送、warm=false、seq1在途、处理数0时进行控制。暂停16.47ms、恢复16.89ms，finish四个相关请求p95 **2040.33ms**；预声明预算200ms不变。23项边界／事实条件通过，但`passed=false`、CLI退出1。不能因为事实正确就称性能通过。

固定[原失败摘要](../../reports/rehab_backend/session_cold_before.json)保留工具／原服务／原API／原权重hash、环境及自己的raw summary／details路径与hash。私有原文件分别为`session-cold-a2227f99/summary.json`与`details.json`，不通过“最新目录”定位。

开发首轮修复验证`session-cold-a2161eca`成功，但不替代最终三轮。两次新单元测试开发试跑退出1，问题在TEST夹具的独立SQLite连接未显式close、旧服务关闭前gate未释放、不存在的feedback字段及Future遮蔽closing名称；修正测试后复验，未改变生产视觉算法、控制预算或事实门槛。其stdout／stderr保留于本轮工具调用，不冒充已有磁盘日志。

## 3. 修复后预声明三轮冷启动

[专项汇总](../../reports/rehab_backend/session_cold_verification.json)固定`session-cold-verification-d7229cf9`。运行前声明3次，先跑8项异步结束检查，再跑3次原模型冷输入；4个子命令全部退出0，源码未变。每次使用不同所属进程与新隔离库，不是从旧状态文件推测存活。

| run后缀 | 暂停p95 | 恢复p95 | 结束接收p95 | 请求至查到最终事实 | 事实条件 |
| --- | --- | --- | --- | --- | --- |
| c8fc2e3f | 12.83ms | 14.05ms | 14.72ms | 2048.51ms | 23／23 |
| 89c5882e | 13.14ms | 13.46ms | 17.08ms | 2056.24ms | 23／23 |
| caf7cbab | 13.70ms | 13.99ms | 15.29ms | 2057.44ms | 23／23 |

每轮有1帧明确`unprocessed/finish_boundary_timeout`、唯一freeze／最终事实／贡献、0确认次、空疼痛／疲劳与一次反馈revision；关闭后独立只读重开快照一致，所属进程／消费者实际退出。终态未处理片段不能算有效0°或动作失败，也不能填成processed。

一轮只有1次暂停、1次恢复、4个相关finish和1次最终事务。p95是这些实际有限样本的计算结果，不是大样本稳定性保证。约2秒收尾未被缩短；改善的是HTTP接收响应，而非模型冷启动、最终提交速度或测量准确率。

## 4. 热模型持续输入复验

[复验汇总](../../reports/rehab_backend/session_load_verification.json)为`session-load-verification-58572d12`；7项对账算术检查＋原模型3轮全部退出0，工作量仍是1冷帧后160次持续请求、6对暂停恢复、4同操作finish、查询／重试／反馈／独立重开。对202明确等commit再做反馈和最终对账，不删掉旧事实断言。

| run后缀 | HTTP接收／规定拒绝 | SQL处理／丢弃 | 暂停／恢复／结束接收p95 | 条件 |
| --- | --- | --- | --- | --- |
| 06f1bec6 | 59／102 | 26／33 | 40.94／29.75／48.21ms | 31／31 |
| 57be5b0b | 65／96 | 29／36 | 45.31／17.40／44.40ms | 31／31 |
| c8dd6b15 | 65／96 | 29／36 | 36.73／15.69／46.60ms | 31／31 |

三轮结束时生产者未完成且推理在途，保留槽最大深度1；所有接收帧在SQL有明确状态、所有finalized后快照不变、每轮只一事实／贡献，退出已确认。原阻塞接口的`session-load-verification-d0c856cf`固定保存在[此前归档](../../reports/rehab_backend/session_load_before_async_finish.json)，不混为此次响应口径。

另外运行已修改的单帧微基准，`session-performance-2c749df8`实际8张原YOLO白图；finish接收14.31ms、202／finishing，工具随后取到canonical finalized，全部所属消费者退出。共享报告为[当前单帧摘要](../../reports/rehab_backend/session_performance.json)，原摘要保存在[此前归档](../../reports/rehab_backend/session_performance_before_async_finish.json)。其生成raw summary hash为`218db62ca8b8bd9adaa9e7be895c8910458861fb7341f062deab69d7ec2970a4`；外层工具首次解析混合告警文本失败，未把它当实验失败或重跑，随后只读核对该明确run的完成产物。此命令stdout未另存完整磁盘日志，不等同两个专项的日志证据。

## 5. 完整回归与保护

[完整回归](../../reports/rehab_backend/regression.json)为`verification-2e35a106`，4条实际命令均退出0：

| 检查 | 实际结果 | 日志SHA256 |
| --- | --- | --- |
| 新后端 | 372项，191.943s单元运行时间 | 4d78761da81663b63fce5af7c7c2833de2a234da6fd7efb2a69a1959471c0f0e |
| 原康复 | 12项，0.088s单元运行时间 | 08fbe870f346085a0f22fc43b802e62b0bbebf17efb3fe0533cd5415463801ba |
| 原手机接口 | 19项，13.10s pytest运行时间 | 4355828600fdcaeb48e37eadf8d1cc3d920dec5e817a9afe1c0ee276d51c8ff9 |
| 禁改范围 | 1308文件，changes=[] | 71b09dbedefc378c193b6ffd6875b21a04f25679030e5c4493320760500ea0a2 |

原保护baseline SHA256为`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`，不重建。8项新测试和7项旧工具测试是372子集，不相加。日志及具体参数已写各自JSON；旧364／357项是历史，不累计为当前测试数。pytest保留原Starlette/httpx弃用告警，未升级环境。

开工280份用户未提交文件包括动作图片、README增补、CSV、任务书和导入脚本；交付前逐路径／状态／SHA256核对并仅暂存本轮明确清单，不把这些文件带入提交。大模型／私人数据／TEST库及日志继续忽略，不纳入Git。

交付复核280份原文件变化0、本轮明确30文件清单外新增0、暂存原先为空；原1308保护再验通过。8份文档520个本地链接无缺失、代码围栏闭合，`git diff --check`通过；25次日志／原始产物hash及64次当前源码hash核对无差异。原受保护清单未重建。

## 6. 实际复现与未完成目标

实际使用本机原Python3.13.12、torch2.9.1、ultralytics8.3.199和原YOLO权重；没有新依赖、付费算力、数据授权操作或训练。

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B -m tools.rehab_ml.session_cold_audit
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_session_cold.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_session_load.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py benchmark-sessions --frames 8
```

独立专业目标域标签、合格真人RGB微调、原模型与候选独立准确性对照、手机／网络／长时和全部物理故障仍未完成。当前只补一类真实工程缺口，P7仍partial，完整目标保持未完成。

产品0.20.0、APK0.2.1、v2默认关闭；首页／康复／健康／用药／家庭五页不变。推送后核对origin/main与本地，再以原脚本／已验证pythonw.exe刷新桌面“安康康复（最新版本）”Git描述；保留原E盘链接目标，不开新窗口、不关闭旧窗口。
