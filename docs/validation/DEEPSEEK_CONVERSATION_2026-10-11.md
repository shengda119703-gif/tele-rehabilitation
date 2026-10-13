# 0.22.0 DeepSeek普通聊天验收

2026-10-11；基于0.21.1继续修复。原有Key／连接测试正常，但用户截图两句普通聊天被健康理解层的无标签澄清模板接走。新增普通对话适配器，接入Runtime→ProductService→桌面／配对网页和直接AgentBridge会话；不是仅验证独立HTTP请求。

## 实际结果

| 检查 | 本次结果与证据 |
| --- | --- |
| 构建／类型检查 | 通过，`qa-output/conversation-build.log` |
| TS完整回归 | 453 passed，`qa-output/conversation-ts-final.log`；其中普通聊天专项12项，最后同义词拦截编译／专项再次通过 |
| 产品／模型协议 | 28 passed，`qa-output/conversation-product-tests-r2.log` |
| Qt窗口／管家／确认／来源／Key | 32 passed，99.80秒，`qa-output/conversation-qt-tests.log` |
| 手机共享接口 | 13 passed，1项Starlette弃用警告，`qa-output/conversation-mobile-tests.log` |
| 真实模型／真实后台 | 4次均通过，`qa-output/conversation-live-20261011-r1/results.json`，0.53–0.94秒；两句截图原话及“蓝鲸七号”两轮上下文；健康与家庭事实hash一致 |
| 真实离线Qt／Edge | 3条网页流程、0页面错误，`qa-output/conversation-ui-20261011-r2/results.json`；无新健康事件，刷新保留回复来源；Qt亮暗1024／1440、网页390／768共7张截图检查通过 |
| 安全扫描 | 无明显硬编码密钥／私钥；Key和模型原回答不输出到QA日志 |

前期错误保留说明：测试收集第一次用错工作目录，纠正后5项来源测试通过；第一轮网页截图等待不足，第二轮等待动画稳定后验收；关闭／重置专项最初误认为clear保存空快照，原实现实际删除存储键，修正断言后通过。原有CSS两个SHA保持`039D942D4BA40B10E020B6B96F15EF43A7DDB8A32F311375635722225B2B669D`、`9279C2F4B835ABEF827C8AA5796ED763BD5A02A2304D168D2CFE5CDC90F1C7D0`，不纳入本轮提交。

## 行为与验收入口

打开桌面“安康康复（最新版本）”→康复管家。在本机已配置Key条件下，输入“你可以做我对象吗”“你喜欢我吗”，应得到自然AI对话并显示“DeepSeek 回复”，不会新增健康事实。普通两轮追问可延续上下文。模块查询与服药／改期确认继续走已有服务，未支持操作明确未执行。Key未配置／请求失败标签表明本地来源，不能把已配置视为成功联网。

普通模型没有工具或写权限，只发送当前聊天及最多6对成功普通聊天／10k字符；旧消息、健康事实、工具资料、私密消息与失败回复不作普通上下文。宿主覆盖来源／情境；同步消息去除伪造的模型来源标记。紧急、健康事实、纠错、隐私、共享和召回保留原逻辑。生成期间关闭／重置会话，迟到结果丢弃。失败只显示受控文案，不输出供应商错误或密钥。

## 发布范围

当前改动覆盖桌面与电脑配对网页以及直接桥接会话源码。旧独立APK0.2.1未重新打包，不能据main更新声称手机安装包已更新。全模块任意写入、持续任务、通用多轮执行规划和相机／训练自动操作尚未实现。当前普通多轮聊天不等于这些能力。未发布到应用商店，不宣称临床／真人动作效果、目标手机或长期网络验收。

协议依据：[官方Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[官方Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。普通聊天固定官方端点与deepseek-flash、关闭思考、最多700输出tokens，整个请求含正文解析20秒截止；只凭真实回执显示来源。
