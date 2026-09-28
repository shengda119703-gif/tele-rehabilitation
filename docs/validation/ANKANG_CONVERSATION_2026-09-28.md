# 0.20.0 对话接入验证

基线 `a693f09`。环境沿用 0.19.0 独立 Python 3.12 测试环境，无新第三方依赖。

## 已验证

- 新旧 Agent 专项共 56 项通过：自由聊天调用适配器、连续追问上下文、正确范围的真实临时 SQLite 查询、隐私不发出、敏感历史过滤、密钥 repr 掩码、缺配置诚实提示、超时明确失败、结构化枚举、思考内容剥离、拒绝 / 当前感受优先、原 UI 门禁与导航。
- HTTP 请求通过隔离的模拟连接校验：模型名称、messages、Bearer、max_completion_tokens、响应解析和拒绝跳转。没有向真实服务发送测试密钥。
- 实际 Runtime 慢模型测试：模型适配器由事件阻塞时，participants 命令仍完成、摄像头未开启；释放后可正常退出。
- `scripts/qa_agent_conversation.py` 渲染未连接状态、模拟连续对话和空密钥配置界面，已目视核对。模拟图显著标注未调用真实模型。
- `compileall` 通过。业务回归 1053 passed、4 subtests passed；界面回归 419 passed。两个组共 1472 项主测试，已包含上述 56 项专项测试，不重复相加。

## 执行命令

在应用目录用独立验收环境 Python 执行：

```text
python -m pytest tests/test_agent_conversation.py tests/test_agent_conversation_ui.py tests/test_rehab_agent.py tests/test_rehab_agent_ui.py tests/test_rehab_agent_runtime.py -q --tb=short --basetemp=.runtime/agent-chat-test-01
python scripts/check_project.py --suite core --output .runtime/chat-core-results
python scripts/check_project.py --suite ui --output .runtime/chat-ui-results
python scripts/qa_agent_conversation.py
python -m compileall -q app scripts/qa_agent_conversation.py tests/test_agent_conversation.py tests/test_agent_conversation_ui.py
```

core / ui 分别使用 `PYTEST_ADDOPTS` 指定 `.runtime/chat-core-01` / `.runtime/chat-ui-01` 临时目录。

## 尚未通过的真人 / 外部验收

未找到或收到可用 MiniMax 密钥，故没有完成真实 API 联通、真实模型连续对话、自然语言准确率或响应延迟验收。
没有开启摄像头或测试真人动作，也没有重跑需要完整姿态依赖的 integration 组。软件模拟测试不能代替这些验收。

已打开独立 `qa-output/manual-agent-chat` 数据目录的新窗口，供用户在软件内填写配置；不关闭或修改原验收窗口的数据。
