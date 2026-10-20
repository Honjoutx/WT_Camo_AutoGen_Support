# 部署、迁移与开发

可直接使用内置 Python 的 [Windows 桌面应用](desktop.zh-CN.md)，或按下文启动源码版。两种界面均支持中英文选择。

## 初次部署与配置

Windows 10/11，PowerShell 5.1/7，Python 3.11–3.13。安装并登录 Codex CLI 后运行 start.cmd。本工具不安装 CLI 或修改其登录，不要求额外 API Key。首次离线部署需自行准备 requirements 对应 wheel。

启动器创建 `.venv`，仅在依赖清单摘要变化时安装。后台服务仅监听 127.0.0.1，检查 Host 与 Origin。默认端口 18188，可通过 `-Port` 修改。日志与 PID 在 `data/logs/`。`stop-workbench.ps1` 核对进程命令行，避免结束复用 PID 的其他程序。

配置优先级：`WT_CAMO_*` 环境变量 > `config/runtime.local.json` > 自动发现/默认值。相对 workspace 路径从仓库根解析。字体仅从本机读取，不分发字体文件。诊断 `scripts/doctor-workbench.py --connect` 不打印 token。

Codex npm shim 仅用于定位原生 CLI，不经 shell 执行用户消息。特殊安装布局可设置 `WT_CAMO_CODEX` 为实际 codex.exe。默认工作区在仓库内，可发现祖先 `.agents/skills/`；外部工作区同步本项目自己的 skill，不改其他 skill 或全局配置。

## 项目创建与模型绑定

初始示例只是一份矢量布局。可以让 Codex 创建独立项目，或执行：

```powershell
.\.venv\Scripts\python.exe tools/livery-layout-editor/project_cli.py new --id vehicle-study --name "Vehicle study"
```

只创建草图，不完成模型绑定。OBJ 修复输出在 `projects/_intake/intake-*/`，不覆盖源文件。按车体、炮塔、炮管、附件、可拆装甲合并，履带排除于设计。auto UV 策略是保守启发式，不识别所有加密或复用；必须查看整数平移与未识别对象报告。

真实平面注册由 Codex/设计者依据网格建立：主要侧面、顶部、斜面和凸起附件分别判断，登记来源面、设计坐标、遮罩、原材质域与图集。字段和数组见 [项目契约](../.agents/skills/wt-camo-workflow/references/project-contract.md)。不能从截图矩形猜测全部面。

已有符合契约的项目放进工作区后，可写一份 registry entry JSON 注册：

```powershell
.\.venv\Scripts\python.exe tools/livery-layout-editor/project_cli.py register --config "D:\Imports\project-entry.json"
```

项目目录必须位于 workspace。素材从添加入口或项目 assets/imported 导入。搬运已有设计时保留相对路径、原模型/纹理、绑定、源 SVG、当前布局及共享池中被引用的资源。不要将旧 outputs 全量复制进代码仓库；含旧绝对路径或旧项目类型的工程需在副本中迁移，不能宣称即插即用。

## 存档和输出

compact 使用内容摘要复用不可变文件，参数存档不携带整套模型，ZIP 用配方在下载时流式生成。portable 提供独立副本。轻量 .blend 可能外链共享图片，不能移动后删除资源池。

原图集导出保护未涂装区域，按原 atlas 归并，只输出修改过且被选择的通道。支持 Basecolor、Metallic、Roughness、Smoothness、Normal、Height。文件名冲突通过别名表记录。没有有效源的通道不应伪造。

4K/8K SVG 按目标分辨率栅格化，放大低清位图不会自动恢复细节。游戏法线/材质通道、DDS/TGA、.blk 绑定另按模板处理。

## 渲染和外部应用

通过 `WT_CAMO_BLENDER` 或 local config 配置 Blender。AUTO 尝试 GPU，失败后记录实际 CPU；`device=GPU`、`silent_cpu_fallback=false` 可要求严格 GPU。backend 默认 AUTO，也可按本机 Blender 支持指定。程序不保存全局 Blender 偏好。

Photoshop、Painter、图像生成与 Blender MCP 均为可选。优先后台文件/CLI；不默认操控桌面。Painter 原生面板仍使用独立 Agent bridge。Blender MCP 可用 `start.cmd -WithBlenderMcp` 自动安装、注册并启动，详见 [接入说明](blender-mcp.zh-CN.md)。其全局注册只管理独立命名条目，基础部署不修改 CLI 配置。

## 更新和排错

- 升级前停止服务，备份 workspace、共享池和本机配置。git pull 后重开 start.cmd。
- 端口占用时指定其他 `-Port`。启动器只复用识别为本工具的服务。
- 启动失败查看 `data/logs/workbench-端口.err.log`，用相同 .venv 运行 doctor。
- CLI 失败检查实际程序路径、`--version` 和 `login status`。不要将 auth.json 放进项目。
- 生成失败查看任务 job.json、worker.log 和 evidence。已删旧输出应从有效源重建，不借用其他项目映射。
- 界面检测布局、源稿、遮罩、素材与配置更新。有未保存手动改动时先保留副本并处理冲突；CSS 可热更新，结构/脚本按提示安全刷新。

基础 unittest 使用合成数据，不读取历史项目。无 Node 时跳过可选 JS 对照测试。发布前检查 staged 文件，只提交代码与通用规范，不提交 data、.venv、本机配置、模型、素材、聊天或凭据。
