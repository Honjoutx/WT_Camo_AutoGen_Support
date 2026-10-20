"""Keep bundled Python DLL search paths out of system Codex/Blender processes."""
from contextlib import contextmanager
from pathlib import Path
import ctypes
import os
import subprocess
import sys
import threading

LOCK=threading.RLock()


def environment(env=None):
    result=dict(os.environ if env is None else env)
    if getattr(sys,'frozen',False):
        base=Path(sys._MEIPASS).resolve()
        entries=[]
        for value in result.get('PATH','').split(os.pathsep):
            try:
                if Path(value).resolve().is_relative_to(base):continue
            except (OSError,ValueError):pass
            entries.append(value)
        result['PATH']=os.pathsep.join(entries)
        if os.name!='nt':
            if 'LD_LIBRARY_PATH_ORIG' in result:result['LD_LIBRARY_PATH']=result['LD_LIBRARY_PATH_ORIG']
            else:result.pop('LD_LIBRARY_PATH',None)
    return result


@contextmanager
def native_search():
    with LOCK:
        changed=bool(getattr(sys,'frozen',False) and os.name=='nt')
        if changed:ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:yield
        finally:
            if changed:ctypes.windll.kernel32.SetDllDirectoryW(str(sys._MEIPASS))


def popen(command,**kwargs):
    kwargs['env']=environment(kwargs.get('env'))
    with native_search():return subprocess.Popen(command,**kwargs)


def run(command,**kwargs):
    kwargs['env']=environment(kwargs.get('env'))
    with native_search():return subprocess.run(command,**kwargs)
