<p align="center"><img src="assets/subtitle-workshop-icon.png" width="112" alt="字幕工坊图标"></p>

# 字幕工坊 · 1.0.3

Windows 本地字幕编辑软件：导入音视频，识别中文语音，学习个人断句习惯，再与文稿对照校对。素材在本机处理。

**当前版本固定为 1.0.3。** 本仓库发布源码、测试和打包工具；GitHub 自动生成的 Source code 压缩包是源码，不是免安装程序。面向 Windows 10 / 11 x64，开发环境使用 Python 3.12。

## 功能

- **本地语音识别**：Whisper Small / Tiny，识别后统一为简体中文，优先使用词级时间。
- **断句习惯**：从最终版 SRT / ASS 学习常用字数、换行和标点习惯，支持保护词与完整历史语句断点复用，可预览前后对比再应用。
- **文稿交叉核对**：导入 DOCX、TXT、Markdown 或粘贴文稿，与独立语音识别结果逐条对照、试听并选择采用。
- **字幕校对**：编辑时间与文字、拆分合并、偏移、查找替换、繁转简、撤销重做。
- **样式与导出**：预览样式，导出烧录字幕的 MP4、SRT、ASS、TXT；保存与导出页显示新导出文件的路径和结果。
- **项目保存**：自动恢复最近项目，另存 .zmproj，确认成稿后才记住断句。

## 从源码运行

安装 [Python 3.12 x64](https://www.python.org/downloads/)、[Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) 和支持 libass、libx264 的 [FFmpeg](https://ffmpeg.org/download.html)。将 ffmpeg.exe 放到 bin/ffmpeg.exe 或加入 PATH。

在仓库根目录运行 PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-recognition.txt
.\.venv\Scripts\python.exe app.py
```

源码模式默认用当前 Python 环境识别，无需填写本机路径。若已有 runtime.json，其中的配置优先；迁移电脑后请重新配置或移走旧配置。首次使用未缓存模型需要联网下载，之后可离线识别。可以先不安装识别依赖，体验已有字幕的编辑与导出。

浏览器调试模式：使用上述 Python 运行 app.py --browser --port 18747。只监听本机，此模式选择文件时输入完整本地路径。

## 使用流程

1. 在「断句习惯」导入已校对完成的 SRT / ASS，检查规则并保存；新建习惯不会继承其他习惯的样本。
2. 导入音视频，选中习惯，再自动识别。已有字幕也可以导入后预览并应用断句。
3. 如有文稿，点击「导入文稿」或「粘贴文稿」。识别完成后自动对照；已有字幕点击「对照当前字幕」。
4. 逐条试听差异，勾选后「采用勾选项」。文稿不灌入语音模型，不自动覆盖识别结果；两边都可能有错。
5. 校对完成后「确认并记住断句」，选择样式并导出。SRT 不带样式，ASS 保留样式，MP4 默认 H.264 / AAC、保留源分辨率。

文字中的 Enter 表示画面换行，「拆分」表示分成两条字幕。空格播放 / 暂停，Ctrl+S 另存项目；非输入状态 Ctrl+Z 撤销、Ctrl+Shift+Z 重做。

## 数据与隐私

- 普通运行数据位于 %LOCALAPPDATA%/SubtitleWorkshop/：autosave.json 是最近项目，profiles.json 是习惯与样本，建议定期备份。
- 免安装构建中，EXE 旁有 portable.flag 时，数据保存在程序旁的 data/，请解压到有写入权限的目录。
- 文稿全文和核对记录随项目保存。.zmproj 引用素材路径，不包含原视频；拖入文件会创建本地副本。
- 视频、音频、文稿和样本在本地处理。本仓库不包含作者素材、项目、模型缓存或本机配置。
- 自动保存要求字幕非空、时间有效且不重叠；界面显示未保存时请先修正再退出。

## 已知边界

- 习惯学习使用统计、分词、保护词和历史断点，没有微调模型，不保证新句子与人工断句完全一致。
- 文稿对照是顺序文本匹配，匹配度不是正确率。大段删改、换序、跨字幕差异和未读文稿需人工核实，不会自动补时间轴。
- 文稿上限 20000 字。DOCX 读取正文和表格，不读取图片或修订删除内容；旧 DOC、PDF、扫描件需另存为 DOCX / TXT。
- 采用文稿保留时间，清除对应旧词级对齐；重新断句可能按字数估算，请试听。只有 SRT / ASS 时也需检查新断点。
- ASS 导入只读取文字和时间，不导入原样式、特效。预览与 FFmpeg/libass 渲染可能略有差异，以成片为准。
- 暂不提供字幕 OCR、翻译、说话人区分、字幕动画或批量视频识别。

## 开发与打包

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
node --check web/app.js
node --check web/clarity.js
node --check web/reference.js
```

自动测试覆盖字幕处理、规则应用、文稿对照、接口和便携运行配置。真实识别和桌面窗口检查需要模型与桌面环境，不包含在普通单元测试中。详见 [构建说明](docs/BUILDING.md) 和 [版本记录](CHANGELOG.md)。

欢迎通过 Issues 提交复现步骤、预期结果和脱敏示例，请勿上传未经授权的素材或私人文稿。

## 许可证

原创代码采用 [MIT License](LICENSE)。依赖、模型、字体与运行时遵循各自许可证，见 [第三方说明](THIRD_PARTY_NOTICES.md)。应用图标由 AI 辅助设计。
