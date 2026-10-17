# PR13 客服助手手测前复查

基于并发更新后的 `125d3c8345f32c5fcf835bcf6e275ee6c4fc347f`，2026-10-17。

仍需修改的基础问题：第一层没有明确禁止事件关系自引用、当前证据不能挂历史ID；康复工具规划示例只写空 arguments，搜索调用可能遗漏 query。本次只补完整提示契约，不改schema、权限、医疗门禁或写入能力。远端已增加自引用关系剔除并标记不确定、缺query时有来源的回退查询、两项动作映射及通用活动计划界面入口；本次保留这些已有改动。新增回归验证当前更正证据不能挂历史ID、无来源回退时空/缺失/超长搜索词仍拒绝，合法更正与查询通过。

`npm run ci`：TypeScript 572/572，产品 Node 35/35，build/typecheck/security通过。没有重新调用真实模型验证概率质量，不将这次提示修改宣称为此前所有真实模型失败已解决。旧完整验收报告保持FAIL。

本机补查：JDK21.0.8实际存在于 `C:/Program Files/Android/openjdk/`，只是未在PATH；没有找到本仓库可用APK、Android SDK/adb、模拟器或连接设备。因此没有构建、安装或打开APK。当前生成Android领域包原为默认semantic flag=false，也不能用旧包声称测到PR13路径。

已在本机loopback启动隔离手测服务，使用正式手机共用UI、ProductBackend/Node桥接及SYNTHETIC/TEST数据空间；进程内语义开关开启，模型凭据只在进程内存，不写文件。浏览器界面明确标为“同源手机 UI 网页预览（非 APK）”。这是电脑Host上的网页预览，不是原生Android、Android本地Host或APK验收。

HTTP GET根页为200，预览标记和正式unified.js存在。实际通过正式HTTP配对和chat接口完成一轮合成问候冒烟，返回provider=deepseek/status=replied，第一层llm_valid，理解与回复两阶段passed。只证明此轮真实连接与普通聊天，不证明原3组语义失败均已修复。没有提交用户聊天、打开相机或执行训练。

尝试通过电脑操作打开Chrome时工具自动停止，原文：

> Computer Use has been stopped for this turn because it could not determine the current browser URL on Windows with enough confidence to enforce policy.

未绕过策略、未再执行UI输入。用户可手动打开 `http://127.0.0.1:8873/#assistant` 继续。服务仅绑定127.0.0.1，不是公网部署。

仍需完成：疾病特异性适用性来源、专业审核到LLM候选采用、扩充当前仅两项的动作技术映射、LLM候选保存展示，以及Android自然语言日程写入。已接通的通用活动计划入口复用既有评估流程，不等于腰突处方闭环。当前可手测普通聊天、公共健康/动作知识、严格本人的只读查询、页面导航及失败回退；不能因手测流畅将整体改为PASS。
