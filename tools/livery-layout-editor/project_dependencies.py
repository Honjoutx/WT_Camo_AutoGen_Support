"""Persistent material references and disposable generation-cache inputs."""
from pathlib import Path
import hashlib,shutil

def pin_file(source,folder,label):
 source=Path(source);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 digest=hashlib.sha256(source.read_bytes()).hexdigest()
 target=folder/(label+'-'+digest[:16]+source.suffix.lower())
 if not target.is_file():shutil.copy2(source,target)
 if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
  raise ValueError('固定项目资源的校验失败：'+str(target))
 return target,digest

def cache_inputs_exist(manifest,contract=None):
 manifest=Path(manifest)
 paths=[manifest,manifest.parent/'layout.json']
 if contract is not None:paths.append(Path(contract))
 return all(p.is_file() for p in paths)
