# 独立专业标注与导入工作流

范围：任务书10.4–10.6、13、P5。只做离线康复标注，不建设前端，不自动训练或启用模型。旧`rehab-professional-label-1`模板保留；新包使用`rehab-professional-label-2`，逐边界／逐问题独立mask，不兼容时拒绝而不是猜测转换。

## 先准备规范，再观看录像

标注者A、B各自独立观看完整录像，只填写自己的JSONL；不要看另一人的表、上游视频评分或模型点／次数／相位预测。专业复核者是第三人，审查起点、转折、部分动作、无法评价和分歧。当前工具只能记录独立声明，不能证明人员资格或文件访问隔离，需要团队实际执行。

当前可生成的是已核验MobiPhysio3.0／CC0的固定E01正面全光照24人队列，不包括坐站／康复深蹲授权素材，不宣称覆盖三动作条件。旧14／5／5人划分不变；原研究只允许视频EAAQ头，不改旧plan、原视频或原实验结果。新标注是独立任务，未审核的包不产生训练参考，也不提供二维点／visibility监督。

### 填写规则

1. `source`、sample_id、人物组、动作、机位、协议、split、文件hash和时间来源不能改。AF是前机位，不是患侧；`side`由观看确认本人解剖左／右，无法确认保留null并交复核，不猜患侧。
2. `annotation`填写个人标识、标注版本；完整观看及逐次清点后才声明completed、video_reviewed、inventory_complete和independently_performed。无动作录像也需要完整观看，不从首末帧推断“0次”。
3. `templates.json`给空记录、单次动作、质量问题和提示机会模板。`repetitions`开始为空，不自动填“做完了”。复制单次模板，为每个独立动作片段分配唯一rep_id；以同一分段规范标注，分段不同也是分歧，不自动一对一平均。
4. 边界时间取同包`*-pts.json`的presentation_s：原流PTS减显式stream start_time，真实呈现时间，不用FPS重建或推理耗时。只标看到的准备／出程／端点与保持／回程／结束，未知null且相应phase mask=false；时间需落在实际帧（0.0002秒仅解码舍入容差）。相位有序，重复片段不重叠。坐站到站立是计次终点，未坐回可没有回程；肩外展／深蹲完整可观察往返需要准备、出程、端点、回程及结束证据。
5. `physical_completion`与`observable_completion`分别用bool／null及独立mask。当前导入器只接受同视频可见且一致的物理参考：physical_reference填kind=same_video_visible、原视频hash与依据说明。另一个同步视角证明实际完成而本机遮挡的情形必须另做同步参考资格，不靠填写外部路径绕过；当前返回明确拒绝，不合成已完成事实。
6. 问题状态present／absent需要assessable=true、两个mask=true、可评价时段和允许变化依据。已审查且无该问题才能填absent。不可评价可以明确assessable=false、assessability_mask=true，而state=unknown、state_mask=false；未审查assessable=null且两mask=false。活动幅度受限或允许扶手不能自动记错。
7. 提示机会仅标专业认可的时段、类别、优先级（0–100为工程排序，不是严重度），label_mask=true。无干预记录时actually_received、later_improved、intervention_evidence均为null。当前不支持导入未经独立资格核对的干预回执，填写非空将拒绝；提示之后动作变化不证明收到了提示或由提示改善。
8. `conditions`保留可接受变化、支持条件及已知目标范围。缺少处方／条件不补统一阈值，不据此增加剂量、判疼痛或自动处方。

没有完整动作的录像也能有真实参考，但须显式填`observable_count=0`、`observable_count_mask=true`，由A、B与复核者完整审查和清点。已列出的单次可观察完成必须全部有明确标签，数量与True标签之和一致；含unknown的清单不能推成0。默认空列表＋count=null／mask=false仍是未标注。这个零是“当前输入可确认的完整动作数”，不是实际身体活动量或治疗效果；侧别仍须确认。

## 三动作的采样核对表

| 动作 | 需要专业覆盖的条件 | 标注重点 |
| --- | --- | --- |
| 肩外展 | 舒适起点、往返、可接受受限幅度、肘／躯干变化、腕缺失、转折遮挡 | 主肩肘证据与辅助质量分开；遮挡转折不补完整次 |
| 坐站 | 坐姿开始、站着进入、未坐回、允许扶手、半起身、暂停恢复、旁人 | 准备不能默认坐姿；站起终点与坐回重置分开 |
| 康复深蹲 | 允许幅度、全腿／踝裁切／髋裁切、支持、慢／常速、视角 | 单一适用主视角；受限幅度不自动不完整；缺点指标独立 |

不诱导患者为采集“错误动作”超出其训练要求。当前24段素材未由专业人员核对上述条件覆盖，不能写成覆盖达标。

## 双人标注与第三人复核

`annotator-A.jsonl`、`annotator-B.jsonl`保留原顺序和所有样本，不删困难或未知记录。`validate-annotations`输出每样本精确分歧路径，包括侧别、条件、边界值与mask、质量及提示字段；它不是人员一致性统计或临床验证。

复核者单独填写`review.jsonl`中的最终标注。review.status为pending／approved／excluded；填写资格描述、最终理由、完整分歧路径和A／B整行canonical SHA256。审核后上游标注发生任何变化都需重新核对，禁止沿用旧复核。A、B与复核者标识必须不同。排除仍保留在队列及分母，不能带监督；可导入已复核的非空部分，状态为qualified_partial，待标／排除ID和完整原队列同时保留。没有一个合格标注则拒绝导入。空标签即便三人签字也不自动变成阴性或零次训练样本。

`import-annotations`生成单独的`rehab-reviewed-temporal-reference-1`，仍是离线研究参考，不接产品数据库、不提供pose标签、不激活模型。后续训练器还需按独立任务mask、完整队列分母、固定人群划分及独立测试要求接入；本工具通过不代表真实标注或模型准确性已完成。

## 命令入口

三个命令均支持--help；指定明确receipt／bundle及新的`.runtime/rehab_ml/run/`输出目录，不能选择“最新目录”。失败非零；已有标注包不覆盖。复用原验证下载器的发布版、许可、大小、MD5／SHA和原划分核对，不重新下载录像。原片只引用、不复制；小时间表和标注留在忽略目录。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py prepare-annotations --help
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py validate-annotations --help
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py import-annotations --help
```

实际本机包、校验、拒绝结果及测试证据另见本轮验收。没有专业标注时继续其他后端验收，不伪造标签启动微调。
