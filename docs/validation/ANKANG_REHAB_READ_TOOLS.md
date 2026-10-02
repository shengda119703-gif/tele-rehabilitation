# 康复助手只读能力验收

日期：2026-10-01。分支 `codex/rehab-agent-stage1`，核实基线 `a3ed36b60eec3bee9cbc0f54931dc7c1de380aa0`；fetch 后相对 origin/main ahead 22 / behind 0。没有 merge main。

接口、数据字段、身份映射、配置与架构见[只读工具设计](../plans/ANKANG_REHAB_READ_TOOLS.md)。

## 本轮实测

| 验证 | 结果 |
| --- | --- |
| Python 相关回归 | 103 passed：新只读工具 4 项、原助手 2 项及 training_hub/product_navigation/app_assessment/training_feedback/saved_training_plans |
| Runtime 相关测试 | 20 passed：新 2 项，原 Runtime 与传递依赖测试；含原 12 轮 React parity、并发、reset/close、更正、午夜、失败回退 |
| TypeScript | `tsc -b`、测试编译与 bridge build 通过 |
| 保留的 React 应用 | Vite production build 通过（173 modules） |
| 原 offscreen smoke | 启动、助手、两轮、Enter 去重、participant 隔离、真实 Node 终止/恢复、原页面与资源退出全部通过 |
| 只读证据 | 合成 SQLite 在三项读取及多轮 UI → Runtime → tools 后 SHA256 不变；不存在库不创建；无写工具 |

`tests/test_rehab_read_tools.py` 的 offscreen 测试使用真实 AssistantDialog/AgentBridge/Node/AgentRuntime 与临时 SQLite；**模型是本机 HTTP 协议替身**，只用于确定性验证选择与回执链路。未使用真实患者或真实模型 API，未验证自然语言模型在任意问法下的准确率。

三个示例的实际回执：

| 问题 | 实际读取 | 测试模型显示的回复 |
| --- | --- | --- |
| 我今天练什么？ | 已保存的合成自动计划；原进度显示已完成 1 项、下一项 shoulder_flexion:left | 合成测试计划：临时演示 · 评估生成训练计划；下一项：shoulder_flexion:left |
| 我最近肩膀怎么样？ | `joint=shoulder`，最新肩前屈/肩外展评估，含原投影范围与条件 | 合成测试评估：肩前屈、肩外展；未作临床改善判断。 |
| 我上次训练完成得怎么样？ | 原肩外展训练完成 3 次，独立反馈 pain=0/fatigue=2/notes=合成反馈 | 合成测试训练：肩外展；完成 3 次；反馈：合成反馈 |

还验证了：更换 participant、source_kind、usage_context 均返回空；UI 换来源/换人从 revision 1 开始；普通聊天可继续；过期自动计划不会显示 next_available=true；模型不能指定 owner 或调用 start_training；private/no_record/紧急安全回合不会进入 rehab 模型或数据 port。

## 复现

route1 目录：

```powershell
node scripts/build-agent-bridge.cjs
node node_modules/typescript/bin/tsc -b
node node_modules/typescript/bin/tsc -p tsconfig.test.json
# .test-build/package.json 沿用原 npm test 生成的 type=commonjs
node --test .test-build/tests/rehab-runtime-tools.test.js .test-build/tests/runtime.test.js .test-build/tests/runtime-dependencies.test.js
node node_modules/vite/bin/vite.js build
```

康复 app 目录，在已有 PySide6/pytest 的隔离 Python 环境中：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest tests/test_rehab_read_tools.py tests/test_ankang_assistant.py tests/test_training_hub.py tests/test_product_navigation.py tests/test_app_assessment.py tests/test_training_feedback.py tests/test_saved_training_plans.py -q
python scripts/smoke_ankang_assistant.py
```

本机额外通过 `PYTHONPATH` 指向既有 `.runtime/ankang-cleanup/python-deps` 以补齐测试环境 pygments；未安装新依赖。Node 24.20.0 满足项目 Node >=22 要求。测试不依赖真实模型环境：临时 loopback endpoint 配置由 pytest 恢复。首次测试发现合成反馈 reason 空串不符合原校验，已将夹具改为原 `not_recorded`，没有放宽生产校验。

## 改动与限制

- 新增：Python `app/rehab_read_tools.py`、TS `src/runtime/rehabTools.ts`、host `scripts/rehab-model.cjs`、两端相关测试、架构/验收文档。
- 修改：原 `client.py` / `agent-bridge.cjs` 支持同通道读取回调；Runtime 可选工具 port；助手捕获 scope、提供 host reader、提示缺模型；MainWindow 注入现有库路径。
- 原康复算法、存储 schema、计划生成/评估/反馈业务函数及安康 understanding/agent/services 均未修改；未连接任何康复写能力或家属通知。
- 本机尚未配置真实 LLM；默认启动只保留原安康规则聊天并提示工具未启用。真实模型端到端验收仍待模型配置，不宣称本机已可用真实模型回答康复数据。
- 未跑全项目/全部浏览器/硬件测试；本轮没有打开摄像头。构建产物、临时数据库、模型密钥不提交。

最终提交 SHA 与远端同步/工作区状态在交付消息报告，避免在同一提交中自引用 SHA。完成后停止，等待审核。
