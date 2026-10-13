# 安卓DeepSeek连接验收 · 2026-10-11

交付APK：android_offline/dist/tele-rehabilitation-mobile-0.3.0.apk，versionCode4，28066355字节。

SHA256：09506E65BCBEE778F4359AD9988FC37FB7E59D0E1D709A69DBF2AD1A20D77EEE。

使用原签名，证书SHA256：a7f88e94c6b6ae6011d16e3eeb2762417361ed28bb1c798a4e617b41a39e0d70。专用新建Android35模拟器AnkangDeepSeekQA安装旧0.2.1再覆盖安装0.3.0成功；不代表个人数据完整迁移或目标实体手机验收。

原生Instrumentation在真实MainActivity／WebView调用PhoneLocal→ProductService→Runtime→Android HTTPS。四次真实DeepSeek请求通过：两句用户截图普通输入、两轮代号上下文。检查回复来源、PHONE_LOCAL可信分区、健康与家庭事实不变、私密轮次不联网、本地联合查询与康复读取。原生出站计数恰好4；加密配置重建可读且偏好不含明文。测试结束清除测试Key及临时文件。配置窗输入为空，不回显旧Key。

工程回归：453项共享TS、72项安卓JS、13项手机接口、3项打包测试通过。打包测试核对原静态资源、模型策略／适配器和排除私人QA文件。实际聊天来源与原生配置窗截图已查看。

本机忽略日志：qa-output/android-deepseek-build-final.log、android-deepseek-qa-build-final.log、android-deepseek-native-r1.log、android-deepseek-tests-final.log、android-agent-shared-tests.log、android-agent-web-tests.log。截图保存在工作区外层qa-output/android-deepseek-final/。密钥、APK与日志不提交Git。

开发失败保留：初始资源打包因Unicode路径失败，改为ASCII暂存；AVD管理器缺少emulator包元数据，采用专用新AVD；首轮联网QA失败，控制诊断后重跑通过，未证明该次失败根因。最终验证使用最终包，非中间包。

边界：不是iOS交付、Health Connect接入、实体手机／临床或上架验收；有限模型工具规划不等于任意模块执行。已有两份CSS保持原hash且不纳入提交。详细范围见[交付说明](../development/ANKANG_DELIVERY_SCOPE.md)。
