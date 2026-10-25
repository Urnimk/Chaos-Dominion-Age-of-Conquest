"""V25_2: one simulation writer, completed-state views, coalesced raster work.

No worker calls Tk. The main thread never queries the live simulation engine.
All caches/views are disposable and excluded from the existing save format.
"""
from __future__ import annotations
import copy
import queue
import threading
import time
from collections import Counter
from pathlib import Path
import numpy as np
from world_state_cache import WorldStateCache


class PresentationMetrics:
    """Coalesced counters; only the simulation writer touches real diagnostics."""
    def __init__(self):self.lock=threading.Lock();self.counts=Counter();self.phases=Counter()
    def count(self,name,n=1):
        with self.lock:self.counts[name]+=n
    def phase(self,year,name,ms):
        with self.lock:self.phases[(year,name)]+=ms
    def flush(self,d):
        with self.lock:counts=self.counts;phases=self.phases;self.counts=Counter();self.phases=Counter()
        if not counts and not phases:return
        if d is None or not d.enabled_for('performance'):return
        for name,n in counts.items():d.count(name,n)
        rows={r['year']:r for r in d.performance}
        for (year,name),ms in phases.items():
            row=rows.get(year)
            if row is not None:
                row['ui_phases_ms'][name]=row['ui_phases_ms'].get(name,0.)+ms;row['ui_ms']+=ms
            else:d.ui_phases[name]+=ms


class PresentationDiagnostics:
    # Engine query wrappers stay disabled on views; UI wrappers can still time Tk.
    enabled=False
    def __init__(self,sink,year):self.sink=sink;self.year=year;self.stack=[]
    def enabled_for(self,category):return category=='performance'
    def count(self,name,n=1):self.sink.count(name,n)
    def push_timer(self,phase):self.stack.append([phase,time.perf_counter(),0.])
    def pop_timer(self):
        name,start,children=self.stack.pop();duration=time.perf_counter()-start
        if self.stack:self.stack[-1][2]+=duration
        self.sink.phase(self.year,name.removeprefix('ui:'),max(0.,duration-children)*1000.)


def capture_view(engine, previous=None):
    view=copy.copy(engine);view.world=copy.copy(engine.world)
    view._presentation_keys={}
    def frozen(array,key,name):
        view._presentation_keys[name]=key
        if previous is not None and previous._presentation_keys.get(name)==key:
            return getattr(previous.world,name[6:]) if name.startswith('world:') else getattr(previous,name)
        result=array.copy();result.flags.writeable=False;return result
    for name in ('territory','border','settlement'):
        arr=getattr(engine.world,name)
        setattr(view.world,name,frozen(arr,(id(arr),engine.visual_revision),'world:'+name))
    for name in ('local_population','local_soldiers','building_owner'):
        arr=getattr(engine,name)
        revision=(engine.world_state_cache.value_revisions.get(name.removeprefix('local_'),0)
                  if name!='building_owner' else engine.visual_revision)
        setattr(view,name,frozen(arr,(id(arr),revision),name))
    # Static terrain/continent/yield arrays are never changed by WarEngine.
    for name in ('countries','campaigns','geographic_regions','islands',
                 'island_name_aliases','name_prefix_history'):
        if hasattr(engine,name):setattr(view,name,copy.deepcopy(getattr(engine,name)))
    view.world.countries=copy.deepcopy(engine.world.countries)
    view.events=list(engine.events);view.history_events=list(engine.history_events)
    view.country_events={cid:list(log) for cid,log in engine.country_events.items()}
    view.alliance_names=dict(engine.alliance_names)
    view._indices_cache={};view._sea_route_cache={};view._active_strategic_snapshot=None
    view.world_state_cache=WorldStateCache(view)
    view.world_state_cache._geographic_indices=dict(engine.world_state_cache._geographic_indices)
    view.rng=copy.deepcopy(engine.rng);view.diagnostics=None;view.rl_brains={}
    return view


class SimulationRuntime:
    """FIFO commands; progress is replaceable, completions/errors are lossless."""
    def __init__(self, prepare_view=None, publish_seconds=.5):
        self.commands=queue.Queue();self.results=queue.Queue();self.lock=threading.Lock()
        self.progress=None;self.engine=None;self.previous=None;self.sequence=0
        self.metrics=PresentationMetrics()
        self.prepare_view=prepare_view;self.publish_seconds=publish_seconds
        self.thread=threading.Thread(target=self._run,daemon=True,name='simulation-writer');self.thread.start()
    def submit(self,kind,**payload):
        self.sequence+=1;self.commands.put((self.sequence,kind,payload));return self.sequence
    def poll(self):
        with self.lock:progress=self.progress;self.progress=None
        packets=[] if progress is None else [progress]
        while True:
            try:packets.append(self.results.get_nowait())
            except queue.Empty:return packets
    def _frame(self):
        started=time.perf_counter()
        view=capture_view(self.engine,self.previous)
        if self.prepare_view:self.prepare_view(view)
        d=getattr(self.engine,'diagnostics',None)
        if d is not None and d.enabled_for('performance'):
            view.diagnostics=PresentationDiagnostics(self.metrics,view.year)
            self.metrics.count('presentation_snapshots')
            self.metrics.phase(view.year,'snapshot_publication',(time.perf_counter()-started)*1000.)
        self.previous=view;return view
    def _run(self):
        from map_generator import generate_world,load_world,save_world
        from war_engine import WarEngine
        while True:
            token,kind,p=self.commands.get()
            self.metrics.flush(getattr(self.engine,'diagnostics',None))
            try:
                result=None;view=None
                if kind=='initialize':
                    world=p.get('world')
                    if world is None:
                        if p.get('generate'):world=generate_world(p['settings']);save_world(world)
                        else:
                            try:world=load_world()
                            except Exception:world=generate_world(p['settings']);save_world(world)
                    self.engine=WarEngine(world,p['path']);self.previous=None
                    if p.get('load_last'):
                        try:self.engine=WarEngine.load(world,p['path'])
                        except (OSError,ValueError,KeyError):pass
                    view=self._frame()
                elif kind=='advance':
                    completed=0;last=time.perf_counter()
                    for _ in range(max(1,int(p['years']))):
                        self.engine.step(1);completed+=1;self.metrics.flush(getattr(self.engine,'diagnostics',None))
                        if time.perf_counter()-last>=self.publish_seconds:
                            packet=dict(token=token,kind=kind,done=False,completed=completed,view=self._frame())
                            with self.lock:self.progress=packet
                            last=time.perf_counter()
                    view=self._frame();result=completed
                elif kind=='save':
                    started=time.perf_counter()
                    if p.get('world'):save_world(self.engine.world)
                    self.engine.save(p['path']);result=self.engine.year
                    self.metrics.count('background_save_calls')
                    self.metrics.phase(result,'background_save',(time.perf_counter()-started)*1000.)
                elif kind=='load':
                    self.engine=WarEngine.load(self.engine.world,p['path']);self.previous=None;view=self._frame()
                elif kind=='export':result=self.engine.export_diagnostic_package()
                elif kind=='close':
                    if self.engine:
                        if p.get('save'):
                            save_world(self.engine.world);self.engine.save(p['path'])
                        self.metrics.flush(getattr(self.engine,'diagnostics',None))
                        if getattr(self.engine,'diagnostics',None):self.engine.diagnostics.flush()
                else:raise ValueError('Unknown runtime command: '+kind)
                with self.lock:self.progress=None
                self.results.put(dict(token=token,kind=kind,done=True,result=result,view=view))
            except Exception as exc:
                with self.lock:self.progress=None
                self.results.put(dict(token=token,kind=kind,done=True,error=str(exc)))
            if kind=='close':return


class RasterRuntime:
    """At most one active raster and one pending latest request; PIL only."""
    def __init__(self,render,metrics=None):
        self.render=render;self.lock=threading.Lock();self.event=threading.Event()
        self.metrics=metrics
        self.pending=None;self.ready=None;self.stopped=False;self.sequence=0
        self.thread=threading.Thread(target=self._run,daemon=True,name='map-raster');self.thread.start()
    def request(self,world,layer,year=None):
        with self.lock:
            self.sequence+=1;token=self.sequence;self.pending=(token,world,layer,year)
        self.event.set();return token
    def poll(self):
        with self.lock:result=self.ready;self.ready=None;return result
    def stop(self):self.stopped=True;self.event.set()
    def _run(self):
        while True:
            self.event.wait();self.event.clear()
            if self.stopped:return
            with self.lock:request=self.pending;self.pending=None
            if request is None:continue
            token,world,layer,year=request;started=time.perf_counter()
            try:result=(token,layer,self.render(world,layer),None)
            except Exception as exc:result=(token,layer,None,str(exc))
            if self.metrics:
                self.metrics.count('environment_raster_renders')
                self.metrics.phase(year,'environment_raster_render',(time.perf_counter()-started)*1000.)
            with self.lock:
                if token==self.sequence:self.ready=result


def sync_tree_rows(tree, rows):
    """Stable IDs preserve selections/scroll; unchanged rows have no Tk writes."""
    ids={str(i) for i,_,_ in rows}
    children=list(tree.get_children())
    for iid in children:
        if iid not in ids:tree.delete(iid)
    current=[v for v in children if v in ids]
    for index,(iid,text,values) in enumerate(rows):
        iid=str(iid)
        if tree.exists(iid):
            item=tree.item(iid)
            if str(item['text'])!=str(text) or tuple(map(str,item['values']))!=tuple(map(str,values)):
                tree.item(iid,text=text,values=values)
            if index>=len(current) or current[index]!=iid:
                tree.move(iid,'',index)
                if iid in current:current.remove(iid)
                current.insert(index,iid)
        else:tree.insert('',index,iid=iid,text=text,values=values);current.insert(index,iid)
