"""Desktop shell and frozen worker entry point; no server or GUI on import."""
from pathlib import Path
import argparse
import io
import json
import os
import runpy
import sys
import threading
import time
import traceback

BUNDLE=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
EDITOR=BUNDLE/'tools/livery-layout-editor'
sys.path.insert(0,str(EDITOR))
WORKER_MODE=any(a.startswith(('--headless','--self-test','--run-script','--blender-mcp-stdio')) or a.endswith('.py') for a in sys.argv[1:])


def restore_streams(log_path=None):
    """Windowed executables still need inherited pipes in MCP/worker mode."""
    for name,number,mode in [('stdin',-10,'r'),('stdout',-11,'w'),('stderr',-12,'w')]:
        if getattr(sys,name) is not None:continue
        stream=None
        if os.name=='nt':
            import ctypes,msvcrt
            kernel=ctypes.windll.kernel32
            kernel.GetStdHandle.restype=ctypes.c_void_p
            handle=kernel.GetStdHandle(number)
            if handle not in (None,0,ctypes.c_void_p(-1).value):
                try:
                    fd=msvcrt.open_osfhandle(handle,(os.O_RDONLY if mode=='r' else os.O_WRONLY)|os.O_BINARY)
                    stream=io.TextIOWrapper(os.fdopen(fd,mode+'b',buffering=0),encoding='utf-8',errors='replace',line_buffering=True)
                except OSError:pass
        if stream is None:
            target=str(log_path) if log_path and mode=='w' else os.devnull
            stream=open(target,'a' if mode=='w' else 'r',encoding='utf-8',errors='replace',buffering=1)
        setattr(sys,name,stream)


def script_dispatch(arguments):
    if arguments and arguments[0]=='--run-script':arguments=arguments[1:]
    if not arguments or not arguments[0].endswith('.py'):return None
    path=Path(arguments[0]).resolve()
    if not path.is_relative_to(BUNDLE.resolve()) or not path.is_file():
        raise ValueError('Only application-bundled worker scripts can be dispatched.')
    restore_streams();sys.argv=[str(path),*arguments[1:]]
    sys.path.insert(0,str(path.parent));runpy.run_path(str(path),run_name='__main__')
    return 0


def serve(port=0):
    import bootstrap
    bootstrap.sync_skill()
    if not (bootstrap.ROOT/'projects/registry.json').exists():bootstrap.initialize()
    import server
    http=server.ThreadingHTTPServer(('127.0.0.1',port),server.Handler)
    http.daemon_threads=True
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    return http,server


def main(arguments=None):
    arguments=list(sys.argv[1:] if arguments is None else arguments)
    if '--blender-mcp-stdio' in arguments:
        restore_streams()
        from blender_mcp.server import main as mcp_main
        mcp_main();return 0
    dispatched=script_dispatch(arguments)
    if dispatched is not None:return dispatched
    parser=argparse.ArgumentParser(description='WT Camo Workbench desktop application')
    parser.add_argument('--port',type=int,default=None)
    parser.add_argument('--data-dir')
    parser.add_argument('--workspace')
    parser.add_argument('--headless',action='store_true',help='Run the bundled service without a window (diagnostics).')
    parser.add_argument('--ready-file',help='Write service readiness metadata to this file.')
    parser.add_argument('--stop-file',help='Gracefully stop diagnostic headless mode when this file appears.')
    parser.add_argument('--self-test',help='Run a hidden real-window UI check and write JSON results.')
    args=parser.parse_args(arguments)
    if args.data_dir:os.environ['WT_CAMO_APP_DATA']=str(Path(args.data_dir).resolve())
    if args.workspace:os.environ['WT_CAMO_WORKSPACE']=str(Path(args.workspace).resolve())
    from runtime import APP_DATA,ROOT,FROZEN,CONFIG
    os.environ.update(WT_CAMO_APP_DATA=str(APP_DATA),WT_CAMO_WORKSPACE=str(ROOT),WT_CAMO_CONFIG=str(CONFIG))
    log_dir=APP_DATA/'logs';log_dir.mkdir(parents=True,exist_ok=True)
    restore_streams(log_dir/'desktop.log')
    # Python multiprocessing needs this before any numerical worker can spawn.
    import multiprocessing
    multiprocessing.freeze_support()
    port=args.port if args.port is not None else (0 if args.headless or args.self_test else 18189)
    try:http,service=serve(port)
    except OSError:
        if args.port is not None or port==0:raise
        http,service=serve(0)
    url='http://127.0.0.1:'+str(http.server_address[1])
    info={'application':'wt-camo-desktop','url':url,'pid':os.getpid(),'frozen':FROZEN,'workspace':str(ROOT),'data_directory':str(APP_DATA)}
    if args.ready_file:
        Path(args.ready_file).parent.mkdir(parents=True,exist_ok=True)
        Path(args.ready_file).write_text(json.dumps(info),encoding='utf-8')
    try:
        if args.headless:
            print(json.dumps(info),flush=True)
            while not (args.stop_file and Path(args.stop_file).exists()):time.sleep(.25)
            return 0
        import webview
        webview.settings['ALLOW_DOWNLOADS']=True
        window=webview.create_window('WT Camo Workbench',url,width=1500,height=960,min_size=(1100,720),
                                     hidden=bool(args.self_test),text_select=True,background_color='#eef5f2')
        test_error=[]
        def check_window():
            if not args.self_test:return
            try:
                deadline=time.monotonic()+45
                while time.monotonic()<deadline:
                    if window.evaluate_js("!!window.LiveryI18n && !!document.querySelector('#regions .region-card') && document.getElementById('loading').hidden && document.getElementById('canvas').children.length>0"):break
                    time.sleep(.25)
                else:raise RuntimeError('UI did not finish loading.')
                original=window.evaluate_js("document.querySelector('#regions .region-card span').textContent")
                window.evaluate_js("(()=>{const text=document.createElementNS('http://www.w3.org/2000/svg','text');text.id='i18n-artwork-probe';text.textContent='撤销';document.getElementById('canvas').append(text);const chat=document.createElement('p');chat.className='chat-rich';chat.id='i18n-chat-probe';chat.textContent='撤销';document.getElementById('codex-messages').append(chat);})()")
                original_state=window.evaluate_js('JSON.stringify(state)')
                original_art=window.evaluate_js("document.getElementById('canvas').innerHTML")
                window.evaluate_js("window.LiveryI18n.setLanguage('en')")
                time.sleep(.25)
                english=window.evaluate_js("({lang:document.documentElement.lang,undo:document.getElementById('undo').textContent,category:document.querySelector('#asset-category option').value,name:document.querySelector('#regions .region-card span').textContent})")
                assert english['lang']=='en' and english['undo']=='Undo',english
                assert english['category']=='全部' and english['name']==original,english
                assert window.evaluate_js('JSON.stringify(state)')==original_state,'Language switching modified layout state.'
                assert window.evaluate_js("document.getElementById('canvas').innerHTML")==original_art,'Language switching modified artwork.'
                assert window.evaluate_js("document.getElementById('i18n-chat-probe').textContent")=='撤销','Language switching modified chat content.'
                header=window.evaluate_js("({bottom:document.querySelector('header').getBoundingClientRect().bottom,control:Math.max(...Array.from(document.querySelectorAll('.top-actions button,.top-actions select')).map(e=>e.getBoundingClientRect().bottom))})")
                assert header['control']<=header['bottom']+1,header
                window.evaluate_js("window.LiveryI18n.setLanguage('zh-CN')")
                time.sleep(.2)
                chinese=window.evaluate_js("document.getElementById('undo').textContent")
                assert chinese=='撤销',chinese
                result={**info,'ok':True,'english':english,'chinese':chinese,'layout_unchanged':True,'artwork_unchanged':True,'chat_unchanged':True,'header_fits':True}
            except Exception as exc:
                test_error.append(exc);result={**info,'ok':False,'error':traceback.format_exc()}
            Path(args.self_test).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            window.destroy()
        webview.start(check_window,gui='edgechromium',private_mode=False,storage_path=str(APP_DATA/'webview'))
        return int(bool(test_error))
    finally:
        http.shutdown();http.server_close();service.STUDIO.chat.process.close()


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        restore_streams()
        error=traceback.format_exc();print(error,file=sys.stderr)
        if getattr(sys,'frozen',False) and not WORKER_MODE:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'Unable to start WT Camo Workbench.\n需要 Microsoft Edge WebView2 Runtime。\n\n'+error,'WT Camo Workbench',0x10)
        raise SystemExit(1)
