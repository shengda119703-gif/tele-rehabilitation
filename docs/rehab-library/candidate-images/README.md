# 康复候选图片接入 v1.0

2026-10-15：按用户确认，18个无明确映射冲突的候选动作配图已开放到正常康复动作库及动作详情，无需本地标记或查询开关。图片仍待医学审核，不改变原动作说明或临床阶段绑定。现有53个动作、机位、计次、左右侧、start/move/return、计划与评估契约不变。185公共卡仍是公共资料，不等于185项相机支持能力。

## 配置及资源

- `mobile_rehab/static/assets/rehab-candidates-v10/resource-index.json`：185公共卡、656选用图片，原路径、原SHA、slot、选用来源/证据、图组、画面、尺寸及显示副本SHA。
- 同目录 `exercise-mapping.json`：全部53动作，25个有候选，28个手指无精确素材。18个通过独立的 `catalog-display.json` 开放正常动作库/详情配图；7个明确冲突仍仅供内部资源审阅，不替换动作封面。
- `catalog-display.json` 明确选择18个动作的封面slot；所有18个动作均选用该动作已有候选列表的最后一张展示动作画面，不自动选择最新版本，不改变左右侧与阶段。此文件与生成映射分开维护，重建导入后应复核封面仍属于原动作候选。
- 所有新增记录 `review_status=pending`，`patient_enabled=false`，实际 `side/phase=null`，两侧三阶段 `phase_slots` 全为null。`proposed_targets` 仅保存原分析CSV中的审核提议，绝不作为运行绑定。
- `cards/` 保留185卡原文；三份清单及 `mapping-source.csv` 保留来源。原始大图由本轮工作区 `work/rehab-images-v10/incoming/` 独立保留，包括archive；不在运行时扫描archive/references。
- 656个WebP是明确选用PNG的完整画面等比例显示副本，最大边1200px、质量92；不裁切、镜像、旋转或按修改时间/最高版本选图。显示副本约31MB；源PNG和源SHA另存。用于动作库配图和内部资源审阅，不代表已完成医学核验。

## 正常动作库展示

正式移动Web正常连接后进入“康复 → 动作库”，18个动作直接显示已选图片，详情顶部大图汇集同动作的全部配图（共38个关联图位），左右滑动或使用切换按钮、方向键浏览，点击放大；不再设独立待审核素材折叠区。进入详情默认定位到封面的最后一张。图片加载失败仍可阅读原文字；28个无精确图和7个冲突动作不借图替换。`patient_enabled=false` 仍表示未开启临床步骤指导，与目录配图展示开关分开。

动作卡图片宽度铺满、按原图比例自适应高度，零内边距，不使用cover裁切或镜像；横图保持横图比例，避免塞进固定竖框产生白边。详情/放大仍保留完整源画面。

## 内部完整资源审阅

使用已有QA Python运行 `tools/serve_rehab_candidate_preview.py --data-dir <仓库外新TEST目录> --port 18971`。示例Python路径见本轮验收报告；不安装新依赖，不连接外部模型。

服务只绑定127.0.0.1；独立TEST档案，模型和语音关闭。首次输入本轮TEST连接码 `TEST-candidate-images`。

- 动作库：`http://127.0.0.1:18971/capture?tab=assess&entry=library&rehabSource=REPLAY_FILE&rehabImagePreview=1`
- 内部资源审阅：`http://127.0.0.1:18971/static/rehab-image-review.html?rehabImagePreview=1`
- 去掉 `rehabImagePreview=1` 关闭完整内部审阅。正常动作库的18项配图始终可见；内部标记只控制185卡完整审阅和7个冲突素材池。

内部标记由QA专用工具以同源外部脚本提供；原CSP、配对/API权限不变。正式index.html不携带启用标记。候选图片只在动作库/独立动作详情内使用，计划、准备、录像、实时跟练、结果和桌面ExerciseGuide不调用新候选逻辑。

## 审阅方式

动作详情保留原介绍、文字和原业务操作；配图在主图轮播内按已有候选列表顺序排列，仅标注图片张数，不将图序伪装为准备/动作/回位或本人左右侧。显示完整源画面；上一张/下一张有边界禁用状态，支持键盘与减少动态效果。图片加载失败仍显示原文字说明。内部完整资源审阅器继续保留准确slot及来源图组；具体映射问题和提议完整保留在原JSON/CSV中。

因为当前没有任何通过审核的侧别/阶段，目录图片均已进入详情主图轮播，但不自动归入临床准备/动作/回位。审核人须独立确认体位、本人侧别、机位、方向、起止位和辅助器械；通过后可登记逐图审核结果并在同一展示模块按确认字段分组。正常动作库已开放配图；未改写临床阶段绑定或算法，也不把待审核状态改成已审核。

7个冲突动作：elbow_flexion、elbow_extension、shoulder_adduction、hip_adduction、wrist_radial_deviation、wrist_ulnar_deviation、trunk_extension。仅保留候选关系，正式阶段未映射。

## 重建及恢复

在已安装Pillow的离线QA环境运行：

`python tools/import_rehab_candidate_images.py --handoff <四包合并目录> --mapping <图片与动作映射表.csv>`

逐文件核对原清单SHA，拒绝路径越界或archive；保持052 s02原版、116 s06 v2的明确选择。导入工具只写自身资源/清单，不执行交接包工具，不修改动作、后台或数据库。重新生成会覆盖本目录自动生成的候选清单，因此完成后人工审核应另行保留审核记录，不能在未经核对的情况下再次导入覆盖审核成果。

Git恢复可独立恢复全部WebP、卡片及配置；原PNG是溯源/重新生成材料，在仓库外保留并另存校验记录，不属于运行时恢复必要依赖。新增公共资料许可和逐图医学准确性仍需确认；资源已随PR #11进入Git，目录展示不代表医学审核或生产部署完成。
