# GitHub 同步与本机验证 2026年10月11日

本机已同步 0.20.0 源码，构建、原业务回归及桌面启动通过。照护调度的自然语言黑箱仍有 10 个失败项；本次同步不等于这些缺陷已经修复。

## 同步范围

`main` 从 `6d09457822894dd071614d9849847bc1b37c4752` 快进到 `a1e7daaad9544d3c07b254c5ef49541a60effe9a`，包含伙伴 `ty060211` 于 10 月 10 日提交的照护调度后端、医学依据和黑箱报告。没有产生业务合并冲突，也没有修改正式 UI 或医疗规则。

更新前后的 279 个本地未提交文件 SHA256 一致；保留动作图片、`exercise-guides/README.md`、图片导入脚本与报告，不将其纳入本次提交。模型、数据库、签名、录像、环境及构建产物继续遵循忽略规则。没有关闭用户旧窗口或重启已有服务，所有新增验证只使用隔离 TEST／临时目录。

桌面快捷方式 `安康康复（最新版本）.lnk` 使用当前仓库的 `Start-Rehab.ps1` 和 `rehab_codex_single_camera_v2_1/.venv/Scripts/pythonw.exe`。应用版本为 0.20.0；提交验证文档后再次刷新快捷方式的 Git 版本描述。五页导航仍为首页、康复、健康、用药、家庭，管家从首页进入。

## 本机环境与实际结果

Windows，Python 3.13.12，PySide6 6.11.2，OpenCV 4.12.0，Node 24.14.0。使用应用目录原有 `.venv`，没有重装环境或下载新模型。本机没有 `.venv-ui-polish`；不能直接照搬伙伴的环境及旧测试计数。

| 检查 | 本次结果 |
| --- | --- |
| `npm run build` | 类型检查与桥接构建通过 |
| `npm test` | 431 通过，0 失败 |
| `npm run test:product` | 16 通过，0 失败 |
| `npm run security:check` | 通过既有凭据扫描，不代表完整安全审计 |
| Python 指定回归集 | 324 通过，0 跳过；1 条既有 Starlette／httpx 弃用警告 |
| Android Node 回归首次运行 | 65 通过，1 失败：旧缓存 `PhoneStore` 缺少新适配器调用的 `backupData` |
| 刷新资源后 Android Node 回归 | 66 通过，0 失败，包含 12 项新增调度测试 |
| 真实 HTTP 调度黑箱 | 完整 69 项，59 通过、10 失败；退出码 1，未更改预期 |
| 正式 `app.main` 启动 | 独立临时目录、禁用模型与语音、离屏启动截图成功 |
| Qt 加载后截图检查 | 隔离 TEST 档案，1440×940、DPR 1；首页、管家、康复工作区可显示，无横向溢出 |

Android 失败来自 `lin-profile.test.cjs` 读取旧 `build/assets/local/store.js`，同时加载更新后的 `web/local-api.js`。用原 `prepare_assets.py` 和 `bundle_product.cjs` 刷新已忽略的资源后重跑通过；没有修改测试、源码规则或个人数据。原首次日志保留。生成目录经路径核对位于仓库的 `android_offline/build/assets/`。

## 未解决的问题和安装包状态

黑箱复现 BB-040、041、049、050、051、054 至 058：具名第三人／朋友误作本人、冲突或含糊时间没有澄清、新增剂量信息被丢弃。明确参数的确认、幂等、部分失败、事实变更保护和重开路径在本次范围内通过，自由聊天调度不能视为验收通过。详见 [伙伴黑箱报告](ANKANG_CARE_BLACKBOX_2026-10-10.md)。

本次完整黑箱没有出现数据库损坏，但数据仅放本机临时目录，没有完成原同步目录异常的根因调查。前端确认卡片仍待接入，本次没有实现它；没有验证真人动作准确度、真实摄像头／麦克风、联网模型、跨网家庭服务或手机实机性能。

安装包 `android_offline/dist/tele-rehabilitation-mobile-0.2.1.apk` 未重打包，SHA256 同步前后均为 `36EF93EE0E9E8E2269EF60FDEE1E28D60B03585697FDEAAA3AD2912AA0F6D861`。刷新构建资源不等于已发布新 APK。

## 执行命令与证据

在 Agent 目录执行 `npm run build`、`npm test`、`npm run test:product` 和 `npm run security:check`。Python 回归在应用目录使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、仓库根 `PYTHONPATH`、`QT_QPA_PLATFORM=offscreen`：

```powershell
& '.venv/Scripts/python.exe' -m pytest -p no:cacheprovider tests/test_automatic_plans.py tests/test_automatic_runtime.py tests/test_rehab_read_tools.py tests/test_product_assistant.py tests/test_product_recovery.py tests/test_product_phone_host.py tests/test_product_completion.py tests/test_product_module_paths.py tests/test_daily_store.py tests/test_care_host.py ../mobile_rehab/tests -q
```

在仓库根、`PYTHONPATH` 包含仓库根与应用目录时执行：

```powershell
& 'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe' android_offline/tools/prepare_assets.py
node android_offline/tools/bundle_product.cjs
node --test android_offline/tests/*.test.cjs
& 'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe' tools/qa/ankang_care_blackbox.py --output qa-output/github-sync-20261011/care-blackbox
& 'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe' rehab_codex_single_camera_v2_1/tools/validate_product_visual.py --width 1440 --height 940 --theme light --phase fluent-v1 --output-root qa-output/github-sync-20261011/qt-ready
```

原始日志和截图在已忽略的 `qa-output/github-sync-20261011/`：`agent-tests.log`、`product-tests.log`、`python-tests.log`、`android-tests.log`、`android-tests-after-assets.log`、`care-blackbox/results.json`、`desktop-smoke.log`、`desktop-home.png` 与 `qt-ready/`。黑箱记录 `completed=true`、`fatalError=null`；测试服务由脚本自行停止。截图已实际查看，不能用本轮启动检查代替完整实机或临床验证。

本轮仅提交交接与本机验证文档。使用 `pages:write-page` 技能核对本地文档内容，不创建或修改云端 Page。
