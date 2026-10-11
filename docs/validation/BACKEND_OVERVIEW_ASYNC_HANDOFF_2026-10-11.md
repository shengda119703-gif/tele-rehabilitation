# 全后端阅读版：当前源码与信息交接核对

日期：2026-10-11。已提交源码基准：`04ab1eae7b075a8a3b8ee3017960fb1de94611a7`。

## 1. 本次交付与范围

用户需要一份Markdown，逐项梳理后端功能、技术方法和功能间的信息传递，以讨论准确性与可靠性优化。继续维护[同一阅读版](../后端功能与技术实现梳理.md)，不另造重复主文档。

本次只修改阅读版、文档索引、HANDOFF和本记录四份文档。没有实施新算法、调参或计划政策，没有训练、分析私人录像、启动业务测试、启停服务／相机、修改UI或Android。此前后台目标是否完成不由本次文档交付决定。

## 2. 内容核对

- F01–F34覆盖档案、输入／视觉、康复评估与训练、健身／器械、体态与居家、健康检测、管家／语音／OCR／资料、照护、家庭／同步、v2和离线工具等主要域。
- 保留逐功能输入、计算／公式、输出、存储、消费者、函数与参数；七条业务链区分电脑、托管网页、本地APK及默认关闭v2。
- 3.7新增实际连接键与排错方法：帧身份／时钟／坐标、job→session、评估指纹、plan revision、训练自评、事件、工作流回执、v2最终事实和报告版本。
- 查阅`mobile_rehab/analyzer.py`，确认先结束保存康复session、再写result.json；两者不是总事务。
- 查阅`mobile_rehab/rehab_v2/api.py`及`service.py`，确认HTTP调用request_finish；SQL冻结后202只表示接收，单消费者调用原收尾／最终事务；内部finish仍阻塞。
- 查阅`app/rehab_v2/sessions.py`，确认freeze／finalize／feedback／report_state／recover_unfinished的责任：最终事实及唯一贡献同事务、反馈独立revision、报告CAS、未终结重启按interrupted恢复。静态阅读不证明新异步路径所有强制崩溃窗口或物理断电已经验证。
- 16.7用当前异步接口三轮结果，并保留旧阻塞接口的归档来源；26.1补JPEG、帧／控制／结束队列及收尾上限，明确不是三端通用参数。

本次不声称全部源码重新逐行审计，也不把34项编号计为34个已完成临床验证的功能。

## 3. 已有证据；不是本次重新运行

| 已有文件／run | 核对范围 |
| --- | --- |
| [regression.json](../../reports/rehab_backend/regression.json)，verification-2e35a106 | 上轮372项新后端、12项原康复、19项原手机接口；工程回归，不是人体准确率 |
| [session_cold_verification.json](../../reports/rehab_backend/session_cold_verification.json)，d7229cf9 | 8项子集及3轮原模型冷启动短时ASGI；finish接收14.72／17.08／15.29ms，最终事实约2.05秒，非推理提速 |
| [session_load_verification.json](../../reports/rehab_backend/session_load_verification.json)，58572d12 | 7项子集及3轮持续输入；结束接收48.21／44.40／46.60ms；等待最终canonical后查唯一事实、贡献和逐帧状态 |
| [异步结束验收](REHAB_ASYNC_FINISH_2026-10-11.md) | 上述运行、失败、hash、来源及保护边界 |

以上8项和7项均已包含于372项，不累加。白色JPEG无人物；没有独立专业参考、目标手机、socket网络或长时完整故障结论。

本次只读核对时三个汇总的SHA256分别为：

```text
regression.json: 9d8a75766774bf1fdf4c954850b3220b31040d39e05bd9162c78928941df4f92
session_cold_verification.json: e1a1512e89bc15ff7bd5f9b59c78025d8f94cb170e8e3d919a4797617a5e1b0d
session_load_verification.json: 98d93027c81a305481d40a7355434316045ffae59c6568b8d348b7280a66c1d2
```

## 4. 文档检查与文件保护

交付前检查四份文档的本地链接、表格列数、代码围栏、F01–F34连续性和Git空白。对照开工时280份用户文件的Git状态及SHA256；原1308保护条目只读核对，不重建基准，不把用户图片／CSV／任务书／导入脚本暂存。

实际检查通过：四份文档440个本地链接存在、41张表格列数一致、代码围栏配对；F01–F34连续且无重复，Git空白检查通过。24项既有日志／summary／details的SHA256与报告一致，10项当前源码指纹与冷热核验器的记录一致；这些是只读检查，不是再次运行实验。

原1308保护条目变化0；保护文件SHA256保持`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`。280份用户文件的路径、Git状态及SHA256变化0，暂存区原为空，本次新增／修改清单仅四份文档。原解释器只读导入确认PySide6 6.11.2及pythonw.exe存在，用于沿用桌面入口；没有启动应用窗口。

文档检查只证明链接／结构和本轮改动范围，不替代业务、真人或设备验收。

## 5. 交付约定

仅四份本轮文档提交推送origin/main，核对远端与本地提交一致。之后用原快捷方式脚本和本机已验证pythonw.exe更新桌面入口描述，保留原E盘符号链接及未保存窗口。

产品0.20.0、APK0.2.1、默认关闭v2和五页导航不变；没有新APK、新模型或正式v2页面上线。
