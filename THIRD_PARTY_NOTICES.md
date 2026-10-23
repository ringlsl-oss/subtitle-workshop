# 第三方组件说明

项目原创代码使用 MIT。依赖及传递依赖保持各自许可证，实际分发时以所用版本的许可文本为准。

| 组件 | 用途 | 上游 |
| --- | --- | --- |
| Flask | 本地 API | https://github.com/pallets/flask |
| pywebview | 桌面窗口 | https://github.com/r0x0r/pywebview |
| PyAV | 媒体处理 | https://github.com/PyAV-Org/PyAV |
| jieba | 中文分词 | https://github.com/fxsjy/jieba |
| OpenCC Python | 繁简转换 | https://github.com/yichen0831/opencc-python |
| OpenAI Whisper | 识别与模型 | https://github.com/openai/whisper |
| PyTorch | 模型推理 | https://github.com/pytorch/pytorch |
| FFmpeg / libass | 转码与字幕导出 | https://ffmpeg.org/legal.html |
| Python | 解释器 | https://docs.python.org/3/license.html |
| Microsoft WebView2 | WebView 运行时 | https://developer.microsoft.com/microsoft-edge/webview2/ |
| Microsoft Visual C++ Runtime | 本地依赖 | https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files |
| PyInstaller | 打包 | https://pyinstaller.org/ |

源码仓库不包含 FFmpeg 可执行文件、Whisper 权重、Python/WebView2/VC 运行时或字体。FFmpeg 授权随构建选项变化；请核实实际构建许可证及源码提供要求。应用引用系统字体，不打包字体文件。

免安装工具生成的组件清单记录实际依赖版本。tools/portable_notices.txt 是本地试用包说明模板，不是任意二进制构建的完整许可清单。应用图标由 AI 辅助设计。
