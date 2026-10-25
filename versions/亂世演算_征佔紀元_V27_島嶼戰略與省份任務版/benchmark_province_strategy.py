import argparse,sys,time,json,random,pickle
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--code',default='.');p.add_argument('--out',default='verification/province');p.add_argument('--enabled',type=int,default=1);p.add_argument('--seed',type=int,default=2026);p.add_argument('--years',type=int,default=1000);p.add_argument('--size',type=int,default=384);a=p.parse_args();sys.path.insert(0,str(Path(a.code).resolve()))
import numpy as np
import map_config as cfg
from map_generator import MapSettings,generate_world
from war_engine import WarEngine
from diagnostic_test_support import state
cfg.ENABLE_DIAGNOSTIC_LOG=False;cfg.COUNTRY_COUNT=12;cfg.PROVINCE_STRATEGY_ENABLED=bool(a.enabled)
random.seed(a.seed);t=time.perf_counter();e=WarEngine(generate_world(MapSettings(a.size,int(a.size*2/3),a.seed,'RANDOM',.7)));init=time.perf_counter()-t
t=time.perf_counter();samples=[]
for year in range(a.years):
 e.step(1)
 if (year+1)%100==0:samples.append({'year':e.year,'alive':sum(c['alive'] for c in e.countries),'owned':int(np.count_nonzero(e.world.territory)),'battles':e.battles})
elapsed=time.perf_counter()-t
cache=getattr(e.world_state_cache,'provinces',None)
result={'seed':a.seed,'years':a.years,'size':[a.size,int(a.size*2/3)],'province_enabled':bool(a.enabled),'init_seconds':init,'simulation_seconds':elapsed,'samples':samples}
if cache is not None:result['province_cache']={'hits':cache.hits,'misses':cache.misses,'frontier_hits':cache.frontier_hits,'frontier_misses':cache.frontier_misses,'last_choices':cache.last_choice}
out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
out.with_suffix('.pickle').write_bytes(pickle.dumps(state(e)))
print(json.dumps(result,ensure_ascii=False),flush=True)
