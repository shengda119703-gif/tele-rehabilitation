# 当前交接：安康居家康复助手

更新日期：2026-10-13。工作台基于 main `e2e256e`，选择性复用 `codex/unified-cloud-service` 的账号、授权、数据库与医生网页，新增患者记录同步、医患文字聊天及医生计划发布／患者采用。公网服务未部署，生产数据库未修改。

## 2026-10-13 本地融合更新

已拉取并融合 origin/main `c34bca6` 与本地 `5bcc2de`，保留正式跟练、后补感受、自动健身轨迹、穿戴后台及手机计步/GPS/BLE心率。融合版本电脑0.24.1、APK0.4.1/code41，原签名实际打包。主分支取消报告OCR和旧Agent代操作，本轮按新主线保留报告原件与手动指标录入，不恢复退役能力。未部署公网服务、未操作原患者库、未关闭旧窗口。

本轮共享TS481、产品24、手机／网页CJS135、手机Python258、电脑专项270＋4子测试、云端59／PG4跳过、包装8和Java42断言通过；实际原环境启动、Qt工作台图与公共网页构建成功。两次测试加载器／时间夹具失败及告警均见[本轮融合验收](validation/MAIN_WEARABLE_MERGE_2026-10-13.md)。新包`android_offline/dist/tele-rehabilitation-mobile-0.4.1.apk`，21,652,734字节，SHA256 `482A9509290F9E0914D81A04CD0243DAB909BA82BA1EFF81A53AF98C31961D50`；旧0.3.4包和279份用户素材SHA不变，指南README修改不提交。未Redmi／手环／GPS／真实相机或生产云验收。

合并前本地增量及所有原失败记录已保留在[本地交接快照](history/HANDOFF_LOCAL_INCREMENTS_2026-10-13.md)，专项索引见[本地历史文档索引](history/LOCAL_DOCUMENT_INDEX_2026-10-13.md)。当前分支仍为 codex/wearable-health-integration，不覆盖远端main。

## 当前版本与入口

| 项目 | main 当前情况 |
| --- | --- |
| 电脑 | 0.24.1；桌面“安康康复（最新版本）” → `Start-Rehab.ps1` → `app.main` → `ProductWindow`；右上“工作台” |
| 独立 Android | 0.4.1／versionCode 41；由 `android_offline/` 构建，保留本地跟练、自动轨迹、手机运动与心率 |
| 现有医生平台源码 | 云服务0.2.0／schema2；原 `/care` 扩展为工作台，公网仍需另行授权更新 |
| 电脑配对网页 | 电脑“我的档案 → 连接我的手机”；同一可信局域网，电脑保持开启 |
| 页面 | 首页、康复、健康、用药、家庭；`/capture` 保留录像、动作、分析和报告入口 |
| 康复 v2 | 源码存在，默认关闭；不能当作正式页面或 APK 已接通 |

版本取自源码，不代表本机已经生成或安装对应 APK。独立 APK 与电脑配对网页使用不同数据宿主，档案不会自动互通。目录 `rehab_codex_single_camera_v2_1/` 仍是正式桌面程序，保留其名称以兼容环境和数据路径。

## 报告资料与手动指标

报告图片和其他资料继续上传、查看／下载原件及回收站恢复；报告识字与图片指标自动提取已取消。请核对原件后从“手动记录指标”填写，来源标为本人录入。训练动作识别保留，旧报告及photo来源的历史记录不删除。详见[退役实现与验证](validation/REPORT_MANUAL_ENTRY_2026-10-13.md)和[退役归档](archive/report-ocr-20261013/README.md)。本次工作台的 APK 构建与实际验收范围见下方验收记录。

## main 已有能力与边界

- 正式康复助手仅问答、解说和本地候选计划；对话不录入健康事件或执行模块操作。已接入完整185张卡（63评估、122训练）；本地候选清单先映射5个起始版本，保留原文条件和剂量，待核对后才决定采用。其余训练卡可问答查询。见[共用动作资料](rehab-library/README.md)和[本次验证](validation/FULL_REHAB_LIBRARY_2026-10-13.md)。
- 已配置DeepSeek时，动作卡问答可请求模型解释；缺资料或隐私回合走本地回复。原手动页面保留，已有数据不删除。
- 手机录像与电脑实时测量保留不同来源条件，不能直接互换为有效训练依据。
- 配对网页共用电脑 ProductBackend；独立手机服务和独立 APK 使用各自的数据空间。
- 工作台复用云账号，患者需确认本机本人归属、同步同意与医生授权。聊天不会修改训练计划，方案经本地核验与云端回执后启用；见[功能说明](workbench/README.md)及[本次实际验收](validation/WORKBENCH_2026-10-13.md)。
- 本地跟练、感受、自动轨迹、手机运动与标准BLE心率一并保留；无厂商权限时不能读小米手环历史／睡眠。会员、API费用、视频问诊、多医生分诊不在本轮范围；真实手机硬件、手环兼容性与全部动作准确度仍需专项验收。

## 正在开发的其他分支

当前 `codex/wearable-health-integration` 已包含原前端／跟练增量及main工作台，保留 `codex/unified-cloud-service` 的其他成果。工作台只选择性整合账号、授权、存储、网页与相关适配；没有整包合并旧云分支的 OCR／Agent。分支会继续变化，下一次整合前重新读取 SHA 与差异。

## 验收与后续

本次工作台验收见[隔离测试、界面截图与构建结果](validation/WORKBENCH_2026-10-13.md)。此前发布证据见[健康归属修复](validation/HEALTH_ATTRIBUTION_FIX_2026-10-12.md)、[DeepSeek 三端范围](development/ANKANG_DELIVERY_SCOPE.md)和[安卓验收](validation/ANDROID_DEEPSEEK_2026-10-11.md)。这些是当时记录；完整旧黑箱失败及环境限制保留在[原诊断](validation/COMPREHENSIVE_BLACKBOX_2026-10-12.md)，本次专项通过不表示旧问题全部解决。

当前后端阅读入口为[功能与技术实现梳理](后端功能与技术实现梳理.md)，细节见[扩展技术索引](BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md)。两份均保留自己的源码基准和历史实验数值，不能据此判断已安装端的版本。

此前清理范围、恢复方法和实际检查见[清理记录](validation/DOCS_LEGACY_CLEANUP_2026-10-13.md)。本次已选择性接入工作台所需云端成果；后续更新既有公网服务需要另行授权，先隔离验证备份、迁移与原运行账号权限。

## 历史与恢复

- [整理前完整交接](history/HANDOFF_SNAPSHOT_2026-10-13.md)：逐阶段记录、旧失败与旧入口原文均保留。
- [历史文档索引](history/DOCUMENT_INDEX_2026-10-13.md)：全部阶段说明与验收链接。
- [本轮退役文件索引](archive/android-legacy-ui-20261013/README.md)：旧 UI／测试的归档位置与恢复命令。

历史资料中的“没有独立 APK”“android_offline 从主线撤出”属于2026-10-06状态，已被后续恢复工作取代。当前资料统一从本页和[文档索引](README.md)进入。

下架功能统一归档见[恢复入口](archive/RETIRED_FEATURES.md)，远端分支archive/retired-features同时保留旧Agent与报告OCR。
