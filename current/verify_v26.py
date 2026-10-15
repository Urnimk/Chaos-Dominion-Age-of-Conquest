"""Reproducible headless royal benchmark/continuation; never writes source saves."""
from pathlib import Path
import argparse,time,json,random,hashlib,copy
from collections import Counter
import numpy as np
import map_config as cfg
from map_generator import load_world,generate_world,MapSettings
from war_engine import WarEngine

def main():
 p=argparse.ArgumentParser();p.add_argument('--save',type=Path);p.add_argument('--years',type=int,default=1000);p.add_argument('--off',action='store_true');p.add_argument('--seed',type=int,default=2026);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 cfg.ENABLE_DIAGNOSTIC_LOG=False;cfg.ENABLE_KING_STRATEGY_SYSTEM=not a.off
 source={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in a.save.iterdir() if f.is_file()} if a.save else {}
 if a.save:e=WarEngine.load(load_world(a.save),a.save/'war_state.npz')
 else:
  cfg.COUNTRY_COUNT=12;random.seed(a.seed);e=WarEngine(generate_world(MapSettings(384,256,a.seed,'RANDOM',.6)))
 random.seed(e.world.settings.seed);start=e.year;initial_alive=sum(c['alive'] for c in e.countries)
 actions=Counter();phases=Counter();maxroyals=0;maxunions=0;events=[];lastseen=0;king_seconds=0
 original=e.king_system.tick
 def timed():
  nonlocal king_seconds
  t=time.perf_counter();original();king_seconds+=time.perf_counter()-t
 e.king_system.tick=timed
 t=time.perf_counter()
 for i in range(a.years):
  e.step(1)
  assert np.all(e.local_population>=0) and np.all(e.local_soldiers>=0)
  assert np.all(e.local_soldiers<=e.local_population)
  for c in e.countries:
   if c['alive']:
    assert c['fleet']>=0 and c['food']>=-1e-6
    if not a.off:assert e.king_system.profile(c) is not None
    event=c.get('macro_last_execution',{})
    if event.get('year')==e.year:actions[event['policy']]+=1
    phases[c.get('strategic_phase','PENDING')]+=1
  for campaign in e.campaigns:
   if campaign.status=='marching':assert not e.king_system.same_union(campaign.attacker,campaign.defender)
  events.extend(x for x in e.king_system.history if x['year']==e.year)
  maxroyals=max(maxroyals,len(e.king_system.persons));maxunions=max(maxunions,len(e.king_system.unions))
  if (i+1)%100==0:print(f'{a.output.stem} +{i+1}y alive={sum(c["alive"] for c in e.countries)} royal={len(e.king_system.persons)} unions={len(e.king_system.unions)}',flush=True)
 elapsed=time.perf_counter()-t
 a.output.parent.mkdir(parents=True,exist_ok=True)
 result=dict(start_year=start,end_year=e.year,years=a.years,seconds=elapsed,king_tick_seconds=king_seconds,king_enabled=not a.off,
   initial_alive=initial_alive,final_alive=sum(c['alive'] for c in e.countries),battles=e.battles,metrics=dict(e.king_system.metrics),actions=dict(actions),phase_years=dict(phases),max_royals=maxroyals,max_unions=maxunions,
   royals=len(e.king_system.persons),unions=len(e.king_system.unions),history=events,country_history=e.king_system.country_history,
   source_unchanged=all(hashlib.sha256((a.save/n).read_bytes()).hexdigest()==h for n,h in source.items()))
 a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2));print('done',a.output,elapsed,flush=True)
 if a.save and not a.off:
  checkpoint=a.output.parent/(a.output.stem+'_checkpoint');checkpoint.mkdir(exist_ok=True)
  e.save(checkpoint/'war_state.npz')
  reloaded=WarEngine.load(copy.deepcopy(e.world),checkpoint/'war_state.npz')
  assert e.king_system.to_dict()==reloaded.king_system.to_dict()
  before=random.getstate();e.step(2);random.setstate(before);reloaded.step(2)
  assert e.king_system.to_dict()==reloaded.king_system.to_dict()
  differences=[]
  for ca,cb in zip(e.countries,reloaded.countries):
   for key in ca.keys()|cb.keys():
    if ca.get(key)!=cb.get(key):differences.append(dict(country=ca['id'],key=key,before=repr(ca.get(key)),after=repr(cb.get(key))))
  if differences:
   a.output.with_name(a.output.stem+'_reload_diff.json').write_text(json.dumps(differences,ensure_ascii=False,indent=2))
  assert e.countries==reloaded.countries, differences[:2]
  np.testing.assert_array_equal(e.world.territory,reloaded.world.territory)
  np.testing.assert_array_equal(e.local_population,reloaded.local_population)
  result['checkpoint_reload_equal_after_2y']=True;a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
