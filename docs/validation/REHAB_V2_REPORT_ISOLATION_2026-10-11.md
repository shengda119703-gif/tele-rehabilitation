# 康复 v2 默认报告进程隔离与事实保护验收

日期：2026-10-11（Asia/Shanghai）。实施基准：main / `4c48195ba6d00db8e46cb1a4bf657062b597ffde`，本文件所在提交交付。任务依据为用户后端实施任务书第6–7节；不是客户端发布。产品0.20.0、APK0.2.1、协议rehab-protocol-2.0，v2默认关闭。

## 1. 实际改动

- `app/rehab_v2/reporting.py`提取原10字段纯报告，不增诊断、计划、剂量或模型。
- `mobile_rehab/rehab_v2/owned_worker.py`抽取准确所属spawn生命周期，姿态推理与报告复用同样的等待／取消／退出确认／清理重试；原推理契约、容量、预算与错误码保持。
- `report_worker.py`只接已冻结的白名单JSON快照。单槽、2 MiB输入＋2 MiB响应、≤4 KiB通知，默认握手10秒、工作等待5秒、terminate／kill各等1秒；不持相机、SQL或LLM。
- 宿主校验长度、SHA、ticket、sid、feedback_revision类型与值、输入hash、有限compute_ms和完整报告事实digest；只有原SQL反馈CAS有提交权威。子进程不能改次数／计划／来源／指纹获得写入资格。
- source记录创建当时的真实报告执行契约；显式本地report_builder callable声明trusted_local_callable与无硬取消，不作为HTTP请求参数。正常默认是owned_spawn。
- 并发重建忙时返回running，不排队或把pending覆盖为failed。报告超时／退出／重试只影响派生报告，最终视觉快照、回执与唯一贡献不变。
- 服务关闭先取消报告，待消费者和准确所属进程退出后才能释放SQLite与lease。退出未确认保留句柄／隔离状态，后续可重试关闭；本地callable真挂起也明确关闭失败，不提前关闭存储。
- report_ms保留宿主整次工作；新增report_compute_ms、report_roundtrip_ms和固定report_timeout／cancelled／busy事件。运行态可查报告SQL故障，不把“写不下失败”称已保存；报告RSS仅在本sid实际在途时测量，其他情况null。

没有DB迁移，没有改原用户UI、Android、旧模型、原Runtime、原GuidancePolicy、旧live删除语义或非康复业务。没有启动／重启用户服务或关闭旧窗口。

## 2. 本机实际验证

使用已验证产品解释器：`rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe`，本轮复核Python3.13.12、PySide6 6.11.2。原YOLO权重SHA256：`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`，未替换或升级。

```powershell
$env:PYTHONPATH='E:\game\health-care-software-main\tests\rehab_backend;E:\game\health-care-software-main'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -m unittest test_report_isolation -v
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 tools/rehab_ml/cli.py verify-sessions --database-mode isolated
```

18项报告专测单独运行通过（19.131秒），也包含在最终完整118项和会话88项中，不能相加。本轮较早的15项单测、115项完整回归是新增3项竞争／故障用例之前的中间结果，不作为最终数量。

最终完整run：`.runtime/rehab_ml/run/verification-7b04bb8c/`，全新隔离TEST数据库和pytest目录在E盘，未写正常档案。机器可读 [完整记录](../../reports/rehab_backend/regression.json)。

| 命令组／日志 | 实际结果 | unittest／pytest时间；含进程总耗时 | 日志SHA256 |
| --- | --- | --- | --- |
| new_backend.txt | 118项通过 | 81.502秒；82.536秒 | affdfed3ffcda6cc9b33235b1ccfe94fb521cf0cd957fc3636bebf9395bda2bd |
| legacy_rehab.txt | 12项通过 | 0.091秒；0.239秒 | e4c361c646011848213770236330c2956752ec3a66d21aeeca515c17e9ca1c8c |
| legacy_mobile.txt | 19项通过、1项既有弃用warning | 12.95秒；13.543秒 | eb46ece6fc4ad96acd9c35e17fe7f6f8a77d3d3d33509b28f8869c03faecad9b |
| scope.txt | 1308个保护文件一致 | 5.262秒 | e289207939419d5c9c28264a659d5af2a894ddb53c80e67c136e30cac97ff47c |

独立会话run：`.runtime/rehab_ml/run/replay-382d0cb8/sessions.txt`，88项通过，命令总耗时63.957秒；SHA256 `2add7a7ea1d4f9df7f0661bcd72a8a74db82fa4fda633d546b4ac2e83243cf61`，见 [会话记录](../../reports/rehab_backend/session_verification.json)。是118项的子集，不是额外88项。

保护基准没有重建，SHA256 `75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`。本轮额外核对用户原有280份素材／README／CSV／任务书／导入脚本，数量和SHA均未改变，全部排除提交。Android和正式UI保持只读，未重打APK。

交付前复核上述四份完整日志及会话日志SHA，全部匹配机器可读摘要；五份本轮文档的255个本地链接均可解析，`git diff --check`通过。没有把文档检查当作额外业务用例。

## 3. 18项专测对应的边界

| 验证组 | 真正运行了什么 | 不能声称什么 |
| --- | --- | --- |
| 默认构建／复用／清空 | 真spawn纯原报告，>4 KiB结果走共享内存；同进程换sid／反馈，成功后传输区为零、close后共享区不可重开 | 没有逐字节擦除存活解释器所有内部RAM |
| 容量／身份／事实 | 拒绝超大输入、响应长度／hash错误、ticket／sid／反馈／输入hash错、布尔revision、非法耗时与改次数；每次故障确认所属退出 | 不是不可信代码沙箱；target只允许可信本地构造 |
| 真挂起／退出／超时 | 子进程while循环及os._exit(31)，等待预算后确认退出；新报告能新建进程 | 不是注入OSError冒充OS退出，也不证明所有原生死锁环境 |
| 取消／释放重试 | 不同sid不误取消；本sid取消；stop后不接新任务；受控屏蔽terminate／kill后保留原句柄，恢复操作后可清理 | 未确认退出时不能说已释放或另起泄漏进程 |
| 事实／关闭／重启 | 一次已确认往返，超时／重建／关机／重开前后snapshot、canonical_commit、唯一贡献digest一致；close取消真挂起并释放存储 | 不代表真实患者准确率；往返为内部SYNTHETIC/TEST证据 |
| 反馈竞争／忙 | 真子进程延迟旧反馈报告；新反馈CAS使旧结果superseded；并发重建返回running、查询和回执不被挂起报告阻塞 | 没有重写视觉数据、没有把旧报告算成新执行量 |
| 写入与本地钩子 | report_work／report_state受控OSError，运行态故障可查、pending保留，移除故障后重试；本地callable挂起时lease保留 | 没有真实磁盘满／损坏；本地callable不能硬取消 |
| 权限／生命周期 | 错owner／未finalized拒绝且不启动报告；closed不新建；未确认报告释放时新宿主不能抢占该数据库 | 不是所有旧产品API或公网安全验收 |

上述工程测试实际覆盖失败边界，不把未知、缺测或未完成动作补为有效。

## 4. 未测及下一步

- OS Process.start自身无硬截止；宿主有界JSON序列化和纯内容核对没有单独硬截止。默认等待预算不是整条链的绝对时间保证。
- 真实磁盘满、损坏、断电／SQLite损坏后的恢复还未验证；已有照护库异常没有在本轮修复。
- 康复深蹲宿主计划未接通，v2正式UI／APK／管家未接入；本任务要求它们只读，不将后台能力写成用户已可使用。
- 没有重跑旧IRDS训练、真人回放或会话性能benchmark；原性能JSON仍为历史 `session-performance-a394a83e`。没有报告全负载p95或红米实机证据。
- 缺目标RGB训练授权、独立专业关键点／可见性／动作边界标签；P5/P6仍未完成，候选默认关闭，不能声称识别准确性已提高。

交付后只维护桌面“安康康复（最新版本）”的Git版本描述，仍指向Start-Rehab.ps1与本机实际验证的pythonw.exe；正式首页／康复／健康／用药／家庭入口和产品版本不变。完整后端任务继续，不能标记整体完成。
