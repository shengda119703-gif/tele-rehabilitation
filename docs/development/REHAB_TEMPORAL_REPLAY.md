# 原录像到计次预测：来源、时间与保存证据

日期：2026-10-12。后端任务书10.4–10.6／15.2／P5的离线增量；不改变正式产品、UI、整个Android、现有患者库或权重，不启动摄像头或用户网页服务。

## 为什么另做实际回放

`evaluate-annotations`接受独立参考和声明式预测文件，但一份JSON及其SHA不能单独证明跑过后端。此前MobiPhysio特征缓存虽然保存了双侧点坐标，却没有原输出的完整参与者列表、框和跟踪信息。不能用补框或固定伪身份把缓存冒充完整流程。

新增`replay-mobiphysio-temporal`重新读取已校验的原录像，复用原YOLO所属进程、`EvidenceAdapter`和`ProtocolEngine`。录像、权重、规则和人体参考不改；原片不复制、不另行下载、不训练、不写正常历史。

## 信息逐跳交接

| 上游→下游 | 传递和核对 | 保存位置／用途 |
| --- | --- | --- |
| 原下载receipt→固定人群队列 | CC0许可、原文件大小／MD5／SHA、计划SHA、原14／5／5人划分 | 选择明确val或test，不能按效果筛录像 |
| 运行前配置→解码 | 明确分析左／右侧、原默认plan、0.25秒采样、640长边／JPEG90、无裁剪镜像 | 新run的config.json；患侧仍unknown |
| 容器→帧 | 显式stream原点、真实展示PTS、discard标记、完整帧清单 | 不使用FPS造时间、不补帧；顺序或完整性异常失败 |
| 帧→原所属YOLO进程 | 原seq／PTS／context、JPEG指纹、固定模型SHA | 原返回全部人、框、轨迹、COCO17契约；没有伪参与者 |
| 模型像素→源像素 | xy及框按显式sx／sy逆缩放 | 原图同尺度二维几何，显示镜像不改变侧别 |
| 原姿态→原因果指标 | 原解剖点选择、置信度、EMA／跳变与缺测逻辑 | 每帧metrics、valid／reason及观察状态 |
| 指标→原协议 | 原准备／停留／转折／缺测规则、seq和source_epoch | 逐帧阶段前后、确认次数、明确事件 |
| 实际trace→预测manifest | 所选完整队列、source／模型／实现／配置SHA、计数和逐边界可用性 | predictions.json；失败保持null，不补成0 |
| 保存证据→再次重放 | 重新从保存的原姿态走原adapter／engine，核对每帧、结果和事件 | 专项聚合只保存运行信息／数量／指纹，不上传逐帧点 |
| 预测＋独立专业参考→评价 | 待专业参考批准后使用第16.15节评价器 | 本轮没有参考、不能生成准确率 |

## 时间与侧别口径

公共文件`time_basis=stream_relative_media_pts`。原引擎支持`mapped_source_seconds`，此离线工具使用从显式媒体PTS到引擎时间的恒等映射；配置保存两种名称与映射，绝不称接收时间或曝光同步。

离线处理年龄设0表示按历史证据重放，不代表实时延迟为0。实际推理往返耗时另存trace，不能把这次电脑运行当手机性能证据。

`--side`必须在推理前显式选择，是分析的解剖侧，不是从AF相机名、治疗师总分或模型结果推断患侧。原固定队列没有患侧标签；未来专业参考侧别与当前预测不同，应重新预声明研究条件，不能拿测试结果挑较好的侧别。

## 哪些阶段可导出

| 评价字段 | 当前导出定义 | 不可冒称 |
| --- | --- | --- |
| outbound_start_s | REST→RAISING或SEATED_READY→RISING当前确认帧的PTS | 真实动作首次启动时刻；停留确认延迟仍可被独立参考测出来 |
| return_start_s | RAISING／PEAK_OR_HOLD／STANDING_REACHED→LOWERING确认帧 | 峰值帧或未经观测的转折 |
| end_s | 本帧新增COMPLETE重复的end_time_s | 部分动作、结束按钮或失败片段的完成时间 |
| preparation_confirmed_s | null；引擎初始校准不是每次重复的准备边界 | 用一个初始基线复制到每次准备 |
| endpoint_start_s／endpoint_end_s | null；原协议未发出同口径事件 | 由峰区计时、计次或未来结果反推人工相位 |

`[]`只表示已实现事件这一录像未输出；`null`表示此边界没有可用导出，两者不可混用。当前导出是确认事件，不是新增相位学习模型，也不是接入正式会话trace的通用适配器。

## CLI与产物

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py replay-mobiphysio-temporal --help
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_temporal_replay.py --receipt '.runtime/rehab_ml/data/mobiphysio/3.0/rgb-e01-front-fl-9ac33275/download-a157e0e1.json' --pending-bundle '.runtime/rehab_ml/run/professional-annotation-audit-3581f13f/cohort/bundle.json'
```

单独回放必须明确`--receipt`、`--split val|test`、`--side left|right`、尚不存在的`--output-dir`。仅接受专用run目录，至少保留原32MB空间门；不覆盖旧产物。没有隐式latest实验，失败CLI非零。

每段保存原姿态／指标／阶段trace、原engine结果；整个run保存运行前config、完整队列predictions与summary。输出只在忽略目录；公开报告不含原录像或逐帧骨架。源文件／代码／配置或权重改变、释放未确认时整个导出失效，失败计数保持null。

原worker持有离线heavy资源租约，推理、超时与释放沿既有Windows所属进程实现；不新建摄像头、SQL、报告服务或患者会话。

## 当前边界

再次重放证明保存证据内部一致，不证明人体点坐标准确、真实生物身份或执行的密码学证明。专业标注独立性、两名标注者与第三人资格仍需实际组织。人工参考与预测不能互相预填；本工具不读取editable A／B／REVIEW表或将治疗师总分用于计次。

这个固定合法队列只有肩外展。坐站和康复深蹲仍缺对应真实独立素材及参考，不用本队列冒充三动作人体验收。临床角度、计次误差、质量／提示效果、手机／LAN／TLS和长时故障没有因此完成。

本机实际次数、运行日志／源码SHA、开发失败及完整回归另见[本机记录](../validation/REHAB_TEMPORAL_REPLAY_2026-10-12.md)。评价方法见[参考评价](REHAB_TEMPORAL_EVALUATION.md)。
