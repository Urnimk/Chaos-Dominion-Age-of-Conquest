"""V23 real engine continuation: no UI, sleep, rule bypass or per-year saves."""
from pathlib import Path
import argparse,collections,hashlib,json,time,shutil,copy
import numpy as np
from map_generator import load_world
from war_engine import WarEngine

def main():
 p=argparse.ArgumentParser();p.add_argument('--save',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--years',type=int,default=500);a=p.parse_args()
 if a.save.resolve()==a.output.resolve():raise SystemExit('output must differ from original save')
 hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in a.save.iterdir() if f.is_file()}
 e=WarEngine.load(load_world(a.save),a.save/'war_state.npz');start=e.year;t=time.perf_counter();actions=collections.Counter();executions=[];residence=collections.Counter();initial=len([c for c in e.countries if c['alive']]);counters={c['id']:dict(c.get('strategy_counters',{})) for c in e.countries}
 for i in range(a.years):
  e.step(1)
  assert np.all(e.local_population>=0) and np.all(e.local_soldiers>=0)
  assert np.all(e.local_soldiers<=e.local_population)
  for c in e.countries:
   if not c['alive']:continue
   assert c['food']>=-1e-6 and c['fleet']>=0
   g=c.get('macro_goal',{});residence[(c['id'],g.get('goal_type','PENDING'))]+=1
   event=c.get('macro_last_execution',{})
   if event.get('year')==e.year:
    actions[event['policy']]+=1;executions.append({'id':c['id'],**event})
   for key in e.rl_brains[c['id']].q_values:
    assert ':' not in key.split('|')[-1],key
  if (i+1)%100==0:print(f'+{i+1}y year={e.year}',flush=True)
 elapsed=time.perf_counter()-t;a.output.mkdir(parents=True,exist_ok=True)
 for name in ('world_map.npz','world_map_info.json'):shutil.copyfile(a.save/name,a.output/name)
 e.save(a.output/'war_state.npz')
 r=WarEngine.load(load_world(a.output),a.output/'war_state.npz')
 assert [c.get('macro_goal') for c in e.countries]==[c.get('macro_goal') for c in r.countries]
 assert [c.get('strategic_commitment') for c in e.countries]==[c.get('strategic_commitment') for c in r.countries]
 # Continuation equivalence catches missing persistent target/reward/RNG state.
 final_countries=copy.deepcopy(e.countries)
 e.step(2);r.step(2)
 np.testing.assert_array_equal(e.world.territory,r.world.territory)
 np.testing.assert_array_equal(e.local_population,r.local_population)
 np.testing.assert_array_equal(e.local_soldiers,r.local_soldiers)
 assert e.countries==r.countries
 assert e.rng.bit_generator.state==r.rng.bit_generator.state
 assert all(b.to_dict()==r.rl_brains[cid].to_dict() for cid,b in e.rl_brains.items())
 assert all(hashlib.sha256((a.save/n).read_bytes()).hexdigest()==h for n,h in hashes.items())
 report={'start_year':start,'years':a.years,'seconds':elapsed,'initial_alive':initial,'actions':dict(actions),'executions':executions,'phase_years':{f'{cid}:{phase}':n for (cid,phase),n in residence.items()},'original_unchanged':True,'reload_plus_2_years_equivalent':True,'target_free_q_keys':True,'countries':[{'id':c['id'],'name':c['name'],'alive':c['alive'],'goal':c.get('macro_goal'),'commitment':c.get('strategic_commitment'),'history':c.get('macro_history',[]),'counters':{k:v-counters.get(c['id'],{}).get(k,0) for k,v in c.get('strategy_counters',{}).items()}} for c in final_countries if c['alive']]}
 (a.output/'sanity_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print('PASS',round(elapsed,2),dict(actions))
if __name__=='__main__':main()
