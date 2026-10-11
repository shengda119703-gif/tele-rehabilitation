# 2026-10-11 离线姿态续训与数值一致性验收

实施基准`710957312c4210f45229bd798ae8146fc04bf540`；本文件所在源码交付提交为最终版本。本机Windows11、AMD Ryzen7 7745HX、原Python3.13.12／Torch2.9.1+cpu／Ultralytics8.3.199；不安装依赖，不重启用户服务，不改UI、整个Android、原权重或正常库。工作流和公式见 [续训与数值契约](../development/POSE_RESUME_WORKFLOW.md)。

## 1. 末次原生恢复证据

| 案例 | run／配置 | 完成事实 |
| --- | --- | --- |
| 基础 | `pose-resume-audit-46708662`；128像素、threads2、batch2、1张train图 | 3epoch／3步；从epoch1恢复后本次2步 |
| 多批次 | `pose-resume-audit-74c04c41`；160像素、threads4、batch2、5张train图 | 3epoch／9步；每轮3步且末批1张；恢复后本次6步 |

两者均使用原YOLO架构、真实前向／双层masked loss／backward／优化器步骤，不用假模型替代。每个案例60项单元检查及7条真实命令按预期退出；总判定`passed=true`。专项单元是完整回归的子集，两次运行不能累计为120项不同测试。

1. 不中断完成3epoch。
2. 实际epoch1完成val并提交边界后请求取消，真实子进程退出1；无test-started。
3. 新run恢复模型、优化器、全部RNG、best／patience及历史，源文件保持不变。
4. 从已完成test实验恢复，预期退出1且不创建输出。
5. epoch2第一个实际CPU AdamW更新之后`os._exit(27)`：基础总步2、多批次总步4；生产父进程真实持有所属句柄并记录非零退出／日志／源码回执。
6. 异常源仍显示training，但有正确所属回执和此前epoch1 manifest，恢复到新run；未完成epoch2重新执行。
7. 两种恢复的最终模型、优化器、参数组digest与不中断版本逐位一致；新尝试的样本／增广／loss、剪裁前后gradient digest及范数完全一致。

两个案例的模型及优化器变化张量数均0、最大绝对差均0；差异统计不是容差判定。原权重仍为`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`。公开无身份摘要：[基础](../../reports/rehab_backend/pose_resume_verification.json)、[多批次](../../reports/rehab_backend/pose_resume_verification_multibatch.json)；各条实际命令、退出码、日志SHA与实现SHA在摘要内，私有详细产物在对应忽略run中。

## 2. 原多轮训练复验

`pose-training-audit-f41930bc`总判定true，30项及5条真实检查按预期：两轮两步、max4/patience1在第2轮早停且best1、缺training权限拒绝、真实活子进程val阶段观察／取消／退出确认。取消后last保留、result不存在；取消请求响应本身仍`exit_confirmed=false`，真正退出另由准确所属句柄确认。见 [新摘要](../../reports/rehab_backend/pose_training_verification.json)。

## 3. 失败没有改判为成功

| 阶段 | 实际发现／处理 |
| --- | --- |
| 原续训检查`3e1472ca`及单线程定位`05bd8d9c` | 最终模型一致，但9个优化器张量有差异；单线程不解决。后者是临时调用定位，不作为发布命令退出证据 |
| MKL定位`121daac2`／`ff21380a` | AUTO,STRICT及COMPATIBLE均未解决；未把环境开关当可靠性保证 |
| 原生层级追踪`25911bec`／`e9b485e9` | epoch2同输入、同全部前向／层输出反向梯度，但3个卷积权重梯度不同 |
| double卷积梯度`da352999`／显式组与clone`e34d5196` | 梯度顺序已一致，仍有2个动量张量微差；总判定false |
| 第一版显式CPU优化器`84d9bca6` | 单批通过，后续5图／3批次`13cf03d4`不通过；没有只保留单批通过结果 |
| double优化器中间量`f964b186` | 多批次最终模型／优化器一致，但step5梯度digest不同，严格总判定仍false |
| 层级追踪`d554491a` | 激活后两处wrapper输出微差，随后一层梯度最大差约1.46×10⁻¹¹，不是±0差异；补训练SiLU double中间策略后复验 |
| 取消回归`pose-training-audit-a1114413` | Windows读状态时原子替换偶发WinError5，子进程正确failed；没有记录成功取消。补有界重试后实际新run复验通过 |

中间通过`9c5f1359`／`0fa3ca86`也不是最终证据：后续补原子写恢复并绑定common后，最终重新跑上面的`46708662`／`74c04c41`／`f41930bc`。不舍入检查点、不删失败样本、不放宽逐位门槛，不把默认Torch／旧算法／跨硬件称为本次数值策略。

最后数值策略为SiLU double中间、卷积权重double固定样本顺序累加、CPU AdamW double中间而float32状态；不是全double模型。CPU原生训练关闭mkldnn／autograd多线程，配置2／4线程，实际继承`OMP_NUM_THREADS=1`，其他MKL字段null，CUBLAS字段`:4096:8`；完整字段随结果／模型卡／检查点保存。只证明上述本机实验，非全部线程／batch／分辨率或CPU／CUDA。

为E盘空间预算，清理了本轮69份旧TEST诊断／失败检查点，共2,614,976,030字节；仅精确白名单文件，非递归清根。旧失败报告、日志、比对和两份梯度证据保留，最终验收检查点保留。清理清单／原SHA在`.runtime/rehab_ml/run/pose-resume-diagnostic-code/cleanup-*.json`；删除文件不能直接恢复，可重做相应工程实验，不称旧文件现在仍可核验。桌面入口所在E盘目录和所有用户文件未清理。

## 4. 原子写及保护回归

`common.write_json`只对WinError5/32/33 PermissionError进行最多4次原子替换尝试，等待10/20/40ms；总sleep预算70ms，非OS硬截止。持久权限／其他I/O／非有限JSON仍失败，旧目标保持，清理准确所属part，不降级成原地写入。新增4项注入测试不冒充物理磁盘满或断电验收；真实取消复验另列于第2节。

最终`verification-3cd67228`实际303项后端／12项旧康复／19项旧手机接口退出0，原1308文件变化0：[回归摘要](../../reports/rehab_backend/regression.json)、[保护核验](../../reports/rehab_backend/scope_verification.json)。旧历史计数不累计，Starlette/httpx旧warning未通过升级依赖消除；不是全UI／Android／照护或真人准确性回归。开工280份用户素材、任务书、CSV和导入脚本独立只读hash比较变化0，不捎带提交；原1308基准不重建。交付核对4份最终摘要均通过，29次源码检查及23份命令日志hash与现存文件一致，8份当前文档385个本地链接及围栏检查通过。

## 5. 仍未完成

TEST灰图／色块没有真人。候选PCK、覆盖0且误差null，仅证明损失、实际更新／恢复及文件／进程工程流程；真人训练为false、clinical_accuracy为null、product_enabled／deployment_eligible仍false。

合格同域RGB／明确训练权限／独立2D与visibility／专业动作参考、同集真人候选对照仍缺。手机／CUDA、全部参数与硬件、完整负载、物理存储故障、康复深蹲宿主计划以及旧客户端正式接线也未完成，整体后端任务保持进行中。桌面主线0.20.0、APK0.2.1与原导航不变；提交后只刷新已有桌面快捷方式版本描述，不打开／关闭用户窗口。
