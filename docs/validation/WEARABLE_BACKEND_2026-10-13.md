# 穿戴后台一期验证记录

2026-10-13；基线707336a；codex/wearable-health-integration。无UI/Qt/安卓前端/视觉算法/剂量规则修改，只新增mobile_rehab/wearables、独立API挂载和后台文档。模型和真实用户记录不改。

## 最终本机结果

Python3.13 / 原项目.venv，cryptography50.0.2、tzdata2026.5、cffi2.1.1、pycparser3.11。pip check无冲突。可选依赖不进入安卓包，不自动开通厂商服务。

```powershell
& .\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe -m pytest mobile_rehab/tests -q --basetemp D:/RehabFrontendFlowVerification/wearable-full-final-03 --tb=short --junitxml D:/RehabFrontendFlowVerification/wearable-full-final-03.xml
```

最终253通过，其中新增69、原184。1条原Starlette TestClient/httpx弃用警告；没有为消除警告更改原HTTP依赖。新增69项单独复测为全集子集，不重复累计。所有数据库、夹具、测试XML只在私有独立测试目录，不入Git，不作设备实测。

原Apple回归在ankang/route1-health-agent运行node scripts/test-healthkit.mjs：原桥接场景（revision/diagnostics/freshness/token/user隔离/过滤去重）通过，10项adapter测试通过。此前原健康39项子集通过，不另加到253。compileall新增模块、git diff --check通过。

CLI doctor最终隔离目录D:/RehabFrontendFlowVerification/wearable-doctor-final-02：SQLite schema1/quick_check=ok；两provider均PROVIDER_NOT_CONFIGURED，rehab_can_continue=true，native_readers_connected=false，team_proxy_binding=false，token key未配置。backup命令在该隔离库创建wearable-doctor-final-02-backup.sqlite3一致副本，未对用户库操作。没有为测试配置真实凭据或开服务。

## 保留的失败过程

| 运行 | 实际结果及原因 | 后续 |
| --- | --- | --- |
| wearable01 | 27通过/20失败，Windows缺IANA时区库为主 | 安装tzdata，明确依赖与时区合同 |
| wearable02 | 38通过/9失败，records写入16占位符/15字段 | 修正15列事务写入 |
| wearable03/04/05 | 47通过；54例运行52通过/2失败（测试夹具缺timedelta导入）；修复后54通过 | 保留首次INTERNAL_SYNC_ERROR，不称初次已通过 |
| wearable07 | 60通过/1失败，撤权故障先被无许可类别profile查询截获 | 无许可类型先独立跳过；末轮页前后scope核对通过 |
| full01 | 245通过，旧可选依赖版本 | 后续新增8例并升级经核对的官方依赖 |
| final08 / full-final-02 | 新专项69通过、全集253通过 | 又补0值/旧日期断言，refresh租约覆盖华为两请求，最终以full-final-03为准 |

上述试次不累计为额外验收数量。未实际开启相机、原生手表SDK、厂商授权、麦克风或付费AI请求；未重启用户服务/关闭旧窗口；没有新的APK发布。

## 保护与发布范围

开工279份未跟踪文件逐项SHA、动作指南README用户修改SHA及86份原UI文件冻结；提交前重新比对。APK0.3.2原包28166056字节、SHA256 C92610BEDB54DBF161ED41E0F6BE9E1B7DE7E9CFDCDB866F1FC3D907745E4BDF保留。只提交本轮后台/测试/文档，不带素材、个人数据库、日志、模型、凭据。提交后沿New-RehabDesktopShortcut.ps1更新原桌面入口Git描述，并核对origin分支与本地SHA；不更新main或其他云分支。

W01—W44逐项的TEST/REAL/部分/未做原因见[acceptance_report](../wearables/acceptance_report.md)。原测试通过不能代替真实兼容、临床性能或整份任务书验收。
