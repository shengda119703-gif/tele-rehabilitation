# 安康移动 Web 首页 V3.6 正式集成验收记录

日期：2026-10-11。实施基准：`2ddbba07c660be84839868e659d774d3c4abb8f9`；独立分支：`feat/mobile-home-v36`。本次只交付移动 Web 首页，待用户视觉审核，不合并 main，不继续改造其他页面。首页视觉标识为 V3.6，未改产品版本、APK 版本或桌面入口。

源码提交：`23969a6`。已本地提交验收资料；推送 `origin/feat/mobile-home-v36` 时 GitHub 返回 403，当前认证账号 `WorkingArtistWang` 没有仓库写权限，**尚未上传**。需要有权限的账号后再推送同一分支；未创建 fork、切换账号或合并 main。

## 1. 实施结果与范围

已完整读取附件 `CODEX_START_HERE.md`、README、确认版 HTML，以及 390 / 320 浏览器参考截图。确认 HTML 的模拟业务与整张主卡不进入生产；按照附件要求将主卡拆为黑底、透明人物、独立 SVG 黄线、真实文字和真实按钮。按仓库 [ui-polish Skill](../../.agents/skills/ui-polish/SKILL.md) 执行冻结、组件检索、截图和回归闭环；已有 React 动效组件不适用于本次固定视觉及原生 JS 实现，因此未引入新框架或依赖。

模块顺序保留：搜索 / AI → 周日历 → 本周训练 → 今日主任务 → 我的计划 / 历史报告 → 今日其他安排 → 纯文字五栏目底栏。日期、档案、来源和刷新入口以轻量控件保留在内容末尾；390 正常状态下这些次级控件可能需要轻微滚动，核心模块和其他安排行在首屏可见。长标题在主卡左侧收紧字号，最多显示两行，完整标题保留于 DOM / title；未增加压暗人物的蒙层。

主卡固定 `#000`。透明人物只有一张无文字 PNG，Alpha 0–255；自然肤色、衣服和手臂保留。荧光黄斜线由独立 SVG 绘制且位于人物后方。标题、剂量、侧别、时间、序号及 CTA 都为独立前端元素。装饰人物不代表当前用户、摄像头、测量结果或动作教学依据。[资产来源与 SHA256](../../mobile_rehab/static/assets/home-v36/README.md)；[实际抠图提示词](mobile-home-v36-20261011/evidence/asset-extraction-prompt.txt)。

## 2. 真实数据与点击路径

首页继续读取 `GET /api/unified?source=LIVE_CAMERA|REPLAY_FILE`，没有新增接口或保存路径。[共享手机接口](../../mobile_rehab/unified.py)、[ProductBackend 快照](../../rehab_codex_single_camera_v2_1/app/product/backend.py)、[作用域只读工具](../../rehab_codex_single_camera_v2_1/app/rehab_read_tools.py) 均未修改。

| 模块 | 实际来源 / 行为 |
| --- | --- |
| 自然周 | 所选日期的本地周一至周日；跨月 / 跨年日期按本地日历计算 |
| 本周训练 | `rehabilitation_ui['rehab.get_training_history'].records` 的已保存、已终结记录，核对本人 / 当前来源 / SELF_USE，按 `end_utc` 转本地日期去重。上传、失败、未保存不计入；表述为“天有记录”，不等同计划已完成 |
| 今日主任务 | 已有活动计划的 `progress.next_key`、`next_available`、`availability_reason`、`progress.blocked`、动作标签、侧别与 `settings`；匹配日期安排的真实时间，未安排不造时间 |
| 手机录像主按钮 | 核验最新快照及请求世代、档案、来源、日期后进入 `/capture?tab=plan`；继续使用原计划 / 条目 / 剂量及训练准备校验 |
| 电脑实时主按钮 | 手机仅查看原计划详情，不发起电脑实时训练；首次评估进入原康复页选择方式 |
| 计划 / 报告 | 原 `planDetail()` 与 `#records`；手机报告仍由原 `/capture?tab=history` 提供 |
| 其他安排 | 原 `dailyProduct.schedules` 与原 `doses()`；只按安排 ID 排除占主卡的同一任务，保留同计划其他时刻。训练到 `#rehab`，用药到 `#medication`，携带所选日期 |
| 搜索 / AI | 搜索入口明确告知尚无全局搜索，链接现有动作库、计划、记录；动作库搜索实际可用。AI 仍进入 `#assistant`，没有假装接通外部模型 |

缺口安全降级：现有日期安排没有与逐次训练完成关联的完成数契约，因此“今日安排”显示真实安排数量，不照搬演示稿“1/4 已完成”。动作序号来自实际下一条目；本次 TEST 计划为 `03/04`。参考截图中的固定日期、时间、3 天记录与完成数都是演示数据，不用于生产。

请求失败后清空旧快照，显示“暂未读取 / 安排暂时无法读取”，不显示虚假的零记录或已完成。重连成功留在首页，不自动启动恢复后的任务。重新配对沿用原鉴权并清空旧快照、草稿和首页日期传递状态。

## 3. 实际环境与截图

本机 macOS；Python 3.12.14、PySide6 6.11.2、FastAPI 0.142.2、pytest 9.1.1、Node 24.19.0。复用此前已批准的隔离 QA 环境和锁定 Node 依赖；没有安装新依赖、模型或浏览器。Node 依赖只以本次 checkout 的临时链接复用，未提交。桥接使用仓库现有构建脚本。

使用 Codex 内置真实浏览器（IAB），实测 390 × 844、320 × 844；未采集内核版本。正式 `serve-review.py --complete` + ProductBackend / SharedProduct 在 127.0.0.1:18879 提供完整 **TEST 林女士** 档案；另一份由已有脚本创建的临时 TEST 档案在 18880 提供首次使用状态。没有连接个人档案、外部模型、摄像头或麦克风。

下列均为浏览器截图，参考稿单独标为“确认稿”。文件尺寸已检查；图片没有后期拼接、重绘或模拟 UI。

| 对照 | 390 × 844 | 320 × 844 |
| --- | --- | --- |
| 原正式首页 | [改造前](mobile-home-v36-20261011/screenshots/before-390.jpg) | [改造前](mobile-home-v36-20261011/screenshots/before-320.jpg) |
| 用户确认稿 | [确认稿](mobile-home-v36-20261011/screenshots/approved_390x844.png) | [确认稿](mobile-home-v36-20261011/screenshots/approved_320x844.png) |
| 本次正式首页 / 手机录像 | [实际运行](mobile-home-v36-20261011/screenshots/home-replay-390.jpg) | [实际运行](mobile-home-v36-20261011/screenshots/home-replay-320.jpg) |
| 首次使用 / 空周 / 无其他安排 | [实际运行](mobile-home-v36-20261011/screenshots/first-use-empty-390.jpg) | [实际运行](mobile-home-v36-20261011/screenshots/first-use-empty-320.jpg) |
| 训练受阻 | [实际运行](mobile-home-v36-20261011/screenshots/home-blocked-390.jpg) | [实际运行](mobile-home-v36-20261011/screenshots/home-blocked-320.jpg) |

[主卡先行复核](mobile-home-v36-20261011/screenshots/hero-first-pass-390.jpg)保留了分层主卡接入早期、其他模块尚未更换的正式页面截图。最终核心指标见 [浏览器布局证据](mobile-home-v36-20261011/evidence/browser-layout-metrics.json)：390 主卡 x=20、y≈280.34、350×206；320 主卡 x=15、290×170.68。两尺寸文档宽度等于视口宽度；主按钮高 44；七个状态条；五栏目仅文字。390 手机录像的其他安排底部≈743.94、底栏顶部=772；电脑实时说明保留后底部≈770.53，仍可完整查看安排行。人物 `filter:none`、`mix-blend-mode:normal`，黑底实测 `rgb(0,0,0)`。

## 4. 功能验证

- **通过 / 真实浏览器：** 我的计划打开原详情；主任务进入原手机计划，下一项肩前屈、本人左侧、5 次 × 1 组一致；继续进入原准备页，机位、侧别、角度目标和停止提醒保留。[计划](mobile-home-v36-20261011/screenshots/plan-detail-390.jpg)、[准备页](mobile-home-v36-20261011/screenshots/training-prepare-390.jpg)。未开始真实录像分析。
- **通过 / 真实浏览器：** 已有 TEST 保存报告可查看；同一反馈版本被另一合法 TEST 请求更新后，旧结果页提交显示“训练感受已更新，请重新打开报告；本次填写尚未保存”，输入仍保留，未错误继续。重新打开报告、按最新版本保存后返回原训练计划，仍为肩前屈 5 次 × 1 组。[失败提示](mobile-home-v36-20261011/screenshots/save-conflict-390.jpg)、[返回计划](mobile-home-v36-20261011/screenshots/result-return-plan-390.jpg)。报告内容由现有 TEST 工具预先写入，不是本轮模型识别结果。
- **通过 / 真实浏览器：** 单独停止本任务 TEST 服务后刷新显示未知状态与重连入口，未沿用旧记录；恢复服务、重连后留在首页。[断连](mobile-home-v36-20261011/screenshots/home-offline-390.jpg)。
- **通过 / 真实浏览器：** 临时 TEST 档案没有计划和训练记录，首次评估进入原康复评估动作库；将这份临时 TEST 的用药安排生效日设为明天后，今日无其他安排。只调用既有接口。
- **通过 / 真实浏览器：** 改选 10 月 10 日后，时间线显示该日用药状态；点击进入原用药页仍是 2026-10-10。[所选日期](mobile-home-v36-20261011/screenshots/home-selected-date-390.jpg)。来源切换重新读取数据，无旧来源闪现为有效任务。
- **通过 / 真实浏览器：** 五栏目、历史报告、搜索弹窗、现有动作搜索、AI 与档案编辑入口可达。搜索弹窗选链接会关闭，Escape 可关闭；仅查看档案编辑，未改真实身份。[搜索](mobile-home-v36-20261011/screenshots/search-entry-390.jpg)、[动作搜索](mobile-home-v36-20261011/screenshots/existing-action-search-390.jpg)、[档案](mobile-home-v36-20261011/screenshots/profile-entry-390.jpg)。
- **通过 / 真实浏览器 + 后端状态：** TEST 不适反馈使原计划返回 `progress.blocked`；首页改为查看结果并完整保留原阻断提示。随后通过原反馈接口恢复 TEST 分数，确认受阻原因清空。没有直接改数据库或绕过业务校验。
- **通过 / 自动回归：** 跨参与者、来源、使用场景隔离；日期跨月跨年；未保存 / 失败排除；同日去重；任务重新核验时身份 / 日期 / 来源 / 世代变化取消跳转；配对清空；未来用药仍禁止记录；原医疗反馈、上传同意与 API 权限不变。
- **未执行 / 界限：** 正式界面没有本人多档案切换器，本轮未新增；跨档案隔离由已有 owner-bound 手机服务测试与新增前端换人取消测试验证，未声称真实多用户浏览器切换通过。相机、真人训练、完整模型分析、外部模型与语音实机未验收。

隔离 TEST 的持久变化只有：连接测试设备；用药计划在临时档案的生效日期；反馈版本冲突及阻断测试的感受修订。分数已恢复为原 0 / 3，版本号保留真实写入的递增；未伪造版本回退或恢复审计历史。临时服务结束即释放临时档案；完整 TEST 证据仍在被忽略的 `qa-output/home-v36/`。未操作患者库。

## 5. 回归结果与未通过项

| 检查 | 本次结果 | 证据 |
| --- | --- | --- |
| 改造前原 Node 页面测试 | 42 / 42 通过 | [日志](mobile-home-v36-20261011/evidence/baseline-node.log) |
| 改造后 Node 手机页面测试 | **54 / 54 通过**，含新增投影和状态竞争测试 | [日志](mobile-home-v36-20261011/evidence/post-node.log) |
| Python 手机服务及 TEST fixture 回归 | **139 通过、3 跳过、4 失败** | [完整日志](mobile-home-v36-20261011/evidence/post-python.log) |
| 现有 bridge 构建 | 退出 0 | [日志](mobile-home-v36-20261011/evidence/bridge-build.log) |
| 已有 Skill 来源清单 | 110 份匹配 | [日志](mobile-home-v36-20261011/evidence/skill-sources.log) |
| 最终正常浏览器场景 | 0 条 warn / error | [浏览器日志](mobile-home-v36-20261011/evidence/browser-console-final.json)，不把故意断网 / 保存冲突算成无错误场景 |
| 文件边界与差异 | 622 份基准文件中仅原首页入口、首页控制器、对应测试改变；`git diff --check` 通过 | [SHA256 核对](mobile-home-v36-20261011/evidence/integrity.json) |

4 项失败为 `test_real_local_model_live_empty_frame_no_false_counts`、`test_fitness_mode_real_model_empty_video`、`test_real_capture_model_and_empty_report`、`test_real_blank_video_saves_under_desktop_owner_and_keeps_source`。真实空帧 / 空视频分析未完成；日志提示本 checkout 没有本地 `YOLO11n-pose` 权重，实时分析返回模型中断。相关 Python / 算法源文件与基准相同，未以本次首页工作为由下载模型、修改测试预期或绕过校验。3 项跳过对应可选语音模型及本地 ASR / OCR 验证材料缺失。不能把这些项目写成通过。

交付日志副本仅清理行尾空白，未改测试内容、预期或结果；原始日志保留在本地 `qa-output/home-v36/`。

复核命令（仓库根目录，复用已有 QA 环境）：

```sh
node --test mobile_rehab/tests/*.cjs
PYTHONPATH=.:rehab_codex_single_camera_v2_1 python -B -m pytest -q mobile_rehab/tests tools/ui-polish/test_test_lin_profile.py
node ankang/route1-health-agent/scripts/build-agent-bridge.cjs
python -B tools/ui-polish/verify-sources.py
```

## 6. 修改文件清单

正式前端：`mobile_rehab/static/unified.html`（加载与缓存版本）、`unified.js`（首页绑定、重验、日期传递、首页导航文字）、`home-v36.js`（只读投影与分层 DOM）、`home-v36.css`（首页范围的确认版视觉）、`assets/home-v36/athlete-cutout.png`（装饰资产）、`assets/home-v36/README.md`（来源与 hash）。

测试：`mobile_rehab/tests/test_home_v36.cjs`；`test_unified_presentation.cjs`（适配已批准首页及新增重连 / 竞态 / 日期回归）。文档：本记录、对应 TEST 截图与证据目录、`docs/HANDOFF.md` 的本次条目。没有改共享样式、`app.js`、其他页面内部业务、APK、桌面、后端、依赖、环境配置、接口或数据库定义。

## 7. 待审核与未解决边界

1. 请审核真实人物抠图、斜线强度与整体还原；参考主卡是合成图，当前独立图层不承诺逐像素一致。
2. 全局搜索及逐日安排的完成关联不存在；本次使用诚实入口和真实安排数量，未扩展后端。
3. 本机缺少姿态模型，4 项相关回归未通过；有完整模型环境后仍需完成原模型用例及真实视频链路验收。
4. 原训练准备 / 结果页保持原样，本次没有落实这些页面的新视觉或导航改造。Android / Windows 真机和外部模型未验证。
5. 当前为 macOS，无法维护原 Windows `.lnk` 快捷方式；未创建假快捷方式或改变桌面版本。已关闭本次独立 TEST 服务，保留其他会话服务和窗口。

首页已完成正式代码接入与上述范围内的运行验证，停止在首页审核节点。没有将本次结果等同于临床、算法准确性或其他客户端验收。
