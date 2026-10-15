# 厂商契约与采用边界

核查：2026-10-13。下面是代码采用的协议，不是本项目已获准或真机适配的证明。代码不回写厂商数据。合同夹具仅在私有测试目录，绝不进入用户档案。

## 小米云（已实现工程契约）

依据：[服务端指南](https://dev.mi.com/xiaomihyperos/documentation/detail?pId=2333)、[云API](https://dev.mi.com/xiaomihyperos/documentation/detail?pId=2328)、[数据类型](https://dev.mi.com/xiaomihyperos/documentation/detail?pId=2329)。

| 类别 | 采用路径与字段 | 时间/语义 |
| --- | --- | --- |
| 授权 | account.xiaomi.com/oauth2/authorize；scope_provider=healthkit；POST /oauth2/token 与 /oauth2/refresh/token | 实授scope；授权state一次性、绑定本人/厂商/期限；未假设PKCE可用 |
| 身份 | openId/open_id仅接受字符串，两别名不一致拒绝；union_id不是健康数据主人的替代键 | 本人+厂商+健康openId的hash；原身份随令牌加密 |
| 日步数 | GET /healthkit/aggregate/dailies；dataTypes=com.xiaomi.steps.total；group[].dataSet[].dataPoints[].value.steps | startDay/endDay yyyyMMdd、zoneName；总量，不叠加区间增量 |
| 心率明细 | GET /healthkit/dataSources/dataPoints；dataTypeName=com.xiaomi.heart_rate.delta；bpm | 查询及点时间毫秒；不是静息心率或诊断 |
| 睡眠 | GET /healthkit/healthRecords；dataTypeName=com.xiaomi.sleep.health | bedtime/wakeup_time毫秒，all_sleep_duration分钟；以醒来所在地日期归档；不把在床时间算睡眠 |
| 运动 | GET /healthkit/sportRecords/all；sportRecords | 点时间毫秒；sportTime为有效秒数，缺失保留null；不回写康复完成量 |
| 可选体重/血氧 | dataPoints，weight.instantaneous/weight（kg），spo2.instantaneous/spo2（%） | 单独获批/实授才查询，未作为首四项必需条件 |
| 许可核对 | GET /healthkit/profile/authorize?clientId=...；authInfo[].scopeId/scopeType | 每个读取窗口前后核对；变化不提交该窗口 |
| 撤销 | HTTPS POST open.account.xiaomi.com/user/unbindOAuth2Grained，access_token/client_id/client_secret为表单 | **仅业务code=0成功**；文档表格写http但curl为https，项目仅https |
| 通知 | POST /callbacks/xiaomi/healthkit/notifications；x-notification-signature头 | lowercase_hex HMAC-SHA256；signed=openId_eventType_subType_eventTime；metaData未签名，完全不作为事实/URL/范围/患者身份 |

请求头：Bearer、X-Client-ID，每一次尝试更新X-Client-Nonce。nonce为8随机字节+4字节大端Unix分钟，URLsafeBase64。端点各自约束；本轮一日一窗口，低于统计7天/最多10数据类型和明细30天约束。分页去重游标、空页继续、重复/缺失游标拒绝、最多100页、每窗口最多50000记录。

兼容版本：只处理正式文档约定的JSON结构和小米账号文档的&&&START&&&前缀。示例里的秒/毫秒矛盾不按数值大小偷偷推测。字段错误拒绝该窗口，保留旧快照。无稳定ID的全部页先暂存，完整非空窗口才原子替换；空返回不证明删除或设备已上云，保留旧记录并报告unknown coverage。

## 华为云（当前仅授权与CN日步数）

依据：[Web账户授权](https://developer.huawei.com/consumer/en/doc/hmscore-guides/web-get-access-token-0000001050048946)、[官方ID Token验证](https://developer.huawei.com/consumer/cn/doc/hms-references/account-verify-id-token)、[CN日步数，2026-09-07](https://developer.huawei.com/consumer/cn/doc/hmscore-guides/steps-delta-scene-0000001050779060)、[Web撤销](https://developer.huawei.com/consumer/cn/doc/hmscore-guides/web-revoke-0000001050050903)。

采用oauth-login.cloud.huawei.com/oauth2/v3/authorize和POST /token；openid+获批step.read，access_type=offline；通过官方POST /tokeninfo验证签名结果，再核对issuer=https://accounts.huawei.com、aud、exp、RS256、nonce，使用已验证sub。未在未验签JWT里直接取身份。

仅CN官方站点 health-api.cloud.huawei.com。POST /healthkit/v2/sampleSet:dailyPolymerize，dataTypes=[com.huawei.continuous.steps.delta]、startDay/endDay、timeZone=明确IANA时区在该日的+HHMM。响应group[].sampleSet[].samplePoints[]为com.huawei.continuous.steps.total，steps整数；采样点时间是**纳秒**，分组时间是**毫秒**。纳秒/opaque ID保留原字符串，Python整数不经JS浮点。x-version必须由项目申请得到的正式版本配置，不把文档***填进去。

scope表暂仅step.read，其他三类不开放不请求。普通心率告警页不能替代历史心率读取契约。心率/睡眠/运动的完整读路径、单位、范围权限、实际响应和企业订阅验签仍待核对/实现。请求地区未确认或非CN明确失败，不根据手机品牌/IP/语言猜地区，不自动携Bearer跳到外域。Huawei通知入口返回503，不伪造验签或204连通性成功。

## 本地/Health Connect（不声明已接入）

[官方Health Connect 1.1.0稳定版](https://developer.android.com/jetpack/androidx/releases/health-connect)已核查，但当前Java手工APK构建未加入该SDK。本轮outbox.py只是经过验证的**可移植队列参考实现**，不是Android原生读取器，也没有调用getSdkStatus或授予权限。它不能证明红米上Health Connect可用。

后续必须新增正式Android依赖/权限/最小包查询、实际getSdkStatus与features检查、Changes token先于快照、逐类型许可、空Changes后的步数aggregate重算。小米本地灰度名单/OS条件和Huawei Android HMS Core/前台条件各自验证，不能套在云路线。不得逆向私有蓝牙协议或默认解绑手环。
