"""End-to-end packaged app verification in an isolated synthetic workspace."""
from pathlib import Path
import argparse
import asyncio
import json
import os
import socket
import subprocess
import time
import urllib.request

REPO=Path(__file__).resolve().parents[1]


def api(url,path,data=None):
    request=urllib.request.Request(url+path,data=json.dumps(data).encode() if data is not None else None,
                                   headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=45) as response:return json.load(response)


async def mcp_check(exe,env,port,output):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    params=StdioServerParameters(command=str(exe),args=['--blender-mcp-stdio'],env={**env,'BLENDER_HOST':'127.0.0.1','BLENDER_PORT':str(port),'DISABLE_TELEMETRY':'true'})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            names=[t.name for t in (await session.list_tools()).tools]
            assert {'get_scene_info','get_object_info','execute_blender_code'}.issubset(names),names
            result=await session.call_tool('get_scene_info',{'user_prompt':'Read-only packaged application check.'})
            assert not result.isError,result
            # Tiny CPU-only render in our empty synthetic scene; never user models.
            code="import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.ops.object.camera_add(location=(0,0,6))\ns=bpy.context.scene\ns.camera=bpy.context.object\ns.render.engine='CYCLES'\ns.cycles.device='CPU'\ns.cycles.samples=2\ns.render.resolution_x=64\ns.render.resolution_y=64\ns.render.resolution_percentage=100\ns.render.filepath="+repr(str(output))+"\nbpy.ops.render.render(write_still=True)\nprint('APP_RENDER_OK')"
            rendered=await session.call_tool('execute_blender_code',{'code':code,'user_prompt':'Render a synthetic 64px CPU test image in the managed test scene.'})
            assert not rendered.isError and output.is_file(),rendered
            return {'tool_count':len(names),'render_created':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,default=REPO/'dist/WT Camo Workbench/WT Camo Workbench.exe')
    parser.add_argument('--output',type=Path,default=REPO/'data/desktop-verification')
    parser.add_argument('--blender',type=Path)
    args=parser.parse_args()
    exe=args.exe.resolve(strict=True);data=args.output.resolve();data.mkdir(parents=True,exist_ok=True)
    workspace=data/'workspace';config=data/'config/runtime.local.json';config.parent.mkdir(exist_ok=True)
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1',0));mcp_port=reserve.getsockname()[1]
    settings={'blender_mcp':{'port':mcp_port,'server_name':'wt_camo_desktop_verification'}}
    if args.blender:settings['blender']=str(args.blender.resolve(strict=True))
    config.write_text(json.dumps(settings),encoding='utf-8')
    env={**os.environ,'WT_CAMO_APP_DATA':str(data),'WT_CAMO_WORKSPACE':str(workspace),'WT_CAMO_CONFIG':str(config),'PYTHONUTF8':'1'}
    # The shipped application must not depend on a Python installation on PATH.
    env['PATH']=os.pathsep.join(p for p in env.get('PATH','').split(os.pathsep) if 'python' not in p.lower() and '.venv' not in p.lower())
    subprocess.run([str(exe),'--data-dir',str(data),'--workspace',str(workspace),'--self-test',str(data/'ui-check.json')],env=env,check=True,timeout=75)
    ui=json.loads((data/'ui-check.json').read_text(encoding='utf-8'));assert ui['ok'],ui
    ready=data/'ready.json';ready.unlink(missing_ok=True)
    stop_file=data/'stop-service';stop_file.unlink(missing_ok=True)
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    with (data/'service.log').open('wb') as log:
        process=subprocess.Popen([str(exe),'--headless','--ready-file',str(ready),'--stop-file',str(stop_file)],env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
    host_started=False;result={'ui':ui}
    manage=exe.parent/'_internal/scripts/blender_mcp_manage.py'
    try:
        deadline=time.monotonic()+30
        while not ready.exists() and time.monotonic()<deadline and process.poll() is None:time.sleep(.2)
        if not ready.exists():raise RuntimeError('Packaged service did not start. See service.log.')
        url=json.loads(ready.read_text())['url']
        assert api(url,'/api/studio/health')['application']=='wt-camo-workbench'
        api(url,'/api/studio/preferences',{'language':'en'})
        assert api(url,'/api/studio/preferences')['language']=='en'
        assert 'Design sketch' in api(url,'/api/workflow?language=en')['stages'][2]['title']
        project=api(url,'/api/project')
        job=api(url,'/api/jobs?project='+project['id'],{'mode':'boards','region':project['state']['active_region'],'state':project['state'],'storage_mode':'compact'})
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            job=api(url,'/api/jobs/'+job['id']+'?project='+project['id'])
            if job['status'] in ('complete','failed'):break
            time.sleep(.3)
        assert job['status']=='complete',job
        with urllib.request.urlopen(url+job['files'][0]['url'],timeout=15) as response:
            assert response.read(4)==b'PK\x03\x04'
        result['worker_export']={'status':job['status'],'files':len(job['files']),'zip_download':True}
        if args.blender:
            subprocess.run([str(exe),str(manage),'setup','--no-register'],env=env,check=True,timeout=30,capture_output=True)
            subprocess.run([str(exe),str(manage),'start'],env=env,check=True,timeout=65,capture_output=True)
            host_started=True
            result['mcp']=asyncio.run(asyncio.wait_for(mcp_check(exe,env,mcp_port,data/'render-check.png'),timeout=40))
            status=api(url,'/api/codex/status?connect=1')
            assert status['blender_mcp']['connected'] and status['blender_mcp']['codex']['ready'],status
            result['codex']={'connected':status['connected'],'signed_in':status.get('signed_in'),'tools':status['blender_mcp']['codex']['tools']}
        result['ok']=True
        (data/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        if host_started:subprocess.run([str(exe),str(manage),'stop'],env=env,timeout=20,capture_output=True)
        stop_file.touch()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)


if __name__=='__main__':main()
