# 安康工作台隔离验收 · 2026-10-13

源码基于 main `e2e256e`，选择性复用云分支 `1ad275a`；开发分支 `codex/workbench-20261013`，变更见 [PR #5](https://github.com/shengda119703-gif/tele-rehabilitation/pull/5)。版本为电脑0.24.0、Android0.4.0/code40、云服务0.2.0/schema2。

## 已实现的三条流程

| 流程 | 实际实现与验收范围 |
| --- | --- |
| 患者保存 → 授权上传 → 医生查看 | 读取原产品档案和原康复数据库，上传已保存评估、训练与反馈、计划；先绑定本人、同意同步，医生每次读取检查授权。修订保留原事件，缺测不补成数值；暂停同步和撤销医生授权分开。 |
| 患者发文字 → 医生回复 | 服务端持久消息与各账号读游标；客户端持久待发编号和内容，刷新、中断与断网后重试，同一操作不重复保存。医生多标签页不能覆盖另一个待发操作，也不能用较早回执清掉新的待发消息。 |
| 医生草稿 → 确认发布 → 患者核对并采用 | 53个实际支持动作与结构化设置；医生草稿可编辑，发布版本不可变，改版新建草稿。患者核对当前本人评估、来源和测量契约，云端回执前保留不可训练的待确认计划，回执恢复后再次检查最新采用版本和本地规则。聊天不执行计划修改。 |

独立手机沿用原本地二维分析与训练规则；电脑沿用原 SceneController/Storage/TrainingEngine。原185张动作资料卡供问答，不能把资料卡自动当作当前软件可执行动作。

## 测试环境与已取得结果

全部记录和账号为虚构 TEST 数据。本机临时数据库、浏览器、图片与构建中间产物位于忽略目录 `.runtime/`。云端浏览器服务只监听127.0.0.1；测试脚本拒绝公网地址。CI 的 PostgreSQL16 数据库名限定为 `ankang_cloud_qa`，随作业创建和移除，不连接现有服务器。

| 执行项目 | 结果 |
| --- | --- |
| 本机云端 Python 测试 | 59通过，4项PostgreSQL专项在本机跳过；仅1项现有Starlette/httpx弃用提示。 |
| 首轮 GitHub CI：云端 + 实际 PostgreSQL | 63通过，无跳过；包括并发发消息、授权撤销与写入串行化、修订同步、旧schema迁移保留账号和授权。见[实际作业](https://github.com/shengda119703-gif/tele-rehabilitation/actions/runs/38399600614)。 |
| 核心实现提交 `533efd2` 的 GitHub CI | 63项Python测试、8项网页／传输Node测试通过；[实际作业](https://github.com/shengda119703-gif/tele-rehabilitation/actions/runs/38404432319)。 |
| 原评估、训练执行、计划、产品窗口与精简康复AI回归 | 240通过；此轮运行在待确认状态修补之前，后续另跑受影响专项，不能相加为新覆盖数。 |
| 原产品 Node 回归 | `npm run test:product` 24通过，含报告OCR和旧Agent保持退役。 |
| 最终原生账号、协作、保存计划、实际开始与产品窗口专项 | 82通过、4个子测试通过；含两实例同时刷新登录、令牌原子写入、回复丢失与队列恢复、真实ProductBackend配对同步／采用、待确认不能训练、最新失败评估／过期评估实际启动阻止、迟到旧方案回执不激活。[原日志](workbench-20261013/native-tests.txt)。 |
| 最终受影响原训练与计划规则 | `test_saved_plan_runtime.py`、`test_training_execution.py`、`test_automatic_plans.py` 179通过。与之前240项有重复，不累计作为总覆盖。 |
| 最终手机JS回归 | 82通过，0失败、0跳过；含采用医生方案后的备份往返、待确认不可训练、断网／重开恢复、云档案旧页面覆盖阻止，以及原生RPC跨页面／账号迟到回复隔离。[原日志](workbench-20261013/android-tests.txt)。 |
| 桌面入口 | 原 `app.main --data-dir <隔离目录> --screenshot <文件>` 与实际pythonw分别启动、离屏抓图和自动退出成功；未打开摄像头、未使用原个人数据。 |
| 医生网页与账号适配Node专项 | 8通过（两份测试文件的总数，不累计重复执行）。 |
| 原手机页面显示与交互回归 | `mobile_rehab/tests/test_unified_presentation.cjs` 8通过，与上一行是不同测试。 |
| 最终真实Edge浏览器端到端 | 17项流程全部通过，零页面错误；[机器结果](workbench-20261013/result.json)。包括实际安康患者界面、离线缓存消息、刷新恢复原待发编号、回执丢失后重试去重、未读保持、医生多页迟到回执保护、草稿冲突保留输入、患者无评估禁止采用、撤销授权清空医生已加载资料，以及患者第二页实际20秒轮询／读消息不能覆盖第一页面的待发文字和待确认方案。 |
| 最终公共网页构建 | 0.4.0，39项资产、2个页面、41,436,519字节；未打包TEST档案。manifest SHA256 `883e5d7409142a65fd6d6ab4acb3781c5cc7cb6aadc1df17a0a9bc357ed4c2cc`。 |
| 最终QA APK | 0.4.0/code40，21,524,282字节；Java→DEX、资源打包、ZIP校验、对齐与v3验签通过，包装测试3/3通过；293个源码输入构建前后未变，包内本地JS逐字匹配冻结源码。详见[构建回执](workbench-20261013/qa-apk-build-receipt.json)。 |

QA APK SHA256为 `c8231a17d14a8cb9d78a7cfa0e5455a6a2a2c2fc3c674252939553fe1c11da36`。本地交付在 `.runtime/qa-apk-delivery/ankang-workbench-0.4.0-qa.apk`，没有上传密钥、安装到设备或发布到生产。使用本轮独立QA证书，不能覆盖原发行签名的已安装App；不能通过卸载原App来无备份地替换真实个人数据。

默认并行签名曾出现Unexpected EOF；保留失败日志后，同官方SDK对新输出以 `-XX:ActiveProcessorCount=1` 重试、完整验签和包装检查通过，底层原因未确认。旧首轮产物标为superseded，不作为最终包。

桌面原快捷方式指向另一份旧代码目录。本轮新增启动器 `-DataDir` 参数，让新代码入口继续使用原资料目录；只核对旧文件存在，未打开或改写原数据库。捆绑Python和原有完整Python环境均以独立QA数据目录启动、截图和退出成功；快捷方式更新时复用原完整环境。旧窗口不会被关闭。

## 实际界面截图

以下均为真实运行界面的虚构TEST资料，未含真实患者信息；不是设计图。

| 界面 | 截图 |
| --- | --- |
| 医生查看保存的评估、训练反馈与本地计划 | [医生记录页](workbench-20261013/doctor-saved-records.png) |
| 医生选择实际动作、设置组次并保存草稿 | [医生计划编辑](workbench-20261013/doctor-plan-editor.png) |
| 患者安康中查看聊天历史与回复 | [患者工作台聊天](workbench-20261013/patient-ankang-chat-mobile.png) |
| 未有有效评估时，阻止采用医生方案 | [采用规则反馈](workbench-20261013/patient-ankang-plan-blocked-mobile.png) |
| 医生及账号页面窄屏布局 | [医生窄屏](workbench-20261013/doctor-mobile.png)；[患者云账号](workbench-20261013/patient-account-mobile.png) |
| 原生电脑端浅色／深色聊天 | [浅色聊天](workbench-20261013/desktop-light-chat.png)；[深色聊天](workbench-20261013/desktop-dark-chat.png) |
| 原生电脑端完整动作与方案设置 | [浅色方案](workbench-20261013/desktop-light-plans.png)；[深色方案](workbench-20261013/desktop-dark-plans.png) |
| 患者第二页有旧快照时保留原待发消息并要求刷新 | [双标签页冲突提示](workbench-20261013/patient-two-tab-conflict-mobile.png) |

## 复现与工具

复现命令（Python测试需先安装原项目与云端依赖）：

```powershell
# 仓库根目录；PG专项仅设置专用QA数据库变量后才运行
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest cloud_service/tests -q
node --test public_web/browser-account.test.cjs tools/cloud/portal.test.cjs
node --test mobile_rehab/tests/test_unified_presentation.cjs
node --test android_offline/tests/*.test.cjs
python tools/cloud/verify_workbench_native.py .runtime/<全新目录>

# 桌面 app 的 Python 测试从对应目录执行
Set-Location rehab_codex_single_camera_v2_1
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest tests/test_app_controller.py tests/test_workbench_clients.py tests/test_cloud_account.py tests/test_saved_training_plans.py tests/test_product_window.py -q
python -m pytest tests/test_saved_plan_runtime.py tests/test_training_execution.py tests/test_automatic_plans.py -q
```

本机使用实际可用的捆绑Python、Node与官方Edge。隔离浏览器脚本在 `tools/cloud/verify_workbench_browser.cjs`，临时服务入口 `tools/cloud/serve_browser_qa.py`；测试请求使用显式虚构账号，不复用生产登录。

Android JS测试需要先按原安卓构建流程生成catalog、TEST夹具及产品bundle资产；上面的命令假定这些准备已完成。原生界面脚本只允许输出到仓库 `.runtime` 的全新目录，使用内存TestClient和临时数据库。

## 交付边界

- 没有连接生产数据库、创建真实患者账号、发送真实医患消息或部署公网服务器。Git源码合入不能使正在运行的旧云服务自动出现新接口；后续需单独授权更新已有服务和执行经过验证的增补迁移。
- 继续复用原共享 `DOCTOR_ADMIN` 身份，本轮没有扩展多医生分诊、机构权限、会员、视频或API费用看板。
- 工程测试中的保存记录标明TEST与客户端声明来源；它们验证软件读写和规则门禁，不代表真人测量、临床效果或医生身份资质认证。
- 没有对真实手机、真实摄像头和公网新版服务完成现场验收。APK签名与安装边界须按下方实际构建结果阅读。
- 手机采用方案沿用现有本地能力：单组、最多5次；不支持的多组、节奏、额外角度约束、陪同等设置明确阻止采用，不会静默删改医生方案。电脑仍按原完整训练支持检查。
- 患者公共网页的云档案多标签页写入会检测旧快照冲突；冲突页需刷新，原待发消息与采用意图保留。当前版本未做同时多页编辑合并。

现有账号／权限／数据库复用、接口列表、以后更新原服务器的步骤见[工作台说明](../workbench/README.md)。[开源参考记录](../workbench/OPEN_SOURCE_REFERENCES.md)说明Chatwoot、Medplum、Socket.IO的借鉴与许可证判断；本次没有复制其源码或引入整套服务。
