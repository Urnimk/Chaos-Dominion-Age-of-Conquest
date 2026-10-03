"""Integration check: use a supplied save copy; mock capture only to isolate defeat metadata."""
import sys,tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from map_generator import load_world
from war_engine import WarEngine,Campaign
sd=Path(sys.argv[1]);e=WarEngine.load(load_world(sd),sd/'war_state.npz')
c=e.country(7);s=e._site(c,17);other=e._site(c,7)
count=len(e._spatial_indices(7,17));point=tuple(map(int,np.unravel_index(e._spatial_indices(7,17)[0],e.world.territory.shape)))
origin=tuple(map(int,np.unravel_index(e._spatial_indices(16)[0],e.world.territory.shape)))
e._capture_area=lambda *a,**kw:1
campaign=Campaign(999999,16,7,'land',origin,point,100000000,0,1,0,0)
e._battle([campaign])
assert campaign.status=='won'
assert s['last_defensive_defeat_year']==e.year and s['defensive_crisis_start_cells']==count
assert 'last_defensive_defeat_year' not in other
with tempfile.TemporaryDirectory() as td:
 path=Path(td)/'war_state.npz';e.save(path)
 reloaded=WarEngine.load(load_world(sd),path)
 assert reloaded._site(reloaded.country(7),17)['defensive_crisis_start_cells']==count
 assert reloaded.rl_brains[10].q_values==e.rl_brains[10].q_values
print('Actual battle records only affected island; new save reload preserves record and Q values')
