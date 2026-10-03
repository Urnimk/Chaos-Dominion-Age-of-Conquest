import sys,json,time
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/sys.argv[1]))
from map_generator import load_world
from war_engine import WarEngine
sd=root/'save/saves';e=WarEngine.load(load_world(sd),sd/'war_state.npz');events=[];retreats=[]
orig=e._log
def log(cid,msg):
 if any(s in msg for s in ('返航','撤','失守','戰役','海外首都','殖民首都')):events.append([e.year,cid,msg])
 return orig(cid,msg)
e._log=log
origret=e._evacuate_theatre
def ret(c,s):
 t=e._theatre(c,s);rec={'year':e.year,'country':c['name'],'id':c['id'],'island':s['continent_id'],'population':t['population'],'army':t['army'],'enemy_army':t['enemy_army'],'food':s.get('supply_food',0),'cells':len(e._spatial_indices(c['id'],s['continent_id']))}
 result=origret(c,s);rec['success']=result;retreats.append(rec);return result
e._evacuate_theatre=ret
start=e.year;beg={c['id']:{'name':c['name'],'population':c['population'],'land':c['territory_cells'],'counters':dict(c.get('strategy_counters',{}))} for c in e.countries}
for i in range(300):
 e.step(1)
 if (i+1)%50==0:print(sys.argv[1],e.year,flush=True)
end=[{'id':c['id'],'name':c['name'],'alive':c['alive'],'population':c['population'],'land':c['territory_cells'],'sites':len(c.get('overseas_capitals',[])),'counters':c.get('strategy_counters',{})} for c in e.countries]
(root/(sys.argv[1]+'_300.json')).write_text(json.dumps({'start':start,'end':e.year,'initial':beg,'final':end,'retreats':retreats,'events':events},ensure_ascii=False,indent=2))
print('RETREATS',json.dumps(retreats,ensure_ascii=False),flush=True)
print('MASTER',json.dumps([x for x in end if '摸魚' in x['name']],ensure_ascii=False),flush=True)
