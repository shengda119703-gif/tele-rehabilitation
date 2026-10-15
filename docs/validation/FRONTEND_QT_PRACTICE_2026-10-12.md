# Qt 已有安排单组跟练：本机验证（2026-10-12）

范围是桌面《安康前端流程优化实施任务书.md》的原 Qt 入口、独立 B01／B02、暂停／结束／原历史接线。不是 U0–U6 全部完成，也不是动作计次、治疗效果、手机真机或物理摄像头验收。

## 实际改变与保留

在 c76e90e 的 `codex/frontend-flow-optimization` 上实现。原 ProductWindow／ProductRehabWindow／训练计划库／Runtime／Storage._call 不换栈、不新增患者库。本人原人工安排有独立执行政策，不再把“缺合格自动评估”当作全部跟练不可用；当前本人、ACTIVE revision、原定义与设置、采用／支撑／必要陪同、已记录停止条件仍检查。

记录与原测量 session 分离；未填次数和初次感受为 null，前台页面时间不是观测保持。原自动安排规则、正式计划贡献、原模型、阈值、算法、Agent 三工具及家庭共享不改。原语音输入只把取消检查提前：已经取消就不加载可选音频组件，不打开麦克风／识别或提交文字。

## 用户从哪个入口使用

1. 桌面“安康康复（最新版本）”→康复→准备／继续训练，进入原训练计划库；原工作区训练计划入口也可用。
2. 选择本人的原人工安排→使用所选项目；确认采用、支撑及原安排需要的陪同，开始跟练。无需摄像头或合格评估前置。
3. 原生暂停／返回停止本地节奏，继续先核对原资格，不重新选动作或重复采用。长 GUI 空白不补运动。
4. 结束立即显示本组填写区；仅明确填写才有自报次数／感受，普通结束不等于目标完成。保存以原 SQLite commit 为准。
5. 原康复历史和统一历史可查本人独立记录；不能套用旧 ROM 报告或改善趋势。查看旧记录不替换当前暂停控制器。

目前只记录本组（set_index=1），不是完整多组／整份计划执行。回退用新进程环境 `ANKANG_REHAB_EXPERIENCE=legacy` 恢复原计划库新开始路径；已有独立历史与原键结束继续可读，不删事实、不切换写入归属。

## 原 Qt／Runtime／SQLite 实际完整流程

脚本 `tools/frontend_flow/verify_qt_practice.py` 每次创建独立 D 盘 TEST 目录。原产品档案 API 创建空 QA 档案，原计划库保存明确 QA 已有安排，不伪造评估。不读取正常患者库或开启相机／HTTP。实际原生 Qt 事件（含键盘 Space）、Runtime 队列与 SQLite commit 均执行，不用 mock 代替这条完整流程。

| 最新运行 | 条件 | 结果 |
| --- | --- | --- |
| actual-qt-practice-3624a552 | offscreen Qt；浅色；1440×940；100% | 原入口→采用→跟练→暂停返回继续→结束回复丢失→原键重试→原历史及统一历史；通过 |
| actual-qt-practice-cd7fd2d5 | offscreen Qt；暗色；1180×780；150% | 同一完整链；通过 |

每个成功 run 原库为 1 份原人工安排、0 测量 session、1 独立 COMMITTED practice；自报 3 是明确 QA 输入，不是人体完成量。confirmed_count／formal_plan_contribution 均 null；疼痛／疲劳仍 null。原安排 revision 不变，Runtime camera.worker 和 controller.session 都未启动。故障注入只丢一次真实 finish 回复，SQLite 实际提交；同一原操作／载荷返回原记录，不能多一条事实。

原始截图／result.json／TEST 库保留于 `D:\RehabFrontendFlowVerification\qt-practice-20261012-delivery-light\actual-qt-practice-3624a552` 与对应 delivery-dark／cd7fd2d5；不上传库、私人 ID 或原录像。10 次已留 result 的完整流程尝试共 7 通过、3 失败，不只报最后两次：

- 411b90f3：首轮 QA 未先建立原产品档案／字体，入口等待失败；完善隔离 QA 初始化后重跑，原失败不覆盖。
- f4c096ed／6e7d13b6：流程已到保存，历史预期重新查询时复用了已提交的当前 dialog，等待新历史窗口失败；限定只有未结束当前记录复用，已提交记录重新走原查询，原严格断言不改。
- 8e253458／e9dc768c／797f548c／1d282721／b74d2dc7 与最后两次通过，全部原件保留。

普通点击 dispatch 返回在最新两轮最大约 70.08ms，只是本机 offscreen 事件处理观测，不是目标设备可见反馈 p95≤200ms 证明；UI 没实际真人运动，不报告人体准确率或自动测量成功率。

## 状态／存储／迟到回复

`tests/test_qt_guided_practice.py` 使用真实原存储，覆盖无评估、原键一致、必要输入／陪同、本人／来源分离、安排归档／定义变化、已有停止条件、新安排不能消掉不适、草稿版本、严格 count／elapsed 类型、只读 UI 类型与真实 Runtime 保存／库重开。

最后两项还核对错误本人安排不返回名称／设置，独立请求错误不覆盖原场景。Runtime 的场景 `_view` 使用单独 views 队列；最终断言用真实 `_view` 调用监测，不以 messages 队列为空代替证据。最终 core／UI 专项合计32通过，是全套子集。

`tests/test_qt_guided_practice_ui.py` 最后 12 项原生控件 TEST 覆盖暂停返回、30 秒 GUI 空白不计时、结束立即响应、提交后回复丢失同载荷、不适／归档后仍可保存、迟到恢复成功及错误不能撤销结束、隐藏后晚到开始只恢复 PAUSED、错误来源不消耗当前请求、历史不替换当前控制器、legacy 及原计划库等待／未知资格。这里的 PassiveRuntime 回复是明确 TEST 控制边界，不把它替代上面的真实执行器流程。

原 `test_native_voice.py` 新增取消前可选导入保护，原 UI 取消及草稿测试一起回归；本机没有 sounddevice，3 个依赖麦克风的测试跳过，不声称原生录音或中文 ASR 已验收。

## 原回归与失败保留

使用原 `.venv` Python 3.13.12、原 `scripts/check_project.py`，TEMP／TMP 指向 D 盘隔离目录。执行不启动用户 8765／1396、摄像头或关闭已有窗口。

| 批次证据 | 结果与范围 |
| --- | --- |
| qt-practice-full-regression-20261012-01 | core 1069 通过／1 失败／2 跳过／4 subtests；已取消录音先导入 sounddevice 导致失败，后续批次原 runner 正常停止；原日志保留 |
| qt-practice-full-regression-20261012-02 | 原 13 个全部批次通过：core1070／UI479／集成228，5 跳过／4 subtests；后续最后两个 UI 边界补丁不由这轮证明 |
| qt-practice-full-regression-20261012-03 | 原 13 批次通过：core1070／UI479／集成228，5 跳过／4 subtests；UI 导入在最后两个补丁前，所以最终 UI 另重跑下一行 |
| qt-practice-final-ui-20261012-04 | 最后源码的全部 36 个 UI 文件：481 通过／2 原生 Windows 模态跳过；新增 12 专项是其子集 |
| qt-practice-final-core-20261012-05 | 最后两个生产边界补丁后 core1072／3跳过／4subtests通过；单项断言随后加强，最终重跑下一行 |
| qt-practice-final-core-20261012-06 | 最终源码及加强断言的全部53个core文件：1072通过／3跳过／4subtests；4条原pytest旧临时目录清理警告保留，未扩大删除 |

core 的 3 跳过是可选麦克风；UI 的 2 跳过来自 offscreen 无原生窗口模态能力。21 关节动作集成、180 可选点组件、原 Runtime／source／vision／双摄／guided／model paths／quiet 合计 228 项是原集成分区，不代表实体相机或真人精度。最终core用06，集成沿用03，UI用04替换479；不重复累计多轮，也不将subtests算作独立患者。06警告是C盘既有pytest目录清理失败；本轮没有清掉这些目录。完整三个端的物理流程仍未完成。

兼容命令在原仓库根运行 `node --test mobile_rehab/tests/*.cjs android_offline/tests/*.test.cjs`：171通过，日志在release2／js-compatibility.log；原手机Python和packaging合计155通过／2subtests，1条原Starlette依赖弃用警告，release2／mobile-compatibility.xml保留。安卓／网页源码、本机Python环境和模型未改。APK0.2.8为28103992字节，SHA `0B568BF97C8903603A4C7387163637BD3458AB0D2DF28E1838A5C4AFEE19669E` 不变，未重新构建或安装。

## 视觉前后核对

基线仍是 05537bf51a16e2c839d0279dc606f4240d24befe，不重建保护清单。原 64 文件中 61 内容不变；product_rehab／product_window／product_completion 是授权控制接线，其他原方法 AST 不变。新 guided_practice UI 没有局部 QSS、QPalette／颜色／字体重定义、图标或固定 geometry。`verify_qt_visual_contract.py` 如实输出 `all_64_contents_unchanged=false`，不是为了让旧全64检查变绿。

原 `tools/validate_product_visual.py --phase fluent-v1` 同 1440×940／浅色／100%／固定 TEST 数据在 baseline 与 final-baseline 两个目录执行：button-audit.json／observations.json 内容相同，原首页 SHA `FA72EA978741D008C494D8510FBD74A8E9677B2ED9D96DE5A245A1AC047E96AD`、康复工作区 SHA `368ED42D3005E4EC22BC6F841930C20069AF02C3E8A19F1D976F89468D8D0CE7` 前后一致。已审看最终新增页确认、结束、保存、原历史和统一历史的浅色／暗色150%；原生键盘焦点和未填写值可见。早期新 spinbox 步进区裁切仅改该新增字段原生 NoButtons，保留键盘和直接输入，没有动全局样式。

尚未完成高对比／125%／200%／多屏、原生 Windows 模态和目标手机视觉验收。原图标、图片、字体、颜色与主要导航保留；用户新增 exercise-guides 素材、README、CSV、任务书和导入脚本不加入本轮提交。

## 剩余完整目标

多组、原组间休息与下一项；正式视觉关联与权威模式段；Qt 后补反馈、跨进程待结束载荷 outbox 和双存储失败导出；全模块独立加载；统一指导／音频取消；跨窗口主动租约；v2 finish 202／commit 全消费者；肩外展／坐站／康复深蹲缺测真实流程与手机真机持续运行。当前单组成功不替换或缩小这些要求，goal_complete 保持 false。
