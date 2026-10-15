# 官方发布数据与评分索引：2026-10-11本机核验

实施基准`98e15e63b9868253e491f3d6cee0dc8f2e4664db`，分支`codex/backend-information-map`。任务书数据阶段的离线增量；不是0.21合并、产品发布或真人准确率验收。原产品0.20.0、既有APK0.2.1、v2默认关闭，五页和原模型保持。方法／接口／公式见[工作流](../development/REHAB_DATAVERSE_METADATA.md)，公开可对账原值见[聚合JSON](../../reports/rehab_backend/dataverse_metadata.json)。

## 实际网络与文件

MobiPhysio本机`dataverse-mobiphysio-13110f5c`先读取根，再`:latest-published`，最后数字3.0；三个官方GET成功，数字版本／条款／文件一致。3688条目、158714197650字节为远端清单；3686视频、README和CSV，没有下载158GB。CC0 URI、13项空自定义条款、明确restricted=false和无embargo均来自发布快照。root未报告guestbook，不能声称已证明guestbook为0；小文件官方GET实际成功，未提交POST或凭据。

| 实际产物 | 字节或结果 | SHA256 |
| --- | --- | --- |
| 发布版原始快照response-03.json | 2155170原响应字节；快照格式化保存 | `f872020a79e2ff58aedbeb22f915f4ad8ac655bc5865ea23845fd0e5798c393f` |
| 规范化发布清单 | 3688文件 | `4a549d1d2ff44a24aadb6a61eb0d00a9ba0239bf51ba429e152bfa9aae8d41d8` |
| 元数据summary.json | 数字版3.0固定 | `be09b80e4a5313a66850d6d84f847f688c283487de7519e8ae04bc039ef3e91d` |
| MobiPhysio.md，ID13453294 | 12668字节 | `80784a069d47088df73c105c6eda95b99052183b13d7d9c34bf08717090b5412` |
| Physiotherapist Exercise Marking .csv，ID13453292 | 539076字节 | `f6e97b3f7ab3771cba19536f3b27c867b73b2084b4e8542414d9882a5430f3ed` |
| metadata-6ee01ba1/manifest.json | 下载551744字节，MD5及SHA通过 | `cf4ad297df79c6a8932a9017145d9cb7a46a7f0aba75cb0d7809a1cb49a07207` |
| mobiphysio-index-1622f855/summary.json | 真实CSV／清单匹配 | `c03e1d9bd9e868a818c78e27cf5fa3fb76c0f6062a6d0b1d600f87489e5bb768` |
| video_score_index.json | 逐组评分、原值、隔离和缺标列表；仅忽略目录 | `1fe77e6dc012bae641e8ff4c621f210d0e1d26884b8f359d62d4271ba25ae1a0` |

README与CSV官方MD5分别`0c8411ef74a9d04eceea3ac08d0c217b`和`f517c958e0aba21745d802a601b304a2`。原摘要保存获取时源码hash；旧分类器结论未改写。当前CC0解释和最终索引源码是后续阶段，不能声称当时已运行最终源码。

SUMedi一次官方`:latest-published`工具输出观察到1.0／NC-SA4.0／3654文件，未保存完整数字快照。正式工具`dataverse-sumedipose-2e411b52`、`dataverse-sumedipose-59a41b51`均根请求ReadTimeout，实际20.857／20.806秒，HTTP状态未取得；两个summary SHA分别`296d38ba0622542732d1495cbf1c86b28454436e91a249aa37a2a3047e46dff2`、`ec61a5b68a24441cb5b0c857a49340800757f7158c1470d3c5046442848455e5`。没有反复打开观察超时后的同一worker、访问申请、数据下载或资格推定。

## 实际评分与开发失败

实际CLI`fetch-dataverse-metadata`退出0，下载551744字节；随后`index-mobiphysio-scores`读取保留文件而非TEST。CSV有3010视频组，3008通过／2隔离、19空行；676视频无评分。正式命名3685／3686，一个未知VP不映射。所有通过评分覆盖24人；E01有380／558评分通过、24人、正面128／左视角128／右视角124。

两异常组保留：`E01_P01_AL_VLJ_GM`含6行／续行出现新平均值；`E09_P23_AR_VO_GM`含15行及无效数值。未拆组猜测缺失视频名、删除后假称全标注或代补标签。最初索引因`E03_P41_AF_VP_GM.mp4`不符合README变式全局拒绝，输出已保留在本轮工具记录；修改为未知清单且不进入已审查命名统计，末次CLI退出0。未知变式没有专业解释，原问题未假称修复了数据。

20项Dataverse TEST和10项CSV TEST单独退出0；覆盖草稿／版本变化／身份／checksum／NC-SA／CC0、缺restricted、guestbook／embargo、安全ID与文件名、禁RGB、数字快照篡改／越界、双表头／继承／三治疗师／重复组／有限数／算术／舍入及视角／动作不误映射。它们是工程契约，不是对3010真实组的抽样准确率。真实索引另列，不混入测试计数。

`build-pose-dataset --dataset mobiphysio --target-schema coco17`实际返回ok=false／缺独立2D监督，更新[监督缺口](../../reports/rehab_backend/pose_supervision_blocker.json)，不产生假关键点。终端随后继续执行完整回归；该拒绝不能因后一命令退出0而被说成训练成功。

## 范围与尚未完成

本增量没有下载或解码RGB、按人划分、RGB模型训练、真人2D／visibility／相位／纠错／提示真值、医学效果或产品上线。原IRDS模型结果保持，不能将CC0或工程测试解释为准确度提高。未修改整个前端／Android／原权重／正常库，不启停用户8765／1396、相机或关闭旧窗口；开工280份用户文件排除提交，原1308保护基准不重建。

## 末次完整回归与保留核对

`verify_all.py`实际`verification-e726e3db`结束0，新后端416／原康复12／原手机19全部通过；20＋10项新TEST是416子集。原Starlette/httpx warning仍保留，未升级依赖。scope读取原1308基准变化0、基准SHA`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`，验证时间2026-10-11T10:33:47.572486+00:00。另对280份开工用户文件状态及逐文件SHA比较，变化0、排除暂存，未重建baseline。

| 完整命令阶段 | 退出码 | 秒 | 实际日志SHA256 |
| --- | ---: | ---: | --- |
| new_backend | 0 | 195.806 | `ded9c063ba399938b0cf48922a00bb4901a615df72be8fdd9b6cce14536a71d5` |
| legacy_rehab | 0 | 0.236 | `d02a26e84c4b111c1022056c665d6658871a3550921b524b210bb8e790a5c375` |
| legacy_mobile | 0 | 15.529 | `a2b3f5ca11f6e0739042f59133565164e9a054094073a637f90e25a5c4aa3312` |
| scope | 0 | 5.413 | `0a81117bae783bed82a5d84cca1caa42b98e4a66c6e61e19374485cebbbd54a0` |

日志全部位于忽略的`.runtime/rehab_ml/run/verification-e726e3db/`；[regression.json](../../reports/rehab_backend/regression.json)保存完整命令、实际解释器、日志路径／尾部。检查counts／hash，不把以往三轮专项称作本轮重跑。

| 最终实现／契约源 | SHA256 |
| --- | --- |
| tools/rehab_ml/dataverse.py | `fd49eada79bc73b24d40c02db924d503ba2789cbc965d06fe185b00b39fcd797` |
| tools/rehab_ml/mobiphysio.py | `a065a360d60b6b74afd5ec9993e93450695c11100859b2ac39c1ef6f5193529d` |
| tools/rehab_ml/cli.py | `d776c521346d31825618f1d5fa40540f243bfa85b1a73bfb821112f828174f6d` |
| tools/rehab_ml/download.py | `38385fabf9f49c229b214a706e6eb272259f133d84c79db7b9ee707574be8f4b` |
| tools/rehab_ml/target_domain.py | `d5837e27e7f0b6983a6f0c5ac26cd2d993e9c08733a65abfbd61a691c766fe85` |
| configs/rehab_ml/datasets.yaml | `5b91e6bed785979a474853bb7a223d698300b0f8111f29a2ca5f145fd014d55b` |
| tests/rehab_backend/test_dataverse.py | `a1ced6e7da49044cf9f680185cd8f4165711ff0fe12072f3f432db25003546e5` |
| tests/rehab_backend/test_mobiphysio.py | `0113bbb81a70ac557275464a8560131734bf59d146c037c9114dd7f1e55dc6d7` |

最终索引绑定其中dataverse.py及mobiphysio.py；元数据获取和SUMedi失败摘要分别绑定当时更早实现／配置。三个阶段的source hash不能互相冒称一致；实际文件和最终实现来源一并保留于[聚合证据](../../reports/rehab_backend/dataverse_metadata.json)。另实际复核23个源／日志／摘要／文档数据／快照／索引hash，变化0；7份本轮文档593个本地链接均存在、代码围栏闭合，diff whitespace检查通过。只提交上述范围及必要文档／报告至后端分支，发布核对远端后刷新原桌面入口的Git描述，产品／页面导航不变。
