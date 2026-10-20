"""Build the Windows desktop distribution with source-only application resources."""
from pathlib import Path
import hashlib
import io
import json
import shutil
import subprocess
import sys
import urllib.request
import importlib.metadata

REPO=Path(__file__).resolve().parents[1]


def main():
    for target in [REPO/'dist',REPO/'dist/WT Camo Workbench',REPO/'data/desktop-build/pyinstaller']:
        if not target.resolve().is_relative_to(REPO.resolve()):raise ValueError('Build target resolves outside the repository: '+str(target))
    build=REPO/'data/desktop-build';build.mkdir(parents=True,exist_ok=True)
    lock=json.loads((REPO/'config/blender-mcp.lock.json').read_text(encoding='utf-8'))
    addon=build/'vendor/addon.py';addon.parent.mkdir(parents=True,exist_ok=True)
    if not addon.exists() or hashlib.sha256(addon.read_bytes()).hexdigest()!=lock['addon_sha256']:
        with urllib.request.urlopen(lock['addon_url'],timeout=30) as response:content=response.read(2*1024*1024)
        if hashlib.sha256(content).hexdigest()!=lock['addon_sha256']:raise RuntimeError('Addon checksum failed.')
        addon.write_bytes(content)
    import resvg_py
    from PIL import Image
    png=resvg_py.svg_to_bytes(svg_string=(REPO/'desktop/app-icon.svg').read_text(encoding='utf-8'),width=256,height=256)
    Image.open(io.BytesIO(png)).save(build/'app-icon.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--workpath',str(build/'pyinstaller'),
                    '--distpath',str(REPO/'dist'),str(REPO/'desktop/workbench.spec')],cwd=REPO,check=True)
    folder=REPO/'dist/WT Camo Workbench'
    notices=folder/'third-party-licenses';notices.mkdir(exist_ok=True)
    for distribution in importlib.metadata.distributions():
        name=distribution.metadata.get('Name','unknown')
        if name.lower() in {'pip','setuptools','pyinstaller','pyinstaller-hooks-contrib','altgraph'}:continue
        for entry in distribution.files or []:
            parts=Path(str(entry)).parts
            if not any(p.endswith('.dist-info') for p in parts):continue
            if not any('license' in p.lower() or p.lower().startswith('copying') for p in parts):continue
            source=Path(distribution.locate_file(entry))
            if not source.is_file() or source.suffix.lower() not in {'','.txt','.md','.rst'}:continue
            target=notices/(name+'-'+distribution.version)/Path(*parts[1:])
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    (folder/'README.txt').write_text(
        'WT Camo Workbench\n\nRun WT Camo Workbench.exe. Keep the _internal folder beside it.\n'
        'No Python installation required. Requires Microsoft Edge WebView2 Runtime.\n'
        'Codex CLI (signed in) and Blender are optional external programs.\n'
        'User projects and settings: %LOCALAPPDATA%/WT Camo Workbench\n'
        'Switch between English and Simplified Chinese in the top toolbar.\n\n'
        '运行 WT Camo Workbench.exe，保留旁边的 _internal 目录。无需安装 Python。\n'
        '需要 Microsoft Edge WebView2 Runtime。Codex CLI 与 Blender 使用本机安装。\n'
        '项目与设置独立存放在用户数据目录；顶部可切换中英文。\n',encoding='utf-8')
    archive=shutil.make_archive(str(REPO/'dist/WT-Camo-Workbench-Windows-x64'),'zip',root_dir=REPO/'dist',base_dir=folder.name)
    with Path(archive).open('rb') as content:digest=hashlib.file_digest(content,'sha256').hexdigest()
    Path(archive+'.sha256').write_text(digest+'  '+Path(archive).name+'\n',encoding='ascii')
    print(json.dumps({'executable':str(folder/'WT Camo Workbench.exe'),'archive':archive,'sha256':digest},indent=2))


if __name__=='__main__':main()
