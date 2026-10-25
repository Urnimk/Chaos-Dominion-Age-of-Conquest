"""Small political fixture; engine integration tests use the actual WarEngine."""
from types import SimpleNamespace
from collections import Counter
import numpy as np
from king_system import KingSystem
class RoyalFixture:
 def __init__(self):
  self.year=100;self.world=SimpleNamespace(settings=SimpleNamespace(seed=99,width=40,height=12),territory=np.tile(np.repeat(np.arange(1,5),10),(12,1)),continent=np.ones((12,40),dtype=np.int32))
  self.countries=[dict(id=i,name=f'國{i}',king_name=f'初王{i}',royal_surname=f'家{i}',king_number=1,king_since_year=90,king_next_year=150,alive=True,capital=[(i-1)*10+5,5],population=10000,soldiers=2000,fleet=200,ports=2,territory_cells=120,food=1e6,timber=1000,minerals=1000,wars_won=0,wars_lost=0,war_exhaustion=0.,alliance=0) for i in range(1,5)]
  self.local_population=np.full((12,40),80,dtype=np.int32);self.local_soldiers=np.full((12,40),10,dtype=np.int32);self.building_owner=self.world.territory.copy()
  self.land_contacts={(1,2):[(0,0)],(2,3):[(0,0)]};self._landmass_sizes=[0,480];self.campaigns=[];self.logs=[];self.diagnostics=None
  self.world_state_cache=SimpleNamespace(landmass_ownership=lambda lm:(480,np.array([0,120,120,120,120]),frozenset((1,2,3,4))),country_landmasses=lambda cid:frozenset([1]))
  self.king_system=KingSystem(self)
 def country(self,cid):return self.countries[cid-1]
 def _home_continent_id(self,c):return 1
 def _homeland_is_unified(self,c):return False
 def _wrapped_distance_cells(self,a,b,width):return abs(a[0]-b[0])
 def _log(self,cid,message):self.logs.append((cid,message))
 def _mark_world_changed(self,*a,**kw):pass
 def _sync_army_totals(self,*a):pass
 def _build_geography(self):pass
 def pair(self):
  a=self.king_system.profile(self.country(1));b=self.king_system.profile(self.country(2));a.gender='F';b.gender='M';a.birth_year=b.birth_year=self.year-25
  return a,b
