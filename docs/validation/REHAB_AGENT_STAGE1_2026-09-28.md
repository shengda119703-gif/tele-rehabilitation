# 康复管家第一阶段验证 · 2026-09-28

基线：`2ebc388`；应用增量版本 0.19.0。测试使用独立 Python 3.12 环境，安装项目锁定的 pytest 9.1.1、PySide6 Essentials 6.11.2、NumPy 2.2.6、OpenCV 4.12.0.88、PyYAML 6.0.3、cv2-enumerate-cameras 1.3.3。未修改已有康复环境和个人数据库。

## 实际结果

| 检查 | 实际结果 |
| --- | --- |
| 新增 Agent 逻辑、原生界面、真实 Runtime / 临时 SQLite | 27 passed |
| `scripts/check_project.py --suite core` | 1027 passed，4 subtests passed |
| `scripts/check_project.py --suite ui` | 416 passed |
| `scripts/qa_rehab_agent.py` | PASS，原界面入口、无评估、合成评估建议三张实际 Qt 截图 |
| 编译检查 | app 和本次新脚本 / 测试通过 |

两个回归组共 1443 项主测试，包含新增的 27 项，不重复相加。没有运行完整 integration 组；当前测试环境没有安装姿态模型权重或完整推理环境。

## 执行方式

在应用目录，用上述独立环境的 Python 执行：

```text
python -m pytest tests/test_rehab_agent.py tests/test_rehab_agent_ui.py tests/test_rehab_agent_runtime.py -q --tb=short --basetemp=.runtime/agent-test-02
python scripts/check_project.py --suite core --output .runtime/agent-core-results
python scripts/check_project.py --suite ui --output .runtime/agent-ui-results
python scripts/qa_rehab_agent.py
python -m compileall -q app scripts/qa_rehab_agent.py tests/test_rehab_agent.py tests/test_rehab_agent_ui.py tests/test_rehab_agent_runtime.py
```

创建 `.runtime` 父目录后执行。core / ui 分别通过 `PYTEST_ADDOPTS` 指定独立的新测试临时目录 `.runtime/agent-core-01` 和 `.runtime/agent-ui-01`。这些目录及截图被 Git 忽略。

## 覆盖与限制

验证无评估、有效依据、过期 / 中断 / 引导计时评估、跨用户 / 来源 / 情境隔离、已有计划进度、缺少反馈、确认过期、完成后不追加、否定 / 过去症状不推断为确诊、拒绝训练、未知输入、读取失败和迟到响应。
界面验证显式点击才导航、原计划确认不预勾选、训练 / 预览 / 保存失败不打开管家、换人使旧操作失效。Runtime 验证真实临时 SQLite 重开后没有新增计划或训练记录，相机 worker 始终为空。

初次安装遇 Windows 长路径错误，改用短路径临时虚拟环境完成。初次 pytest 因系统临时目录权限导致 19 个 fixture 初始化错误（8 项 UI 测试通过）；指定新目录时首次缺少父目录，创建后 27 项通过。以上都是测试环境问题，没有以跳过测试方式处理。
离屏截图初次缺少中文字体，QA 脚本加载 Windows 微软雅黑后重新渲染并目视检查。

这不是完整安康 Agent、大模型自然语言能力、真人动作精度、真实相机长期运行、手机健康数据或家庭通知验收。
