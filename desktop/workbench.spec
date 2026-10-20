# Build from the repository root using scripts/build-desktop.ps1.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all,copy_metadata

repo=Path(SPECPATH).parent
editor=repo/'tools/livery-layout-editor'
datas=[]
# Explicit source-only roots: never collect a user's workspace or local config.
for relative in ['tools/livery-layout-editor','.agents/skills/wt-camo-workflow','skills/blender-vehicle-livery','scripts','docs','config']:
    folder=repo/relative
    for path in folder.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in {'.py','.js','.html','.css','.json','.txt','.md','.yaml','.ps1'}:continue
        if any(x in {'__pycache__','data','cache','outputs','state','.venv','.tools'} for x in path.relative_to(folder).parts):continue
        if path.name.startswith('test_') or path.name=='runtime.local.json':continue
        datas.append((str(path),str(path.parent.relative_to(repo))))
for name in ['requirements.txt','requirements-mcp.txt']:
    datas.append((str(repo/name),'.'))
datas.append((str(repo/'data/desktop-build/vendor/addon.py'),'vendor/blender_mcp'))
binaries=[];hidden=[]
for package in ['resvg_py','blender_mcp']:
    data,binary,imports=collect_all(package)
    datas+=data;binaries+=binary;hidden+=imports
for package in ['blender-mcp','mcp','pywebview']:
    datas+=copy_metadata(package)
hidden += [path.stem for path in editor.glob('*.py') if not path.name.startswith('test_') and path.stem not in {'native_preview','gpu_bootstrap'}]
hidden += ['webview.platforms.winforms','webview.platforms.edgechromium','clr_loader','pythonnet']
a=Analysis([str(repo/'desktop/launcher.py')],pathex=[str(editor)],binaries=binaries,datas=datas,hiddenimports=hidden,hookspath=[str(repo/'desktop/hooks')],
           excludes=['PyQt5','PyQt6','PySide2','PySide6','gi','gtk','cefpython3','tkinter','matplotlib','IPython','pytest','scipy.tests','numpy.tests'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='WT Camo Workbench',debug=False,bootloader_ignore_signals=False,
        strip=False,upx=False,console=False,icon=str(repo/'data/desktop-build/app-icon.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='WT Camo Workbench')
