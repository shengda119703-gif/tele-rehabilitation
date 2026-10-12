# 正式跟练相机旁路：本机验证与发布

日期：2026-10-13（Asia/Shanghai）。基于已推送 `c6d4a17`，分支 `codex/frontend-flow-optimization`。本文件记录本次增量，不声称完整任务书或人体／临床准确性验收。

## 真实入口与行为

已明确启用 v2 的原 `/capture?tab=plan` → 原正式安排 → “使用已有安排跟练” → 当前组 → “摄像头自动记录（选用）”。独立跟练先开始；相机同意和机位确认只限制可选测量，不限制原许可范围的练习。

相机使用原 SessionAdapter、原 JPEG/processed-sequence 帧泵、原 YOLO、原 SQLite writer 与原 visual-link，不新增模型、阈值、剂量、医疗资格或视觉事实写入方法。六秒展示等待后，同组继续；无效指标显示 —，不补基线／次数。暂停、隐藏、导航和换本人释放画面／音频；换本人不自动补发旧操作。关闭相机／结束练习分别核对两种记录。服务自行终结也能关掉相机，不丢跟练。

原练习小草稿保存 `formalVisual`（原创建、绑定、原控制草稿、原关联键／回执），不存 JPEG；刷新只查原身份并暂停，不自动开相机。未知关联回复重用原键与载荷，校验本地及服务回执。测量草稿标记客户端 `practice_binding`，独立实时训练不误借这些草稿；损坏数据可导出。模式变化目前只是本机展示元数据，有明确来源、世代、session／epoch、组位置与非有效保持时间基础；服务器权威 `mode_segments` 未接，不伪造连续运动时间。

## 实际执行及分母

原件、受限人物画面、cookie、配对码、逐帧结果、库、截图及操作录屏不提交。私有根目录 `D:/RehabFrontendFlowVerification`。正安排前置评估是显式 **TEST 几何契约夹具**，不是人体合格评估；在正式训练前已恢复原 provider，后续真正帧由原 YOLO 处理。以下自报 10 是 QA 明确填写，不是受试者真值。

| 验证 | 实际结果及边界 |
| --- | --- |
| 正式相机旁路 | 6 尝试／6 完整，手机 01–04 与电脑 01–02；最终手机 04 为 390×844，15 帧；电脑 02 为 1440×940，16 帧。每次 1 原视觉创建、2 同载荷关联 POST，原关联回复丢失后找回同一旅程 |
| 等待和暂停 | 原 WAIT_READY 六秒后仍是同一组且跟练继续；暂停释放流，刷新找回原创建键／session／填写总量，不申请相机。恢复跟练不自动恢复测量；显式选择才开相机 |
| 两种结束 | 最终手机 04 丢失视觉 finish 与独立 practice finish 回复后，刷新分别找回 COMMITTED；无结束后新帧。电脑 02 在测量服务自行终结时立即释放流，跟练仍运行，随后保存独立练习 |
| 事实 | 自动 0、无基线；自报 10 单独保存；confirmed_count／formal_plan_contribution 为 null，原正式进度 0。两个 saved_parts 分别 COMMITTED，未填写感受仍 null，canonical 与原最终事实相符 |
| API 和页面 | 六次实际相机流程浏览器错误和 API5xx 均空；历史能读原跟练和原视觉，不套旧 summary。新入口不称后台 READY 或人体评估合格 |
| APK 资源本地流程 | 4 尝试／4 完整（phone01–04），最后原 CPU Worker 原肩外展视频识别 3 次、覆盖 0.9606299186765038，**覆盖不是准确率**；原 Store 独立自报总量、暂停处理、丢结束回复刷新、历史／备份、legacy 与后补感受可用，0 Python／云 API |

最终证据：`formal-camera-20261013-mobile-04/result.json`、`formal-camera-20261013-desktop-02/result.json`、`formal-camera-20261013-phone-04/result.json`。原批准肩外展文件及预录相机副本 SHA 不变；未拍新人体视频或运行用户物理摄像头。

原独立实时训练另做 1 尝试／1 完整兼容，`formal-camera-20261013-original-training-01/result.json`：原 YOLO 5 帧、0 次、无基线；创建丢回复同键两 POST、暂停刷新、原 canonical、后补 QA 感受、返回原计划及 legacy 历史通过，页面错误和 API5xx 空。该前置安排同样是明确 TEST 合同夹具，不是人体测量成功。

原无相机跟练另做 2 尝试／2 完整，每次两组兼容；最终证据 `formal-camera-20261013-no-camera-02/result.json`：可选相机面板出现但不选用，0 相机申请／0 视觉创建；自报 3／null 是明确 QA 输入，原暂停刷新、丢结束回复、下一组、历史和后补感受保持，浏览器错误和 API5xx 空。该验证只覆盖不选用相机的路径，不替代上表六次实际旁路验证。

## 回归、失败与视觉

- 最终共享 JS／Android JS **297 通过，0 失败**，`formal-camera-20261013-js-final-04.log`。新增控制器测试核对单权限、迟到流、旧本人资源释放、同键关联、伪造本地回执拒绝、结束优先、迟到读不回退提交、三种状态分离；原训练测试核对不借用旁路草稿；原测量测试核对读到最终快照仍触发相机释放；pagehide 事件归一为稳定原因。这些都是该全套的子集，不另累计。
- mobile Python 与真实包检查 **186 通过＋2 subtests，1 条原 Starlette 警告**，`formal-camera-20261013-python-02.xml`。最终另验实际 ZIP 3 项＋2 subtests，`formal-camera-20261013-packaging-final.xml`（子集）。不是全 Qt／后端重新验收。
- 首次 JS 发现原预览单独载入时 `formalFlow` 尚未定义，已以存在性保护修正；之后旧 ui-lock 与新源码不一致的 1 项失败保留在 `formal-camera-20261013-js-01.log`，通过原打包流程重建而非放宽断言。
- 首次 Python 为 185 通过／1 包指纹失败：验证期间源码更新，包尚未重建；原失败 `formal-camera-20261013-python-01.xml` 保留。最终按同一原构建流程完成后重新跑全套，再单验最终 ZIP；不是隐藏产品故障或删掉失败用例。
- 原构建共 4 次，最后 `formal-camera-20261013-build-04.stdout.log`；中间源修正后的旧构建不作为最终包。保留原 Java 8／deprecated 编译警告，不称零警告。
- `formal-camera-20261013-visual-final.json`：相对 c6d4a17 的 **65 已跟踪保护内容不变**、390×844 与 1440×940 原预览／按钮几何不变；实际新增页截图已审。CSS、图标、动作图片、字体和主题未改。手机新增长按钮沿原样式换行；旧固定导航和原颜色对比仍是原设计，没有借本次接线改视觉。

## 构建、入口与回退

APK：`android_offline/dist/tele-rehabilitation-mobile-0.2.16.apk`，versionCode18，28145432 字节，SHA256 `8B7A3C7B628AF01764D9F095227DDD987EFE3CA2E43A3F1CB0B19859B293F31F`。原 v3 签名证书 SHA256 `607edd7dc1df261e52fa2fe35ea6391e1ce77cbcebc315fea80dd815bac1a5d8` 保持；实际 ZIP 匹配 30 共享锁定资源及 3 原本地核心。0.2.15 原 APK 指纹仍 `67B81D3CCB89467E4BA52349523B61D2592FE1D619D324C7A3118F43FD3D9C38`，未覆盖。

PHONE_LOCAL 不声明托管正式测量能力，仍走原本地执行器和库。桌面产品版本仍 0.20.0；提交后按原 `New-RehabDesktopShortcut.ps1`／验证 pythonw 更新桌面“安康康复（最新版本）”入口的 Git 描述，仍指原 `Start-Rehab.ps1`。没有重启用户 8765／1396、打开用户摄像头、关闭旧窗口或改伙伴素材。

回退：`experience=legacy` 不启动新正式测量，原精确键恢复／结束、独立跟练历史、原 canonical 和后补感受继续可读。正在运行的旅程不切 provider；不删事实／草稿／原片，不用旧 live 删除冒充正式保存。

## 未完成范围

完整 U0–U6／F01–F36 **仍未完成**。服务器权威模式事件／其他端正式视觉关联、Qt 后补感受与跨进程 outbox、全模块局部加载／持久原片、同旅程跨窗口主动租约、全产品音频、坐站与康复深蹲实际输入、Redmi 安装／真实声音／p95／熄屏回收／长时压力尚未完成或未验证。本次不能称手机全功能真机上线、全部后端验证或临床效果证明。
