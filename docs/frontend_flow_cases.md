# F01–F36 验收映射（2026-10-12）

“局部”不等于三端验收。实际浏览器采用桌面 Edge headless 的手机尺寸，不能替代真机。测试夹具和 QA 输入不是临床真值。

当前 Qt 增量：`test_qt_guided_practice.py` 用原 writer／Runtime 验证独立政策、本人／来源、原设置、原键、草稿和已有停止事实；`test_qt_practice_sequence.py` 8项增加真实writer的多组／下一动作、原休息、继续原键、停止／归档、取消休息及来源控制。`test_qt_guided_practice_ui.py` 当前19项包含原入口、暂停返回、原保存、晚到回复与结束优先、隐藏开始不续练、原历史和legacy，以及多组／休息／换动作确认、继续丢回复、在途创建／查询时结束、未知结束先查原身份、失败结束查询有界。`test_native_voice.py` 的无需音频组件取消不代表麦克风／ASR实测。最终core1080、UI488、原集成228，专项为全套子集，不重复相加。

多组实际`verify_qt_practice.py --multi`五次完整通过，最终75a7c11f／9a78f2bb：每run同1旅程、3独立提交组、0测量session，QA次数3／2／null。原休息不计练习，换动作只核对本项支撑／必要陪同，结束和继续丢回复均原键核对；原康复及统一历史可见各组。实际光暗截图已审，未改原设计；不作为真机／身体动作准确性验证。下段单组10次为f3dc32e时点的独立证据，不与多组次数相加。

`verify_qt_practice.py` 共 10 尝试／7 完整通过／3 失败保留；最新浅色 3624a552 和暗色 150% cd7fd2d5 调用真实 ProductWindow／Runtime／原 SQLite，0 评估／1 原安排→1 独立提交，暂停／返回／结束回复丢失／原历史及统一历史通过。QA 自报 3、confirmed／正式贡献 null。原首页／工作区截图和按钮审计同基线，61 个保护文件不变／3 个授权 Qt 控制模块变化。不把 offscreen Qt 当作原生 Windows 模态、物理手机、相机或人体准确性。

当前独立感受证据：`test_practice.py` 新4个HTTP／SQLite案例、`care-local.test.cjs` 新5个原Store案例、`test_practice_feedback.cjs` 6个控制器案例（均全套子集），以及 `verify_feedback_flow.cjs` 从原结束／历史实际操作。成功托管 `actual-hosted-feedback-20261012-0166a9cd`、实际APK资源 `actual-phone-feedback-20261012-06d1d950`；丢回复刷新仍1练习／原回执，真实冲突不自动覆盖。原返回按钮以文档坐标核对，CSS／图标不改。此前本轮托管4次及手机2次未完整通过均保留，不能算成功。反馈字段是明确QA输入，不是人体感受真值。

0.2.6：`test_observation_presenter.cjs` 7个生产展示器案例、`test_live_lifecycle.cjs` 3个新跟练consumer案例，以及 `verify_practice_observation.cjs` 调用真实两端预录相机／原模型。末次托管64d8a3ba／手机920fdcfe（完整run见改动报告），分别200／235帧；两端各4次流程通过，只有手机观察到稳定自动指导，托管稳定指导负结果保留；手机前三轮中的完整稳定指导→长缺测→恢复原证据仍保留。两端暂停停止相机，一次继续按原同意恢复新预览边界通过；原资格GET已实际完成但回复不可读取时，相机DOM／流／输入／正在练习均保留。模式转换仅客户端草稿；不是权威完整测量模式段、真机或精度验收。

0.2.7人工安排证据：`test_manual_practice.py` 7个原HTTP／SQLite案例、`test_manual_arrangements.cjs` 5个控制器案例，均全套子集。实际浏览器三次尝试、两次完整通过；首轮最后legacy检查的重复定位失败保留。末次 `actual-manual-practice-20261012-f67219e0` 原SQLite为0评估／1原人工计划／1独立practice；自报3为QA输入，confirmed_count及正式贡献null。明确确认默认未选、回到原练习不重复确认、结束回复不可读后刷新恢复原身份、原安排及进度不改。当时原自动路径托管477fb04d／实际APK资源358da890兼容通过，APK本地人工B01未接。

0.2.8本地人工安排：`care-local.test.cjs` 新增7个原local-api／Store案例覆盖原键／重开、必要确认／陪同、原提交失败、不可消除的不适、本人／原设置／备份校验、定义改变及最近训练不适；均为171全套子集。`verify_phone_manual_practice.cjs`实际包资源完整流程3尝试／2通过／1历史QA定位失败保留，末次6eabf152为0原作业／0自动计划／1人工安排／1独立已提交练习；录入和finish回复故障刷新、原暂停／返回、历史／备份／legacy通过，0 Python API。次数3仅QA输入，正式字段null。末次托管兼容7deb03c9和原本地CPU Worker自动路径966aff8d通过；JS171、Python155／2subtests及64保护内容／两尺寸几何通过。没有Qt、真机、多组或临床精度证明。

| 用例 | 现有证据／状态 | 尚需覆盖 |
| --- | --- | --- |
| F01 | 未完成；统一 snapshot 仍整页等待 | 局部加载／报告故障隔离 |
| F02 | 托管／APK 原路径不补头像／身高；Qt 原空身体档案采用已存安排跑通 | 全模块及真机缺资料 |
| F03 | 局部：预览有停止／返回；生命周期测试只有一申请 | 实际忽略授权＋允许非相机路径 |
| F04 | `test_live_lifecycle.cjs` 晚到流释放通过 | 真机权限与宿主生命周期 |
| F05 | 托管／APK资源原允许安排并行预览：真实黑JPEG／原模型准备失败，6秒后仍跟练，无新相机／旅程 | Qt、正式v2并行测量及真机 |
| F06 | 托管、APK 原 Store 及 Qt 原 SQLite 各自 B01：无合格评估、明确采用原安排后开始／暂停返回／同键结束；原自动门不放宽 | 资格未知自主草稿及三端完整执行器／真机 |
| F07 | 未改原测量规则 | 主动作与辅助质量的实际帧演示 |
| F08 | 原展示器1.5秒静默、无效角度 —／次数保留；两端真实短黑JPEG后跟练继续 | Qt／v2和目标手机 |
| F09 | 手机实际预览AUTO→GUIDED→AUTO，独立确认仍null；客户端转换留草稿，不跨来源累加 | 权威模式段、明确转折遮挡／完成参考和三端 |
| F10 | 手机实际长黑JPEG及恢复不重启旅程；静态建议、相机／计次规则不改；托管不稳定负结果保留 | 多次循环、Qt／v2与真机 |
| F11 | 保留原身份／跟踪策略 | 旁人入镜，不串人／不丢旅程 |
| F12 | 未改坐站算法 | 坐站实际跟练＋准备失败输入 |
| F13 | 未造膝角 | 康复深蹲真实输入与缺点降级 |
| F14 | 预览 cancel／generation 单元；Qt 已取消语音不加载可选麦克风／ASR，原 UI 取消链回归 | 统一音频及迟到 onend／物理音频全链 |
| F15 | 托管／APK 原预览暂停释放；Qt 原跟练暂停返回保持原身份、恢复先查资格、迟到请求不撤销结束 | 三端正式 pause/resume 控制、真机 |
| F16 | 隐藏停 preview；跟练暂停不补长 dt；实际 APK 资源调用原 offlinePause 保留输入 | 真机熄屏／进程回收／原生音频 |
| F17 | 结束的 practice 只读；新版资格查询不可续练 | v2 finalized／interrupted 关联新段 |
| F18 | 独立 self_count，confirmed=null；不改计划 | 实际 6／8／10 三来源组合 |
| F19 | 三端独立契约空 count 保持 null；Qt 普通结束立即填写区，不写完成目标 | 全部正式测量结束入口与真机 |
| F20 | practice 200 真 commit，不冒充 v2 202 | v2 finish／慢报告消费者 |
| F21 | 托管／APK 同键结束刷新；Qt 原 SQLite commit 后丢回复／同载荷重试 1 条记录，原库重开测试 | Qt 跨进程待结束 outbox、v2 与真机 |
| F22 | 草稿写失败有内存措辞，服务器可提交 | 实际存储故障完整客户端验收 |
| F23 | 尚未完成 | 双端容量不足与导出 |
| F24 | 托管／APK独立感受真实页面：后补／丢回复刷新／真实revision冲突／明确选择通过，null不补0；每旅程草稿 | Qt／v2反馈及全模块outbox／真机 |
| F25 | 三端 B01 保留相关停止事实；Qt 原安排／定义／必要陪同变更阻止继续但已有事实可结束保存 | v2、Qt 后补感受及下一项全链 |
| F26 | `test_upload_receipts.py`＋原录像实际 browser 1 POST／1 job | 真机弱网、客户端重开操作日志 |
| F27 | 未把报告失败重建为第二次评估 | 正式派生报告重建接口 |
| F28 | 同页面原 File／同意状态可复用 | 跨重开可达媒体引用与重新选择原件 |
| F29 | 旧回调 owner generation／页面节点隔离；Qt 错本人安排不返回名称／设置，独立请求错误不覆盖原场景 views，错误来源回复保留原待核对操作 | 全模块 outbox 与服务器切换 |
| F30 | 实际APK0.2.8原local-api／Store人工安排6eabf152及原CPU Worker自动路径966aff8d：开始→暂停／返回→结束丢回复→刷新／历史／备份，0 Python API；原自报与视觉／正式贡献分离 | 完全离线真机全旅程、熄屏／进程回收及其他动作 |
| F31 | preview 不称历史；APK PHONE_LOCAL、Qt qt-local-1 独立事实各归原存储，v2 默认关；Qt legacy 只关闭新入口 | 各端完整能力矩阵／fallback |
| F32 | 上传不锁导航；跟练返回保留输入通过真实 browser | 全模块非阻塞与迟到写回 |
| F33 | 后端拒绝另一 open journey；同事实结束幂等 | 同 ID 两窗口主动租约／接管 |
| F34 | 独立表不覆盖旧 schema | v2／跨条件可比性 UI |
| F35 | preview单帧在途；跟练原资格查询期间实际video DOM／流不重建；Qt原入口两组肩外展→原休息→下一动作→三组原回执／历史通过；休息不计练习，下一组丢回复不重复创建 | 手机／托管多组、慢推理压力、长时、实际设备p95 |
| F36 | 网页原两尺寸几何不变；Qt 61 内容原样／3 授权控制变化，首页／工作区 SHA 及按钮审计相同，新增页浅色／暗色 150% 审图 | 全页面、高对比／多屏／原生模态及真机 |

本轮专用证据：`android_offline/tests/care-local.test.cjs` 的7个独立 practice 案例、`test_product_ui.cjs` 的 History API 保留；`verify_phone_practice.cjs` 当前成功 run `actual-phone-practice-20261012-cf10b538`，`verify_practice_flow.cjs` 当前成功 run `actual-practice-20261012-4f0d91b7`。前者是实际 APK 页面／算法／本地存储，不是物理 Android；其 10 次为 QA 本人输入字段，不是观测数。

原始证据在忽略的 `.runtime/frontend_flow/20261012-u0/`、`20261012-u1-phone/` 与隔离 QA 输出中保留。公开文档不含私人原片、照片、逐帧数据、本人 ID、cookie 或配对码。完整 U2–U6 尚未通过，不能只用测试总数判断任务完成。
