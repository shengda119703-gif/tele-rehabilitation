# 实际浏览器验证，2026-10-19

仅 SYNTHETIC / TEST。由 `tools/qa/pr13-ui.py --data-dir .runtime/SYNTHETIC_TEST_PR13_V2_BROWSER --output .runtime/v2-browser --serve --port 8786` 启动本地测试 Host。模型关闭，未启动摄像头；测试结束后已停止该服务、关闭本轮测试标签页，未关闭用户其他窗口。

通过 cua 浏览器工具在实际 in-app browser 访问 `http://127.0.0.1:8786`，并执行：

1. 输入测试配对码 `test-code`，进入 SYNTHETIC / TEST 首页。
2. 点击“我的计划”，导航到康复页面，再进入计划/拍摄页。该页面来源为 LIVE_CAMERA，隔离测试保存计划来源为 SYNTHETIC，页面显示“从一次评估开始”。不能据此声称 AI 新计划已展示，也不把来源隔离误报为生产数据丢失。
3. 回到助手，发送“你好，TEST 离线验证”；收到本地回复，界面明确显示“未配置 DeepSeek · 本地回复”。
4. 实际刷新标签页，消息及回复仍然存在。

工具已返回实际页面截图并供人工检查；没有导出浏览器截图文件，不伪造磁盘截图链接。`desktop-*.png` 是另外执行的 Qt 截图，不是浏览器截图。

未验证：真实模型、在线多轮候选、审核与采用、同一来源下的新 AI 计划显示、独立 Android/iOS/Watch、公网。首次以 `iab` 创建标签页发生工具超时，改用工具枚举返回的浏览器 ID 后成功；超时不计作产品通过或失败。
