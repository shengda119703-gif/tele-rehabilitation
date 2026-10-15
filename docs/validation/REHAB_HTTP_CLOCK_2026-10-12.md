# 康复v2 HTTP时钟：本机诊断、断流与回归

日期2026-10-12（Asia/Shanghai），开工`3376265167d329aed980e5af718bd48a370eee98`。本轮继续后端任务书，不是前端或APK更新。原失败根因未证明，整项后端目标未完成；以下为隔离工程结果，人工证据复核pending，不是科学投稿或临床验收。

## 问题与方法

原`verification-f28dac51`455项／1失败：最终64／64／64已保存，完整次数0，旧断言要求1。原日志没有逐帧时间／阶段，不补造其根因。[时钟工作流](../development/REHAB_HTTP_CLOCK_AUDIT.md)说明TEST角度、真实接收时钟与固定证据时钟的不同职责。所有病例为白图JPEG＋明确TEST几何钩子，不是拍摄真人或运行新视觉模型。

探针在真实配对／认证／JPEG、原服务／引擎／SQL／结束链上记录时间、dt、阶段、基线、逐次和失效原因。不修改生产时钟和500毫秒连续性阈值。固定证据时钟的正例只验证接口／保存／比较；真实接收时钟的负例在seq55前实际等待650毫秒，先证明seq54在RAISING，再查半次和提交边界。

## 实际运行与原始证据

下表由[聚合核对](../../reports/rehab_backend/timing_http_clock_verification.json)E001–E004逐帧重算，时间单位秒；原trace／测试原输出／summary的SHA保存，不使用最新目录。

| run ID／证据 | 实际命令参数 | 会话／处理帧 | 最大dt | 结果／退出 |
| --- | --- | --- | --- | --- |
| `timing-http-probe-41d401af`／E001 | 初版探针，无额外延迟，原真实接收时钟正例 | 2／128 | 0.10129190000043309 | 各1 COMPLETE；退出0 |
| `timing-http-probe-eb16b425`／E002 | 初版`--delay-before-seq 55 --delay-s 0.65` | 1／64 | 0.7532320000000254 | 0 COMPLETE＋1 UNASSESSABLE／long_evidence_gap；旧正例断言失败，退出1 |
| `timing-http-probe-c61513b3`／E003 | 当前`--case recorded` | 2／128 | 0.050000000000000266 | 各1 COMPLETE；退出0 |
| `timing-http-probe-e61cf5dd`／E004 | 当前`--case host-gap` | 1／64 | 0.7568056999998589 | 0 COMPLETE＋1 UNASSESSABLE／long_evidence_gap；新断流断言通过，退出0 |

E002保留的是失败而非通过。E003／E004每个会话最终接收／处理／持久边界64／64／64；四个完整诊断run均核对关闭与所属推理／报告句柄释放。旧生产service SHA`61ec22ad6442daf247a1444cbab8378e9df5ae75f4929319bb56e1c8fac7f4c5`、engine SHA`e339dae493dc6bc03edb27a12cb650a568045dce22c13bc64704db0aa4869283`与各run一致。

初次开发探针`timing-http-probe-b550f662`在汇总时访问了不存在的`resources_released`属性，退出1，原trace未写出；没有将其计为完成。之后先保存主证据，资源检查改用实际service释放状态及准确process句柄；重新运行得到上述E001，不覆盖这个空的失败run。

当前两个工具均实际执行`--help`退出0；核对器另将错误计数、时间回退、predicted冒充observed三个本地TEST变异逐一拒绝。这些是核对器自检，不是另外三次HTTP实验，不加入测试总数。

## 专项与完整回归

专项`timing-comparison-audit-8cf7fe7c`：19项，34.561秒，退出0；包含新负例，属于456项子集。日志SHA`34243b2a06e170539ce92feb4f9bc66bdd497a288d92721f56f55584ffd1f1a6`，见[专项摘要](../../reports/rehab_backend/timing_comparison_verification.json)。

完整`verification-dc63e7b4`实际终止退出0：[回归摘要](../../reports/rehab_backend/regression.json)新后端456项／213.798秒，旧康复12／0.087秒，旧手机19／13.12秒，四命令含scope都退出0。新后端原日志SHA`4ab292817286e1fa7ac2e33ca8aee2f476a82f1deddac939d41d72ab711e6c8d`；完整summary SHA`0b54da5c0a243a3bb63d150f132ac3e9213d153156fe360c5bb9c9e19135a065`。各命令的wall-clock包裹时间另存，不拿包裹时间冒充unittest正文时间。

核对器`timing-http-audit-2c92dc6a`退出0，逐证据核对原失败、四trace、当前TEST源码、原生产源码、资源和完整回归原日志SHA；`original_failure_root_cause_proven=false`、`human_verification=pending`、`clinical_accuracy=null`。原455项失败及RGB负结果仍在原验收，不改写为当时通过。

本轮命令在原产品Python3.13.12环境执行，没有安装或升级依赖。既有Starlette／httpx弃用警告保留；不借修测试升级产品。

交付文档静态核对7份、600个本地链接、56张表、66个代码围栏标记，缺失目标／表格列数／未闭围栏错误0；Git差异空白检查通过。这只是文档一致性，不增加业务／人体测试计数。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_timing_comparison.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_timing_http_probe.py --natural timing-http-probe-41d401af --known-gap timing-http-probe-eb16b425 --recorded timing-http-probe-c61513b3 --host-gap timing-http-probe-e61cf5dd --regression verification-dc63e7b4
```

## 保护与交付边界

完整回归scope核对1308个原保护文件变化0，baseline SHA`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`不重建；280份既有用户文件逐文件SHA变化0并排除提交。整个UI、Android、原权重、正常库和非康复业务不改；不启停用户8765／1396／相机，不关闭窗口。只发布当前后端分支，不把main0.23.0／APK0.3.0合入冻结本机。

本机产品仍0.20.0、既有APK0.2.1，v2默认关闭；页面仍首页／康复／健康／用药／家庭。发布后只沿原脚本、实际已验证pythonw及原E盘链接刷新桌面“安康康复（最新版本）”Git说明。

本轮补的是测试前提和诊断可追溯性，不是新的临床计次模型。P5／P6仍缺独立点／visibility／相位／可观察完成参考；自然弱网、手机、LAN／TLS及长时条件未新增。科学写作技能用于保留失败、绑定原始证据和方法／结果一致性，其公开来源及人工核验限制见工作流末节。
