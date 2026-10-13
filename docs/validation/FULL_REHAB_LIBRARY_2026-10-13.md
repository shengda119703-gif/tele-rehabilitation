# 完整动作库接入与候选清单验证 · 2026-10-13

基准main：c7f9c640dfed57fa6f53cad56be1b5aaa5978670。用户确认采用新完整版，继续执行已批准的问答／解说／本地候选计划范围。

## 内容与实现

- 用户提供完整原文原样保存到`docs/rehab-library/SOURCE_v1.0.md`，SHA256为4D0164623D410DCD8AECAA51C5606FA57C739334A51CD0929C47292207FBD138。旧部分稿移到该目录history，只供溯源。
- 共185个唯一详细卡编号，63评估、122训练；185卡均有操作、要领、开始／停止条件、器材和原文协议字段。结构完整不等于医学审核通过。
- 编号及名称检索、相关说明章节和引用条目供三端共用。只把选中的资料给模型解释，不上传本人康复记录；模型未配置、隐私或失败时返回本地资料。真实联网模型未重测。
- local-rules-2先映射5个起始版本，覆盖肩／髋／膝／踝；最多3项，输出原文范围和核对条件，没有固定处方剂量，不自动进阶。限制有内容时needs_review；无映射或器材时no_match。其他117训练卡可查询，尚未纳入自动编排。
- 桌面使用可滚动候选预览；配对网页和独立手机接口展示相同字段。均不持久化候选、不采用、不改计划或健康记录。报告原件、手动指标、训练动作识别路径不改。
- 原care网页测试在远端archive/retired-features中完整保留，blob为9ba4f50d670fe901887c0c4f6f8461df314ebaf1，与更新前main一致。当前测试改为验证旧操作关闭、只读查询和候选草稿；未删除原历史资料。

## 实际检查

| 检查 | 结果 |
| --- | --- |
| 导入脚本 | 185卡／185结构完整；原文SHA核对 |
| npm run build | TypeScript与桥接构建通过 |
| npm run test:product | 24通过；编号／短名称、原文范围、不自动采用、隐私、不写健康与旧操作关闭 |
| npm test | 471通过；原领域及兼容路径回归 |
| Qt：test_product_window、test_simple_rehab_assistant、test_report_manual | 11通过；真实Node桥接，隔离TEST数据和PassiveRuntime |
| 手机HTTP：test_health_completion与test_unified，排除real_blank_video | 17通过、2语音依赖测试跳过、1录像项排除；原件／手动记录、本人来源、关闭care、本地候选与不写数据 |
| 网页test_unified_presentation.cjs | 8通过 |
| 安卓领域bundle | 63模块构建通过；未制作／安装APK |
| git diff --cached --check | 源文2处Markdown硬换行尾空格原样保留；排除该原样副本后其余变更通过 |

Qt候选预览在浅色／深色分别截图并查看，未见文本裁切；可滚动查看原文。截图在本机`%LOCALAPPDATA%/AnkangChecks/report-manual-20261013/screenshots/full-library-plan-light.png`和`full-library-plan-dark.png`，不上传个人运行目录。截图与Qt测试使用隔离合成档案，不代表真人训练或测量准确度验证。

扩大手机回归首次运行有7项失败：6项仍要求已退役care行为，已更新并通过；1项真实空白录像分析因未配置本地YOLO11n-pose权重失败，日志明确指出缺权重。录像模块本轮未修改，后续回归明确排除该项，没有把它记为通过。无新权重下载、真实相机或手机硬件测试。

本次交付源码和领域bundle检查，发行版本仍为桌面0.23.1／安卓0.3.1。本仓库缺正式启动所需YOLO权重／项目独立环境，故未用仅通过PassiveRuntime的测试Python重指向桌面最新版本快捷方式；正式启动入口仍为Start-Rehab.ps1，页面入口是首页“康复管家”→“本地候选计划”。
