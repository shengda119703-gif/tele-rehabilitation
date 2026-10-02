# 本地开发者 DeepSeek Key 入口

分支：`codex/rehab-agent-stage1`。本轮仅增加本机凭据入口与现有模型适配器的配置读取，不改 Agent 业务、rehab tools 或康复写操作，不合并 main。

## 使用

康复软件主窗口按 `Ctrl+Shift+D`，打开开发者对话框。界面仅有 `DeepSeek API Key`、密码输入框、确定和清除 Key；主导航没有模型设置。保存和清除成功后关闭旧助手会话，重新打开安康助手时由现有 bridge 创建新会话、重新读取配置。

保存位置为 `%APPDATA%\tele-rehabilitation\deepseek.json`；无 APPDATA 时使用用户主目录的 `.config/tele-rehabilitation/deepseek.json`。本机从 Codex 启动的验证进程实际路径为：

`C:\Users\Sophie\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Roaming\tele-rehabilitation\deepseek.json`

文件在 Git 工作区外，原子替换保存。不得复制文件或凭据进仓库、README、日志或测试输出。

`scripts/rehab-model.cjs` 仍为唯一模型适配器，读取本地文件的 `api_key`；没有本地 Key 时兼容 `ANKANG_REHAB_LLM_API_KEY`。URL 固定为 `https://api.deepseek.com/chat/completions`，模型固定为 `deepseek-flash`；旧 URL / Model 环境变量不再改变这两个固定值。两种来源均没有 Key 时返回不可用。清除本地 Key 后，如果仍设置了旧环境变量 Key，会按兼容规则回退。

## 本机最小验证

- `tests/test_deepseek_developer.py`：2 passed。真实 Qt 密码输入框填写合成凭据并保存；新进程读取；重新打开仍为遮蔽显示；清除文件；无环境变量 Key 时模型不可用。
- 适配器模拟请求验证本地 Key 优先、原环境变量 Key 回退、URL / Model 固定；网络异常即使含有凭据也只返回固定错误文字，测试进程不输出凭据。
- 使用真实本机配置在独立进程重新读取并检查密码遮蔽；检查应用源文件与应用 `.runtime` 日志，没有发现真实 Key。
- 真实最小请求：删除该请求进程中的环境变量 Key 后，通过现有 `createRehabModel(...).describe(...)` 使用本地保存的 Key 请求 DeepSeek；输出 `DEEPSEEK_MINIMAL_REQUEST_OK model=deepseek-flash`，返回有效非空文本。未传患者数据、未读取康复记录、未调用工具、未执行康复写操作。
- Python 源文件编译与 `node --check` 通过。没有重跑全部历史测试。

验证用 Qt Essentials / pytest 安装在工作区外的隔离 `.runtime/deepseek-dev-deps`，未改变正式软件依赖。
