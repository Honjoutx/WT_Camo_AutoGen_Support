# Windows 桌面应用

应用版使用独立窗口，内置 Python、矢量栅格化、图像计算和 Blender MCP 服务端。使用时不需要另装 Python，也不需要先运行 PowerShell 或打开浏览器。

## 使用

解压 `WT-Camo-Workbench-Windows-x64.zip`，运行其中的 **WT Camo Workbench.exe**。保留旁边的 `_internal` 目录；分发时发送整个 ZIP，不能只复制 EXE。

需要 Windows 10/11 x64 和 Microsoft Edge WebView2 Runtime。缺少 WebView2 时从 [Microsoft 官方页面](https://developer.microsoft.com/microsoft-edge/webview2/)安装 Evergreen Runtime。

顶部语言选择提供简体中文和 English，首次跟随浏览器/系统语言，之后记住选择。操作按钮、属性、提示和设计流程提供英语；设计画布、素材文件名、项目名称、图层名称及已有聊天保持原文。新发给 Codex 的消息携带当前界面语言，用户的明确语言要求优先。

应用设置可以指定本机 Codex CLI 与 Blender 的程序路径；留空时自动查找。Codex 沿用本机登录，不要求另外填写 API Key。没有这两个外部程序时，仍可使用平面编辑、素材和图片导出；对话和 Blender 操作需要对应程序。

工作目录可在设置中修改，保存后重启应用。现有项目可直接选择其 workspace 根目录，不会自动扫描或复制历史工程。

## 数据与升级

默认用户数据目录：`%LOCALAPPDATA%/WT Camo Workbench/`。

- `workspace/`：项目、素材、参数存档和输出。
- `config/runtime.local.json`：本机程序路径和可选工作目录。
- `ui-preferences.json`：语言选择。
- `blender/`：独立插件、后台会话和日志。
- `logs/`、`webview/`：应用日志和窗口存储。

应用资源与用户数据分离。升级时关闭应用，再替换解压的程序目录，保留用户数据目录。使用自定义工作目录时，一并保留其共享素材池。不要在 `_internal` 中存工程或编辑程序资源。

高级启动参数支持 `--data-dir "D:\CamoAppData"` 与 `--workspace "D:\LiveryProjects"`。基础浏览器版仍可使用 `start.cmd`，互不替代。

## Blender MCP

应用设置中的“安装并启动 Blender MCP”使用打包时已校验的插件与内置服务端，无须在线安装 Python 包。Blender 本身仍使用本机安装。应用版默认连接名 `wt_camo_desktop_blender`、端口 18877，与源码版的连接分开。

后台会话从空场景开始，由 Codex 导入当前模型。它不控制现有 Blender 桌面，不会自动覆盖源模型。停止前先保存需要保留的场景。后台预览渲染到文件，不提供桌面视口截图。更多连接行为见 [Blender MCP 接入](blender-mcp.zh-CN.md)。

关闭窗口会停止当前应用的网页服务和聊天连接；已启动的独立 Blender 会话与导出任务不因此清空，需在停止前保存或等待任务完成。

## 从源码构建

在 Windows 安装 Python 3.11–3.13，并运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
```

构建环境隔离在 `.tools/desktop-build-env`；输出在 `dist/`，包括应用目录、ZIP 和 SHA-256 文件。只收集程序代码、通用配置、工作流说明、第三方许可证和固定版本插件，不收集 workspace、聊天、模型、图像素材或本机配置。

构建使用 [pywebview 的 Windows 打包方式](https://pywebview.flowrl.com/guide/freezing)和 [PyInstaller](https://pyinstaller.org/en/stable/spec-files.html)。运行时区分只读资源与可写数据，并在启动本机 Blender、Codex 时恢复系统 DLL 搜索路径，符合 [PyInstaller 外部程序说明](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application)。

验证构建产物：

```powershell
.\.tools\desktop-build-env\Scripts\python.exe scripts/test-desktop.py
# 同时验证本机 Blender、打包 MCP 和小尺寸 CPU 渲染
.\.tools\desktop-build-env\Scripts\python.exe scripts/test-desktop.py --blender "D:\Blender\blender.exe"
```

验证使用独立合成项目：隐藏的真实窗口检查中英文往返、选项内部值、原画布及布局保持不变；后台模式检查进程导出、ZIP 下载、可选 MCP、实际渲染和 Codex 工具发现，不修改用户模型。
