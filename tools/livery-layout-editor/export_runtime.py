"""Lossless export throughput, bounded by live RAM and available CPU cores."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from contextlib import contextmanager
from pathlib import Path
import ctypes
import json
import os
import threading
import time
import uuid
import zipfile
import numpy as np

GIB=1024**3
_mode=os.environ.get('WT_CAMO_EXPORT_PERFORMANCE','max')
_output=None
_lock=threading.RLock()
_report={}


def validate(value):
    if value not in ('max','balanced','serial'):raise ValueError('Unknown export performance mode.')
    return value


def memory():
    if os.name=='nt':
        class MemoryStatus(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in
                ('total','available','total_page','available_page','total_virtual','available_virtual','extended')]
        value=MemoryStatus();value.length=ctypes.sizeof(value)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):return value.total,value.available
    try:
        page=os.sysconf('SC_PAGE_SIZE')
        return page*os.sysconf('SC_PHYS_PAGES'),page*os.sysconf('SC_AVPHYS_PAGES')
    except (AttributeError,OSError,ValueError):return 2*GIB,GIB


def resources():
    total,available=memory();reserve=max(256*1024**2,int(total*.025))
    return {'logical_cpus':os.cpu_count() or 1,'ram_total_bytes':total,'ram_available_bytes':available,
            'ram_reserve_bytes':reserve,'ram_budget_bytes':max(0,available-reserve),
            'default_mode':'max','quality':'lossless; original UV and resolution unchanged'}


def configure(mode='max',output=None):
    global _mode,_output,_report
    _mode=validate(mode);_output=Path(output) if output else None
    _report={'schema':'livery-export-performance/v1','mode':mode,'resources':resources(),
             'png_compress_level':1 if mode=='max' else 6,'stages':{},'counters':{},'started':time.time()}
    flush();return dict(_report)


def flush():
    if _output is not None:
        from project import write_json
        with _lock:write_json(_output/'evidence/export-performance.json',_report)


def count(name,amount=1):
    with _lock:
        counters=_report.setdefault('counters',{})
        counters[name]=counters.get(name,0)+amount


def capacity():
    current=resources();workers=current['logical_cpus'];budget=current['ram_budget_bytes']
    if _mode=='serial':workers=1
    elif _mode=='balanced':workers=max(1,workers//2);budget//=2
    return workers,budget


@contextmanager
def stage(name):
    started=time.perf_counter()
    try:yield
    finally:
        with _lock:
            row=_report.setdefault('stages',{}).setdefault(name,{})
            row['seconds']=row.get('seconds',0)+time.perf_counter()-started
        flush()


def ordered_map(function,items,estimate=lambda item:0,stage_name='parallel',on_done=None):
    """Keep output order deterministic; never queue all large arrays at once."""
    items=list(items)
    if not items:return []
    workers,budget=capacity();workers=min(workers,len(items))
    pending={};results=[None]*len(items);index=0;reserved=0;peak=0
    with stage(stage_name),ThreadPoolExecutor(max_workers=workers,thread_name_prefix='livery-export') as pool:
        while index<len(items) or pending:
            while index<len(items) and len(pending)<workers:
                cost=max(0,int(estimate(items[index])))
                if pending and (reserved+cost>budget or cost>resources()['ram_budget_bytes']):break
                # A single task retains its existing block/tile implementation.
                # Conservative estimates must not deadlock a low-memory machine.
                future=pool.submit(function,items[index]);pending[future]=(index,cost)
                reserved+=cost;index+=1;peak=max(peak,len(pending))
            done,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in done:
                slot,cost=pending.pop(future);reserved-=cost;results[slot]=future.result()
                if on_done:on_done(slot,items[slot],results[slot])
    with _lock:_report.setdefault('stages',{}).setdefault(stage_name,{}).update(tasks=len(items),peak_workers=peak,ram_budget_bytes=budget)
    flush();return results


def save_png(image,path):
    """Lower DEFLATE effort changes size, never pixels or channel depth."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        image.save(temporary,format='PNG',compress_level=1 if _mode=='max' else 6,optimize=False)
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
    count('png_writes')


def save_mapping(path,**arrays):
    """Compatible compressed NPZ, with fast lossless DEFLATE in throughput mode."""
    path=Path(path);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1 if _mode=='max' else 6,allowZip64=True) as archive:
            for key,value in arrays.items():
                with archive.open(key+'.npy','w',force_zip64=True) as target:
                    np.lib.format.write_array(target,np.asarray(value),allow_pickle=False)
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


class ArrayCache:
    """Retain decoded planes while leaving RAM for the active native bake."""
    def __init__(self,working_bytes=0):
        self.working_bytes=int(working_bytes);self.limit=max(0,resources()['ram_budget_bytes']-self.working_bytes)
        if _mode=='balanced':self.limit=max(0,resources()['ram_budget_bytes']//2-self.working_bytes)
        if _mode=='serial':self.limit=0
        self.items=OrderedDict();self.bytes=0;self.lock=threading.RLock()
    def get(self,key,loader,estimated_bytes=0):
        with self.lock:return self._get(key,loader,estimated_bytes)
    def _get(self,key,loader,estimated_bytes=0):
        if key in self.items:
            self.items.move_to_end(key);count('plane_cache_hits');return self.items[key]
        cost=int(estimated_bytes)
        while self.items and (self.bytes+cost>self.limit or cost>max(0,resources()['ram_budget_bytes']-self.working_bytes)):
            _,old=self.items.popitem(last=False);self.bytes-=old.nbytes;count('plane_cache_evictions')
        value=loader();count('plane_decodes')
        if value.nbytes<=self.limit and value.nbytes<=max(0,resources()['ram_budget_bytes']-self.working_bytes):
            while self.items and self.bytes+value.nbytes>self.limit:
                _,old=self.items.popitem(last=False);self.bytes-=old.nbytes
            self.items[key]=value;self.bytes+=value.nbytes
        return value
