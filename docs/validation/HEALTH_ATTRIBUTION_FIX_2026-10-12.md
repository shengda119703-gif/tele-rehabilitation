# 健康聊天归属修复验收 · 2026-10-12

电脑0.23.1，独立安卓0.3.1（versionCode5）。起点为6b293ed；修复分支fix/health-chat-attribution，按用户要求验证后并入main并推送。

## 修复结果

- 陌生姓名、朋友等他人数值不再默认属于本人。人物不能确定时先澄清；判断在本人识别及历史主体继承之前执行。
- 引用、示例及“不是我的”数值在拆句、纠正目标选择之前解释，不新增本人事实，也不误删上一条真实记录。带数字的归属否认要求另述本人结果；不带新数值的明确撤回及原家人症状纠正继续保留。
- 原五条失败原话（张三血糖、李四血压、朋友血糖、资料血压、报告示例血糖）在最终发布代码的五个独立空库中均无误写，关闭／重开后仍为空。
- 补家庭权限、连接状态、康复记录的离线同义表达。新增身体汇总只读工具，复用原readPersonTwinProduct；是已有健康档案的状态汇总，不把它称为康复动作或训练报告的身体汇总。未知趋势显示数据不足，不创建测量、诊断或训练计划。
- 正常本人血糖、血压、静息心率、历史日期、分享接收人和原家人／代词归属保留。

## 实际验证

| 检查 | 结果 | 本机证据（qa-output/） |
| --- | --- | --- |
| 最终共享TypeScript完整回归 | 475通过，0失败 | attribution-fix-ts-release.log |
| 最终构建／类型检查 | 通过 | attribution-fix-build-release.log |
| ProductService／扩展回归 | 20通过，0失败 | attribution-fix-product-release-r2.log |
| 原五条真实HTTP独立空库、重启读回 | 5通过，0失败 | attribution-fix-release-repro/results.json |
| 12条归属／示例原话×空库／已有真实血糖，重启读回 | 24通过，0失败 | attribution-fix-http/results.json |
| 原健康语义／家庭／查询HTTP矩阵 | 55通过，0失败（原为49通过、6失败） | attribution-fix-state-final/results.json |
| 当前Qt界面真实QTest操作 | 14通过，0失败，offscreen | attribution-fix-desktop/results.json |
| 真实Edge网页流程 | 42通过，0失败，0页面错误 | attribution-fix-web/browser/results.json |
| 发布手机域逻辑与安卓JS回归 | 73通过，0失败 | attribution-fix-android-js-release.log |
| 当前版本APK打包检查 | 3通过 | attribution-fix-packaging-release.log |
| 凭据静态检查 | 通过 | attribution-fix-security.log |

HTTP模块查询逐步回执核对：family_status、extension_status、rehab_history、body_overview均为succeeded。手机新增测试从实际发布bundle加载ProductService，对五条原话分别使用空档案和已有记录的档案，重新构建Service核对持久化事实未变。该检查在Node VM执行，不称为安卓原生操作。

24项扩展矩阵及55项矩阵在开发末期运行；最后额外收紧“说错了＋不是我的数值”处理后，475项共享回归、五条发布原话重启复现、发布手机73项及打包检查重新验证。不同层次和重叠样例不累加成独立场景总数。

## APK交付

文件：android_offline/dist/tele-rehabilitation-mobile-0.3.1.apk（本地交付，按已有规则不提交二进制）。

SHA256：e744073876060ecb37650dd8a76e64cbdd18e367a32ce7fcae26066381591cc0。大小28066355字节。采用原本机签名，签名验证通过，证书SHA256为a7f88e94c6b6ae6011d16e3eeb2762417361ed28bb1c798a4e617b41a39e0d70。

启动专用安卓模拟器的命令被自动审批以“blocked by policy”拒绝，未绕过；因此本轮没有新做模拟器安装／原生操作／覆盖升级验收。安装包和共享逻辑回归通过不能代替实体手机验收。

## 开发失败和保留边界

初版主体保护误挡普通逗号后的本人血压以及已知家人的代词，共享回归467通过、2失败；修正后保留全部既有回归。扩大归属否认时误挡“不是我，是我爸摔了”，已调整为带数值的整句保护。接口初轮误挡“我今天静息心率68”，结果54通过、1失败；补测量修饰语后重跑55项全通过。原始日志均保留，不抹去失败。

只使用隔离TEST档案，不读写正常患者库，不启停用户相机、麦克风和原有服务，不关闭旧窗口。不对历史记录自动清理：旧误记无法仅凭数值安全区分，需用户在原档案核对。两份开工CSS保持原SHA256且排除Git提交。APK沿原构建流程打包当前已有静态资源。

本次是此次诊断问题的修复回归，不是所有语言表达均正确的证明；复杂转述／混合主体仍可能需要拆句确认。未重跑上轮全部Python／模型环境检查，其既有解释器缺失、fixture不匹配和收集问题仍见原诊断报告；不宣称已解决临床精度、实机、录像全链路、长时／断电等未测范围。

桌面沿New-RehabDesktopShortcut.ps1维护“安康康复（最新版本）”，使用本机已验证.venv-ui-polish/Scripts/pythonw.exe；首页／康复／健康／用药／家庭导航保留，聊天从管家进入。
