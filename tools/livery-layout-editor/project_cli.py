"""Create isolated studies or register an existing model-bound project."""
import argparse,re,shutil
from project import ROOT,read,write_json
from projects import ProjectManager,REGISTRY

def main():
 parser=argparse.ArgumentParser()
 sub=parser.add_subparsers(dest='command',required=True)
 new=sub.add_parser('new');new.add_argument('--id',required=True);new.add_argument('--name',required=True)
 new.add_argument('--library',default='common')
 reg=sub.add_parser('register');reg.add_argument('--config',required=True)
 args=parser.parse_args();manager=ProjectManager()
 if args.command=='new':
  if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',args.id):raise ValueError('Use a lowercase ASCII project id.')
  if args.id in manager.registry['projects']:raise ValueError('Project id already exists.')
  if args.library not in manager.registry['libraries']:raise ValueError('Unknown shared library.')
  config=dict(id=args.id,name=args.name,type='boards',directory='projects/'+args.id,
   shared_library=args.library,models=[],description='独立分区草图；请建立当前模型的真实平面和原 UV 绑定。')
  target=ROOT/config['directory']
  if target.exists():raise ValueError('Target directory already exists.')
  starter=ROOT/'projects/starter'
  if not (starter/'model-project.json').exists():raise ValueError('Starter sources missing; restore them before creating a study.')
  target.mkdir(parents=True)
  # Clone source definitions only, never user layout, chats, outputs or artwork.
  for folder in ['sources','guides','previews']:shutil.copytree(starter/folder,target/folder)
  shutil.copy2(starter/'model-project.json',target/'model-project.json')
 else:config=read(args.config)
 ident=config['id']
 if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',ident):raise ValueError('Invalid project id.')
 if ident in manager.registry['projects']:raise ValueError('Project id already exists.')
 directory=(ROOT/config['directory']).resolve()
 if not directory.is_relative_to(ROOT):raise ValueError('Project directory must stay inside the workspace.')
 if config.get('shared_library') not in [None,*manager.registry['libraries']]:raise ValueError('Unknown shared library.')
 manager.get(snapshot=config) # Validate contract, SVG inventory and required files before registration.
 manager.registry['projects'][ident]=config;manager.registry['active_project']=ident
 write_json(REGISTRY,manager.registry);print(ident)

if __name__=='__main__':main()
