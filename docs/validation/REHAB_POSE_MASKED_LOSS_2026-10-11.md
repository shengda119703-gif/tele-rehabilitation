# 双层 masked pose loss：2026-10-11 本机验收

最初实施基准`d0b21d240422e1788b73e072d365f9072436ea4b`；交付前复验基准`ab47ee0f7478c948ab77310f66c0e7000fa86108`，中间文档提交不改变本次五份实现文件。本轮补任务书12.2的坐标＋关键点objectness未标注屏蔽，以及原YOLO实际前向、反向、一步工程更新与重载。不是真人微调、准确率提升或客户端发布；完整任务仍未完成。

## 1. 实际命令和运行

仓库根目录，产品`.venv/Scripts/python.exe`；TEMP／TMP设为E盘`.runtime/rehab_ml/run/process-temp`、PYTHONDONTWRITEBYTECODE=1。无安装／升级／相机／原服务操作。

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_pose_masked_loss.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
```

专项末次run`pose-masked-audit-d8188b3a`：23项单测0.592秒／外层2.616秒，所属原YOLO工程步骤1.472秒，包裹CLI4.083秒；三条实际命令退出分别0／0／1，拒绝命令预期1。公共 [摘要](../../reports/rehab_backend/pose_masked_loss_verification.json)含真实命令、源码hash、原生结果、检查点hash与各日志hash。TEST参考为三个分人split、每份一张96×64灰色空图及明确合成独立标签，仅train图参与优化；不存在真人准确率参考。

完整末次run`verification-9d1cdb62`：200项新后端90.279秒／外层92.950秒，12项旧康复0.087秒／外层0.236秒，19项手机12.87秒／外层13.404秒，1308保护文件变化为空；四条退出均0。23项是200项子集，不与上次177、17、30、12、18等计数相加。现有Starlette/httpx warning保留，不升级依赖。

此前成功run`pose-masked-audit-91fab841`与`verification-999f96ea`保留在各自忽略目录，不替代此次复验、不累计测试数。两次专项的源码hash及确定性梯度／损失／更新参数digest／检查点hash一致；耗时和日志hash各自独立记录。

| 完整回归日志 | SHA256 |
| --- | --- |
| new_backend.txt | `efec0b75e9db53a2ba64945a3f5751cc1613a597b7dcc520a14db59b26d30ab9` |
| legacy_rehab.txt | `271fe9a3b08696b5e6a4ac15168b69acd1de7ed093a803cf803873c2d3268a00` |
| legacy_mobile.txt | `808379affbd78fc54899d5791aab112877280e225075056d2a90f1adff253e32` |
| scope.txt | `9e94a3176412f7d8c87b64ec995dabdda5f2e4ac801c4c292eb5590c4dde52a1` |

实际烟测CLI输入`.runtime/rehab_ml/run/pose-masked-audit-d8188b3a/reference.json`，输出该目录下`native-smoke`。这是脚本实际生成的TEST资料，不能在产品中当患者记录。独立参考及检查点SHA在公共摘要，原图／坐标／二进制只存忽略目录。

## 2. 具体证明了什么

| 项目 | 证据 |
| --- | --- |
| 锁定库／损失 | Ultralytics8.3.199；LF规范化loss.py SHA`c09d05d83a514c8f7e7bd69dc489b68a8d3371745ad114d615339ced6992d7e0`，改源文件hash会拒绝 |
| 原权重 | 实际加载原yolo11n-pose.pt，前后SHA`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`不变；不下载／覆盖 |
| 原生分配 | 原模型训练forward＋原TaskAlignedAssigner实际取得10前景anchor，不使用伪造assigner来声称端到端通过 |
| 标签范围 | 1 train对象，每对象15个可定位点、1已复核无法定位点、1未标点；共150坐标槽／160objectness槽 |
| 未标输出梯度 | 新损失unknown点xyz／logit梯度max=0；原stock对照unknown objectness梯度L1=0.02916156 |
| 已复核不可定位 | 坐标梯度max=0，objectness梯度L1=0.02769500；不是关闭整个pose head |
| 已标定位点 | 输出梯度L1=3.32911658；visibility1／2都保留可靠坐标正例语义 |
| bbox／类别／DFL | 原通路和gain保留；完整标注五项损失与stock匹配；全unknown点仍有人体框／检测监督 |
| 更新／重载 | SGD1步、lr1e-5、无momentum／weight_decay、clip10；参数digest前后不同；新TEST检查点严格重载，固定输入最大输出差0 |
| 权限与隔离 | 缺training权限在创建输出／子进程前拒绝；非TEST烟测拒绝；仅train入张量，val／test不用于优化 |
| 身份和数值 | 同batch多对象／不同图GT ordinal与mask对应；背景dummy不gather；越界／浮点visibility／非有限值／非法尺寸拒绝 |
| mask生命周期 | 失败清空、下一批不沿用；并发同实例拒绝；零标签为连图0损失／0梯度；unknown不稀释分母 |
| 取消 | 受控Popen的timeout／KeyboardInterrupt／释放未确认分别保留失败状态；只操作准确所属句柄，不用进程名广泛结束 |

损失五项为`[3.00307059, 11.00246620, 1.26409149, 3.86194730, 2.20253801]`，顺序box／pose／kobj／cls／dfl；这些只是TEST训练目标函数，不是动作评分或准确率。clip前梯度norm10145.783，只作为可追查数值记录，不用它证明泛化。输出零梯度不代表共享骨干、BatchNorm或所有参数不变化。

专项日志SHA：unit`d27ce7f826dd339eaa5c67e2af72d72a806d4ba33ee29a1956b2b745594f85e0`，native_smoke`b38fdf255de724901399d8b7de04591f779fb9f7b69d14611d963c731eb9b46b`，权限拒绝`8929aeaa27f0bd92125f5cb2c0772d87a9744adf08979fc92486953033348b0e`。最终检查点SHA`b6eebae2eef01c8529368232d41d511169055b66955061f57abbe8a3908c72ea`；该包fixture_only=true、product_enabled=false，不可当正式模型更新。

## 3. 失败、修复与未测边界

最初两个实际run`pose-masked-audit-177654bb`／`96468dd8`原生梯度检查失败，保留原日志／失败JSON，未算通过。原因是retain_grad也收到了stock对照的autograd.grad结果，新损失测量缓冲混入原梯度；明确清空该输出缓冲后再独立反向，并补测试证明原负例梯度与新零梯度。没有降低容差或删除未知点。

第一run还发现YOLO_CONFIG_DIR父目录不存在，库将新settings写到仓库根Ultralytics。先确认目录只有此次生成settings.json，再将该文件移到第一次失败run的unexpected-settings.json，空目录移除；文件可恢复，未改用户设置。修复为先创建忽略输出内专属config目录，后续原生日志确认该位置。

取消测试是受控Popen，不是实际原生死锁／OS创建硬截止验证；原生正常退出是实际进程。当前CPU单图128、2线程、SGD一步，非多轮训练／CUDA／AMP／DDP／压力／手机验收。没有新的合法真人RGB标注、动捕标定投影、完整增广训练器、独立姿态精度比较或候选上线。

本轮不重跑IRDS正式训练、两段真人VIDEO对照、会话CLI或性能benchmark；它们各有历史run。UI、整个Android、原模型、正常数据库与非康复业务保持，v2默认关闭。280份用户动作素材／说明／CSV／任务书／导入脚本另外核对并保留，不提交。深蹲本人正式计划契约、专业参考与目标手机实测仍缺，整个目标继续进行。

## 4. 交付前核对

在末次运行后逐一重算五份实现源码、七份实际命令日志及五份产物的SHA256，共17项，与公共报告一致；不是只读取报告的passed标志。23项日志末尾确认为OK，完整回归四条实际命令均退出0。八份本轮Markdown的378个本地链接目标存在，代码围栏配对；五份Python经AST解析，`git diff --check`无错误。280份用户未提交文件与开工指纹逐一相同、无新增或消失，保留在工作区不提交。

本机C盘剩余0字节，E盘约12.46 GB；此次所有测试临时输出使用E盘忽略目录，未安装依赖或清理用户磁盘。该环境风险未因本次回归通过而消失。只提交本轮16份实现／测试／文档／聚合报告；不提交TEST图、独立标签坐标、权重、环境或私人数据。
