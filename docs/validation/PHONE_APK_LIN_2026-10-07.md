# APK 0.2.1 · 林女士完整档案验证

日期：2026-10-07，本机 Windows，JDK21 / Android SDK35。电脑/统一网页版本仍为 0.19.2；本轮只做 Android 本地适配、档案整合和验证，不修改正式静态 UI、领域业务或动作算法。

## 交付物

- `android_offline/dist/tele-rehabilitation-mobile-0.2.1.apk`，28,066,653 bytes。
- 包名 `cn.tele.rehabilitation.offline`，versionName 0.2.1，versionCode 3，minSdk29 / targetSdk35。
- APK SHA256：`36ef93ee0e9e8e2269ef60fdee1e28d60b03585697fdeaaa3ad2912aa0f6d861`。
- 签名证书 SHA256：`607edd7dc1df261e52fa2fe35ea6391e1ce77cbcebc315fea80dd815bac1a5d8`，与旧 APK 相同，v3 验证成功。
- APK、模型、语言包、用户数据、签名与 QA 文件不入 Git。源代码/构建脚本/文档上传 main。

## 数据与路径

构建从既有 `tools/ui-polish/test_lin_profile.py` 重新生成纯 TEST 档案，临时目录只使用 qa-output 的独立子目录；不读取或复制 1396/8765/8876 用户库，不将已有真人录像打入 APK。资源带 `test-lin-apk-v1`、`synthetic=true`，每份原动作结果仍带 `test-lin-profile-v1`；原器械轨迹来源和物理假设不丢失。手机契约字段只是这些 TEST 历史的可移植适配，不是一次真实手机推理。

| 主要区域 | 内置数据与验证 |
| --- | --- |
| 本人/健康/首页周报 | 68 岁 TEST 林女士；14 天 10 类指标共 140 条；已有健康对话、周报与趋势 |
| 康复评估与汇总 | 18 条评估，保留左右侧、角度、次数；原身体汇总读取全部 24 条记录 |
| 计划与训练 | 原规则生成 4 项计划；2 条训练关联到前两项，感受保留；正常计算 2/4，下一项左肩前屈 |
| 健身 | 深蹲 8 次、划船 6 次，负重均 20 kg；保留器械轨迹、逐次上升表现、速度/加速度/外力/功率 |
| 体态 | 正面与侧面各一份报告，原二维指标和边界保留 |
| 用药 | 3 项药物、2 项有效；按原时间安排与逐次历史读取，不预填首开时仍在未来的完成项 |
| 资料 | 3 份 UTF-8 文本原件，可读取/导出；资料保存/回收站仍走原 ArchiveService |
| 家庭 | TEST 林晓关系与获准健康摘要，类别选择仅操作本地 TEST 关系 |

首开平移时间一次，之后不自动重写日期/补充服药。全新安装默认 Lin；已有个人或旧 0.1 档案默认仍是个人。原生菜单新增两项档案切换，不增加网页导航或演示分区。个人与 Lin 的 JSON 命名空间隔离，IndexedDB 按 owner 分隔。写入资料的 owner 在初始化完成后动态读取，避免使用导入前的占位 ID。

TEST 备份只能恢复到 TEST 命名空间，个人备份不能覆盖 Lin；恢复前分别保留 `:before-restore`。JSON 备份仍不包含录像/资料原件，原件需分别导出。原个人授权不从备份恢复，原个人恢复会暂停旧云端连接；TEST 备份恢复只保留本地类别设置，不动个人云端凭证。TEST 不发布到云端，不把历史家庭行当成实际外部绑定成功。

## 自动检查

```powershell
& ./android_offline/tools/build.ps1
node --test android_offline/tests/*.test.cjs
node --test mobile_rehab/tests/test_product_ui.cjs mobile_rehab/tests/test_extensions_ui.cjs mobile_rehab/tests/test_ui_copy.cjs mobile_rehab/tests/test_unified_presentation.cjs
$env:PYTHONPATH='E:\game\health-care-software-main\rehab_codex_single_camera_v2_1;E:\game\health-care-software-main'
& ./rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe -m pytest tools/ui-polish/test_test_lin_profile.py mobile_rehab/tests android_offline/tests/test_packaging.py -q
& ./rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe -m unittest discover -s android_offline/tests -p 'test_packaging.py' -v
```

- Android Node：54/54；含 10 项新档案适配测试。检查 counts/20 kg、规范契约、当前日期与未来服药、独立命名空间、旧个人原件不动、幂等/写冲突拒绝、真实 ProductService 五区域快照、训练进度/下一项、动态资料 owner、回收站、备份、云端隔离与切换。
- 网页 Node：42/42，正式呈现与原动作/同意/来源/用户文案回归通过。
- Python：第一次组合运行 143 项（141 档案/手机 + 2 原包装检查）通过，2 个 subtests 通过；49.67 s。7 条警告为 Starlette/httpx 弃用与 pytest 旧临时目录清理失败，未强删这些目录。
- 新包装检查加入后单独运行 3/3，通过。APK ZIP 无反斜线/路径越界、无视频/患者数据库/QA 测试脚本/签名私钥；`ui-lock.json`、APK 静态文件、仓库正式静态文件 hash 全部一致。
- `aapt2 dump badging`、签名校验和构建成功；javac 的 Java8 目标弃用警告不影响生成。

## Android 实际流程

专用 `emulator-5556`，API35 x86_64，覆盖安装发布包保留现有 QA 个人数据。通过独立测试 APK 的 `LinSmoke` 操作发布包真实 WebView/接口，不替换显示函数：

- 五页：首页/康复/健康/用药/家庭，以及原周报与管家路由均打开；五导航保留，411 CSS px 视口无横向溢出。
- 140 条指标、3 药物、3 原件读取一致；周报、家庭姓名、JSON 备份校验通过。
- 24 条活动历史及两份 20 kg 健身报告正常显示；TEST 姓名保留，原简洁标签在此上下文生效。深蹲功率 132.73045 W、划船 43.39323 W 是原 fixture 曲线计算结果，不是实测功率。
- 原肩外展评估/训练反馈、体态报告、身体与训练汇总均打开；2/4 进度、下一项左肩前屈与正常录像选择入口连接正确，没有新造一条已完成训练。
- 重开和通过本地切换函数来回切换两个档案通过；保留所有持久记录，仅领域 session 的正常 revision 增量不作为记录丢失。Lin 操作期间个人 JSON 原文不变，升级前已有数据未清空。

初次测试脚本有导航完成时序、数字显示 `20.0 kg`、授权框只在选文件后出现的断言错误；修正 QA 脚本后上述完整检查通过，未为测试改正式 UI/业务。后续脚本补了原生菜单选择验收并已编译，但运行前设备环境断开，因此不能声称这个新增菜单点击检查已经执行通过。菜单调用的本地切换函数已通过 Node/Android 检查。

追加原 `SmokeTest` 新录像/OCR流程时，ADB 设备消失、模拟器进程退出，未返回验收结果；不将这次追加复测记为通过，不推断为应用逻辑错误。只结束了本轮随后等待不存在设备的诊断 reader，未关闭用户电脑应用/网页服务。旧 0.2.0 真人录像测试作为历史记录保留，不计入本轮通过数。

## 保留边界

- Lin 四项计划已经按原规则生成并完成本地映射，不是手机带病处方自动生成的准确性证据。手机既有建议器仍把 conditions 文字作为活动限制；本轮不为演示删掉高血压/肩部情况，也未放宽新计划规则。此档案可查看和继续已有计划，不能据此宣称新的带病处方生成验证通过。
- 本轮没有原 Lin 录像、影像 OCR 附件、实际外部设备或已联网语音服务，不能把这些预填成成功。普通用户实时指导/录像分析仍用手机模型与真实输入；主要功能已有数据不等于每个动作都做完真人验收。
- Redmi K60 Ultra 未连接 USB；手机实机性能、相机/权限、离线语音、全部动作准确度尚待实测。不同网络云端/RTSP/多相机 3D 等既有未接入边界不变。
- TEST 档案用于功能展示，内部 provenance 保留；不能拿 fixture 数值证明真人测量、真实肌力或临床准确度。正式页面未重设计，固定“电脑/上传”等旧 UI 措辞仍存在。
- 原用户动作图片、导入脚本和 exercise-guides/README.md 修改全部保留，不属于本次提交。
