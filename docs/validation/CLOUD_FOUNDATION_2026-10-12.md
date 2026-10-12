# 统一云账号与服务器实际验证

日期2026-10-12，Asia/Shanghai；云服务0.1.0/schema1，分支`codex/unified-cloud-service`，基线c6fada6。此次不是完整64场景或三端安装验收。

## 环境与保护

- 原工作树：E盘项目，原前端分支、未提交修改和用户素材保留。新管理工作树位于`C:/Users/Administrator/.codex/worktrees/unified-cloud-service/health-care-software-main`。
- 本机：Windows，隔离`.runtime/cloud-service-venv`，不安装到原Qt/手机模型环境。
- 远端：用户提供的139.224.216.18，root/22密钥SSH实际成功；Ubuntu22.04.5/Python3.10.12/PostgreSQL14。可见RAM约1.7GiB、根盘40GB，初始仅SSH服务，没有既有网站覆盖。
- 云运行：非root ankang-cloud账号，单进程API环回8780、PG环回5432；UFW只开放22/80/443。没有云模型、权重、旧应用录像、患者库或整份Git上传。
- 医生密码生成于服务器，只通过受限本地桌面文件交付。原PEM未改；操作副本/known-hosts在忽略目录，不输出密钥内容。

## 测试与实际流程

| 检查 | 实际结果 | 证据/边界 |
| --- | --- | --- |
| 本机pytest cloud_service/tests | 21通过、2跳过 | 2项需实际PG；最终`.runtime/cloud-tests-isolated-final.xml`，不能把SQLite视为并发证明 |
| 主机pytest同版本代码 | 23通过、0跳过 | 最终`.runtime/server-qa-results-final.xml`；独立ankang_cloud_qa，绝不drop生产库 |
| PostgreSQL原生刷新竞争 | 4并发请求，1个200/3个401 | test_concurrent_native_refresh_only_once，真实行锁与轮换 |
| PostgreSQL记录重试竞争 | 4并发，1原记录，其余同resource_id | test_concurrent_record_retries_one_fact，实际唯一约束/事务 |
| 简单密码 | 单字符、纯数字、纯字母、中文、空格、128字符均按规则测试 | 无复杂度，不trim；空密码拒绝；最大长度只限制滥用 |
| 隔离与来源 | 禁止角色注入/患者越权，医生仅授权范围，记录DECLARED | 原始输入错误不回显秘密，同键异内容409 |
| 会话与CSRF | 网页Cookie/同源CSRF、改密全会话吊销、指定会话吊销通过 | 原生短令牌契约测试不是实际APK安全存储证明 |
| 公网浏览器 | 完整路径通过，pageerror为0 | 实际Edge，无ignoreHTTPSErrors；手机390×844、电脑1440×940 |
| 原UI保护 | 4份共享CSS/icon内容SHA与基线一致 | 新云页复用原视觉，未重构原患者UI；截图逐张审查 |
| 包依赖/脚本 | pip check、JS语法、Python编译、Git diff检查通过 | 运行与证书包从显式HTTPS镜像安装，不声明全项目回归 |

公网浏览器实际创建专用合成账号，密码`1`；登录后通过真实API追加一条明确标注合成资料的SELF_REPORT，并同键重试。刷新保留会话与记录；医生未获授权时列表为0，授权后可打开实际云记录；撤销后既有医生会话查询该患者404、列表移除；退出后同患者重新登录读取成功。这里是部署验证，不是人体测量、临床数据或现有用户历史填充。

公网完整浏览器流程实际独立通过2次：初始部署的`.runtime/public-browser-01/`，固定0.1.0发布后再验的`.runtime/public-browser-02/`。各有result.json、PRIVATE-patient-before-grant.png、PRIVATE-doctor-records.png、PRIVATE-doctor-after-revoke.png；两次pageerror均为0，最终两尺寸截图再次审查。原始患者/会话标识不纳入公开报告。两次各精确停用其验收账号、吊销会话、关闭共享；原始合成事实和审计保留，没有删除实际患者。

## HTTPS与运行状态

实际HTTPS入口：`https://139.224.216.18/`、`/care`；`/health/live`和`/health/ready`都位于根路径，不在API前缀。一次误用`/api/cloud/v1/health/ready`返回404，随即核对真实路径为200；没有把路由错误当作服务未启动。

真实证书：Let's Encrypt YE1，SAN为该公网IP；起始2026-10-12 21:06:54，到期2026-10-19 13:06:53（Asia/Shanghai）。首次staging验证、正式签发和后续`renew --dry-run --run-deploy-hooks`均有成功日志。第二次续证远程进程结束后SSH工具会话未自动返回；核对进程已结束、日志成功、Nginx/API健康，再关闭本轮自有连接，不记录为证书失败或声称SSH退出码成功。

续证timer每日两次、随机最多30分钟，服务TimeoutStartSec=300；备份timer每日03:15。服务active/enabled，NRestarts=0；一次快照MemoryCurrent约89MiB，仅是空闲快照，不代表p95、并发或负载容量。SSH再连接成功，原电脑服务不启停。

最终发布链接为`/opt/ankang-cloud/current -> /opt/ankang-cloud/releases/0.1.0`，原c0目录保留。仅本轮云代码/部署脚本/4份公开视觉资源进入发布包；本地和SSH主机发布包SHA256一致：`9f3c06db26757bc1e5c2daabec22ef7d16cccf828e6c838340f3ebfbda8c8707`。固定发布后重跑23项主机测试、DB权限及第二次公网完整浏览器流程；没有重启旧电脑服务。OpenAPI为该运行版本下载的真实16条路径。

## 数据库权限与备份

真实应用角色非superuser、非表owner；cloud_audit UPDATE/DELETE禁止、INSERT允许；密码全部Argon2id。公开API对每条查询重新核对当前授权，无RLS，不声称有额外RLS或独立审计锚。

20261012T140752Z.dump.enc为实际加密备份，18928字节，AES256/PBKDF2独立秘密。在单独ankang_cloud_restore_check恢复，schema1、唯一共用医生、审计存在验证通过；生产库未覆盖。此备份发生在公网合成追加之前，只证明当时的云基础事实恢复。检查库保留供核验。

密文副本保存在本地`.runtime/server-backups/`，密钥仍为服务器受限文件；不是自动持续异地备份，没有独立灾备主机、密钥恢复材料交付或RPO/RTO承诺。需要后续指定私有异地备份目的地和告警接收方式。

## 保留的警告和未完成项

Starlette TestClient使用httpx的弃用警告在本机与服务器均存在，测试0失败。一次本机默认pytest临时目录退出清理报告6条Windows目录非空警告；没有清理他人临时资料，使用本轮新隔离basetemp再次验证。最初服务器默认包镜像为HTTP，随后把运行环境与Certbot依赖从显式HTTPS阿里云镜像完整重装；官方HTTPS PyPI安装连接等待过久，只停止本轮自有安装进程，不能称该次官方源安装通过。

没有真机APK/Qt账号接入、原患者迁移、端侧模型精度、临床审批/发布、消息/语音/文件直传或跨网TURN验收；没做任务书负载画像压测、独立审计锚、正式域名DNS或灾备RPO/RTO。完整差异见[CLOUD_TASKBOOK_STATUS_2026-10-12.md](CLOUD_TASKBOOK_STATUS_2026-10-12.md)。

上线范围为简单账号和授权查看的第一阶段；原APK/桌面仍原版本，原前端长目标继续独立推进。源文件/配置允许上传，密钥、登录信息、私有QA和备份不纳入Git。
