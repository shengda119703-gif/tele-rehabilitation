# 康复v2逐次时间条件与只读历史比较：本机验收

日期：2026-10-11。实施基准`fc8ba232e82bf13582ae317bef4ef408d2d07337`；最终源码以本文件所在提交为准。对应任务书6.6和15节的比较／证据不变量，仅此阶段增量，不认定整个任务完成。产品0.20.0、APK0.2.1、v2默认关闭；UI／整个Android／原权重／正常患者库不改。

## 1. 实际实现

三动作每次开始冻结`rehab-timing-context-1`，保留当次起点、协议／域／时钟、六个工程时间参数、目标／时间安排、扶手／陪同和训练剂量。原时间算法与封套保持，后续准备不解释旧次。独立`rehab-timing-comparison-1`读取本人两条已finalized事实，核对canonical视觉digest，四项时间分别给条件、分母／原因、中位数及同条件差值；不驱动推理、不回写事实、反馈、报告或贡献。

旧无context、nominal时钟、条件混合或完整次时间缺失不补零。部分保持是已见下界，不作完整保持比较；坐站只站起仍保存一次及已见起身时间，不虚构回坐。具体身份与语义条件分开，source_ref不等于source_epoch。数据链、字段／公式／API及复现见 [工作流](../development/REHAB_TIMING_COMPARISON.md)。

## 2. 实际执行与环境

使用原产品`rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe`，3.13.12；不升级依赖、不下载模型、不训练或分析私人视频。命令使用`-X utf8 -B`，进程环境`PYTHONDONTWRITEBYTECODE=1`、TEMP／TMP指定E盘已存在的`.runtime/rehab_ml/run`；不改用户全局环境。测试库和日志放新忽略run，不启动用户应用、相机或服务。

| 实际命令 | run／结果 | 时间与范围 |
| --- | --- | --- |
| `verify_timing_comparison.py` | `timing-comparison-audit-07d9c64b`；18项、退出0 | 命令35.146秒，unittest34.853秒；7份源码hash前后一致 |
| `verify_backend_plans.py` | `backend-plan-audit-4a9181d2`；19项、退出0 | 命令42.884秒，unittest42.584秒；6份源码hash前后一致 |
| `verify_all.py`新后端 | `verification-6adfee5b`；340项、退出0 | 命令207.118秒，unittest204.267秒；原240秒预算未延长 |
| 同次原康复 | 同run；12项、退出0 | 命令0.245秒，unittest0.091秒 |
| 同次原手机接口 | 同run；19项、退出0 | 命令12.700秒，pytest12.18秒；既有Starlette／httpx warning保留 |
| 同次保护核验 | 同run；1308条、变化0、退出0 | 命令5.119秒；原baseline SHA256不重建 |

专项18／19项是340项子集，不累计为377项，也不是18／19／340名真人。完整回归仅新后端目录、原康复单元与原手机接口，不是全UI、Android或所有非康复验收。命令完整路径在`tools/rehab_ml/`。

滚动最新机器记录：[时间专项](../../reports/rehab_backend/timing_comparison_verification.json)、[安排重验](../../reports/rehab_backend/backend_plan_verification.json)、[完整回归](../../reports/rehab_backend/regression.json)、[保护核验](../../reports/rehab_backend/scope_verification.json)。此前322／318等阶段保留各自验收，不用本轮report替代历史结果。

## 3. 日志与源码指纹

原日志在E盘`.runtime/rehab_ml/run/<run>/`，不上传整份忽略目录。已记录SHA256：

| 日志 | SHA256 |
| --- | --- |
| `timing-comparison-audit-07d9c64b/timing-comparison.txt` | `3a46db8198498f06bf8dd1efdd46b931e01df3f68ef93e17c1759ad9ef5136e2` |
| `backend-plan-audit-4a9181d2/plans.txt` | `8d06a274b53da222773ba842ecdf3283f25238737f047f9f4b8ca0a9db4ca984` |
| `verification-6adfee5b/new_backend.txt` | `2ad8e7efd34f2497cdccac7538025da2cbf371c44288674bb62220e6e817f3a3` |
| `verification-6adfee5b/legacy_rehab.txt` | `e4c361c646011848213770236330c2956752ec3a66d21aeeca515c17e9ca1c8c` |
| `verification-6adfee5b/legacy_mobile.txt` | `17131473fba53674d8323f094210d0106123ef81003184f0f5ed768f76e992e4` |
| `verification-6adfee5b/scope.txt` | `b3214f06cb09f5235674d0c70d40ce5bb037a27e65d7d95d3bb666f36a308e7a` |

两个专项保存逐文件implementation_sha256及`implementation_unchanged=true`，服务／API重叠，13次核对不是13份不同源码。原1308条基准SHA256为`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`。

## 4. 确定性覆盖与输入性质

18项覆盖三动作完整周期，身份／条件分离，支持／剂量／目标／时钟／模型／基线变化，旧记录／错误绑定，有限／零／非法值，部分保持，完整次缺时间和未完成分母，坐站未回坐，两组不同起点，权威digest、草稿／授权／严格请求，反馈、报告失败、重启／重复只读及默认关闭。

实际HTTP测试通过宿主配对cookie、X-Rehab-Client保护、公共JPEG入站、处理等待、finish事务和比较路由。几何是显式TEST provider；图像是白色TEST JPEG，不是真人或原模型精度。安排专项另复用原YOLO白图缺人拒绝，但无人测试不能证明真人可靠性。TEST数值扰动只在测试内存，不写正常历史或冒充真实测量。

输出固定`clinical_comparable=false`、`improvement_assessed=false`、`significance_assessed=false`、`sampling_invariance_validated=false`、`frontend_not_connected=true`。未新增诊断、自动剂量或质量阈值。

## 5. 首次失败及修复

| 失败run | 实际结果／日志SHA256 | 修复及边界 |
| --- | --- | --- |
| `timing-comparison-audit-7f80888c` | 16项、退出1、26个失败断言／子例；`a57c5653789a2ca31d514f3f59e99eb136a2463629576b93fcb324efb7cad338` | signature[0]实际source_ref被误用作source_epoch；引擎改为显式传真实epoch，保留来源名称；证据门控不放宽 |
| `timing-comparison-audit-1b889460` | 16项、退出1、3个失败子例；`c88c61567e12ac3a0dd1e96b966190481c2f5ed8bc87e7bcd5a8444d0ac1250d` | TEST预期fixture错误，EvidenceFrame默认实际internal-replay；分别断言真实epoch／source_ref，不改原数据类型 |

两份失败日志保留，不计通过。最终增加算法／证据与显式剂量边界后18项，再跑全部专项和完整回归；没有用失败前源码证明新实现。

## 6. 未完成项与交付范围

mapped宿主接收时间不是手机曝光时间，网络延迟、采样抖动尚未标定；不同钟不混为同来源。相同的未知支持安排不能证明实际环境相同。仍缺合法同域RGB、独立专业计时／相位、真人分层误差与覆盖、采样／丢帧实验、临床变化依据、目标手机和完整物理故障／压力。旧页面／APK未连接，无新服务部署或候选启用。

只提交新比较器、康复engine／封套与API／Service小接线、专项测试／工具、统计report和必要文档。开工280份用户图片、CSV、导入脚本、图片README和任务书逐路径保留、不纳入提交；原患者库／Android／前端／原权重及非康复只读。交付前核对源码／日志、原保护及文档；只刷新桌面入口Git版本描述，不关闭旧窗口。

实际交付核对：280份用户文件开工／结束逐路径SHA256变化0；工作区299条为本轮19份和用户280份，未发现额外文件或原暂存改动。原1308保护／baseline、两个专项13次源码hash及6份成功日志hash一致；9份文档440个本地链接、50个表格及82个围栏检查无错误。Git空白检查通过，fetch后基准HEAD与origin/main一致；发布只使用19份明确清单，不批量暂存用户资料。文档改后再次核对同一检查范围，不用重建基准掩盖变化。
