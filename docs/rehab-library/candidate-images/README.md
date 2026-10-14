# 康复候选图片接入 v1.0

本次是内部候选资源接入，不是医学审核或患者教学发布。现有53个动作、机位、计次、左右侧、start/move/return、计划与评估契约不变。185公共卡仍是公共资料，不等于185项相机支持能力。

## 配置及资源

- `mobile_rehab/static/assets/rehab-candidates-v10/resource-index.json`：185公共卡、656选用图片，原路径、原SHA、slot、选用来源/证据、图组、画面、尺寸及显示副本SHA。
- 同目录 `exercise-mapping.json`：全部53动作，25个有候选，28个手指无精确素材。18个允许内部封面预览；7个明确冲突仅在详情待审区/内部资源审阅器可见，不替换动作封面。
- 所有新增记录 `review_status=pending`，`patient_enabled=false`，实际 `side/phase=null`，两侧三阶段 `phase_slots` 全为null。`proposed_targets` 仅保存原分析CSV中的审核提议，绝不作为运行绑定。
- `cards/` 保留185卡原文；三份清单及 `mapping-source.csv` 保留来源。原始大图由本轮工作区 `work/rehab-images-v10/incoming/` 独立保留，包括archive；不在运行时扫描archive/references。
- 656个WebP是明确选用PNG的完整画面等比例显示副本，最大边1200px、质量92；不裁切、镜像、旋转或按修改时间/最高版本选图。显示副本约31MB；源PNG和源SHA另存。只用于内部预览，不是已核验教学衍生图。

## 本地启用

使用已有QA Python运行 `tools/serve_rehab_candidate_preview.py --data-dir <仓库外新TEST目录> --port 18971`。示例Python路径见本轮验收报告；不安装新依赖，不连接外部模型。

服务只绑定127.0.0.1；独立TEST档案，模型和语音关闭。首次输入本轮TEST连接码 `TEST-candidate-images`。

- 动作库：`http://127.0.0.1:18971/capture?tab=assess&entry=library&rehabSource=REPLAY_FILE&rehabImagePreview=1`
- 内部资源审阅：`http://127.0.0.1:18971/static/rehab-image-review.html?rehabImagePreview=1`
- 关闭：去掉 `rehabImagePreview=1`。普通正式服务不注入内部标记，即使附加参数也不开启预览。

内部标记由QA专用工具以同源外部脚本提供；原CSP、配对/API权限不变。正式index.html不携带启用标记。候选图片只在动作库/独立动作详情内使用，计划、准备、录像、实时跟练、结果和桌面ExerciseGuide不调用新候选逻辑。

## 审阅方式

动作详情保留原介绍和文字；待审材料折叠区显示准确slot、公共动作ID、独立图组、原画面描述、具体冲突；点击图片可放大，支持Esc关闭和焦点返回。所有图像contain，不裁掉必要部位。

因为当前没有任何通过审核的侧别/阶段，本轮全部集中在待审材料区，不自动归入准备/动作/回位。审核人须独立确认体位、本人侧别、机位、方向、起止位和辅助器械；通过后可登记逐图审核结果并在同一展示模块按确认字段分组。本轮不实施患者教学启用；批准正式指导还需另行授权与回归。

7个冲突动作：elbow_flexion、elbow_extension、shoulder_adduction、hip_adduction、wrist_radial_deviation、wrist_ulnar_deviation、trunk_extension。仅保留候选关系，正式阶段未映射。

## 重建及恢复

在已安装Pillow的离线QA环境运行：

`python tools/import_rehab_candidate_images.py --handoff <四包合并目录> --mapping <图片与动作映射表.csv>`

逐文件核对原清单SHA，拒绝路径越界或archive；保持052 s02原版、116 s06 v2的明确选择。导入工具只写自身资源/清单，不执行交接包工具，不修改动作、后台或数据库。重新生成会覆盖本目录自动生成的候选清单，因此完成后人工审核应另行保留审核记录，不能在未经核对的情况下再次导入覆盖审核成果。

Git恢复可独立恢复全部WebP、卡片及配置；原PNG是溯源/重新生成材料，在仓库外保留并另存校验记录，不属于运行时恢复必要依赖。新增公共资料许可和逐图医学准确性仍需确认，本轮没有上传或发布。
