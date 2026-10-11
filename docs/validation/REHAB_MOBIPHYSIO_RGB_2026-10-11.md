# MobiPhysio真实RGB与视频评分：本机验收

2026-10-11，Asia/Shanghai。实施基准`d18bd57d4ac84a540f5ad846d05ba785b0523ff9`；实验provenance保留当时HEAD与逐源码SHA，不把随后文档提交说成训练时提交。工程探索记录、人工科学复核pending，非临床或投稿认证。

## 已实际运行的数据与提取

同一不可变`rgb-e01-front-fl-9ac33275/plan.json`，SHA`2b4c484ab6655ff05aa6878cd3516019a542fc74c070713cd3f88a1e74290d36`；24人／24段、680355016字节。全部已核验E01、AF、VFL，每人一段；seed20261011，train14／val5／test5先于特征冻结。完整个体分组在私有plan与provenance，无同人跨split。

原`download-66c6f9f3.json`停在running／22段／618556665字节；原handle90476已不存在，OS检查也没有该下载Python进程，才允许同计划重开。新handle85441最终退出0，receipt`download-a157e0e1.json`为24段680355016字节、MD5＋SHA均通过；22段复用本机校验文件、2段继续获取。旧running receipt不篡改为终态成功；未测网络实际传输量，`network_bytes=null`。

三个提取失败全部保留、退出1、所属worker释放confirmed：

- `mobiphysio-pose-7c6c5119`：P05 header777与decoded775不符；后续实际PyAV demux确认777包、2个discard、decode775。
- `mobiphysio-pose-8fec51f0`：P02 packet与OpenCV时刻不同；stream.start_time1242、time_base1／90000，差0.0138秒有明确容器来源。
- `mobiphysio-pose-fee5e7ea`：P04仅OpenCV首帧0.033222秒与packet0秒不符，后续时刻一致。

这些是离线媒体兼容问题，不改正式采集，不改score／split／测试配置，不以帧数容差或标称fps补齐。最终改用已安装PyAV16.0.1，真实frame PTS和非discard packet时间逐一核对。

最终handle5597退出0：`mobiphysio-pose-78a27c8b`完成24段，summary SHA`d62ca9df99aaa2bcba309838055048ac0b4953065e6d3c4b22f851d8b94c2d3a`。21579显示帧、4个显式discard包、2569原PTS采样帧、2193帧单人且肩尺度可用；没有丢弃参与者或把无效点当真值。原YOLO权重SHA未变。所属PID14272最终confirmed释放，未启相机、正式服务或患者库。

2569次worker往返p50／p95为35.015／38.188ms，包含冷启动，排除解码、resize/JPEG前处理、网络与手机；不是整个流程p95或手机FPS。完整提取约274秒。详细原图点和预测只在忽略目录；Git无原片／逐帧骨架／个体预测。

## 实际训练结果

`mobiphysio-quality-71c92ec5`实际退出0；summary SHA`2f791975d9fd2f24ce5a430e030c8846ce2244847353738a7ba422f351bc1453`，配置canonical SHA`c4b8a073d0c4bdf20042210f957573cdc5a04bffaa97860b33033eb4603b73cb`。因果TCN共10epoch、val选第4epoch、patience6提前停止；最佳权重重新加载后，各split保存独立预测，本run对test只推理一次。训练用CPU／4线程；Py3.13.12、NumPy2.2.6、torch2.9.1、OpenCV4.12.0.88、ultralytics8.3.199、PyAV16.0.1；没有新依赖安装。

视频EAAQ总分0–100分，非正确率，预测不截断。以下保留到3位仅便于阅读，原JSON保存完整值；验证和测试各5人／5视频：

| 模型 | val MAE | test MAE | test RMSE | test R² |
| --- | ---: | ---: | ---: | ---: |
| train-median常量 | 13.810 | 11.333 | 12.822 | −0.013 |
| 标准化Ridge | 10.716 | 16.263 | 18.738 | −1.163 |
| 因果TCN | 15.674 | 11.333 | 13.208 | −0.074 |

TCN test MAE原值11.333420599550783，常量11.333333332，不能因四舍五入相同就称TCN更好；RMSE同样没有改善。Ridge train MAE0.174而test16.263，本批结果呈明显过拟合表现。24人／单机位／单光照／每人单段、test只有5人，未做稳定性置信区间或临床泛化验证；没有证据宣称任何候选优于常量。模型保持关闭，不调整处方、计次或正式权重。

## 已存证据的核对

`verify_mobiphysio.py`实际退出0：重查全源链／全部RGB、分组／官方label、NPZ／明细与模型artifact SHA；核对train帧统计／target统计、val选模epoch，从保存的prediction重新计算MAE／RMSE／R²，不再次推理test。聚合[机器可读证据](../../reports/rehab_backend/mobiphysio_rgb_experiment.json)有E001–E015路径／SHA、N001–N004分母与数值、M001–M004方法、三原失败与报告门；`agent_checked=true`不等于`human_verification=verified`。

首次姿态拒绝命令漏`--target-schema`只产生CLI参数错误，不当作监督门通过。补参数后`build-pose-dataset --dataset mobiphysio --target-schema coco17`实际拒绝缺独立2D／visibility监督，生成[阻塞摘要](../../reports/rehab_backend/pose_supervision_blocker.json)。其training_allowed=false仅指pose／phase监督，不否定本轮已完成的整视频EAAQ实验。

```powershell
$taskPython='.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe'
& $taskPython -X utf8 -B tools/rehab_ml/cli.py train-mobiphysio-quality --extraction '.runtime/rehab_ml/run/mobiphysio-pose-78a27c8b/summary.json'
& $taskPython -X utf8 -B tools/rehab_ml/verify_mobiphysio.py --experiment '.runtime/rehab_ml/run/mobiphysio-quality-71c92ec5/summary.json' --failed-extraction '.runtime/rehab_ml/run/mobiphysio-pose-7c6c5119/summary.json' '.runtime/rehab_ml/run/mobiphysio-pose-8fec51f0/summary.json' '.runtime/rehab_ml/run/mobiphysio-pose-fee5e7ea/summary.json' --interrupted-download '.runtime/rehab_ml/data/mobiphysio/3.0/rgb-e01-front-fl-9ac33275/download-66c6f9f3.json'
```

这是实际命令记录，不要求重复训练固定test；安全重核用verify工具读已存预测即可。[工作流](../development/REHAB_MOBIPHYSIO_RGB.md)包含公式、坐标、缺失mask、loss、来源及人工复核边界。scientific-writing用于证据分层与失败保留，并在工作流引用其当前v2论文，不以技能代替人工审批。

## 回归、保护与剩余目标

完整回归没有全部通过，保留三次终态与[失败摘要](../../reports/rehab_backend/mobiphysio_rgb_regression_failure.json)：

- `verification-f2c6728f`：新后端240秒超时，旧处理器没有保留途中日志；不猜测失败位置或测试计数。
- `verification-a6ba4ccd`：454项／1失败。独立SQL只发现TEST故障探针的`derived_report_state`由pending变ready，测量事实未变；测试原先在构造后停报告线程，存在先处理待办的竞争。只修TEST宿主启动顺序，未改正式服务、未弱化整库相等检查；新增契约后专项5项实际通过。
- 最终`verification-f28dac51`：455项／1失败，实际227.176秒；失败为`test_timing_comparison...test_actual_authenticated_host_endpoint_and_default_off_routes`。finalized且接收／处理／证据seq均64，但`completed_reps`期待1、实际0。根因尚未确定，不将上一项TEST修复写成全套通过，也不把这一失败解释为真人测量误差。原日志SHA`30d5c467f0c01e801b6bfc9704e7aa2f02cb2fcd9e7f790eb3eb9d8a7943f020`。

最终旧康复12项、旧手机19项退出0；1308保护文件变化0、原baseline不重建。38项RGB新增TEST与1项报告消费者契约是455项子集，不累计此前专项计数。新验证器只增强途中日志与每run终态保存，240秒门限没有放宽；[当前回归](../../reports/rehab_backend/regression.json)明确`passed=false`。本阶段保存离线研究源码和失败证据，不视为已验证产品发布；当前阅读文档请求不扩大为继续修业务或再次训练。

产品0.20.0／既有APK0.2.1、v2默认关闭，首页／康复／健康／用药／家庭不改；没有启停8765／1396或旧窗口。P5／P6仍缺合格独立2D、visibility、专业相位／可观察完成／提示参考，未完成真人姿态微调；完整P7仍缺目标手机／真实网络／长时与部分物理故障条件。公开视频实验不替代这些验收，整个任务仍未完成。
