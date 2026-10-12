# 正式安排独立跟练与视觉关联：本机验证

验证时段2026-10-12至10-13；基于已上传`0267d35`，分支`codex/frontend-flow-optimization`。继续桌面《安康前端流程优化实施任务书.md》的B01/B02与U1–U3接线，完整U0–U6／F01–F36仍在实施。

## 原入口的实际改变

已启用v2的宿主在原训练计划卡片提供“使用已有安排跟练”，沿用原按钮、确认区域和practice页面。确认采用本人安排、支撑及确需的陪同后，直接进入允许的跟练，不申请相机或等待视觉READY。普通结束仍只是结束，明确“本组已完成”才推进独立组序列；原计划剂量、自动完成进度和测量资格不改。

多组／休息／下一项、暂停返回、刷新恢复、原键查回丢失结束回复、原历史和独立后补感受复用原控制器。刷新后保持原组和填写并暂停，不自动采集。运行绑定决定真实URI；归档安排不能阻止原结束操作查回。切本人后的迟到404不能创建旧练习，原结束草稿不自动向新本人补交。

### B01/B02最小接缝

仅v2已启用时，`mobile_rehab/rehab_v2/practice.py`沿原`Storage._call`保存独立命名空间；没有新患者数据库或第二个writer。初始化前做SQLite一致性备份，namespace version未知拒绝，不修复或覆盖。原user_version、正式session事务和既有事实不改。

资格来自原BackendPlans、评估引用／协议digest、plan_progress、eligibility_session和feedback_block的当前事务核对。原本人／来源／版本、明确采用／支撑／必要陪同和已知不适保留；正许可带稳定`FORMAL_ARRANGEMENT_GUIDED_ALLOWED`，不授予正式测量或贡献，不声明临床适宜性已评估。初次入口沿原next_key，后续只推进冻结独立guided序列。旧不适不因后来填0或换同动作计划消除。

独立记录保存`GUIDED_PRACTICE:SELF_USE`，另存安排来源`LIVE_CAMERA:SELF_USE`。整组自报／页面时间不写为自动确认／有效保持／正式贡献；未填保持null。未接权威模式事件时`mode_segments=[]`，不拿服务收据起止制造连续运动片段。

`visual-link`核对原session的owner、participant、原计划版本／条目、training模式、动作侧别、完整settings及来源；一个session只关联一个journey，同键同载荷可核对。原source_epoch、快照、canonical和贡献不修改，范围为`journey_not_self_reported_set_total`。GET的`saved_parts`分别读取练习、视觉canonical和感受的实际保存状态。

**真实关联接口已验证，训练页并行摄像头、权威模式事件和统一保存汇总尚未接。** 新独立跟练页不拿旧/live预览冒充正式测量。托管能力不向PHONE_LOCAL声明，APK保持既有本地能力。

## 输入与真实性边界

- 正计划由隔离TEST几何合同评估经原服务生成，不直接改SQL，不放宽产品资格，不是人体合格评估。
- 实际视觉训练前provider已恢复原值；获准肩外展原片的预录相机帧走原YOLO／HTTP／SQLite。本次5处理帧、0自动次、无基线，如实保存，不宣称人体测量成功或精度。
- APK资源CPU Worker／PhoneStore回放同一MP4：3视觉次数、有效画面占比0.9606299186765038，后者不是准确率。独立自报10及感受修改是明确QA输入，不是录像测得的完成量或患者感受，不与3相加。
- 原片、cookie、person／session编号、库、逐帧输出、截图及WebM不提交。服务只用私有目录和随机loopback端口，用户8765／1396、相机和旧窗口未启停。

## 尝试分母与最终证据

| 路径 | 实际分母 |
| --- | --- |
| 新跟练页面 | mobile-01、desktop-01、mobile-02、desktop-02共4次，4次完整；前两次较早源码，后两次最终源码 |
| 原视觉引擎关联 | native-link-01、native-link-02共2次，1次失败保留、1次完整；02目录名称含20261013仅为标签，实际始于10月12日23:53 |
| 包资源本地兼容 | phone-01、phone-02共2次，2次完整；02使用最终构建02资源 |
| 原本机构建 | build-01、build-02共2次，最后02作为交付产物 |

native-link-01首个创建返回403，未完成相机训练。验证工具漏带原`X-Rehab-Client: mobile-v1`；只补验证请求，不改产品权限保护。原失败目录保留，确认进程退出后才在新目录发起02。

| 最终私有证据标识 | 已证明范围 |
| --- | --- |
| `formal-guided-20261012-mobile-02`，390×844 | 2独立COMMITTED组、1journey；首组自报3、次组null；暂停刷新、丢结束回复查回原键、后补感受／历史／legacy；0相机申请、0视觉创建、0正式进度；浏览器错误与API5xx空 |
| `formal-guided-20261012-desktop-02`，1440×940 | 同一最终流程两组完整；电脑浏览器尺寸不称Qt重验 |
| `formal-guided-20261013-native-link-02` | 原YOLO训练5帧／0次／无基线，创建两POST同键同载荷，canonical一致；真实HTTP关联；视觉COMMITTED时practice仍LOCAL_DRAFT，practice独立结束后COMMITTED，feedback仍null；自报10不进自动确认／贡献 |
| `formal-guided-20261012-phone-02` | 最终包资源真实Worker／Store、1job／1独立practice；原生暂停处理、丢结束回复刷新、历史备份／legacy、独立反馈3个QA版本；0Python请求；不是真机或物理声音验收 |

最后源码JS284通过、0失败（`formal-guided-20261012-js-final.stdout.log`）。最后构建02和最终grant断言后，手机Python／实际包装186通过、2subtests、1原Starlette弃用警告，58.70秒（`formal-guided-20261012-python-release.xml`）。13个新增HTTP／writer专项是186子集，不另累计。原相关后端不是全套；Qt本轮不改，不用历史计数冒充重验。

原session／progress／BackendPlans／async_finish回归最终52通过、26subtests、1原警告，50.40秒（`formal-guided-20261013-backend-release-02.xml`）。首个发布前回归为51通过／1失败，历史分页测试连续创建第4个session时收到`rehab_compute_resource_busy`（`formal-guided-20261012-backend-release.xml`）；失败保留，原测试和service均没有改动，确认任务终止且无QA宿主仍运行后按原命令重验通过。原report有短暂primary独占准入而formal为非等待共享准入，存在资源交接时间窗口；本次没有用清锁文件、关用户服务或放宽准入消除失败，也不能仅凭重跑通过声称该偶发竞争已修复。较早backend-01的52通过仅是原时点，不覆盖这次失败。

65已跟踪保护内容相对0267d35未变，两尺寸原预览按钮／视频／字体几何不变（`formal-guided-20261012-visual-release.json`，原预览`formal-guided-20261012-preview-01`）。主代理已审最终手机结束页、电脑第二组和测量历史截图。frontend-design用于原组件复用和截图审查，没有CSS／字体／图标／主题变化。既有窄屏按钮换行与长页固定导航未重设计，不称全产品／高DPI／真机视觉验收。用户未跟踪图片不在65分母中。

## 构建、发布与回退

APK0.2.15／code17、28137155字节；SHA256 `67B81D3CCB89467E4BA52349523B61D2592FE1D619D324C7A3118F43FD3D9C38`，原v3签名、证书SHA256 `607edd7dc1df261e52fa2fe35ea6391e1ce77cbcebc315fea80dd815bac1a5d8`。实际ZIP核对29共享资源和3原本地核心与源码一致，原origin、权限、模型和签名不换。原0.2.14仍SHA `5B5D0AD15CE87B075630F62D0F051A29AA3C8D146CA0A8DA7BC1D8D494FCEBAF`。原构建三条javac8过时提示保留；未在红米安装，APK按原规则不上传GitHub。

本轮仅提交自己的源码／测试／文档，推当前流程分支，不自动合并main。桌面仍0.20.0，提交后沿原脚本／已验证pythonw更新桌面“安康康复（最新版本）”Git描述；本机PySide6 6.11.2。不关闭旧窗口，不替用户启用默认关闭的v2。

`experience=legacy`关闭新开始按钮，已有记录／原操作核对／只读历史仍可读；不在运行中换provider／本人／origin，不删除namespace或恢复备份抹去后来事实。降装APK不是数据回退方法。

## 未完成与下一项

下一增量优先接正式跟练页的原摄像头测量旁路、6秒软等待、原session关联、权威模式事件，再接各部分保存状态单行汇总。接口验证不代替页面接线。Qt后补感受／跨进程outbox，全模块局部加载／持久原片／跨窗口租约／全部音频，坐站与康复深蹲输入、Redmi性能／生命周期及完整F01–F36仍待，完整目标保持active。

## 可复跑

目录必须全新且位于私有验证根；正式服务与Python专项串行以遵守原计算租约。超时先查原句柄，不直接再起任务。

```powershell
node tools/frontend_flow/verify_formal_guided.cjs D:/RehabFrontendFlowVerification/<fresh-mobile> --record
node tools/frontend_flow/verify_formal_guided.cjs D:/RehabFrontendFlowVerification/<fresh-desktop> --desktop
node tools/frontend_flow/verify_formal_training.cjs D:/RehabFrontendFlowVerification/<fresh-link> --guided-link --record
node tools/frontend_flow/verify_phone_practice.cjs "<authorized-original-video>" D:/RehabFrontendFlowVerification/<fresh-phone> --feedback
python -m pytest mobile_rehab/tests android_offline/tests/test_packaging.py -q
python -m pytest tests/rehab_backend/test_sessions.py tests/rehab_backend/test_progress.py tests/rehab_backend/test_backend_plans.py tests/rehab_backend/test_async_finish.py -q
node tools/frontend_flow/verify_visual_resources.cjs <private-json> <private-preview-directory> 0267d35
```
