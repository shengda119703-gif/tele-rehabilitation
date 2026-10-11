# 后端功能阅读版：当前代码快照核对

日期：2026-10-11，Asia/Shanghai。文档核对代码快照：`ab5dda0b8f24160c0e5b463885ba16bc7af1062c`；条件式姿态训练实现提交：`502a9f6d5dfcc4bb22b3cec0d77f041f011b4766`。

## 交付范围

更新 [后端功能与技术实现梳理](../后端功能与技术实现梳理.md)、索引与交接新增段落，加上本核对记录；只有四份文档。本次不实施算法，不改前端／业务／模型／APK／正常数据，不开启输入、不启停原服务、不运行训练。

阅读版已有逐功能输入、公式／规则、输出、消费者、字段与入口。本次补实际运行位置及事实存储（1.2）、连接与尚未闭环的边界（3.3）、按最早偏差定位（19.4）、负载／时效实验（22.7）。修正“多轮训练仍为工作区增量”的过时说法；已提交训练器与真人资格不足分别说明。

## 本次源码对照

| 范围 | 本次直接对照的入口 | 文档中的关键区分 |
| --- | --- | --- |
| 视觉与契约 | `app/domain.py`、`vision.py`、`quality.py`、`dual_camera.py`、`dual_view.py` | 像素／骨架／身份／时间、原点与因果滤波、各路二维观察 |
| 几何与动作目录 | `app/exercises.py`、`quality.py`、`geometry.py` | 动作类别与左右槽位、所需点、参考轴、镜像呈现不改解剖学侧别 |
| 自动计划 | `app/automatic_plans.py` | 最新证据、7天／覆盖／完整次工程准入、范围目标、反馈与冻结依据 |
| 电脑与托管网页 | `app/product/backend.py`、`bridges/ankang/client.py`、`mobile_rehab/desktop.py`、`unified.py`、`server.py` | 单业务worker、所属回执、固定owner、白名单、jobs与SQL的不同提交边界 |
| APK | `android_offline/web/local-api.js`、`motion.js`、`store.js`、`worker.js` | ProductService复用与手机视觉规则差异、业务串行、localStorage／IndexedDB独立 |
| 器械 | `mobile_rehab/barbell.py` | 标尺／NCC、局部二次拟合、采样与残差、自由重量外力与功率，不是肌肉测力 |
| 健康与照护 | `engine/baseline.ts`、`detect.ts`、`detection/rules/metricBaseline.ts`、`care/CareCoordinator.ts` | 基线／规则分数、原事实expected、十五分钟确认和宿主幂等回执 |
| v2生命周期 | `mobile_rehab/rehab_v2/service.py` | 有界队列、control／terminal epoch、finish权威提交后取消、报告独立 |
| 已提交研究链 | `tools/rehab_ml/pose_training.py`、`pose_masked_loss.py`、`model_registry.py`、`README.md`及已有验收 | train-only优化、val选模、test冻结、单pose作业锁不等于全产品资源协调 |

以上是源码和已有报告对照，不是新的真人测试。其余功能说明沿用阅读版、扩展索引及各自原验收范围；不将有适配器、接口或旧分支等同于实机全链接通。

## 检查与保护

本机实际检查结果：

| 检查 | 结果 |
| --- | --- |
| 阅读版相对链接 | 116个，缺失0 |
| 索引／交接／本记录相对链接 | 56／56／1个，缺失0 |
| 阅读版Markdown表格／围栏 | 18张表格列数一致；36个代码块围栏闭合 |
| 其他三份文档结构 | 表格列数一致，无未闭合围栏 |
| Git空白检查 | 本次文档 `git diff --check` 通过 |
| 原保护基准 | 1308个文件重新计算SHA256，变化0；基准未重建 |
| 开工用户文件 | 分20份一批只读核对280份SHA256，变化0；均不纳入提交 |
| 目录只读导入 | 本机Python3.13.12，康复53／健身8／体态2；不加载模型、不启动服务 |

保护基准沿用 `reports/rehab_backend/protected_files.json`，SHA256为 `75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`。阅读版SHA256为 `47214ec6fc073588903651f45accea99e883a7102a8b26a52780937b74c17d6e`。检查命令与输出在本轮工具记录中；未重写原scope报告或训练报告。

导入使用原 `.venv/Scripts/python.exe -X utf8 -B`、`PYTHONDONTWRITEBYTECODE=1`，临时目录指向E盘；没有安装或升级依赖。C盘可用空间仍为0，因此沿用原桌面入口的E盘符号链接恢复目标，不创建新的C盘构建／缓存，不删除用户文件。

## 结论边界

- 第18、19的建议评价、第22–23的优化和实验设计，不是本次已经实施的算法更改。
- 不重跑历史230／12／19项回归、工程训练或既有录像；不把历史数量作为本轮新验收或准确率。
- 合法真人RGB训练权限、独立关键点／动作参考、真人候选收益、康复深蹲宿主计划、全产品资源协调、目标手机／高负载／物理故障仍待完成。
- 自然语言人物／时间／用量的既有独立黑箱失败仍保留，没有此次修复结论。
- 产品0.20.0、既有APK0.2.1、v2默认关闭。提交后刷新原桌面快捷方式Git描述；旧页面、原服务和未保存窗口不动。
