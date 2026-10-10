# 后端文档与算法优化依赖核对 · 2026-10-11

## 本轮交付

用户要求一份Markdown，逐项说明后端功能、技术实现、功能间信息传递，用于讨论准确性和可靠性优化。交付文件为 [后端功能、算法与数据流梳理](../BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md)，同步 [HANDOFF](../HANDOFF.md) 与 [文档索引](../README.md)。本轮只提交上述三份文档和本记录。

已提交源码基准：`06366bdac2bddbd0888d8fe1b67a7abab62f9067`，main，origin为 `https://github.com/shengda119703-gif/tele-rehabilitation`。电脑／托管网页0.20.0，APK0.2.1；康复v2默认关闭，未接正式五页和APK。本轮无算法实施、UI修改、依赖升级、模型训练、安装包构建、原服务重启、相机／麦克风操作或正常数据库写入。

## 内容与实际源码核对

完整读取既有主文档和当前交接；结合提交状态、现存报告和以下源码核对：

- ProductService实际dispatch、档案／权限、health.record、chat、voice.input、image.parse／confirm、家庭、资料、通知和生命周期边界。
- ProductBackend的串行队列、私有回执、超时和`ui.voice.transcribe`只返回草稿路径；手机转写worker及APK语音填草稿适配。
- PoseAnalyzer的焦点、必要点、因果EMA、跳变及画面竖直肩角；评估作用域、自动计划剂量／休息、原管家只读入口。
- v2 service／API、报告纯构建函数、工作区storage_boundary及原生故障测试。未宣称本轮逐行审核或实际验收了整个仓库。

保留原文第1–21节的三端功能、几何／EMA／状态机／时间／求导／力学／健康基线／研究训练公式和逐跳数据交接；更新已提交报告版本，单列未提交存储增量。新增第22节：21个后端改动点的输出、下游、必要联测和章节入口；第23节：候选滤波、稳健基线、求导误差传播、共享语义结构及代码／数据／硬件的不同验收要求。候选公式不是已上线算法或已测成绩。

外部依据只使用作者或官方页面：

- [One Euro作者说明](https://gery.casiez.net/1euro/)：速度自适应低通与调参意义；作者论文跳转返回403，GitHub实现跳转取回失败，未声称成功读取这两份材料或复制实现。
- [SciPy MAD说明](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.median_abs_deviation.html)：中位绝对偏差及正态尺度换算，不套作医学阈值。
- [SQLite结果码](https://www.sqlite.org/rescode.html)：锁、只读、容量、I/O和损坏区别。
- 复核 [Ultralytics姿态说明](https://docs.ultralytics.com/tasks/pose/) 与 [MediaPipe姿态说明](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)，不因此升级本地依赖／权重。

## 现存工程结果：本轮读取，不是新跑

接回此前已启动的`verify_all.py`进程结果，run为`verification-1d000563`。工作区新后端130项、旧康复12项、旧手机19项通过，1308保护文件一致；130项含12项未提交原生存储测试，不能写成06366bd已发布验收。没有本轮新CLI子集、训练、性能、私人录像、全产品／Agent／Android或临床验证。

| 原命令域 | 现存结果 | 本轮重算并匹配的日志SHA256 |
| --- | --- | --- |
| new_backend | 130项，79.393秒；命令80.468秒，exit0 | `c19d6c9883c6d3d30d61611c316f963fe7892606adea8aac0e9382bd73c850d1` |
| legacy_rehab | 12项，0.095秒；exit0 | `e8a0c1d8219e5bc513e11ea1e4b50cbd9be043a753db0e058e010f976c7cf62e` |
| legacy_mobile | 19项，12.87秒；exit0、1条既有弃用warning | `808379affbd78fc54899d5791aab112877280e225075056d2a90f1adff253e32` |
| scope | 1308项保护文件一致；exit0 | `7e77cc8e762b73a6f9343321acd5c2f2ebfbea1202d4460b9e80e10b03b4b6e8` |

工作区FULL由SQLite容量上限触发，未填满真实硬盘；只读连接／query_only不代表全部Windows ACL；损坏TEST头不是结构修复，已知备份只恢复到新TEST路径。物理ENOSPC、断电／介质故障、旧Care库损坏根因、手机负载和真人精度仍未知。工程数量不得转成准确率或和历史累加。

## 本轮实际只读检查与保留

1. 记录287份既有dirty文件SHA256：280份用户素材／说明／任务书／CSV／导入脚本，加7份既有后端增量／测试／生成报告。本轮全部保留、不捎带提交。
2. 只读导入确认Python3.13.12、PySide6 6.11.2；未启动应用。
3. 直接重算保护manifest的1308文件SHA，changes为空；基准文件SHA为 `75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`。本轮检查不调用会改写report时间戳的CLI，不改现存regression／scope报告。
4. 重算上述四份日志SHA均匹配，原实验和历史验收记录不改。
5. 实际检查四份本轮文档：279个本地链接存在、8个显式锚点跳转存在、47个连续表格块列数一致、代码围栏闭合、Git空白通过。287份既有dirty文件SHA256与本轮开始时一致；新增改动仅四份文档，提交前检查范围限定它们。

一次只读manifest结构查询误用不存在的files属性，另一次误将整个protected对象当单个条目导致输出截断；随后按`protected.PSObject.Properties`逐文件正确核对，不修改manifest、测试预期或文件内容。它们是查询错误，不计为业务测试失败。

交付遵循仓库约定提交并推送main，再核对远端SHA；失败时如实报告，不把本地提交称为上传。提交后用原脚本刷新桌面“安康康复（最新版本）”版本描述，继续指向Start-Rehab.ps1和已确认的`.venv/Scripts/pythonw.exe`。首页／康复／健康／用药／家庭导航不变，旧窗口不关闭。
