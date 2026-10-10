# 0.20.0 安康调度后端验收

日期：2026-10-10；环境：Windows、Node 24.20.0、项目已验证 `.venv-ui-polish` Python。使用隔离 TEST 数据和内存／临时存储，没有写正常患者库、调用真实联网模型或操作真实摄像头。

## 修改与交付范围

共享 TypeScript `CareCoordinator` 已接入 ProductService、原 Runtime 对话、Python 桌面桥接、电脑托管手机接口及独立 APK 后端源码。查询当天安排和原康复下一项；经明确确认写入指定服药记录或修改既有训练日期／时间；支持多步骤状态、逐项回执、持久幂等恢复和执行前事实核对。

医学与路演资料为独立文档，包含九项权威／原始研究来源及适用边界：[医学证据](../plans/ANKANG_MEDICAL_EVIDENCE_2026-10-10.md)。产品解释、前端请求和剩余范围见 [调度接入](../plans/ANKANG_CARE_COORDINATION_2026-10-10.md)。

电脑应用版本更新至 0.20.0。安装包 0.2.1 未重打包。没有修改正式前端，两个原有 CSS 未提交改动保留。前端确认按钮仍待负责同学接入；不会把后端接口通过写成完整页面交互通过。

## 实际测试

| 检查 | 实际结果 | 覆盖范围 |
| --- | --- | --- |
| Agent `npm test` | 425 通过，0 失败 | 原有 412 项及新增 13 项协调测试；最后文本修复后重跑通过 |
| `npm run build` | 通过 | TypeScript 类型检查和桥接构建；最后修复后再次通过 |
| `npm run test:product` | 16 通过 | 持久产品、隐私、用药、家庭、备份和扩展；桥接构建通过 |
| `npm run security:check` | 通过 | 现有硬编码凭据检查 |
| Python 广泛回归 | 321 通过、2 跳过 | 自动计划、原 Runtime、康复读取、产品、桌面托管、全部手机 Python 测试；跳过不计通过 |
| 新真实复合接口测试 | 1 通过 | 广泛回归后新增：指定服药与既有训练改期，经真实 Node/Python 桥接、SQLite 两步执行，重复确认及旧提案冲突保护 |
| 最终托管接口复验 | 12 通过 | 见 `mobile_rehab/tests/test_unified.py`；包含新增复合流程 |
| Android 全部 Node 回归 | 66 项中 65 通过、1 失败 | 新增 12 项源代码级调度测试全部通过；唯一失败为既有 UI 资源 hash 不一致，详见下文 |

Python 广泛回归中的两项跳过来自可选的本地 ASR／OCR 验证条件缺失；没有将这些实际识别能力记为本轮通过。FastAPI TestClient 有现有依赖弃用提示，本轮未扩大为依赖升级。

### 验证过的关键行为

- 准备提案阶段不写入服药记录或日程，伪造 token、`confirmed: false`、其他 owner 和其他来源不能执行。
- 原药物、用药安排、指定次数、训练日程或计划版本变化后拒绝旧提案；其他无关记录变化不误阻塞。
- 两步骤顺序执行；部分失败保留已经提交的事实，不把未执行项写成成功。
- 同一执行编号重放、并发确认、宿主已写入但回执丢失，均不重复生成业务写入。
- 十五分钟确认期限；已提交回执可恢复，过期后未发生的操作不能继续写入。
- 重新启动产品服务后待确认任务可继续核对；清除本人记录后旧 ID 失效。
- 导出审计不包含 token、请求签名和完整 expected 事实；APK 备份／恢复不复活执行批准。
- 文本否定、无需／无须、他人、假设、引述、举例被澄清；“阿托伐他汀”不会因药名中的“他”误拦。
- 今天改明天、原 14:00 改 16:00 分别定位；含糊午夜、未支持的分钟表达和歧义日期不猜测。
- 私密／不记录对话保留原处理路径；原症状、安全、漏服、纠正和分享路径优先。

## Android 唯一失败与保留文件

进入本轮前，`mobile_rehab/static/unified-polish.css` 与 `unified.css` 已有用户未提交修改。APK 的既有 UI lock 针对旧发布资源；测试 `new APK bundles original domain rules and unchanged official UI assets` 比较当前 CSS 与旧 lock，得到：

- 当前 hash：`9279c2f4b835abef827c8aa5796ed763bd5a02a2304d168d2cfe5cdc90f1c7d0`
- 旧 lock：`7c0b6fd1aab38a6ba0e5a3f1f507a211b91113fb0fb785925ed35c26c19b04de`

该失败在新增调度前就存在。本轮未修改 CSS、HTML、UI lock 或打包新安装包，未通过重写预期值掩盖失败。仅刷新忽略的本地后端 bundle／适配资源。前端整合与打包阶段需要由实际 UI 状态重新验收。

## 执行方式与证据位置

Agent 目录执行：

```text
npm test
npm run build
npm run test:product
npm run security:check
```

Python 使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、仓库根为 `PYTHONPATH`、`QT_QPA_PLATFORM=offscreen`，在应用目录执行：

```text
../.venv-ui-polish/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_automatic_plans.py tests/test_automatic_runtime.py tests/test_rehab_read_tools.py tests/test_product_assistant.py tests/test_product_recovery.py tests/test_product_phone_host.py tests/test_product_completion.py tests/test_product_module_paths.py tests/test_daily_store.py tests/test_care_host.py ../mobile_rehab/tests -q
```

广泛回归之后新增复合接口测试，单独执行 `../mobile_rehab/tests/test_unified.py -k compound -q`，随后最终重跑整个 `test_unified.py`。Android 在仓库根运行 `node --test android_offline/tests/*.test.cjs`；新增测试直接编译当前 TypeScript 源码，不靠旧 APK bundle 假称接入。

运行日志位于仓库外、忽略的工作区 `.runtime/`：`care-tests-ts-20261010.log`、`care-regression-python-20261010.log`、`care-api-final-20261010.log`、`care-android-tests-20261010.log`。产品扩展／安全和新增单项结果保留在本轮执行输出。

## 未测与仍未实现

没有真人测量准确度、实机 APK 新流程、真实外部模型、外部通知、后台定时提醒、临床疗效或商业收入验证。本轮没有新增自动给药、诊断或自动训练启动。

桌面串行桥接的模型等待问题仍存在；多进程共享数据目录的工作流登记竞争未验证。当前工作流／回执分别有 200／1000 条上限，尚无独立归档管理入口。APK 原进度核查与桌面适用性核查能力不同，不能把同名 `care.next` 写成临床规则完全相同。

这些边界不影响本轮已验证的有限调度流程，但路演应展示已测表达和实际回执，并明确安装包与前端接入状态。
