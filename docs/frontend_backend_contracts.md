# 前端与后端接缝（2026-10-12）

## 已接通

### 任务书10.5：独立感受后补（不是 B03 指导契约）

| 请求 | 字段与语义 |
| --- | --- |
| `GET /api/practice/{id}/feedback` | 本人原记录的practice_id／context／revision／values／saved_at；首次revision=0，未填pain／fatigue／note为null |
| `POST /api/practice/{id}/feedback` | 精确字段operation_id UUID、expected_revision非负整数、values（pain／fatigue各null或0–10整数，note为null或非空≤500字）；至少一个明确填写 |
| `GET /api/practice/{id}/feedback/operations/{operation}` | 原操作真实COMMITTED、原载荷／expected_revision／提交revision／时间，不以最新编辑冒充旧回执 |

托管原SQLite及APK原Store只有原练习COMMITTED后接收，未提交返回PRACTICE_NOT_COMMITTED；反馈不阻止结束。最多100次编辑，满时507不删原件。同键同值先回原回执，改载荷FEEDBACK_KEY_CONFLICT；旧版本FEEDBACK_REVISION_CONFLICT、不写入。内容和回执同一原事务提交，失败无成功回执。原finish_payload.feedback、各来源次数／正式贡献不修改；原备份保留并校验来源与编辑链。历史明确不适不能通过后改0清掉，沿用原pain>0／fatigue≥5含义，已打开旅程复核执行资格。

客户端先存原键／值，丢回复先查询；实质冲突读最新并保留填写，明确选择才以新revision新键提交；同值按真实快照收敛。稍后填写不写空值，原历史可补填／修改，已填直接读回。草稿按本人／来源／旅程保存，兼容旧单指针；不换provider。不是全模块outbox或Qt／v2正式反馈实现。

### B05：查询原上传

原 `POST /api/jobs` 可以携带 UUID `X-Rehab-Upload-Operation`。托管服务在接收视频前，将该操作及动作／侧别／模式／计划绑定保存到原 job.json；保存失败不制造内存回执。`GET /api/uploads/{operation}` 只能查询本人原 job。原键再次 POST 返回 409，不做第二份分析。APK 原本地 route 也在原 Store 串行写入中保存和查询此字段。

404 不是原 POST 已退出的证明；客户端查询同键，不盲目另建作业。回执表示视频／作业已收到，不等于 session 或报告已保存。断点续传、派生报告重建和跨刷新媒体恢复仍未实现。

### B01／B02：已有安排的独立跟练记录（托管与 APK 本地）

| 请求 | 实际字段与语义 |
| --- | --- |
| `GET /api/practice/context` | 从原认证取得 participant、provider、source_context、policy_version；客户端不指定本人或来源 |
| `POST /api/practice` | 精确字段 operation_id（UUID）、plan_id、plan_revision、entry_key；同操作同载荷返回原旅程，改载荷 409 |
| `GET /api/practice/{id}` | 查询原本人旅程，带当前 execution_allowed／execution_reason；已结束不再授予执行资格 |
| `POST /api/practice/{id}/finish` | 独立 UUID、count（整数或 null）、elapsed_ms、reason、feedback（pain／fatigue 各为整数或 null）；原载荷重发返回原事实，已结束后的不同载荷 409 |
| `GET /api/practice` | 本人记录列表，原历史页面用独立类型读取，不塞入旧 job／session schema |

政策 `saved-arrangement-guided-1`：只接受本人 REPLAY_FILE／SELF_USE、当前 ACTIVE 同版本自动安排，完整复用原自动计划核对；没有相机 READY 前置条件。一个本人最多一份未结束旅程。明确不适／疲劳保留原停练门；查询恢复时重新核对当前安排，失去资格仍可结束并保存已发生内容。

使用原 `Storage._call` 所属 SQLite 线程及真实 commit，在同一数据库增加独立 `guided_practices` 表，不新增患者库，不改变原 user_version。开始检查和创建在 `BEGIN IMMEDIATE` 事务内；结束同键去重和事实保存也在原事务内。创建／结束以权威写入完成后返回，不是 202 受理语义。

记录显式保留 plan_ref、context、policy、record_origin、count_scope=set_total／set_index=1、服务回执时间模式段。没有视觉会话时 visual_session_ref／confirmed_count／formal_plan_contribution 均为 null。用户输入 10 次不是 10 次视觉确认；页面时间不是有效保持，空感受不是 0。

APK 实现相同小型请求形状，写入归属不同：`provider=phone-local-1`、`source_context=PHONE_LOCAL:SELF_USE`、`policy_version=phone-saved-arrangement-guided-1`。不调用托管服务，不把 PHONE_LOCAL 改标 REPLAY_FILE。当前本人来源来自原 Store，plan_ref 只接受当前同版本本地计划；用原 `LocalEngine.propose` 重新核对评估时效／覆盖／完整观察／活动限制／不适，使用原 `planProgress` 的反馈门，并与原安排的评估引用及剂量设置匹配。未满足时不创建记录；这是自动安排的适用核对，不是一个相机 READY 条件。

本地 `practice.js` 在原 `Store.serial` 通道中接线，用原 `Store.change/commit` 将独立 `practices` 数组和事实原子写入同一档案；失败不会返回 COMMITTED。至多 250 份，不自动删除旧记录；只有当前本人可读。结束同键同载荷查询恢复，在资格后来变化时仍能保存已结束事实。null、self_count、页面时间与正式贡献保持分离，时间段为设备回执时间范围，不证明全段都在运动。原备份导出保留此类型，恢复校验来源、本人与计数性质；旧 version2 没此数组仍可读。没有新增患者事实库、模型或正式贡献。

**边界：**这不是“无合格评估”的普遍陪练授权。独立人工计划、资格未知路径、三端同等B01、关联视觉session、多组分段仍待接；独立感受仅上述托管／APK类型已接。Qt未接独立记录，各端资格并非相同，不把同形请求说成同一医疗执行器。

## 其余依赖

| 接缝 | 状态 |
| --- | --- |
| B03 过期指导取消 | 预览已有 generation／有效性／语音限频／cancel；完整 cue ID／证据／epoch／TTL 调度适配待做 |
| B04 新来源历史 | 托管／APK 的 `/capture` 分开显示原 job 与独立跟练，APK 原备份保留独立记录；统一首页、Qt、v2 历史投影待做 |
| B06 原因与真正阻止条件 | 新 practice 拒绝有固定码／对象；尚未全面覆盖原 API、空间、格式和全部业务 |

v2、原视觉、独立练习、反馈和报告的回执不能相互替代。客户端不以 HTTP abort 宣称服务器回滚，也不因技术失败换 provider。
