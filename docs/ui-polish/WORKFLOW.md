# UI Polish 工作流

触发：用户说“进入 UI polish mode”。入口是根 AGENTS.md 和 `.agents/skills/ui-polish/SKILL.md`。本轮搭环境没有启动 UI 修改授权。

## 四层

| 层 | 工具/资源 | 应产出的证据 |
| --- | --- | --- |
| Design knowledge | 本地 ui-ux-pro-max BM25/CSV；pyside6-fluent-ui 的 Qt/Fluent 规则与语义 token | 针对当前产品的字体、间距、层级、密度、可访问性和交互决策 |
| Taste | frontend-design + 下列项目规则 | 明确视觉方向和删减装饰的理由 |
| Procurement | React Bits registry JSON + 真实 demo；既有 Qt widgets/composites；Qt 官方文档 | 每个 primitive 的候选、依赖、props、行为、许可、适配/拒绝理由 |
| Visual feedback | 正式 Qt ProductWindow + 既有截图/QTest；Playwright/Edge 用于网页 | 同状态前后 PNG、像素审阅、错误日志、功能回归 |

## 功能冻结

开始前记录本页 action ID / signal / state / 数据写入 / navigation / error/disabled 契约。冻结 API semantics、Runtime、data model、routing/state semantics、medical logic、Agent reasoning、现有功能。保留隐私、来源/情境标识、保存失败、缺测与未启用语义。允许 layout/widget/DOM 重组，但不能悄悄改变点击后做什么、何时可用、用户确认或数据归属。

## 审美规则

- 先确定页面的核心工作与阅读顺序；首页应让下一步行动胜过次要统计。
- 不把一切放进等权卡片。不重复 icon + title + description 模板；数据用行/表/分组，表面容器必须有分组或交互目的。
- 禁止无理由的巨大空 hero、无意义 badge/pill、到处大圆角、随机阴影或渐变、紫蓝 SaaS 套路、默认 shadcn 外观。根据真实内容选择，不把禁止某个色彩变成新的统一模板。
- 字体和层级一致，中文行高与实际系统渲染优先；不要为了“有设计感”降低银发用户可读性。
- 留白应组织信息，不能只是填满窗口。密度随任务、设备和字号变化。
- 色彩承担状态或品牌语义，不能只靠颜色传达危险/选择/禁用。保持键盘 focus、可读对比度和足够点击目标。
- 动效说明用户动作带来的变化；保留 reduced motion，避免弹性/模糊影响医疗数值阅读或实时摄像头资源。
- 在动手前写一个简短 design brief；不得用追求新奇推翻用户已经选定的视觉方向。

## 默认顺序

FUNCTION FREEZE → VISUAL AUDIT → DESIGN SYSTEM → COMPONENT PROCUREMENT → IMPLEMENT → VISUAL REVIEW → FUNCTION REGRESSION → ITERATE。

逐项采购范例：周期选择 → segmented control → 查 Rubber Segment / Qt button group → 比较键盘与状态契约 → 适配。Tooltip 查 Warm Tooltip；select 查 Glide Select；AI input 查 Prompt Bar；复杂导航查 Branched Menu。名字是候选，不是强制替换。

## 验收

- 桌面实际 ProductWindow 截图已经打开审阅；1024 窄窗、字号/DPI、light/dark；不是历史截图或源码推测。
- 浏览器网页目标额外检查 desktop/tablet/mobile；Qt 不冒称手机 UI 已通过。
- 无内容裁切、横向溢出、不可见核心操作；层级/间距/对齐/字体/交互语言一致。
- empty/loading/error/disabled/hover/focus/selected 等适用状态已观察；dialog/menu 焦点与返回正确。
- 无明显 card soup 或无意义 AI 模板装饰；对比度满足正文 4.5:1、大字/必要非文本 3:1 的目标并记录测量边界。
- web console/pageerror 或 Qt stderr/runtime 没有未解释的新错误。
- 原有用户流程和业务状态保留，针对性回归通过。截图数据固定隔离 SYNTHETIC/TEST，不触碰个人患者库、不启相机/LLM/麦克风。
- 视觉判断由 agent 打开图后书面记录；脚本截图成功只表示 capture PASS。

新组件采购记录建议：primitive | candidate/source | behavior | dependencies | props | preview | license | Qt compatibility | decision。未来每轮证据放 `qa-output/`；选取少量不含个人数据的图和报告进入 `docs/validation/`。
