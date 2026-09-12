# 0.18.1 下一步动作指导本机验收

日期：2026-09-13
环境：当前 Windows 工作区的项目独立环境

## 执行结果

执行：

```text
.venv/Scripts/python.exe scripts/check_project.py --suite all --timeout 240 --output .runtime/checks/next-action-guidance-v0181-final
```

结果：13 个批次全部通过，共 1645 项主测试和 4 项子测试。

| 批次 | 结果 |
| --- | ---: |
| core | 1012 passed，4 subtests passed |
| ui | 406 passed |
| test_app_joint_expansion_flow | 21 passed |
| test_app_landmarks | 179 passed |
| test_app_runtime_integration | 3 passed |
| test_app_source_integration | 1 passed |
| test_app_vision_integration | 2 passed |
| test_camera_test_integration | 3 passed |
| test_dual_runtime_integration | 5 passed |
| test_dual_vision_integration | 1 passed |
| test_guided_runtime_integration | 4 passed |
| test_model_paths_integration | 6 passed |
| test_quiet_runtime_integration | 2 passed |

证据目录：`rehab_codex_single_camera_v2_1/.runtime/checks/next-action-guidance-v0181-final`

## 覆盖结论

- 准备姿势确认后，动作卡推进到“下一步：开始动作”。
- 出程未取得完成证据时不提前提示回位。
- 回程或目标完成证据成立后，动作卡切到回位。
- 完整回位后提示下一次动作。
- 坐站在坐位准备后提示起立，在站位确认后提示回坐。
- 短暂缺测不使用无效帧推进提示，严重异常仍覆盖普通提示。
- 53 个动作的普通与大字显示继续使用同一动作文字和阶段素材路径。

## 未覆盖

本轮没有用真人和真实摄像头验证提示切换的主观节奏，也没有重新验证关节角精度。现场仍需选取肩外展、坐站和一个手部动作，核对“准备—动作—回位—下一次”是否符合使用者理解。
