# 0.21.0 DeepSeek 康复 Agent 验证

## 自动验证范围

- 配置只接受 DeepSeek 官方根地址，以及当前支持的 `deepseek-flash` / `deepseek-v4-pro`。
- HTTP 合同隔离验证：`/chat/completions`、Bearer、`max_tokens`、JSON Output、完整返回检查和拒绝跳转。
- 普通聊天只调用一次模型；计划 / 评估 / 历史查询调用本机规则后再进行一次自然语言解释。
- 第二次请求不含 participant ID、session ID 或原始证据；模型不能引入本机结果中不存在的数字。
- 第二次调用失败时，本机结果、证据和页面入口仍保留。
- 私密表达不联网、不进入后续上下文；当前不适和拒绝训练继续优先于模型的计划意图。
- 慢模型调用不占用摄像头或主运行队列。

## 本机结果

- Agent 专项：62 passed。
- Core 回归：1059 passed，4 subtests passed。
- UI 回归：419 passed。
- 主测试合计 1478 项；专项已包含在 core / UI 中，不重复相加。
- `scripts/qa_deepseek_agent.py` 已渲染未配置、两段式结果和 DeepSeek 配置界面；所有对话为明确的模拟数据，没有调用真实模型。
- `compileall` 通过。

## 尚未验证

没有读取、保存或提交真实 API Key，也没有向 DeepSeek 发出真实付费请求。因此真实服务联通、账户模型权限、回答质量、费用、网络延迟和限流行为需要用户在软件内配置后人工验收。

没有启动摄像头或进行真人动作准确度测试；本次改动不改变姿态识别、角度、计次和训练安全算法。
