# 厂商开通与部署清单

当前信息：用户小米手环7，暂按小米运动健康（Mi Fitness）；华为设备/账号、两厂商开发者审批和凭据均未提供。无需解绑/恢复出厂；密码、ClientSecret、token不要发在聊天或提交Git。

## 项目负责人准备（外部条件）

| 条件 | 小米 | 华为 |
| --- | --- | --- |
| 平台账号、应用和健康服务申请 | 待负责人办理 | 待负责人办理 |
| 包名/签名登记 | 原cn.tele.rehabilitation.offline；后续原生接入用原证书 | 同左，所选Android/云产品需正式登记 |
| 获批范围 | 初选步数200016、心率200007、睡眠200009、运动200004；可选范围不强制 | 当前代码只step.read；其他三项待契约/审批后补实现 |
| ClientID/Secret | 仅服务器环境/Secret Store | 同左 |
| 公网HTTPS回调 | /api/health/oauth/xiaomi/callback | /api/health/oauth/huawei/callback |
| 地区/版本/时间范围 | 核对真实应用、账号和首周历史范围 | 确认CN账号与正式x-version；非CN暂不支持 |
| 实际健康App同步 | 在原Mi Fitness确认步数/心率/睡眠/运动已同步 | 还需确认App开放授权/关联、上云条件；空返回不能证明已完成 |
| 通知 | 可选审批及公网回调；后台验签入口已实现，未自动创建厂商订阅 | 企业条件、当前签名及204连通性握手待实现，不开假成功 |
| 真机 | Band7 + 当前手机实际OS/App版本、本人明确授权 | 华为手机/手表及当前HMS/App版本 |

Band7可绑定Mi Fitness或Zepp Life（[官方说明](https://www.mi.com/es/support/faq/details/KA-60093/)）；本项目小米云合同不是Zepp Life接口，不保证另一App旧记录自动迁移。原生SDK、Health Connect环境是否可用，必须在目标手机运行后判断。

## 服务端配置与命令

现有 `.venv/Scripts/python.exe` 已安装 cryptography50.0.2、cffi2.1.1、pycparser3.11、tzdata2026.5；本轮无模型下载。版本已核对[cryptography 官方 PyPI 发布](https://pypi.org/project/cryptography/50.0.2/)和[tzdata 官方 PyPI 发布](https://pypi.org/project/tzdata/2026.5/)。跨时区政策变化时更新tzdata并重验日期合同，不以服务器本地时区代替用户所在地。

在项目目录安装可选依赖：

```powershell
& .\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe -m pip install -r mobile_rehab/wearables/requirements.txt
```

使用 `mobile_rehab/wearables/.env.example` 的变量名配置服务进程。程序读取**环境变量**，不会自动加载该模板；Secret由安全启动器/服务管理器注入。ANKANG_HEALTH_ENABLED=1、所需品牌CLOUD_ENABLED=1，其余真实参数齐全才开放该provider。TOKEN_KEY为Fernet32字节URLsafeBase64密钥，使用cryptography.Fernet.generate_key()在私有Secret Store生成并安全保存；不得贴入报告。轮换必须另做解密/重新加密迁移，本轮不自动换key。

诊断（下面目录为隔离检查目录，不是用户库）：

```powershell
& .\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe -m mobile_rehab.wearables.cli doctor --data-dir D:/RehabFrontendFlowVerification/wearable-doctor-01
```

真实服务data-dir取当前原启动器实际路径，不使用测试目录来上线。同步/检查仅由本机管理员执行，owner必须是已有配对本人ID，不是被查看患者：

```powershell
python -m mobile_rehab.wearables.cli sync-once --data-dir <服务运行目录> --owner <已有本人ID> --connection-id <已有连接ID>
python -m mobile_rehab.wearables.cli inspect-sync --data-dir <服务运行目录> --owner <已有本人ID> --job-id <已有任务ID>
```

reconcile复用有界回看；inspect-capabilities与export-compatibility输出只含配置状态/能力，不含凭据或原始健康事实。doctor会初始化独立穿戴库并检查schema，不会初始化个人健康档案；正在活动的job不因诊断而被抢占。

## HTTP接线

沿现有配对cookie以及写操作X-Rehab-Client: mobile-v1。先GET /api/health/capabilities，再POST /api/health/oauth/{provider}/start（可选metrics），在**同一已配对浏览器**打开返回官方授权URL；callback完成后查询attempt与connections，显式POST /connections/{cid}/sync，读job/summary/records。state、code、token不进前端历史/公共日志。暂不支持APK外部浏览器→本机WebView票据回传；不能把上述网页步骤说成已经完成APK一键授权。

原LAN服务不能直接当互联网医疗数据服务公开。上线前需HTTPS域名/反代、可信转发头配置、回调敏感参数日志脱敏、服务器Secret Store/磁盘访问控制、备份策略；多用户登录/治疗师权限要接独立云账户工程，当前配对cookie不能冒充完整账号系统。

## 备份、回退

上线/升级前使用SQLite backup取得一致副本：

```powershell
python -m mobile_rehab.wearables.cli backup --data-dir <服务运行目录> --output <不存在的私有备份文件.sqlite3>
```

备份含敏感健康数据和加密token，仍需私有保存。schema1只创建新穿戴库，不改旧康复库。回退时关闭穿戴enabled环境开关并重开由你控制的服务，旧页面/训练照常；不删除wearables.sqlite3或token key。若需恢复，仅在停止该服务后按经过验证的备份操作恢复此独立库，不能覆盖home_rehab/Apple/manual/药物数据。本轮未对用户运行服务作备份/启停/迁移，未关闭旧窗口。
