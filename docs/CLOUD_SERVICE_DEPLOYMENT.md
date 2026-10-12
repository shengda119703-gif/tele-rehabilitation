# 安康统一云服务：服务器与简单账号第一阶段

日期：2026-10-12（Asia/Shanghai）。依据桌面《安康三端统一云服务与医疗团队协作实施任务书.md》；先完整阅读1316行，再检查当前源码。本文只描述本轮账号、隔离与部署，不将整份C0–C6任务书称为完成。

## 本轮明确调整

用户最新要求优先：公开自行注册，只用账号密码，不要求大小写、数字、符号组合，不强制MFA；医生端一个共用`doctor`管理员账号。密码可为1–128个字符，不去除首尾空格，限制最大输入只为防滥用。使用Argon2id慢哈希，不存明文；登录限流和数据隔离继续保留。共用号只追溯到共用账号和设备，不能分辨具体医护，不能伪称独立二人审阅通过。

普通注册永远只创建本人的全新空白患者档案，不接管原TEST档案，不按姓名或本地owner合并。`doctor`为受控初始化保留账号；注册请求不能携带role/team/actor来升级。患者单独授权后，共用医生号才能查看其档案、云端记录；撤销后新查询立即失权。第一阶段不授予自动诊断、用药修改或专业计划发布能力。

## 已有入口到新边界

| 原入口/事实 | 本轮新增适配器 | 云接口 | 数据归属/状态 |
| --- | --- | --- | --- |
| mobile_rehab.server：本机连接码、SharedProduct固定参与者、YOLO/voice/ocr安装链 | 独立cloud_service.app，不导入旧服务器 | /api/cloud/v1/auth/* | 每请求认证得到账号；每注册创建新的patient UUID |
| mobile_rehab.phone_cloud：设备令牌、家庭摘要、整份备份 | 新账号会话API；旧云辅助不覆盖 | 注册、登录、会话、设备吊销 | 新云患者库与旧设备身份不自动合并 |
| APK CloudTransport + cloud.js：旧/v1辅助契约 | 预留真实APK/DESKTOP原生短令牌及刷新契约 | login(client_kind)、refresh、devices | 接口已提供；实际APK界面/安全存储尚未接入，不称三端完成 |
| 本地训练/测量事实与独立practice历史 | 明确来源的record-events追加API | patients/{id}/record-events、records | 提交者来自会话；客户端来源为DECLARED，不升级为专业/设备已核验事实 |
| 当前患者网页静态视觉资产 | 新云账号/授权/医生查看页复用4份原CSS/icon | /、/care | 原患者页面/布局/图标不修改；新页不是原功能已全部迁移 |

## 当前可用范围

真实自行注册、网页HttpOnly会话、共用医生登录、本人档案、患者授权/撤销、服务器过滤分页患者列表、已授权详情及记录读取、带来源追加记录、同操作重试/同键异内容冲突、改密吊销所有会话、指定设备吊销；APK/电脑可用短期Bearer + 原子刷新接口，但本轮未更新实际安装端。

暂不可用且能力接口如实关闭：专业计划工作流、完整增量同步/outbox、家庭分类授权、用药管理、文字/语音会话、文件直传、通话/TURN、模型/短信/推送等外部provider。不是把这些原本机功能删除，而是尚未接入新云账号边界。原个人电脑服务、安装包、录像、患者库均不启停、不上传。

## 独立部署

本机服务器实查为Ubuntu22.04、约1.7GiB可见内存、40GB盘，原仅SSH监听。本轮采用任务书允许的等价模块化单体：Nginx + 单进程FastAPI + 本机PostgreSQL14 + systemd。未安装Docker、GPU、YOLO、MediaPipe、LLM、ASR/TTS/OCR或训练依赖；不复制旧deploy/mobile镜像。

公开端口仅SSH22、HTTP80(ACME验证/重定向)、HTTPS443；数据库5432与API8780仅环回监听。请求最大256KiB，单记录32KiB、分页最多100、连接池4+2、哈希同时2、API并发40；服务400MiB/1核上限。服务器没有模型frame/job入口。Nginx覆盖转发地址，不采信用户自行伪造的X-Forwarded-For。

部署目录：`/opt/ankang-cloud/current`为发布链接，`/opt/ankang-cloud/releases/`为保留版本；运行环境`/opt/ankang-cloud/venv`、证书工具`/opt/ankang-cloud/certbot`。账号密码、数据库凭据、会话秘密在`/etc/ankang-cloud/`受限文件，不入仓库、前端或日志。PEM原件保持不变，操作使用本地忽略目录内的受限权限副本。

本机已使用[Let's Encrypt IP短期证书](https://letsencrypt.org/2026/03/11/shorter-certs-certbot/)完成真实签发：患者入口`https://139.224.216.18/`，医生入口`https://139.224.216.18/care`。公开HTTPS和续期dry-run实际通过，不跳过证书校验。当前证书到期为2026-10-19 13:06:53（Asia/Shanghai）；每天两次自动检查续期，单次最多5分钟，成功后重载Nginx。尚无用户提供的域名，DNS不作已配置声明。

### 全新Ubuntu主机部署顺序

1. 确认机器归属、SSH密钥、已有服务及80/443安全组；不改变SSH登录方式。
2. 安装nginx/postgresql/python3-venv/ca-certificates，上传仅cloud_service、deploy/cloud和4份公开视觉文件；不上传.env、PEM、模型或患者数据。
3. 运行deploy/cloud/install_ubuntu.sh；Python包使用显式HTTPS软件源。默认`https://pypi.org/simple`；服务器实测官方源连接较慢，使用`CLOUD_PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/`完整重装运行环境与证书工具。安装脚本拒绝HTTP源；不把实际镜像安装写成官方源验证通过。
4. 运行configure_nginx.py --origin HTTPS_ORIGIN，准备HTTP ACME路径。Certbot certonly --webroot --webroot-path /var/www/ankang-acme --ip-address ASSIGNED_IP --preferred-profile shortlived --agree-tos（首次宜staging验证；正式去掉staging）。没有通知邮箱时注册无邮箱，续证定时器和状态需自行监控。
5. 在current目录用专用venv运行`python -m deploy.cloud.initialize_host --origin HTTPS_ORIGIN`。只执行一次，已初始化拒绝覆盖；内部秘密和初始医生8位随机数字密码在服务器生成。
6. configure_nginx.py加--tls，systemctl启用ankang-cloud与备份/续证timer。不要把生产凭据写在命令行。
7. 检查health/ready、真实注册/登录/授权撤销、公网证书、数据库权限、备份恢复，记录实际通过/失败；不以单元测试替代部署验收。

### 数据库与审计

迁移为显式管理步骤，不在每个API worker启动执行。`ankang_owner`拥有表并迁移；`ankang_app`非superuser、非表所有者、无schema CREATE，审计只允许INSERT/SELECT而不可UPDATE/DELETE/TRUNCATE。注册、授权、记录、会话更改与审计同事务。没有实施RLS，不能宣称已具备RLS额外防护；访问范围在每条API中执行。

首次schema v1为追加式账号/患者/会话/授权/原始记录/审计/限流表。提交事件按原operation和来源唯一键去重，当前仅分页记录接口，不把普通received_at/主键当增量提交序号。所有客户端声明保持DECLARED，不证明动作精准或实际服药。

### 登录与秘密

初始化医生密码仅保存在服务器`doctor-password.txt`及交付给用户的本地登录信息文件；不在GitHub、常规测试报告或工具输出打印。没有公开医生注册/重置接口。密码遗忘由拥有服务器权限者走受控恢复，不能凭姓名或手机号重置他人。

本次交付的受限本地文件为桌面`安康云端登录信息.txt`。患者先在`/`注册，登录后可点击“授权医生查看”；医生在`/care`用`doctor`登录。没有授权的患者不显示在医生列表中；需要共享时由患者明确授权，不预勾选或把所有注册资料公开给医生。

网页为host-only Secure/HttpOnly/SameSite=Strict Cookie，写入需同源Origin和CSRF；原生访问15分钟、刷新最多30天，刷新成功旧token失效；会话吊销后访问/刷新皆失败。真实安装端安全存储尚待接线。

### 备份、恢复与回滚

每天Asia/Shanghai03:15 pg_dump自定义格式，用AES256/PBKDF2独立秘密加密，文件在`/var/backups/ankang-cloud/`。只有同机备份不等于灾备；独立复制与密钥恢复材料须另存，不把密钥和密文放同一公开位置。

恢复在新QA/恢复库进行，先解密，再pg_restore；确认schema/账号/审计/记录及原表权限后再切换，不覆盖正在使用的生产库。密钥、`service.env`、发布代码版本分别保留。回滚只切换current发布链接并重启此云服务，前提为schema兼容；不删任何云历史、本机数据库或outbox。

## 验收边界

自动测试使用隔离合成资料。SQLite测试不是PostgreSQL并发证明；真实公网网页不是APK/Qt安装端证明；初始化医生不是已核验执业身份；注册成功不是患者已授权；云接收不是动作正确。最终实测结果见docs/validation/CLOUD_FOUNDATION_2026-10-12.md。

当前实际OpenAPI在`/api/cloud/v1/openapi.json`，同版本离线副本在`docs/cloud/openapi-v1.json`；调用与认证要求见`docs/cloud/API_V1.md`。整份任务书64项进度见`docs/validation/CLOUD_TASKBOOK_STATUS_2026-10-12.md`，未实现项不以“接口预留”视为通过。

[密码哈希依据](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)；[SQLAlchemy事务](https://docs.sqlalchemy.org/en/20/core/connections.html)。frontend-design技能仅用于必要新页面复用现有视觉，不重做原产品UI。
