# 康复助手工作流接口 V1

状态：开发分支设计与实现，尚未合并 main、尚未部署。

## 1. 总链路

```
用户输入
  -> LLM #1 通用语义理解
  -> SemanticTurn / Johnson
  -> route=rehab
  -> LLM #2 工具规划
  -> Host 执行已注册工具
       ├─ 本人当前计划
       ├─ 本人训练历史
       ├─ 本人近期评估
       ├─ 动作知识库
       ├─ 康复指导资料
       └─ 确定性计划算法（条件满足时）
  -> LLM #3 候选康复方案 JSON
  -> 程序验证器
  -> validated / needs_review / rejected
  -> 当前版本只生成候选计划，不写入用户计划
```

LLM 不直接访问数据库，也没有通过输出工具名取得权限。LLM 只提出工具调用；Host 验证工具名、参数、本人范围并实际执行。

## 2. LLM #2：工具规划接口

输出：

```json
{
  "version": 1,
  "calls": [
    {
      "name": "rehab.get_training_plan",
      "arguments": {},
      "reason": "需要知道当前计划"
    },
    {
      "name": "rehab.search_knowledge",
      "arguments": {"query": "膝关节相关训练"},
      "reason": "需要查找存在的训练动作"
    },
    {
      "name": "rehab.search_guidance",
      "arguments": {"query": "剂量和进阶"},
      "reason": "需要训练原则"
    }
  ],
  "uncertainties": []
}
```

允许工具：

- `rehab.get_training_plan`
- `rehab.get_training_history`
- `rehab.get_recent_assessments`
- `rehab.search_knowledge`
- `rehab.search_guidance`
- `rehab.run_plan_algorithm`

工具规划阶段不诊断、不生成方案、不修改计划。

## 3. 工具结果

### 个人数据

由 Host 根据 participantId 读取：

- 当前康复计划
- 训练历史
- 近期评估

participantId 不允许由模型提供。

### 动作知识库

来自 `rehab/catalogue.ts`。

动作必须使用真实、完整的 training card。至少包括：

- action ID
- name
- region
- level
- equipment
- startConditions
- stopConditions
- sourceDose

模型不能创造动作 ID。

### 康复指导资料

来自 `rehab/guidance.ts`，用于：

- 训练原则
- 剂量与进阶
- 器材与支撑
- 单人执行边界
- 评估与训练区别

### 算法

来自 `rehab/localPlan()`。

算法是确定性的程序逻辑，不由 LLM 自己计算。LLM 只能提出算法输入；Host 执行算法并把真实结果返回。

## 4. LLM #3：候选方案接口

输出：

```json
{
  "version": 1,
  "goal": "膝部训练调整",
  "summary": "根据当前已读取资料形成候选训练调整。",
  "algorithm_input": {
    "goal": "膝部训练调整",
    "region": "膝",
    "equipment": ["无轮稳固椅"],
    "restrictions": [],
    "level": 0,
    "screening_confirmed": false
  },
  "candidate_actions": [
    {
      "exercise_id": "T-LOW-003",
      "reason": "动作库中存在且与当前输入匹配"
    }
  ],
  "doctor_review_required": true,
  "doctor_review_reasons": ["screening尚未确认"],
  "uncertainties": []
}
```

### 强约束

1. `candidate_actions[].exercise_id` 必须存在于动作知识库，且必须是完整 training card。
2. assessment 卡不能当训练动作。
3. dose 如果出现，只能逐字来自该动作的 `sourceDose`。
4. 不允许模型自行创造次数、组数、负重、保持时间。
5. `screening_confirmed=true` 必须有工具结果或用户明确资料支持。
6. 有个人限制、未知术后限制、重要信息缺失等情况时，应进入 `needs_review`。
7. `doctor_review_required` 不是“所有康复问题都就医”，而是当前信息或规则要求专业核实。
8. 当前 V1 不包含写入计划的操作字段。

## 5. 程序验证器

验证不是验证“JSON 格式”这么简单，而是验证 LLM 产生的候选方案是否能被已有数据和规则支持。

检查：

- JSON 结构
- 动作 ID 是否真实存在
- 是否为完整 training card
- 是否包含开始/停止条件
- dose 是否来自动作卡
- 个体限制是否存在
- screening 是否确认
- LLM 候选动作是否属于算法返回的候选集合
- 算法是否 `no_match`
- 算法是否要求进一步核对
- LLM 是否声明需要医生核实

结果：

- `passed`：结构和已知约束均通过
- `needs_review`：可以保留为候选，但不能自动采用
- `rejected`：方案与知识库/算法结果冲突，不能使用

## 6. 当前明确不做

- 不写入用户当前训练计划
- 不自动删除/修改动作
- 不执行程序模块操作
- 不把候选方案直接视为个人处方
- 不由 LLM 自己创造不存在的动作或剂量
- 不因为 route=rehab 自动推荐线下就医

后续再增加：

```
validated candidate
  -> 用户确认
  -> program_operation
  -> 写入当前计划
  -> App 展示待做动作
```

## 7. 代码入口

核心实现：

- `ankang/route1-health-agent/src/rehab/workflow.ts`
- `ankang/route1-health-agent/src/runtime/semanticExecution.ts`
- `ankang/route1-health-agent/src/rehab/assistant.ts`
- `ankang/route1-health-agent/src/rehab/catalogue.ts`
- `ankang/route1-health-agent/src/rehab/guidance.ts`
- `ankang/route1-health-agent/src/rehab/planRules.ts`

本接口 V1 的目的不是一次完成所有临床决策，而是先把“语义理解 → 工具调用 → 确定性算法 → 候选方案 → 程序验证”的软件链路固定下来，为下一阶段计划写回和程序操作提供稳定接口。
