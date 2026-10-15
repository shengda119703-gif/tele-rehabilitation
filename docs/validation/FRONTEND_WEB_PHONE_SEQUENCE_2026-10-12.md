# 托管与APK本地组序列验证（2026-10-12）

基于已上传的d996f64565c333d7719ae8fc806bc53134858255，工作分支`codex/frontend-flow-optimization`。对应桌面任务书第10节与F15／F16／F19／F21／F25／F30／F32／F35的独立跟练部分；不是完整U0–U6或人体准确性验收。桌面产品仍0.20.0，本轮没有修改Qt源码。

## 接线与边界

托管原HTTP／SQLite writer；PHONE_LOCAL原local-api／Store.serial/change/commit，没有新患者数据库。schema2冻结原安排序列及组位置，同旅程的每组各有原id和独立结束事实。前组successor与后组在同一原提交写入，失败不承认任一新关联。普通ended／discomfort不自动完成目标；明确completed_set后才提供下一组／下一动作导航，未填次数与感受保留null。本人总次数不写成视觉确认，也不增加原正式计划贡献。

继续载荷和关闭载荷严格匹配原接口，owner／provider／source不由客户端改写。同键同载荷先核对原后组，后来资格改变不阻止读取已发生事实；新执行仍重查原规则、原版本／设置／定义、停止和单活动限制。换动作按原要求重新核对支撑／陪同，不重新采用整份安排。托管自动分支的原正式next_key门仍会真实拒绝下一项，专项验证未绕过；手机自动分支沿原提案与进度函数，未改其资格规则。

休息按所属writer UTC回执重查；本地短单调倒计时只是展示，不算运动／保持，不跨主机比时钟。未知继续先查原键；返回／刷新优先恢复带结束意图的父组，再核对实际后组；恢复PAUSED，不后台补时。自动入口不因为正式next_key未前移而再次创建首组。结束在途创建时先停止本地，核对实际后组后结束；查询失败有界，保留原身份由本人重试。小型分组草稿不是全模块全局outbox或跨窗口租约。

## 自动化检查

隔离输出均在`D:/RehabFrontendFlowVerification/`，不提交日志、私人原片、身份、逐帧数据或截图。

| 范围 | 最后完整结果 | 证据 |
| --- | --- | --- |
| 全部手机网页＋APK JavaScript | 189通过／0失败 | `phone-sequence-20261012-js-release.log` |
| 全部手机网页Python＋真实APK包装 | 163通过／2subtests／1原依赖警告 | `phone-sequence-20261012-python-release.xml` |
| 新PHONE_LOCAL组序列 | 8项，全套子集 | `android_offline/tests/care-local.test.cjs` |
| 共享组序列控制器 | 10项，全套子集 | `mobile_rehab/tests/test_practice_sequence.cjs` |
| 新托管组序列 | 8项，全套子集 | `mobile_rehab/tests/test_practice_sequence.py` |
| 原视觉保护范围 | 61内容不变／3既有授权Qt控制模块，无未授权变化 | `phone-sequence-20261012-original-visual-contract.json` |
| 两尺寸原动作／预览控件几何 | 与原基线相同 | `phone-sequence-20261012-preview-geometry/observations.json` |

Python警告为既有Starlette/httpx弃用，不新增／升级依赖压掉警告。Qt先前d996f64完整core1080／集成228／UI488的证据仍按原时点读取，不把手机回归当作本轮重跑Qt全套。

## 原存储／页面实际流程

托管原浏览器／HTTP／SQLite共8尝试、8完整、0失败：`actual-hosted-sequence-20261012-01`、`-02`、`-final-mobile`、`-final-desktop`、`-phone-final-mobile`、`-phone-final-desktop`、末次`-release-mobile`／`-release-desktop`。各3独立已提交组、1旅程、0评估，明确TEST已有安排，QA输入次数3／2／null，组位置1／2／1。真实提交后人为使finish／continue回复不可读，仍按原身份恢复；原休息、返回、换动作支撑／陪同、原分组历史及legacy通过。

APK实际包资源／原本地路由／Store共5尝试、5完整、0失败：`actual-phone-sequence-20261012-01`、`-final-mobile`／`-final-desktop`、末次`-release-mobile`／`-release-desktop`。各4独立已提交组、2旅程：本人的明确已有安排两组＋原自动规则两动作。分组QA次数3／2／1／null，组位置1／2／1／1，原正式进度0；0Python或云API、0浏览器异常。原休息、原键丢回复刷新、同组返回保留输入且暂停、自动入口恢复实际后动作、原历史和备份通过。

本地多组流程的两份评估是明确TEST标量夹具经过原LocalEngine.analyzeReplay及原提案，不是摄像头观测、专业真值或患者数据。两尺寸为桌面Edge headless 390×844和1440×940，不能代替红米或Android生命周期。没有以QA总次数证明人体完成量。

额外实际原录像兼容共3尝试、2完整、1失败：`actual-phone-sequence-20261012-worker-compatibility`用短版，分析done、覆盖1、0次数，原提案无候选，流程在新执行前停止，原件保留；没有降低门槛。`-worker-full`及末次`-worker-release`用原始肩外展录像，实际原CPU Worker、原文件SHA前后不变、1真实作业、3视觉次数、覆盖0.9606299186765038，经原自动安排完成单组、暂停返回、丢结束回复刷新、原历史／备份及3次明确QA后补反馈。独立次数10为QA填写、自动确认／正式贡献null、正式进度0、0PythonAPI。该真实视觉路径是单组兼容，不冒充多组正式视觉关联。

## 失败保留

- 托管新用例最初7项失败（未有continuation／新路由），`host-sequence-20261012-test-first.xml`保留；后补原自动资格第8项通过。
- 旧0.2.8包和新共享源码不匹配，原完整Python161通过／1包装失败、JS177通过／1资源指纹失败保留在`host-sequence-20261012-python-all.xml`／`host-sequence-20261012-js-all.log`。沿原构建生成新包解决，未删／弱化校验器。
- 共享控制器第一次专项1项失败：QA在已消费匹配回执后错误要求仍保留pending；改为发送前断言保留、匹配后断言消费，不改生产恢复语义。
- PHONE_LOCAL新8项test-first全失败保留在`phone-sequence-20261012-test-first.log`；第一次完整本地40通过／2失败为跨VM数组原型比较及QA反馈参数调用错误，`phone-sequence-20261012-core-01.log`保留；纠正QA参数／值跨域转换后42通过，最终全套覆盖。
- 额外短版原录像无资格失败如上，不能算完整通过，也不改其0次结果。

## 视觉审查、包与交付

共享页面复用原card／consent／button，不改CSS、字体、图标、主题或主要页面布局。实际截图审查后缩短新按钮文字、按后项更新标题、澄清独立历史的录像空态；不是重新设计。已查看最终两尺寸休息、下一动作和历史截图；原保护基线未重建，原预览几何相同。高对比／多屏／深色全页、物理音频和Android实机仍待。

APK0.2.10／versionCode12，28108088字节，SHA256`F5C1DFC52B255E68E2B43157596A62B98770744A47F41BD3CD212D8446C21562`。原v3签名证书SHA256`607edd7dc1df261e52fa2fe35ea6391e1ce77cbcebc315fea80dd815bac1a5d8`。最后构建日志`phone-sequence-20261012-apk-release-build.log`；真实ZIP包装测试核对三个本地源码及全部共享静态指纹。0.2.8原SHA`0B568BF97C8903603A4C7387163637BD3458AB0D2DF28E1838A5C4AFEE19669E`与中间0.2.9原SHA`16891E504D54A3054037BD107A2DBF7F21298D0F50A41483EED2E35C549CE64B`未变。未真机安装，无新模型／依赖下载；原origin／权限／签名／正常患者库不变。

回退：先结束当前旅程或保留原待核对键，用`experience=legacy`隐藏新开始入口，独立历史／感受与原键仍可读，不删事实、不跨provider。不要靠降装旧APK恢复未导出的schema2数据。只提交本轮自己的代码／文档，推原流程分支并核对远端；桌面原入口按已验证pythonw刷新Git描述。不启停用户8765／1396、相机、旧窗口，不捎带原图片／CSV／导入脚本。

完整任务仍未完成：正式视觉session关联／权威分段、Qt后补感受与跨进程待操作outbox、公共模块独立加载／报告隔离、持久媒体／双507导出、主动租约／统一音频、v2 canonical提交、三重点动作和物理真机／长时性能。局部用例与构建不能替代逐项最终验收，goal保持active。
