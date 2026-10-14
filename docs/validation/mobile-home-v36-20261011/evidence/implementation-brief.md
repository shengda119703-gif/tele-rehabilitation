# V3.6 实施约束

基准：2ddbba07c660be84839868e659d774d3c4abb8f9；分支 feat/mobile-home-v36。工作区开工干净。

只改统一移动Web首页及其必要展示资源，其他页面函数、capture工具、API、Python/TS业务、Android、Qt保持。首页数据均来自/api/unified既有snapshot；当前source/owner边界由认证宿主确定。

|控件|既有依据/动作|保留约束|
|---|---|---|
|动态主任务|rehabilitation_ui计划/progress,next_available|不计算新剂量；手机不启动LIVE；阻塞原因保留|
|本周训练|rehab.get_training_history已保存terminal记录|本地自然周、日期去重；不把分析中/失败标完成；当前source/本人|
|计划/报告|原planDetail、#rehab、#records、/capture?tab=plan/history|读取已保存事实，不复制原型记录|
|每日安排|dailyProduct.schedules+medSchedules/doses|删除主卡对应的一个安排ID；用药跳原日期页面，不能代填服药|
|AI|#assistant|本地记录/模型不可用说明保留|
|搜索|原全局搜索不存在|明确未提供；仅连接已有动作库/计划/记录，不伪装搜索服务|
|档案/刷新|editProfile、load|保留入口；换本人配对清理旧snapshot|

视觉冻结：暖白#f9f9f6、纯黑#000、荧光黄#dfff36；系统中文无衬线；模块顺序按附件；390/320原稿布局。主卡背景、SVG斜线、透明RGBA人物、动态文字/按钮五独立层，不引用主卡整图。

采购：已检查原生button/link/dialog/date和已有controls.css；真实查询RubberSegment（motion依赖、拖拽/弹性），不采用，批准稿无拖拽且不增加React/依赖。Qt Skill只作约束输入，Web任务不运行Qt桌面打磨流程。

缺口：schedule没有与某次训练保存一对一的完成字段，不能制造“当日X/Y已完成”；展示真实安排数量，累计计划序号与周训练记录天数分开。搜索没有既有全局API，只说明能力缺口。
