# 真实模型逐例人工复核（最终产品助手语义）

源码 `e4539938788f6c8217fa9011bba8f6d82e5d6dd5`；DeepSeek `deepseek-flash`。22 组、28 轮、42 次真实调用，全部42次返回；第一层27次中23次通过严格校验。隐私1轮为零模型调用。
真实Host读取13次：计划5、历史4、评估3、安排1；安排为空。home_rehab合成库SHA前后相同；没有执行写工具。普通会话revision不等于计划revision。
理解/route检查19组通过、3组失败。脚本将通过理解的组标为PARTIAL，全部实际能力由本表和总报告另判；没有任何候选采用闭环PASS。

| 场景ID | 第一层/route | 模型次数 | Host读取 | 实际结果及限制 |
|---|---|---:|---|---|
| chat | PASS | 4 | 无 | 两轮自然聊天，4次模型调用，无康复读取。 |
| health_public | PASS | 2 | 无 | 咖啡与睡眠公共知识直接解释，未固定要求就医；没有个人健康指标工具。 |
| lumbar_plan | PASS | 2 | 无 | 第一层rehab有效；第二层search_guidance缺arguments.query，整个工具规划被拒，未执行工具、未生成候选，返回补充信息。更后面的个体适用性、腰部模板、审核、采用、映射、保存/UI也缺失。 |
| knee_mixed | PASS | 2 | 无 | 识别混合意图；康复工具规划未形成可验证结果，明确不修改训练处方。 |
| negation | PASS | 2 | 无 | 否定胸痛与疲劳分别保留，无急症误执行；未新增健康事实。 |
| navigation | PASS | 1 | 无 | 已有ProductAgent导航返回康复页面目标，模型1次；不是浏览器/手机实际打开验收。 |
| correction | FAIL | 4 | 无 | 左膝更正响应构造from_event=to_event=0，严格校验拒绝；回退文字理解左膝，但结构化更正FAIL。 |
| action_guidance | PASS | 2 | 无 | 实际动作卡T-AXU-023公共资料进入最终LLM，回复保留开始/停止条件；不是个体训练许可。 |
| record_analysis | PASS | 1 | rehab.get_training_history | 真实SQLite训练历史本地呈现；只报告已有次数和来源，不得推断临床改善。 |
| rest_guidance | PASS | 2 | 无 | 真实休息/疲劳章节进入LLM解释，没有生成计划或写库。 |
| plan_read | PASS | 1 | rehab.get_training_plan | 真实本人SYNTHETIC/TEST计划读取并本地展示；当前不可直接执行的原因保留。 |
| assessment_read | PASS | 1 | rehab.get_recent_assessments | 真实本人评估读取并本地展示；未作临床效果判断。 |
| history_read | PASS | 1 | rehab.get_training_history | 真实训练历史本地展示，无个人回执外发。 |
| schedule_operation | FAIL | 3 | rehab.get_training_plan、rehab.get_schedule | 首轮module JSON有效；本地读取当前计划/安排后因隐私授权缺口明确阻断。取消轮生成自引用relation，校验失败并回退，未产生pending或写入。 |
| mixed_discomfort | PASS | 2 | 无 | 问题与修改一起识别；复核状态阻止任何直接计划变化。 |
| urgent | PASS | 1 | 无 | 既有急症规则先回复停止活动并寻求急救，无后续工具/计划修改。 |
| other | PASS | 1 | 无 | 股票程序请求给业务超范围说明，没有虚构程序执行。 |
| unknown_action | PASS | 1 | 无 | 明确找不到动作并要求名称/编号，没有直接升级医生。 |
| external | PASS | 1 | 无 | 预约请求明确尚未执行，没有声称联系医生或预约成功。 |
| clinical | PASS | 1 | 无 | 明确诊断/开药边界，并说明没有联系医生或预约。 |
| multiturn | FAIL | 7 | rehab.get_training_plan、rehab.get_recent_assessments、rehab.get_training_history、rehab.get_training_plan、rehab.get_training_history、rehab.get_recent_assessments | 4轮中2轮第一层被拒；器材纠正及方案状态未闭环。最后没有采用/保存，也不能据此宣称条件已持久更新。 |
| private | PASS | 0 | rehab.get_training_plan | 没有模型调用，没有Host读取；本地回退文案泛化，理解未执行并非模型PASS。 |

初次 harness 因缺少 now 参数、0次模型调用的失败保存在 live-harness-initial-20261017.json；中间 direct Runtime 运行42次调用但未传产品只读/导航端口，保存在 live-runtime-round1-20261017.json，不作为产品闭环证据。最终再次真实运行42次；整个任务实际共84次DeepSeek请求，不能只报最终42次为总费用次数。
真实模型原始请求/响应仅包含合成输入、公共资料及脱敏Host回执；认证header从不记录。实际供应商账单/金额没有查询。
