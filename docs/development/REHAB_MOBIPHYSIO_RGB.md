# MobiPhysio真实RGB：整视频质量实验

工程研究记录；不是临床验证或投稿材料，来源的人工科学复核待完成。只增加康复离线数据／提取／训练／核对工具，不更换产品模型，不接入前端或APK。

## 1. 要回答的问题

任务书8.4、9、10、11要求把真实RGB与独立视频评分接起来。这里研究：原YOLO产生的二维骨架序列，能否预测同一视频的治疗师EAAQ总分。不是研究关节定位真值、逐次完成、相位、提示收益、诊断或训练剂量；这些没有对应监督。

选取官方发布3.0里所有已核验评分的E01／正面AF／全光VFL记录，每人恰好一段，共24人、24段、680,355,016字节。不是按分数、预测或文件大小挑选。预先固定seed20261011与按人划分14／5／5；同人的其他机位、光照或提取版本必须仍归原集合。来源详见[上一阶段](REHAB_DATAVERSE_METADATA.md)。证据见[聚合审计](../../reports/rehab_backend/mobiphysio_rgb_experiment.json)N001–N002，人工复核pending。

## 2. 信息交接与完整性

`数字发布版＋许可／inventory → 官方CSV与file_id／checksum独立核对 → immutable cohort plan＋subject split → 断点下载／MD5＋SHA → 显式显示时间轴 → 原YOLO所属进程 → 坐标／mask／dt → 整视频标签 → train统计／val选模／test一次 → 保存预测与残差核对`。

完整24段才允许提取和训练。每次重开重新核对官方文档、评分、发布清单、计划与实际RGB字节，不把局部成功变成完整实验。原文件和失败run保留；RGB、逐帧骨架、模型与个体预测只在忽略目录，本次Git只保留工具和聚合证据。

首次OpenCV提取在P05失败：header777而decoded775；PyAV实际demux显示777包、其中2包显式discard，PyAV实际decode775。之后按packet校验又发现P02有明确stream.start_time=1242／90000秒，P04的OpenCV首帧时间与packet不同。三个失败run均保留，未训练任何局部样本，也未据此调整标签、划分或测试预测。

最终离线提取使用已安装PyAV，frame.pts×frame.time_base减容器显式start_time得到源时间；逐帧与非discard packet PTS相符、帧数完全对应，任何缺时间、非单调、corrupt、缺显示帧或超预算均失败。空flush packet不是视频帧。每段最多180秒、18,000包，尺寸32–4096；时间比较容差0.0002秒仅用于数值精度，不补造FPS时间。这是容器与解码的一致性检查，不是独立运动或关节真值。

## 3. 特征与三个模型

原权重SHA：`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`。每次所属worker只处理本段Context；没有调用相机或正常患者库。实际PTS间隔至少0.25秒采样，非插值4Hz；显式长边640、只缩小、不镜像／裁剪，JPEG90后调用原推理，再按实际sx／sy还原原图坐标。多人／无人保留未知，不强行指定目标。

COCO17每帧特征69维：34归一化坐标＋17有效mask＋17预测置信度＋实际dt。双肩中点作中心、肩宽作尺度；双肩不可用／退化时身体尺度无效，零占位伴随false mask。单点置信度≥0.5、有限、原图内才可用。预测置信度不叫标注visibility；左右解剖点保留，调用hint不是患侧标签。没有z=0伪三维。

三模型配置在测试前固定：

- 训练集分数中位数常量：衡量比“总是猜中间分数”是否好。
- Ridge：69维每列mean／std／q10／q50／q90共345维；坐标统计排除无效mask，未知仍有覆盖通道。仅整段结束可用，不能用于实时相位。训练集标准化、α=1，解双形式`β=Zᵀ(ZZᵀ+αI)⁻¹(y−mean_train)`。
- 因果TCN：channels32，四块dilation1／2／4／8、每块两卷积、kernel3，仅左padding、逐时刻LayerNorm、dropout0.1；`R=1+2×(3−1)×(1+2+4+8)=61`步。全片段masked汇聚后单个视频回归头；不能称逐帧评分。仅train有效身体尺度帧拟合输入统计，target同样仅train；每split独立padding，test长度不决定训练batch形状。

TCN用AdamW、lr0.001、weight_decay0.0001、clip1、CPU4线程；最多30epoch、patience6，val视频MAE选择权重。每视频只一个MSE目标，不复制标签到每帧。保存配置／provenance／日志／权重／预测／model card；这条新训练器没有宣称断点恢复或产品导出。

## 4. 结果如何核验

实际结果见[本机验收](../validation/REHAB_MOBIPHYSIO_RGB_2026-10-11.md)与聚合JSON。`MAE=mean(abs(pred−reference))`，`RMSE=sqrt(mean((pred−reference)²))`，`R²=1−SSE/SST`；常量参考R²为null，预测不截成0–100来美化指标。

`verify_mobiphysio.py`核对完整源链、split、官方标签／保存预测配对、全部artifact SHA、train统计、val选中epoch以及从已存预测重新计算指标，不再次对test做模型推理。验证日志与test结果分开，后续调参必须使用新设计的训练内验证，不能反复优化本轮5人test。

仅24人、正面／全光／每人单段，不能代表康复患者或手机环境；原YOLO训练数据与此公开源有无重叠未独立核实。没有独立2D、visibility、相位、误差部位、提示窗口；即使EAAQ误差较小，也不能推出关节准确率、计次准确率、疗效或提示收益。模型默认不激活，IRDS的Kinect候选也不混用此二维域。

## 5. 实际入口

从仓库根，用原已验证`.venv`；设置TEMP／TMP到现有E盘run目录以避免C盘不足。以下是明确的私有证据路径，不是通配扫描最新run。

```powershell
$taskPython='.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe'
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& $taskPython -X utf8 -B tools/rehab_ml/cli.py fetch-mobiphysio-rgb --plan '.runtime/rehab_ml/data/mobiphysio/3.0/rgb-e01-front-fl-9ac33275/plan.json'
& $taskPython -X utf8 -B tools/rehab_ml/cli.py extract-mobiphysio-rgb --receipt '.runtime/rehab_ml/data/mobiphysio/3.0/rgb-e01-front-fl-9ac33275/download-a157e0e1.json'
```

`plan-mobiphysio-rgb --index-run ... --audit-run ...`创建新的不可变计划，不覆盖原计划。抽取输出明确summary，随后`train-mobiphysio-quality --extraction ...`；验收文档记录本次真实训练及核对命令。不要为了复现指标反复重新训练或测试同一固定test。

## 6. 来源、权限与报告状态

数据版本／许可来自[Harvard官方3.0记录](https://dataverse.harvard.edu/api/v1/datasets/:persistentId/versions/3.0?persistentId=doi:10.7910/DVN/XSI0QN)及已保存快照；[CC0](https://creativecommons.org/publicdomain/zero/1.0/)不自动放弃隐私／肖像等权利，不声称原数据伦理或受试者同意已由本项目独立复核。没有新人体采集、外部上传视频或联系作者。

帧／packet时间字段采用[PyAV官方Frame说明](https://pyav.org/docs/stable/api/frame.html)和[Container说明](https://pyav.org/docs/stable/api/container.html)，结合本机实际版本行为验证；网页“stable”页面所列版本不当本机依赖版本。本机依赖由run provenance记录。

scientific-writing用于来源绑定、方法结果对账、保留失败与未知、区分工程和临床结论。报告只为工程研究，不宣称TRIPOD／STARD等正式报告规范认证；投稿／临床目标、人工来源复核、作者／机构审批均没有代填。软件流程引用：Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. [DOI](https://doi.org/10.48550/arXiv.2609.00065)；2026-10-11打开arXiv当前记录，最新v2于2026-09-02修订，无所列期刊版本。引用不支持本项目有效性结论。
