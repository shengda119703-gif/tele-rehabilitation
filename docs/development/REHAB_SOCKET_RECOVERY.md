# 康复v2：真实HTTP连接丢失与独立服务重启

日期：2026-10-11；实施基准`1fd6806666d4f41cb6b235d4f99d95154b7611b5`。对应后端任务书6.1／6.4–6.6、7、C14–C19／C23及P7。本次只增加隔离后端工具、测试与证据，不修改生产服务、动作算法、权重、前端、整个Android或正常用户库。

## 1. 为什么增加这一层

此前ASGITransport验证在同进程调用原路由，SQLite退出工具证明检查点恢复，WindowsJob工具证明所属进程随宿主退出。但没有实际TCP连接、原宿主签名cookie和第二个独立HTTP服务器。测试通过不能跨层宣称网络重连已验收。

[socket_recovery_audit.py](../../tools/rehab_ml/socket_recovery_audit.py)启动真正的`mobile_rehab.server.create_app(..., rehab_v2=True)`和Uvicorn。子进程先绑定127.0.0.1、端口0，再初始化隔离库；端口由OS选择，不占用8765／1396，不开放LAN／公网。监督程序准确持有直接base解释器句柄、保留本机venv初始化，不通过旧PID重新查杀。

## 2. 实际信息链与响应丢失

```text
实际HTTP配对 → 原签名cookie／owner → 隔离已有评估／原自动计划
   ↓
原create／SQL幂等记录 → TEST响应门（服务已返回，HTTP尚未返回）
   ↓                    ↓
查询／同key重试 ← 客户端真实TCP RST，未读取响应
   ↓
暂停／恢复 → JPEG／原YOLO → 实际阶段统计／逐帧检查点
   ↓
原finish接收 → 后台最终事务／canonical／唯一贡献
   ↓
TEST响应门 → 客户端TCP RST → 查询／同key／别名key找回同一canonical
   ↓
独立null反馈 → 原所属报告进程 → 原训练事实保持
   ↓
再建评估／真实JPEG检查点 → 实际宿主强制退出／准确worker句柄退出
   ↓
同隔离数据目录启动第二个真实服务器 → 原recover_unfinished
   ↓
旧cookie重新连接新临时端口 → 原finalized不变／draft变interrupted
```

响应门只在该TEST子进程实例包裹原`create`和`request_finish`，不添加公开端点或弱化鉴权。门标记证明原创建已落库或原最终canonical可读；客户端在门尚未放行时关闭自己的实际socket，设置零linger产生RST，未调用recv。之后才释放门；这不是修改客户端程序，也不是只丢弃一个已经收到的JSON。

真实配对、cookie验签、原X-Rehab-Client保护、owner隔离、原保存计划解析和原v2路由均未替换。隔离既有评估为明确TEST fixture，沿用原集成测试的几何值，不是专业参考。`Jobs.runner`为该测试实例的空钩子，未调用录像作业或非康复接口；没有启动Node健康bridge。

## 3. 输入与检查

原320×240白色JPEG分别进入训练会话和重启前的新评估，由原所属YOLO处理；报告也由原所属进程构建。图像没有人物，确认次必须为0；既有TEST计划不因白图变成完成。

| 阶段 | 主要检查 |
| --- | --- |
| 创建响应丢失 | 同key重试同session；改载荷409；没有第二份创建 |
| 控制／真实输入 | 原暂停恢复revision；原JPEG已处理、推理阶段统计；无人0次 |
| 结束响应丢失 | 查询／同key／别名key同canonical；改载荷409、晚帧拒绝 |
| 反馈／报告 | null不补零、反馈只写一次；派生报告ready、原视觉事实保持 |
| 强制退出 | 原pose和report句柄确实存活；宿主退出后两child自动退出，无补杀 |
| 第二个实际服务器 | 不同实际宿主PID；同库恢复interrupted，旧finalized／canonical不变 |
| 查询／权限／SQL | 历史两唯一行；每session一贡献；已finalized不能恢复，别的配对owner404 |
| 正常关闭 | 新宿主实际退出0；原consumer／共享worker准确释放，没有备用清理 |

共22项条件，事先固定45秒等待、5秒宿主退出、2秒原child退出、5秒HTTP请求超时。报告从pending到ready使用实际查询，不把HTTP202当最终保存。SQL独立只读事务重查事实／贡献／反馈，不靠页面显示判断。

## 4. 复现与证据

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/socket_recovery_audit.py --publish
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_socket_recovery.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
```

专项`socket-verification-9b308f4f`实际3项测试＋预声明3轮，每轮22条件通过。两次响应丢失、原JPEG／报告和第二服务器在每轮重新执行；旧宿主强制退出1，新宿主正常退出0，没有监督程序补杀。15份工具／源码／原权重hash、真实参数、两宿主日志和原始summary见[专项汇总](../../reports/rehab_backend/socket_verification.json)及[本机验收](../validation/REHAB_SOCKET_RECOVERY_2026-10-11.md)。

## 5. 不能扩大解释的地方

这是Windows本机loopback TCP HTTP，不是手机、Wi-Fi／LAN、TLS、公网、代理、弱网重传或长时负载。第二服务取得新临时端口，客户端显式换地址但保留cookie／密钥；没有证明原URL自动发现／客户端自动重连。门人为定位响应丢失窗口，不给出自然网络故障概率、端到端控制p95或吞吐性能。

两个白图已实际推理，但不能证明人体识别准确；重启前新评估只有0确认次／缺测检查点，非该轮验证一确认＋半次，后者沿用[此前三窗口证据](REHAB_ASYNC_RECOVERY.md)。不训练、不替换候选。产品0.20.0、既有APK0.2.1、v2默认关闭；目标RGB／专业参考、手机、真实网络及长时条件仍需补足。
