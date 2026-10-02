# 安康 Agent → 康复 PySide6 最小助手验收

日期：2026-10-01。分支 `codex/rehab-agent-stage1`；开始及 fetch 核实的开发分支基线为 `e9ca8e98e5f544c68fe64177d221873261a1329c`。不 merge main。

## 本轮结果

康复软件左侧导航新增“助手”，打开独立、非模态对话窗口。包含纯文本对话区、输入框、发送、正在处理和错误状态。无需开启摄像头，原康复工作区保留。

调用链：`MainWindow → AssistantDialog → AssistantWorker → bridges/ankang/client.py → scripts/agent-bridge.cjs → AgentRuntime`。后台工作线程串行调用原客户端；主线程只处理 UI 和结果队列，不阻塞康复运行线程。未新增通信协议或另一套客户端。Node 仅在第一次发送时启动，缺失 Node / bridge 构建不会阻止软件或原页面启动。

## participant / session

使用 `MainWindow.participant_id`（新档案为 `person-<UUID>`，兼容既有本机 ID），sessionId 为 `rehab:<participant_id>`。姓名、摄像头 track_id 不参与映射。权威用户切换 `_apply_participant` 同步更新助手；每个 participant 在当前 Node 进程拥有单独 Runtime session 和 UI 对话记录。切回同一人继续原会话；处理中换人，旧结果只归旧人的记录，不显示在新人的窗口。任一时刻只允许一个待处理 turn，Enter 和点击发送共享同一 busy 门禁。

只传该 sessionId、用户输入文本、时钟及 Runtime 必填的空 profile：疾病/药物/联系方式均为空，其他能力为 unknown、家庭共享 denied；age=0 是未提供年龄的占位，不读取康复年龄。没有读取或操作评估、训练计划、历史、反馈、药物/家庭/通知等产品数据，也没有新账号系统或持久化库。

关闭助手窗口仅隐藏，应用会话内可以重开。关闭主程序时，空闲 worker 调用原 close_session 后关闭进程；在途请求会终止 Node，避免残留进程。对话不跨应用重启保存。bridge 失败/超时会报告本轮未完成并重置进程内全部会话和 UI 上下文；下一次发送明确开启新会话，不假装旧上下文仍存在。

## 文件

| 新增/修改 | 路径（相对仓库根） | 内容 |
| --- | --- | --- |
| 新增 | `rehab_codex_single_camera_v2_1/app/ui/ankang_assistant.py` | 最小对话 UI、后台工作队列、participant/session 适配 |
| 修改 | `rehab_codex_single_camera_v2_1/app/ui/main_window.py` | 打开入口、切换 participant 通知、应用退出清理 |
| 修改 | `rehab_codex_single_camera_v2_1/app/ui/workspace.py` | 导航新增“助手”按钮 |
| 修改 | `bridges/ankang/client.py` | 沿用原 JSON lines；增加 ANKANG_NODE、隐藏 Windows 子进程、60 秒响应超时、可中断关闭 |
| 新增 | `rehab_codex_single_camera_v2_1/tests/test_ankang_assistant.py` | 2 项针对 UI/身份/迟到结果/重复提交/错误/退出的测试 |
| 新增 | `rehab_codex_single_camera_v2_1/scripts/smoke_ankang_assistant.py` | 真实桌面 Runtime 与 Node 的 offscreen 合成 smoke |
| 新增 | `docs/validation/ANKANG_PYSIDE6_ASSISTANT.md` | 本验收记录 |

没有 TypeScript 生产代码改动；`understanding/llmUnderstanding/agent`、Agent Runtime、所有阶段 5 services 和 Node bridge host 原样保留。未改康复业务 runtime、数据库或动作算法。

## 启动与验证

在已有安装依赖的源码工作区，一次构建 bridge（Node 22+）：

```powershell
node ankang/route1-health-agent/scripts/build-agent-bridge.cjs
```

随后沿用原 `Start-Rehab.ps1` / `python -m app.main`，点击左侧“助手”。默认从 PATH 查找 node；自定义安装位置可设置 `$env:ANKANG_NODE='C:\path\to\node.exe'`。本轮不修改打包流程，也不自动下载 Node/npm 依赖；缺少构建时 UI 显示原 bridge 的构建提示。

在应用目录运行：

```powershell
python -m pytest tests/test_ankang_assistant.py tests/test_product_navigation.py tests/test_training_hub.py -q
python scripts/smoke_ankang_assistant.py
```

本机实测使用既有隔离 Python 环境和 `.runtime/ankang-cleanup/python-deps`（PYTHONPATH），QT_QPA_PLATFORM=offscreen；PYTHONNOUSERSITE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 排除本机无关 xonsh 插件。初次测试启动被该全局插件的控制台需求阻断，隔离后通过；未安装新依赖、未改变全局环境。Node 为本机 PATH 的 **v24.20.0**。

实际结果：

- **27 passed**：新增助手 2 项 + 原导航/训练中心 25 项。
- bridge 构建通过。
- 真实 offscreen smoke 通过：主窗口正常启动；助手可打开；合成“我今天头晕”实际收到“先坐稳，别硬站着……”回复；第二轮血压输入返回回复，revision 依次 1/2，chat 长度 2/4。
- Enter 后同时点发送不产生第三轮、不关闭主窗口或助手；切换 participant 新会话 revision=1，切回只看到本人记录。
- 杀掉实际 Node 子进程后 UI 显示“助手不可用”，主窗口仍可用；再次发送创建新会话 revision=1。
- 原身体评估、训练中心、身体档案、历史入口均可进入；退出后桌面 runtime 线程、助手线程和 Node 进程结束。
- smoke 仅使用 TemporaryDirectory 的合成数据，无摄像头/真人测量，不接原个人数据库；未运行全项目重复测试。

验收仅证明原安康 Agent 已能在康复 PySide6 中进行独立对话，不代表已经接入康复计划/评估/反馈或其他安康业务模块。
