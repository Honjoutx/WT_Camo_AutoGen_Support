# WT Camo Auto Gen

面向 Blender 与 Adobe Substance 3D Painter 的载具涂装设计、素材生成和 Agent 辅助工作流。

项目提供可复用的 Codex Skill、Blender 分层涂装管线，以及原生 Substance 3D Painter 插件。仓库只保存程序、脚本、配置模板和设计规则；车辆模型、角色立绘、参考图片、生成贴图、`.spp`、`.blend` 与渲染结果不会上传到 Git。

## 主要功能

### Substance 3D Painter 插件

- 在 Painter 内提供原生 **Vehicle Livery Agent** 停靠面板。
- 截取当前 Painter 窗口并手动框选需要设计的模型表面。
- 将框选截图、Painter 工程信息、纹理集、活动图层栈和投影方式发送给 Agent。
- 复用本机 Codex/ChatGPT 登录，不需要额外配置 OpenAI API Key。
- 浏览项目现有图片素材，并拖入参考区辅助 Agent 理解角色、配色、纹理和版式。
- 支持从 Windows 资源管理器拖入图片；外部图片会版本化复制到项目目录。
- 尝试识别 Painter Assets 拖拽数据中的 `resource://` 资源标识。
- 将 Agent 生成结果导入当前 `.spp`、可选用户 Shelf，并记录素材来源。
- 自动创建可编辑的原生 Fill 图层，支持 Planar、UV、Triplanar、Spherical 和 Cylindrical 投影。
- 保留 Painter 的投影 Gizmo、蒙版、透明度、混合模式和材质通道供后续手动调整。

当前插件版本：`0.3.1`。

### Blender 涂装管线

- Blender MCP 场景检查和模型审计。
- 程序化底色、粗糙度、金属度、清漆与微表面参数。
- 二次元立绘、文字、贴花和多层图片投射。
- 结构导引图、对称约束、立绘比例保护和投影范围验证。
- JSON 预设、实时控制面板、热重载、预览渲染和 `.blend`/GLB 输出。

## 仓库结构

```text
painter_plugins/vehicle_livery_studio/   Painter 原生插件
livery-workbench/agent_bridge.py         Codex App Server 桥接
livery-workbench/server.py               本地 Agent HTTP 服务
skills/blender-vehicle-livery/           Codex 涂装 Skill 和设计规则
scripts/                                 安装、启动、构建与管线脚本
config/                                  可复用 JSON 示例和模板
requirements-assets.txt                  Painter Agent 服务所需 Python 依赖
requirements-mcp.txt                     Blender MCP 依赖
```

## 环境要求

- Windows 10/11。
- Adobe Substance 3D Painter 10.1 或更高版本。
  - 当前实现已在 Painter `11.0.1`、Python `3.11`、PySide6 环境验证。
- Python 3.11 或更高版本。
- PowerShell 7 或 Windows PowerShell 5.1。
- 已安装并登录 Codex CLI。
- 使用 Blender 功能时需要 Blender 4.x/5.x；当前主要验证版本为 Blender 5.2 LTS。

## 快速开始：Substance 3D Painter

### 1. 克隆仓库

```powershell
git clone https://github.com/Honjoutx/WT_Camo_Auto_Gen.git
cd WT_Camo_Auto_Gen
```

### 2. 安装项目本地 Python 依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-assets.txt
```

插件启动 Agent 服务时会优先使用项目中的 `.venv`。

### 3. 安装 Painter 插件

```powershell
.\scripts\install-painter-livery-plugin.ps1
```

默认安装目录：

```text
%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\vehicle_livery_studio
```

### 4. 启动 Painter

```powershell
.\scripts\start-painter-livery.ps1
```

如 Painter 安装在其他位置：

```powershell
.\scripts\start-painter-livery.ps1 `
  -PainterPath "D:\Adobe\Adobe Substance 3D Painter\Adobe Substance 3D Painter.exe"
```

也可以正常启动 Painter，在 Python 插件管理器中启用 `vehicle_livery_studio`，然后打开：

```text
Window > Vehicle Livery Agent
```

## Painter 使用流程

1. 打开或创建 `.spp` 工程，选择需要处理的 Texture Set。
2. 将 3D 视口旋转到目标设计角度。
3. 点击 **截图并框选设计区域**，框住实际需要生成涂装的表面。
4. 在 **参考素材库** 搜索素材，将图片拖入下方 Agent 参考区；也可以从资源管理器直接拖入。
5. 选择 Planar、UV 或 Triplanar 等投影方式。
6. 输入设计要求并发送给 Agent。
7. Agent 返回图片后，插件会按设置导入 Painter 并创建 Fill 图层。
8. 在 Painter 中调整投影框、蒙版、混合方式和材质通道。
9. 从框选视角和至少两个斜视角检查人物比例、边缘、遮挡和错误投射。

参考区最多保存 16 项素材。参考图片只用于帮助 Agent 思考，不会自动替换当前贴图或创建图层。

Painter 的公开 Python Resource API 不保证提供资源原图路径。因此，从 Painter Assets 直接拖入的 `resource://` 项目可能只能向 Agent 提供名称、类型和用途；需要像素级分析时，请拖入对应的本地图片文件。

## Agent 服务

Painter 面板会自动尝试启动本地 Agent 服务。也可以单独启动：

```powershell
.\scripts\start-painter-agent-service.ps1 -Port 8766
```

停止由项目脚本启动的服务：

```powershell
.\scripts\stop-painter-agent-service.ps1 -Port 8766
```

默认地址：

```text
http://127.0.0.1:8766
```

服务只监听本机回环地址。它通过 Codex App Server 复用现有登录，不会在浏览器 JavaScript 或项目设置中保存 API 凭据。

## 构建 Painter 插件

```powershell
.\scripts\build-painter-livery-plugin.ps1
```

默认输出：

```text
dist\vehicle-livery-painter-plugin-0.3.1.zip
```

`dist/` 属于本地构建产物，不提交到 Git。

## Blender 基础用法

创建项目本地 MCP 环境：

```powershell
python -m venv .tools\blender-mcp-env
.\.tools\blender-mcp-env\Scripts\python.exe -m pip install -r requirements-mcp.txt
```

启动 Blender MCP：

```powershell
.\scripts\start-blender-mcp.ps1 -ModelPath ".\SMSV\vehicle.obj"
```

运行分层二次元涂装管线：

```powershell
.\scripts\run-anime-livery.ps1 `
  -ModelPath ".\SMSV\vehicle.obj" `
  -ProjectPath ".\config\anime-liveries\pantsyr-anime-template.json" `
  -OutputDir ".\outputs\anime-test"
```

生成的 `.blend` 是分层工作版本，预览图与 `report.json` 会写入同一输出目录。

## 数据目录

- Painter 框选记录：`painter-livery-studio/state/captures/`
- Painter 插件设置：`painter-livery-studio/state/settings.json`
- Agent 生成素材：`assets/livery-studio/generated/`
- Painter 导入素材：`assets/painter-library/textures/`
- 外部参考图片副本：`assets/painter-library/references/`
- Painter 资源索引：`assets/painter-library/index.json`
- Blender 输出：`outputs/`

这些目录中的用户素材和运行时数据默认由 `.gitignore` 排除。

## 常见问题

### 插件没有出现在 Painter 中

确认 Painter 版本不低于 10.1，插件已安装到用户 `python/plugins` 目录，并在 Python 插件管理器中启用。也可以通过 `start-painter-livery.ps1` 启动。

### 出现 `QCommonStyle already deleted`

安装或更新到插件 `0.3.1` 及以上版本，然后重新加载插件。若 Painter 仍缓存旧模块，请完整重启 Painter。

### Agent 返回 HTTP 404

先点击面板中的 **连接 Agent**。确认 Codex CLI 已登录，并检查：

```powershell
codex login status
```

插件会依次从 `CAMO_CODEX_PATH`、系统命令路径，以及受支持编辑器的 `openai.chatgpt-*` 扩展中查找 Codex。

### Planar 投影覆盖了不需要的零件

截图框是构图边界，不等于模型面选择。请在 Painter 中缩小投影深度、调整 Gizmo、添加几何蒙版，或改用明确的 UV 工作流。

### 打开工程只看到底色

确认视口处于材质显示模式、生成图片已导入当前 `.spp`，并且活动 Texture Set 中存在启用 Base Color 的 Fill 图层。

## 素材与隐私边界

请勿提交授权受限的车辆模型、角色立绘、私人参考包、生成渲染、`.spp`、`.blend` 或凭据。仓库的 `.gitignore` 已排除当前常用素材、输出和运行时目录；新增素材位置后仍应在推送前检查：

```powershell
git status
```
