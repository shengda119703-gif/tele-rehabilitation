# 穿戴后台一期验收（2026-10-13）

版本 wearable-history-1；基线707336a，分支codex/wearable-health-integration。桌面仍0.23.2、APK仍0.3.2/code32。**本报告不是整份任务书完成证明，也不是小米手环7实测结果。**

## 证据和分母

- TEST：本机Windows/Python3.13，隔离SQLite + httpx.MockTransport官方字段合同 + 原FastAPI TestClient认证。没有发送厂商真实请求，没有把夹具写进个人库。
- 最终Python全集：mobile_rehab/tests，253项通过，其中69项新增穿戴测试、184项原测试；不能再把此前39项健康子集或专项69项重复相加。原Starlette/httpx弃用警告1条，无失败。
- Apple回归：原test-healthkit.mjs桥接场景通过，另10项adapter测试通过；不是iPhone/Apple Watch真机。
- REAL：W01—W44本轮均未完成设备实联。W39—W41明确NOT_RUN；两厂商审批、凭据、HTTPS回调、真实授权和华为设备缺失。W44未重建/安装APK，未宣称鸿蒙。
- 证据文件：mobile_rehab/tests/test_wearables.py中以下函数；测试输出位于D:/RehabFrontendFlowVerification/wearable-full-final-03.xml（私有，不入Git），原过程失败及后续复测见[验证日志](../validation/WEARABLE_BACKEND_2026-10-13.md)。所有表格的“通过”只指列出的TEST子场景。

## W01—W08：授权和身份

| ID | 输入及期望 | TEST实际及证据函数 | 剩余部分 / REAL |
| --- | --- | --- | --- |
| W01 | 小米换票/回调，绑定配对本人、实际scope、不泄露令牌 | 通过HTTP往返与部分scope；authorization_http_roundtrip_partial_scope_without_secret | 真授权NOT_RUN；网页同一配对浏览器，APK回跳未接 |
| W02 | 华为合法完整授权往返与查询 | 部分：tokeninfo官方验证结果核对iss/aud/exp/nonce/sub；huawei_tokeninfo_verified_identity；日统计合同通过 | 完整HTTP授权往返未测，真账号NOT_RUN |
| W03 | 错state、错owner/provider、过期、重放、新尝试覆盖旧尝试，不绑错人 | 通过六类故障；authorization_state_faults | REAL未执行 |
| W04 | 授权中换安康/厂商身份，不串账户 | 部分：错owner、expected_identity/generation拒绝；explicit_identity_change_and_revoked_auth_attempt | 原生账号切换/外部浏览器生命周期未接 |
| W05 | 只授权部分指标，其他指标独立停读 | 后台通过；HTTP部分scope、revocation_mid_page_permission_change_no_snapshot | 分项UI状态不在本轮范围，真授权NOT_RUN |
| W06 | A退出B登录，A队列不拿B凭证、B不继承来源 | Python队列scope/HTTP owner隔离通过；local_account_change_and_expired_cursor_preserve_past、http_history_receipts_owner_isolation_and_original_write_guard | APK logout/凭证接线未实现 |
| W07 | 家属/治疗师切患者，不改变健康数据主人 | 部分：API只用原配对owner、跨owner404/空结果、不信JSON patient_id | 本分支没有真实团队登录/跨患者授权；NOT_IMPLEMENTED |
| W08 | 撤销后旧任务/通知晚到，不再导入 | generation、租约失效、回调不复活通过；revoke_late_worker_logout_lease_and_delete_scope、xiaomi_callback_signature_metadata_replay_revoked | 真撤销NOT_RUN |

## W09—W18：事实与统计

| ID | 输入及期望 | TEST实际及证据函数 | 剩余部分 / REAL |
| --- | --- | --- | --- |
| W09 | 三次重复/丢响应重试，统计只一份 | 通过；batches_repeat_lost_response_and_conflict、local_bootstrap_transaction_outbox_restart_response_lost | 真实来源重复上传NOT_RUN |
| W10 | 多route/混合来源，不叠加、可追溯 | 保守单一primary通过；multiple_routes_logical_ids_and_delta_dedup | 没有实际HC混合来源或可信映射；不声称厂商同一事件ID匹配 |
| W11 | 同厂商身份复授权保留历史、换身份分开 | 通过logical_source_id/cid保留与generation递增；owner_identity_generation_and_encrypted_tokens | 真复授权NOT_RUN |
| W12 | 不同owner/来源相同record ID，不误合并 | owner/连接/route/kind/store/record隔离通过；owner_identity_generation_and_encrypted_tokens、old_versions_tombstones_and_stable_scope_keys | REAL未执行 |
| W13 | 新版先到、删除后旧新增，不回滚或复活 | 稳定ID版本/墓碑通过；old_versions_tombstones_and_stable_scope_keys | 厂商删除Changes实际读取未接 |
| W14 | 日总量和增量不相加，策略变化时整桶重算 | 前半通过；daily_total_suppresses_same_day_increment | HC官方aggregate与空Changes触发策略重算/版本链未实现，不能整项判通过 |
| W15 | 上海本地跨午夜睡眠修订，只留下一个正确来源版本 | 通过23:00→次日08:00、420→450分钟、旧版本晚到保留450；sleep_midnight_and_effective_exercise_not_rehab_completion、sleep_midnight_revision_replaces_only_same_source | 官方分段ID与真设备次日修订NOT_RUN；华为睡眠未实现 |
| W16 | 秒/毫秒/纳秒、超JS整数、游标精度，未知格式拒绝 | 精确Python整数转换、保留原字符串，非法数/浮点拒绝；exact_time_units、bad_time_never_guessed、strict_semantics、huawei_verified_daily_payload_preserves_ns_and_collector | 无原生JS/Kotlin SDK边界实测 |
| W17 | 缺失、真实0、旧测量晚到，保持区别/原时间 | null保持null，旧日0保持0与旧测量时间；unknown_value_not_zero_summary_not_fake_samples | REAL未执行 |
| W18 | 汇总心率/部分睡眠，不造曲线或字段 | 汇总不生成sample；睡眠保留有效分钟/awake，运动没sportTime则null；unknown_value_not_zero_summary_not_fake_samples、sleep_midnight_and_effective_exercise_not_rehab_completion | UI尚未展示新事实，REAL未执行 |

## W19—W28：同步故障

| ID | 输入及期望 | TEST实际及证据函数 | 剩余部分 / REAL |
| --- | --- | --- | --- |
| W19 | 初始快照期间发生变更，不漏回放 | Python先Changes token、快照、再变化新版顺序通过；local_bootstrap_transaction_outbox_restart_response_lost | 未用官方Changes服务制造并对账新增/修改/删除，NOT_IMPLEMENTED原生reader |
| W20 | 本地事务前失败/提交后重开，cursor/cache/outbox一致 | 异常回滚、重建对象读取同SQLite通过；local_bootstrap_transaction_outbox_restart_response_lost、snapshot_fact_and_job_progress_rollback_together | 没有OS杀进程/Android进程恢复证据，不等同真机 |
| W21 | server保存后回复丢失，同batch重试/查回执 | 通过；batches_repeat_lost_response_and_conflict、local_bootstrap_transaction_outbox_restart_response_lost、http_history_receipts_owner_isolation_and_original_write_guard | 真断网NOT_RUN |
| W22 | 中间页503、空/重复游标，有限停止 | 通过3次有界请求和cursor守卫；multi_page_no_id_failure_never_switches_active_snapshot、cursor_guards、nonce_format_fresh_retry_and_no_redirect | 厂商原网络故障NOT_RUN |
| W23 | 过期token受限重快照，范围外不删 | Python缓存/旧待发事件保留通过；local_account_change_and_expired_cursor_preserve_past | 实际平台token过期及历史许可未接 |
| W24 | 单类型撤权，其他类型继续，不清旧事实 | 分类型SCOPE_MISSING，读完前后scope核对；revocation_mid_page_permission_change_no_snapshot、full_cloud_sync_atomic_checkpoint_coalescing_reconcile | 真实撤权NOT_RUN |
| W25 | 中间页失败/权限变化/空返回，不猜删除 | 通过；multi_page_no_id_failure_never_switches_active_snapshot、snapshots_complete_window_revision_replay_and_scope_loss、full_cloud_sync_empty_does_not_erase_past | 没有无ID云删除确认能力 |
| W26 | SQLite空间满/不可用，不提前ACK/cursor | 实际SQLite max_page_count触发FULL，记录与回执/游标均回滚；server_disk_full_atomic_no_receipt_or_partial_facts、local_disk_full_cursor_does_not_advance；wearable_storage_failure_does_not_disable_original_catalog | 没有把用户真实磁盘填满；隔离故障TEST |
| W27 | 并行刷新，串行交换、scope/token原子提交 | 两service对象/同库/三线程只1次HTTP换票；cross_process_refresh_single_exchange | 函数虽叫cross_process，本轮没有两个OS进程实验；不可冒称进程级已验证 |
| W28 | 无ID多页失败→重试替换→旧快照重放 | 前半分页503/暂存、完整窗口替换和旧seq拒绝通过；multi_page_no_id_failure_never_switches_active_snapshot、snapshots_complete_window_revision_replay_and_scope_loss、full_cloud_sync_atomic_checkpoint_coalescing_reconcile | 未对同一真实厂商两页重排完整序列做实联；不能当作所有无ID删改完成 |

## W29—W38：厂商及交互边界

| ID | 输入及期望 | TEST实际及证据函数 | 剩余部分 / REAL |
| --- | --- | --- | --- |
| W29 | 小米重试时nonce更新，业务ID不变 | 三HTTP nonce均不同、格式正确，batch/job重试保留ID；nonce_format_fresh_retry_and_no_redirect、expired_worker_resumes_same_job_and_sequence | 真限流/重试NOT_RUN |
| W30 | 错签名/改unsigned metaData，不直接写事实 | 头部HMAC拒绝错签名，metadata恶意URL忽略，hint去重、撤销后不复活；xiaomi_callback_signature_metadata_replay_revoked | 真通知NOT_RUN；hint提交→job入队间崩溃未实现耐久dispatcher |
| W31 | 华为独立连通性验证及签名/通知确认 | 明确503 VENDOR_NOTIFICATION_CONTRACT_REQUIRED，不伪造204成功；同上函数 | NOT_IMPLEMENTED，不判通过 |
| W32 | 华为跨地区/恶意Location，不泄密 | CN限定、HTTPS官方白名单、重定向拒绝通过；configs_fail_closed_for_guessed_region_header_and_callback、nonce_format_fresh_retry_and_no_redirect | 合法跨地区重路由未实现 |
| W33 | 小米本地环境不支持，云路线/康复继续 | capabilities如实声明native_readers_connected=false | 本地SDK/get能力/回退未实现，原生NOT_RUN |
| W34 | 华为SDK息屏/离前台，暂停/补读 | 未实现；不声称后台持续读取 | NOT_IMPLEMENTED原生生命周期 |
| W35 | 无GMS/HC不支持，不强制安装/挡训练 | 本轮不引入HC依赖或安装要求；原APK不变 | 可用性/安装交互代码未接；Android NOT_RUN |
| W36 | 无表/拒绝/暂无数据，原康复仍可完成 | 部分：disabled/provider/storage失败时catalog和原健康服务正常，184原模块回归通过 | 未额外操作真机完成一次原训练开始→保存；不将catalog200当全流程验收 |
| W37 | 重载/Activity重建/回跳失败，不重建任务 | 仅后台attempt/job可查询、重复sync合并、活跃lease不被别的service抢；two_service_start_does_not_steal_live_worker、expired_worker_resumes_same_job_and_sequence | 前端状态恢复/Activity/外部回跳NOT_IMPLEMENTED |
| W38 | 停同步/删来源副本，不删厂商原件或其他来源 | upload lease单独停用、仅本来源副本删除、明确reimport通过；revoke_late_worker_logout_lease_and_delete_scope、http_history_receipts_owner_isolation_and_original_write_guard、vendor_revoke_success_not_http_200 | 真厂商revoke NOT_RUN；失败unconfirmed，不能说厂商原件已处理 |

## W39—W44：真实兼容及回归

| ID | 要求 | 本轮结果 | 下一条件 |
| --- | --- | --- | --- |
| W39 | 小米真实App→安康数据字段/时间/来源对照 | REAL NOT_RUN | Band7实际App确认、开发审批、HTTPS、本人授权；不得用TEST替代 |
| W40 | 华为同样实联 | REAL NOT_RUN | 设备账号/审批/正式header；目前仅云步数，另外3主类仍需开发 |
| W41 | 真实三端同本人/同版本/统计一致 | REAL NOT_RUN，页面未接 | 原健康卡片查询适配、原生授权/读取、三端实际测试 |
| W42 | 苹果原数据通道保持 | TEST通过原bridge场景+10 adapter测试及原Python健康回归 | Apple Watch/iPhone真机NOT_RUN，不新增兼容声明 |
| W43 | 同步失败/迟到数据关联训练，不重复贡献 | 部分：training-context只读样本，明确完成/剂量不受影响；training_background_finite_real_samples_only；原训练回归 | 未自动关联正式session/晚到补链，也未测真训练链路；名称中real只指sample类型，输入是TEST |
| W44 | 正式签名/目标系统 | 新穿戴APK NOT_RUN；原0.3.2包保留，hash未变；无鸿蒙支持声明 | 原生工程完成后再原证书构建、安装Band7组合并验生命周期 |

## 操作入口与剩余清单

安装可选依赖后执行隔离测试：

```powershell
& .\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe -m pip install -r mobile_rehab/wearables/requirements.txt
& .\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe -m pytest mobile_rehab/tests -q --basetemp <新的独立测试目录>
node scripts/test-healthkit.mjs # 在ankang/route1-health-agent目录执行
```

不要用用户运行数据目录作为pytest basetemp（pytest会清该测试目录）。上线审批、最小HTTP往返、命令/一致备份/回退见[vendor_access_checklist](vendor_access_checklist.md)。外部条件与尚未开发部分分列于[known_limitations](known_limitations.md)，设备组合见[compatibility_matrix](compatibility_matrix.md)。本期成果是后台第一阶段，不把NOT_IMPLEMENTED写成只有审批不足。
