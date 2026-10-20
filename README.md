# WT Camo Auto Gen

[简体中文](README.md) · [English](README.en.md)

本地载具涂装工作台：用 Codex CLI 辅助模型审计、设计草图、分区矢量编辑、材质调整、原 UV 贴图导出与海报素材制作。

仓库只包含工具、脚本、通用配置和自有工作流 skill。模型、角色素材、设计项目、生成结果、聊天记录及登录凭据保存在本地，不上传 Git。

## Windows 桌面应用

[下载最新版 Windows 应用与 SHA-256 校验文件](https://github.com/Honjoutx/WT_Camo_Auto_Gen/releases/latest)。请选择 Release 附件中的 `WT-Camo-Workbench-Windows-x64.zip`；GitHub 自动提供的 Source code 是源码包。

解压 `WT-Camo-Workbench-Windows-x64.zip`，运行 **WT Camo Workbench.exe**。内置 Python 和工作台依赖，独立窗口运行；Codex CLI、Blender 使用本机安装。顶部可切换简体中文与 English，语言选择会保留，不翻译设计稿、素材名或聊天原文。

用户工程与配置保存在 `%LOCALAPPDATA%/WT Camo Workbench/`，与应用资源分开。完整使用说明、构建和验证命令见 [桌面应用](docs/desktop.zh-CN.md)。

## 源码快速启动（Windows）

准备 **Python 3.11–3.13** 和已安装、已登录的 **Codex CLI**。下载后双击 **`start.cmd`**：

```powershell
git clone https://github.com/Honjoutx/WT_Camo_Auto_Gen.git
cd WT_Camo_Auto_Gen
.\start.cmd
```

首次创建 `.venv`、安装依赖、生成独立示例工作区，随后打开 `http://127.0.0.1:18188`。之后复用环境；依赖清单变化时才重新安装。关闭浏览器后后台服务继续运行。

端口占用时：

```powershell
.\start.cmd -Port 18190
```

指定 Python 或不打开浏览器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-workbench.ps1 -PythonPath "D:\Python313\python.exe" -NoBrowser
```

停止本启动器创建的服务及其子进程（运行中任务会中断，已保存文件保留）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-workbench.ps1
```

指定其他端口时，停止命令也传相同的 `-Port`。

## 使用流程

1. 初始项目提供原创矢量分区草图，没有游戏模型与角色素材，也不代表实际模型的 UV。
2. 在素材库添加图片/SVG，分区调整位置、等比大小、旋转、翻转、图层顺序、透明度、阴影和金属/粗糙度；支持撤销、布局存档及冲突保护。
3. 在 **Codex** 对话面板连接本机 CLI，选择模型与访问范围，发送文字或图片附件。流程选项覆盖修复、任务书、草图、分区、材质、迁移、映射检查、导出和海报。
4. **模型初始修复与拆分** 接受本机 OBJ 路径，分析 MTL、整数 UV 相位和模块归属，另存修复 OBJ/MTL、原 UV 备份及报告。自动分类需结合真实结构复核。
5. 让 Codex 按模型建立真实主要平面、面归属及原 UV 绑定。模型修复不自动完成语义平面注册；未绑定草图只能导出分区 PNG/SVG，不能冒充游戏贴图。
6. 已注册模型项目可预览和导出原 UV 图集，支持 4K/8K、指定图集/通道及可选 GPU 贴图计算。最终 PNG 按原图集归并，只导出修改过的文件，放在同一目录。

命名示例：`vehicle_body_c_camo_Basecolor.png` → `vehicle_body_Basecolor.png`，法线为 `vehicle_body_Normal.png`。内部编辑分区不增加最终图集数量。

参见 [部署说明](docs/deployment.zh-CN.md)、[设计执行规范](tools/livery-layout-editor/docs/workflow-guide.zh-CN.txt) 与 [模型绑定契约](.agents/skills/wt-camo-workflow/references/project-contract.md)。


## 导出性能

生成栏默认选择“全速 · 尽用可用资源”，也可切换均衡或串行兼容模式。全速模式按可用逻辑 CPU 和实时空闲内存安排独立平面、UV 域与原图集合并任务；保留约 2.5% 物理内存（至少 256 MiB）作为调度余量，不设固定线程数上限。单个超大任务仍受自身工作集和物理内存约束，不保证任意分辨率都能执行。

快写 PNG/映射缓存降低的是无损压缩计算量，不改变像素、位深、分辨率或原 UV，文件可能稍大。平面解码按剩余内存缓存；共用 UV 的优先级、原面覆盖顺序与共用法线归并保持一致。勾选部分文件时，会提前跳过无关 UV 域和未选通道的最终合并；依赖的完整 PBR 所有权仍保留。

GPU 选项继续负责浮雕法线、法线合成和颗粒平滑，不负责 PNG 压缩。显存池与分块根据启动时的空闲显存计算，不再固定限制为 4 GiB；设备运算串行共享缓存，同时 CPU 处理其他域。缺少 CuPy/CUDA 或设备失败时报告并回退 CPU。独立应用没有捆绑体积较大的 CUDA 运行库。

每次任务的 `evidence/export-performance.json` 记录资源预算、阶段耗时、并发峰值和缓存命中，GPU 另见 `export-acceleration.json`。选择不同模式不改变贴图清单与命名规则。

## 配置与诊断

需要指定外部工作区、Codex、Blender 或字体时，复制 `config/runtime.example.json` 为 **`config/runtime.local.json`** 后修改。后者已被 Git 忽略。环境变量也可覆盖：

```powershell
$env:WT_CAMO_WORKSPACE = "D:\LiveryProjects"
$env:WT_CAMO_CODEX = "D:\Tools\codex.exe"
$env:WT_CAMO_BLENDER = "D:\Blender\blender.exe"
.\start.cmd
```

优先识别 PATH 中的 Codex 原生程序、常见 npm 安装包、VS Code 扩展附带的 CLI，复用现有登录。Blender 只在模型预览、烘焙或渲染时需要；草图、聊天与 OBJ 修复不依赖 Blender、Node、Photoshop 或 Painter。

```powershell
.\.venv\Scripts\python.exe scripts/doctor-workbench.py
# 验证 CLI 握手、登录状态与可用模型，不发送生成任务：
.\.venv\Scripts\python.exe scripts/doctor-workbench.py --connect
```

Blender 渲染默认 AUTO 优先 GPU，否则使用 CPU；可配置严格 GPU。贴图计算的 GPU 与 Blender 分别配置，需要可用 CuPy/CUDA 环境；缺少时界面报告或回退。8K 仍受显存、内存及 PNG 写盘速度限制。

## 项目、存档和 skill

默认工作区 `data/workspace/`，每个项目独立目录，相关车型可选择共享素材库。布局存档只记录参数，不可变资源按内容摘要复用，ZIP 下载时打包。独立搬运使用 portable 输出；轻量项目需连同共享资源一起备份。不要清理仍被引用的共享池。

仓库级 [wt-camo-workflow skill](.agents/skills/wt-camo-workflow/SKILL.md) 供 Codex 自动发现。外部工作区会同步这份项目 skill，不修改全局 skill。也可输入 `$wt-camo-workflow`。规范不内置历史主题、角色或配色。旧的可选 Blender/Painter skill 保留在 `skills/blender-vehicle-livery/`。

CLI 使用自己的模型/MCP 配置，不自动获得另一聊天应用的 ImageGen 或 Photoshop MCP。Blender MCP 可通过下方入口自动安装并接入。

## 可选 Painter 与 Blender MCP

一并安装 Blender MCP 插件、注册本机 Codex CLI 并启动独立后台场景：

```powershell
.\start.cmd -WithBlenderMcp -BlenderPath "D:\Blender\blender.exe"
# 可选模型：追加 -ModelPath "D:\Models\vehicle.obj"
.\.venv\Scripts\python.exe scripts/doctor-workbench.py --blender-mcp
```

默认端口 18876，不操作现有 Blender 桌面。没有指定模型时从空场景开始。内置对话显示连接和工具发现状态；支持后台 bpy 操作与文件渲染，视口截图需要桌面环境。版本锁定、离线安装、停止与配置见 [Blender MCP 接入](docs/blender-mcp.zh-CN.md)。

原生 Vehicle Livery Agent 和 Blender 脚本保留为独立入口：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-assets.txt
powershell -File scripts/install-painter-livery-plugin.ps1
powershell -File scripts/start-painter-livery.ps1 -PainterPath "D:\Adobe\Adobe Substance 3D Painter\Adobe Substance 3D Painter.exe"
```

参见 [Painter 工作流](skills/blender-vehicle-livery/references/painter-livery-studio.md)。Painter 不属于工作台或 Blender MCP 的必要依赖。

## 目录和验证

```text
start.cmd                         一键安装/启动
scripts/*workbench*               安装、启动、停止、诊断
tools/livery-layout-editor/        编辑器、聊天、修复、烘焙/导出
.agents/skills/wt-camo-workflow/   通用执行 skill 与契约
config/runtime.example.json       本机配置模板
data/workspace/                   本地项目（Git 忽略）
skills/blender-vehicle-livery/     可选 Blender/Painter 流程
painter_plugins/                  可选 Painter 插件
```

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tools/livery-layout-editor -p "test_*.py"
```

接入采用官方 [Codex App Server 协议](https://developers.openai.com/codex/app-server)，skill 发现方式见 [Codex Skills](https://developers.openai.com/codex/skills)。协议随 CLI 版本变化，异常时先运行诊断并记录版本。
