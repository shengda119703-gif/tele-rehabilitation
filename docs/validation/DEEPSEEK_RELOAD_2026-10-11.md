# DeepSeek配置后后台重启修复验收

日期：2026-10-11；产品0.21.1。

用户截图中的WinError 50发生在Key保存后的后台重新加载。本机私有配置已存在且能够读取，没有输出密钥。以Start-Process、pythonw、stdout/stderr日志重定向和隔离临时TEST数据执行三轮后台启动／profile.list／关闭：修复前首轮通过，第二、三轮返回同一WinError 50；无日志重定向的对照三轮通过。Node子进程显式stderr=DEVNULL后同一重定向用例三轮全部通过，避免继承桌面日志句柄。不是供应商鉴权报错。

回归：`tests/test_deepseek_developer.py`实际3 passed，涵盖密钥遮罩／持久化／清除、适配器配置优先级和固定端点、Windows重定向pythonw三次真实桥接重启。新增回归不调用模型。现场忽略日志`qa-output/key-reload-probe.json`记录三轮成功；开发失败结果曾在同一路径打印，未宣称失败日志仍被保留。

真实连接：使用当前已有适配器和本机私有Key，只发送连接测试及records为空、SYNTHETIC/TEST标记，返回非空文本。输出仅`LIVE_REQUEST_OK; nonempty=true`，不输出密钥或模型原文。证明当前请求连通，不证明通用闲聊、多轮规划、所有工具流程或临床效果。普通聊天仍受既有运行时路由约束，不能认为配置Key后所有输入自动改走模型。

未修改原用户数据、相机、模型权重或两份既有CSS；不关闭旧窗口。密钥文件位于仓库外，不提交。
