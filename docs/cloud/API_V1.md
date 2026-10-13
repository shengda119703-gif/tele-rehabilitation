# 云账号第一阶段接口

当前服务0.1.3，schema1，原账号／结果API形状保持兼容；本文件与`cloud_service/app.py`对应，同目录`openapi-v1.json`保留0.1.0接口快照，实时版本取`/api/cloud/v1/openapi.json`。真实公网源为`https://139.224.216.18`。只描述当前已实现接口，不代表C0–C6的全部契约。

0.1.3增加受WEB患者会话保护的完整应用根入口和`/capture`，账号／云记录移到`/account`，医生仍`/care`；能力接口新增`public_user_web=true`和`browser_analysis=LOCAL_CPU`。这不是服务器模型执行或完整增量同步：`server_models`、`incremental_sync`、`plans`与`calls`保持false。公开资源仅来自构建清单，具体见[公网用户网页](PUBLIC_USER_WEB.md)。

## 认证与数据边界

网页登录默认`client_kind=WEB`，响应写host-only、Secure、HttpOnly、SameSite=Strict会话Cookie；`auth/me`返回本会话CSRF令牌。写请求使用`Content-Type: application/json`、同源`Origin`、`X-CSRF-Token`。密码不写入URL。网页令牌不能改作Bearer。

原生登录`client_kind=APK`或`DESKTOP`，响应返回15分钟`access_token`和最多30天`refresh_token`。无浏览器Origin的原生注册/登录/刷新需`X-Ankang-Client: native`；这个声明只允许匿名认证请求，不赋予任何账号权限。登录后受保护请求用`Authorization: Bearer ...`。刷新原子轮换，旧访问/刷新令牌立即失效；不要在收到未知回复时创建新身份或上传到另一账号。APK0.3.1的AndroidKeyStore与桌面0.21.0的DPAPI／独立队列适配已接，真机验证仍待，见[端连接说明](CLIENT_CONNECTION.md)。

账号、患者UUID、会话来源由服务器确定。普通注册只创建自己的空白档案，不能带role/team_id/actor_id；共用医生只读明确授权患者。`record-events`只允许患者本人写入，共用医生不能冒充患者代录。`source_kind`是客户端声明，服务器固定标记`attribution_state=DECLARED`，不声称专业核验。

最大请求256KiB、单记录32KiB；查询limit为1–100。秘密、密码和原始令牌不进入业务审计。域错误是`code/message`，校验失败不回显原输入。

## 已实现调用映射

路径未注明前缀的均位于`/api/cloud/v1`。

| 方法/路径 | 调用方和输入 | 返回/语义 |
| --- | --- | --- |
| GET `/health/live`（无前缀） | 监控，无账号 | 进程存活与服务版本 |
| GET `/health/ready`（无前缀） | 监控，无账号 | schema1和已启用共用医生均存在才ready |
| GET `/capabilities` | 能力发现 | 当前账号/患者能力；专业计划、增量同步、消息、通话和全部外部provider关闭 |
| POST `/auth/register` | 患者；username/password/display_name | 201，全新patient_id；不覆盖同名账号，不自动登录 |
| POST `/auth/password/login` | 网页/原生；username/password/client_kind | 账号及患者绑定，网页Cookie+CSRF或原生令牌 |
| GET `/auth/me` | 当前已登录者 | 当前账号/角色/患者；网页CSRF |
| POST `/auth/refresh` | 原生；refresh_token | 新访问/刷新令牌；并发只有一个成功 |
| POST `/auth/logout` | 当前已登录者；空JSON | 当前会话撤销，COMMITTED |
| POST `/auth/password/change` | 本人；current_password/new_password | 原密码核对；新密码哈希保存并吊销所有会话 |
| GET `/auth/devices` | 本人 | 最多100个会话及当前会话ID |
| POST `/auth/devices/{ident}/revoke` | 本人；会话ID/空JSON | 只撤销自己的指定会话；其他会话保留 |
| GET `/patients/{ident}` | 本人或当前授权医生 | 档案、共享状态、grant_version；跨患者404 |
| PUT `/patients/{ident}/doctor-access` | 患者本人；enabled/expected_version | COMMITTED+新grant_version；旧版本412 |
| GET `/care/patients` | 共用医生；offset/limit/search | 只在服务器过滤后的授权范围分页/计数/搜索 |
| POST `/patients/{ident}/record-events` | 患者本人；见下一节 | 201，COMMITTED/resource_id/idempotent |
| GET `/patients/{ident}/records` | 本人或当前授权医生；offset/limit | 分页云记录，含来源声明；不是增量游标 |

网页`portal.js`调用注册、登录、me、改密、退出、本人档案/共享、医生列表/详情及records。记录追加已可用并经过浏览器API验收，但原产品的本地上传/outbox适配尚未完成；不要把网页空档案当作旧数据丢失。

## 记录追加契约

输入包含UUID `operation_id`、`source_event_id`、`installation_id`、`source_kind`、对象`payload`。允许来源为WEB_LOCAL/APK_LOCAL/DESKTOP_LOCAL/SELF_REPORT/IMPORT。服务器添加record UUID、submitted_by、received_at、固定来源状态及内容摘要，与审计在同一事务提交。

同一提交者/operation_id、同患者/同内容重试得到原resource_id。相同操作的不同内容返回409 `IDEMPOTENCY_CONFLICT`；同一来源事件换操作键返回409 `SOURCE_EVENT_EXISTS`，客户端核对原事实，不生成重复记录。 PostgreSQL在患者行锁内核对两个唯一约束，真实并发已实测。

这只是有来源的追加事实接口，不覆盖已有临床评估字段、不自动发布计划、不计入旧执行器的正式贡献。`received_at`和记录主键不作为增量提交序号。

## 常见状态

- 401：会话或密码失效，重新登录；没有姓名/手机号捷径找回。
- 403：来源/CSRF/角色不符合；不能用客户端角色参数解除。
- 404：不存在或不属于当前授权范围，不透露他人是否存在。
- 409/412：同键异内容/授权版本冲突，保留原内容后重新核对。
- 413/422：大小或字段不合契约，不回显密码输入。
- 429：认证限流，按Retry-After等待，不无限重试。
- 503：数据库依赖或资源暂不可用，不声称已保存。

没有REST医疗计划、聊天、私有文件或执行推理入口。旧`/api/live`、job、模型安装和旧v2调试接口在本服务不存在。后续三端接线需独立版本验收，不能只换base URL把旧共享固定参与者当作新账号。
