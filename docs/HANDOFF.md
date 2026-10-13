# 当前交接：安康居家康复助手

整理日期：2026-10-13；本轮基于 main `48e94e58ccf260bd560f6ed4c67731e58e347380`。此次只整理说明和退役源码，不合并前端或云端功能，不改变产品版本。

## 当前版本与入口

| 项目 | main 当前情况 |
| --- | --- |
| 电脑 | 0.23.1；`启动康复助手.cmd` → `Start-Rehab.ps1` → `app.main` → `ProductWindow` |
| 独立 Android | 0.3.1／versionCode 5；由 `android_offline/` 构建，档案和计算在手机本地 |
| 电脑配对网页 | 电脑“我的档案 → 连接我的手机”；同一可信局域网，电脑保持开启 |
| 页面 | 首页、康复、健康、用药、家庭；`/capture` 保留录像、动作、分析和报告入口 |
| 康复 v2 | 源码存在，默认关闭；不能当作正式页面或 APK 已接通 |

版本取自源码，不代表本机已经生成或安装对应 APK。独立 APK 与电脑配对网页使用不同数据宿主，档案不会自动互通。目录 `rehab_codex_single_camera_v2_1/` 仍是正式桌面程序，保留其名称以兼容环境和数据路径。

## 报告资料与手动指标

报告图片和其他资料继续上传、查看／下载原件及回收站恢复；报告识字与图片指标自动提取已取消。请核对原件后从“手动记录指标”填写，来源标为本人录入。训练动作识别保留，旧报告及photo来源的历史记录不删除。详见[本轮实现与验证](validation/REPORT_MANUAL_ENTRY_2026-10-13.md)和[退役归档](archive/report-ocr-20261013/README.md)。本轮交付源码，未生成或安装新版APK。

## main 已有能力与边界

- 正式康复助手仅问答、解说和本地候选计划；对话不录入健康事件或执行模块操作。动作库为部分版本，训练卡待补齐，当前不会凭评估卡编造训练计划。见[共用动作资料](rehab-library/README.md)。
- 已配置DeepSeek时，动作卡问答可请求模型解释；缺资料或隐私回合走本地回复。原手动页面保留，已有数据不删除。
- 手机录像与电脑实时测量保留不同来源条件，不能直接互换为有效训练依据。
- 配对网页共用电脑 ProductBackend；独立手机服务和独立 APK 使用各自的数据空间。
- main 尚未合入新云账号和前端分支全部流程；全模块任意写入、持续任务、真实手机硬件与全部动作准确度等仍需各专项验收。

## 正在开发的其他分支

`codex/frontend-flow-optimization` 已包含上述 main 基准，另有前端／跟练增量；`codex/unified-cloud-service` 有云账号等增量。两者已分叉，均保留。分支会继续变化，整合前重新读取 SHA 与差异；不能根据名字、版本号或旧报告整包覆盖 main。

## 验收与后续

最近 main 发布证据见[健康归属修复](validation/HEALTH_ATTRIBUTION_FIX_2026-10-12.md)、[DeepSeek 三端范围](development/ANKANG_DELIVERY_SCOPE.md)和[安卓验收](validation/ANDROID_DEEPSEEK_2026-10-11.md)。这些是当时记录，本次没有重跑产品验收；完整黑箱失败及环境限制保留在[原诊断](validation/COMPREHENSIVE_BLACKBOX_2026-10-12.md)。

当前后端阅读入口为[功能与技术实现梳理](后端功能与技术实现梳理.md)，细节见[扩展技术索引](BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md)。两份均保留自己的源码基准和历史实验数值，不能据此判断已安装端的版本。

本轮清理范围、恢复方法和实际检查见[清理记录](validation/DOCS_LEGACY_CLEANUP_2026-10-13.md)。后续先整合前端／云端有效成果并做跨端回归，再讨论旧兼容服务和跨语言规则退役。

## 历史与恢复

- [整理前完整交接](history/HANDOFF_SNAPSHOT_2026-10-13.md)：逐阶段记录、旧失败与旧入口原文均保留。
- [历史文档索引](history/DOCUMENT_INDEX_2026-10-13.md)：全部阶段说明与验收链接。
- [本轮退役文件索引](archive/android-legacy-ui-20261013/README.md)：旧 UI／测试的归档位置与恢复命令。

历史资料中的“没有独立 APK”“android_offline 从主线撤出”属于2026-10-06状态，已被后续恢复工作取代。当前资料统一从本页和[文档索引](README.md)进入。

下架功能统一归档见[恢复入口](archive/RETIRED_FEATURES.md)，远端分支archive/retired-features同时保留旧Agent与报告OCR。
