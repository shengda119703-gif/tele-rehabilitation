# RGB 关键点转换与独立评估：本机验收

日期：2026-10-11（Asia/Shanghai）。代码基准`a9e31cce518c0fa2367b1394848c570afcf72307`；本文件与本轮工具同提交交付。任务对应12.1–12.3：缺少真人参考时，先实现转换和评估工具。产品0.20.0、APK0.2.1、v2默认关闭；不是新客户端或微调模型发布。

## 1. 本轮实现与数据边界

- 独立COCO17二维参考模板／核验：权限文件和hash、原图尺寸／EXIF／hash、匿名人／录制／帧／时间、完整人体框、人工标注者与不同复核者、三种按人独立划分。
- masked导出保留null及坐标／objectness两层mask；完整17点才可导出stock YOLO标签与YAML。缺标拒绝，不补为0负例。
- 原YOLO所属spawn进程预测：原manifest／权重、CPU640，原图quality95 JPEG、不缩放、双hash、逐图Context；参考框唯一匹配，无匹配／多候选无有效点。
- 独立评估：帧身份对齐、像素欧氏误差、bbox对角线归一误差、覆盖、PCK_all／PCK_covered、分关节／人／动作／视角／visibility及疑似左右交换。
- 7条CLI真实执行、30项专项及旧路径回归。未训练姿态模型，不自动上线；原权重、正式UI、整个Android、非康复业务、正常患者库不变。

工作流与公式见 [POSE_REFERENCE_WORKFLOW](../development/POSE_REFERENCE_WORKFLOW.md)，全功能数据流见 [后端梳理17.10](../BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md)。工具可核对数据声明与指纹，不能代替法律／伦理审核，也不能证明人工标签本身正确。

## 2. 环境与实际命令

产品解释器`rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe`，Python3.13.12、torch2.9.1+cpu、Ultralytics8.3.199、numpy2.2.6，未安装／升级依赖。原权重SHA256：`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`。

本轮观察到C盘可用空间0，E盘12521111552字节；没有清理用户文件或故意占满物理硬盘。测试TEMP／TMP、数据库和产物均放E盘忽略目录，并禁止写pyc。命令从项目根执行：

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run\process-temp'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_pose_tools.py
```

两条脚本各生成独立新run，未相互复用输出，也没有启动相机／原服务。耗时包括命令启动；不要当正式产品响应延迟。

## 3. 最新完整回归

run：`verification-0bba991b`。原始日志位于`.runtime/rehab_ml/run/verification-0bba991b/`；公开命令、退出码和末尾见 [regression.json](../../reports/rehab_backend/regression.json)。

| 项目 | 实际结果 | 命令耗时 | 日志SHA256 |
| --- | --- | ---: | --- |
| 新后端 | 160项／91.081秒，通过，exit0 | 92.209秒 | `44c0ff9e1d3f768db59024d4c51a775652bf9578e4ab4d964d8d602ad3dfad82` |
| 旧康复 | 12项／0.085秒，通过，exit0 | 0.238秒 | `7baece3da273ec557d1b66b5ca7a390109ed871f135a82d24f2f8249fd687934` |
| 旧手机 | 19项／12.89秒，通过，exit0 | 13.440秒 | `53a9ae385c7679415db406280f87c255361f51735321323bc658dabc30f61b4a` |
| 保护范围 | 1308文件、changes=[]、exit0 | 5.378秒 | `7602c05cf983f3b9641ba4f606de346ab93a2623a849160a67ed52187c84652c` |

30项工具、12项存储和18项报告专测均包含在160项中，不重复累计。旧会话CLI100项为之前交付，本轮没有另重跑；旧训练、真人录像、性能benchmark和全UI／Android／Agent回归没有重跑。旧手机保留1条既有Starlette/httpx弃用warning，未升级依赖以掩盖它。

## 4. 工具实际CLI往返

run：`pose-tools-57a19221`。脚本生成3份64×64 PNG，分别属于TEST-train／TEST-val／TEST-test人物和录制，几何点明确人工构造；权限文档也注明SYNTHETIC夹具。它们不是获许可真人或专业标注。完整命令／源码hash／产物hash／退出结果见 [pose_tools_verification.json](../../reports/rehab_backend/pose_tools_verification.json)。

| 执行 | 实际／预期exit | 命令耗时 | 日志SHA256 |
| --- | --- | ---: | --- |
| unittest test_pose_dataset | 0／0；30项，5.043秒 | 5.212秒 | `9bd5f75850a8c619ecc5cb2a09396adf7f1b330a90576c0b0d6fc5de9f5ce113` |
| masked转换 | 0／0 | 0.169秒 | `0fa5ae1b483e80cb9b338833830c2859f21562c66629d2e80f04284d6e1bcaa6` |
| 完整YOLO转换 | 0／0 | 0.201秒 | `c9d536d8db0f7eab01ae2894b5f0eb03f9573a67192733c13b775d945ba7d8b2` |
| 原YOLO test预测 | 0／0，所属释放确认 | 2.526秒 | `0907357ef08ca01ff483640f71591bd49291d6836426659397bd49cbbdd8bd04` |
| 独立评估 | 0／0 | 0.174秒 | `1650aec1d81d7e4e5f1e0c4ea2d7c03eeb22db1e524ae1eb6fdb22e9590091e9` |
| partial mask导stock格式 | 1／1，预期拒绝且无输出目录 | 0.156秒 | `b38b51c21d21effffa5d01cda1d816b6f15d8686b6aec6dad0d2a8d36218335a` |
| 缺资格train-pose | 1／1，预期拒绝 | 0.151秒 | `f7a7a72c4d8d421b6ab22f443c1345f79f035a13151bb4b3f125d1fb994348de` |

无人TEST图原模型没有人体点：17个构造参考槽、覆盖0、PCK_all=0、像素均误差null、PCK_covered=null；没有把缺失输出写成0误差或“有效正确”。该结果只证明工具缺失处理，不能表示原模型对真人误差很大或很好。

参考清单SHA`b0af468043b66c2dad97844cf3dcb11ee10f5af4efd5f432b09b04dc51c928bc`；原模型预测SHA`edbda784f79403f2c3bc6bbd0f9840785718d319683617e4544abbbe82785653`；评估SHA`7c44f383ed5d83b2b76aa06b3bea61beb6571347d686c5ba89a47ba8719c7479`。逐点原始产物仅在上述忽略run。

### 本机库格式检查（另行运行）

在产品解释器单独调用`ultralytics.data.utils.verify_image_label`，参数为PNG路径、标签路径、空prefix、keypoint=True、num_cls=1、nkpt=17、ndim=3、single_cls=False。实际读取该run train／val／test三份复制图／标签，均返回原路径、图形64×64、keypoints形状1×17×3、corrupt=0、message为空，命令exit0；六个文件前后SHA256完全相同。

第一次shell单行脚本因PowerShell引用转义导致SyntaxError，未调用解析器；改为内存here-string经stdin传入后完成。该独立检查没有另生成持久日志，不纳入30项或160项计数，也没有运行train。YOLO_CONFIG_DIR及临时目录设为E盘、关闭自动安装和联网。

## 5. 覆盖用例与最初失败

30项测试及子断言覆盖：完整／缺标／不可定位mask、原非方形图宽高归一、COCO17翻转、权限文档和图hash、帧时间／录制／人物隔离、独立复核、伪标签拒绝、Windows路径／大小写／保留名、已有输出／正式目录拒绝、错误帧身份、重复／非有限JSON、低conf／出画／缺样本分母、3–4–5几何、PCK双分母、疑似左右交换、候选声明test泄漏、真实CLI及原YOLO无人输出／释放。

最初27项运行出现PNG verify错误：先getexif会加载或关闭decoder，随后verify违反Pillow调用时序；实现改为新句柄立即verify，没有取消图像校验。之后1项出现测试夹具复用污染，改为deepcopy恢复，不放宽产品检查。补非方形归一及录制时间／bbox来源等边界后30项通过。此前工具／完整成功run只作调试历史，发布以上最新同源码run；没有累计失败／旧成功计数。

本机Ultralytics8.3.199`utils/loss.py`实际第643–647行：坐标loss用visibility非零遮罩，objectness BCE仍覆盖全部点，文件SHA`c09d05d83a514c8f7e7bd69dc489b68a8d3371745ad114d615339ced6992d7e0`。因此工具拒绝部分标注stock导出；这是对本机锁定实现的核对，不假定所有版本损失相同。

## 6. 保护与剩余工作

保护基准SHA`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`，1308文件一致。另按本轮开始清单核对280份既有用户图片／README／CSV／任务书／导入脚本，数量和SHA未变化；这些不提交。没有重建保护基准，没有覆盖旧模型、下载来源或患者库。

仍未完成：同域真人权限／专业参考、部分骨架masked训练器、真实姿态微调、候选同集误差对照、标定动捕投影、MediaPipe目标域实验、康复深蹲宿主计划、真实物理存储／全负载／手机长期验证。IoU参考辅助匹配不能证明无参考自动跟踪；逐图Context不是连续视频；缺标mask检查不能证明专业标注准确，声明划分不能排除第三方预训练重叠。没有临床ROM／计次／疾病准确率或新手机FPS结论。

本轮提交后仅刷新桌面“安康康复（最新版本）”Git描述，继续使用Start-Rehab.ps1与本机已验证pythonw.exe；首页／康复／健康／用药／家庭不变，不关闭用户旧窗口。总实施目标保持进行中。
