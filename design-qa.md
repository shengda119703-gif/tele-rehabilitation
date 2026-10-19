# 视频第2帧预览与自动回放 APK 0.5.15 QA（2026-10-19）

沿用原选片和上滑回看布局。选片未播放显示本片真实第2帧，报告静音自动回放，暂停及拖动保留当前视频/标注。已实际查看`.runtime/video-presentation-20261019/final-browser/`的第2帧、2秒稳定预览、原深蹲报告暂停及拖动截图；巨型系统占位图已由真实视频画面替代，正常控件保留。封面刚赋值时的短暂加载弧1秒后消失，未因此引入样式改写。

MP4 B帧/CTTS、VFR MP4及VFR WebM真实颜色样片逐像素确认第2帧；Android早发seeked导致黑帧的问题由实际帧提交等待修复，最终原生三样片与原手势门禁下的静音自动播放通过。报告视频与标注暂停/拖动后双层像素指纹稳定。615项JS/14项Python通过，安装0.5.15/code65后原记录SHA不变；详细失败过程和范围见[验收](docs/validation/VIDEO_PRESENTATION_2026-10-19.md)。未重新设计Qt界面或改变测量规则。

# 动作库直接训练 APK 0.5.14 QA（上次记录保留）

功能修复：训练卡主按钮从错误的“选择评估动作”改为“开始训练”；122卡进入各自原图文步骤。沿用浅色库页面和现有深色运动回看配色，不改首页、Qt UI或测量逻辑。跟练页为大图/大字、明确步骤前后、前端用时、暂停和结束；图片是图示，用户点击下一步，不假称系统已观察完成。

已实际查看`.runtime/library-training-20261019/`下的`ankle-training-paused.png`、`training-detail-button.png`、`training-feedback.png`、`training-history.png`、`small-phone-training.png`、`desktop-training.png`与`emulator-training-detail.png`。430×932、360×740、1440×1000，以及Android412×789 CSS/DPR1.75。原按钮/卡片风格保持；深色正文、反馈select和下方控件对比清晰，图片contain不裁切；小屏信息区可滚动，步骤/暂停/结束操作可见。

122卡详情按钮逐项通过；实际踝动作跟练、暂停、退出/刷新续练、反馈与历史通过，旧健身录像分析也重跑通过。无页面异常/外部请求，不改原正式计划进度。独立图文记录明确为本机存储，未称为视频测量或自动跨端同步。原生只读核对开始按钮，没有代本人做训练并填入记录。最终包0.5.14已覆盖安装、原数据指纹未变；未发现阻断操作的呈现问题，真机与全部系统字号仍需另验。

# 统一动作库 APK 0.5.13 QA（上次记录保留）

本轮沿用现有动作库，功能范围为目录/别名/分析导航，不做新的视觉体系。原浅色底、微软雅黑/系统CJK、青柠选中态、44px触控分类和双列动作卡保持。新增“健身”第四分类；8张可分析卡前置，不让用户翻完185张图文卡才找到。

已实际查看`.runtime/unified-action-library-20261019/phone-fitness-library.png`、`phone-squat-upload.png`、`small-phone-library.png`、`desktop-library.png`及`emulator-fitness-library.png`。430×932、360×740、1440×1000；Android412×789 CSS/DPR1.75。深蹲/硬拉对应现有照片，四张无对应照片的卡采用项目原哑铃符号；首次文字占位显得空且重复，已替换并重打包重验。不用地板卧推或支撑单臂划船照片冒充杠铃动作。

分类选中、搜索、8项说明/拍摄/选片入口、两个明确图文直达入口、返回保留条件、资源失败降级已通过。本人原深蹲录像在隔离环境实际CPU分析并进入原上滑回看。原生覆盖升级不清数据，升级前后临床存储指纹相同。无横向溢出、页面异常0、外部请求0；未改变原计划/反馈/计次或已有上滑面板。最终截图未见阻断操作的呈现问题；真机摄像头与全部系统字号另行验证。

# 评估与训练 APK 上滑面板 QA（上次记录保留）

- Source visual truth: `E:/ai-video-lab/results/模型分析_20261018/v6_上滑交互版/audit/phone-collapsed.png`、`phone-expanded.png`，用户已确认的本地14929交互稿。
- Implementation: `.runtime/apk-motion-review-20261019-final/assessment-collapsed.png`、`assessment-expanded.png`、`training-collapsed.png`、`training-feedback.png`；原生Android截图 `.runtime/apk-motion-review-20261019/emulator-live-ready.png`。
- Viewport: 同尺寸430×932 CSS px、DPR1；源与浏览器截图均430×932像素。补测360×740与1440×1000。Android实际412×789 CSS px、DPR1.75，720×1380截图；原生图单独按真实密度检查，不当作与430px稿逐像素一致。
- State: 同为暂停回看约4秒、收起/展开；参考是深蹲样片，实际验收为已有肩外展录像，数值和画面不同属有意的真实内容替换。
- Full-view combined evidence: `.runtime/apk-motion-review-20261019/full-final.png`、`expanded-final.png`。
- Focused combined evidence: `.runtime/apk-motion-review-20261019/focused-final.png`，对比数字、单位、结论、按钮与播放区。

## 比较与修复历史

初轮 blocked：单位/结论节点混选(P1)、展开后骨架越出画面(P1)、反馈暗底黑字(P1)、主按钮被播放区裁切(P2)。修正直接子节点、媒体尺寸监听、反馈颜色与滑块、收起/小屏布局。`full-before/expanded-before/focused-before.png`保留失败证据；after图显示上述修复。

后轮 blocked：旧主题主要按钮悬停变暗(P2)、实时提示仍继承黑字(P1)、Android未打开相机显示系统巨型海报(P2)。显式限定主要按钮/提示令牌，未有视频帧时隐藏video而保留相机尺寸和原授权控件；不提前打开相机。

## 五项呈现核对

- 字体：微软雅黑/系统CJK回退，42px主值、36px次值、31px指标；标签/说明下沉，数字等宽。Android使用系统字形，非强制打包商用字体。
- 布局：原44%/76%上滑比例、完整人物contain、固定播放区保留。新增计划/反馈操作占用较紧凑间距；小屏收起仅保留主指标，次值在展开内，属于功能接入的明确调整。
- 颜色：#292630面板、#36323e卡片、#f7f7f9正文、#c3becb辅助、#40e5b5曲线、#099b6d主值、#ffd091关注结论。反馈与悬停使用同一深色令牌。主数字大字号白/绿对比约3.55:1；辅助/绿色文字分别约6.86:1/7.78:1。
- 图像/图标：实际用户授权录像，人物不裁切；标注来自本次推理而非预制图；原Bootstrap MIT符号同参考，不新造插画。空相机不拿样片冒充实时画面。
- 文案：短指标+紧随的结论；不显示完成次数，不把动作角度差写成两腿力量；原方案确认/真实反馈必填保持。

交互已验：上滑/指针、键盘、进度/播放、当前/全段、指标曲线、AI往返、原反馈保存、账号切换失效、小屏主要按钮完整可见。浏览器异常0、外部请求0。最终重新捕获并实际查看full-final、expanded-final、focused-final同屏对比及原生空预览：骨架随缩放对齐，主按钮完整且悬停对比正常，反馈/实时提示可读，未打开相机时不再显示系统海报。五项呈现核对无剩余P0/P1/P2。

残余边界：未测试红米真机摄像头、全部动作精度及所有系统字号；这些不视为已通过。现有录像帧本身的运动模糊保留原貌，不做美容或补帧。源码实现与参考的CTA、侧别文字和真实指标不同属于已说明的产品接入，而非样式缺失。

final result: passed
