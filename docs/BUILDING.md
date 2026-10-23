# Windows 构建说明

使用 Windows x64、Python 3.12，从仓库根目录执行。先完成 README 的依赖安装，再安装 requirements-dev.txt。FFmpeg 必须放到 bin/ffmpeg.exe，源码启动时的 PATH 替代方式不能满足当前打包脚本。

## 本机桌面构建

```powershell
.\.venv\Scripts\python.exe tools/configure_runtime.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean 字幕工坊.spec
```

输出为 dist/字幕工坊/字幕工坊.exe。configure_runtime.py 将当前解释器路径写入被 Git 忽略的 runtime.json。这个构建仍依赖该解释器、识别环境和系统 WebView2，适合本机使用，不能直接当作免安装版分享。

## 完整免安装构建

当前脚本需要手动准备官方运行时、模型及兼容依赖。请使用全新构建目录，避免把旧程序或使用数据混入发行物。

1. 在同一个 Python 3.12 x64 环境中安装项目、开发和识别依赖。脚本从运行它的环境收集 Whisper 的依赖闭包，建议 CPU 版 PyTorch。
2. 将 [Python 3.12.10 embedded x64](https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip) 保存为 output/portable-downloads/python-embed.zip。
3. 从 [Microsoft 官方页面](https://developer.microsoft.com/microsoft-edge/webview2/) 下载 Fixed Version 的 x64 CAB，保存为 output/portable-downloads/webview2-x64.cab。1.0.3 本地验证使用 156.0.4314.42，更换后须重新验证。
4. 构建机需要 Microsoft Visual C++ 2015–2022 x64 Redistributable。脚本从 System32 收集应用本地运行库，请核对再分发条款。
5. 下载模型到默认缓存并构建：

```powershell
.\.venv\Scripts\python.exe -c "import whisper; whisper.load_model('tiny'); whisper.load_model('small')"
.\.venv\Scripts\python.exe tools/configure_runtime.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath output/portable-app 字幕工坊.spec
.\.venv\Scripts\python.exe tools/build_portable.py
.\.venv\Scripts\python.exe tools/archive_portable.py
```

暂存目录为 output/portable-staging/字幕工坊-1.0.3，ZIP 输出到 分享包/。脚本校验模型摘要、复制嵌入式 Python 和依赖、改写相对路径配置并启用 portable.flag。归档会检查个人项目数据并生成 SHA256。请确认包内组件清单、许可证和第三方说明；MIT 不取代各运行时的许可要求，公开分发二进制须按实际构建补齐许可文本和适用的源码提供方式。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check web/app.js
node --check web/clarity.js
node --check web/reference.js
```

将 ZIP 解压到另一个带中文和空格的目录，在不依赖开发环境的条件下验证启动、Tiny / Small 中文识别、文稿核对与 MP4 导出，检查已缓存模型的离线运行。

tests/ 中的桌面、真实识别和 UI smoke 脚本是手动验证辅助，需要先阅读脚本并准备其测试服务或音频，不随普通 pytest 自动执行。发布源码请勿添加 runtime.json、data/、bin/、output/、模型、私人截图或项目文件。
