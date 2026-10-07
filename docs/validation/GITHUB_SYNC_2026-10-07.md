# GitHub main 本机同步 · 2026-10-07

## 版本与变动

本机在 `main`，远端为 `https://github.com/shengda119703-gif/tele-rehabilitation`。用户要求检查并同步较大的主线变动。本轮从 `4a4a0b8` 快进到 `b1a6dad`，共 26 个伙伴提交、635 个差异文件。没有重新实现伙伴功能，没有改测量算法、API、权限或 UI，也没有强制覆盖本地工作区。

应用主线为 **0.19.2**：首页、康复、健康、用药、家庭五页；电脑 ProductWindow 与手机 PhoneHost 共用 ProductBackend，动作分析沿用 `/capture`。主管家、逐次用药、资料、家庭授权等变化以当前交接和伙伴报告为准，不以提交标题推定所有能力实测通过。

默认手机入口改为电脑“我的档案 → 连接我的手机”，需要电脑运行及同一可信局域网。独立 APK 源码从主线撤出，其 Git 历史保留在已获取的 `origin/archive/pre-unified-mobile-20261006`（4a4a0b8）；旧独立手机启动工具移到 `tools/mobile-standalone/`。上述主线删除均可由 Git 归档恢复，不删除用户数据或模型。

## 保留与入口

- 本地动作素材、导入 CSV / 脚本、`exercise-guides/README.md` 的 4 行原有修改与主线不冲突，全部保留，没有纳入本轮提交。
- 虚拟环境、模型、数据库、运行日志、签名密钥及旧 APK 文件保留，没有重启旧网页服务或关闭用户窗口。
- 旧 APK 仍在 `android_offline/dist/tele-rehabilitation-offline-0.1.0.apk`，21,014,212 字节；SHA256 为 `be15373555c89cba6858aab50ec477b00abc3f68d019de3516ee2e3b45996302`，与前次交付一致。保留文件不是新版主线已迁入离线能力。
- 桌面入口“安康康复（最新版本）.lnk”由 `New-RehabDesktopShortcut.ps1` 更新，指向本仓库 `Start-Rehab.ps1` 与 `.venv/Scripts/pythonw.exe`。提交后重新核对 Git 版本描述，不碰其他快捷方式。

## 本机实际验证

环境：Windows，Python 3.13.12 / PySide6 6.11.2，Node 24.14.0 / npm 11.9.0。现有依赖满足构建，未清理额外 Node 缓存，也未重新安装整个环境。

| 验证 | 实际结果 |
| --- | --- |
| `ankang/route1-health-agent`：`npm run build` | TypeScript 与本机 bridge 构建成功 |
| 当前 `tests/test_product*.py` 加 `test_five_page_experience.py`、`test_daily_store.py` | 148 通过，2 跳过，197.47 秒 |
| `pytest -q mobile_rehab/tests` | 123 通过，43.85 秒 |
| `node --test tests/product-desktop.test.cjs tests/product-extensions.test.cjs` | 16 通过 |
| 手机三个 Node 页面测试文件 | 31 通过 |
| 独立目录 `app.main --screenshot` 启动 | 退出码 0，离屏首页截图产生并检查 |

Python 桌面回归使用离屏 Qt、临时 TEST 档案和被动测量 Runtime，真实 Node 桥接参与读写；2 项跳过是需要 Windows 原生窗口系统的计划弹窗模态锁，不把离屏按钮测试称为该锁已验证。手机回归包含新共享档案接口；原 Starlette TestClient 弃用警告保留。

独立启动使用 `.runtime/github-sync-20261007/` 数据目录，禁用外部模型与语音，截图在该忽略目录。只检查正式入口能启动及首页五页导航，不是全产品视觉审查、真人摄像头验收或联网模型验收；截图时安排区域仍在读取，不能以此断言完整数据加载已通过。

本轮没有红米实机、真实家庭关系、真实摄像头 / 双摄、真人语音 / OCR 准确度或互联网联机验收。没有主动迁移正常患者库；首次启动正式版本的数据兼容与设备操作仍应观察。伙伴报告中的旧测试计数、截图及环境不作为本机新增结果。
