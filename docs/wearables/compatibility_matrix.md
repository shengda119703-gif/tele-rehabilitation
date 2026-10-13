# 实际兼容矩阵（不是品牌承诺）

| 组合 | 工程实现 | 本机验证 | 真机 |
| --- | --- | --- | --- |
| Windows/Python3.13 + 原FastAPI配对服务 + 小米云 | 四主类+可选体重/血氧、OAuth、刷新、解绑、许可核对、有限通知 | HTTP合同/数据库/故障TEST | 未提供审批/凭据/真实授权，NOT_RUN |
| 同宿主 + 华为CN云 | OAuth/官方tokeninfo/日步数；正式header外部配置 | 日统计毫秒组/纳秒点、授权合同TEST | 华为账号/手表/审批/版本未提供，NOT_RUN |
| 原Apple HealthKitDeviceAdapter/JSON桥 | 未修改 | 原bridge场景+10 adapter测试通过 | 不新增iOS或Apple Watch兼容声明 |
| 小米手环7 + Mi Fitness + 用户红米手机 | 目标组合；不解绑 | 仅官方支持两种App的事实；具体OS/App/读取未验 | NOT_RUN |
| Band7 + Zepp Life | 未实现Zepp数据合同 | 无 | NOT_RUN，不当成Mi Fitness |
| APK0.3.2/code32 Android29–35 | 原功能和旧签名包保留；本轮没有原生wearable reader/授权回传入口 | 不重打包、不做安装测试 | Wearables NOT_IMPLEMENTED |
| Health Connect 1.1.0 / Google服务 | 官方稳定依赖已查；Python outbox参考底座 | 队列/Changes启动顺序/原子cursor工程TEST | Android SDK/getSdkStatus/features/aggregate未接，NOT_IMPLEMENTED |
| 小米本地SDK | 未加入正式SDK | 无 | 灰度资格/OS条件需负责人确认，再实现 |
| Huawei Android Health SDK | 未加入正式SDK | 无 | HMS/前台与App开放条件需真实设备，再实现 |
| HarmonyOS NEXT设备 | 未承诺Android APK运行或原生支持 | 无 | NOT_RUN |
| 独立团队云/家属共享 + 手机/电脑一致 | 当前分支没有该服务器权限模型，未合并另分支 | 本人隔离通过，非团队联调 | NOT_RUN |

具体命令、当前计数及失败历史见 acceptance_report.md；不能把工程合同测试当成准确率或真实设备采样。API版本wearable-history-1；桌面0.23.2、APK0.3.2不因新增后台模块自动更改编号。
