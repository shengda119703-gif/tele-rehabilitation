# Productization Day 本机验证

2026-10-02，分支 codex/rehab-agent-stage1。隔离临时 TEST 用户和数据库；不操作实际患者数据，不打开摄像头，不调用真实 DeepSeek，不合并 main。

## 已通过

- `node scripts/build-agent-bridge.cjs`：产品与原 Runtime bridge 编译成功。
- `npm run typecheck`：全项目 TypeScript 类型检查成功。
- `node --test tests/product-desktop.test.cjs`：3 项通过。实际原服务链路验证 owner 隔离、重启、药物任务持久化、指标/周报、no_record 不落盘、绑定和授权分离、私密附件过滤、通知渠道 unavailable 和确认重启、本人导出附件字节、限定清除、损坏文件拒绝读取、图片候选确认。图片 provider 是标明 TEST 的协议夹具，不算真实 OCR 验收。
- Python `test_product_window.py`、`test_product_navigation.py`、`test_rehab_read_tools.py`、`test_deepseek_developer.py`、`test_ankang_assistant.py`：共 29 项通过。涵盖真实 Node bridge、首次建档等待 Runtime 就绪、七主页面及两工具页面、用户切换立即清旧资料、撤销授权清除家属摘要与记录审计、原康复门禁、药物/指标操作、私密聊天、康复读工具及固定模型 URL 的本地协议夹具。旧协议测试改为 child fetch 拦截，临时 APPDATA 与 TEST Key，生产 URL/model 未改。
- 正式 `python -m app.main --data-dir <隔离目录> --screenshot <本机截图>`：真实 Runtime 启动、加载已保存 TEST 档案、截图、退出，进程返回 0；未打开输入。
- Start-Rehab / Setup-Rehab PowerShell AST 无语法错误；git diff --check 无空白错误。
- 九页面截图已逐页查看，中文可读；康复原界面成功嵌入且保留输入确认流程。截图与临时数据不入 Git。

## 环境与限制

验证使用本机已有隔离 Python 环境与 PySide6 依赖；正式目录默认 .venv 当前不存在。Start-Rehab 可通过 PythonPath 指定已准备好的环境，否则先运行 Setup-Rehab。两启动脚本现在准备/检查同一 TypeScript bridge，不安装第二套 Agent。

没有重跑全部历史测试。没有真实相机、训练保存实测、真实 OCR、外部通知发送或新增真实 LLM 验收；继承之前已有的 DeepSeek 最小请求验收。家庭绑定是本机关系与授权，并非云身份认证。SOS 只提供联系信息，不宣称拨号/救援送达。七主页面与通知/设置均接实际业务接口，空数据按未记录/未知呈现。

产品业务与用户路径详见 [Productization Day 方案](../plans/PRODUCTIZATION_DAY.md)。
