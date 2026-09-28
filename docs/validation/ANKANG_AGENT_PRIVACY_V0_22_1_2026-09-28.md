# 0.22.1 安康 Agent 迁移起点：本机验证

日期：2026-09-28。范围：隐私意图、分享请求的诚实状态、桌面 UI 回执及现有银发入口。没有真实 DeepSeek Key、远程家属服务或真人康复验收。

- `tests/test_agent_conversation.py`、`tests/test_agent_conversation_ui.py`、`tests/test_rehab_agent_ui.py`：使用本机隔离 Python、Qt offscreen、独立临时测试目录运行，**56 项通过**。
- 用例覆盖：不记录/不告诉家人不调用模型，分享请求不调用模型且不伪称送达；受保护回合不进入后续模型历史；隐私回执独立显示；按钮打开现有银发页面，不创建请求或授权。
- `compileall` 对改动的 Python 应用文件通过；`git diff --check` 通过。
- 未验证：真实 DeepSeek 服务、真实家属手机送达、真实用户交互可用性、Agent 结构化陈述和任务闭环。这些不能从上述单元测试推断为完成。
