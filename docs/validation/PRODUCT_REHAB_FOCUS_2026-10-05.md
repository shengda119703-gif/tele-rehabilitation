# 康复页面结构与操作收口 · 2026-10-05

用户明确授权一次完成此前诊断的康复页面及关联流程调整。本轮仅修改产品呈现、导航选择和对应文案；不改变 Agent、医疗判断、Runtime、存储 schema、训练计数或自动计划适用条件。分支 `codex/product-ui-v1`。

## 最终页面

| 目的地 | 职责 |
| --- | --- |
| 训练 | 无计划时引导评估 / 建立安排；有计划时显示下一项、侧别、目标、累计完成与真实不可用原因；计划完成后进入训练记录 |
| 康复评估 | 新评估、评估记录与摘要、身体档案与测量条件、原输入 / 训练设置 |
| 训练计划 | 已保存计划、原计划库、按既有规则自动安排、完整计划详情 |
| 训练记录 | 已保存训练、反馈预览、完整报告 / 反馈、原可比历史、训练与反馈变化 |

没有按日排期能力，故不再把默认康复页叫“今日恢复”。原内部数据字典键保留，避免改动读模型合同。黑白灰、原字体与 token；原生 QTabWidget / QScrollArea / QPushButton，使用既有 core_card 和 WrappingLabel；无新增动画或依赖。

## 操作与业务冻结

| 原能力 / ID | 呈现调整 | 保留的行为 |
| --- | --- | --- |
| rehabHome | 默认页隐藏重复按钮 | 原首页路由及稳定 ID，左侧首页可见 |
| rehabPerson | 移到设置 / 个人资料，名称为康复测量个人资料 | 原 ParticipantDialog、编辑安全限制与保存 |
| silverRehab | 康复页隐藏重复入口 | 家庭页既有 silverFamily 可进入同一个活动照护 / 家庭回应 / 整改窗口；所有原能力保留 |
| rehabOverview | 移至评估页，名称为摄像头与训练设置 | 同一个原工作区及输入 / 设备 / 双摄 / 回放入口 |
| rehabContinue | 根据真实计划状态显示开始评估、准备训练、查看训练记录 | 无计划调用原评估目录；准备仍进入原计划与确认流程；不可用计划不启动 |
| rehabStart | 概览隐藏 | 原工作区 start_button、准备条件、人工确认、Runtime.start 全部保留 |
| rehabAction | 仅有下一项时显示查看动作说明 | 原动作目录路径，不绕过训练准备 |
| rehabCreatePlan | 无计划时的次操作 | 原计划库；不创建假计划、不自动开始 |
| recoveryAssessment / History / Plans / Ask | 隐藏重复快捷入口 | 稳定 ID 和原 callbacks，页签与全局管家入口可见 |
| rehabReports | 隐藏与训练详情重复的按钮 | 训练详情 / 反馈仍打开同一完整报告 |
| rehabWorkspaceBack / 报告返回 | 返回康复并保留来源页签 | 摄像头测试、CONNECTING、PREVIEW、ONLINE、SAVE_FAILED、busy 的返回保护仍保留；刷新保存结果 |

## 最重要的变化与修复

- 无计划只显示一次空状态和两个明确动作；隐藏空进度、空表与四段反复“没有数据”的摘要。
- 训练页不再堆完整评估与趋势；分别放到评估与训练记录。有数据才显示相应摘要。
- 不再把“继续”和“开始”两个不同阶段并排呈现；启动只发生在看得到准备条件的原操作区。
- 无记录时查看详情禁用；不可用计划显示具体原因，准备按钮禁用；训练活跃状态保持导航保护。
- 切换用户时清空辅助说明与摘要可见状态，防止旧内容残留。
- 响应式容器最初仍持有移出摘要，会在 relayout 时将其放回训练页；已修正 widget ownership，并用回归测试验证父容器。
- 页面底部加入布局弹性空间，避免少量内容被分散撑满视口。
- 历史列表中的本人说明限制为 64 字预览，明确完整说明见详情；原记录、详情和反馈保存不截断，零评分保留。

## 组件研究

按项目 ui-polish 工作流读取 Fluent / frontend-design 指南，查询 UX empty state primary action，采纳“空状态给明确动作”。运行官方 registry discovery `empty state`，实际结果 No registry match。比较现有 Qt 控件后复用原生控件；本轮没有使用或安装 React Bits 组件，不为布局引入 React / WebView。

## 实际验证

- Windows 原生 Qt，1440×940 / 1024×940，浅色 / 深色，DPR 1.5；每个组合 12 个截图状态，共 48 个状态。包括四页签空态、焦点 / hover、键盘 Space 主操作、加载、真实 bridge 无效指标错误、有计划、计划不可用、计划完成、长反馈与记录变化。
- 所有数据使用临时隔离 TEST bridge。计划 / 历史展示使用明确 TEST 读模型；不冒充生产计划、真人训练或医疗判断。回归另通过正式 Runtime / SQLite 验证 SYNTHETIC/TEST 训练报告、反馈保存与返回路径。
- `tests/test_product_completion.py test_product_recovery.py test_product_module_paths.py test_product_visual.py test_product_ux.py test_product_rehab_focus.py test_product_window.py`：末轮 **41 passed**。
- 长反馈预览最后调整后，`test_product_rehab_focus.py test_product_recovery.py test_product_visual.py`：**14 passed**，与上述范围重叠，不相加称 55 个独立测试。
- `npm run build`：typecheck 与 build:bridge 通过。修改 Python 文件 compileall 通过；git diff --check 通过。
- 首轮 26 passed / 3 failed：旧页签、文案合同以及固定返回第一页预期，按用户授权的新行为更新。新增父容器测试发现真实布局问题并修复。
- 中间复跑 30 passed / 1 failed / 1 error：新增 action 的审计集合遗漏已补齐；构建与回归并行时 `.bridge-build` 正在重写，导致一个 Node 启动缺文件。停止该并行方式，构建完成后串行复跑 41 项全通过。不把中间运行称为全绿。
- 最终截图检查无横向溢出；长反馈标签预留完整换行高度。最终可见运行无未捕获 Python / Qt 异常。错误截图中的指标无效是主动触发的错误反馈验收。

## 证据

修改前：[宽窗](assets/product-rehab-focus-2026-10-05/before-1440-light.png)。

最终：[无计划](assets/product-rehab-focus-2026-10-05/1440-light-empty.png)、[窄窗](assets/product-rehab-focus-2026-10-05/1024-light-empty.png)、[有计划](assets/product-rehab-focus-2026-10-05/1440-light-plan.png)、[不可用](assets/product-rehab-focus-2026-10-05/1024-dark-unavailable.png)、[计划完成](assets/product-rehab-focus-2026-10-05/1440-light-complete.png)、[反馈](assets/product-rehab-focus-2026-10-05/1440-light-saved-feedback.png)、[记录](assets/product-rehab-focus-2026-10-05/1440-light-record-trend.png)。48 个状态的元数据见同目录 observations.json。

## 仍存在的边界与下一轮

本轮覆盖范围未发现未解决的 regression；没有运行全仓库所有测试，不能据此宣称全产品全部通过。没有新增真人动作、相机准确率、远程模型或实体设备验收。原训练工作区继续保留完整流程，尚未对其中每个设置对话框重新做视觉设计。照护窗口仍含独立演示能力，后续可专项整理其信息架构，但不应在本轮顺带删除。下一轮优先让实际用户完成评估 → 建立安排 → 准备训练 → 保存反馈，确认操作理解是否清楚，再决定原工作区的进一步简化。
