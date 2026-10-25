import sys,time,json,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
import map_config as cfg
from map_generator import generate_world,MapSettings
from war_engine import WarEngine
cfg.ENABLE_DIAGNOSTIC_LOG=False;cfg.COUNTRY_COUNT=12;random.seed(2026)
t=time.perf_counter();e=WarEngine(generate_world(MapSettings(1200,800,2026,'RANDOM',.7)));initial=time.perf_counter()-t
p=e.world_state_cache.provinces;l=p.layout;land=e.world.terrain>=2
# Use one real island with an established front, no simulation or RNG in timings.
ids,cnt=np.unique(e.world.continent[land],return_counts=True);lm=int(ids[np.argmax(cnt)])
ys,xs=np.where(land&(e.world.continent==lm));mid=np.median(xs);mask=land&(e.world.continent==lm)
e.world.territory[mask]=1;e.world.territory[mask&(np.indices(mask.shape)[1]>mid)]=2
e._mark_world_changed(1,2,landmass_ids=[lm]);e._selected_theatre=(1,lm,'ATTACK_FRONT')
def legacy():
 m=(e.world.territory==2)&e._adjacent_land_mask(e.world.territory==1)&(e.world.continent==lm)
 return np.flatnonzero(m)
def region():
 groups=p.frontier(1,2,lm)
 return np.sort(np.concatenate(list(groups.values()))) if groups else np.empty(0,int)
np.testing.assert_array_equal(legacy(),region())
def measure(fn,n=100):
 times=[]
 for _ in range(n):
  t=time.perf_counter();fn();times.append((time.perf_counter()-t)*1000)
 return dict(median_ms=float(np.median(times)),p95_ms=float(np.percentile(times,95)),calls=n)
old=measure(legacy);cached=measure(region)
def cold():p._fronts.clear();return region()
cold_time=measure(cold)
objectives={}
for enabled in (False,True,True,False):
 cfg.PROVINCE_STRATEGY_ENABLED=enabled
 entry=measure(lambda:e._objective(1,2,'land',lm),30)
 objectives.setdefault(str(enabled),[]).append(entry)
summary=dict(size=[1200,800],init_seconds=initial,provinces=len(l.indices)-1,
 immutable_array_bytes=sum(x.nbytes for x in l.indices)+l.ids.nbytes+l.boundary.nbytes,
 frontier_count=len(legacy()),legacy_frontier=old,cold_frontier=cold_time,cached_frontier=cached,objective_ABBA=objectives,
 note='Same established front and unchanged world; timings exclude generation. Objective choices differ by design. Array bytes exclude Python objects.')
Path('verification').mkdir(exist_ok=True)
Path('verification/microbench.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
