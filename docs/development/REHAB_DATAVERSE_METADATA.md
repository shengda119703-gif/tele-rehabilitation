# 发布版数据核验与MobiPhysio评分交接

本增量对应后端任务书P3／P5／P6的数据前置条件。只改离线工具、数据注册、测试和文档；不改变正式算法、剂量、权重、UI、APK或患者历史。公开聚合证据见[数据摘要](../../reports/rehab_backend/dataverse_metadata.json)，本机实际核验见[验收记录](../validation/REHAB_DATAVERSE_2026-10-11.md)。

## 1. 固定发布版，不取草稿

[dataverse.py](../../tools/rehab_ml/dataverse.py)只查询固定的两个官方DOI。数据集根响应只用于核对身份和guestbook；其`latestVersion`可能是草稿，不作为数据版本。随后取得`:latest-published`，再读取明确数字版本，如`3.0`。两次规范化后的版本、许可、自定义条款和文件清单必须完全一致；`RELEASED`、dataset/version/file ID、文件大小和官方checksum分别验证。

保留每次实际GET、响应快照／SHA256／规范化指纹及失败。每请求连接／读取预算10／20秒，读取过程中检查45秒和16MiB预算；这不是包含操作系统及最后一次等待在内的绝对45秒硬截止。不提交账号、token、guestbook、访问申请或条款接受。挑战页／非JSON、HTTP错误、超时明确记为blocked，不说“数据已下载”。

`fileAccessRequest=true`表示支持访问申请，不能据此把公开文件误判成受限；只有明确`restricted=false`且无embargo才是公开元数据。缺少标志为unknown。元数据可读本身不授权训练。

## 2. 本机取得什么

MobiPhysio官方3.0发布版为CC0-1.0；3688个文件条目均显示不受限、无embargo，自定义条款为空。清单总大小158,714,197,650字节是元数据统计，不是本机下载量。只下载并校验README 12,668字节和治疗师评分CSV 539,076字节，共551,744字节。README自称v1.1，和Dataverse发布版3.0是两种版本，不能混写。

下载入口只接受从保留的数字版本快照核对出的1–2个真实文件ID，重新验证原快照、摘要与清单一致。只允许CC0、小于等于2MiB、非转换tabular、无自定义条款／guestbook要求的安全文档文件名。现有下载器做大小、MD5、SHA256、断点Range和空间检查；本入口拒绝MP4。历史获取摘要的旧分类器尚未识别CC0，保留原件与当时源码hash；目前结论来自实际URI／条款和校验成功的文档，不篡改旧摘要。

SUMediPose一次官方发布响应观察到1.0／CC BY-NC-SA 4.0／3654文件，但两次完整审计均在根请求读取超时，没有保留完整数字版本快照。不将观察结果升级为完整访问验收；资格仍未确认，不下载或训练。REHAB24-6的学术／非营利资格仍待确认。

## 3. 评分怎么进入研究链

[mobiphysio.py](../../tools/rehab_ml/mobiphysio.py)只适配已审查的3.0实际文件。信息交接为：

`官方数字版本快照 → 原文件ID／大小／MD5 → 文档manifest／SHA256 → 两行表头＋连续治疗师行 → 视频名 → 发布清单file_id／视频checksum → 逐视频评分索引＋未知／隔离清单 → 后续按人划分的质量研究`

CSV不是普通一行表头。一个非空视频名开始一组，后续空视频名继承该组，不把三名治疗师当成三次动作。每组要求三名不同治疗师、四个Primary和三个Control因子；数值有限且在规定范围。复核：

```text
T_j = Σ(4个Primary因子＋3个Control因子)
S_j = 100 × T_j / 7
S_video = (S_1 + S_2 + S_3) / 3
```

保留CSV原平均分和两位小数值，检查总分／换算／均值／舍入是否一致。数值容差1e-5仅用于文本序列化核对，不是临床阈值。异常整组隔离，未评分视频保持未知；不补均值、补治疗师、拆错位组或把未知转成正常。

实际3686视频对应3010组CSV记录，3008组通过、2组隔离；676视频没有匹配的独立评分。已审查命名3685视频，另1个`VP`变式官方README没有对应解释，留未知，不猜测为FL等。评分覆盖24人，视频清单覆盖58人，不能按58人宣称有评分。

E01肩外展清单558视频，其中380个评分通过、24人，正面128／左视角128／右视角124。`AL/AR`是拍摄视角，不是左／右患侧，因此affected_side=null；E08“Both Leg Flexion”不自动映射成坐站或康复深蹲。其余八动作只是保留数据身份，不新增正式产品动作。

## 4. 能支持的任务与缺口

评分是**整段视频EAAQ**，可作为后续视频动作质量回归的独立来源。现在尚未下载RGB、建立按人train/val/test、提取骨架或训练RGB质量模型。后续应先固定参与者划分，再生成特征／窗口，保留拍摄视角、遮挡、光照、抖动和分辨率条件用于分层验证；不能把同一人的不同视频拆到训练和测试两边。

这些分数不能推出每帧COCO17点、visibility、每次动作标签、相位、具体身体部位错误、提示时机、疼痛或临床剂量。姿态微调仍需独立2D标注与验证基线；当前`build-pose-dataset --dataset mobiphysio`继续明确拒绝。缺标签不是负标签。CC0允许的版权使用不等于隐私／肖像权被放弃，也不等于医学有效性或患者人群适用性。

## 5. 实际命令

从仓库根，用已验证产品解释器；临时目录放E盘，原始数据继续忽略。以下审计是官方网络GET，失败也有自己的run；不要因等待输出超时另开重复进程。

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py resolve-dataverse --dataset mobiphysio
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py resolve-dataverse --dataset sumedipose
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py fetch-dataverse-metadata --audit-run '.runtime/rehab_ml/run/dataverse-mobiphysio-13110f5c' --file-ids 13453294 13453292
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py index-mobiphysio-scores --audit-run '.runtime/rehab_ml/run/dataverse-mobiphysio-13110f5c' --metadata-manifest '.runtime/rehab_ml/data/mobiphysio/3.0/metadata-6ee01ba1/manifest.json'
```

旧run在其他电脑不存在；需先自行审计并显式传新的run／manifest，不能仅复制路径或把本机数据当作随Git分发。研究索引和原CSV留在`.runtime`；公开报告只含文件指纹、聚合统计及必要的异常身份，不含视频、骨架或治疗师逐行评分。

官方方法依据：[Dataverse Native API](https://guides.dataverse.org/en/latest/api/native-api.html)、[Data Access API](https://guides.dataverse.org/en/latest/api/dataaccess.html)、[CC0条款与权利边界](https://creativecommons.org/publicdomain/zero/1.0/)。
