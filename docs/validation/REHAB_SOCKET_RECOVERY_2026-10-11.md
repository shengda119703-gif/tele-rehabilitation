# 真实HTTP丢响应与独立服务重启：本机验收

日期：2026-10-11；基准`1fd6806666d4f41cb6b235d4f99d95154b7611b5`。只新增socket工具、核验器和3项测试；生产服务、前端、整个Android、规则、权重、正常库均未修改。

## 1. 实际专项

开发`socket-recovery-d8583bca`22条件退出0；最终源码以以下固定三轮为准，不用开发轮代替。产品解释器运行`-X utf8 -B tools/rehab_ml/verify_socket_recovery.py`；`socket-verification-9b308f4f`四命令退出0，3项单测及3次预声明TCP审计，耗时6.622／6.606／6.590／6.445秒。命令预算90秒，不调整预算去换通过。

| 实际run | 条件 | 原宿主／新宿主实际退出 | 原宿主两native退出 | 备用清理 | 原始summary SHA256 |
| --- | --- | --- | --- | --- | --- |
| `socket-recovery-0a6947bc` | 22／22 | 强制1／正常0 | 是／是 | 无 | `bdd988c5a99900f660061e550241854833441063588d11fec76dbdaeb447eda0` |
| `socket-recovery-23f2c71b` | 22／22 | 强制1／正常0 | 是／是 | 无 | `9e76100220db9b780f1ce7d373ee9ea357cee22fa35386c5402b63af45e77de8` |
| `socket-recovery-9d6542af` | 22／22 | 强制1／正常0 | 是／是 | 无 | `d0210b4255ba158be82ebdc784dd57acecfa0c14a7d7513ac01e905405eab4a3` |

[专项汇总](../../reports/rehab_backend/socket_verification.json)记录15份源码／原权重SHA、四命令日志hash及每轮两宿主日志；[最后一轮](../../reports/rehab_backend/socket_recovery.json)对应9d6542af。原始TEST库、cookie及内部响应门文件只留忽略目录，公开结果不包含owner或凭证。

真正的生产`create_app`和Uvicorn监听OS选择的127.0.0.1端口；真实pair与原cookie验签、已有计划解析、原v2路由、原YOLO JPEG与报告都被执行。创建／结束原服务已落库后，由TEST门延迟HTTP响应；客户端RST自己的实际连接且未读取响应，随后网络查询／重试找回原ID。强制宿主准确所持句柄退出后，第二个实际服务器在同隔离数据目录启动，旧cookie重新连接不同临时端口。

SQL独立只读核对2个session、每个1贡献、训练1反馈／评估0反馈。既有TEST评估不是人体真值；白图无人计次0、计划进度0，不能称康复训练完成。原finalized事实与canonical／反馈revision不变；新draft恢复interrupted且禁止resume。工程验证不改变继续政策或自评。

## 2. 完整回归与保护

完整`verification-6fe7c7c8`在本次最终源码实际运行，四命令退出0：新后端386项（211.790秒含启动）、原康复12项（0.241秒）、原手机接口19项（15.243秒）、原1308保护（14.132秒）变化0。原240／150秒预算保持，3项socket测试是386子集；三轮22条件不累计成测试或准确率。Starlette／httpx原警告保留，没有依赖升级。[完整摘要](../../reports/rehab_backend/regression.json)与[保护摘要](../../reports/rehab_backend/scope_verification.json)记录真实命令、日志hash及退出码。

开工280份用户文件保留，逐文件SHA与状态核对后排除提交；原保护baseline SHA仍为`75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`，没有重建。15份专项源码／原权重、四专项日志、三原始summary、六宿主日志及四完整回归日志共32项hash核验一致。正常用户库／模型／客户端只读。

发布静态核对：7份维护文档的575个本地链接、48张表与代码围栏通过，公开JSON可解析，Git差异检查通过。本次没有额外构建Android或运行UI／照护验收；3项新增单测包含在386项内，不另加重复轮数。

## 3. 范围

仅Windows本机TCP，不是目标手机、LAN、TLS、公网、代理、自动发现、自然弱网概率、长时或多客户端负载。这里第二评估没有确认次／半次；已确认次恢复仍引用此前独立TEST几何实验，不冒充这一轮实际JPEG结果。没有新增算法准确性、临床金标准或研究候选接入证据。

产品0.20.0、既有APK0.2.1、v2默认关闭，首页／康复／健康／用药／家庭保持；不启停用户8765／1396服务／相机、不关闭用户窗口。

发布范围：远端main并发推进至`b78f67400645d08d53f1ea653c4409a7c4ac9ecd`，含管家、正式界面和版本变动；未合入本轮冻结源码。已验收增量发布到`codex/backend-information-map`，不覆盖或强推main；本文结果仅对应上列本机源码及专项产物。
