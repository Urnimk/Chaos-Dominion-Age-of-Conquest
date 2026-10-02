import sys,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(1,str(Path(__file__).resolve().parent))
from load_world import load
from map_viewer import MapViewer,messagebox
# Multiple countries must deduct shortage losses from their own homeland.
e=load(Path(__file__).resolve().parents[1]/'saves');selected=[];homes=set()
for c in e.countries:
 if c['alive'] and e._home_continent_id(c) not in homes:
  selected.append(c);homes.add(e._home_continent_id(c))
 if len(selected)==2:break
calls=[];old=e._remove_population_in_mask
def record(mask,amount):
 if amount:calls.append((set(map(int,np.unique(e.world.territory[mask]))),set(map(int,np.unique(e.world.continent[mask])))))
 return old(mask,amount)
e._remove_population_in_mask=record
for c in selected:c['food']=-1e8
e._economic_year()
for c in selected:
 assert ({c['id']},{e._home_continent_id(c)}) in calls
 assert c['food']==0
assert np.all(e.local_population>=0)
print('PASS two-country shortage uses each correct homeland')
# A failed worker must pause before displaying a modal; nested callbacks cannot retry.
v=MapViewer.__new__(MapViewer);queue=[];shown=[]
v.root=SimpleNamespace(after=lambda delay,fn,*args:queue.append((fn,args)))
v.war=SimpleNamespace(step=lambda years:(_ for _ in ()).throw(NameError("name 'home' is not defined")))
v.war_busy=True;v.running=True;v._sim_year_credit=8
v.run_button=SimpleNamespace(configure=lambda **kw:None);v.status=SimpleNamespace(configure=lambda **kw:None)
def popup(*args):
 shown.append(args);assert not v.running and v.war_busy
 v.advance_war(1) # must be blocked during modal loop
 v._handle_advance_error('nested') # must not display a duplicate
messagebox.showerror=popup
v._advance_worker(1)
assert not v.running and v._sim_year_credit==0 and v.war_busy
assert len(queue)==1
fn,args=queue.pop();fn(*args)
assert len(shown)==1 and not queue and not v.war_busy and not v.running
print('PASS failed worker pauses, clears backlog and shows one non-reentrant dialog')
