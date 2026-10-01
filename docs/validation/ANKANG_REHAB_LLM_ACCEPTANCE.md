# 安康康复真实 LLM 人工 / 半自动验收

日期：2026-10-02  
分支：`codex/rehab-agent-stage1`  
基线：`7a15486e773a8b5b14d2103fb5241f31aa04363a`

## 结论

**NOT RUN - no real LLM configured**

本轮没有把本地 HTTP 模型替身、fixture 或规则回复计为真实模型验收，也没有修改 Agent Runtime、rehab tools、生产路由、UI 或关键词规则。

## 配置核查

当前完整链路的康复模型适配器读取以下宿主环境变量：

- `ANKANG_REHAB_LLM_URL`
- `ANKANG_REHAB_LLM_MODEL`
- `ANKANG_REHAB_LLM_API_KEY`（服务需要鉴权时使用）

已检查当前进程、当前 Windows 用户和系统级环境变量；三项均未配置。仓库内也没有 `.env` 或本地配置文件提供这些值，只有不用于康复工具路由的示例配置。未记录、输出或提交任何 API Key。

没有 `ANKANG_REHAB_LLM_URL` 和 `ANKANG_REHAB_LLM_MODEL` 时，`scripts/rehab-model.cjs` 返回未启用，PySide6 → Python bridge → Node Runtime 可以继续使用原规则聊天，但三项 rehab tool 不会由真实模型选择和表述。因此不能执行本次要求的自然语言路由与忠实回答验收。

## 实际结果

| 项目 | 结果 |
| --- | --- |
| 使用模型 | 未配置 |
| 配置方式 | 既有宿主环境变量；本轮未新增配置方式 |
| 实际测试问题数 | 0 |
| 正确数 | 0 |
| 失败数 | 0（未发起模型请求，不将缺配置记作模型失败） |
| 合成 participant / 合成数据库 | 未创建；真实模型不可用时不执行验收 |
| 真实用户数据 | 未读取 |

计划、评估、训练历史和空数据问法均为 **NOT RUN**。因此没有可报告的模型 tool 选择、tool 实际返回、最终回答、典型成功案例或典型失败案例。

## 失败分类

没有产生单条验收失败。阻塞原因属于验收前置条件缺失：**模型未配置**，不是“选错 tool”“没有调用 tool”“读错 participant”“回答错误”“编造数据”“临床改善误述”或“模型 / 网络失败”的实测结果。

## 下一步建议

**不建议进入下一阶段。**

先由运行环境提供一个可用的 Chat Completions 兼容真实模型端点和模型名；如端点需要鉴权，再提供 API Key。配置完成后，应复用当前 PySide6 → Python → bridge → Runtime → rehab tool 链路，以隔离的合成 participant 和合成数据库执行计划、评估、训练历史及空数据的多种自然问法，并逐条记录用户原话、tool 选择、tool 返回、最终回答和判定结果。
