# Windows 中文语音输入：宿主接线与验证

范围：`codex/product-ui-v1`。不改 Agent 语义、训练逻辑、数据 schema 或主题。TTS 仍明确不可用。

## 正式运行链路

Qt 语音模块 → 确认使用麦克风 → `ProductBackend` 后台队列 → 原 Python/Node bridge → `ProductService.voice.input` → `HostVoicePort` → 原 bridge 的宿主回调 → `NativeVoiceHost` 真实麦克风 → 本机 faster-whisper 中文 ASR → 原 `ProductService.chat` → 对话反馈。

没有第二套 Agent 或聊天业务。原浏览器 VoicePort 保留；宿主明确注入时才使用原生 adapter。取消通过线程安全标志/终止 ASR 子进程立即执行，不排在录音队列后面。说完按钮结束录音并识别，停止语音取消。录音最长 30 秒，ASR 最长 90 秒；不保存麦克风音频、不上传音频、不自动下载模型。识别文字沿用原对话记录规则；“本轮不记录”开启时语音入口拒绝录音，文字输入仍可用。录音/识别期间禁止修改该隐私选项及切换用户。

## 可选安装

`Setup-Rehab.ps1 -IncludeVoice`，或在应用环境运行 `scripts/setup_voice.ps1 -PythonPath <python>`。主 PySide6 依赖不变，不引入 QtMultimedia、PyQt 或 Web。

- sounddevice 0.5.6 / faster-whisper 1.2.1 / av 16.0.1；av 19 与此 faster-whisper 的文件解码参数不兼容，已固定兼容版本。
- CPU int8 multilingual base：`Systran/faster-whisper-base`，固定快照 `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`；安装脚本逐文件核对 Git blob / SHA256，模型和缓存保持忽略。
- 许可及部署边界见 `rehab_codex_single_camera_v2_1/assets/voice/README.md`。
- 缺组件/模型/麦克风时显示真实配置状态。朗读尚未接入，按钮禁用并说明原因。

## 2026-10-03 本机证据与限制

- Windows System.Speech 只有 en-US，不能用于宣称中文识别，因此选择独立可选本地 ASR。
- 实际 Surface 默认麦克风支持 mono / 16 kHz / float32，真实 InputStream 已打开、读取并关闭。
- 公开 Google FLEURS 中文 TEST 文件 `10026684690566417990.wav`，CC-BY-4.0，固定数据快照 `70bb2e84b976b7e960aa89f1c648e09c59f894dd`，本地 ASR 得到“這並不是告別這是一個偏章的結束也是新偏章的開始”。存在识别错字，不宣称准确度合格。
- 扬声器播放此公开文件→真实麦克风→ASR 两次尝试均返回“未识别到清晰语音”，没有假成功/写入对话。第二次真实采样 183296 个 float32 值，RMS 0.003875、peak 0.05844。未保存麦克风录音；测试资料和观测留在被忽略的 `qa-output/voice-native`，临时 TEST 档案清除。
- **实体采集已验证；公开扬声器回采识别未通过，真人中文输入仍待用户实测。** 不能把文件识别或模拟输入的闭环称为真实麦克风语音识别验收。本人说话、系统麦克风权限/音量、噪声与硬件回声处理需在验收时核对。

## 针对性软件验证

Python/Qt：`test_native_voice` + `test_product_assistant` + `test_product_visual` + `test_product_window`，21 passed。覆盖原 VoicePort→真实 bridge→原聊天链路（明确 TEST 文本宿主）、提前取消、静音拒绝、关闭采集再识别、忙碌期间结束/取消可操作、重复提交阻止、成功跳转对话、取消不写对话、TTS 明确禁用、原按钮契约与用户隔离。

Node：原 `product-extensions.test.cjs` 9 passed。测试输入不代表实体设备验收。原 116 个发布按钮、侧栏发送、13 个管家导航保留，仅增加一个结束录音按钮。

复核命令：应用目录 `python -m pytest tests/test_native_voice.py tests/test_product_assistant.py tests/test_product_visual.py tests/test_product_window.py -q`；实体公开声源 QA 为 `python tools/validate_native_voice.py`，失败会非零退出并记录真实状态。

来源：[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[固定模型](https://huggingface.co/Systran/faster-whisper-base)、[sounddevice streams](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html)、[FLEURS](https://huggingface.co/datasets/google/fleurs)。
