# 后端梳理文档核对记录 · 2026-10-11

## 范围和基准

用户要求：整理全部后端功能、技术实现及模块间传递的信息，用于思考准确性和可靠性优化。

交付文件：[后端功能、算法与数据流梳理](../BACKEND_ARCHITECTURE_AND_OPTIMIZATION.md)。本轮仅更新该文档、本核对记录和 HANDOFF，不实施算法修改，不动 UI、APK、模型、数据库或运行服务。

核对开始时 HEAD 为 `146392996ed3c3bef360db52b02690df7d930a7c`，origin 为 `https://github.com/shengda119703-gif/tele-rehabilitation.git`。电脑／托管产品版本 0.20.0，既有 APK 0.2.1，不因文档更新改版本。

此前后端任务留下尚未提交的代码／测试／报告；动作图片、导入脚本、CSV、任务书等也仍在工作区。本文区分已提交第一阶段和后续工作区状态，不把这些未提交文件捎带提交。

## 本轮查阅和补充

查阅当前交接、原后端梳理及实施报告，核对新增 v2 的 protocols、evidence、engine、rounds、cues、temporal、compatibility、sessions、service、api 和 server 宿主适配，以及工作区 progress、离线 features／models／训练配置和实验摘要。

文档保留原三端、健康／管家／调度／家庭／安全／存储等梳理，新增功能依赖索引、v2 正式事实流、单指标证据契约、时钟含义、未提交计划贡献扩展、实际训练链／结果以及八项优先实验。明确区分：源码存在、已验证、用户端接通；观测／目标／质量／计划完成；工程默认与专业阈值；确定性测试与真人准确度。

原产品语义缺陷沿用有日期的黑箱证据，没有宣称本轮修复。原 4–15 节的电脑／APK 差异仍适用原路径，新增 v2 不代表旧引擎已经替换。

## 工作区代码的核对指纹

以下为文档核对时的 SHA256，指向未提交的后续代码，不是声称 GitHub 已含这些版本：

| 文件 | SHA256 |
| --- | --- |
| `mobile_rehab/rehab_v2/api.py` | `eb45698303411399aa7fe483c4a9352bfc1490b1530956c9f7151820c722bd35` |
| `mobile_rehab/rehab_v2/service.py` | `e17c63bc1a4a2fd08c49ab660c870b9028004c3c8aa0aaffe4bd190e95062f36` |
| `mobile_rehab/server.py` | `00186c005f193db4dbfea2762c4464cfcfff8b8b461bf3f548b3c7d60711e953` |
| `app/rehab_v2/sessions.py`，位于应用目录 | `f749468084b981315c5f718dd1ada7a0a9047d8129f1921c3b134a1c7db3b7f7` |
| `app/rehab_v2/progress.py`，位于应用目录 | `5c4734a8ed64401edec4012cc3f8545cf1bc2815a9024431cb76145ab3d85dff` |
| `tests/rehab_backend/test_api.py` | `e02174637fdefe541571f99db185bcc7a58342156276919bd6013ca267cd0b62` |
| `tests/rehab_backend/test_progress.py` | `d3f003b4c37acd2d35de0d321afd08b1136dc0c0f9d1f0c62af9da679ea6d12f` |

## 读取到的后端验证，不是本轮重跑全部回归

接续读取此前已启动的 `tools/rehab_ml/verify_all.py` 执行会话，进程 exit 0。实际证据目录为 `.runtime/rehab_ml/run/verification-6150da86/`，产物仍在忽略目录，没有打包私人视频或数据库。

| 命令／日志 | 实际结果 | 日志 SHA256 |
| --- | --- | --- |
| `unittest discover -s tests/rehab_backend -p test_*.py -v`；`new_backend.txt` | 61 项通过 | `02fe8e5c330f791511b50673a1587cdd6fdd0f04f950d0c3c8fd65433e336d93` |
| `unittest discover -s rehab_codex_single_camera_v2_1/tests -p test_app_rehab.py -v`；`legacy_rehab.txt` | 12 项通过 | `43cd5fcf219c8cff3046012833c594f8b58492685a7293cf1d844fa482787dbd` |
| `pytest mobile_rehab/tests/test_mobile.py -q -p no:cacheprovider --basetemp <隔离目录>`；`legacy_mobile.txt` | 19 项通过；1 条既有 httpx 弃用 warning | `1dca7ffd764f5a03cac3654f0afe8940a48e263ba033895ae616c4d14deed3b5` |
| `cli.py verify-scope --baseline reports/rehab_backend/protected_files.json`；`scope.txt` | 1308 文件一致、changes 为空 | `a15faa5e4aac0311ddf21d3d9d44e1c1171d5feb555a476ddf393b1ed8d9901c` |

对应工作区 `regression.json` SHA256 为 `f3a2c91127268188ea3fe5c4b50c1bf92bd7afed3c24004670ba24ed9693292f`。该报告在本轮不提交；本记录保留实测范围与指纹，避免 GitHub 上的第一阶段 49 项报告被误读为后续 61 项结果。

之前一次 `verification-308e358b` 的 60 项运行有 1 项失败：没有显式 submode 的崩溃检查夹具被冻结为 training，重建时缺组次而拒绝。后续工作区加入创建前显式 mode 校验，并将实际评估夹具设为 assessment，末次 61 项通过。旧失败报告仍保留在工作区 `regression_before_mode_fix.json`，没有把失败结果改成通过。

## 文档校验与未测范围

交付前实际检查三个文档：125 个本地链接均存在、28 个连续表格块列数一致、代码块闭合；四份后端日志 hash 与报告一致，Git 空白检查通过。未加入连接码、密钥、真实档案标识、私人录像或患者库。暂存清单限定为三个文档。提交后核对远端 SHA，并更新原桌面快捷方式的版本描述，不启动／关闭原窗口。

本轮没有新跑真人录像、临床角度／计次标注、器械参考仪器、手机实机、公网、设备、全业务或全部 UI 回归。工作区测试包含确定性规则输入及测试注入姿态，不构成真人准确率。TCN 仍关闭；RGB 质量训练、深蹲宿主计划、明确节奏处方、硬挂起隔离和完整故障恢复仍未完成。
