# PR13 V2 开发检查点，2026-10-19

**工程尚未完成，不建议合并 main。** 这是可恢复检查点，不是最终验收通过。没有后台续跑任务；下一次必须从此检查点继续。未完成项既有内部工程缺口，也有外部验证条件，不能统称外部阻断。

仅目标分支 `codex/unified-llm-entry-20261015`、[PR #13](https://github.com/shengda119703-gif/tele-rehabilitation/pull/13)。本轮先将该分支快进到远端 `06a8650b196991564cce431ec88d4b48c66df8a1`，未合并 main、未部署、未访问或修改真实患者数据库。

## 已提交的三轮代码

| 提交 | 改动及边界 |
|---|---|
| `7ae128f721eda49652049960b881611ecb73ce2a` | 自然语言候选重新连接真实检索/分析/校验；本地任务持久化、器材追问、重开、取消和过期；来源回传、剂量拒绝；既有云规则候选绑定资料/授权版本、审核内容摘要及持久回执；修复旧三问口语读取。云回执仍不是 AI 可执行方案批准。 |
| `f64a52916de5c3d873859204527f95a63cef25ee` | 明确改名→本地解析→真实预览→确认→Host/SQLite→写后重读；唯一当前计划与 revision 约束；未验证保存时不声称成功。仅改名称，不代表自然语言剂量/动作/时间修改完成。 |
| `02c0eb638163fa0edaeeced300514b49273ef41d` | 多轮明确不可用器材冲突拦截；后续明确更正生效；第三人、假设及不确定语句不授予可用性；区分卡片可选器材。仍不是完整个人限制或临床许可解析。 |

所有代码提交已推送目标分支。报告提交的 SHA 可由 `git rev-parse HEAD` 取得；`run-manifest.json` 的 source_head 指已测源码，文档提交不会改变该源码。

## 当前验收

原始 77 项完整逐行结果及新增 UX01–UX12 见 [STATUS.md](pr13-v2-evidence/STATUS.md) 和 [status.json](pr13-v2-evidence/status.json)。原编号、历史结果及限制保留；不把历史 PASS 自动继承为当前 PASS。

原 77：33 PASS、10 PARTIAL、13 NOT IMPLEMENTED、20 UNVERIFIED、1 FAIL。新增 UX：4 PARTIAL、4 NOT IMPLEMENTED、4 UNVERIFIED。PASS 是对应节点限定范围的证据，绝不代表整个客户端/临床/模型通过。

| 实际执行 | 结果 | 限定 |
|---|---|---|
| Agent `npm run ci` | TypeScript 582/582，product 36/36，build/security 通过 | 模型用可识别 fixture，非真实 DeepSeek |
| Python 实际 Host、Node 桥、SQLite | 23/23 | 临时合成数据；包括改名前不写、确认写一次、重读/重开、scope/revision/竞态与医生处方保护 |
| 云服务测试 | 76通过，4跳过 | 本地测试库；PostgreSQL四项无环境，未部署 |
| 配对网页 JS | 124/124 | 静态/逻辑回归，不代替浏览器验收 |
| Android资源与 JS | 资源准备、72模块 bundle成功；85/85 | 仓库根目录执行；不是 APK 安装或真机 |
| 实际 Qt | 六页及离线聊天通过；真实 app.main 截图启动退出0 | 隔离 TEST、offscreen、无摄像头/模型；页面探查使用 PassiveRuntime，真实主启动单独执行 |
| 实际浏览器 | TEST配对、导航、离线回复、刷新保留消息 | [操作记录](pr13-v2-evidence/browser-review.md)；未测 AI 采用展示 |
| 扩展桌面 | FAIL；定向首错复现4通过1失败 | 全部产品测试运行至48%出现10个F，之后长时间无输出而中断；无完整总数/JUnit，不冒充跑完。单独首错日志/JUnit另存 |

扩展桌面首错：`tests/test_product_assistant.py:90` 的 `test_medication_shortcut_edits_draft_only_and_explicit_send_keeps_privacy` 找不到 `product-201`，抛 `StopIteration`。源码正式助手已移除旧模块操作快捷入口；需核对退役合同、实际页面与替代入口后处理。未修改断言、删除测试或恢复已退役操作来制造绿色结果。全套停滞原因和其余失败尚未逐项定位，仍是内部待办。

本轮通过日志、真实截图、JUnit及修复前失败日志在 `pr13-v2-evidence/`。`run-manifest.json` 记录运行命令、环境、源码/证据 SHA256；未提交合成数据库或凭据。

## 主链尚缺，下一轮先做

1. `src/rehab/workflow.ts`：个人限制/评估可信来源解析仍缺；`screening_confirmed` 不能由模型或普通自述变成许可。现有只读端口为 `app/rehab_read_tools.py`，不要把原始个人记录放进外部模型提示。
2. `src/rehab/taskState.ts` 当前只存本地任务原话与草案；重开会丢弃草案验证 authority 并重走校验。补具有内容摘要、版本、scope、来源证据的持久 AI draft 存储与提交接口，而不是把当前聊天文本当已批准计划。
3. `cloud_service/rehab_workflow.py` 现有 `RESOURCE_CANDIDATE_REVIEW` 明确 `execution_approved=false`。下一轮须复用认证/医生授权边界，将 AI draft 精确内容、映射动作及待批准剂量绑定专业审核。现有 receipt 不可升级或挪作执行批准；资料/授权/内容版本变化必须失效。
4. 接专业批准特定版本→患者明确确认→新计划 create/adopt→事务保存 ID/revision→权威重读→患者页面显示与重开。当前完全没有本链路。不要从 `needs_review` 直接保存、伪造医生或复制通用剂量。
5. `exerciseMapping.ts` 仅 T-LOW-003→knee_extension、T-LOW-017→sit_to_stand 两个技术映射。无腰椎起始模板，不承诺4–5动作；适用性、具体剂量和负荷须真实核验。
6. `programOperations.ts` 目前只完成非常窄的本人唯一计划改名。动作/剂量/时间的授权本地解析和预览仍缺；提醒调度和联系医生/预约工具仍缺。不能用日程记录冒充系统通知。
7. UX01欢迎快捷问、UX03可信记录免重问、UX08提交审核/调整草案控制、UX09/12完整闭环，以及独立手机Host、跨端权限变化仍需实现。保留默认语义 flag 关闭。
8. 定位扩展桌面剩余失败及停滞，复跑手机 Python/真实视觉回归。不能把旧失败数或当前124个JS测试当其验证结果。

## 真外部条件

- 本轮用布尔检查确认当前环境无可用 DeepSeek配置。未额外获取凭据、未调用付费真实模型；所有协议 fixture 明确标识。真实多轮指代、口语/检索、核心端到端质量仍 UNVERIFIED。
- 无 PostgreSQL测试环境、Android/iOS/Watch真机与相关授权，没有本轮APK安装、HealthKit数据或临床批准证据。未授权部署公网。
- 环境包含 PySide6/numpy/OpenCV 基础依赖，但没有本轮安装或验证人体模型权重。摄像头与真实视觉结果不计通过。

## 复现与恢复

工作目录：`康复2/tele-rehabilitation-pr13`。独立 `.venv-agent-v2` 已建立，忽略提交。所有验证使用 SYNTHETIC / TEST 数据。

```powershell
git status --short
git branch --show-current
git fetch origin codex/unified-llm-entry-20261015
# 先核对本地状态和远端，不重置未知改动，不切 main。
Set-Location ankang/route1-health-agent
npm run ci
Set-Location ../..
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH=(Join-Path (Get-Location) 'rehab_codex_single_camera_v2_1')
./.venv-agent-v2/Scripts/python.exe -m pytest rehab_codex_single_camera_v2_1/tests/test_rehab_read_tools.py rehab_codex_single_camera_v2_1/tests/test_rehab_operation_tools.py -q
./.venv-agent-v2/Scripts/python.exe -m pytest cloud_service/tests -q
node --test mobile_rehab/tests/*.cjs
./.venv-agent-v2/Scripts/python.exe android_offline/tools/prepare_assets.py
node android_offline/tools/bundle_product.cjs
node --test android_offline/tests/*.test.cjs
./.venv-agent-v2/Scripts/python.exe tools/qa/pr13-v2-status.py
./.venv-agent-v2/Scripts/python.exe tools/qa/pr13-v2-manifest.py
```

恢复指令：**“读取 docs/validation/PR13_V2_CHECKPOINT_2026-10-19.md，严格留在 codex/unified-llm-entry-20261015，从可信资料/持久AI草案与专业审核连接继续循环开发；不要沿用历史PASS或合并main。”**

## 桌面入口与回滚

按仓库约定更新桌面“安康康复（最新版本）”：指向本开发工作区 `Start-Rehab.ps1`、本轮验证 `.venv-agent-v2/Scripts/pythonw.exe`，使用隔离 `.runtime/SYNTHETIC_TEST_PR13_V2_LAUNCH`，描述明确“隔离TEST开发版，工程未完成”。进入“康复助手”查看；默认语义flag仍关闭。没有更换原患者数据、打开其数据库或关闭旧窗口。旧快捷方式属性只备份在忽略目录 `.runtime/shortcut-before-v2.json`，不上传其数据路径。

回滚代码：先保存其他人改动，在同一开发分支按 `02c0eb6`、`f64a529`、`7ae128f` 倒序 `git revert`，解决冲突并回归后再推送；不 reset/force push、不碰 main。原患者数据库从未迁移或修改，无生产数据回滚。测试数据和虚拟环境可保留供复现；恢复桌面入口时用本地备份属性，不能删除或覆盖真实患者目录。
