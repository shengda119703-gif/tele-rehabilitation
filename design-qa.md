# 评估与训练 APK 上滑面板 QA

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
