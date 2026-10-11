# 后端阅读版：功能、读写依赖与信息链核对

日期：2026-10-11，Asia/Shanghai。文档开工HEAD为`1a4dd43bcb7a7747518423c72a40122b348a9b2d`。

## 本次交付

更新 [后端功能与技术实现梳理](../后端功能与技术实现梳理.md)，覆盖34项主要功能的输入、实现方法、公式、输出、消费者和源码位置。三端运行／存储差异、已接与未接功能、逐跳字段、分母、参数及单层验收保留；新增14条读写依赖，解释原自动计划／人工计划／工作区v2显式安排的区别，补健身和上传康复录像的完整链路。用这些依赖定位误差最早出现的环节，而不是将所有问题归到模型准确率。

仅修改上述阅读版、README索引、HANDOFF本新增段落与本记录。不实施算法、不改前端／Android／原模型／正常库、不启动训练／相机／服务、不分析私人录像或安装依赖。现有未提交功能及用户素材不捎带上传。未新启动完整业务、真人、手机或性能回归。

## 源码对照

| 核对域 | 实际代码与确认内容 |
| --- | --- |
| 原康复与计划 | assessment.py、automatic_plans.py、training_plans.py：最新同范围证据、proposal指纹、保存计划／条目／版本、执行与反馈，和健康事件不同 |
| 托管录像 | analyzer.py、fitness_analyzer.py、posture_analyzer.py、server.py、care.py：康复SQL先保存后job结果；健身体态主要写job结果；媒体PTS、首部兼容、来源／情境及不同结果对象 |
| 器械 | barbell.py：真实标尺、有限模板匹配、位置与求导分层、采样／残差限制；质量不替代标定，不解释为肌肉发力 |
| 健康及管家 | ProductService、events.ts、derive.ts、detect.ts及相邻模块：事件→日数据→Finding／PersonTwin／上下文；图像／语音入口及接受事实区分 |
| Care／家庭 | CareCoordinator、care_host.py、daily_store.py、FamilyService、NotificationService：确认、expected原事实、事务receipt和授权／送达分开 |
| 跨端 | Runtime、PhoneHost、统一宿主与APK适配：计算位置、规则、存储与继续政策不全部相同 |
| 已提交恢复 | pose_training.py、POSE_RESUME_WORKFLOW及验收：显式epoch恢复、来源／RNG／数值契约；旧失败与最终工程通过分别保留 |
| 工作区计划 | plans.py、SessionService、v2 API及server的participant注入：三个协议、最新已提交评估、显式安排、自评、版本与幂等；未发布、未接UI／APK、不自动生成剂量 |

已提交产品版本仍0.20.0，APK包元信息仍0.2.1；v2默认关闭。源码有实现不代表正在运行的服务或已安装手机包已经更新。

## 接收此前专项的实际终态

现存专项`backend-plan-audit-4a829c6a`：15项、退出0，执行约31.46秒，`passed=true`、`implementation_unchanged=true`。六份源码hash与当前文件核对一致；完整日志SHA256为`b7ea6b28943bd454b797719ee958d5ffc01e9983f0463dc3fcddb5b234fc1062`。

范围是隔离TEST几何、实际宿主HTTP与原YOLO对白色JPEG缺人的拒绝；报告明确human_data=false、training_performed=false、clinical_accuracy=null。这不是本次新启动的检查，不是15项真人试验，不证明自动处方、精度提高或完整回归通过。最初`backend-plan-audit-9316c072`的15项中一个两组训练用例实遇休息后继续送帧导致失败；随后只修正测试夹具，真实暂停拒收规则保留。原失败日志不删除。

工作区文件与报告只读保留；读者查看已提交仓库时，应把阅读版16.4理解为本机工作区状态说明，而不是已发布接口。

## 文件保护与文档检查

开工快照289份既有未提交文件，逐路径记录SHA256，包含用户280份素材／任务书／CSV／导入脚本及原后端工作。原保护manifest为`reports/rehab_backend/protected_files.json`，SHA256 `75f736e75795a334431f0d87664f720fede7093c62d3614f9969d0af35b3d742`；不重建、不刷新原审计报告。

同一批289份文件逐路径／SHA256比较后变化0。以ordinal排序的`路径|小写SHA256`、UTF-8编码、LF分隔且无末尾换行聚合，SHA256为`49bf0d629ecc8600d2e81ca34759c8904f084cc701dbb5c8554919873a67ba0a`。原1308保护条目另行实际重算，变化0，manifest hash不变。

| 本次实际只读检查 | 结果 |
| --- | --- |
| 功能及依赖 | 34项主要能力、14条读写关系、五条完整例子；原26节参数地图保留 |
| 阅读版结构 | 1272行、31张表、50个代码围栏标记闭合；四份文档表格列数一致 |
| 四份文档本地链接 | 阅读版179、README62、HANDOFF75、本记录1，共317；缺失0 |
| 既有工作区保护 | 原289份逐路径hash变化0；只新增本次四份文档差异 |
| 原保护条目及manifest | 1308条目hash变化0，manifest未重建、hash不变 |
| 专项终态依据 | 当前六份源码hash及一份完整日志hash与现存报告一致；最初失败日志存在 |
| 远端和差异 | fetch后HEAD与origin/main无分歧；文档差异检查通过 |

这些是源码／文档／文件保护核对，不是本次完整业务、真人、手机或负载验收。历史303项回归和当前15项专项均保留各自运行范围，不相加为本次通过数量。

本次四份文档独立提交、推送并核对origin/main。桌面“安康康复（最新版本）”继续指向原Start-Rehab.ps1及已验证pythonw.exe，只刷新Git版本描述；不打开或关闭用户应用窗口。
