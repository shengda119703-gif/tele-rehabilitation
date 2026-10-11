# 后端阅读版：功能、数据流与函数入口核对

日期：2026-10-11，Asia/Shanghai。只读源码基准：`11dc301f6cc6065d9df9b074e9ba7f76b9d09e49`。

## 范围

按用户请求更新一份可用于后端优化讨论的 [Markdown阅读版](../后端功能与技术实现梳理.md)，保留逐功能输入、实现、公式、输出、消费者及未完成边界。新增误差传播（22.8）、函数级定位和下游联测（24.1）、实验接口责任（24.2）、可复用记录模板（24.3）。修正旧资源协调说法：同checkout的v2与主要离线重任务已有准入，旧入口／APK／报告仍未完整覆盖。

本次只交付阅读版、文档索引、HANDOFF新增段落及本记录四份文档。没有修改业务或UI、运行训练／模型推理、分析私人视频、操作正常患者库、构建APK、启停用户服务或相机。历史测试与研究结果不作本次重跑或临床准确性证据。

## 直接对照的关键代码

| 链路 | 源码与核对内容 |
| --- | --- |
| 输入／视觉／几何 | `app/vision.py`、`quality.py`、`axial_geometry.py`、`joint_calibration.py`、`dual_view.py`；人物、骨架、EMA、起点、投影与辅助指标 |
| 评估／建议／执行 | `app/rehab.py`、`assessment.py`、`automatic_plans.py`、`training.py`、`movement_timing.py`、`guidance.py`；原函数、目标公式与工程准入、组次与质量分离 |
| 录像／健身／体态 | `mobile_rehab/analyzer.py`、`fitness.py`、`fitness_analyzer.py`、`barbell.py`、`posture.py`、`posture_analyzer.py`；作业分发、共用康复路径与独立器械链 |
| 健康／管家／照护 | `pipeline/events.ts`、`engine/baseline.ts`、`detect.ts`、`personTwin.ts`、`understanding.ts`、`care/CareCoordinator.ts`、`app/product/care_host.py`；事件归一、个人基线、真实函数与业务回执 |
| 权限／通知／场景 | `family/FamilyService.ts`、`notification/NotificationService.ts`、`app/activity.py`、`bedroom.py`、`safety.py`、`silver_service.py`；独立状态、权限投影与响应责任 |
| v2／训练／资源 | `mobile_rehab/rehab_v2/service.py`、`app/rehab_v2/sessions.py`、`resources.py`、`tools/rehab_ml/pose_dataset.py`、`pose_training.py`；最终提交、反馈CAS、报告独立、原生准入与研究资格 |
| 三端边界 | 既有阅读版与扩展索引、`android_offline/web/engine.js`、当前HANDOFF及各自原验收；手机独立规则不改成电脑版，源码交付不等于已安装APK更新 |

第22、24节的优化公式、隔离原则与模板是供团队选择的实验设计，不是本次已实施的算法，也不是当前存在的统一API。角度扰动例子是几何示例，不是假称实测结果。

## 文档与保留检查

本机实际检查如下。只做结构、源码定位与文件保护核对，不启动完整业务回归。

| 检查 | 实际结果 |
| --- | --- |
| 功能总表 | 34项主要后端能力；不把左右槽位当动作类别 |
| 新增函数索引 | 对照76个函数／类符号，缺失0；另直接阅读关键实现，符号存在本身不证明实机接通 |
| 阅读版结构 | 977行、21张表格列数一致、40个代码块围栏闭合 |
| 阅读版源码／文档链接 | 160个本地链接，缺失0 |
| 索引／HANDOFF／本记录链接 | 核对时分别57／61／1个，缺失0；历史交接段落未删除 |
| Git空白 | 本次文档差异检查通过 |
| 只读目录导入 | Python3.13.12、PySide6 6.11.2；康复53项、健身8项、体态2项；不加载视觉模型、不启动应用 |
| 既有保护基准 | 1308份文件重算SHA256，变化0；基准本身未重建 |
| 本次开工用户文件 | 280份素材、说明、任务书、CSV与导入脚本，按20份一批只读复核，变化0；排除提交 |

保护基准为`reports/rehab_backend/protected_files.json`，SHA256：`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`。文档检查和保护检查的实际输出见本次工具记录；未修改既有回归、训练或scope报告。

只读导入使用原`.venv/Scripts/python.exe -X utf8 -B`，设置`PYTHONDONTWRITEBYTECODE=1`及E盘临时目录。未安装依赖、下载模型或产生新训练产物。检查时C盘可用392445952字节、E盘11721072640字节；这只是当时读数，不沿用此前C盘0空间作为当前事实。

## 尚未验证或完成

真人RGB训练权限与独立专业参考、真人候选收益、康复深蹲的正式宿主计划、全产品资源协调、显式续训、目标手机／负载／物理故障仍待完成。自然语言照护原黑箱缺陷保留，没有本次修复结论。产品0.20.0、既有APK0.2.1、v2默认关闭；原首页／康复／健康／用药／家庭不变。

遵循仓库约定，本次文档在核对后单独提交／推送；桌面入口继续用原`Start-Rehab.ps1`与已验证`.venv/Scripts/pythonw.exe`，只更新Git版本描述，不开启或关闭用户应用窗口。
