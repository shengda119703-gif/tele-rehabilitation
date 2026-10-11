# 条件式多轮姿态训练：2026-10-11 本机验收

最终实施／复验基准`7647037c956f3bcef6a0486b797ab9f667820879`。继续任务书12.1–12.3和第7节的离线作业边界。本轮补真正可运行的多轮masked训练、训练集增广、验证选模／早停、最后／最佳检查点、独立测试、状态和取消；另外修复内部子进程错误调用时的失败写入范围。没有新增合格真人RGB监督、专业精度结论或客户端更新。

## 1. 实际运行

仓库根目录，产品原`.venv/Scripts/python.exe`。TEMP／TMP和全部原生输出位于E盘忽略目录，PYTHONDONTWRITEBYTECODE=1；没有安装／升级、相机、原服务或正常数据库操作。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_pose_training.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
```

专项末次`pose-training-audit-6c350f29`，公共 [摘要](../../reports/rehab_backend/pose_training_verification.json)。实际五条命令：

| 命令 | 实际结果 | 外层秒数 |
| --- | --- | --- |
| unit：test_pose_training | 30项，1.615秒，退出0；含范围外实际子进程反例 | 3.647 |
| train-pose --config .../config.json | 原YOLO真实两轮／两步AdamW，退出0 | 7.638 |
| train-pose --config .../early-stop-config.json | 最多4轮、patience1，在第2轮早停，退出0 | 8.163 |
| train-pose --config .../not-authorized-config.json | training权限false，未创建输出／子进程，预期退出1 | 0.157 |
| pose_training.py --child-request .../cancel-run/request.json | 准确活句柄确认；epoch1／step1的validation阶段请求取消，实际退出1 | 4.849 |

两轮运行的所属工程步骤4.841秒，最佳epoch1、末次epoch2，严格重载best。train／val／test各一个独立TEST身份、一张96×64灰色空图及明确合成标签；不是患者或独立真人真值。只train进行128图优化；验证／测试使用原JPEG95／640跟踪路径，原模型与候选覆盖均0、PCK_all=0、已覆盖误差null。不能据此写模型改善或准确率。

完整末次`verification-b4bcb387`：230项新后端85.622秒／外层88.334秒，12项原康复0.087秒／外层0.238秒，19项手机14.20秒／外层14.730秒，1308保护文件变化为空；四条退出0。30项专项是230项子集，不与此前227、200、177或其他子集相加。现有Starlette/httpx warning保留。

## 2. 验证范围

| 项目 | 证据和界限 |
| --- | --- |
| 多轮接线 | 实际原YOLO／原TAL／双层masked loss／AdamW两轮；参数digest发生变化；不是只调用mock optimizer |
| 增广和几何 | 只train亮度／对比度，记录随机种子与逐样本实际值；实际128×85 resize／21px上边距；框／点同轴比例，未标与v0掩码不改 |
| 数据隔离 | train tensor拒绝val／test；身份大小写跨split拒绝；冻结输入SHA；每split有定位参考；research不接受synthetic_fixture |
| 验证选模 | PCK_all以全部独立定位参考为分母、coverage为第二键；同分保留较早模型；测试不选模，也不进入优化 |
| baseline gate | 在优化前先原模型val；完美PCK不启动research优化的门控由受控单测验证，不是伪造真人训练 |
| 冻结与验证副本 | 冻结层参数／BN缓冲保持、原DFL固定；验证用副本，原生运行逐次核对训练model state未因融合改变 |
| 检查点 | last／best均实际保存，新state严格重载；模型卡包含来源、split、域、checkpoint SHA及禁用状态，不覆盖原权重 |
| OS资源互斥 | 同进程两把实际OS锁证明第二份lease拒绝、释放后可获取；文件存在不冒充活进程；尚非完整多客户端压力 |
| 真取消 | 直接拥有原生子进程句柄，poll确认活着后请求；observed validation／epoch1／step1；最后检查点保留、failure=cancelled、结果文件不存在、实际exit已确认 |
| 受控故障 | Popen创建失败、timeout、Ctrl+C、释放未确认、初始空间不足等单测；这些不冒充原生卡死、物理硬盘满或断电实测 |
| 取消引用 | 只本run冻结请求／resolved config；外部原配置删除不阻断请求；请求本身返回exit_confirmed=false |
| 子进程失败写入 | 路径／request.json文件名在OS锁前检查；范围外实际CLI退出1，临时目录内request／failure／status三份hash及文件集合不变；错误文件名不写失败状态 |
| 损坏状态处理 | 所属run的非object状态不会遮盖原取消错误；重新记录failed／cancelled且completed=false。属于受控文件内容反例，不是介质故障验收 |

原权重前后SHA`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`不变，Ultralytics8.3.199／原loss.py hash继续锁定。最佳检查点SHA`e8d055f90f5ba266d7ec11b7dcfce6579cda8d027d6797095c99cb8610995b34`，末次SHA`5bbda81631b2403d53f51d71f34da72aa8f35c2f98e4bdc0ea135ed79c5d6950`。TEST检查点不上传Git，不注册成正式模型。

| 日志 | SHA256 |
| --- | --- |
| unit.txt | `d8f3c5a0db9f8e4ea9237248f11e86489047ec42abafd014490ccb82ac27be3e` |
| native_multi_epoch.txt | `71e930ddef76410fa7d5ec7a6c28f1d264c87372d44611f4dbb90380c3c56e90` |
| native_early_stopping.txt | `b6d5508a68c63233560955fadae96ad613bc9fdcdbdc53220fbc998ec8b21f5f` |
| reject_training_permission.txt | `e55418ae11e9f1f61d68b02fa2d8ef758e89fc4553ef6d13a9c2bfb8035a0408` |
| native_cancel.txt | `dc35313f1011b2d0e35481d9107db87dc90157bd013918537b475accc55ff6bc` |
| new_backend.txt | `e9d39dd25ef63364cfbfbf6b240aca93b4e2f654a8f0418e7d8fa30125149bac` |
| legacy_rehab.txt | `271fe9a3b08696b5e6a4ac15168b69acd1de7ed093a803cf803873c2d3268a00` |
| legacy_mobile.txt | `80a5ed8a55fcebd4b2c70a1ec3aa0e4a0ec78e835f3581c94902d4be440a3e0c` |
| scope.txt | `c7d0a6f97fbdff1071ffde95de597dcfdc8eafcc0b4d9a541714511bb1f0c07e` |

公共摘要另列五份实现文件和十五份产物SHA；取消run的last SHA与主run不同，因为配置和停止边界不同，不混用其checkpoint或耗时。

## 3. 迭代失败与限制

首次单测21项中timeout夹具失败：模拟wait已返回，但poll一直None，因此实现正确保留release_unconfirmed。修正夹具在确认wait后返回真实终态0，不降低释放要求。成功历史`5e084a40`／`65d5a85e`为较早代码；`d9115a24`为加入早停／取消后的版本，`022320dd`为27项工作区版本。复核发现直接调用内部子进程的异常处理可能写在范围外请求旁，加入同路径检查和三项反例后，本节末次`6c350f29`在最终代码上复跑。所有旧忽略日志保留，不计为当前最新验收。

没有真人RGB／专业标注或真实微调收益，没有跑50轮真人实验、CUDA／AMP／DDP、ONNX、手机、多人压力或物理存储故障。当前只实现train颜色增广，不声称翻转／遮挡／变速增广已核验。训练器保留恢复材料但没有自动resume；其OS互斥只管离线pose作业，未和整个产品活动训练调度互斥。权限文件的内容不被代码合法性认证，姿态模型对原图的上游预训练排除也未知。

本轮未重跑IRDS正式训练、两段真人录像、会话CLI或性能benchmark；旧结果仍是各自历史。深蹲宿主没有正式本人计划契约，不把膝屈曲／健身深蹲改名。UI、整个Android、原模型、正常库与非康复业务保持，v2与候选默认关闭。完整后端目标未完成。

## 4. 交付前文档与保留文件核对

更新阅读版、扩展索引、工具说明、实施报告和交接，让“训练循环已实现”与“真人监督／产品上线未完成”对应。历史验证页及其旧hash不倒改；修正扩展索引原有公式表格中的未转义竖线为数学范数／绝对值字符，只影响Markdown呈现。

280份开工用户素材／CSV／任务书／导入脚本等逐文件SHA核对，变化0；1308正式保护文件的独立命令同样通过，基准未重建。只暂存本轮20份源码／配置／测试／聚合报告／文档，不包含图片、原片、模型、环境或用户数据。Git空白及相关10份Markdown的相对链接、围栏和表格列数在交付前检查。

首次一次性传入280份hash核对清单触发Windows命令行长度限制，命令未创建；拆成20份一组后实际核对通过。首次文档检查发现扩展索引旧表格的公式竖线，修正后复查；这些检查错误和文档问题不冒充业务或精度验证。

产品仍0.20.0、独立APK0.2.1、v2默认关闭。提交后更新桌面“安康康复（最新版本）”的Git描述，继续使用仓库Start-Rehab.ps1与本机已验证pythonw.exe，首页／康复／健康／用药／家庭导航不变；不关闭原窗口或启停服务。
