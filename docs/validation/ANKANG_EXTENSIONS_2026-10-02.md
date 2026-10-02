# Ankang 扩展能力迁移与验收（2026-10-02）

分支：`codex/rehab-agent-stage1`。基线：`e0fc5a4`。只迁移既有能力边界和实现，不 merge main，不改 UI 样式，不改 Agent 理解/检测/回复规则，不新增账号、云服务或硬件驱动。原 React、demo、Swift 和 Route2 源码保留。本文覆盖上轮 Productization 的剩余扩展能力；历史迁移地图以本文最新结论为准。

## 正式边界与实现来源

正式桌面入口仍是 `app/ui/product_window.py → app/product/backend.py → bridges/ankang/client.py → scripts/agent-bridge.cjs → src/product/ProductService.ts`。TypeScript 路径均相对 `ankang/route1-health-agent/`，Python 路径相对 `rehab_codex_single_camera_v2_1/`。

- `src/product/ExtensionPorts.ts` 定义 VoicePort、SyncPort、ProductExtensions；宿主注入设备、HealthKit、语音、通知和同步通道。业务仍复用原 Runtime、FamilyService、NotificationService、ArchiveService 与 HealthEvent。没有 Python 第二套业务实现。
- 语音：把 VoiceListeningDialog 原识别生命周期抽入 `adapters/BrowserVoiceAdapter.ts`。React 原组件继续调用同一控制器，语言 zh-CN、临时结果、结束时单次发送、取消丢弃、启动超时及权限错误保留。ChatView 的 TTS 和主气泡选择也共用原实现；正式 voice.input 调用已有 chat，voice.output 只读当前本人 Agent 消息主块，voice.cancel 终止输入/输出。Node/PySide6 默认没有浏览器语音 API，状态明确 unavailable，未虚构 Windows ASR。
- 同步：原 message union/envelope 移入 `sync/protocol.ts`，旧 hook 兼容导出。PeerJSCrossDevice 改为宿主注入原信令/ICE 配置，React 原配置继续传入；原 PeerJS transport、邀请码命名空间、状态和超时实现保留。`sync/BrowserSyncAdapter.ts` 对这些实现提供正式 SyncPort，并保留 BroadcastChannel 本地通道。
- ProductService 同步入口为 sync.start/status/poll/publish/close；宿主订阅先进入有界 inbox，poll 在产品请求线程应用，防止异步回调直接改 Runtime。原 FamilyService 负责邀请码握手；未绑定 peer 拒收，通知限定 owner/mode/relationship，原 NotificationService 合并保护已确认状态。私密完整事件和聊天只走 local；药物更新按原授权门禁及旧 familyId/mode/name 载荷核对。新版带 owner/mode 的载荷也支持。原 signals.summary 计数载荷兼容；family.consent 兼容原 sentAt，按同一关系的时间拒收旧授权。HealthEvent 仍按原稳定 ID 合并，不新增通用多主数据库冲突协议。
- HealthKit：正式调用原 HealthKitDeviceAdapter，不模拟 iOS。原样保留 Swift HealthKitService/Models/Uploader、entitlements、HTTP bridge、诊断、错误码和 autoSync revision 工具。HealthKit 的原测量校验器扩为通用来源参数，原 HealthKit 默认源和错误语义保留；单位、有限数值、来源、日期、ID 与 confidence 在入口验证。导入后复用 measurementToEvent/appendHealthEvents，再由原 Runtime 投影到 Person Twin。权限仅由 iOS companion 请求；Windows 的 healthkit.diagnostics 返回外部授权状态。
- 设备：`adapters/MeasurementInputAdapter.ts` 只把已有 HealthMeasurement schema 接入正式入口；device.import 需匹配当前 owner，device.pull 调用注入的原 DeviceAdapter。血压、静息心率、血氧、活动等均使用既有 METRICS 和单位。整批校验后再落盘；demo 数据必须在 demo scope。原 DemoDeviceAdapter 可注入作为测试支持。
- 通知：`webhookFamilyDelivery` 复用原 sendWebhookPush，支持 Server酱、PushPlus/custom；ProductService.notification.plan 使用宿主 delivery，后方仍只有原 NotificationService 授权、去重、持久化预留和确认规则。渠道接受记录 accepted，不能叫 delivered。BrowserNotificationChannel/browserFamilyDelivery 继续保留，可由浏览器宿主注入，不在 Node 伪造浏览器 push。
- 图片/视频：原 RealImageHealthParser、HttpVisionProvider、imageNormalizer、用户确认链路继续使用。正式 `app/product/capture.py` 直接加载原 Route2 `backend/capture.py` 的 CaptureFile/CaptureBatch/CaptureSource/BrowserUploadCaptureSource，未复制其实现，不加载空间处理器。ProductBackend.submit_capture → ProductService.media.import → 原 ArchiveService 保存图片/视频；附件不自动成为健康事实。原康复 CameraManager/回放仍是相机拥有者，不另开 VideoCapture。

## 最终能力表

| 原 Ankang 能力 | 是否已迁 | 当前正式位置 | 是否实际可运行 | 是否需要外部设备/平台 | 后续还缺什么 |
| --- | --- | --- | --- | --- | --- |
| Agent/多轮/自报/档案/检测/Person Twin | 上轮已迁，本轮复用 | ProductService、runtime、pipeline/events、personTwin | 本机业务链可运行 | LLM 路径需要已配置服务 | 真人业务验收持续保留 |
| 药物、今日任务、家庭关系/共享/隐私、周报/趋势 | 上轮已迁，本轮复用 | medication、family、archive/healthHistory、ProductService | 本机业务链可运行 | 远程身份另需可信映射 | 未新增账号/云多用户 |
| 语音输入/ASR 生命周期与状态 | 本轮接口与原浏览器实现迁入 | ExtensionPorts.VoicePort、BrowserVoiceAdapter、ProductService voice.input/cancel | 浏览器替身验证通过；默认 Windows unavailable | 浏览器麦克风/语音服务，或未来原生 adapter | Windows 原生宿主接线、真实麦克风验收 |
| TTS/语音输出 | 本轮迁入 | BrowserVoiceAdapter.speakText、mainSpeechText、voice.output | mock 验证主气泡；真实音频未验收 | 浏览器合成引擎或原生 TTS adapter | Windows 输出接线及真实播放验收 |
| 跨设备 message schema/PeerJS/本地同步/绑定与合并 | 本轮迁入 | sync/protocol、BrowserSyncAdapter、PeerJSCrossDevice、SyncPort、ProductService sync.* | 真实本地 BroadcastChannel 通过；产品 peer 门控为 mock | WebRTC 浏览器宿主、信令/STUN/TURN、另一台设备 | 默认 PySide6 外部通道宿主接线、双端可信 owner 映射和实机验收；原多 tab 原子锁仍未实现 |
| HealthKit 数据模型、权限、HTTP adapter、revision、mock 支持 | 本轮迁入/保留原外部实现 | HealthKitDeviceAdapter、healthkit/autoSync、healthkit.*；原 scripts/healthkit-bridge.mjs、native-ios | HTTP/mock 协议和导入通过；iPhone 未验收 | iPhone、Mac/Xcode；Watch 指标还需相应数据 | iOS 签名、权限与真实样本端到端验收 |
| 外部 webhook/push/channel | 本轮接到原通知服务后方 | NotificationService → webhookFamilyDelivery → WebhookPushChannel；BrowserNotificationChannel | mock HTTP 接受/授权/去重通过 | 推送服务/token；浏览器 push 需浏览器宿主 | 真实请求/接收者回执验收；默认未配渠道即 unavailable |
| 通用健康设备输入与演示设备 | 本轮迁入 | DeviceAdapter、MeasurementInputAdapter、device.import/pull → HealthEvent → Twin | 合成批次及 Python/Node 真实 bridge 可运行 | 真实采样需设备/厂商宿主 | 真实设备协议 adapter 和测量验收；不把 DemoDeviceAdapter 当设备驱动 |
| 特殊硬件接口/协议/driver | 全库核查；现有接口已保留 | DeviceAdapter、HealthKit bridge、CaptureSource；正式产品各端口 | 接口/mock 可运行 | 相应真实设备/平台 | 上游没有独立雷达/BLE/串口等 driver，不能宣称已迁或已验收不存在的实现 |
| 图片识别/报告 OCR、归一化、候选确认、mock | 上轮已迁，检查无遗漏 | 原 RealImageHealthParser/HttpVisionProvider/imageNormalizer → image.parse/confirm | 测试 provider 可运行 | 真识别需外部视觉服务 | 真实 OCR/模型验收 |
| 图片/视频采集批次、文件附件、康复摄像头/回放 | 本轮补通用 capture 接口，上轮相机/附件复用 | app/product/capture.py、submit_capture、media.import、ArchiveService；CameraManager/回放 | capture 文件映射及视频附件协议通过 | 实时采集需真实摄像头；测试文件无需 | 媒体/摄像头实机验收；上游没有独立视频健康推理 parser |
| Home Twin/Route2 空间建模/3DGS、查物/空间风险/复扫推理 | 继续延后 | 原 HomeTwinClient/HomeSafetyActionAdapter、route2-home-3d 原实现 | 本轮未运行 | 空间素材/GPU/相关平台 | 按用户后续授权接入；其 generic capture 合同已单独复用 |

## 默认桌面配置与调用

Bridge 读取宿主环境，不把 token 写入健康记录：

- `ANKANG_HEALTHKIT_ENDPOINT`：原 bridge measurements HTTP endpoint；`HEALTHKIT_BRIDGE_TOKEN` 与 iOS/bridge 一致。产品 ownerId 必须与桥接样本用户一致；不存在静默认领/重映射。
- `ANKANG_WEBHOOK_PROVIDER`（serverchan/pushplus/custom）、`ANKANG_WEBHOOK_TOKEN`、custom 的 `ANKANG_WEBHOOK_URL`。没有配置不发送，保持 unavailable。真实外部发送本轮未执行。
- 浏览器语音和 PeerJS adapter 必须由支持相应平台 API 的宿主注入 ProductExtensions；默认 Node bridge 不注入 voice/sync，接口状态/调用明确告知不可用。未来原生/移动宿主实现同一 port，无须改健康业务规则。
- `extensions.status` 返回各实际配置状态、同步状态/摘要和 externalAcceptance=unverified。仅声明存在模块不表示设备在线。

## 验收（本轮实际结果）

- build:bridge、全项目 typecheck 通过。
- `node --test tests/product-extensions.test.cjs tests/product-desktop.test.cjs`：12/12 通过（新增 9 项 + 原产品 3 项）。包括批次校验/隔离/去重/Twin、原 HealthKit adapter、通知 accepted/去重、同步授权/旧消息/确认不倒退、local 观察/检验/聊天/药物、真实本地 BroadcastChannel、ASR 取消和主气泡 TTS、视频附件。
- `node scripts/test-healthkit-adapter.mjs`：原 10/10 通过。没有改其测试或伪造实机状态。
- Python 使用捆绑解释器：原 CaptureBatch 合同 → 文件大小/字节/私密附件 payload 检查通过；另一次实际 AgentBridge 子进程 → ProductService 建档/device.import/status 检查通过，临时 SYNTHETIC TEST 用户，退出清理。
- 原 voice-dialog-browser 脚本默认 Chromium 因本机未安装 Playwright Chromium 无法启动。临时运行副本改为本机 Edge：原“取消按钮在 844px 首屏内”断言失败（y=810.40625、高=52）；跳过这一条布局断言后，取消丢弃、识别完成只发一次、权限失败与退出功能断言通过。该原布局断言此前迁移地图已列为上游复现失败，本轮不做 UI 调整；不把删去布局断言后的功能通过写成原完整测试通过。临时副本/截图不入 Git。
- 未打开摄像头、未使用真实语音、未连接真实 WebRTC peer/iPhone/Watch/厂商硬件、未发送真实 webhook、未调用真实 OCR。所有外部能力标为“接口已迁 / 实机未验收”。

## 覆盖结论

本轮新迁：Voice、Cross-device Sync、HealthKit、外部通知 channel、通用设备输入和与空间推理解耦的通用 capture。原 Ankang 30 项迁移地图和全库 adapter/driver/bridge/native-ios/pipeline 已复核；除了用户延后的 Home Twin/Route2/3DGS 及其依赖的查物/空间风险操作，没有发现另一个独立有产品价值的未纳入能力模块。React 呈现、演示种子和调试展示保留为参考/测试，不作为第二套正式业务。

ProductService 已覆盖最终保留能力的业务入口及外部端口边界；这不表示默认 Windows 桌面已具备浏览器 ASR/WebRTC，也不表示外部平台实机验收完成。核心业务沿用上轮正式产品实现；旧 A1/A2/A3 未恢复。后续欠缺是宿主/外部服务与真实验收，不是重新写 Agent/通知/健康业务。
