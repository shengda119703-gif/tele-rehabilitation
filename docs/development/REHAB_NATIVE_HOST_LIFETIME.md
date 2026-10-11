# 康复v2：宿主退出时释放原生子进程

日期：2026-10-11。实施基准`a1b96143773f0911f401636685238cc8d87a5739`。对应后端任务书6.5、7、C18／C23及P7。只修改默认关闭v2的所属worker生命周期和必要工具／测试；不改动作公式、计次、目标、剂量、旧live、前端、整个Android、正常库或权重。

## 1. 实际问题

上轮验证了三个SQL结束窗口，但没有启动原生pose／report子进程。原`OwnedJsonWorker`在正常关闭时能终止准确所持进程，宿主突然退出却没有同等保护。子进程若正等待原生计算，不一定能及时读取管道EOF；它还可能持有计算资源和共享内存。

未接保护的`native-parent-acc2c753`实际退出1：两个TEST原生阻塞用例和原YOLO冷ticket用例，都没有在宿主退出确认后的2秒期限内结束；仍为STILL_ACTIVE=259，测试监督程序随后只用预先保留的准确子进程句柄清理，并确认实际退出。失败保留在[原始基线](../../reports/rehab_backend/native_parent_before.json)，不能用之后通过覆盖。

两个TEST用例写出标记后调用60秒`kernel32.Sleep`，使用本机CPython `PyDLL`保持GIL；不是普通Python线程sleep。原YOLO用例使用原目标函数和320×240白色JPEG，冷ticket已发送、worker存活、warm=false；它证明冷启动任务所属生命周期，不证明模型完成了一次forward，更不是真人精度。

## 2. 修复与实现依据

[host_lifetime.py](../../mobile_rehab/rehab_v2/host_lifetime.py)在Windows创建匿名、不可继承的Job Object，设置`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`。宿主独自持有句柄，子进程不继承它；宿主退出导致最后句柄关闭，关联子进程树由内核结束。机制与限制来自[微软Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)、[结构定义](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information)和[AssignProcessToJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)。嵌套job在Windows8及后续支持；受外层job限制导致绑定失败时不能降级成无保护计算。

```text
宿主创建匿名Job／独持不可继承句柄
            ↓
spawn准确所持Process → 子进程等待admission，不执行模型目标
            ↓
将Process原sentinel句柄绑定到Job
            ├─ 失败：明确host_lifetime_unavailable，原所属清理，不放行目标
            └─ 成功：admission.set → 原姿态／报告目标与通信协议
                                      │
                           宿主突然退出：OS关闭Job句柄
                                      ↓
                            内核终止该关联子进程树
                                      ↓
                     资源锁／共享内存随实际进程退出释放
```

[OwnedJsonWorker](../../mobile_rehab/rehab_v2/owned_worker.py)复用原spawn、消息大小、共享缓冲及准确所属释放。Windows新增启动门：绑定成功前不能调用目标；未放行子进程还检查父进程存活与原startup budget，不永久等待。创建／绑定失败返回稳定角色错误，不加载模型、开相机或假称推理成功。

正常关闭仍先确认所属进程退出，才关闭Job与共享区／pipe／process句柄。Job关闭失败保留有效句柄和quarantine，后续可重试；不先把Process对象关闭后再留下不可重试状态。复用同worker保持同Job，准确释放后重启取得新Job。报告取消、超时、抢占仍沿用原逻辑。

pose／report execution contract增加`host_lifetime`，版本`rehab-owned-host-lifetime-1`。它是生命周期元数据，不是骨架／动作算法升级，不重写旧事实。在非Windows保留原所属释放路径并明确`kernel_enforced=false`；没有宣称新增跨平台原生父死亡保证，也没有把它当作恶意代码sandbox或OS Process.start硬截止。

## 3. 验证范围与信息对账

[native_parent_audit.py](../../tools/rehab_ml/native_parent_audit.py)每用例创建新宿主和TEST库。监督程序先证明所持宿主句柄存活、实际PID匹配，再从新创建的原worker证明捕获子进程句柄；之后绝不根据旧PID重新查杀。先结束准确宿主，再等已保留的子进程句柄；通过必须不需要监督程序补杀。失败时仍清理准确句柄并保留失败。

| 用例 | 输入／任务 | 训练事实核对 |
| --- | --- | --- |
| TEST native pose wait | 原IsolatedPoseWorker transport＋GIL-held原生等待＋formal lease | 1确认次＋1半次检查点；重开interrupted，不补半次 |
| TEST native report wait | 原IsolatedReportWorker transport＋GIL-held原生等待＋report lease | 已提交事实的canonical原样保留，不因派生任务中断回滚 |
| original YOLO cold ticket | 原pose_process目标／原权重／白色JPEG／冷ticket在途 | 同TEST检查点恢复；不把白图当人体证据 |

均核对子进程真实退出、计算heavy lease可重新取得、volatile shared memory已不可打开、原确认次保留、canonical不重复、唯一贡献和空反馈。确认次来自内部TEST几何，不是该白图或等待函数生成；贡献不具正式计划完成资格。新Store／Service生命周期恢复在监督程序内进行，不是第二个socket服务器。

7项测试覆盖实际三用例、非Windows不冒充、Job句柄不可继承、创建失败、绑定失败不放行目标、复用／重启，以及Job关闭失败后实际句柄可重试。它们和完整工程回归都不是人体参考数据。

## 4. 复现

```powershell
$env:TEMP='E:\game\health-care-software-main\.runtime\rehab_ml\run'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/native_parent_audit.py --publish
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_native_parent.py
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/verify_all.py
```

专项预声明7项测试＋3次审计重复，最终`native-parent-verification-ee19bb9f`退出0；三轮×三用例均不需补杀，每用例11条件通过。记录的0.0105–1.1022毫秒是**宿主已经退出确认后**对child句柄的观察等待时间，不能当作从宿主kill开始的端到端终止延迟或稳定p95。源码／原权重hash、命令／日志及每轮原始summary见[汇总](../../reports/rehab_backend/native_parent_verification.json)和[本机验证](../validation/REHAB_NATIVE_HOST_LIFETIME_2026-10-11.md)。

## 5. 仍待完成

本机Windows短时工程证据；没有Linux／macOS、实际相机或手机、网络、长时／多客户端、物理断电／磁盘满。没有任意外部native库、恶意子进程或OS启动永久阻塞验证。原YOLO用例不代表人体准确率或forward性能，不能据此上线研究候选。

v2默认关闭，产品0.20.0、既有APK0.2.1和五页导航保持；未启停用户旧服务／相机，不关闭窗口。合法目标域RGB／独立专业参考仍缺，P5／P6及完整P7未完成。
