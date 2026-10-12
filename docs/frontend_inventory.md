# 前端流程盘点（2026-10-12）

依据：桌面《安康前端流程优化实施任务书.md》。工作分支 `codex/frontend-flow-optimization`，基线 `05537bf51a16e2c839d0279dc606f4240d24befe`。这是分阶段实施盘点，不是全任务完成报告。

## 真实入口

| 端 | 入口与源代码 | 执行与保存 | 本轮范围 |
| --- | --- | --- | --- |
| Windows 正式产品 | `Start-Rehab.ps1` → 应用 `.venv` → `app.main` → ProductWindow／Runtime | 原宿主、SQLite、SceneController | 0.20.0；未改 Qt 控件、样式或执行器，完整流程接线待做 |
| 托管统一网页 | 正式首页 `mobile_rehab/static/unified.html`／`unified.js`；康复入口进入 `/capture?tab=plan` 等 | 当前共享宿主；统一白名单与原 SQLite | 保持五导航；全量 snapshot 的加载拆分待做 |
| 保留的动作页面 | `/capture` → `index.html`、`app.js`、`extensions.js`；`practice-flow.js`／`practice-feedback.js`／`practice-observation.js`／`observation-presenter.js` | 原录像执行器／预览／同库独立practice与感受版本 | 原安排跟练中可选用旁路预览，6秒／缺测宽容不改变原引擎；正式视觉关联待接 |
| 独立 Android | 打包源是 `mobile_rehab/static/`，不是旧 `android_offline/web/index.html`；本地 `local-api.js`、PhoneMotion／Worker／PhoneStore | PHONE_LOCAL 原本地库和媒体存储；无需 Python 服务 | APK0.2.6／code8：原开始／并行预览／暂停／结束／感受／刷新／历史实际验证，原备份保留类型；未真机安装 |
| 可选康复 v2 | `/api/rehab/v2/...`，默认关闭 | 独立 session／commit／反馈语义 | 未冒充旧 preview 或 practice；完整客户端适配仍待 |

本轮不合入远端整包，不改变 WebView origin、签名、权限或模型。电脑 8765／1396、相机和已有窗口不启停。独立 QA 服务只用随机 loopback 端口。

## 保护范围与现状

- 原图标、动作图片、CSS、字体、Qt UI 等 64 个已跟踪资源对 Git 基线核对：二进制逐字节、已知文本只容许 CRLF 与 LF 的差别。不能将文本的行尾差别说成原始 SHA 相同。
- 实际网页浅色基线为 390×844、1440×940 的动作／预览页面；前后按钮和视频的几何、字号对比相同。尚未完成三端全部页面、深色、高 DPI 与真机对比。
- 用户已有 exercise-guides README、图片、CSV、任务书和导入脚本不属于本轮提交；不以清理它们建立“干净”工作区。
- `/live` 删除不能产生训练历史。正式计划资格继续由原 `validate_automatic_use` 核对，缺合格评估不生成假计划。
- APK 原 `planProgress`、模型、阈值、规则和正式计划贡献不改。新增 `practice.js` 只处理原串行 Store 中的独立类型；按原 `LocalEngine.propose` 复核当前本人自动安排，不把独立记录塞回旧 job。
- 原评估结果进入训练后，query 路由保留训练返回入口；历史渲染函数不再遮蔽浏览器 History API。APK 视频元素先解析本人本地 Blob，不请求不存在的 Python 视频接口；切页释放对应 URL。

截图、原始 QA 回执和测试夹具仅在忽略目录／隔离 QA 目录保留，不公开私人录像、逐帧信息、身份标识、连接码或密钥。

独立感受接口新增当前revision与同键回执，原finish不变。每旅程小型恢复草稿独立存留，旧单指针兼容；这不是全模块outbox。历史打开已提交练习保持history query，评估／训练继续保持plan query。旧医疗执行器、Qt及v2尚未适配。

0.2.6实际预录相机路径：末次托管198／手机236个真实预览响应，手机稳定指导／缺测降级／恢复出现，托管未稳定接上。既有主要按钮文档位置、核对时video节点／媒体流保持；无普通缺测弹窗或相机自动重启。当前可选相机仍需本次隐私同意，不把6秒预算当授权或资格替代。预览次数仅内存、客户端转换仅草稿元数据，不称权威视觉保存。源码与APK同份资源，原型和原规则未换；物理Android、三端完整覆盖仍待。
