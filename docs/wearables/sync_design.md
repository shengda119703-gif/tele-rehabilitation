# 穿戴后台同步与数据流

版本：wearable-history-1。仅后台，原UI/CSS/Qt/安卓前端、模型、计次、处方均冻结。

`原配对cookie本人 → 一次性授权尝试 → 官方授权 → 后端换票/身份核对 → 加密token + logical_source_id → 有界同步任务 → 每类型/每日全页解析 → 原子快照/回执 → /api/health/records、summary、training-context`

## 身份及数据

1. owner来自server.py原owner闭包，不接受JSON中的patient/participant/owner。共享页面查看别的患者不会改变本机主人；没有跨患者绑定授权。
2. logical_source_id与connection_id复授权保留；generation递增，旧工作者/上传lease立即失效。另一个厂商账号是另一来源，不按昵称或设备型号合并。
3. 每种记录明确kind、unit、start/end_ms、原时间字符串/单位、timezone及来源、store/record ID、version、parser_version。null不补0，不把平均心率展开成曲线。事实独立于旧ProductService与苹果桥。
4. 多路来源按本人/类型/自然日保守选一个primary（cloud→official_local→health_connect），其他记录可追溯但不相加。步数daily存在时，summary不再叠加delta；时间重叠的睡眠/运动不盲目累计，返回未知总时长。

## 写入与恢复

新wearables.sqlite3 schema1独立，未知版本拒绝；旧康复库user_version不改。records/snapshots/receipt/job checkpoint事务写入。每日无稳定ID快照全页暂存于工作者内存，完整非空后一次事务切换；中途中断/权限变化/空返回不清旧结果。当前不做云端删除推断。旧成功覆盖仍可读，局部失败明确partial_or_unknown。

首读7个来源自然日，后续回看最近3个自然日（项目默认策略，近似72h，DST时并非精确72小时）；时区必需明确。每任务冻结日期锚/窗口，重启后仍从原窗口开始，已提交窗口有同事务证据。快照事务顺序号阻止晚到旧任务覆盖新结果；seq不是厂商测量时间。

任务有180秒worker租约，另一个服务启动不抢活跃工作者；重复点击合并到同job ID。过期工作者只在重启/显式同步检查恢复，**没有常驻自动轮询器**。连接refresh单独120秒串行租约+revision CAS（覆盖华为换票与tokeninfo两个有界请求），调用者最多35秒等待；令牌刷新回复丢失时不冒充已有新refresh token。

HTTP最多3次有界网络重试/退避抖动；401/403不自动循环授权；不跟随重定向。页面/响应/窗口有量限制。鉴权失败不会触碰相机或康复。厂商错误原始body不输出，不记录token/AppSecret。原启动器access_log=False，启用外部网关还必须关回调query日志或脱敏code/state。

## 本地导入参考底座

outbox.py：owner+connection+generation+installation作为scope；page cache+事件+source cursor同事务；另行收到耐久server ACK才标记队列完成。崩溃/断网/回复丢失复用batch/event ID；服务端receipt可查询。换本人暂停旧队列，不拿B的凭证发A数据。逐源ID版本与删除墓碑阻止旧数据复活；partial/rejected receipt不清队列；disk full不推进cursor。

此底座是Python参考实现，**尚未移植并接入APK SQLite及SDK**。server upload-lease是安装通道许可，可单独停用，不能假称已接入原APP logout。HC过期token的保存流程有工程测试，平台实际Changes/DeletionChange与aggregate策略仍未实现。

## 撤销与训练边界

撤销先本地generation++，停新读写、取消jobs/leases，再单次远端解绑。返回confirmed/unconfirmed；不确认远端失败为成功。令牌只为本次撤销读取，随后清除；远端失败后用户需在厂商App三方管理中手动撤销，本轮尚无远端解绑重试worker。仅显式delete_imported_copy=yes删除本来源安康副本（无法从本库恢复，未删除厂商原件）。复授权后重新导入已删副本需在start明确reimport=true。

training-context只按明确时间窗读实际历史心率，保留记录ID/版本，不插值，不更新康复完成/训练剂量。未接自动session关联/家属授权共享，也未回填ProductService健康卡片；这两项留作独立后续工作。
