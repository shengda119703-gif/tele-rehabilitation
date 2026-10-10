# 部分关节标注的双层 masked pose loss

任务书12.2要求未标注点不能成为负例；不仅坐标损失，关键点置信监督也必须屏蔽。本增量实现隔离、版本化损失实例与原YOLO实际工程烟测，不修改安装库、产品模型、UI、APK或数据库。真人微调仍缺适用RGB授权、独立标注和同集误差基线，`train-pose`继续拒绝；本工具不是完整的增广／多轮选模训练器。

## 1. 信息链与原实现的连接

```text
独立参考清单、权限文件、原图hash与先按人划分的split
  → load_reference(training=True) 核对17点、原尺寸、bbox、人工visibility和annotation_mask
  → training_batch：只把train图像变为张量，实际整数resize＋letterbox同时变换bbox／点
  → 原YOLO forward／原TaskAlignedAssigner：每图GT ordinal
  → assigned_targets：ordinal → 同一原对象的点和annotation_mask
  → 双层masked坐标／objectness；原bbox／类别／DFL损失与gain保持
  → 工程梯度审计 → 一步SGD／新TEST检查点 → 严格重载／固定输入输出核对
```

代码：[损失](../../tools/rehab_ml/pose_masked_loss.py)、[批次与所属进程烟测](../../tools/rehab_ml/pose_masked_smoke.py)。原库8.3.199及LF规范化`utils/loss.py` SHA256固定为`c09d05d83a514c8f7e7bd69dc489b68a8d3371745ad114d615339ced6992d7e0`，不只核对版本字符串。原库的关键点BCE没有独立annotation mask，见 [该固定版本源码](https://github.com/ultralytics/ultralytics/blob/v8.3.199/ultralytics/utils/loss.py)；标准完整标签格式见 [官方格式](https://docs.ultralytics.com/datasets/pose/)。新实例继承原检测／分配通路，不做全局monkey patch，不将缺标导出为stock训练负例。

## 2. 两种mask、两个分母

对已分配的前景anchor a、关节j：m_aj是独立annotation_mask，v_aj是人工0／1／2，c_aj=m_aj·[v_aj>0]。0表示经复核无法定位，1是可靠参考已定位但图像不可见，2是可见；不是模型confidence。

```text
d_aj² = (x̂_aj − x_aj)² + (ŷ_aj − y_aj)²
e_aj = d_aj² / [ 2 · (2σ_j)² · (area_a + 10⁻⁹) ]
A_xy = { a : Σ_j c_aj > 0 }
L_xy = mean_a∈A_xy [ Σ_j c_aj · (1 − exp(−e_aj)) / Σ_j c_aj ]
L_obj = Σ_aj m_aj · BCEWithLogits(z_aj, [v_aj>0]) / Σ_aj m_aj
```

坐标沿用原COCO OKS sigma与原分配框的stride坐标面积；原点和框一起变换，不混用归一x／y作欧氏几何。没有对应标签时该项是连着计算图的0，梯度也是0。整个anchor没有坐标时不加入坐标均值；未标点不加入objectness分母，不能通过新增unknown点稀释已标监督。此归一规则单独版本化为`rehab-coco17-dual-masked-loss-1`，不是承诺所有稀疏情形与stock权重一样。

| 参考含义 | 坐标监督 | objectness监督 |
| --- | --- | --- |
| 未标注／unknown | 无 | 无 |
| 已复核无法定位（v=0） | 无 | 已审查的不存在负例 |
| 已可靠定位但不可见（v=1） | 有 | 存在正例 |
| 已定位且可见（v=2） | 有 | 存在正例 |

输出槽的零梯度不表示共享骨干、BatchNorm或所有参数都不更新：其他已标点和人体框仍有监督。完整有效标注的测试同时核对原bbox／类别／DFL／坐标／objectness五项结果；空人物目标和全unknown点分别测试，不能用关闭整个人体检测来实现mask。

## 3. 范围、容量和取消

criterion批次≤8图、每轴64–640且32整除、总人体对象≤64；规范浮点RGB在[0,1]，目标单类person、17×3，mask必须bool，v必须整数编码；未标点在张量中仅用0占位并携带false，不是有效观测。训练批次工具当前每清单train图1–4张、每图一位已独立标注参与者；只用于小批次工具验证，尚无迭代DataLoader／缓存／随机增广／多卡支持。

每次损失调用独占实例，失败清除该次mask并释放锁；并发同实例拒绝，下一批不沿用上一批标签。TAL映射按每图原GT顺序，不以全batch ordinal取另一个人的标签；背景dummy index不参与gather，前景越界拒绝。

`smoke-pose-masked`只接受所有来源为synthetic_fixture的TEST清单及明确training权限；真人／RESEARCH拒绝，不借工程命令绕开12.1。只读取现有产品解释器和可信原权重，权重SHA`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`。CPU2线程，默认128图、seed20261011、SGD一步lr1e-5、无momentum／weight_decay、clip10；五项gain记录在实际结果。

所属隐藏子进程默认等待120秒，可受控5–300秒；取消／超时只terminate该句柄，等2秒，必要时kill再等2秒。释放未确认不声称成功。Popen创建、文件hash及JSON序列化本身未有独立OS硬截止；受控Popen测试不等于真实卡死进程验收。超时后不会自动启用检查点。所有checkpoint都明确TEST、product_enabled=false，不是可直接换进产品的YOLO包。

## 4. 已实际运行的复现入口

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_pose_masked_loss.py
```

脚本在E盘忽略run目录生成TEST参考，实际运行23项专项、原YOLO前向／双层masked反向／一步更新／保存／重载，以及无training权限非零拒绝。CLI为`smoke-pose-masked --reference <TEST清单> --output-dir <全新忽略目录>`，输入输出例见 [本机验收](../validation/REHAB_POSE_MASKED_LOSS_2026-10-11.md)。

公共聚合证据：[pose_masked_loss_verification.json](../../reports/rehab_backend/pose_masked_loss_verification.json)。原TEST图像、坐标、检查点、失败日志保留在忽略目录。Ultralytics和原权重继续沿原manifest的AGPL-3.0／独立Enterprise路线，未声称取得企业许可。没有下载、安装或升级依赖；不代表临床能力、手机性能或正式微调收益。
