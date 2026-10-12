# 前端与后端接缝（2026-10-12）

## 已接通

以下旧版本段落按原验证时点读取；当前0.2.15的B02关联／saved_parts API已接，前端并行测量和统一保存展示仍待。

### B01/B02：原正式安排的独立跟练（0.2.15）

仅已启用v2的catalog增加`formal_measurement.guided_practice:{provider:'hosted-rehab-v2-guided-1',policy_version:'formal-arrangement-guided-1',base_path:'/rehab/v2/practice'}`。能力不是资格；PHONE_LOCAL与正常未启用服务均不声明。原训练卡片沿用按钮、采用确认和practice页面，独立历史沿用原记录位置，不把新源写成旧测量summary。

| 真实接口 | 载荷／回执 |
| --- | --- |
| GET `/api/rehab/v2/practice/context` | 原认证owner_scope／可信participant_id；provider与policy，source_context=GUIDED_PRACTICE:SELF_USE，arrangement_source_context=LIVE_CAMERA:SELF_USE |
| POST `/api/rehab/v2/practice` | operation_id UUID，plan_id，plan_revision，entry_key，manual_arrangement_confirmed／support_ready／companion_present三个显式bool；拒绝客户端剂量和未知字段 |
| GET `/api/rehab/v2/practice`、`/{id}` | 所属原schema2独立组记录；plan_ref／冻结settings／journey／组位置；当前execution_decision独立于已保存execution_grant |
| POST `/{id}/finish` | operation_id UUID，count=null或本组自报整数，elapsed_ms仅页面活动时间，reason=ended/completed_set/discomfort，feedback:{pain,fatigue}保持null；普通结束不是完成目标 |
| POST `/{id}/continue` | operation_id与原三个确认bool；原记录原子关联predecessor／successor；原服务UTC核对休息；仅推进独立guided_navigation_only，不改变正式next_key |
| POST `/{id}/close-journey` | operation_id；同一原组结束回执，不删除已有事实 |
| GET/POST `/{id}/feedback`、GET `/{id}/feedback/operations/{operation}` | 原独立感受契约：operation_id、expected_revision、values:{pain,fatigue,note}；COMMITTED后可补，真实冲突明确处理，同键载荷不可变 |
| POST `/{id}/visual-link` | operation_id UUID、session_id；同owner／原计划版本／动作侧别／完整settings／来源验证；关联范围journey_not_self_reported_set_total，source_epoch来自原session |

原`rehab-v2.sqlite3`同一个Storage writer，增加`rehab_v2_practice_meta(version=1)`、`rehab_v2_guided_practices`、`rehab_v2_practice_links`；初始化前一致性备份，未知版本拒绝，没有新患者数据库或全局迁移。原BackendPlans._assessment／原protocol与digest／原plan_progress／eligibility_session／feedback_block在当前事务内核对，原正式测量资格与处方不变。初始条目沿原next_key，后续只按本人明确完成的独立冻结组序列导航；当前正式反馈阻止仍保留，历史独立不适不因后来填0或换同动作新计划清除。

保存来源不是LIVE_CAMERA观察事实。记录的confirmed_count／formal_plan_contribution始终null，用户总量不与视觉量相加。visual-link提交只确认关联本身；GET saved_parts分别取practice_records、visual_facts、feedback各自权威回执，visual canonical不会替独立practice或感受确认保存。一个视觉session仅关联一个旅程；原source_epoch／快照／canonical不修改。前端旁路相机调用、权威模式事件和统一savedParts展示还未接；目前mode_segments=[]，不将server收据起止冒充无间断有效运动或观察。关联真实原引擎的验证范围见[本机记录](validation/FRONTEND_FORMAL_GUIDED_2026-10-12.md)。

`experience=legacy`不出现新开始按钮，原历史／原ID的保存核对保持，不删除原草稿或事实。正常用户服务仍v2默认关闭，本轮未启停用户服务或部署入口。

### 原v2正式训练计划：0.2.14共享页面

原 `GET /api/rehab/v2/plans` 与 `GET .../plans/{id}` 分别读取计划清单和进度；支持条件来自原 `entry_support`、`actual_input_required`、`progress.input_compatible/blocked/next_key`，只消费同本人LIVE_CAMERA:SELF_USE、schema1、rehab-explicit-plan-1、原ACTIVE计划。不拿旧 `/api/plan` 候选改写成v2计划；旧／人工／正式三个区域独立读取。

原 `POST /api/rehab/v2/sessions` 训练载荷只有 `idempotency_key,consent,submode:'training',plan_id,expected_plan_revision,entry_key,view,training_plan_confirmed`，确需陪同时才加 `companion_confirmed:true`。客户端恢复binding保存原动作／侧别／机位／完整设置，用于核对服务冻结内容，不作为新增请求字段或事实写入。创建、帧、控制、结束、commit、反馈沿原SessionAdapter和writer；同原键恢复按训练计划／条目筛选，不借用评估草稿或新计划版本结束旧训练。

原RESTING和plan_complete控制原休息／继续按钮，UI不倒计时制造组完成。返回计划时读原进度；上次感受确实阻止继续时提供原历史补填，普通结束和canonical结果保存不要求先填。原program_progress有一条固定中文原因，本轮仅精确映射显示文字；允许执行仍依完整结构化进度，不解析模糊错误推断医疗资格。

没有新增生产后端契约或放宽合格评估。真实未合格肩片仍409 `committed_observable_v2_assessment_required`，正式计划清单为空。正训练入口用隔离TEST几何合同评估形成原计划，之后撤掉几何provider、真实预录相机帧走原YOLO；不是人体评估合格证据。PHONE_LOCAL不会消费该能力。B02正式计划与独立practice关联、权威分段及savedParts仍未接，不能称“视觉准备失败后正式训练全过程已陪练化”。详见[训练验证](validation/FRONTEND_FORMAL_TRAINING_2026-10-12.md)。

### 原v2正式记录反馈：0.2.13共享页面

原测量结束区和历史详情消费原`GET /api/rehab/v2/sessions/{id}`的`feedback_revision`／`latest_feedback`，写入仍是原`POST .../{id}/feedback`，精确载荷为`idempotency_key`、`expected_revision`、`feedback:{pain,fatigue,reason,notes}`。pain／fatigue严格null或0–10整数；reason沿原枚举，notes沿原1000字限制。所属provider／owner／participant／LIVE_CAMERA:SELF_USE由当前真实能力和原session核对，不由用户填写新内部字段。

原服务只在finalized后接受感受；未提交测量的填写先保留独立小草稿，不阻止视觉事实保存，不抢先POST。实际本地写入失败提供导出，不冒充可靠草稿。原同键操作查询先于revision校验，所以丢回复恢复用同key／同payload再POST，不增加虚构operation-query路由；ACK必须核对原session／self_report／版本／内容，迟到旧GET不回退ACK后的状态。

`feedback_revision_conflict`先读最新；同值收敛并保留原被拒操作，不记为该操作ACK；实质冲突由用户明确选择，新的修改用新的键和当前revision。损坏旧草稿原字节保留，不默认覆盖；本人／来源变化停止旧队列补交。所有感受独立于canonical视觉提交、次数及正式计划贡献。这里只接已启用宿主的正式记录，不让PHONE_LOCAL获得托管API或正式资格。

最小宿主接缝：原`store_for`只串行原Storage构造，避免几个独立页面请求对同一新库交错初始化。原writer／事务／版本／未知库保护不改，不声称解决跨进程持久outbox或迁移问题。真实HTTP／SQLite和两尺寸原模型流程及失败分母见[本机反馈记录](validation/FRONTEND_FORMAL_FEEDBACK_2026-10-12.md)。正式训练视觉关联与savedParts仍待。

### B03当前消费：共享动作页面指导协调（0.2.12）

没有新增医学API或修改原cue策略。`guidance-scheduler.js`仅消费UI事件：绑定owner世代、journey/session、provider、source_context、动作／本人侧、frontend_generation；回调复核真实控制器。来源为FORMAL_CUE、LIVE_PREVIEW、GUIDED_SCRIPT、USER_OPERATION、EXECUTION_STOP、ENCOURAGEMENT；后两种优先级只接受显式事件，不从报错文字猜停练资格。生产当前已接前三种，不能声称全部专业停止事件已接齐。

正式源必须携带原cue_id、session_id、exercise_id、side、calibration_epoch、evidence_refs、valid_phases和可信remaining_ttl_ms；原GET全部往返扣除后由本地单调期限管理。当前指令取消／相位改变／超期立即清候选并调用AudioPort.cancel；既不跨时钟相减，也不延长原证据。预览没有正式TTL和canonical测量，采用独立保守UI租约；同一已收到观察的剩余租约只递减，不用250ms展示tick伪造新观测。

普通候选容量1、间隔6000ms、同句10000ms；通知issue在同绑定的进程内一次，去重集合有界。暂停／结束／离页／本人切换不持久化音频队列；恢复只接受新当前事件。原视觉／练习／反馈保存状态不由此修改。完整模式段、视觉关联、savedParts权威收敛、Qt与其他模块音频仍待。

Android原OfflineAndroid桥新增guidancePrepare／guidanceAvailable／guidanceSpeak(id,text≤500)／guidanceCancel；回调仅匹配当前id，文字不是权威测量。原MainActivity同一个前台状态与取消世代控制GuidanceAudio；仅安装好的离线中文Voice，QUEUE_FLUSH，不保留初始化前文本；onPause stop、onDestroy stop/shutdown，不增加麦克风权限或网络音频。AndroidManifest新增TTS服务可见性query不是敏感权限。原PHONE_LOCAL记录、Store和云端白名单不变；没有真机语音证据。

### 可选托管v2正式评估／只读B03、B04（0.2.11增量）

`GET /api/catalog`仅已启用宿主返回formal_measurement（provider=hosted-rehab-v2-1、原owner_scope／participant_id、LIVE_CAMERA:SELF_USE、原protocols）；默认null，不是执行资格或开关。客户端不会将PHONE_LOCAL映射成它。

| 原接口 | 当前客户端消费 |
| --- | --- |
| POST `/api/rehab/v2/sessions` | 评估精确载荷idempotency_key、consent=true、submode=assessment、exercise_id、side、view；未知回复原键同载荷重POST，由原create lookup收敛 |
| POST `/{sid}/frames` | 原image/jpeg、X-Rehab-Event-Id、X-Rehab-Seq；保比例最大宽640，单请求在途，等原processed追上accepted；不缓存离线JPEG或添加可信曝光字段 |
| POST `/{sid}/pause`、`/resume` | 原idempotency_key／expected_revision；串行控制，收到回执再读原状态；原409明确拒绝后新意图用新键，不能改旧载荷 |
| POST `/{sid}/finish` | 原reason=user_stopped；立即停客户端资源，202不是COMMITTED；原结束键持久保留 |
| GET `/{sid}`、`/commit` | owner／来源／动作侧机位／revision核对，原canonical ID／digest／计次须与最终snapshot一致；报告状态不阻止查看已提交事实 |
| GET `/api/rehab/v2/sessions` | 原所属history，补只读submode=原frozen plan模式；旧schema不写回；原记录页不混旧job和独立practice |

控制adapter保留同作用域多条小型草稿，不把它们称为事实存储。所有请求发送前复核原owner世代／binding；切本人、服务器或授权后禁止自动发送旧操作，保留原payload。legacy不允许新相机测量，已有正式记录／原键保存仍可查看和核对。

B03在原CueEvents.query已通过相位、epoch和原期限后，GET只读返回remaining_ttl_ms=min(原发出期限剩余,原source期限剩余)，不改算法或证据TTL；客户端再扣本次HTTP往返并核对证据，只播当前有效口令。全程序统一音频出口仍待，不能称本项替代U4。

0.2.11时点新UI仅正式评估；0.2.13正式反馈界面见前述。v2 plans／训练create尚未完整接线，独立原安排practice仍不冒充v2合格plan。训练视觉关联、独立保存各部分及正式贡献规则保持未完成状态。主启动与正常用户服务仍v2默认关闭。

### 托管与PHONE_LOCAL B02组序列（0.2.10，schema2）

两端新增同形`POST /api/practice/{id}/continue`及`POST /api/practice/{id}/close-journey`。继续载荷精确为`operation_id` UUID、`manual_arrangement_confirmed`／`support_ready`／`companion_present`严格bool；关闭精确为operation_id。本人／provider／source由所属宿主取得，不接客户端覆盖。原create／finish／feedback载荷不变。

托管原SQLite BEGIN IMMEDIATE；手机原Store.serial／一次change+commit同时写前组successor_id和后组。schema2新增journey_id、冻结arrangement_sequence、sequence_index、set_index、sequence_policy及关闭事实，分别为`hosted-guided-sequence-1`／`phone-guided-sequence-1`。各组自己的原id／结束载荷／自报总量，confirmed_count／formal_plan_contribution仍null。旧schema1可读，无continuation，不倒推旧组次。

只有COMMITTED＋明确completed_set＋未关闭且无原后组才提供新候选。按原target_sets／原项次序导航；不以自报数量伪造正式完成。原本人、revision、原设置／定义、原停止事实和单活动记录重查。换动作支撑／陪同默认未确认，原已采用安排不重复录入。托管自动下一动作仍经过原validate_automatic_use，正式next_key没移时真实拒绝保留；本地仍经过原LocalEngine.propose与planProgress，不改这些函数。

原休息保留null或原值，手机`owning_device_receipt_utc`／托管`owning_server_receipt_utc`；继续写操作核对REST_PENDING，页面短单调倒计时仅显示，不算运动、观察保持或跨主机时钟。下一动作不新增组间休息。

同continue key＋同载荷先返回原后组，即使后来的执行资格变化；不同载荷或再创建明确冲突。未知创建／结束先查原身份，父组结束意图优先于已创建子组；隐藏迟到子组仅暂停。close不会改原finish／次数。共享小型草稿按本人／provider／origin／原组分键，自动入口从同计划原记录恢复实际后组；不是跨模块全局outbox。手机备份验证序列、组位置、前后关联及原来源，不从备份恢复视觉或正式贡献。

### Qt B02多组导航增量（schema2）

只用原Runtime／SQLite writer，新增`practice_continue`（id为已提交前组，payload精确为operation_id UUID、arrangement_confirmed／support_ready／companion_present三个严格bool）及`practice_close_journey`（id为无已创建后组的已提交组，payload精确为operation_id）。原start／finish载荷不变。新记录冻结原validated items为arrangement_sequence、sequence_index和set_index；同journey_id，每组自己的id／finish_payload／自报范围，前后关联在同一原事务提交。不把多组累计写入旧计划贡献。

只在已提交前组明确reason=completed_set时投影continuation；按原target_sets及原项顺序算候选位置，不按次数阈值推断身体完成。当前原政策重查，支撑／必要陪同在新动作复核；原安排revision或设置改变、已有停止、另一个open练习都阻止新执行，已提交各组不回滚。普通ended／discomfort和已结束导航不提供新开始，null次数不补0。

组间rest_remaining_ms来自原记录ended_at与同一本机UTC，rest_seconds保留原值／null；不是跨主机单调时钟，也不是人体观测。客户端短倒计时只作显示，实际继续仍由所属writer核对REST_PENDING。下一动作不擅自添加上一项的组间休息。无时长仍显示准备好后由本人继续。

前组successor_id保留原子关联；同operation_id／同continue_payload返回原后组，不同载荷或再建后组明确冲突。结束未知创建时先查其原id，查不到才关闭前组导航，查到则按实际后组结束；不借“结束”再创建一次。close_payload可原键重查，不能篡改原组finish或次数。schema1历史只读兼容，不反推之前的组／未来安排。Qt暂未实现跨进程待continue／finish载荷outbox与主动租约；当前手机／托管的独立组序列契约见上节，不互换三端provider或资格。

### B01／B02／局部 B04：Qt单组基础（f3dc32e，保持兼容）

本轮接原 `ProductRehabWindow`／`Runtime`／`Storage._call`，不走网页 HTTP。独立 `guided_practices(owner,id,payload)` 仍在原 SQLite，owner 是 `qt-local-1:` 加原作用域摘要，不能读托管 owner 或 PHONE_LOCAL。context 包含原 participant_id／source_kind／usage_context、provider、policy_version；读取不存在的新表不会创建表，写入沿原事务和 commit。

| 原命令 | 实际载荷与回执 |
| --- | --- |
| `practice_prepare` | scope、原 id／revision／entry_key、request_id；返回原安排／结构化 decision／当前未结束 record |
| `practice_start` | scope／request_id；payload 精确为 operation_id UUID、plan_id、plan_revision、entry_key、arrangement_confirmed、support_ready、companion_present；后三者严格 bool |
| `practice_get` | scope、id、request_id；查询原事实并重新核对当前执行资格，不重新授予旧 grant |
| `practice_draft` | id／scope／request_id；payload 为原 operation_id、expected_revision、elapsed_ms、count；同键同载荷返回原草稿，版本冲突不覆盖 |
| `practice_finish` | id／scope／request_id；payload 为独立 operation_id、count、elapsed_ms、reason、feedback（pain／fatigue）；原键同载荷只返回原事实 |
| `practice_history` | scope／request_id；只读当前 Qt owner 的独立列表 |

政策 `qt-saved-arrangement-guided-1` 从原保存库校验本人、ACTIVE revision、原动作定义和设置；采用／支撑与原安排或档案要求的陪同未确认返回 MISSING_INPUT。既有不适、同动作同侧换安排、原测量训练最新不适和原设置变化按真实原因阻止继续；已经发生的事实仍可结束。自动安排若调用政策仍须原 `validate_automatic_use`；本次新 Qt 入口只接原人工安排，原自动开始流程未替换。

Runtime 原视觉任务／预览／相机测试尚在活动时不新开此 practice；等待资格与结束请求在原命令队列中。Qt 控制器立即暂停／结束本地节奏，不把查询返回或旧恢复意图当成新的开始。晚到开始回复在隐藏页只恢复 PAUSED；错误来源不清掉当前待核对操作。结束后不重新计时，用户输入冻结在不可变原载荷中。

不属于当前本人的安排核对不返回名称或条目设置；独立 practice 错误只回到对应请求，不调用原场景的 operation_error 展示出口，避免无关旧工作区被错误覆盖。专项通过真实 Runtime `_view` 调用监测核对，不把独立 messages 队列当作场景 views 队列。

count 留 null 或明确的 0–10000 整数；elapsed_ms 只记前台本组页面时间，不是有效保持；初次疼痛／疲劳留 null 或明确 0–10 整数。COMMITTED 仅由原 SQLite commit 后返回。正式关联／assessment／confirmed_count／formal_plan_contribution 均 null，自报范围 set_total、set_index=1；SQLite 回执时间模式段不是完整权威运动分段。草稿最多 100 个修改操作，达到边界明确拒绝而不删除；未实现跨进程待结束载荷 outbox 或多组。

原 `training_plans`／`history` 可携带 `include_guided=True`，新增 decision／独立 practices，不重写原 available 或 sessions。原桌面 snapshot 单独给 UI `guided_practice` 只读投影，原 Agent 三个工具、家庭共享、身体档案与正式进度不变。本人记录不可套旧 ROM 报告或改善曲线；查看旧记录不替换仍未结束的当前跟练控制器。

回退开关 `ANKANG_REHAB_EXPERIENCE=legacy` 只恢复原计划库的新开始路径和原 guided_available 展示，不删除新表，不禁用原历史／结束，不在运行中换执行器。Qt 尚无独立感受后补、视觉 session 关联、跨窗口主动租约及 v2 202 消费。具体证据见 [本机记录](validation/FRONTEND_QT_PRACTICE_2026-10-12.md)。

### B01 APK 本地分支：独立已有安排（0.2.8）

原local-api明确声明manual_practice_arrangements=true及manual_arrangement_entry=true。同形`/api/...`请求由原本地桥处理，不请求Python／托管服务。原Store.serial通道提供`GET /api/practice/arrangements`和`POST /api/practice/arrangements`，写入同一原档案的独立manualArrangements数组，不塞入自动plans或job，也不生成评估引用。

录入精确载荷为operation_id UUID、name（1–80字）、exercise_id、side、settings；settings精确为target_reps（1–999整数）、target_sets（1–20整数）、rest_between_sets_s（null或0–1800有限数）、target_angle_deg=null、needs_companion严格bool。数值范围仅沿用原training_plans存储输入边界，不是推荐剂量；本页面不填默认次数或组数，只照已有安排填写。动作必须来自当前原康复catalog，正式测量契约仅作为原定义指纹，不等于合格测量依据。独立记录revision=1、record_origin=manual_saved、measurement_version／assessment_ref=null；原键同载荷先查原记录，改载荷MANUAL_KEY_CONFLICT，至多250份、满时507，不删除原件。

开始复用原POST /api/practice的四个引用字段，加manual_arrangement_confirmed／support_ready／companion_present三个严格bool。实际政策phone-explicit-manual-practice-1核对原本人、当前revision、动作契约及原设置；采用／支撑／必要陪同未确认返回稳定MISSING_INPUT，不将相机READY或合格评估作为本独立分支门槛。原practice、原最近训练反馈中明确不适阻止相关执行，同动作／侧别换安排或自动计划、后编辑0不能消掉停止事实。原定义或保存快照变化停止继续执行，已有事实仍可结束保存；不伪造专业授权。

独立practices保留guidance_policy、arrangement_ref.kind=MANUAL_SAVED及当时execution_grant；formal_plan_ref／assessment_ref／visual_session_ref／confirmed_count／正式贡献null。兼容plan_ref只引用本地真实人工记录，不代表合格自动计划。提交仍用原Store.change/commit；失败无COMMITTED回执，备份在原validateBackup中验证来源、确认、原载荷与设置快照。原自动propose／planProgress／剂量与测量版本不改。

客户端小型录入草稿按原本人／provider／source_context分键，先保留原操作和载荷，未知回复锁定原内容并查询原id，刷新“核对原保存”不创建第二份。晚到读取不覆盖本轮已填输入，真实拒绝才允许修改；成功只清本操作草稿。仍不是完整跨模块outbox、专业方案编辑器、多组或Qt接线。

### B01托管独立分支：本人原人工计划（0.2.7）

`GET /api/catalog`明确声明manual_practice_arrangements=true。0.2.7增量只有托管实现；0.2.8本地独立政策见上节，两端不互换存储或资格。托管未声明manual_arrangement_entry，前端不显示本地录入表单。`GET /api/practice/arrangements`只读当前本人、REPLAY_FILE／SELF_USE、ACTIVE的原training_plans手工记录，返回原id／revision／name／items和当前独立decision。没有新计划库、处方生成或数据库迁移。

`POST /api/practice`保留自动安排原四字段；仅手工分支增加三个严格bool：manual_arrangement_confirmed、support_ready、companion_present。原动作／侧别／settings从保存库读取、校验当前定义及revision；不会接受客户端剂量或伪评估。适用政策explicit-saved-manual-practice-1返回GUIDED_PRACTICE允许／稳定code／category／message／companion_required，formal_measurement_allowed=null；未知正式资格不是ALLOWED。需要陪同取原安排和档案assisted，未确认不执行；当前本人明确采用自己的安排不宣称专业人员已授权。

事实仍写原guided_practices，同原事务／原键／查询／结束／后补感受／历史。`plan_ref`兼容指向真实手工库记录，不称合格正式计划；`arrangement_ref.kind=MANUAL_SAVED`，formal_plan_ref／assessment_ref=null。未关联视觉时visual_session_ref／confirmed_count／formal_plan_contribution保持null，模式段原因明确独立手工安排，不补观察。停止反馈按原pain>0／fatigue≥5／discomfort含义保留，同相关动作换安排或改反馈0不清除；原自动处方规则和视觉执行器未改。结束不因后来资格变化而拒绝保留事实。

只有原GET404之后的实际POST明确MISSING_INPUT／EXECUTION_BLOCK拒绝才记录startRejected；不明回复继续对原键查询，不修改在途有效载荷。APK本地手工分支已在0.2.8接入；Qt、完整多组与专业方案编辑仍待，不把两个浏览器入口当成三端B01完成。

### 任务书5／6：跟练并行接现有预览（没有新增正式测量契约）

复用原 `POST /api/live`（exercise／side／consent）、`POST /api/live/{id}/frame`（原JPEG限额与源时间语义）及 `DELETE /api/live/{id}`。托管仍是原独立worker、LIVE_CAMERA；APK原local-api／PhoneMotion CPU Worker，PHONE_LOCAL，不请求Python。原跟练绑定保持不变，预览是明确不同的读／指导子来源，不用LIVE_CAMERA冒充REPLAY_FILE自动计划的训练事实。

稳定显示仅接受当前返回的原相位、有效主值与有限客户端接收间隔，准备预算不改READY。暂停／结束取消本地采集并对原preview发DELETE，其回执不是practice／session／commit保存。每帧不重建页面，原练习资格查询也不重挂video。当前次数仅标预览／未保存，历史仍只读真实独立practice；客户端转换元数据有来源／世代／相对页面时间，仅写小型草稿，不是视觉有效时间或已提交权威模式段。v2正式测量、B02关联多段、持久测量收尾和统一B03仍待，不能靠删除live宣称完成。

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

**边界：**自动安排分支不是“无合格评估”的普遍陪练授权。三端人工安排各自政策见上节；资格未知自主草稿、关联视觉 session、多组分段仍待。独立后补感受仅托管／APK 已接，Qt 初次结束感受不代表后补实现。各端资格和来源并非同一医疗执行器。

## 其余依赖

| 接缝 | 状态 |
| --- | --- |
| B03 过期指导取消 | 预览已有 generation／有效性／语音限频／cancel；完整 cue ID／证据／epoch／TTL 调度适配待做 |
| B04 新来源历史 | 托管／APK `/capture` 分开显示原 job 与独立跟练，APK 原备份保留类型；Qt 原康复历史及统一时间线只读独立类型已接。网页统一首页与 v2 完整历史投影仍待 |
| B06 原因与真正阻止条件 | 新 practice 拒绝有固定码／对象；尚未全面覆盖原 API、空间、格式和全部业务 |

v2、原视觉、独立练习、反馈和报告的回执不能相互替代。客户端不以 HTTP abort 宣称服务器回滚，也不因技术失败换 provider。
