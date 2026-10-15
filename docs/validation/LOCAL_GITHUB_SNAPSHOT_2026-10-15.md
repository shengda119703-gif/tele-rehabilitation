# 2026-10-15 本地源码与 APK 归档

## 本轮范围

用户要求将本地 APK、动作库及相关更新提交 GitHub。本轮只归档与上传，不重新部署服务器、不重打 APK，不触发模型付费调用，不生成患者测量、用药或训练记录。

从 `origin/main` 的 `8f1fc2c` 及其家庭账号增量 `5449f9e` 派生独立分支 `codex/assistant-online-assessment`。不推送本机累计的原图历史，不覆盖伙伴的 `main`。本地运行仓库仍为 `E:/game/health-care-software-main`；发布工作树仅用于筛选和提交。

## 源码与已构建安装包分开管理

| 内容 | 状态 |
|---|---|
| Android APK | 现有原签名 0.5.9，versionCode 59；本轮不重建 |
| 桌面源码 | 0.25.7 |
| 云端源码版本字段 | 0.3.10 |
| 完整动作图文库 | 185 项：63 评估、122 训练；656 张选定 WebP 与索引 |
| 最新未验收增量 | `rehab-dialogue-4`、`online-assessment-routing-2`、顺序任务与视频入档辅助代码，按开发快照保存 |

动作图文不等于新增 185 项自动测量。保留已有测量算法、按用户隔离、授权及安全分流，不用聊天生成测量数值。

APK 0.5.9 是此前构建的发行包，不包含这次源码快照中的全部后续开发内容；版本字段相同不能证明二者源码完全一致。最新顺序评估、视频入档闭环尚未完成全链路验收，不应直接部署本分支到生产或声称该 APK 已包含完整闭环。

## 下载文件

- 文件名：`tele-rehabilitation-mobile-0.5.9.apk`
- 大小：54,911,962 字节。
- SHA256：`4FF7D2949AE5A820D1DE573680D9623851D3840B38DB0955E1ED1F175EAA02FE`。
- 包名：`cn.tele.rehabilitation.offline`。
- 签名证书 SHA256：`607edd7dc1df261e52fa2fe35ea6391e1ce77cbcebc315fea80dd815bac1a5d8`。
- 预发布归档页：<https://github.com/shengda119703-gif/tele-rehabilitation/releases/tag/local-snapshot-20261015-apk0.5.9>。实际上传及远端核对结果以本轮交付为准。

APK 作为 Release 附件保存，不加入 Git 对象；继续保留 APK、build、dist、私有签名和权重的忽略规则。原文件仍在本机 `android_offline/dist/`。

## 上传与排除

提交相关 Android、手机网页、云服务、桌面客户端、打包工具和测试源码，并保留必要说明。动作库提交程序直接使用的压缩 WebP、`catalogue.json` 和已有入口抠图，不提交本机原始大图、候选生成批次或用户导入目录。

不上传 `.runtime/`、虚拟环境、node_modules、模型权重、账号数据库、原始录像、私钥、服务器环境配置、对话正文回执和运行日志。未改写用户导入文件；用户的 exercise-guides README、导入报告、实施任务书和导入脚本不在此次提交范围。保留远端已有文件，不通过本地旧快照删除伙伴新增文件。

## 本轮验证

本轮在筛选后的独立工作树实际执行：

- 121 个 Python 文件 AST 语法检查、89 个 JavaScript 文件 `node --check` 通过。
- 185 项动作索引与656个 WebP 文件逐项 SHA256 一致；资源构建和介绍加载测试2项通过。
- 账号、家庭关系、原生登录契约、评估计划、动作库与网页传输的客户端检查106项通过。
- 云端回复和评估安排测试为 **58通过、2失败**。失败分别是旧测试仍预期单项评估而当前候选包含多个动作，以及旧结果关联方式不能使新顺序任务完成；位置为 `test_assistant_assessments.py` 中 `test_one_followup_schedules_online_assessment_and_no_training_or_measurements` 和 `test_only_real_subsequent_matching_completed_assessments_finish_appointment`。本轮按 Git 归档范围保留开发现场，不修改逻辑或把失败改写为通过。该快照不能作为生产验收版本。
- APK 文件 SHA256 与原发行记录一致，`apksigner verify --print-certs` 通过，原签名不变。
- 已筛选文件未检出私钥或常见云/GitHub/模型密钥形态；没有将账号库、运行目录、签名文件及原视频加入提交。
- 原280份用户导入/修改文件逐项SHA256一致。第一次清单复核把大小写不同的十六进制串直接比较，误报差异；更正为不区分大小写后280/280一致，没有恢复、覆盖或删除任何用户文件。

云测试还遇到旧系统临时目录清理警告；这不改变上述两项实际断言失败。本轮没有把以前版本的通过计数当作当前快照全量通过证明，未重验全部动作、真机性能或视频入档端到端闭环。

原始校验清单和完整测试输出留在本机忽略目录 `.runtime/git-publish-20261015/`，不向 GitHub 上传含环境路径或私密回执的日志。
