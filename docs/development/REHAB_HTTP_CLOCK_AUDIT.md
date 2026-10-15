# 康复v2：HTTP测试时钟与断流证据核对

范围：任务书4.3、6.4、C03／C08／C20及P7。只改隔离TEST用例、诊断／核对工具和必要文档；不改生产接收时钟、姿态推理、动作协议、阈值、正式数据或客户端。

## 为什么把两种测试分开

旧HTTP用例以帧序号生成0°／70°的TEST角度，同时以宿主实际接收时间参与起点、驻留和相位判断。每次等待50毫秒不等于下一帧一定在50毫秒后到达：HTTP处理、SQL、调度都会增加间隔。超过原协议500毫秒的间隔不能补成连续观察。最终seq64已保存，也不能据此要求计数一定是1。

原`verification-f28dac51`455项／1失败保留，其失败没有逐帧时钟与相位记录。本轮可复现“真实间隔超限时0次＋无法确认半次”，但不能把相似结果当作原失败根因的证明。

## 实际信息链与测试责任

| 路径 | 输入与时钟 | 保留的判断与保存 | 验证范围 |
| --- | --- | --- | --- |
| 固定证据时钟 | 真正的配对／签名cookie／JPEG请求；仅私有TEST推理钩子输出`seq × 0.05`秒及TEST角度，来源`TEST-recorded-http-evidence` | 原引擎驻留／往返、原SQL检查点、原202／最终回执及时间比较 | 鉴权、归属、路由、比较和保存；不是实际相机时效或人体准确性 |
| 真实接收时钟 | 同一TEST角度配方；逐帧读取原`source_time_s = received − runtime.started`；在seq55前实际等待650毫秒 | 原500毫秒连续性门产生`long_evidence_gap`，保存一条UNASSESSABLE，完整次数0，边界64／64／64 | 有证据的接收断流／部分次保存；不是手机曝光时钟或自然弱网 |

真实HTTP接收、排队、控制、报告与结束期限仍使用原宿主时钟。固定时钟只作用于TEST证据，不映射到实际相机曝光，不修改服务对外协议；私有TEST推理钩子不是可信外部关键点接口。当前提示的跨时钟时效不由这一固定时钟用例验收。

正例仍要求两次独立评估各确认1次、本人可比较、伪造owner拒绝、跨owner不可见、失去认证拒绝、v2默认关闭。负例先确认seq54处于RAISING，再检查seq55真实间隔超过650毫秒、保存的部分次原因和最终接收／处理／证据边界。不能通过放宽`max_gap_s`或删除缺测门让正例通过。

## 诊断与复查工具

[timing_http_probe.py](../../tools/rehab_ml/timing_http_probe.py)包裹原TEST用例，原调用返回后记录逐帧时间、dt、指标来源、前后阶段、基线、驻留、逐次结果及失效原因。每次创建独立run，保存trace、测试原输出、source SHA与退出资源状态；不写患者历史，不开启相机。失败仍返回非零，不能把故意复现的旧正例失败标成测试通过。

从根目录运行：

```powershell
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/timing_http_probe.py --case recorded
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/timing_http_probe.py --case host-gap
& '.\rehab_codex_single_camera_v2_1\.venv\Scripts\python.exe' -X utf8 -B tools/rehab_ml/timing_http_probe.py --case receive --delay-before-seq 55 --delay-s 0.65
```

最后一条沿旧“总应1次”的真实时钟正例断言故意制造断流，预计退出1；其0次并非引擎失去保护，而是原断言前提没有成立。CLI打印实际run ID，不能用“最新目录”替代指定证据。

[verify_timing_http_probe.py](../../tools/rehab_ml/verify_timing_http_probe.py)只读显式四个run与完整回归run，核验文件SHA、64帧序号、真实dt、TEST角度配方、observed来源、阶段／部分原因、原生产源码未改及准确资源释放；另外用本地TEST篡改检查核对器是否拒绝错误计数、时间回退、predicted冒充观测。这些自检不是额外HTTP实跑，不加入unittest计数。

聚合证据发布到[时钟核对摘要](../../reports/rehab_backend/timing_http_clock_verification.json)，逐帧TEST结果仍在忽略目录。此前trace版本和失败不覆盖。实际run、命令、完整回归及保护结果见[本机验收](../validation/REHAB_HTTP_CLOCK_2026-10-12.md)。

## 剩余条件与证据责任

原455项失败根因仍待独立证明；当前措施是修正测试的时钟前提并覆盖真实断流，不宣称修复了人体动作漏计。无独立相位／可观察完成标签、目标手机、LAN／TLS／自然弱网或长时实测，P5／P6与完整P7不能据此完成。既有RGB负结果与候选关闭保持。

scientific-writing用于方法／结果一致性、保留失败、人工核验pending和工程／临床分层。只在本机处理TEST证据，没有向外发送录像、点或患者资料；外部仅核对公开技能论文元数据。参考Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026), *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*, [DOI](https://doi.org/10.48550/arXiv.2609.00065)。2026-10-12核对官方记录仍为2026-09-02的v2；该参考不证明本项目有效性，人类审核与科学审批未完成。
