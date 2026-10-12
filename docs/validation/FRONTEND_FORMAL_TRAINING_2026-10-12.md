# 原正式计划到实时训练：本机验证

日期2026-10-12；基于已上传`f2e185a`，分支`codex/frontend-flow-optimization`。依据桌面《安康前端流程优化实施任务书.md》继续U1／U3／局部U5，完整U0–U6和F01–F36仍未完成。当前不重训模型、不改变处方或原评估合格规则、不重设计页面。

## 本轮接线

原训练页的旧计划、人工安排与v2正式计划独立加载。已启用宿主的`formal-training.js`读取原计划清单、原进度和条目支持，开始时复核版本／next_key／实际来源，明确采用原本人安排；确需陪同才确认陪同。原设置仅在恢复binding中冻结并核对，创建请求不带客户端剂量覆盖。

共享原实时测量页面、SessionAdapter、JPEG、控制、finish、canonical commit和独立feedback；恢复按原训练plan／entry／operation区分评估草稿。创建或结束回复丢失仍用原不可变键／载荷核对，刷新不开相机、保留原采用确认，旧计划变更不能阻止原结束操作查回。原RESTING与plan_complete消费原组规则，不用UI时间制造自动组完成。原历史显示对应计划／版本／条目／冻结剂量与原自动完成组数，返回安排时读真实进度。

不填感受也先保存已经发生的训练。原规则确需上一感受时，原安排可进入上一记录补填；不能借新计划清除旧阻止。原program_progress的一条固定中文原因仅精确映射显示，资格仍来自完整原结构，未知错误不猜执行许可。

恢复时原正式订阅可以同步离开旧计划页；现先捕获原区域再挂订阅，迟到成功／失败均不访问已经移除的DOM。实际浏览器发现这项竞态，不能由仅Node通过推断页面无错。未知创建／核对中的状态行和大字提示均不提前宣称后端已暂停。

## 输入与真实性边界

- 正计划入口的合格评估来源为明确TEST几何合同夹具，经原JPEG队列、协议、writer和BackendPlans生成；没有直接改SQL，也没有改产品资格。夹具限私有隔离目录，评估标识明确不是人体观察／疾病处方。
- 在浏览器实际训练开始前，几何provider已恢复原值。训练使用获准肩外展原片的预录相机输入、真实原YOLO／HTTP／SQLite；正夹具只证明接线，不证明真人合格评估、精度或训练达标。
- 独立无夹具验证同一原片的实际正式评估为22帧、0次、无基线；原计划创建保持409 `committed_observable_v2_assessment_required`、清单空。不用正夹具掩盖这一真实资格结果。
- 最后APK资源使用原CPU Worker和PhoneStore分析原片，3视觉次数、有效画面占比0.9606299186765038（不是准确率）；QA明确自报10独立保存，confirmed_count／正式贡献null，正式进度0，不与3相加。感受也是明确QA编辑，不是录像测得的患者感受。
- 原MP4和预录Y4M指纹不变；原片、本人编号、cookie、私有库、逐帧点、截图和录屏不上传仓库。所有实际流程在独立随机loopback端口，不启动用户相机或改用户8765／1396服务。

## 实际尝试与最终结果

原正式训练验证共13次：08／09／11／12／13共5次完整；01–07和10共8次未完整，失败原件均保留。不要把失败或几何合格夹具算作人体自动测量成功。

| 尝试 | 实际结果与处理 |
| --- | --- |
| 01 | 创建未核对先显示暂停，QA过早拿到null身份；修复未知／busy显示和核对完成后的刷新 |
| 02 | 刷新后QA丢finish回复注入没作用于恢复的adapter；实际已保存，脚本等待失败；改为对恢复的原请求注入回复故障 |
| 03 | 独立旧计划尚未加载，QA提前断言空区；等待原局部结果，不让新正式区域依赖旧计划 |
| 04 | 原进度固定中文原因未映射，QA预期显示失败；仅增精确显示及上一记录入口，不从文字推断资格 |
| 05 | 原正常progress.blocked为空字符串，QA错误预期null；按原契约核对，不改进度 |
| 06／07 | 实际两个null-DOM异常；07补完整浏览器调用栈定位app计划区域捕获时序；修复生产订阅后重验，错误断言仍要求空 |
| 08／09 | 手机／电脑完整通过，最终前一UI补丁时点 |
| 10 | 录屏新页面创建前缺测试编码组件；补装Playwright FFmpeg及其Winldd到本机工具缓存，未改应用依赖 |
| 11 | 录屏流程完整通过；后续大字待核对补丁前时点 |
| 12／13 | 最后源码手机／电脑完整通过；12同时生成实际操作WebM录屏 |

| 最后证据（私有目录内名称） | 结果 |
| --- | --- |
| `formal-training-20261012-12`，390×844 | 1原训练、5处理帧、0自动次／无基线；原3次×2组不改；创建2POST同键同载荷；canonical一致、刷新不开相机、结束后原历史、原独立感受补填、legacy读取 |
| `formal-training-20261012-13`，1440×940 | 同一流程1原训练、6处理帧、0次／无基线；浏览器错误与API5xx均空 |
| `formal-training-20261012-assessment-02` | 最后源码实际评估原肩片22帧／0次／无基线，原否资格409；创建／finish回复丢失、反馈冲突／同值收敛兼容；01／02两次完整 |
| `formal-training-20261012-phone-02` | 最后包资源实际CPU Worker／本地Store，1job、1独立practice、0 Python API，结束丢回复刷新、历史备份、原反馈三独立版本通过 |
| `formal-training-20261012-12/PRIVATE-flow-recording` | 实际浏览器操作录屏，390×844、7.64秒；包含TEST合同安排及授权原片，只作私有流程验证，不冒充患者或临床成功宣传素材 |

最后源码／构建05后JS全套274通过、0失败，日志`formal-training-20261012-js-04.stdout.log`。手机Python／实际APK包装173通过、2subtests、1原Starlette弃用警告（`formal-training-20261012-python-02.xml`）；原session／progress／BackendPlans／async_finish相关52通过、26subtests、1原依赖警告（`formal-training-20261012-backend-01.xml`），不是后端全套。各专项属于全套子集，不叠加数量或称医学准确率。Qt本轮源码不变，没有重新宣称Qt全套结果。

65已跟踪保护内容相对f2e185a未变；原390×844及1440×940预览的按钮／视频／字体几何保持，`formal-training-20261012-visual-contract-03.json`。实际训练页和历史截图由主代理审查；沿用原卡片／输入／按钮，未新增CSS／图标／主题。长内容使用原滚动／固定导航，不称全产品或真机视觉验收；用户未跟踪动作素材不在保护文件分母中。

## 构建、发布与回退

本轮5次原本机构建日志保留，最后05是交付资源。APK0.2.14／code16、28137155字节，SHA256 `5B5D0AD15CE87B075630F62D0F051A29AA3C8D146CA0A8DA7BC1D8D494FCEBAF`；原v3签名、证书SHA256 `607edd7dc1df261e52fa2fe35ea6391e1ce77cbcebc315fea80dd815bac1a5d8`。实际ZIP逐项核对29共享资源与3原本地核心；原0.2.13指纹未变。APK不上传GitHub，未在红米安装；PHONE_LOCAL不启用托管v2，也不以本轮正式接线替代本地算法功能。

源码按原要求提交并推送当前分支，不自动合并main。桌面仍0.20.0，提交后沿原脚本／已验证pythonw更新“安康康复（最新版本）”入口描述；不关闭旧窗口。正常宿主v2默认关闭，未替用户启用或重启。

动作页`experience=legacy`关闭新正式训练入口，保留原历史读取与原草稿结束核对；不删除新记录、不换provider／origin／本人、不以降装旧APK抹去事实。正式操作仍应结束或导出原恢复记录，再回退代码；原反馈与未保存部分独立。

## 未完成范围

正式v2计划与独立陪练的关联及权威模式段／savedParts仍未接，不声称正式准备失败已经实现完整并行陪练降级。实际原组自动完成／下一动作、坐站与康复深蹲输入、Qt后补感受与跨进程outbox、全模块独立加载／持久原片／跨窗口租约／全产品音频、目标手机p95／熄屏／声音／长期资源压力仍待。完整任务保持active。

## 可复跑命令

下面输出目录必须全新且位于私有验证根，不能复用或覆盖已有失败目录；真实原片仅按已获授权用于流程检查。

```powershell
node tools/frontend_flow/verify_formal_training.cjs D:/RehabFrontendFlowVerification/<fresh-name> --record
node tools/frontend_flow/verify_formal_training.cjs D:/RehabFrontendFlowVerification/<fresh-desktop> --desktop
node tools/frontend_flow/verify_formal_measurement.cjs D:/RehabFrontendFlowVerification/<fresh-assessment> --feedback
node tools/frontend_flow/verify_phone_practice.cjs "<authorized-original-video>" D:/RehabFrontendFlowVerification/<fresh-phone> --feedback
python -m pytest mobile_rehab/tests android_offline/tests/test_packaging.py -q
python -m pytest tests/rehab_backend/test_sessions.py tests/rehab_backend/test_progress.py tests/rehab_backend/test_backend_plans.py tests/rehab_backend/test_async_finish.py -q
```
