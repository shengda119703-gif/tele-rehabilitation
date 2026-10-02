# Main Integration 最小完整验收（2026-10-02）

仓库 shengda119703-gif/tele-rehabilitation。原 main=2ebc388d4160d647456487007670d89f02f80914；迁移代码基线=55a0476a4e7bc10187a809e491048f74fd58839b；包含审计记录的保留 stage1=4b2d108a3003d84c89ac42da25580017d5b1de17。

main merge commit：c5e56ea4d93393573bdbdb60b05e5243059270bd，两个父提交是原main与stage1审计提交。采用no-ff merge，0冲突，没有复制覆盖文件，也没有恢复A1/A2/A3。merge后main与stage1文件树完全一致、工作区clean；本文件及README/HANDOFF/仓库说明修正随后作为main文档提交。最终SHA见Git和交付汇报，不在提交自身内自引用。

## 本轮实际通过

1. 全项目 TypeScript typecheck 和 build:bridge。
2. Node：product-desktop + product-extensions，12/12。ProductService加载、Runtime、自报、Person Twin、药物、family/privacy/sharing、archive/history/report、通知及接口边界。
3. Python：test_product_window、test_product_navigation、test_rehab_read_tools、test_deepseek_developer、test_ankang_assistant，29/29。实际Node child，正式七主页面及notifications/settings全部可打开；AI康复管家存在；用户切换、持久化和康复运行门禁保持。模型网络测试为local fetch替身，没有真实外部调用。
4. 原康复针对性4/4：保存计划重开/版本/归档/会话不可变；SQLite v3升级备份和只读旧库；automatic plan provenance重开；按保存训练会话推进进度并保留缺失反馈。
5. 正式 `python -m app.main --data-dir qa-output/main-product-launch --screenshot qa-output/main-product-main.png`：实际ProductWindow+Runtime+Node ProductService启动，加载通过真实bridge建档的SYNTHETIC MAIN TEST，首页截图生成、中文可读、正常退出码0。不是React或仅mock窗口。截图/TEST库均ignored，不入Git。
6. 原participants/assessment/body/training/exercises/camera/runtime/storage等核心blob与原main一致；UI仍保留原康复评估、训练中心、计划、history和report入口。没有打开真实摄像头，没有进行真人测量验收。
7. 当前tracked文件排查无.env/deepseek.json/用户SQLite/node_modules/.venv/build/runtime输出；现有29个待合并历史快照常见Key/私钥特征无命中。原.example仅占位。未发现重要未commit/未push源代码；ignored依赖、cache、测试媒体与原始zip未迁入Git。

Python首次运行受沙箱对旧pytest临时目录限制而出现fixture权限错误；用workspace basetemp又遇到路径/配置权限问题。最终用全新ASCII临时目录、经工具审批执行同样测试后29项通过，不改断言或产品实现。另4项计划测试同样使用隔离临时合成库。不是把环境失败算作通过，也不是降低验收。

## 保留范围与限制

原React/iOS/Route2/3DGS进入Git仅为reference/source retention，不成为正式入口。空间主流程仍延后。外部Voice/WebRTC/HealthKit/OCR/webhook与真实设备一律“接口已迁 / 实机未验收”。SOS仍为联系信息，非自动呼叫。未扩功能或调整Agent语义/UI视觉。

本机默认.venv未建立；验证复用已有临时隔离Python环境（PySide6 6.11.2），不把该本机路径硬编码到产品。相机/姿态运行仍需Setup-Rehab声明的依赖与模型；本轮是产品启动/集成验收，不是完整硬件验收。

repo原fetch配置仅含stage1。本轮显式fetch+ls-remote main，确认其仍是2ebc388，再为本机增加main fetch mapping及tracking，避免后续误以为只fetch stage1就刷新了main。

main的后续文档提交只修正AGENTS仓库地址、README当前入口、HANDOFF当前状态及保存本验收；功能代码与保留stage1一致。main推送并核对后才创建codex/product-ui-v1，只做页面/icon/assets/theme/截图问题盘点，等待下一轮视觉要求。
