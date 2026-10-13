# 当前交接：安康居家康复助手

更新日期：2026-10-13。工作台基于 main `e2e256e`，选择性复用 `codex/unified-cloud-service` 的账号、授权、数据库与医生网页，新增患者记录同步、医患文字聊天及医生计划发布／患者采用。公网服务未部署，生产数据库未修改。

## 当前版本与入口

| 项目 | main 当前情况 |
| --- | --- |
| 电脑 | 0.24.0；`启动康复助手.cmd` → `Start-Rehab.ps1` → `app.main` → `ProductWindow`；右上“工作台” |
| 独立 Android | 0.4.0／versionCode 40；由 `android_offline/` 构建，档案和计算在手机本地 |
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
- 前端分支其他流程、会员、API费用、视频问诊、多医生分诊与可穿戴设备不在本轮扩展范围；真实手机硬件与全部动作准确度仍需专项验收。

## 正在开发的其他分支

`codex/frontend-flow-optimization` 的前端／跟练增量和 `codex/unified-cloud-service` 的其他成果继续保留。工作台只整合账号、授权、存储、网页与相关适配；没有整包合并旧云分支的 OCR／Agent。分支会继续变化，下一次整合前重新读取 SHA 与差异。

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
