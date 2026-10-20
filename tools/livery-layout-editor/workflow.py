"""Project-specific design playbook and explicit workflow context for Codex."""
from pathlib import Path
import json
from project import ROOT, HERE, read

GUIDE=HERE/'docs/workflow-guide.zh-CN.txt'
STAGES=[
 dict(id='intake',title='01 模型修复与拆分',summary='分析源模型和原 UV，按实际结构合并大模块。',prompt='先审计输入模型、MTL、纹理路径和原 UV。按实际结构将车体、炮塔主结构、炮管、附加组件、可拆装甲合并成大模块；履带可排除于设计。机枪盾、独立盒子和镜体按装配关系归组件，主装甲归主结构。仅修复已证实的整数 UV 相位，不重排、不逐顶点取模、不焊接改变几何。导出修复 OBJ/MTL、原 UV 备份、模块清单和未覆盖报告。不能照搬其他模型的对象序号。使用模型修复入口执行，或读取其 intake-manifest.json 继续建立项目。'),
 dict(id='brief',title='02 需求与素材整理',summary='记录主题、角色、字体、配色、区域和交付物。',prompt='建立本项目设计任务书：主题、主辅色、角色设定、素材来源、字体、需要角色的平面、展示方向、共享 UV 限制、材质目标和导出文件。保留原素材；去背不改变角色。以当前任务书为准。列出缺少的信息，先推进不依赖这些信息的工作。'),
 dict(id='sketch',title='03 设计草图',summary='先设计宏观走向、明暗和疏密，再做细节。',prompt='先完成独立可查看的设计草图，再继续正式设计。车体与炮塔分别按真实主要平面构图；以大色块、曲线边界、明暗、疏密、视觉重心和立绘安全区说明方案。在装配视角检验两侧与顶部连接。草图保存为项目文件，并记录对应版本及后续变化。'),
 dict(id='planes',title='04 大模块平面分区',summary='主要覆盖面整体设计；突出件和倾斜面独立判断。',prompt='按当前模型的实际主要覆盖面分区：车体左右和顶部、炮塔左右和顶部与正面、炮管及附件。主侧面只覆盖主要结构，不将该方向所有可见零件一起投影。相连共面板应合并，倾斜面按真实角度展开；镜体、突出组件单独处理，避免切割角色。根据实际面建立覆盖轮廓、设计坐标、面编号和遮罩，不能靠大矩形覆盖。'),
 dict(id='design',title='05 分区涂装与角色',summary='每个平面独立设计，装配后保持整体连续。',prompt='每个主要平面独立设计，不能一张图套整车。先完成框架走向与双色交界，再分层增加纹样；整车物理纵向统一渐变，车体与炮塔的边界在装配后应形成平滑连续曲线。密集元素要有层次，极细线融入背景，主线稍粗；避免机械重复刻度。背景优先矢量，保留要求的原始图像纹样，不用模糊生图代替清晰边缘。独立立绘保持服饰配件一致；按指定方向、放大和裁切，完整背景画框与去背立绘分开。背景即使没有角色也应完整。'),
 dict(id='materials',title='06 材质与法线',summary='按图层设置金属、粗糙和浮雕；保护结构细节。',prompt='按图层和实物区分底漆、图案、角色、文字、金属、橡胶、布料和镜片，设置金属度、粗糙度、阴影与浮雕。参数参考当前项目任务书和已接受的质感，不套用其他项目数值。高亮装饰按设计需要设置，法线平滑保留接缝、螺栓、刻线及硬边。检查实际渲染的高光、曝光和噪点。'),
 dict(id='migration',title='07 同族车型迁移',summary='共享物理布局，分别注册各自原 UV。',prompt='同族车型以物理坐标和共同锚点迁移布局，不能直接复用 UV 图集。保持主尺寸与原艺术布局，前部变短时裁掉缺失区域，不缩放挤压全图。将不同附件单独登记。检查左右侧板、可拆爆反、雷达、镜体和排气格栅，明确共享 texel 的权威区域与优先级。对照原始完整模型验证几何、材质和 UV，而非假定所有基础件完全相同。'),
 dict(id='mapping',title='08 漏色与映射修复',summary='逐面追查归属、遮罩、材质绑定和导出。',prompt='从用户指出的实际部件定位 source_object / face IDs，依次检查原 UV、paint/owner、分区归属、art_uv、native mask、material recipe、atlas merge priority、最终导出文件及游戏 .blk 绑定。区分编辑预览正常、原 UV 图集错误、游戏文件未替换等情况。镜像或共享 UV 不可凭移动整张贴图修复。补齐上下表面、内侧竖面、车尾侧板、后顶盖和小长条。先给出证据，再只修受影响域；不要借修复改整车设计。'),
 dict(id='export',title='09 原 UV 贴图导出',summary='2K 起，支持 4K / 8K、指定图集与 GPU。',prompt='仅导出相对原图修改过的原始材质图集，不将内部板块/材质域当作最终文件数量。保留原 UV；至少 2K，按需 4K/8K；GPU 为可选，渲染使用 GPU。最终图片平铺在一个目录，文件名删除 _c/_n 到通道后缀前的部分，使用 _Basecolor/_Metallic/_Roughness/_Smoothness/_Normal/_Height。可选择具体图集和通道。PNG 为中间交付；若用于游戏发布，按游戏要求另做通道打包、DDS/TGA 与 .blk，不改 UV。保存清单、来源、缓存依赖；旧输出清理后必须能从有效源重建。'),
 dict(id='poster',title='10 渲染与海报素材',summary='按当前构图渲染，人物、背景与排版分别交付。',prompt='先制作干净渲染，保留用户手调模型与相机。场景、构图、光照、背景和样式以当前任务书为准，不继承其他项目。需要时恢复原履带及贴图，使用许可清楚的场景。透明需求区分天空、地板、阴影和道具，充分降噪。原模型渲染不能被生图重绘畸变；人物、阴影、背景、文字和边框分层提供。'),
]
CORE_RULES=f'''你是这个本地涂装工作台的设计执行助手。按当前消息指定的界面语言交流，直接完成用户已授权的工作。
会话开始或规范变更时阅读 {GUIDE}；后续只读取当前阶段需要的当前项目配置与源文件，遵循用户最新明确要求。默认不读取、罗列或向界面暴露历史项目案例、角色和配色；只有用户明确要求参考时才读取相关历史资料。
保留模型原 UV、几何、法线和原素材；任何修复先备份并给出可追溯证据。先草图再正式设计。大结构按主要平面设计，突出件单独处理。
只在当前明确项目操作，不改其他车型或全局配置；跨项目迁移必须由用户选择。操作版本化保存，不能覆盖手工布局。
新生成任务默认使用轻量存档 storage_mode=compact，复用固定资源，下载时打包，避免反复复制模型与内嵌整套贴图。不要删除共享资源池；独立搬运时采用 portable。具体存储约束见 {HERE/'docs/storage.zh-CN.txt'}。
优先后台 Blender / 文件 / CLI；Photoshop 可用时作为可编辑中间件，避免直接操控桌面。确认本 CLI 实际工具能力，不声称能调用宿主聊天界面的 ImageGen/MCP；能力缺失时继续矢量、布局、UV等独立工作并明确说明。
谨慎对待游戏素材和立绘授权；上传合规须查现行条款，不能保证自动通过。不要主动发布、发消息或收费。
未完成事项不得标完成；给出修改文件、结果和必要的局部验证。减少重复全量导出与无意义截图。
'''

ENGLISH_STAGES=[
 ('01 Model repair and grouping','Inspect source geometry and UVs; group by physical structure.'),
 ('02 Brief and source assets','Record the theme, characters, typography, palette and deliverables.'),
 ('03 Design sketch','Establish flow, contrast and density before adding detail.'),
 ('04 Principal surface regions','Design large physical surfaces; isolate slopes and protrusions.'),
 ('05 Surface art and characters','Compose each surface separately and check assembled continuity.'),
 ('06 Materials and normals','Set metallic, roughness and relief while retaining structural detail.'),
 ('07 Related model migration','Share physical layouts; register each model’s original UVs.'),
 ('08 Coverage and mapping fixes','Trace faces, masks, material bindings and final atlases.'),
 ('09 Original UV texture export','Export changed atlases with channel selection and optional GPU compute.'),
 ('10 Rendering and poster assets','Keep accepted cameras; deliver renders and design elements separately.')]

def stage_rows(language):
 return [{**s,'title':en[0],'summary':en[1]} for s,en in zip(STAGES,ENGLISH_STAGES)] if language=='en' else STAGES

def catalogue(language='zh-CN'):
 guide=HERE/'docs'/('workflow-guide.en.txt' if language=='en' else GUIDE.name)
 return {'stages':stage_rows(language),'guide_path':str(guide),'guide':guide.read_text(encoding='utf-8'),'version':3,'language':language}

def context(manager,pid,region=None,stage=None,notes='',language='zh-CN'):
 from runtime import FROZEN
 import sys
 c=manager.config(pid);P=ROOT/c['directory'];details={'project_id':pid,'project_directory':str(P),'workspace':str(ROOT),'project_config':c,'selected_region':region}
 details.update(tool_directory=str(HERE),workflow_skill=str(HERE.parents[1]/'.agents/skills/wt-camo-workflow/SKILL.md'))
 details['python_worker_launcher']=[sys.executable,'--run-script'] if FROZEN else [sys.executable]
 if c['type'] in ['boards','native-uv']:
  details.update(contract=str(P/'model-project.json'),layout=str(P/'state/current.json'))
 if c.get('surface_directory'):
  contract=read(P/c['surface_directory']/'contract.json');details.update(surface_contract=str(P/c['surface_directory']/'contract.json'),native_contract=str(P/contract['native_contract']),model=str(P/contract['model']),layout=str(P/'state'/('surface-'+Path(c['surface_directory']).name)/'current.json'))
 if region:details['region']=contract.get('regions',{}).get(region) if c.get('surface_directory') else None
 stage_row=next((s for s in stage_rows(language) if s['id']==stage),None)
 reply='Reply in English unless the user asks for another language.' if language=='en' else '除非用户另有要求，以中文交流。'
 return '\n\n'.join([CORE_RULES,reply,'Current interface context:\n'+json.dumps(details,ensure_ascii=False,indent=2),('Current workflow: '+stage_row['title']+'\n'+stage_row['prompt']) if stage_row else '',('Additional user requirements: '+notes) if notes else ''])
