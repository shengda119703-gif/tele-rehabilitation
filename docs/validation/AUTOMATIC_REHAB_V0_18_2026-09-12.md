# 0.18.0 自动康复闭环本机验收

日期：2026-09-12。工作区：`E:/game/health-care-software-main`。

## 本轮实际实现

- 从当前用户 / 来源 / 使用情境的已保存评估自动生成身体测试摘要和训练计划，不再要求逐项填写动作、侧别、次数与组数。
- 现有 53 项动作、左右侧共 106 个评估条目全部有自动规则；逐动作、逐侧创建与保存契约均有参数化测试。
- 每轮最多 4 项；成功完成的动作在下一轮后置，尚未完成、引导计时或中断记录不会冒充已经练过。
- 9 类动作标记为“官方动作条目匹配”；其余 44 类标记为“本人评估适配”，WHO 只作为从少量开始的一般活动原则，不冒充具体动作处方。
- 最新评估、7 天、0.8 有效比例、完整动作、测量契约、计划顺序、参数、规则、来源和个人条件均在生成 / 准备 / 正式开始三处验证。
- 实时和报告分开显示完整次数、已观察目标达成、需调整和未能核实；训练后可一键明确记录无疼痛 / 不疲劳。疼痛、明显疲劳、疾病 / 术后 / 档案限制会停止自动续练。

## 自动测试

最终完整分批回归：

```text
.venv/Scripts/python.exe scripts/check_project.py --suite all --timeout 240 --output .runtime/checks/automatic-v018-final-exact
```

预期且实际通过的分组总计为 **1641 项主测试和 4 项子测试**：core 1008、ui 406，另有 11 个逐文件集成批次共 227。各批次 stdout、JUnit 与 JSON 汇总保存在上述证据目录。测试覆盖原双摄、关键点进程、录像 / 实时来源、引导计时、SQLite、人工计划和新增自动闭环。

新增自动规则定向复核：

```text
.venv/Scripts/python.exe -m pytest tests/test_automatic_plans.py tests/test_automatic_runtime.py tests/test_automatic_ui.py -q
154 passed
```

其中包括 53 项 × 左右两侧的候选、计划创建和持久化契约，过期 / 失败 / 缺测 / 引导计时 / 跨范围排除，来源和确认防篡改，完成顺序、不适阻断、保存重开、相机不被计划读取打开，以及原生界面消息乱序保护。

## 原生界面检查

以下脚本均通过；只使用临时 SQLite 和明确 SYNTHETIC / TEST 数据，不打开摄像头或个人数据库：

```text
scripts/qa_automatic_plans.py
scripts/qa_training.py
scripts/qa_plan_library.py
scripts/qa_product.py
scripts/qa_desktop.py
```

`qa-output/automatic-v018/` 保存自动建议、顺序执行、缺少感受恢复和一键感受界面截图。检查确认适用性复选框默认未选、按钮层级清楚、来源可查看，并能在常见桌面窗口显示。

## 本次没有证明的内容

- 没有打开真实摄像头，没有真人执行 53 项动作，也没有形成临床准确性或治疗有效性证据。
- 53 项“接入自动流程”表示软件可以在取得有效评估后生成和执行保守安排；不表示每项视觉测量都已完成真人对照。腕、踝和手指仍依赖可选本地关键点环境。
- 视觉监督只覆盖该动作已实现的二维指标、目标、分期和少量可见问题。多数精细动作尚无独立代偿规则，不能称为全面动作质量判断。
- 本版只提供一般基础活动建议。疾病、损伤和术后计划必须由专业人员核对；系统不诊断、不推断肌力、不自动加量。

## 来源核对

本轮查阅并在计划快照中保存对应 URL：[WHO 身体活动指南](https://www.who.int/publications/i/item/9789240015128)、[WHO 身体活动主题页](https://www.who.int/health-topics/noncommunicable-diseases/physical-activity)、[NHS Strength exercises](https://www.nhs.uk/live-well/exercise/strength-exercises/)、[NHS Sitting exercises](https://www.nhs.uk/live-well/exercise/sitting-exercises/)、[North Tees NHS Chair Exercises](https://www.nth.nhs.uk/resources/chair-exercises/) 和 [North Tees NHS Bed Exercise](https://www.nth.nhs.uk/resources/bed-exercise/)。来源的公开建议与本软件工程参数在界面、记录和文档中分开陈述。
