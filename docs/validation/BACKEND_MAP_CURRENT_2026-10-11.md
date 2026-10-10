# 全后端梳理：当前源码与逐跳交接核对 · 2026-10-11

## 交付与范围

用户要求 Markdown，逐项梳理全部后端功能、实现方法和功能间传递的信息，以便讨论准确性与可靠性优化。

主文件：[后端功能、算法与数据流梳理](../BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md)。本轮仅更新该文件、[HANDOFF](../HANDOFF.md)、[文档索引](../README.md)与本记录。源码审查基准为 main 的 `129e5cb67e15af09d1508e715214f7e60e6da2f9`；没有实施报告隔离或其他算法修改，不因正在进行的后端总目标扩大本轮授权。

产品仍0.20.0、APK仍0.2.1、康复v2默认关闭。正式首页／康复／健康／用药／家庭导航和入口不变；没有新安装包、UI修改、依赖升级、服务启动／重启、相机／麦克风操作或正常数据库写入。

## 内容与依据

完整读取既有全后端文档，结合当前交接、提交与现存报告审查以下入口：

- v2 `api.py` 的认证操作、JPEG接收和diagnostics；`service.py` 的冻结计划、source／trace、控制epoch、推理前后检查、EMA、检查点、最终提交、报告、反馈和关闭。
- `pose_worker.py` 的所属推理、身份／序列／时间绑定、有界传输和取消释放。
- `protocols.py`、`evidence.py`、`engine.py` 的必要点、可选质量指标、观测／过滤、准备和计次含义。
- `sessions.py` 的namespace版本、canonical commit、唯一贡献、反馈revision、报告CAS和历史ordinal；`compatibility.py` 的指标含义与证据身份区别。
- `server.py` 的v2显式启用、原保存计划绑定和当前支持边界；`ProductService.ts` 的档案scope、健康／chat入口、家庭投影及禁用能力。
- 原视觉、康复、健身／器械／体态、活动／安全、健康／管家／语音／OCR／用药／家庭、三端存储和训练的已有模块导航。没有声称本轮逐行审查了全仓库或验收全部功能。

新增快速导航及第21节：康复逐跳交接表、不同结果的最小证据、v2控制／计算／保存顺序、健康／照护语义链、建议诊断账本与六项优化讨论问题。保留具体几何、EMA、时间、求导／力学、健康基线与研究模型公式；建议评价方法明确不是当前实测成绩。

纠正文档旧状态：所属推理与有界诊断已经在129e5cb提交；历史核对文档继续保留当时“未提交”的状态。性能报告的运行版本4d46061＋当时工作区增量不倒改为129e5cb。报告仍为线程、v2尚未接正式页面／APK／原管家事实链、深蹲宿主计划仍缺、目标RGB授权／独立标签和临床精度未知，继续如实列出。

## 本轮实际检查，不是新跑工程／准确性测试

1. 读取当前Git提交、remote和dirty清单；对280份既有用户素材／说明／任务书／CSV／导入脚本保存SHA256，交付时复核。
2. 产品Python只读导入：Python3.13.12、PySide6 6.11.2；没有启动应用。
3. 重新计算下表现存日志SHA并核对尾部与已保存报告。没有重跑100／12／19或70项测试，也未重跑训练／性能／私人录像。
4. 实际运行保护范围校验：1308文件一致、changes为空，基准SHA `75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`。此次时间为 `2026-10-10T21:01:44.315549+00:00`；工具会改写报告时间戳，已用apply_patch只恢复本轮产生的单字段变化，保留旧回归报告原证据。本轮结果记录在这里，不重写旧验收。
5. 实际检查四份文档：268个本地链接存在，7个跳转显式锚点存在，43个连续表格块列数一致，代码围栏闭合，Git空白检查通过。280份既有用户文件SHA256一致；暂存范围限定四份文档。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/cli.py verify-scope --baseline reports/rehab_backend/protected_files.json
git diff --check
```

首次定位时查询了不存在的`tools/rehab_ml/scope.py`，是只读路径查找错误；通过rg文件列表和CLI导入定位到实际`inventory.py`，未因此修改源码。上述保护命令成功，不将路径查找错误隐去或算作业务测试失败。

### 复核的现存日志

| 现存运行 | 原结果／范围 | 本轮复核SHA256 |
| --- | --- | --- |
| verification-7ec35ad4／new_backend | 100项通过；原工程验证，不是真人准确率 | `26edf5c8da50ed30a5c54b450f8b913b7c870ce7faa7ad0872de592629fd4a9c` |
| 同run／legacy_rehab | 12项通过 | `08fbe870f346085a0f22fc43b802e62b0bbebf17efb3fe0533cd5415463801ba` |
| 同run／legacy_mobile | 19项通过、1条既有弃用warning | `de1527d84c3831809ed7cb26a558cbaa170f1b631c3b5e924162784db4c92d6e` |
| 同run／scope | 原1308文件保护检查 | `6d5f9c57ba17a1e2a439bf261f06d59cfc912dcb5c3bbcd179e8caa9ed0a81d6` |
| replay-a339171a／sessions | 70项，为100项子集，不能累加 | `23b0b008096925aa21d0ae4de9096db5af69074ef0c13ba745f4a300e9ccae6f` |

精确命令、运行环境、性能原始值和未测范围继续见 [进程与诊断验收](REHAB_V2_ISOLATION_TELEMETRY_2026-10-11.md)。本轮没有新增外部模型或医疗效果论断；软件阈值不称临床金标准，数据源和预测结果不互相冒充。

## 保留与交付

不提交既有用户280份文件，不收录环境、模型、私人媒体、患者库、运行日志或签名；没有关闭原窗口／服务。提交后核对origin/main与本地完整SHA一致，并用`New-RehabDesktopShortcut.ps1`刷新桌面“安康康复（最新版本）”Git描述，继续指向当前Start-Rehab.ps1和已验证的`.venv/Scripts/pythonw.exe`。

后端总任务仍为局部完成；本轮只完成该文档请求，不宣称完成报告硬隔离、真实存储故障、目标RGB训练、手机实测或临床验收。
