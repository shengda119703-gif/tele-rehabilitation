# 最小 Python → 安康 Runtime bridge

仅证明 Python 能调用现有 TypeScript Runtime。Node 22+、原项目 npm 依赖、Python 3.10+；Python 只用标准库。没有网络服务、数据库、UI 或康复业务接线；不配置外部 LLM、持久化或送达 port，使用原 Runtime 默认规则路径与会话内存。

首次使用在 `ankang/route1-health-agent` 执行 `npm ci`。然后从仓库根目录运行：

```powershell
python bridges/ankang/smoke.py
```

Python/Node 不在 PATH 时使用其完整可执行文件路径，Node 通过 `--node` 指定。smoke 自动调用原 TypeScript 编译器生成 `.bridge-build/`，随后启动 Node 子进程，open → 连续两次 process → close，打印回复和接收成功提示；所有构建产物忽略，不写健康数据到磁盘。

- [Node host](../../ankang/route1-health-agent/scripts/agent-bridge.cjs)：逐行读取 stdin JSON，直接调用 `AgentRuntime`，原样返回结果；stdout 只有 JSON，诊断写 stderr。
- [Python client](../../bridges/ankang/client.py)：同步、单调用者 client；启动子进程，UTF-8 编解码，context manager 关闭进程。没有重试、并发、复杂协议或 Agent 逻辑。
- [可直接运行的 smoke](../../bridges/ankang/smoke.py)：使用明确标记的合成 profile，输入“我今天头晕”“我今天量了血压150/95”，断言两轮 revision、chat、events 及 close 结果。

请求只有 operation（open/process/close）、sessionId 和需要的 profile/text/now；响应为 `{ok, result}` 或 `{ok:false, error}`。时间由 Python 提供带时区的 ISO 时间，host 转成 Date。process 返回原 Runtime 字段：reply、replyBlocks、understanding、appliedChanges、sourceMessageId、snapshot、findings、personTwin、tasks、persistence、delivery、revision；snapshot 内包含 events、familyEvents、chat 等。未配置存储和 transport，不把内存结果称为持久化/送达成功。

单独使用 client 前，在 route1 运行 `npm run build:bridge`；它只编译 Runtime 的传递闭包，不编译 React 页面。未修改任何 Runtime/理解/检测领域实现或原测试。

2026-10-01 实测（基线 `6c3a332d1039937771be6c2923c292c770540d9b`）：

- Python **3.12.14** 启动系统 Node **24.20.0**，smoke 退出 0；open、连续两次 process、close 全部通过。
- “我今天头晕”返回原 Agent 头晕回复，revision=1、events=1；第二句血压输入后 revision=2、events=4；末尾打印 `Python successfully received Agent result`。
- 原 `npm test` 使用此前验证的 Node **22.14.0** / npm **10.9.2**：**396/396 通过**，无失败/跳过/取消，包含原 upstream 与 Runtime 核心测试。没有新增大批 bridge 异常/并发测试。

本机已验证命令（从仓库根目录）：

```powershell
& 'C:/Users/Sophie/.codex/.chatgpt-projects/g-p-6aa7c931ae7081919e73c0e8b21d2fc3/.agent-test-env/Scripts/python.exe' bridges/ankang/smoke.py --node 'C:/Program Files/nodejs/node.exe'
```

没有修改 Runtime、Agent 领域代码或康复 Python 应用；本轮只增加传话 host/client、构建入口和 smoke。没有连接 UI、评估、训练、数据库或 rehab tools。
