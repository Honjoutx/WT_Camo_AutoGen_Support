# Blender MCP 接入

桌面应用已内置服务端和校验过的插件，可在应用设置中启动；默认使用 `wt_camo_desktop_blender` 与 18877 端口。数据保存在用户数据目录。下文的虚拟环境安装和 PowerShell 命令针对源码版，详见 [桌面应用](desktop.zh-CN.md)。

工作台可安装并启动独立后台 Blender，供内置 Codex 对话操作。无需点击 Blender 面板，不占用已打开的 Blender 场景，也不依赖示例车辆、旧预设或 Painter。没有指定模型时创建空场景。

## 一起启动

先安装并登录 Codex CLI，准备 Python 3.11–3.13 和 Blender **4.2 或更新版**。在仓库目录执行：

```powershell
.\start.cmd -WithBlenderMcp -BlenderPath "D:\Blender\blender.exe"
# 可选：在新后台进程中加载自己的模型
.\start.cmd -WithBlenderMcp -BlenderPath "D:\Blender\blender.exe" -ModelPath "D:\Models\vehicle.obj"
```

支持 OBJ、FBX、GLB/GLTF、BLEND。只读取源文件，不自动保存或覆盖。后台 MCP 中执行的命令仍然可以修改场景或写文件；保存位置由当前任务决定。

首次建立隔离环境 `.tools/blender-mcp-env`，安装 `requirements-mcp.txt`，下载固定版本的 Blender 插件，校验 SHA-256，并通过官方 `codex mcp add` 注册独立条目 **`wt_camo_blender`**。不会覆盖同名但不属于本安装的配置；出现冲突可在 local config 设置新的 `server_name`。修改前将 CLI 的 config.toml 按内容摘要备份到 `data/blender/config-backups/`，不复制登录文件。

后续启动复用安装和已识别的后台会话。未提供 `-WithBlenderMcp` 时仅启动工作台。Blender 会话独立于网页服务，关闭网页或停止工作台不会丢弃后台场景。

在 Codex 对话中点击“连接本机 CLI”，侧栏显示 Blender 进程连接和 CLI 工具发现状态。如果安装时工作台已经运行，等待当前对话任务结束，再点击“重新连接”；空闲连接会加载更新后的配置。

## 单独管理

```powershell
# 安装及 CLI 注册
powershell -ExecutionPolicy Bypass -File scripts/setup-blender-mcp.ps1
# 只安装到本仓库，不修改全局 CLI 配置
powershell -ExecutionPolicy Bypass -File scripts/setup-blender-mcp.ps1 -NoRegister
# 启动、查看状态、停止
powershell -ExecutionPolicy Bypass -File scripts/start-blender-mcp.ps1
.\.venv\Scripts\python.exe scripts/blender_mcp_manage.py status
powershell -ExecutionPolicy Bypass -File scripts/stop-blender-mcp.ps1
```

Blender 路径可长期填写到 `config/runtime.local.json` 的 `blender`，或环境变量 `WT_CAMO_BLENDER`。更换模型前先显式停止会话；启动器不会自动清空已运行的场景。停止前可让 Codex 把场景另存为自己的 `.blend`。

端口默认 **127.0.0.1:18876**，不与通常使用 9876 的其他 Blender MCP 争用。`runtime.example.json` 中的 `blender_mcp` 可配置 `enabled`、`port`、`server_name`；环境变量 `WT_CAMO_BLENDER_MCP_PORT` 可覆盖端口。改变端口前在旧配置下停止旧会话，再启动并重跑 setup 更新全局注册。

工作台的 app-server 同时传入该连接的进程级配置，不依赖外部工作目录是否受信任；即使使用 `-NoRegister`，内置聊天仍可发现工具。普通终端 Codex 使用全局注册。配置方式见官方 [Codex MCP 文档](https://developers.openai.com/codex/mcp)。登录仍复用 CLI，无需额外 API Key。

## 后台能力与限制

上游 Blender 插件的桌面服务依赖 `bpy.app.timers`，直接 `blender -b` 无法执行请求。本仓库的 `blender_mcp_host.py` 在 Blender 主线程接收同一套 socket JSON 命令，调用已安装上游插件的处理器，保持 bpy 操作位于主线程。

工作台只向 Codex 开放三个核心工具：`get_scene_info`、`get_object_info`、`execute_blender_code`。可检查模型、材质、UV，执行场景操作，并通过代码设置相机和渲染到文件。后台没有桌面视口，不能调用视口截图；需要预览时渲染 PNG 后读取。上游的 Poly Haven、Sketchfab、Hyper3D、Hunyuan 集成默认关闭，遥测通过环境变量关闭。

插件仅安装到本仓库的 `data/blender/scripts/addons/`，启动时自动启用。Blender 用户配置目录也隔离在 `data/blender/`，不保存全局偏好。监听仅限回环地址；识别到其他仓库或其他程序占用端口时拒绝复用，不终止其他 Blender。

## 验证与故障定位

```powershell
# 插件摘要、后台场景身份、实际 Codex app-server 工具发现
.\.venv\Scripts\python.exe scripts/doctor-workbench.py --blender-mcp
# 通过 MCP stdio 真正读取场景并执行只读 bpy 代码
.\.tools\blender-mcp-env\Scripts\python.exe scripts/test-blender-mcp.py
```

日志为 `data/blender/host.out.log` 和 `host.err.log`。安装记录、会话身份、环境和下载的插件均留在本地，Git 不收录。诊断不读取或打印登录 token。默认无须打开 Blender 桌面。

网络无法下载时，可准备 `config/blender-mcp.lock.json` 指定提交的 `addon.py`，执行 `setup-blender-mcp.ps1 -AddonFile "D:\Offline\addon.py"`；仍校验相同摘要。Python 依赖可按标准 pip 离线 wheel 方式配置。升级依赖或插件后，应先停止旧会话，再重新安装和启动。

上游为 [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender)，采用 MIT 许可证。配套提交和插件摘要记录在 `config/blender-mcp.lock.json`，服务端版本记录在 `requirements-mcp.txt`。本接入已用 Blender 5.2.2 LTS 验证；其他版本需运行上述诊断，不假定所有上游工具均适用于后台。
