# F01–F36 验收映射（2026-10-12）

“局部”不等于三端验收。实际浏览器采用桌面 Edge headless 的手机尺寸，不能替代真机。测试夹具和 QA 输入不是临床真值。

当前独立感受证据：`test_practice.py` 新4个HTTP／SQLite案例、`care-local.test.cjs` 新5个原Store案例、`test_practice_feedback.cjs` 6个控制器案例（均全套子集），以及 `verify_feedback_flow.cjs` 从原结束／历史实际操作。成功托管 `actual-hosted-feedback-20261012-0166a9cd`、实际APK资源 `actual-phone-feedback-20261012-06d1d950`；丢回复刷新仍1练习／原回执，真实冲突不自动覆盖。原返回按钮以文档坐标核对，CSS／图标不改。此前本轮托管4次及手机2次未完整通过均保留，不能算成功。反馈字段是明确QA输入，不是人体感受真值。

0.2.6：`test_observation_presenter.cjs` 7个生产展示器案例、`test_live_lifecycle.cjs` 3个新跟练consumer案例，以及 `verify_practice_observation.cjs` 调用真实两端预录相机／原模型。末次托管64d8a3ba／手机920fdcfe（完整run见改动报告），分别200／235帧；两端各4次流程通过，只有手机观察到稳定自动指导，托管稳定指导负结果保留；手机前三轮中的完整稳定指导→长缺测→恢复原证据仍保留。两端暂停停止相机，一次继续按原同意恢复新预览边界通过；原资格GET已实际完成但回复不可读取时，相机DOM／流／输入／正在练习均保留。模式转换仅客户端草稿；不是权威完整测量模式段、真机或精度验收。

0.2.7人工安排证据：`test_manual_practice.py` 7个原HTTP／SQLite案例、`test_manual_arrangements.cjs` 5个控制器案例，均全套子集。实际浏览器三次尝试、两次完整通过；首轮最后legacy检查的重复定位失败保留。末次 `actual-manual-practice-20261012-f67219e0` 原SQLite为0评估／1原人工计划／1独立practice；自报3为QA输入，confirmed_count及正式贡献null。明确确认默认未选、回到原练习不重复确认、结束回复不可读后刷新恢复原身份、原安排及进度不改。当前原自动路径托管477fb04d／实际APK资源358da890兼容通过；APK本地人工B01仍未接，不是三端完成。

| 用例 | 现有证据／状态 | 尚需覆盖 |
| --- | --- | --- |
| F01 | 未完成；统一 snapshot 仍整页等待 | 局部加载／报告故障隔离 |
| F02 | 托管／APK 资源真实路径不补头像／身高；本地默认档案可运行 | Qt 及真机缺资料实际流程 |
| F03 | 局部：预览有停止／返回；生命周期测试只有一申请 | 实际忽略授权＋允许非相机路径 |
| F04 | `test_live_lifecycle.cjs` 晚到流释放通过 | 真机权限与宿主生命周期 |
| F05 | 托管／APK资源原允许安排并行预览：真实黑JPEG／原模型准备失败，6秒后仍跟练，无新相机／旅程 | Qt、正式v2并行测量及真机 |
| F06 | 托管0.2.7原人工库B01：无合格评估／无自动候选，明确采用原安排后开始、返回／刷新、结束丢回复及历史同一记录；原自动门不放宽 | APK本地／Qt同等明确安排及自主草稿出口 |
| F07 | 未改原测量规则 | 主动作与辅助质量的实际帧演示 |
| F08 | 原展示器1.5秒静默、无效角度 —／次数保留；两端真实短黑JPEG后跟练继续 | Qt／v2和目标手机 |
| F09 | 手机实际预览AUTO→GUIDED→AUTO，独立确认仍null；客户端转换留草稿，不跨来源累加 | 权威模式段、明确转折遮挡／完成参考和三端 |
| F10 | 手机实际长黑JPEG及恢复不重启旅程；静态建议、相机／计次规则不改；托管不稳定负结果保留 | 多次循环、Qt／v2与真机 |
| F11 | 保留原身份／跟踪策略 | 旁人入镜，不串人／不丢旅程 |
| F12 | 未改坐站算法 | 坐站实际跟练＋准备失败输入 |
| F13 | 未造膝角 | 康复深蹲真实输入与缺点降级 |
| F14 | 预览 cancel／generation 有单元证据 | 统一音频及迟到 onend 全链 |
| F15 | 托管／APK预录相机实际暂停释放媒体；一次继续在原归属／原同意下开启新preview，无后台补帧；同键practice不新增 | 三端正式 pause/resume 有界控制、真机 |
| F16 | 隐藏停 preview；跟练暂停不补长 dt；实际 APK 资源调用原 offlinePause 保留输入 | 真机熄屏／进程回收／原生音频 |
| F17 | 结束的 practice 只读；新版资格查询不可续练 | v2 finalized／interrupted 关联新段 |
| F18 | 独立 self_count，confirmed=null；不改计划 | 实际 6／8／10 三来源组合 |
| F19 | 托管／本地契约：空 count 保持 null，普通结束不写完成目标 | Qt 各结束入口与真机 |
| F20 | practice 200 真 commit，不冒充 v2 202 | v2 finish／慢报告消费者 |
| F21 | 托管／实际 APK 资源同键结束、破坏提交后回复、刷新原记录通过；本地 Store 重开测试通过 | v2／Qt 与真机跨进程恢复 |
| F22 | 草稿写失败有内存措辞，服务器可提交 | 实际存储故障完整客户端验收 |
| F23 | 尚未完成 | 双端容量不足与导出 |
| F24 | 托管／APK独立感受真实页面：后补／丢回复刷新／真实revision冲突／明确选择通过，null不补0；每旅程草稿 | Qt／v2反馈及全模块outbox／真机 |
| F25 | 后补明确不适阻止相关练习，后改0不自动消除；托管B01同动作／侧别跨安排不能绕过已有停练，已有记录仍可保存 | Qt／APK人工安排／v2与下一项全链 |
| F26 | `test_upload_receipts.py`＋原录像实际 browser 1 POST／1 job | 真机弱网、客户端重开操作日志 |
| F27 | 未把报告失败重建为第二次评估 | 正式派生报告重建接口 |
| F28 | 同页面原 File／同意状态可复用 | 跨重开可达媒体引用与重新选择原件 |
| F29 | 旧回调 owner generation／页面节点隔离 | 全模块 outbox 与服务器切换 |
| F30 | 实际APK0.2.7资源／原CPU Worker／Store兼容重验358da890：肩外展→自动计划→跟练→保存／刷新／历史／备份，0 Python API；未启用人工安排本地能力 | APK人工安排完整接线及完全离线真机全旅程 |
| F31 | preview 不称训练历史；本地 practice 实际启用且保存 PHONE_LOCAL；v2 默认关 | Qt、各端完整能力矩阵／fallback |
| F32 | 上传不锁导航；跟练返回保留输入通过真实 browser | 全模块非阻塞与迟到写回 |
| F33 | 后端拒绝另一 open journey；同事实结束幂等 | 同 ID 两窗口主动租约／接管 |
| F34 | 独立表不覆盖旧 schema | v2／跨条件可比性 UI |
| F35 | preview单帧在途；跟练原资格查询期间实际video DOM／流不重建；两端完整停止后无新帧 | 慢推理压力、多组、长时、实际设备p95 |
| F36 | 64 保护内容、两浅色尺寸动作／预览几何通过 | 全页面、深色／缩放／Qt／真机 |

本轮专用证据：`android_offline/tests/care-local.test.cjs` 的7个独立 practice 案例、`test_product_ui.cjs` 的 History API 保留；`verify_phone_practice.cjs` 当前成功 run `actual-phone-practice-20261012-cf10b538`，`verify_practice_flow.cjs` 当前成功 run `actual-practice-20261012-4f0d91b7`。前者是实际 APK 页面／算法／本地存储，不是物理 Android；其 10 次为 QA 本人输入字段，不是观测数。

原始证据在忽略的 `.runtime/frontend_flow/20261012-u0/`、`20261012-u1-phone/` 与隔离 QA 输出中保留。公开文档不含私人原片、照片、逐帧数据、本人 ID、cookie 或配对码。完整 U2–U6 尚未通过，不能只用测试总数判断任务完成。
