# 前端流程盘点（2026-10-12）

依据：桌面《安康前端流程优化实施任务书.md》。工作分支 `codex/frontend-flow-optimization`，基线 `05537bf51a16e2c839d0279dc606f4240d24befe`。这是分阶段实施盘点，不是全任务完成报告。

## 真实入口

当前增量为0.2.12：原 `/capture` 的实时预览、已有安排旁路指导和已启用v2正式评估，统一经 `guidance-scheduler.js` 输出提示／语音；旧独立 speechSynthesis 调用已移入唯一 AudioPort。普通候选容量1、6秒间隔、同句10秒、缺测建议同旅程同动作一次；当前来源／世代／相位／期限失效会停止真实输出，不等待下一帧。APK沿原桥增加选用的已安装离线中文TTS与原生暂停／销毁停止；没有新增敏感权限、联网语音或自动下载。当前没有覆盖Qt音频、独立TS浏览器适配器及全程序全部音频模块；不能称U4全部完成。实际输入和失败分母见[指导验收](validation/FRONTEND_GUIDANCE_SCHEDULER_2026-10-12.md)。

0.2.11已接原托管动作详情条件性“实时测量并保存”，`formal-session.js`／`formal-measurement.js`接原v2创建、JPEG、控制、202及canonical commit。仅宿主已明确启用v2时出现；正常用户服务仍默认关闭。原历史位置分别读正式事实和本机待核对草稿，不套旧summary；legacy仍可读原事实及核对原操作。独立APK没有该托管能力，不访问Python。完整训练旁路视觉关联／分段和三端验收仍未完成。

| 端 | 入口与源代码 | 执行与保存 | 本轮范围 |
| --- | --- | --- | --- |
| Windows 正式产品 | `Start-Rehab.ps1` → 应用 `.venv` → `app.main` → ProductWindow／Runtime | 原宿主、SQLite、SceneController；独立 Qt practice 仍用原 writer | 0.20.0；原康复／计划库接本人已有安排，多组、休息、下一动作、暂停返回及每组原历史；完整三端流程仍待 |
| 托管统一网页 | 正式首页 `mobile_rehab/static/unified.html`／`unified.js`；康复入口进入 `/capture?tab=plan` 等 | 当前共享宿主；统一白名单与原 SQLite | 保持五导航；全量 snapshot 的加载拆分待做 |
| 保留的动作页面 | `/capture` → `index.html`、`app.js`、`extensions.js`；`practice-flow.js`／`practice-feedback.js`／`practice-observation.js`／`observation-presenter.js`／`manual-arrangements.js` | 原录像执行器／预览／同库独立practice与感受版本 | 原安排并行预览；本人原人工计划库B01；schema2多组／原休息／下一动作及独立历史已接；正式视觉关联待接 |
| 独立 Android | 打包源是 `mobile_rehab/static/`，不是旧 `android_offline/web/index.html`；本地 `local-api.js`、PhoneMotion／Worker／PhoneStore；GuidanceAudio沿原桥 | PHONE_LOCAL 原本地库和媒体存储；无需 Python 服务 | APK0.2.12／code14：原CPU Worker、旁路预览、原规则安排、暂停／丢回复刷新／反馈／历史备份重验；0 Python请求。新增离线TTS经原SDK编译、打包和桥接单测，未真机安装或验证实际声音 |
| 可选康复 v2 | `/api/rehab/v2/...`，默认关闭；已启用宿主的原动作详情／历史位置 | 独立原 session／202／canonical commit，不与旧事实库互换 | 原肩外展录像实际创建／帧／暂停恢复／保存／历史通过，未建立基线、0次如实保存；正式训练关联／反馈UI及三重点动作仍待 |

本轮不合入远端整包，不改变 WebView origin、签名、权限或模型。电脑 8765／1396、相机和已有窗口不启停。独立 QA 服务只用随机 loopback 端口。

## 保护范围与现状

本增量相对8d9f481复查65个已跟踪保护文件，内容未变（文本仅允许CRLF差异），两尺寸原预览几何／字号未变；新增测量结果和原历史截图已审。它不覆盖用户约280张未跟踪动作图片，也不替代历史Qt原基线／3个授权控制模块的报告。当前证据见[正式测量增量](validation/FRONTEND_FORMAL_MEASUREMENT_2026-10-12.md)。

- 原 64 个保护文件中 61 个内容不变；3 个 Qt 控制模块是本任务明确授权的事件／状态／历史接线变化，非授权方法 AST 不变。新界面复用原 Qt 控件与原主题，无新 QSS／字体／图标。`verify_qt_visual_contract.py` 明确报告并非全部 64 个文件原样；没有重置原基线。文本只容许 CRLF 差别，不称原始 SHA 全相同。
- Qt 浅色 1440×940／100% 的原首页、助手、康复前后 button-audit 与 observations 内容相同；首页和康复工作区截图 SHA 相同。新增跟练页在浅色 100%／暗色 150% 实际运行并审图；不是 Windows 原生窗口模态、高对比、多屏或手机真机验收。
- 实际网页浅色基线为 390×844、1440×940 的动作／预览页面；前后按钮和视频的几何、字号对比相同。尚未完成三端全部页面、深色、高 DPI 与真机对比。
- 用户已有 exercise-guides README、图片、CSV、任务书和导入脚本不属于本轮提交；不以清理它们建立“干净”工作区。
- `/live` 删除不能产生训练历史。正式计划资格继续由原 `validate_automatic_use` 核对，缺合格评估不生成假计划。
- APK 原 `planProgress`、模型、阈值、规则和正式计划贡献不改。新增 `practice.js` 只处理原串行 Store 中的独立类型；按原 `LocalEngine.propose` 复核当前本人自动安排，不把独立记录塞回旧 job。
- 原评估结果进入训练后，query 路由保留训练返回入口；历史渲染函数不再遮蔽浏览器 History API。APK 视频元素先解析本人本地 Blob，不请求不存在的 Python 视频接口；切页释放对应 URL。

截图、原始 QA 回执和测试夹具仅在忽略目录／隔离 QA 目录保留，不公开私人录像、逐帧信息、身份标识、连接码或密钥。

独立感受接口新增当前revision与同键回执，原finish不变。每旅程小型恢复草稿独立存留，旧单指针兼容；这不是全模块outbox。历史打开已提交练习保持history query，评估／训练继续保持plan query。Qt 初次结束感受可留空，但独立后补／修改尚未接，v2 仍未适配。

0.2.6实际预录相机路径：末次托管200／手机235个真实预览响应，手机稳定指导出现，此前手机完整稳定指导／缺测降级／恢复原轨迹保留，托管未稳定接上。既有主要按钮文档位置、核对时video节点／媒体流保持；无普通缺测弹窗或相机自动重启。当前可选相机仍需本次隐私同意，不把6秒预算当授权或资格替代。预览次数仅内存、客户端转换仅草稿元数据，不称权威视觉保存。原型和原规则未换；物理Android、三端完整覆盖仍待。

0.2.7新增入口为托管“我的训练→已有人工安排→使用已有安排”。只读取本人的原REPLAY_FILE／SELF_USE人工计划，不新增或改剂量；当前确认／支撑及必要陪同通过原作用域政策核对。自动资格与正式计划贡献不改。实际原库0评估／1人工计划→1独立跟练完成保存／刷新／历史；这是明确TEST安排及QA次数，不是专业授权或人体试验。当时APK本地B01和Qt未接，保留历史时点。

0.2.8本地“康复→我的训练→录入已有安排／使用已有安排”使用原PhoneStore独立manualArrangements／practices。录入可选，原剂量明确输入且默认空；原键保存、未知回复刷新核对、返回不重复确认、原历史和备份通过。实际末次6eabf152为0原作业／0自动计划／1人工安排／1独立记录，自报3为QA输入，正式字段null；原自动Worker兼容966aff8d仍通过，0 Python请求。这是 c76e90e 发布时点的64内容不变证据；d996f64只更新Qt时未重打APK，不能将当时边界当作当前状态。

当前0.2.10托管与PHONE_LOCAL组序列各走原writer，休息、下一组、下一动作与原身份恢复已接；普通结束不填写完成量，各组自报只作独立导航。实际托管8／8完整、本地资源5／5完整，最终两尺寸审图；本地自动两动作资格来自明确TEST标量经原引擎，不是视觉观测。原始肩外展实际CPU Worker另行重验通过，短版0次负结果保留。正式视觉关联／权威分段、全模块outbox／租约、真机仍待。见[本轮验证](validation/FRONTEND_WEB_PHONE_SEQUENCE_2026-10-12.md)。

## 当前 Qt 已有安排路径

“康复→准备／继续训练→原训练计划库→使用所选项目”，或原工作区的训练计划入口。当前原人工安排由原库读取，不需要合格评估或相机 READY；采用、支撑、必要陪同仍明确确认且默认不勾选。未知／不适／安排改变不是普通缺测。当前原自动安排仍走原自动入口和规则。

`app/guided_practice.py` 的 `qt-local-1` 与 `qt-saved-arrangement-guided-1` 绑定原本人／输入种类／使用情境；不是托管或 PHONE_LOCAL 身份。Qt 直接走原 Runtime 命令和 Storage._call，不引入 HTTP／DOM 或第二个患者库。原历史与统一历史只读独立类型，不能当评估、自动确认或正式计划贡献。

f3dc32e的单组基础继续兼容；当前Qt多组沿冻结原安排推进，各组独立原回执、同一旅程，原休息后由本人继续，下一动作重查支撑及陪同。实际两组肩外展＋一组坐位膝屈伸及历史五次通过。跨进程待结束／继续outbox、后补感受、统一音频／租约及正式视觉关联仍未完成；当前手机／托管多组已接，仍不能称完整三端目标完成。`ANKANG_REHAB_EXPERIENCE=legacy`在新进程恢复原计划库新开始入口，已有独立历史与结束仍可读，下一组新开始隐藏，不在运行中换provider。见[单组基础](validation/FRONTEND_QT_PRACTICE_2026-10-12.md)及[多组本机记录](validation/FRONTEND_QT_SEQUENCE_2026-10-12.md)。
