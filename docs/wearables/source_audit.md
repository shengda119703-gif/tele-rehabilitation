# 穿戴接入源代码盘点（2026-10-13）

基线：707336a，实施分支 `codex/wearable-health-integration`。依据 E:/安康小米与华为穿戴设备接入实施任务书.md，新增后台能力，不改正式 UI。用户现有小米手环7，称使用“小米运动情况app”；暂按小米运动健康（Mi Fitness），Zepp Life 需另确认，不解绑、不重置。

| 边界 | 实际文件与结论 |
| --- | --- |
| 安卓包 | android_offline/AndroidManifest.xml：Java / WebView，cn.tele.rehabilitation.offline，min29 / target35；原0.3.2/code32 |
| 构建签名 | android_offline/tools/build.ps1，编译 android-35.jar，原本机私钥；不引入或更换签名 |
| 手机服务 | mobile_rehab/server.py:create_app，FastAPI；已有签名rehab_device配对cookie、X-Rehab-Client写入保护 |
| 共享本人 | mobile_rehab/unified.py、server.py owner闭包：共享宿主仅配对当前本人；不是治疗师登录或多租户云账户 |
| 个人健康 | mobile_rehab/product.py -> product_host.cjs -> 原ProductService；不修改手填、药物、聊天或备份规则 |
| 桌面 | 原PySide6 + ProductBackend，可通过现有手机服务宿主调用新增后端；本轮不加Qt控件 |
| 苹果通道 | ankang/route1-health-agent/src/adapters/HealthKitDeviceAdapter.ts、scripts/healthkit-bridge.mjs：最新一份JSON快照、原单位/归属校验；不是通用穿戴历史库，不迁移、不替换 |
| 本机数据 | 新wearables.sqlite3放create_app提供的运行目录，与旧home_rehab/个人健康库独立；不修改旧user_version |
| 云端/团队 | 当前分支没有独立云账户/治疗师服务；CloudTransport.java仅为另一服务协议的客户端，不能当作已有可用后端；不合并无关云分支 |
| 厂商SDK | 未发现小米本地SDK、Huawei Health SDK、Health Connect Jetpack依赖；当前Java手工打包不能冒称已接官方读取器 |
| 外部条件 | 未提供两厂商审批、Client ID/Secret、HTTPS回调、获批权限、华为测试设备；读取真实数据待这些条件 |
| 用户保护 | 279份未跟踪文件与指南README修改保留；86份已跟踪页面/样式/本地前端/Qt文件开工SHA冻结 |

实施顺序：独立身份/加密授权/幂等历史库 → 官方云契约 → 有界同步/查询/撤销/通知 → 隔离故障验证 → 接入条件与真实验收登记。仅为新增只读健康背景，不改变训练资格、视觉计数、处方剂量或完成量。网页仍用原配对机制，不新建登录系统；请求中的patient_id不具有授权效力。
