# Final Integration：合并前成果审计（2026-10-02）

仓库以实际 origin 为准：shengda119703-gif/tele-rehabilitation。审计完成时尚未 merge。

- 原远端 main：`2ebc388d4160d647456487007670d89f02f80914`；本地原无 main 分支。
- stage1 本地/远端 HEAD 均为 `55a0476a4e7bc10187a809e491048f74fd58839b`。
- `origin/main...stage1`：main 独有 0，stage1 独有 28 个提交；main 是 stage1 祖先，无需处理双边冲突。
- 开始时工作区 clean，普通 untracked=0，stage1 未推送提交=0。后面新生成的本审计文件是本轮交付，不是遗漏成果。
- 按 Git blob 比较：main 292 个 tracked 文件；stage1 744 个；285 个完全一致，452 个新增，7 个修改，0 个删除。逐文件完整表见 [CSV](FINAL_INTEGRATION_FILE_AUDIT_2026-10-02.csv)。不以 commit 数量替代内容比较。

## 到底在哪里（合并前）

P=rehab_codex_single_camera_v2_1/app；T=ankang/route1-health-agent/src。

| 模块/文件 | main已有 | stage1分支已有 | 仅本地 | 是否最终保留 | 是否需要进入main | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| participant：P/participants.py、ui/participants.py | 是 | 是 | 否 | 是 | 已有 | blob一致，用户隔离逻辑保留 |
| 评估/Body Profile：P/assessment.py、assessment_batches.py、ui/body_overview.py | 是 | 是 | 否 | 是 | 已有 | 原评估和身体汇总未覆盖 |
| 动作/几何/分期/监督：P/exercises.py、geometry.py、rehab.py、training.py | 是 | 是 | 否 | 是 | 已有 | 原53项任务、缺测与非诊断边界保留 |
| 相机：P/camera_manager.py、source_worker.py、dual_camera.py、vision.py | 是 | 是 | 否 | 是 | 已有 | 原CameraManager独占输入；未复制采集实现 |
| 计划/自动计划：P/training_plans.py、automatic_plans.py、ui/training_hub.py | 是 | 是 | 否 | 是 | 已有 | 原计划版本、来源、顺序门禁一致 |
| progress/feedback：P/training.py、ui/training.py、automatic_plans.py | 是 | 是 | 否 | 是 | 已有 | 原进度/训练后反馈保持兼容 |
| history/report：P/longitudinal.py、reports.py、ui/longitudinal.py | 是 | 是 | 否 | 是 | 已有 | 原条件可比历史和报告保留 |
| silver/family support：P/silver_service.py、silver_store.py、family_demo.py | 是 | 是 | 否 | 是 | 已有 | 与Ankang家庭服务分清原支持记录范围 |
| runtime/command bus/storage：P/runtime.py、storage.py、scene_controller.py | 是 | 是 | 否 | 是 | 已有 | 原线程/队列命令和SQLite兼容性不变 |
| Agent Runtime/multi-turn/understanding：T/runtime、engine/understanding.ts、elderTurn.ts | 否 | 是 | 否 | 是 | 是 | 原Ankang实现；不恢复Python A1/A2/A3 |
| self-report/HealthEvent/detection/Person Twin：T/pipeline、engine/detection、personTwin | 否 | 是 | 否 | 是 | 是 | 进入正式产品服务，原算法复用 |
| correction/privacy/consent/sharing/Care Tasks：T/engine、family、runtime/careTasks.ts | 否 | 是 | 否 | 是 | 是 | 授权/事实/一次性许可与任务链路 |
| medication/今日用药/漏服：T/medication、engine/medicationCare.ts | 否 | 是 | 否 | 是 | 是 | 本机药物和原任务规则 |
| family contacts/SOS/binding/facts：T/family、ProductService | 否 | 是 | 否 | 是 | 是 | SOS是联系信息，非自动拨号或救援送达 |
| archive/attachments/history/timeline/reports/trends/lifecycle | 否 | 是 | 否 | 是 | 是 | T/archive、product、原本机storage port |
| notification/external channels：T/notification、adapters/WebhookPushChannel.ts | 否 | 是 | 否 | 是 | 是 | 唯一NotificationService业务规则 |
| Voice/ASR/TTS：T/product/ExtensionPorts.ts、adapters/BrowserVoiceAdapter.ts | 否 | 是 | 否 | 是 | 是 | 接口/原浏览器实现；Windows原生接线与实机验收未完成 |
| cross-device sync：T/sync、adapters/PeerJSCrossDevice.ts | 否 | 是 | 否 | 是 | 是 | 保留原协议/绑定；外部宿主/双端实机未验收 |
| HealthKit：T/adapters/HealthKitDeviceAdapter.ts、native-ios、healthkit-bridge | 否 | 是 | 否 | 是 | 是 | 正式外部健康源；不在Windows模拟iOS |
| generic device/special hardware：T/adapters/DeviceAdapter.ts、MeasurementInputAdapter.ts | 否 | 是 | 否 | 是 | 是 | 接口已迁；上游没有独立雷达/BLE/串口driver |
| image/video/multimodal/capture：T/adapters、P/product/capture.py | 部分：原康复相机/回放 | 是 | 否 | 是 | 是 | 复用图片解析和附件、通用capture；不启动空间推理 |
| Python/Node bridge/rehab-model：bridges/ankang、scripts/agent-bridge.cjs、rehab-model.cjs | 否 | 是 | 否 | 是 | 是 | Python→原TS Runtime；固定DeepSeek模型adapter |
| rehab read tools：P/rehab_read_tools.py、T/runtime/rehabTools.ts | 否 | 是 | 否 | 是 | 是 | 当前仅只读，不让Agent直接写训练 |
| ProductService/PySide6 assistant：T/product、P/product、P/ui/ankang_assistant.py | 否 | 是 | 否 | 是 | 是 | 原业务复用，无第二套Python Agent |
| 正式产品：首页/管家/康复/健康/用药/家庭/历史、通知/设置 | 原康复UI | 是 | 否 | 是 | 是 | P/ui/product_window.py为正式入口，app/main.py明确加载 |
| icon/assets/theme：assets/ui/ankang、P/ui/product_theme.py | 原康复素材/主题 | 是 | 否 | 是 | 是 | 新9个SVG与产品主题；本轮不改视觉 |
| plans/validation/migration/architecture/productization文档 | 原康复文档 | 是 | 否 | 是 | 是 | plans+validation：main 36份，stage1 52份；历史记录完整保留 |
| 原React/demo/Route2/3DGS/空间风险与查物 | 否 | 是 | 否 | reference源码 | 是，仅作为源码参考 | 不作为正式入口；空间主流程继续延后，不阻塞合并 |
| 废弃A1/A2/A3 Python Agent | 否 | 已删除出当前tree | 历史commit中 | 否 | 否 | 28个提交中保留试验和清理历史，不恢复废弃代码 |
| ignored：依赖/build/cache/截图/upstream zip | 否 | 否 | 是 | 保留本地 | 否 | 无未入Git的独立产品源代码 |

## 三种危险情况

1. stage1独有有效成果：上表Ankang业务/Runtime、bridge/tools/model adapter、ProductService/PySide6骨架、扩展端口、9个SVG及16份新增plans/validation，全部已commit+push。逐文件新增/修改列见CSV。
2. 未commit/未push：审计起点没有；ignored目录没有发现遗漏的独立业务源码。未删除任何本地文件。
3. main独有更新：0；main完整树是stage1祖先。原康复核心285个文件blob不变。7个既有文件变化是 Setup-Rehab.ps1、Start-Rehab.ps1、docs/HANDOFF.md、docs/history/CHANGELOG.md、app/main.py、ui/main_window.py、ui/workspace.py，用于正式产品启动/嵌入/交接；无删除。

## ignored与secret排除

ignored清单包括：node_modules、.bridge-build/.test-build/dist、tsbuildinfo、Python/pytest缓存、7张测试截图，以及backups/incoming/ankang-cbdc8f3.zip。普通扫描3564个ignored文件；受沙箱限制的pytest缓存另行只读核查为README、CACHEDIR.TAG、.gitignore、nodeids、lastfailed，均非产品成果。没有复制或删除它们。

upstream zip SHA256=f44ee67fe70d7ebc6d5a6e4964aab87783ab030a76deed326f7d94ff42329dc4，与UPSTREAM.md记录一致，源码已经tracked，不需再入Git。当前工作区无用户SQLite/.env/deepseek.json，开发Key配置设计位于工作区外APPDATA；只核对源码/路径，不打印凭据。

当前tracked树排查：未发现.env、deepseek.json、SQLite运行库、依赖目录、runtime临时文件和build outputs。仅.env.example/.env.hardware.example为tracked占位示例。29个待合并提交快照（28个stage1提交+main快照）及当前文本文件的常见API Key/私钥特征扫描无命中；模式检查不等于通用秘密检测证明。

## 集成决定

采用可追溯的no-ff Git merge，完整保留阶段提交和清理历史；不复制覆盖main、不cherry-pick遗漏有效成果。先提交本审计到stage1并推送，再在origin/main上创建本地main并merge stage1。main通过最小启动/业务链验收后才建codex/product-ui-v1。禁止在main做UI大改。正式入口保持PySide6。

主产品运行需要外部配置的Voice/WebRTC/HealthKit/OCR/推送仍是接口已迁、实机未验收；本次main验收不扩充功能，也不声称这些设备已在线。验收完成后另写本轮main结果，UI分支只盘点。
