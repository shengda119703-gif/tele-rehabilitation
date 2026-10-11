# 原生子进程随宿主退出：本机验证

日期：2026-10-11；基准`a1b96143773f0911f401636685238cc8d87a5739`。新增WindowsJob／启动门，改默认关闭v2的owned_worker及pose／report契约；不改动作、规则、源权重、前端、整个Android、正常用户库或非康复。

## 1. 原始失败与修复

未接新保护的`native-parent-acc2c753`实际CLI退出1，三个用例均在2秒期限内未自动退出（子进程仍259），需要监督程序使用准确已捕获句柄清理。其后资源／记录检查通过不把该轮总结果改成通过。[基线归档](../../reports/rehab_backend/native_parent_before.json)保留原源码hash和`cdab597c9e1a41bd677316a277f0dc57e134c07f468e0d7c43d61ea082e682d5`原始summary SHA。

开发首轮`native-parent-fd6155b2`三个用例通过；工具后续只精简未用import、增强新TEST输出检查并登记原权重hash。正式结果由以下固定三轮和源码hash提供，不用开发轮替代。

## 2. 最终专项

产品解释器`rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe`，实际命令`-X utf8 -B tools/rehab_ml/verify_native_parent.py`退出0。专项`native-parent-verification-ee19bb9f`预声明7项测试＋3次审计；四命令12.638／11.706／11.339／11.374秒，各退出0。

| 实际run | 三用例 | 每用例条件 | 需监督程序补杀 | 原始summary SHA256 |
| --- | --- | --- | --- | --- |
| `native-parent-6788c4a0` | 全通过 | 11 | 否／否／否 | `3939783e18de3b9bb49b08b13da4f4028e48100acd6a9f9b93351c53ae0e650f` |
| `native-parent-38893349` | 全通过 | 11 | 否／否／否 | `e8d909c411adeb8e5fcc3395ac26fe6c496efd15dc3c79cabed91462d1c29319` |
| `native-parent-49130fa6` | 全通过 | 11 | 否／否／否 | `63da514d8c38ab546c9cea63a7e7f1b4120f65568ecff57ed0c45f461550f009` |

[专项汇总](../../reports/rehab_backend/native_parent_verification.json)列真实参数、源码／权重、日志与SHA以及每用例全部检查；[最后一轮摘要](../../reports/rehab_backend/native_parent_audit.json)对应49130fa6。9份源码／权重前后不变，原YOLO SHA仍`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`。原始TEST快照与独立SQL在忽略目录，未写正常历史。

子进程handle信号确认退出，退出码0是Job关闭终止的观测值，不当成正常任务成功；宿主均强制退出1。共享内存不可再打开、heavy lease可取得、确认次保留／半次不补／原或恢复canonical／唯一贡献／空反馈均通过。0.0105–1.1022毫秒只计父退出确认后的句柄观察，不称端到端退出速度。

## 3. 解释边界

两个TEST目标是GIL-held原生等待；原YOLO为白色JPEG冷ticket／原目标函数，不证明forward已完成或真人检测。检查点1确认＋1半次来自另行内部TEST证据；报告用例在提交后阻塞派生任务，恢复不改原事实。没有socket、患者、手机、目标人群或临床金标准。

Job内核保护只对本机已绑定的Windows所属worker，启动门失败明确拒绝并清理。非Windows契约不称同等保证；OS Process.start本身无硬截止。保护失败／嵌套Job限制不静默放行，不把它称安全sandbox。

## 4. 完整回归与范围

实际`verification-6fbb8b9c`沿用原`verify_all.py`与240／150秒预算，四命令退出0：新后端383项（208.208秒含启动）、原康复12项（0.243秒）、原手机接口19项（13.794秒）、原1308保护（5.380秒）变化0。7项生命周期测试为383子集，不累计三轮用例。原Starlette／httpx警告保留，不升级依赖。[完整摘要](../../reports/rehab_backend/regression.json)及[范围摘要](../../reports/rehab_backend/scope_verification.json)记录真实命令、日志hash和退出码。

开工280份用户文件逐文件SHA256与状态一致，排除提交；原保护基准SHA`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`没有重建。9份专项源码／权重与实际日志、三轮原始摘要逐项核对。原始TEST证据仍在忽略目录，没有写入正常历史。

发布静态核对：7份维护文档的564个本地链接、48张表及代码围栏通过，5份公开JSON可解析，29项专项／完整日志与源码hash一致。首检查发现公开失败归档夹带了工具输出截断文本，已从SHA保持不变的原始summary提取精简归档，省去冗长TEST proof而保留三个失败用例、预声明、检查、源码与原始路径／SHA；原始失败仍为false，没有改写原始summary或将失败计为通过。

产品0.20.0、既有APK0.2.1、v2默认关闭，首页／康复／健康／用药／家庭保持；目标数据／专业参考、手机、网络、长时及完整物理故障尚缺。本次不是全UI、全照护或Android构建验收。
