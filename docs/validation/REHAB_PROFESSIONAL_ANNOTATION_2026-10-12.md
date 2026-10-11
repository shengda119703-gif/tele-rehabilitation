# 独立专业标注链：本机工程验收

日期：2026-10-12。实施起点`3a51edbfb7dcf466d3d92ccfb1b0e7e0c2bbb810`，分支`codex/backend-information-map`。对应任务书10.4–10.6／13／P5；只改离线康复工具、测试和必要文档。产品0.20.0、已有APK0.2.1、v2默认关闭；不改正式模型、算法、前端、整个Android或正常患者库，不启停用户服务和摄像头。

## 实际新增与运行

- `professional_annotations.py`生成独立JSONL、规范与模板、真实媒体PTS；校验逐任务／边界mask、来源／组划分、双人独立声明、第三人专业复核、分歧及输入digest。没有独立标注不导入；审核部分可导入但完整队列、待标／排除与分母保留。不存在自动补真值或模型上线。
- CLI新增prepare-annotations／validate-annotations／import-annotations；全部--help退出0，失败非零，明确新输出路径，不覆盖已有包。v1模板保留，v2为独立标签版本。
- 真实授权队列仍为MobiPhysio3.0／CC0，E01正面全光照24人24段，680355016字节、固定14／5／5人。复用原发布版／README／CSV／清单、原下载回执与源文件MD5／SHA核对，不下载或复制原录像，不改原视频EAAQ研究计划。
- 新包24份A、24份B和24份REVIEW记录，以及24张真实PTS表；患侧和动作标签均未自动填写。当前pending=24、approved=0、known_labels=0，reference_generated=false。时间表来源是原文件packets／显式stream start_time，不用标称FPS、预测或推理耗时。

最终专项run：`professional-annotation-audit-3581f13f`。[可公开聚合证据](../../reports/rehab_backend/professional_annotation_verification.json)引用原日志／源／包hash。私有包位于`.runtime/rehab_ml/run/professional-annotation-audit-3581f13f/cohort/`，不上传。summary SHA256为`ebb1e831bdaf2b8cc8d304f999dc730b05605b255a01ab767eb8cc8649f25318`；bundle SHA256为`bb3a57bdd0717bb971309005c7b360b5f2f58c1e6a3d1b5e07acc419c8c8df45`。该run全部产物约2487925字节，未包含680MB原视频副本。

## 验收与负例

| 检查 | 实际结果 | 范围 |
| --- | --- | --- |
| 专业标注TEST契约 | 34项、0.315秒、退出0 | 三动作字段契约、缺标／相位、独立复核、分歧、部分导入、明确零次；不是34名真人 |
| 真实队列prepare／validate | 退出0；24人／0标签 | 真实源与时间、空表资格，不是临床标注完成 |
| 空表import | 退出1；blocked_missing_independent_professional_supervision | 输出目录未创建，未生成reference |
| TEST评分预填 | 退出1；annotation_record_schema_or_identity | 原样本包不改，仅新建TEST副本 |
| TEST人群划分改写并重算摘要 | 退出1；bundle_source_or_split_changed | 原14／5／5仍冻结 |
| TEST时间表改写并重算hash／摘要 | 退出1；timeline_does_not_match_verified_original | 重新从校验原片读取媒体时间，不能信自声明hash |
| 禁改范围专项 | 退出0；原1308项变化0 | 基准SHA仍75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742，未重建 |

最终run四份实现／测试文件的前后SHA一致；所有命令原日志及SHA另存该run。之前27项／31项／33项分别在`professional-annotation-audit-3f6aecb2`、`bd976644`、`22da7f8c`保留；均通过，不将各轮计数相加。最终模板在媒体时间读取前生成，真实录像仍空标注。另用隔离TEST检验已完整审查且明确count=0／mask=true的参考能导入，未标空表、含unknown的清单和数量不一致仍拒绝；单帧同一时间不能标成完整生命周期。

## 复现命令与填写入口

### 全量回归与实际存储限制

最终源码上的`verification-e8c8c33f`：490项新后端有4个空间预检错误；原康复12项通过；旧手机19项中7项因507空间不足失败；保护1308项通过。[原完整记录](../../reports/rehab_backend/regression.json)保留，不能称490／12／19全部通过。四个错误均在`pose_training.py`的实际512MiB加预估输出空间门触发，七个旧接口失败均在Jobs的真实存储空间门触发，没有修改这些生产文件。核对时E盘剩443142144字节；C盘约79998976字节，不清理用户数据或放宽门槛。

随后只将隔离TEST临时路径设到实际有16105250816字节空闲的D盘，运行整份姿态训练工程模块30项和旧手机接口19项，全部通过；1308保护也通过。此为不同真实磁盘的受影响子集重验，不是新一轮完整490项验收，不把多轮／重复项相加。[D盘重验证据](../../reports/rehab_backend/storage_recheck_verification.json)引用`D:/RehabBackendVerification/annotation-storage-20261012-ec47f951/summary.json`，SHA为`f3fc06590302f0c16fc23c59ede25ec498b050995ebae8a707092f5e1c48f524`。实际空间、原失败summary／日志hash和未改门槛均保存；原E盘失败证据未变，不迁移源数据、数据库或清理任何文件。

此前`verification-b9cf81b2`487／12／19全部通过，是补明确零次与单帧边界之前的记录；不能代替最终版本完整验收。34项标注专项是最终490项的子集，不额外累加。旧Starlette／httpx警告保留，不升级产品依赖。默认E盘的录像上传仍可能返回507，需恢复实际容量后才能验收默认存储环境。

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_professional_annotations.py --receipt '.runtime\rehab_ml\data\mobiphysio\3.0\rgb-e01-front-fl-9ac33275\download-a157e0e1.json'
```

复核者使用[标注规范](../development/REHAB_PROFESSIONAL_ANNOTATION.md)，在已生成包的A／B／REVIEW表中填写，不覆盖源、split或时间表。验证／导入时使用该bundle的明确完整路径与新的输出目录。重复运行验收会另建包，不影响已经填写的表。

`verify_storage_recheck.py --failed-summary <明确原失败summary> --output-dir <新的外盘TEST目录>`支持--help，真实空闲须至少1GiB，失败非零。只重验空间受阻子集，原完整回归的passed=false保留；输出目录不覆写，不能指向盘根、仓库或已有目录。本次实际命令使用上文原失败路径与D盘目录，已使用的目录不能再次作为新输出。

## 未完成范围

发布前另核对7份本次维护文档的633个本地链接，缺失0，`git diff --check`通过；18份专项／存储／完整回归日志及两个summary指纹一致，四份标注实现／测试SHA未变。`verify_storage_recheck.py --help`实际退出0。原280份用户素材／CSV／任务书／脚本hash全部一致，原1308保护再次变化0，baseline未重建。同步阅读版第16.14节，但没有因文档更新追加训练或重新分析私人录像。

独立2D／visibility、相位／完成／质量真实标注仍缺；这里只完成可填写、校验、复核和导入工具，不宣称专业真值、姿态微调、准确性提高或客户端接通。人员独立性及专业资格需要实际人工组织，字符串声明不是资格证书。当前仅同视频可见物理参考；外部同步参考与干预回执需另行资格适配，不能靠自行写路径接入。尚未得到坐站／康复深蹲的相符授权录像，也未验证手机、LAN／TLS、自然弱网、长时及全部物理故障。
