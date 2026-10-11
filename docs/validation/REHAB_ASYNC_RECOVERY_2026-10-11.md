# 异步结束三窗口：本机进程退出验证

日期：2026-10-11；实施基准`a9156c7622071bbf32db2551678481bc831775fc`。生产来源`04ab1ea`保持。新文件为隔离审计、专项核验器、4项测试及工程报告／必要文档；不修改生产源码、原权重、前端、整个Android或正常用户数据。

## 1. 最终专项

产品解释器`rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe`运行`-X utf8 -B tools/rehab_ml/verify_async_recovery.py`，实际退出0。工具运行前登记3轮，不遇到失败再无限追加直到成功。专项`async-recovery-verification-f00e75d2`包含4项unittest及3轮审计；命令时间为16.459／16.843／16.812／16.006秒。这是工程命令耗时，不是动作或HTTP延迟。

| 轮次 | 三窗口 | 每窗口条件 | 实际宿主退出码 | 原始summary SHA256 |
| --- | --- | --- | --- | --- |
| `async-recovery-a50b48ce` | 全通过 | 32 | 1／1／1 | `5221176acfd48dc1c55bfb9db779978ba84901ec811548cb8144b0fc2c40cb31` |
| `async-recovery-18ea068c` | 全通过 | 32 | 1／1／1 | `cd0d41ebe913f6e28672bfe996b5629c6e8bd759e9b65febd098e648e58c04bc` |
| `async-recovery-eb570147` | 全通过 | 32 | 1／1／1 | `863c10583cce7ce647405a6316ef275383022e633eee844a0f17ff828ac45133` |

[公开汇总](../../reports/rehab_backend/async_recovery_verification.json)列实际参数、日志路径／SHA、10份源码hash、3轮全部检查与每窗口details／SHA；核验器实际读取原始summary、log与details核对范围和hash，源码前后不变。原始逐次、SQL和TEST身份仅留本机忽略目录，没有加入原用户历史。

## 2. 结果怎样解读

- 前两个窗口：独立读取仍只见draft／finishing与0贡献；未提交写入不算最终保存。新生命周期恢复成interrupted，保留原确认次，半次UNASSESSABLE。
- 已提交未回应窗口：独立读取确见finalized、canonical与1贡献；恢复保留原user_stopped事实，原回执不变。
- 三窗口都只有1贡献，原／别名重试同回执；异载荷409、别的owner404；空感受保留null，反馈独立1行；二次重开不改库。

每用例输入是1确认次＋1半次的内部TEST几何和1条内部accepted未处理证据。它不是真人或原生在途推理，不具正式计划完成资格。实际强制退出的是所持宿主句柄；恢复在父监督程序的新Storage／Service生命周期内。没有socket服务器、手机或临床准确率。

## 3. 开发失败保留

| 原run | 实际失败 | 处理与边界 |
| --- | --- | --- |
| `async-recovery-fd6715e3`、`async-recovery-d7aed8c2` | 内部回放宿主拒绝公开JPEG，HTTP400，未到退出屏障 | 原生产输入校验保持；改为明确内部accepted证据夹具，不冒充真实相机或放宽公开接口 |
| `async-recovery-aeff4a5f` | Windowsvenv启动器PID与实际解释器PID不同，父程序拒绝当作准确所持句柄 | 本轮旧3个解释器在TEST超时后自然退出；只读确认已不存在，未按旧PID杀进程。改为本机CPython同样的base解释器＋venv初始化；最终屏障PID匹配 |
| `async-recovery-927f0933` | 原始summary显示3窗口通过，但过大控制台输出被外层工具截断，父命令退出码未保留 | 不作为最终CLI验收；原始输出仍保留。正式CLI打印紧凑结果，专项重新保存每命令日志和实际退出码 |

以上失败不能删掉或改成通过。启动器失败时子日志会在原父退出后继续更新，早先捕获的log hash不能当成当前文件hash；仅最终专项的稳定日志hash纳入成功核验。

## 4. 范围与未完成项

同产品解释器运行`-X utf8 -B tools/rehab_ml/verify_all.py`，完整`verification-62f925a1`实际退出0：376项新后端／12项旧康复／19项旧手机接口通过；1308保护一致，原baseline SHA256仍为`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`，不重建。[实际回归](../../reports/rehab_backend/regression.json)保留4命令、日志与SHA；新后端命令212.700秒，unittest本身209.589秒。旧手机保留1条Starlette／httpx弃用warning，不为工程审计升级依赖。

4项专项是376的子集；3轮实际工程重复另列，不相加，也不借用此前372项作本次结果。发布前核对开工280份用户文件hash与未暂存状态，检查必要文档的链接、表格、围栏和Git范围；只提交本轮工具／测试／工程摘要／必要文档，不含任务书、动作图片或私人数据。

未测活跃原生pose／report子进程时的宿主崩溃、物理断电／磁盘满、网络、目标手机、长时或多客户端。目标域专业标签／合法RGB监督缺口仍在，P5／P6／完整P7未完成；产品0.20.0、既有APK0.2.1、默认关闭v2和五页导航保持。

发布静态核对：7份必要文档540个本地链接存在、49个表格列数及围栏匹配，`git diff --check`通过；4份完整回归日志、4份专项命令日志、3份原始summary、18份窗口log／details和10份源码hash匹配。280份开工用户文件的状态／SHA变化0，原任务书仍为用户未提交文件。本轮仅13份工具／测试／摘要／必要文档；推送后核对origin/main和本地提交一致，沿用原已验证pythonw.exe与快捷方式脚本，不启动产品或关闭旧窗口。
