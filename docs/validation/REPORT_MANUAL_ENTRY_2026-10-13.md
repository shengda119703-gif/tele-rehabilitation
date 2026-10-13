# 报告原件保留、指标手动录入验收

日期：2026-10-13。基线 main：`2f52d6298df70d871a93f4848540202b1c182f62`。

## 本轮范围

报告上传、保存、下载、回收站和人物隔离保留。取消报告／图片识字、候选结果确认和图片提供商接线，健康指标沿用既有手动表单，保存来源为 `manual`，默认仅本人可见。旧客户端的 `image.parse`／`image.confirm` 明确拒绝；网页 OCR 路由返回 404。历史 `photo` 记录保持原来源，不删除用户数据。训练动作识别、摄像头、语音和其他 AI 能力不在本轮修改范围。

独立退役源码、旧依赖和旧识字文档从 main 撤出，完整基线保存在远端 `archive/pre-report-ocr-retirement-20261013`，恢复方式见[归档说明](../archive/report-ocr-20261013/README.md)。安卓新资产构建清理其生成目录内旧 OCR 资产，不清理用户数据或源目录。

## 实际验证

| 检查 | 结果 | 边界 |
|---|---|---|
| 健康 agent `npm test` | 471 通过，0 失败 | 共享领域回归 |
| `npm run security:check`、`npm run build` | 通过 | 类型检查、桥接产物；初次删除遗留 import/config 引用后修复并重跑 |
| `npm run test:product` | 20 通过，0 失败 | 真正临时持久化服务，包含原件读写、手动来源、人物隔离、旧识字拒绝且提供商零调用 |
| 网页 `node --test mobile_rehab/tests/*.cjs` | 42 通过，0 失败 | 包含手动入口跳转和旧识字控件消失 |
| 手机 HTTP `test_health_completion.py` | 8 通过，2 跳过 | FastAPI TestClient、真实隔离存储；跳过的是可选语音模型／语音合成输入缺失，与本轮无关 |
| 桌面 `test_report_manual.py` + `test_product_window.py` | 10 通过，0 失败 | Qt 离屏实际窗口、真实 Node 桥接；被动训练 Runtime，不代表摄像头实机验收 |
| 桌面报告专项，缩放 1.0 | 1 通过 | 与上一行部分重叠，不相加 |
| 安卓 backup-current / video-current / barbell / deepseek / care-local 专项 | 29 通过，0 失败 | 本地 JS 逻辑，未构建 APK 或真机运行 |
| `bundle_product.cjs` | 通过，60 个领域模块 | 生成安卓本地领域 bundle，非 APK |
| JS 语法、相关 Python 编译、`git diff --check` | 通过 | 不替代实际接口／UI 验证 |

报告测试仅用 TEST 合成资料。上传不会新增健康事件；手动记录体重 63 kg 后，持久化、重新读取均为 `manual`，其他本人账户不能读取原件或指标。Qt 实际渲染生成浅色／深色、窗口请求 800×600 和 1100×760、缩放 1.0／1.5 的 12 张截图；窗口最小尺寸约束可能使实际尺寸大于请求。已查看代表性报告页与手动录入页截图。截图在本机 `AppData/Local/AnkangChecks/report-manual-20261013/screenshots`，不提交测试产物。

## 环境与交付边界

首次官方依赖下载超时；镜像 PySide6 下载校验不匹配被 pip 拒绝，没有绕过校验。随后官方源 PySide6-Essentials 6.9.3 安装成功，补齐本轮测试依赖后完成桌面实际验收。pytest 首次被系统自动加载的 xonsh 插件打断，关闭无关插件自动加载后测试通过。

本轮是源码修改，没有发布新 APK、重装正常用户运行环境或验证真人摄像头。不把测试环境指定为日常桌面入口；既有版本号与快捷方式沿用原配置。实际使用的 Skills：`pyside6-fluent-ui`（沿用原生 Qt 控件和主题，进行桌面功能与截图验证）。
