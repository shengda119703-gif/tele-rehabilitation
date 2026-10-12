# F01–F36 验收映射（2026-10-12）

“局部”不等于三端验收。实际浏览器采用桌面 Edge headless 的手机尺寸，不能替代真机。测试夹具和 QA 输入不是临床真值。

当前独立感受证据：`test_practice.py` 新4个HTTP／SQLite案例、`care-local.test.cjs` 新5个原Store案例、`test_practice_feedback.cjs` 6个控制器案例（均全套子集），以及 `verify_feedback_flow.cjs` 从原结束／历史实际操作。成功托管 `actual-hosted-feedback-20261012-0166a9cd`、实际APK资源 `actual-phone-feedback-20261012-06d1d950`；丢回复刷新仍1练习／原回执，真实冲突不自动覆盖。原返回按钮以文档坐标核对，CSS／图标不改。此前本轮托管4次及手机2次未完整通过均保留，不能算成功。反馈字段是明确QA输入，不是人体感受真值。

| 用例 | 现有证据／状态 | 尚需覆盖 |
| --- | --- | --- |
| F01 | 未完成；统一 snapshot 仍整页等待 | 局部加载／报告故障隔离 |
| F02 | 托管／APK 资源真实路径不补头像／身高；本地默认档案可运行 | Qt 及真机缺资料实际流程 |
| F03 | 局部：预览有停止／返回；生命周期测试只有一申请 | 实际忽略授权＋允许非相机路径 |
| F04 | `test_live_lifecycle.cjs` 晚到流释放通过 | 真机权限与宿主生命周期 |
| F05 | 托管／APK 资源已有合法安排直接无相机跟练，通过实际浏览器 | 并行测量 WAIT_READY 6 秒自动降级 |
| F06 | `test_practice.py` 无安排／不足评估拒绝、无假记录 | 明确允许的独立安排和自主草稿出口 |
| F07 | 未改原测量规则 | 主动作与辅助质量的实际帧演示 |
| F08 | 预览不把无效角度显示为 0，原计数不被缺字段清零 | 静默窗口及三端缺测展示 |
| F09 | 未完成 | 遮挡转折、模式分段与来源去重 |
| F10 | 局部：语音限频、无自动相机重启 | 长缺测循环恢复实测 |
| F11 | 保留原身份／跟踪策略 | 旁人入镜，不串人／不丢旅程 |
| F12 | 未改坐站算法 | 坐站实际跟练＋准备失败输入 |
| F13 | 未造膝角 | 康复深蹲真实输入与缺点降级 |
| F14 | 预览 cancel／generation 有单元证据 | 统一音频及迟到 onend 全链 |
| F15 | 预览生命周期去重；托管／APK 跟练原读操作核对与同键创建 | 三端正式 pause/resume 有界控制 |
| F16 | 隐藏停 preview；跟练暂停不补长 dt；实际 APK 资源调用原 offlinePause 保留输入 | 真机熄屏／进程回收／原生音频 |
| F17 | 结束的 practice 只读；新版资格查询不可续练 | v2 finalized／interrupted 关联新段 |
| F18 | 独立 self_count，confirmed=null；不改计划 | 实际 6／8／10 三来源组合 |
| F19 | 托管／本地契约：空 count 保持 null，普通结束不写完成目标 | Qt 各结束入口与真机 |
| F20 | practice 200 真 commit，不冒充 v2 202 | v2 finish／慢报告消费者 |
| F21 | 托管／实际 APK 资源同键结束、破坏提交后回复、刷新原记录通过；本地 Store 重开测试通过 | v2／Qt 与真机跨进程恢复 |
| F22 | 草稿写失败有内存措辞，服务器可提交 | 实际存储故障完整客户端验收 |
| F23 | 尚未完成 | 双端容量不足与导出 |
| F24 | 托管／APK独立感受真实页面：后补／丢回复刷新／真实revision冲突／明确选择通过，null不补0；每旅程草稿 | Qt／v2反馈及全模块outbox／真机 |
| F25 | 后补明确不适亦阻止同原计划继续，后改0不自动消除；已发生事实仍可保存 | Qt／v2、下一项全链与独立安排政策 |
| F26 | `test_upload_receipts.py`＋原录像实际 browser 1 POST／1 job | 真机弱网、客户端重开操作日志 |
| F27 | 未把报告失败重建为第二次评估 | 正式派生报告重建接口 |
| F28 | 同页面原 File／同意状态可复用 | 跨重开可达媒体引用与重新选择原件 |
| F29 | 旧回调 owner generation／页面节点隔离 | 全模块 outbox 与服务器切换 |
| F30 | 实际 APK 资源／原本地 Worker 与 Store 完整肩外展→计划→跟练→保存／刷新／历史／备份通过，0 Python API 请求 | APK 完全离线真机全旅程 |
| F31 | preview 不称训练历史；本地 practice 实际启用且保存 PHONE_LOCAL；v2 默认关 | Qt、各端完整能力矩阵／fallback |
| F32 | 上传不锁导航；跟练返回保留输入通过真实 browser | 全模块非阻塞与迟到写回 |
| F33 | 后端拒绝另一 open journey；同事实结束幂等 | 同 ID 两窗口主动租约／接管 |
| F34 | 独立表不覆盖旧 schema | v2／跨条件可比性 UI |
| F35 | preview 单帧在途、语音不排队 | 慢推理、多组、长时资源验收 |
| F36 | 64 保护内容、两浅色尺寸动作／预览几何通过 | 全页面、深色／缩放／Qt／真机 |

本轮专用证据：`android_offline/tests/care-local.test.cjs` 的7个独立 practice 案例、`test_product_ui.cjs` 的 History API 保留；`verify_phone_practice.cjs` 当前成功 run `actual-phone-practice-20261012-cf10b538`，`verify_practice_flow.cjs` 当前成功 run `actual-practice-20261012-4f0d91b7`。前者是实际 APK 页面／算法／本地存储，不是物理 Android；其 10 次为 QA 本人输入字段，不是观测数。

原始证据在忽略的 `.runtime/frontend_flow/20261012-u0/`、`20261012-u1-phone/` 与隔离 QA 输出中保留。公开文档不含私人原片、照片、逐帧数据、本人 ID、cookie 或配对码。完整 U2–U6 尚未通过，不能只用测试总数判断任务完成。
