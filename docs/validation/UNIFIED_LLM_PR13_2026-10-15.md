# PR #13：统一 LLM 理解架构测试与修复

验收日期：2026-10-15。结论：**PARTIAL PASS，保留草稿和默认关闭，不满足完整闭环的合并验收条件。**

仓库：[tele-rehabilitation](https://github.com/shengda119703-gif/tele-rehabilitation)。PR：[#13](https://github.com/shengda119703-gif/tele-rehabilitation/pull/13)。开发分支：`codex/unified-llm-entry-20261015`。

本次代码提交：`6c1a7771e020526b82dacf2d0185d16577a0cd02`。审查基准为原 PR HEAD `d791650a7ca72b66ac4e6171841fc6ced4a0b9da`，当时远端 main 为 `8f1fc2c706504f4119fb9bad984ab9ded87aa86d`。原本机 main 为 `cccfd28b68f2e97627f2f7d0ab940f4803105c14`，工作区干净。本轮在单独工作树完成，未切换或修改原 main，未覆盖其他任务改动，未部署、未合并、未更换桌面入口。

开始前检查了其他 Codex 聊天的状态；相关开发聊天没有正在修改本仓库。后续使用本任务的三个子代理分工审查协议、宿主接线和测试，共享工作树按文件分工，无其他用户聊天被发送消息。

## 1. 原 PR 审查结果

检查了原 PR 全部四个文件的 Diff，及 ProductService、桌面／手机桥接、云账号和模型传输的实际调用方。

| 严重性 | 原问题 | 后果／验证依据 |
| --- | --- | --- |
| P1 | `rehabAssistant` 特殊分支覆盖新路由，正式 ProductService 未传入开关、理解模型和读工具 | 仅直接 Runtime 可配置；真实助手入口不能完成新链路 |
| P1 | 新层仍调用普通聊天模型策略，云适配丢失任务用途 | 系统要求自然语言回答，与 JSON 解析契约冲突 |
| P1 | 把模型工具建议当成授权，绕开原 `canUseModuleTools` | 原代码动态 Mock 复现“查看张三的训练记录”却调用本人计划读器 |
| P1 | 把个人工具输出交给最终模型重写，且没有结果约束 | 原代码 Mock 复现个人记录外发、空结果被改成“已完成十次训练” |
| P1 | 理解 JSON 校验弱，无法可靠表达否定、假设、多人、多意图和跨轮来源 | 字段合法不代表可以当作健康事实或工具权限 |
| P1 | 解析完成后仍走旧理解／回复路径，结果未贯通事件处理 | 增加模型调用却未保证语义生效；例如“没那么喘了”仍可能作为发生事件 |
| P2 | 最终回复和回退缺少内部 JSON／虚构回执检查 | 模型 JSON、工具字段或未执行的记录／共享承诺可能显示给用户 |
| P2 | 只增加解析器测试，没有正式入口、宿主和工具闭环证据 | 编译或五个 JSON 单测不能证明实际产品可用 |

## 2. 实际修复

| 文件／范围 | 修改 |
| --- | --- |
| `ankang/route1-health-agent/src/runtime/semanticRouter.ts` | 保持 v1 兼容；严格白名单、长度、枚举、参数和原文来源校验；补 `intents`、`tool_requests`、症状状态／主体／时间原词、`correction_of`；仅允许本会话获准外发的原始用户上下文 |
| `runtime/session.ts`、`runtime/semanticExecution.ts` | 隐私检查后先理解，成功后执行新链路；适配正式只读助手；理解／工具／回复分阶段 trace；去重工具请求；验证最终文本并在失败时本地回退；关闭旧的重复理解调用 |
| `runtime/semanticLegacyAdapter.ts`、`runtime/turn.ts` | 复用既有 `mergeClauseStatus`、理解规则和 `runDetection`，把有完整原文证据的极性传回原流程；主体冲突、混合或不完整证据先澄清；既有急症事实和处置保留；不新增症状标签或医学规则 |
| `runtime/rehabTools.ts`、`rehab/assistant.ts` | 校验工具名、参数、只读回执及本人归属；接现有计划／历史／评估读器；公共卡片与现有通用康复资料真实检索；个人记录本地可读渲染，清除原 JSON 直出 |
| `product/ProductService.ts`、`scripts/agent-bridge.cjs` | 正式入口注入开关、模型及本人读器；配置可用性变化后更新 Session；默认关闭 |
| `runtime/conversation.ts`、`scripts/chat-model.cjs` | 增加固定 `understanding/reply` 用途；理解使用专用系统提示及 JSON 输出模式；回复明确先回答问题，不例行追加就医结尾，原紧急处置要求保留 |
| `cloud_service/ai_usage.py`、Python `cloud_account.py`／`product/backend.py` | 云服务及账号传输保留用途；拒绝未定义用途；用途参与幂等核对，重试保留原用途；旧 reply 请求继续兼容 |
| `android_offline/`、`public_web/browser-account.js` | 手机 JS／原生传输及网页桥接传递用途；独立手机构建开关默认 false |
| 新增／扩展测试及 `scripts/verify-semantic-acceptance.cjs` | 覆盖运行时、旧理解兼容、正式宿主、云用途、真实 SQLite 读工具；提供可重跑的合成调用链验收脚本 |

医学决策引擎、动作库正文、训练算法、身份权限及原工具授权语法均未修改。适配器只调整本轮已授权的语言理解和回复调度。正式助手仍不通过聊天保存健康事件、采用计划或操作用药。

## 3. 测试报告

环境：Windows，Node `24.20.0`、npm `11.19.0`、Python `3.12`。Python 缺少的测试依赖安装在隔离测试目录，未写入项目依赖清单或使用真实患者库。需要本机回环端口的测试在允许回环连接的执行环境运行。

| 项目 | 结果 | 证据／边界 |
| --- | --- | --- |
| TypeScript 类型检查、Bridge 构建 | **PASS** | `npm run ci` 内的 `tsc -b`、`build:bridge` |
| Runtime／旧架构／隐私安全单元与集成测试 | **PASS：530/530** | `npm test`；包含语义解析、会话、多轮、否定、重置、工具、旧安全断言 |
| 正式产品及 Node 宿主 | **PASS：34/34** | `npm run test:product`；真实 ProductService、Node 子进程；模型 Mock |
| 密钥扫描 | **PASS** | `npm run security:check`，不代表完整安全审计 |
| Android／网页相关模型与权限测试 | **PASS：24/24** | `deepseek.test.cjs`、`care-local.test.cjs`、`browser-account.test.cjs` |
| Android 领域代码打包 | **PASS** | `bundle_product.cjs` 打包 66 个模块，产物开关 false |
| 云用途、原 beta、云账号、SQLite 和桥接 | **30 PASS、1 FAIL** | 最终同一 Python 测试批次共 31 项；保留失败，详见下文 |
| 三项真实 SQLite 读器的新语义桥接 | **PASS** | Mock 理解 → 真实 Python／Node → 实际 SYNTHETIC／TEST SQLite → 本地回执；数据库 SHA256 前后相同 |
| 合成对话调用链 | **PASS：21/21** | 32 次 Mock 模型调用，真实公共知识检索；个人记录端明确为 Mock Host |
| 真实 DeepSeek | **UNVERIFIED** | 计划 17 组，实际调用 0；未发现可用现有配置 |
| Android 全量资源依赖测试 | **FAIL：42 PASS、14 FAIL** | 独立工作树缺少生成的 `catalog.json`、`ui-lock.json`、`lin-profile.json` 等资源；未把专项通过当作全 APK 通过 |
| APK 原生编译／手机硬件、浏览器完整 UI、线上环境 | **UNVERIFIED** | 本次未安装 APK、未运行真人／真机、未部署 |

Python 剩余失败为 `test_real_bridge_three_questions_and_scope_isolation`：旧测试期待“我最近肩膀怎么样？”、“我上次训练完成得怎么样？”直接进入记录工具，但原 PR 的 `canUseModuleTools` 就会拒绝这两句话。逐字比较原／今门禁源码相同，独立执行原／今结果也相同；没有为通过测试删除断言或放宽权限。证据：[原权限语法对照](pr13-evidence/legacy-guard-baseline.json)。这属于既有缺口，仍计为 FAIL，不宣称整个 Python 集成套件通过。

初轮 TokenVault 测试在同步目录出现 Windows `os.replace` 拒绝访问；换到唯一系统临时目录后定点及最终整批均通过，具体占用源未确认。初轮新增测试还发现只读回执与 no_record 回退问题，已修复后完整复跑。no_record 的原 `safetyAction` 标志语义保持原状，同时完整保留原本地停止活动／急救文字，不新增医疗判定。

可复跑命令（在相应项目目录执行，先准备原项目依赖）：

```text
# ankang/route1-health-agent
npm run ci
node scripts/verify-semantic-acceptance.cjs --output <mock-evidence.json>
node scripts/verify-semantic-acceptance.cjs --real --output <real-evidence.json>

# 仓库根目录
node --test android_offline/tests/deepseek.test.cjs android_offline/tests/care-local.test.cjs public_web/browser-account.test.cjs
node android_offline/tools/bundle_product.cjs
python -m pytest cloud_service/tests/test_ai_purpose.py cloud_service/tests/test_beta.py rehab_codex_single_camera_v2_1/tests/test_cloud_account.py rehab_codex_single_camera_v2_1/tests/test_rehab_read_tools.py -v
```

本机 Python 通过隔离 `PYTHONPATH` 提供依赖，使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`PYTHONNOUSERSITE=1` 和唯一系统临时目录，避免全局 pytest 插件和同步文件占用影响。旧流程复跑明确设置 `ANKANG_SEMANTIC_ROUTING_ENABLED=0`，新桥接 fixture 在自己的子进程设置为 1。

## 4. 模型验收与完整调用链

没有真实模型成功或失败案例；可用性检查未发现现有本机直连密钥、环境密钥或默认宿主云账号会话。没有遍历任意自定义数据目录，也未建立合法本人云端会话。没有要求把 API Key 写入仓库；`--real` 没有发送请求，逐组记录为 UNVERIFIED。

以下均为**合成输入和 Mock 模型**，不能证明 DeepSeek 的理解质量、自然程度或医学正确性：

| 案例 | 实际链路与结果 |
| --- | --- |
| “你好，陪我聊聊旅行吧” | 理解 JSON → 校验 → 无工具 → reply 模型；2 次 Mock 调用 |
| “肩外旋怎么做” | 理解 JSON → `rehab.search_knowledge` → 实际动作卡 `T-AXU-023` 等 → 资料进入 reply 请求 → 模型回答，附原开始／停止条件 |
| “L0和L2等级是什么意思” | 理解 → 检索现有分级说明 → 原文进入 reply 请求 → 模型回答 |
| “查看我的训练计划／训练记录／最近评估结果” | 理解 → 原授权门禁 → 真实宿主读工具（另有真实 SQLite 测试）→ 本地格式化；个人结果未进入模型 |
| 多症状、否定、假设、不确定、多轮纠正、指代、多意图 | JSON 保留相应信息和原文来源；适配保留旧事实／安全规则，不能确定时不写事实 |
| 工具失败、返回其他用户、空记录 | 失败／隔离／空结果明确显示，没有改成成功或编造记录 |
| 无效 JSON、网络错误、不存在的工具、虚构“计划改好了” | 拒绝无效提议或输出，回到本地／旧流程；故障注入测试通过不代表真实服务无故障 |

证据文件均已去除密钥及真实身份，仅包含合成测试信息和公共资料：

- [21 组完整请求、模型响应、公共检索载荷、工具回执、trace、最终回复和逐项断言](pr13-evidence/mock-dialogues.json)。公共工具结果同时存在最终请求中，并单独记录其 SHA256；个人 Host 的模拟性质有明确标记。
- [真实 DeepSeek 可用性与 17 组 UNVERIFIED 清单](pr13-evidence/real-model-availability.json)。
- [真实 SQLite 跨 Python／Node 三工具 trace](pr13-evidence/sqlite-tool-traces.json)。数据库为实际隔离库，数据来源为 SYNTHETIC／TEST；模型仍为 Mock。
- [最终计数、环境、限制及本机原始日志 SHA256](pr13-evidence/test-summary.json)。原始运行日志位于工作树旁的 `build-pr13/`，未作为患者数据或线上成功凭据。

## 5. 入口与架构核对

成功解析时的顺序为：隐私门禁 → LLM 理解 → 严格 JSON／原文证据验证 → 既有事实与安全处理 → 工具候选与授权／参数验证 → 真实工具执行 → 回执验证 → 公共资料 LLM 回答或个人资料本地回答 → 一次性应用计划。

解析超时、无效 JSON、不可用模型走本地／原逻辑；不会重复调用旧的理解模型。普通聊天和公共知识通常各 2 次模型调用（理解、回答各一次）；个人记录与已有安全处置通常只调用理解一次；隐私回合零外发。成功后的健康变更只调用一次 `applyTurnPlan`。工具去重、会话重置丢弃迟到结果、上下文按用户及来源情境隔离均有回归测试。

| 入口 | 状态 |
| --- | --- |
| 普通 `AgentRuntime`／`agent-bridge open` | 已接通，真实 Node 子进程 Mock 测试 PASS |
| 桌面康复助手／底部普通聊天 | `ProductWindow → ProductBackend → AgentBridge → ProductService` 已接通；领域及桥接测试 PASS，未做真实 UI／模型验收 |
| 电脑配对手机及健康管家 | 共用上述 ProductBackend，源码贯通；未进行完整浏览器 UI 验收 |
| 独立 Android | `local-api → ProductService → PhoneDeepSeek → native/cloud` 已接线；JS 与打包 PASS，原生 APK／真机 UNVERIFIED |
| 独立 public_web | 共用 ProductService／local-api，云传输用途已验证；未部署及端到端 UI 验收 |
| 旧独立 Python 手机服务 | `mobile_rehab/product_host.cjs` 明确禁止继承远程模型，仍为本地 ProductService；保持其隐私边界，**未接入统一 LLM** |
| 云 `/ai/requests` | 作为用途明确的模型传输层已验证；不在云端执行本地康复工具 |

因此不能宣称全部聊天入口已经完成统一 LLM 闭环。

## 6. 遗留限制

1. **个人记录没有交给 LLM 最终组织回答。** 现有授权允许用户主动聊天和公共知识，不包含已存健康记录外发。本次保持这一边界，使用真实工具结果本地展示。若要求个人数据也走最终 LLM，需另行设计并授权对应数据范围，不能仅靠改 prompt。
2. 原工具授权语法仍会拒绝部分口语、多意图和跨轮“再看那个”查询；模型建议不会扩大权限。知识多意图可解释，个人查询需要明确表达。本次未为方便调用放宽权限。
3. 其他业务模块的通用工具目录尚未接通，已退役 Agent 写操作未恢复；没有伪造模块执行结果。
4. 旧 v1 JSON 省略状态时仍兼容本地规则；新模型字段不直接生成新的医疗事实标签、主体或日期。复杂混合症状可能要求澄清，跨轮来源也不等于更正权限。
5. 语义上下文只保留本会话有限原始用户输入，不携带个人工具结果或恢复旧持久会话全部历史；输入、上下文和输出有长度上限，超限可能回退。
6. 模型结果检查能拦截已测内部字段、虚构操作回执和若干越界表达，不能证明所有自然语言改写都无幻觉；不能据 Mock 宣称已经解决“总推荐就医”的真实体验问题。
7. 理解等待上限 15 秒，最终回答等待上限 25 秒。Runtime 丢弃迟到结果，但通用模型接口尚无取消信号，底层请求可能继续结束或计费；云端保持原回执／重试门禁，不能把超时当作免费或成功。
8. 真实模型、未部署的云用途支持、完整设备／UI 验收及上表既有失败仍未解决。必须保留默认关闭。

## 7. 回滚与恢复旧路径

桌面／Node：删除 `ANKANG_SEMANTIC_ROUTING_ENABLED`，或设置为 `0`，重启该开发版本进程。只有精确值 `1` 才开启。直接创建 ProductService／AgentRuntime 的调用方省略或传 `semanticRoutingEnabled:false`。

独立 Android／网页：构建时不设置该环境变量或设为 `0`，重新生成领域包；产物 `AnkangSemanticRoutingEnabled=false`。本轮没有改动已安装应用或线上开关。

用途字段缺省仍是 `reply`，兼容旧云请求；旧数据、算法和权限不需要迁移。开关关闭会恢复原调度，不会删除既有记录。若需撤销全部代码修复，可在开发分支对 `6c1a7771e020526b82dacf2d0185d16577a0cd02` 执行 `git revert`，保留审计历史；不重置或强推 main。

## 8. 合并建议

**暂不按“统一 LLM 全部完成”合并，保持 Draft／默认关闭。** 本次已经证明普通聊天、公共知识和三项实际读工具有可运行链路，也修复了原 PR 的入口、授权、数据外发和回退问题。但真实 DeepSeek 未验收、个人结果仍本地回复、旧独立手机入口与其他模块未接通，且仍有已记录的旧测试和构建资源缺口。满足用户要求的完整验收前，状态应持续为 PARTIAL PASS。
