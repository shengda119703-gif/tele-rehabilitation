# 康复后端 P0 开工清单

采集时间：2026-10-10T18:11:32.613716+00:00；基准：`b6d22fc392915738401fe6e14d9cc32b877a5acc`。

保护 1308 个文件（包含整个 android_offline 的忽略产物）；完整 hash、原有未提交改动和环境见 `rehab_backend/protected_files.json`。

## 范围

只新增 app/rehab_v2、康复会话宿主、tools/rehab_ml、configs/rehab_ml 和后端测试。旧域对象、PoseAnalyzer、GuidancePolicy、TrainingEngine、Storage 和所有界面冻结；新协议通过独立版本入口复用原域对象与分析器。旧 live 仍只预览。

## 当前入口与复用

- app/runtime.py：桌面原采集及训练；本轮不改入口和 UI。
- mobile_rehab/server.py、live.py：既有认证、隔离推理；新会话须 opt-in，不能改旧 live 语义。
- app/quality.py：原图像素、逐点 EMA、分指标测量；肩主角度只依赖肩和肘。
- app/rehab.py、training.py：旧动作计数与训练；新协议解决坐站首帧、遮挡转折和计数/质量分离。
- app/storage.py：单线程 SQLite v4；任何新表使用同一 owning thread，隔离库验收。
- app/guidance.py：复用原下一步提示策略；另加有时效的结构化事件。

## 基线与机器

旧康复/坐站后端回放 exit=0，0.257 秒，日志 `E:\game\health-care-software-main\.runtime\rehab_ml\run\inventory\legacy-replay.txt`，SHA256 `37342bd308d42319c7d0b460402f5a8de31756dc2465a5ac1c7d15fdc075655b`。这是确定性回归，不是真人准确度。

环境与依赖：

```json
{
  "python": "3.13.12 (tags/v3.13.12:1cbe481, Feb  3 2026, 18:22:25) [MSC v.1944 64 bit (AMD64)]",
  "executable": "E:\\game\\health-care-software-main\\rehab_codex_single_camera_v2_1\\.venv\\Scripts\\python.exe",
  "platform": "Windows-11-10.0.22631-SP0",
  "dependencies": {
    "numpy": "2.2.6",
    "torch": "2.9.1",
    "PySide6": null,
    "requests": "2.34.2",
    "PyYAML": "6.0.3",
    "ultralytics": "8.3.199"
  },
  "roots": {
    "data": "E:\\game\\health-care-software-main\\.runtime\\rehab_ml\\data",
    "run": "E:\\game\\health-care-software-main\\.runtime\\rehab_ml\\run",
    "model": "E:\\game\\health-care-software-main\\.runtime\\rehab_ml\\model"
  },
  "disk": {
    "C:/": {
      "total": 322122543104,
      "used": 321836003328,
      "free": 286539776
    },
    "D:/": {
      "total": 701020237824,
      "used": 684914987008,
      "free": 16105250816
    },
    "E:/": {
      "total": 1024191361024,
      "used": 1011400388608,
      "free": 12790972416
    }
  },
  "git_commit": "b6d22fc392915738401fe6e14d9cc32b877a5acc"
}
```
