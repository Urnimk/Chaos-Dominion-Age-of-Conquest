import json
from pathlib import Path
import numpy as np
from map_generator import MapSettings,GeneratedMap
from war_engine import WarEngine
def load(save):
 p=Path(save);i=json.loads((p/'world_map_info.json').read_text());s=MapSettings(width=i['width'],height=i['height'],seed=i['seed'],world_style=i['world_style'],target_ocean_ratio=i['target_ocean_ratio'])
 with np.load(p/'world_map.npz') as z:a={k:z[k].copy() for k in z.files}
 keys='height terrain continent plate temperature humidity rainfall biome water agriculture timber minerals freshwater city_value defense_value movement_cost territory border settlement roads sea_routes'.split()
 w=GeneratedMap(settings=s,**{k:a[k] for k in keys},countries=i['countries'],sea_level=float(a['sea_level']),world_style=i['world_style'],generation_seconds=0.)
 return WarEngine.load(w,p/'war_state.npz')
