# TEST 林女士 · 器械历史验证

日期：2026-10-07，本机 Windows；正式应用仍为 0.19.2，APK 0.2.0 未重新构建。

## 范围与来源

只补齐隔离 `qa-output/test-lin-profile/` 中 TEST 林女士的两份既有健身历史，20 kg 为用户指定的 fixture 器械质量。按原动作每次起点、转折、回位时间生成 60 Hz 平滑轨迹，深蹲先下降再上升（行程 0.35 m），划船先上升再下降（行程 0.20 m）。参考长度 0.5 m / 500 px，调用现有 `mobile_rehab.barbell.analyze_track`，使用原局部二次回归计算速度、加速度及 `F=m(g+a)`、`P=Fv`。

这不是原录像的器械跟踪，不是实测肌肉力量、关节力矩或临床证据。fixture 的 `synthetic=true`、`source=SYNTHETIC / TEST`、`fixture`、轨迹来源及物理假设保留。TEST 姓名在报告标题直接显示；该上下文的数值字段采用简洁名称，不重复附加标签。普通视频、其他账号及原 40 kg 独立示例的来源说明不变，不能仅传展示参数就改变普通报告的口径。

## 数据更新

```powershell
& .\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe tools/ui-polish/test_lin_profile.py --refresh-fitness
```

工具仅接受 qa-output 严格子目录、匹配且已完成的 manifest、匹配的读取器、原 TEST 身份以及两份固定 job 的 owner/来源/动作/状态；两份报告全部验证后才写入。符号链接和解析后越界路径拒绝；其他已有器械结果、冲突备份、变化的身份或来源不覆盖。每份先保留 `result.before-load-v1.json`，再用原 JSON 原子写入器替换结果。只添加器械报告和姓名，不重写 job、原人体结果/时间/次数，不追加历史。第二次执行返回两项 `changed=false`，文件保持不变。

真实独立服务 `http://127.0.0.1:8876/` 的原配对、历史与单条结果接口确认：

| 报告 | 次数 | 负重 | 峰速 | 峰值器械外力 | 峰值器械功率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 深蹲 | 8 | 20 kg | 0.65545 m/s | 241.72086 N | 132.73045 W |
| 俯身划船 | 6 | 20 kg | 0.22097 m/s | 205.51928 N | 43.39323 W |

历史总数仍为 24。原康复、体态、健康、用药及计划没有重填。1396 / 8765 正常患者服务未重启、未更改绑定。

## 自动验证

```powershell
$env:PYTHONPATH='E:\game\health-care-software-main\rehab_codex_single_camera_v2_1;E:\game\health-care-software-main'
& .\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe -m pytest tools/ui-polish/test_test_lin_profile.py mobile_rehab/tests -q
node --test mobile_rehab/tests/test_product_ui.cjs mobile_rehab/tests/test_extensions_ui.cjs mobile_rehab/tests/test_ui_copy.cjs mobile_rehab/tests/test_unified_presentation.cjs
```

- Python 141 项通过，49.80 s；6 条警告为 Starlette/httpx 兼容弃用及 pytest 旧临时目录清理失败，没有强行删除这些目录。
- Node 42 项通过；新增断言覆盖 TEST 上下文简洁标签、原来源标记不被改写、普通/独立示例说明不丢失、姓名显示。
- 档案集成覆盖 20 kg、8/6 次、连续时间、每次器械阶段对齐、数值有限且画面内、质量翻倍时外力/功率翻倍而速度不变；补充工具的幂等、备份、原记录不变、来源/身份/写入器/已有结果/备份冲突拒绝。
- `git diff --check` 通过。

## 实际页面审查

使用 computer-use 技能的浏览器接口，从首页“我的记录与周报 → 查看全部 → 查看手机分析报告 → 健身”进入两份报告。标题、20 kg、峰值卡片、原动作次数、逐次数据和曲线正常；展开“更多数据与测量说明”检查 5 张图及物理说明。页面文本没有用户要求删去的重复字样，默认 1280×720 视口无横向溢出，控制台无 warn/error。没有改导航、CSS 或业务/API/算法。

本机截图保存在忽略目录：

- `qa-output/test-lin-load-review/squat-desktop.jpg`
- `qa-output/test-lin-load-review/row-desktop.jpg`

资料、结果、备份和截图不上传 Git。没有验证真实手机、真实器械识别准确度、真实力量、云端或不同网络；本轮网页更新未进入未重打包的 APK。电脑桌面仍使用“安康康复（最新版本）”，林女士独立档案继续用根目录 `打开林女士档案.cmd`。
