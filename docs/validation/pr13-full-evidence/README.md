# PR13 本轮证据与复现

日期：2026-10-17；初始基线 `c3a5aaff`，远端只读审计冻结 `8667766`，远端修复代码 `59c5226`（原本地aa8cf7b/e453993，同一Git tree）。默认开关关闭；保持 Draft，不合并 main、不部署。

- `test-summary.json`：精确命令、退出码、结果、原日志 SHA256、失败测试 ID、节点统计。套件有重叠，不将其相加为总通过率。
- `baseline-typecheck.txt` / `baseline-ts-tests.txt`：修改前真实编译失败，未删除。
- `semantic-audit.md` / `rehab-audit.md` / `host-ui-audit.md`：源码调用链、初始缺口及定向复测。
- `host-ui-focused-junit.xml`：真实隔离 SQLite 64 项；`host-ui-final-evidence.md` 说明初始11失败/5通过、修复及复测。
- `mock-20261017.json`：21组、32次 Mock 模型调用，个人 Host 也是 Mock；不能作为真实Host验收。
- `live-20261017.json` / `live-review.md`：最终产品式只读助手，22组/28轮/42次真实DeepSeek、13次真实Python SQLite读取。第一层23/27有效，隐私1轮零调用；3组理解失败，未写计划。
- `live-harness-initial-20261017.json`：测试器遗漏必需时间参数，0次模型调用；不能算产品失败/通过。
- `live-runtime-round1-20261017.json`：中间direct Runtime未安装产品只读/导航端口的42次真实调用，保留但不算产品助手验收。整个任务共84次真实供应商调用；账单金额未核验。
- `y-failures.txt` / `q-failures.txt` / `m-failures.txt`：保留1项桥接、18项桌面产品、4项手机视觉测试失败；详情及归因见 `broad-regression-review.md`。
- `ui/`：真实Qt offscreen渲染与6页离线冒烟、4张截图；浏览器工具没有可用surface，网页UI仍UNVERIFIED。

所有个人记录均由临时 SYNTHETIC/TEST 构造器生成，数据库与私密配置不提交。模型认证头不记入trace，供应商异常只记安全类别。运行时使用静默stdin凭据，代码/报告不包含凭据值。

## 本机复现

在仓库根执行；使用独立Python环境，不复用患者数据目录：

```powershell
npm.cmd ci --prefix ankang/route1-health-agent --ignore-scripts --no-audit --no-fund
npm.cmd run ci --prefix ankang/route1-health-agent
$pr13Python = '<隔离环境>/Scripts/python.exe'
$env:PYTHONPATH = 'rehab_codex_single_camera_v2_1'
$env:PYTHONUTF8 = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
& $pr13Python -m pytest rehab_codex_single_camera_v2_1/tests/test_rehab_operation_tools.py rehab_codex_single_camera_v2_1/tests/test_daily_store.py rehab_codex_single_camera_v2_1/tests/test_care_host.py rehab_codex_single_camera_v2_1/tests/test_saved_training_plans.py -q
node tools/qa/pr13-full-live.cjs $pr13Python '<全新隔离目录>/SYNTHETIC_TEST_PR13/live-new' '<输出目录>/live.json'
# runner显示静默stdin提示后才输入凭据；不要把凭据放到命令行或文件。
& $pr13Python tools/qa/pr13-ui.py --data-dir '<隔离目录>/SYNTHETIC_TEST_PR13/ui-new' --output '<输出目录>/ui'
```

Python环境本轮为3.11.9，Qt6.11.2；使用pytest9.1.1、numpy2.2.6、opencv4.12.0.88、PyYAML6.0.3、fastapi0.142.2、SQLAlchemy2.0.54、uvicorn0.54.0、httpx0.28.1、Pillow11.3.0等隔离依赖。未安装YOLO/torch及姿态权重，相关真实视觉能力没有通过验收。Node24.20.0/npm11.19.0，TS依赖按既有package-lock安装，未增加项目依赖。

Android `prepare_assets.py` 在缺少已登记权重时真实失败；生成的其余资源和TEST fixture足够运行85项JS测试，但不能称为APK构建成功。桌面快捷方式及已安装版本未切换：本轮是隔离审计分支，没有发布版本。
