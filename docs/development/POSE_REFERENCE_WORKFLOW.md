# RGB 关键点参考、转换与误差评估

本流程落实后端任务书12.1–12.3的“缺数据时先完成转换／评估工具”。工具已实现，不表示已获得真人标注、完成姿态微调或提高准确率。仅离线后端；不改正式UI、APK、原YOLO或患者库。代码：[pose_dataset.py](../../tools/rehab_ml/pose_dataset.py)、[pose_inference.py](../../tools/rehab_ml/pose_inference.py)，入口：[cli.py](../../tools/rehab_ml/cli.py)。

## 1. 准备哪些输入

使用 [JSON模板](../../configs/rehab_ml/pose-reference-template.json) 建立一个完整参考清单。模板故意没有权限、坐标和split，不能直接当合法数据运行。把清单、原帧和权限证据放在受限的实验目录；真人资料不提交Git。

| 字段 | 内容与核验 |
| --- | --- |
| schema_version／schema_id／keypoint_order | 固定版本、COCO17解剖左右顺序；不能把Kinect25或MediaPipe33直接改成17点 |
| coordinate_space／frame_size | 原图像素、`[宽,高]`，工具核对实际PNG／JPEG尺寸；不自动旋转或双重归一化 |
| permissions | analysis／training独立；核验者匿名ID、权限文件相对路径及SHA256。软件检查存在与指纹，不代替法律／伦理审核 |
| sample_id／subject_group／recording_id／split | 匿名ID；先按人划分train／val／test，再取帧。人、录制或同一图像hash不能跨split |
| image_ref／image_sha256 | 清单目录内相对路径与实际原帧hash；拒绝逃逸、路径别名、大小写冲突和覆盖既有产物 |
| frame_seq／source_time_s／time_basis | 明确帧序和媒体PTS或接收单调时间；同录制时间须随序号增加，不把曝光时刻猜成已知 |
| exercise_id／side／view | shoulder_abduction／sit_to_stand／rehab_squat；解剖left／right、front／side |
| bbox_xyxy_px／bbox_origin | 人工完整人体框；不能仅用可见手臂点围成“全身框” |
| xy／visibility／annotation_mask | 都为17槽，按下表编码；可见性是独立人工标签，不是模型conf |
| annotations | human、匿名标注者／不同复核者、版本、明确独立复核。模型伪标签不进入独立参考 |

当前转换器支持独立人工二维RGB参考；经标定动捕投影、多人同帧、多相机标定投影和数据源专用自动映射尚未实现，不把它们宣称为可直接输入。每帧一个已标注参与者；同录制不允许换subject_group。所有三种split须非空，但这只是数据完整性检查，不证明样本量足够或临床独立性。

| 人工标注含义 | xy | visibility | annotation_mask | 坐标／可定位置信损失mask |
| --- | --- | --- | --- | --- |
| 未标注、不知道 | null | null | false | false／false |
| 明确无法定位 | null | 0 | true | false／true |
| 位置已标、不可见 | `[x,y]` | 1 | true | true／true |
| 位置已标、可见 | `[x,y]` | 2 | true | true／true |

“不可见但已定位”要求可靠独立参考，不由模型自己补点。fixture仅允许TEST，所有验证产物保留synthetic来源，不能改成真人数据。RESEARCH里的人工标签仍需真实采样与权限证据。

## 2. 转换为什么分两种

`masked`保存原坐标、null、annotation_mask及分开的coordinate_loss_mask／visibility_loss_mask，不创建训练YAML，不复制图片。

`yolo_pose`创建images／labels的三种split、dataset.yaml和完整provenance。图片逐字节复制并复核hash；bbox中心／宽高分别按原图宽高归一，左右翻转索引固定按解剖顺序。格式依据 [Ultralytics官方pose数据说明](https://docs.ultralytics.com/datasets/pose/)，不随该网站当前展示的新型号升级本项目。

本机锁定库Ultralytics8.3.199的`utils/loss.py`第643–647行：坐标损失用`visibility != 0`遮罩，关键点objectness BCE对全部点计算。该文件SHA256为`c09d05d83a514c8f7e7bd69dc489b68a8d3371745ad114d615339ced6992d7e0`。因此把未标点写成visibility0仍会训练“不存在”负例，工具拒绝任何annotation_mask=false的stock YOLO导出，而不是悄悄丢弃样本。只有明确标注为不可定位的0才输出`0 0 0`。

导出格式正确只返回`labels_format_ready=true`，`fine_tuning_qualified`仍false；尚须合法真人数据、旧模型同集误差／覆盖验收、实验资格与独立验证，不能导出后自动训练或覆盖权重。缺标部分骨架如果要训练，未来需同时修正坐标和objectness的masked loss，当前没有这条训练器。

## 3. 实际命令

以下路径是待填写的输入示例，不是已有真人数据。输出必须位于独立REHAB_DATA_ROOT或REHAB_RUN_ROOT的新目录，默认`.runtime/rehab_ml/data`或`run`；禁止写入正式docs、客户端、个人库或覆盖旧目录。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py build-pose-dataset --reference '.runtime/rehab_ml/data/授权参考/reference.json' --target-schema coco17 --output-format masked --output-dir '.runtime/rehab_ml/run/新转换'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py build-pose-dataset --reference '.runtime/rehab_ml/data/授权参考/reference.json' --target-schema coco17 --output-format yolo_pose --output-dir '.runtime/rehab_ml/run/新YOLO导出'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py infer-pose-reference --reference '.runtime/rehab_ml/data/授权参考/reference.json' --split test --output-dir '.runtime/rehab_ml/run/新原模型预测'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py evaluate-pose --reference '.runtime/rehab_ml/data/授权参考/reference.json' --predictions '.runtime/rehab_ml/run/新原模型预测/predictions.json' --split test --confidence-min 0.5 --pck-threshold 0.05 --output-dir '.runtime/rehab_ml/run/新评估'
```

每个命令支持`--help`，成功输出JSON产物路径／hash；失败为非零退出。旧`--dataset`官方数据资格入口保留，不能用它绕过缺少数据访问／授权；`train-pose`仍明确拒绝，不是隐藏的训练成功。

`infer-pose-reference`复用已有所属spawn YOLO进程、CPU640和原可信manifest，加载SHA`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`；不下载／升级。原帧不缩放、不镜像／转置，但明确重编码为quality95 JPEG，记录原图和实际推理JPEG的独立hash。每张图重置Context，不是连续视频tracker验收。按独立参考人体框IoU≥0.5唯一匹配；多候选为ambiguous，无匹配为no_person，不自动挑一个来增加有效覆盖。

只接收现有进程1920×1080像素预算与512KiB JPEG容量以内的输入，超出明确失败，不悄悄降清晰度。进程启动／推理／释放预算沿用已验证所属worker，不宣称OS创建调用有绝对硬截止。图片来源必须与该次清单hash相符；参考清单在运行期间变化则拒绝。

## 4. 如何读误差，为什么不能只看一个准确率

独立参考集合J只包含annotation_mask=true且visibility为1或2、坐标已标的点。预测需matched、有限且在原图范围、conf≥阈值才加入已覆盖集合C。

```text
e_j = || prediction_j - independent_reference_j ||_2       [原图像素]
d_s = sqrt((bbox_x2-bbox_x1)^2 + (bbox_y2-bbox_y1)^2)
normalized_error_j = e_j / d_s
coverage = |C| / |J|
mean_euclidean_error_px = sum(e_j, j∈C) / |C|
PCK_all = count(normalized_error_j ≤ threshold, j∈C) / |J|
PCK_covered = count(normalized_error_j ≤ threshold, j∈C) / |C|
```

像素均值是欧氏误差均值，不是角度MAE。默认PCK0.05按bbox对角线归一，是可配置工程指标，不是临床合格阈值；改变阈值要另报版本。缺预测／低conf／出画计入覆盖分母，不填0误差。J或C为空时相应指标为null。未标点不计为负例；明确不可定位的点单列其被预测为存在的数量。左右点比对只报“疑似交换次数”，不称已证实的解剖混淆。

结果同时包含逐关节、逐人、动作、视角、visibility分层和逐点证据；可追查某个均值是否只来自少数最清晰帧。预测绑定清单hash、原图hash、subject／recording／帧序／时间／尺寸及骨架顺序；重复、错位、未知样本拒绝。候选训练／选模声明须分别属于train／val的人群，不能声明用test训练；该检查不能证明第三方原始预训练绝未看过某人。

推理roundtrip按实际样本给出nearest-rank p50／p95，少量样本不能宣称稳定性能。当前不计算动作计次／角度金标准、临床准确率或人群置信区间；它们是下一步独立参考与端到端评估，不由关键点PCK替代。

## 5. 工具验证和边界

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_pose_tools.py
```

这条命令实际生成明确SYNTHETIC／TEST空图夹具，跑30项测试、masked与YOLO转换、原YOLO预测、覆盖评估，以及partial-label／缺资格训练非零拒绝。日志、源码hash与产物hash见 [工具验证摘要](../../reports/rehab_backend/pose_tools_verification.json)，完整范围见 [本轮验收](../validation/REHAB_POSE_TOOLS_2026-10-11.md)。不把空图、合成点或这30项测试称为真人准确率。所有原图、逐点产物、实验日志和测试库只留在E盘忽略目录。

本轮还单独调用本机Ultralytics8.3.199的`verify_image_label`读取该run三份PNG／标签：三种split均成功，keypoints形状1×17×3、corrupt=0，前后文件hash不变。这只是库格式兼容检查，没有执行训练；不以解析成功替代标注真实性、损失正确性或临床验收。

现有私人肩外展／深蹲录像只有分析授权，无训练许可和独立参考标注，未导入本工具或训练集。IRDS的Kinect3D整次标签也不是本工具的RGB二维真值。后续先取得权限、独立标点及专业动作边界，再比较当前／候选模型、端到端角度与完成率，最后决定是否实际微调。
