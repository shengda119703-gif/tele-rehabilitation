# 本地语音输入资源

只提供资源来源说明，模型与录音不入 Git。使用可选 `requirements.voice.txt`，设置步骤为工作区 `Setup-Rehab.ps1 -IncludeVoice` 或应用 `scripts/setup_voice.ps1 -PythonPath <应用 Python>`。

- sounddevice 0.5.6：MIT；Windows wheel 包含 PortAudio（MIT），真实麦克风采集。
- faster-whisper 1.2.1：MIT；CTranslate2 CPU int8 推理，PyAV 解码（BSD，捆绑 FFmpeg 的许可须随实际部署分发检查），ONNX Runtime（MIT）用于既有 VAD。
- 模型：官方 SYSTRAN 转换的 multilingual Whisper base，MIT，`Systran/faster-whisper-base`，固定 revision `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`；原 OpenAI Whisper 模型 MIT。
- 模型写入 ignored `.runtime/voice/whisper-base`。显式准备脚本固定来源并验证每个 Git blob/LFS SHA256；应用运行时 `local_files_only=True`、离线运行、不自动下载。
- 录音只在进程内存与受控子进程 stdin 中使用，30 秒上限，不保存用户录音，不调用远程 ASR。不改变已有 Agent/家属共享规则。

主 PySide6 Essentials 版本不变，不安装 QtMultimedia/Web/PyQt 或新 GPU 框架。语音包独立可选；未安装、无模型、无麦克风/权限均显示不可用及具体原因。朗读端口仍保留，本机宿主当前只接中文输入。

来源：[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[模型](https://huggingface.co/Systran/faster-whisper-base)、[sounddevice](https://python-sounddevice.readthedocs.io/)。具体安装版本与本机验收见 2026-10-03 阶段记录。
