# 活动度评估配图 v1

2026-10-19。覆盖现有53项活动度评估，不增加动作、测量模型或临床能力。手机列表、动作详情、评估准备和已有计划缩略图共用 `mobile_rehab/static/assessment-artwork.js`，沿用现有页面导航和控件。

## 内容与范围

- 53个动作ID对应28张唯一封面：19张沿用已有公开动作图库，8张由内置 `image_gen` 新生成。腕部俯视照片另以 `hand-extension.webp` 共用，故新增9个WebP文件，合计310,558字节。
- 新图位于 `mobile_rehab/static/assets/assessment-artwork-v1/`；逐文件尺寸、输出SHA256、原生成图SHA256和来源写入同目录 `provenance.json`。
- 风格：中年东亚女性、深色马尾、白色短袖、黑色长裤、灰蓝摄影背景、柔和均匀光线。手部为同风格近景，无文字、箭头、光效或水印。
- 配图仅是动作/部位封面，不绑定本人左右侧、起点、出程或回程，不参与测角、次数、处方、视频分析及保存。手指同一手指的MCP/PIP/DIP项目共用部位概览；伸展项目共用自然伸手图，不宣称为单一关节标准动作图。
- 肘部采用坐位图，躯干后伸采用坐位轻微后移图，腕桡偏/尺偏采用俯视腕部图；不直接提升原先有姿势/机位冲突的候选图为分期教学素材。
- 清单与详情以 `object-fit: contain` 完整显示，不镜像、不改变解剖侧别、不裁剪人物。旧内部候选审阅入口仍独立存在，正常页面不读取未打包的候选目录。

## 生成提示词集

使用内置 `image_gen`，参考已有 `048_E-AXU-012_s02.webp` 的人物和摄影风格。以下为最终提示词规格；参考图只用于风格与人物，不作为患者照片或测量输入。

共同约束：

> ONE standalone rehabilitation app catalogue photograph, no card layout. Match the reference: same middle-aged East Asian woman with tied-back dark hair, plain white short-sleeve sports T-shirt and black trousers; seamless soft blue-gray studio background, soft even commercial healthcare photography. Portrait 4:5, generous margins, all relevant body parts visible, natural anatomy. No text, arrows, numbers, glow, watermark, border or collage. Static overview illustration, not a motion sequence or isolated single-joint clinical exercise.

各图姿势：

| 文件 | 具体提示 |
| --- | --- |
| elbow-seated | Right-side view, seated upright on stable gray armless chair, feet flat. Upper arm vertical beside torso, elbow bent approximately90°, forearm horizontal forward, palm up and hand relaxed. No weights. Full head, arm, chair and feet. |
| trunk-extension-seated | Side view, stable seated position, feet flat and pelvis centered on seat. Entire upper trunk shifts gently backward about10° from the hips. Neck aligned, hands on thighs, no dramatic arch. |
| wrist-overhead | Direct overhead close-up of a right forearm and hand resting palm down on matte blue-gray tabletop. Wrist neutral, fingertips toward top, thumb on image left. Exactly five natural digits, entire hand and short forearm visible. |
| thumb-flexion | Oblique palm-side close-up. Four long fingers comfortably extended; thumb gently bends across toward palm. No pinching or props. Entire right hand and wrist visible. |
| index-flexion | Oblique palm-side close-up. Index finger beside thumb gently curls toward palm; other long fingers comfortably extended; thumb relaxed outward. Curled fingertip visibly separate. |
| middle-flexion | Oblique palm-side close-up. Central middle finger gently curls toward palm. Other fingers comfortably extended with natural relaxation. Maintain the correct anatomical digit position. |
| ring-flexion | Oblique palm-side close-up. Ring finger beside little finger curls toward palm. Index and middle comfortably extended; natural mild linked bend in neighbors permitted. Keep five digits distinct. |
| pinky-flexion | Oblique palm-side close-up. Short little finger at outer edge curls toward palm. Three longer fingers comfortably extended with natural relaxation; thumb relaxed outward. |
| hand-extension | Reuse wrist-overhead photograph as an extended-hand region overview; no extra generation, mirroring or clinical joint claim. |

原始生成PNG留在本机生成目录，用户原有图片及数据库不改。项目只收录App使用的压缩配图及元数据；原始大图、私有运行材料和个人资料不进入Git。
