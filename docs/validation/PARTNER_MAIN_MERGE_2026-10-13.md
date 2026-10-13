# 伙伴 main 与本机前端流程合并验收

日期：2026-10-13，Asia/Shanghai。目标分支 `codex/frontend-flow-optimization`；本机基准 `5599e9b7ae7144f20edd2d90355f64dde1d403c3`；伙伴 main 固定为 `48e94e58ccf260bd560f6ed4c67731e58e347380`。本轮是合并及兼容验证，不是完整前端任务书、全产品或临床准确率验收。

## 合并内容与取舍

| 伙伴提交 | 保留的改动 |
| --- | --- |
| dbee11a | ProductAgent模块注册／查询／导航，照护操作显式确认及回执 |
| b78f674 | 伙伴已有main合并历史，保留作者与父节点，不改写历史 |
| efeef75 | Windows pythonw重建Node桥接时隔离stderr，不继承不兼容日志句柄 |
| 4990b88 | 普通DeepSeek多轮聊天、可信来源上下文、隐私／失败降级和真实来源显示 |
| 8e79bce | AndroidKeyStore加密本机配置、原生HTTPS、手机康复只读宿主、备份信任保护 |
| 6b293ed | 原黑箱诊断／QA工具和真实失败记录，作为历史而非本轮验收 |
| 48e94e5 | 他人姓名／朋友／引用／示例不误写本人健康事实，查询同义词完善 |

9个冲突文件：AndroidManifest.xml、package.json、package-lock.json、build.ps1、prepare_assets.py、local-api.js、test_packaging.py、HANDOFF.md、docs/README.md。

- 加载器同时保留原PhonePractice与新增PhoneDeepSeek／共享policy；local-api同时保留原练习请求、照护端口和新增模型／只读宿主工厂，未以整文件选择一侧覆盖另一侧。
- 包验证同时保留原指导音频、正式跟练相机、UI锁及本地核心检查，并补共同元数据／加载顺序／原生桥接检查。build.ps1使用伙伴的manifest版本命名，避免硬编码旧包名。
- HANDOFF保留双方全部既有章节，新合并状态置顶。原桌面任务书及剩余清单不改写或宣称完成。
- 产品版本0.23.2；APK0.3.2 / code32；三个JSON／manifest元数据统一。code32高于本分支旧code18和已知另一发布code31，包名／证书保持。没有合并云端分支，编号不代表其功能进入本分支。
- 保留当前页面布局及动作流程，只接纳伙伴本身提交的管家确认／导航与来源显示；没有额外视觉重设计。不修改模型、训练剂量、资格、临床阈值或患者数据。

## 实际执行

所有QA原始输出保存在本机私有 `D:/RehabFrontendFlowVerification/partner-merge-20261013-01/`。隔离TEST档案／SQLite、新浏览器origin及回环随机端口；未连接正常数据库、用户物理摄像头、用户麦克风或付费模型。原片、完整回执、cookie、配对码、人物画面和数据库不提交。

| 检查 | 本轮结果 | 证据与限制 |
| --- | --- | --- |
| Agent原CI | typecheck／bridge build／TS481／产品20／security通过 | `agent-ci.log`；不是481项人体测试 |
| 模型与产品CJS全集 | 28通过、0失败 | `agent-models.log`；包含上述产品20，不能相加计48；模型请求使用测试传输，不调用真实DeepSeek |
| 网页与安卓JS | 304通过、0失败 | `js.log`；包括原跟练／formal-practice-camera和新增安卓DeepSeek逻辑 |
| 手机Python及实际APK包装 | 188通过＋2subtests、0失败 | `mobile-python.log/xml`；11警告：既有Starlette弃用和pytest旧临时目录清理告警；不是全Qt／全后端重新验收 |
| 桌面相关回归 | 105通过、2跳过、0失败 | `desktop.log/xml`；9个旧临时目录清理警告。两个embedded_plan native modal-lock用例要求Windows原生平台，在offscreen下跳过，不能算通过 |
| 健康归属HTTP | 构建后全新24／24通过 | `health-http-02/results.json`；12条陌生主体／引用原话×空库与已有本人真实QA记录两种状态，每条停止／独立重开，未误增／误删 |
| 管家实际双端UI | 网页12流程、0页面错误；Qt4截图 | `agent-ui/results.json`及截图；原ProductBackend／Node／DailyStore，确认前不写药物状态，确认后仅1条实际保存／审计；含取消／刷新恢复／导航／来源切换，未启动摄像头 |
| 原正式跟练相机旁路 | 1尝试／1完整；390×844 | `formal-browser/result.json`；原YOLO处理6帧，自动0／无基线，自报10为显式QA填写，confirmed／贡献null、正式进度0；practice和visual分别COMMITTED，感受null，1次创建／2次同载荷关联、暂停刷新不重开相机、两个结束丢回复后找回，0页面错误／API5xx |
| APK资源本地多组流程 | 1尝试／1完整；4组／2旅程 | `phone-browser/result.json`；原Store／路由，QA自报3／2／1／null分开，组间休息和下一项支持确认、丢回复刷新、历史／备份／legacy保持；前置动作是明确TEST标量夹具，非人体摄像头结果；0 Python／云 API |
| APK资源原录像本地分析 | 1尝试／1完整；CPU Worker识别3次 | `phone-worker/result.json`；原`E:/game/test video/肩外展.mp4`，有效覆盖0.9606299186765038，覆盖不是准确率；原本地Store保存1录像结果与1独立跟练记录，自报10不冒充自动次数，暂停／刷新／历史／备份通过，0 Python／云 API／页面错误 |

Qt亮／暗640×480、800×600确认窗口和手机390×844确认弹窗截图已实际审看，标签／按钮可见，无明显裁切。网页768×1024深色图也已审看。本轮没有以构建通过替代这些截图，但仍不是目标手机或系统DPI实测。

复现命令入口：Agent目录`npm run ci`与`node --test tests/*.test.cjs`；根目录`node --test mobile_rehab/tests/*.cjs android_offline/tests/*.test.cjs`、原`.venv/Scripts/python.exe -m pytest mobile_rehab/tests android_offline/tests/test_packaging.py`；桌面定向覆盖product_window、care_controls、conversation_status、deepseek_developer、assistant、navigation、recovery、rehab_focus、plan_modality和三份Qt跟练／组流程测试。实际HTTP用`tools/qa/health_attribution_fix_blackbox.py`，实际UI用`tools/qa/agent-ui-acceptance.py`与`tools/frontend_flow/verify_formal_practice_camera.cjs`、`verify_phone_sequence.cjs`、`verify_phone_practice.cjs`，均使用上述新输出目录。

## 原始失败与启动顺序

首次`health-http`在原TS桥接生成物重建完成前并行启动，第一条“张三今天血糖9.5”误记本人，命令退出1。该测试开始01:08:51Z、结束01:08:54Z；本次生成的`.bridge-build/engine/understanding.js`写入09:09:06+08，晚于该失败。未删日志、未放宽断言、未修改已失败的TEST库。完成原bridge build后，在新目录`health-http-02`重跑完整24项及逐项重开，全部通过。以后合并后的HTTP／Qt验证应等bridge build完成再启动。原Start-Rehab已先构建bridge再打开产品，本轮未修改该入口。

## 安装包与保护范围

沿原`android_offline/tools/build.ps1`完成构建，日志`apk-build.log`。保留原Java8选项及deprecated编译警告，不称零警告。实际aapt badging核对：包名`cn.tele.rehabilitation.offline`、versionName0.3.2、code32、minSDK29、targetSDK35。

- 新包：`android_offline/dist/tele-rehabilitation-mobile-0.3.2.apk`，28166056字节；SHA256 `C92610BEDB54DBF161ED41E0F6BE9E1B7DE7E9CFDCDB866F1FC3D907745E4BDF`。
- 原v3签名验证通过，证书SHA256 `607edd7dc1df261e52fa2fe35ea6391e1ce77cbcebc315fea80dd815bac1a5d8`不变。
- 旧0.2.16包未覆盖，SHA256仍为 `8B7A3C7B628AF01764D9F095227DDD987EFE3CA2E43A3F1CB0B19859B293F31F`。
- 原肩片SHA256前后为`97a9fa1b9f06de6482c06c109f40bc4e6e1681f53dde6fd7f478b5ac59405e0d`；预录相机副本为`91fdc03604337e7f9f239cace8435be603c9dd4b05e5e6235b12f70005136ea1`，均不改。
- 开工279份未跟踪用户文件逐项SHA不变且未暂存；用户动作指南README的4行修改及hash保持，未捎入本次提交。原模型／环境／数据／日志仍遵循gitignore。

提交并推送当前前端分支，核对远端SHA与本地一致；main仅读取，不强推、不替换。完成后沿原`New-RehabDesktopShortcut.ps1`更新桌面“安康康复（最新版本）”Git描述，仍指当前仓库Start-Rehab和本机已验证PySide6 6.11.2的`.venv/Scripts/pythonw.exe`。不关闭用户尚未保存的窗口，不重启8765／1396或打开相机。

## 未测与后续

未安装Redmi／模拟器，未实测AndroidKeyStore重开、覆盖升级、真实麦克风／扬声器、联网DeepSeek及系统性能；本轮仅构建原生代码、验证包内容／签名和本地浏览器执行器。未将伙伴其他电脑的模拟器或付费请求结果当本机验收。PHONE_LOCAL不冒充托管正式能力，不自动同步电脑数据库。

原正式相机验证前置评估使用明示TEST几何合同，不是人体资格；没有产生新的合格人体评估证据。权威mode_segments、跨进程outbox、全模块持久媒体／跨窗口租约、完整音频、三重点动作真人及真机性能等仍按剩余工作专项清单处理。本轮合并不清零历史未完成项。
