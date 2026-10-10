# 后端字段与数据契约核对 · 2026-10-11

## 交付与范围

用户要求一份Markdown，逐项说明后端功能、技术方法和功能间的信息传递，用于思考准确性与可靠性优化。交付 [后端功能、算法与数据流梳理](../BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md)，同步 [HANDOFF](../HANDOFF.md) 和 [索引](../README.md)。本轮只提交这四份文档，不实施代码。

起始工作树为main的 `f181d04f9b82eb8e943fc01c9ea4dec6b1410f3d`；最近后端实现为 `06366bdac2bddbd0888d8fe1b67a7abab62f9067`，之后f181d04为文档更新。origin仍为 `https://github.com/shengda119703-gif/tele-rehabilitation`。电脑／托管产品0.20.0、现有APK0.2.1，v2默认关闭且未接正式页面／APK。

没有业务、UI、依赖、模型、APK、正常数据库、原服务或窗口改动；没有开相机、麦克风，也没有新启动测试、训练或性能任务。

## 源码核对与内容补充

完整读取当前主文档，核对以下实际实现；不声称逐行审核全仓库。

| 核对位置 | 补充或纠正内容 |
| --- | --- |
| domain.py | Context、帧时间与骨架契约；xy／conf／track_key／bbox属于people中的PosePerson |
| assessment.py | 最新同作用域评估、items字段、原session引用、状态与范围来源 |
| automatic_plans.py／training_plans.py | proposal、automatic扩展、items.key、执行reference、进度及反馈条件 |
| rehab.py／training.py | 三样本中位角度证据；评估／训练valid_ratio分母、组次完成字段 |
| fitness.py／fitness_analyzer.py | 时间覆盖与逐指标帧覆盖分开；健身result与可选barbell输出 |
| posture.py／barbell.py | 全部样本coverage与最长片段统计不同；跟踪比例、完整上升段与求导输出不同 |
| APK engine.js／motion.js | 本地时间有效率、无跨度0值、原始极值、录像结果目标完成口径；只读未改 |
| events.ts／types.ts | HealthEvent的内容嵌套、主诉status、visibility所在层级、Finding证据类型 |
| ProductBackend／AgentBridge | 串行请求、草稿转写与通用voice.input区别、私有回执与超时边界 |
| CareCoordinator.ts | 原事实expected、scope、期限、提议状态、确认与逐步回执 |
| v2 sessions.py／rounds.py／reporting.py／service.py／api.py | snapshot、最终commit、feedback版本、派生报告及工作区故障适配的区别 |

保留主文档第1–23节全部主要功能。新增3.7的15项字段交接和3.8的7项统计口径／5项完成判断，便于将输入、算法、输出和下游逐项对上。新增内容是源码说明，不是统一schema、已上线新算法或临床参考成绩。

## 已启动检查：本轮收取，未重新启动

接回此前运行中的 `verify-sessions --database-mode isolated`，exec session 51404，实际exit0。日志 `replay-2167d5a9/sessions.txt` 末尾为100项／82.646秒、OK；命令耗时83.2715696秒。重算日志SHA256：

`e97c209a9307264c90005e2dbe4c28faeb701297fce4e865b7f17adaa40495e4`

该100项是此前工作区130项完整回归中的子集，包含未提交原生存储测试；不能当作已发布f181d04的实现验收或本轮新启动回归。起始已有session_verification.json继续保留、不纳入文档提交。原操作此前遗漏database-mode参数导致的argparse失败，不计为业务失败；本轮没有重新执行该失败命令或修业务。

SQLite容量上限测试不是物理硬盘满，损坏TEST头不是B-tree修复，恢复到新TEST路径不是正常患者库自动恢复。手机实机、临床测量、真实I/O、全负载和新模型准确度均未新增验证。

## 本轮实际文档与保留检查

- 起始记录288份dirty文件SHA256，280份用户素材／说明／任务书／CSV／导入脚本，加8份此前后端存储增量／测试／生成报告。只提交四份文档，其他文件保留。
- 只读重算保护清单1308文件：changes为空，基准SHA256为 `75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`；不改写scope报告。
- 使用产品环境 `python.exe -X utf8 -B -c` 只读导入，确认Python3.13.12、PySide6 6.11.2；没有创建应用或开启输入。
- 四份文档实际检查：301个本地链接存在、9个显式锚点存在、50个表格块列数一致、代码围栏闭合，Git空白通过。再次比对288份起始文件，SHA256全部不变；新增改动仅四份文档，提交前核对暂存区范围。

本轮初次查找误用不存在的tools/rehab_ml/scope.py，随后从inventory.py和实施报告定位到真实保护manifest；属于只读定位错误，不算业务测试失败。

提交后按项目约定推送origin/main并核对远端SHA，使用New-RehabDesktopShortcut.ps1刷新桌面“安康康复（最新版本）”Git描述。仍指向Start-Rehab.ps1及本机已确认的pythonw.exe；正式首页／康复／健康／用药／家庭不变，不关闭旧窗口。后端实施总任务仍进行中，本轮不扩大为代码实施。
