# 工作台开源项目参考

查阅日期：2026-10-13。目标是加快现有安康医生平台的三个功能交付，保留原有账号、授权和数据库。

| 项目 | 本轮可借鉴的内容 | 接入判断 |
| --- | --- | --- |
| [Chatwoot](https://github.com/chatwoot/chatwoot) | 会话列表、历史消息、未读与发送状态的客服工作台流程 | 现有医生网页继续扩展；整套 Rails/Vue、Redis 服务会增加账号和部署整合工作，本轮仅参考交互流程 |
| [Medplum](https://github.com/medplum/medplum) | 通用模板与具体患者计划分开，具体计划关联患者、任务和状态 | 本轮保留安康既有动作契约与本地训练规则，仅参考计划建模；引入完整 FHIR 服务会扩大范围 |
| [Socket.IO](https://github.com/socketio/socket.io) | 消息编号、确认、数据库持久化和断线后的游标补取 | 第一版采用现有 HTTP API；未来需要实时推送时可加通知通道，持久化与重试仍由当前数据库和客户端队列负责 |

上述接入判断是对本项目结构的工程评估，并非这些项目的性能结论。本轮未复制其源码，也未新增这三个项目的运行依赖。

## 核对过的原始资料

- Chatwoot 的[根许可证](https://github.com/chatwoot/chatwoot/blob/develop/LICENSE)：普通社区源码为 MIT Expat，`enterprise/` 另有许可证，第三方组件遵守各自许可。以后复制源码时须核对具体目录并保留声明。
- Medplum 的[许可证](https://github.com/medplum/medplum/blob/main/LICENSE.txt)为 Apache-2.0；[Care Plans 文档](https://github.com/medplum/medplum/blob/main/packages/docs/docs/careplans/index.md)将抽象 `PlanDefinition` 与针对患者的 `CarePlan` 区分。本轮医生草案、不可变发布版本、患者采用记录延续安康自己的数据结构，未宣称符合 FHIR。
- Socket.IO 的[许可证](https://github.com/socketio/socket.io/blob/main/packages/socket.io/LICENSE)为 MIT；[Delivery guarantees 文档](https://socket.io/docs/v4/delivery-guarantees/)指出默认连接不保证断线消息补送，重试也不能独自保留刷新前的待发消息。因此工作台将操作编号和待发内容持久化，服务端按编号去重，历史消息按序号补取。

现有云分支 `codex/unified-cloud-service` 的 FastAPI、SQLAlchemy、Argon2 账号与授权功能才是本轮直接复用的代码。外部项目的诊疗示例不作为安康的动作支持、评估门槛或处方依据。
