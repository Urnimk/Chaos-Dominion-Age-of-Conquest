from pathlib import Path
import sys,random,json,time,hashlib,dataclasses
import numpy as np
root=Path(__file__).parent
mode=sys.argv[1]
if mode=='baseline' and len(sys.argv)<4:raise SystemExit('baseline mode requires the original project folder as third argument')
sys.path.insert(0,sys.argv[3] if mode=='baseline' else str(root))
import map_config as cfg
from map_generator import load_world
from war_engine import WarEngine
if mode!='baseline':
 from diagnostic_headless import configure
 configure({'off':0,'light':1,'summary':1,'on':2}[mode],root/('verification_'+mode))
if mode=='light':
 for key in ('ENABLE_AI_DECISION_LOG','ENABLE_STAGNATION_LOG','ENABLE_WAR_DIAGNOSTIC_LOG','ENABLE_LOGISTICS_DIAGNOSTIC_LOG'):setattr(cfg,key,False)
s=Path(sys.argv[2])
e=WarEngine.load(load_world(s),s/'war_state.npz');random.seed(e.world.settings.seed)
source={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in s.iterdir() if p.is_file()}
started=time.perf_counter()
for i in range(100):
 e.step(1)
 if (i+1)%25==0:print(mode,i+1,flush=True)
runtime=time.perf_counter()-started
if mode!='baseline' and e.diagnostics:e.export_diagnostic_package(root/('verification_example_'+mode+'.zip'))
def plain(v):
 if isinstance(v,np.ndarray):return {'shape':list(v.shape),'dtype':str(v.dtype),'sha256':hashlib.sha256(v.tobytes()).hexdigest()}
 if isinstance(v,np.generic):return v.item()
 if isinstance(v,np.random.Generator):return plain(v.bit_generator.state)
 if isinstance(v,random.Random):return plain(v.getstate())
 if isinstance(v,dict):return {str(k):plain(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)):return [plain(x) for x in v]
 if isinstance(v,(set,frozenset)):return sorted(plain(x) for x in v)
 if dataclasses.is_dataclass(v):return plain(dataclasses.asdict(v))
 if isinstance(v,Path):return str(v)
 if v is None or isinstance(v,(str,int,float,bool)):return v
 return str(v)
def digest(v):return hashlib.sha256(json.dumps(plain(v),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
# Include every authoritative engine/world field; exclude derived caches and diagnostics only.
excluded={'diagnostics','world','world_state_cache','rl_brains','_active_strategic_snapshot','_indices_cache','_sea_route_cache','_sea_water_components','_sea_water_component_parent','_sea_labels','_navigation_epoch'}
fields={}
for k,v in vars(e).items():
 if k in excluded or k.startswith('_diagnostic') or 'cache' in k or k in ('_sea_component_cache',):continue
 fields['engine.'+k]=digest(v)
for k,v in vars(e.world).items():fields['world.'+k]=digest(v)
fields['rl_brains']=digest({k:b.to_dict() for k,b in e.rl_brains.items()})
fields['global_random_state']=digest(random.getstate())
report={'mode':mode,'seconds':runtime,'start_year':e.year-100,'end_year':e.year,'fields':fields,'combined_state_sha256':digest(fields),
        'source_unchanged':all(hashlib.sha256((s/n).read_bytes()).hexdigest()==h for n,h in source.items()),'summary':e.summary()}
(root/('benchmark_'+mode+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(mode,runtime,report['combined_state_sha256'],flush=True)
