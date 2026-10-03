import sys,unittest,copy
from pathlib import Path
from types import SimpleNamespace as N
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from war_engine import WarEngine
from country_generator import PORT


def fixture():
 e=WarEngine.__new__(WarEngine);e.year=100;e.visual_revision=0;e.territory_dirty=set();e.campaigns=[]
 e.world=N(territory=np.array([[1,1,0,1,1,2]]),continent=np.array([[1,1,0,2,2,2]]),settlement=np.array([[PORT,0,0,PORT,0,0]]),settings=N(width=6,height=1))
 e.local_population=np.array([[1000,0,0,15000,15000,30000]]);e.local_soldiers=np.array([[100,0,0,1500,1500,20000]])
 e.building_owner=e.world.territory.copy()
 site={'continent_id':2,'anchor':[4,0],'logistics_port':[3,0],'supply_food':10000.,'last_defensive_defeat_year':99,'defensive_crisis_start_cells':4}
 c=dict(id=1,name='test',alive=True,capital=[0,0],population=31000,fleet=30,food=100000.,overseas_capitals=[site],overseas_capital=site,colonies=[])
 e.countries=[c,dict(id=2,alive=True)];e._home_continent_id=lambda c:1
 e._sea_route=lambda a,b:[list(a),list(b)];e._route_distance_km=lambda r:75.
 e._build_geography=lambda:None;e.messages=[];e._log=lambda cid,msg:e.messages.append(msg)
 e._apply_delayed_rl_credit=lambda *args:(_ for _ in ()).throw(AssertionError('evacuation must not be penalized as port loss'))
 e._theatre=lambda c,s:dict(enemies=[2],army=3000,enemy_army=20000,port=(3,0),lm=2)
 return e,c,site

class RetreatTests(unittest.TestCase):
 def test_peaceful_large_population_stays(self):
  e,c,s=fixture();s.pop('last_defensive_defeat_year');self.assertIsNone(e._retreat_reason(c,s));self.assertFalse(e._evacuate_theatre(c,s));self.assertEqual(e.local_population[0,3:5].sum(),30000)
 def test_old_or_other_island_defeat_not_enough(self):
  e,c,s=fixture();s['last_defensive_defeat_year']=79;self.assertIsNone(e._retreat_reason(c,s))
  s.pop('last_defensive_defeat_year');c['last_defensive_defeat_year']=100;self.assertIsNone(e._retreat_reason(c,s))
 def test_small_land_loss_stays(self):
  e,c,s=fixture();s['defensive_crisis_start_cells']=2;self.assertIsNone(e._retreat_reason(c,s))
 def test_reinforcement_pending_stays(self):
  e,c,s=fixture();c['reinforcement_voyage']={'soldiers':100};self.assertIsNone(e._retreat_reason(c,s))
 def test_full_transport_preflight(self):
  for change in ('fleet','food'):
   e,c,s=fixture()
   if change=='fleet':c['fleet']=1
   else:c['food']=0;s['supply_food']=0
   before=(e.local_population.copy(),e.local_soldiers.copy(),e.world.territory.copy(),copy.deepcopy(c))
   self.assertFalse(e._evacuate_theatre(c,s))
   for actual,expected in zip((e.local_population,e.local_soldiers,e.world.territory),before[:3]):np.testing.assert_array_equal(actual,expected)
   self.assertEqual(c,before[3])
 def test_complete_evacuate_and_return_conservation(self):
  e,c,s=fixture();pop=int(e.local_population.sum());army=int(e.local_soldiers.sum());food=c['food']+s['supply_food']
  self.assertTrue(e._evacuate_theatre(c,s));v=c['reinforcement_voyage']
  self.assertEqual(int(e.local_population.sum())+v['transported_population'],pop)
  self.assertEqual(int(e.local_soldiers.sum())+v['soldiers'],army)
  self.assertEqual(v['route'],[[0,0],[3,0]])
  self.assertIsNone(c['overseas_capital']);self.assertEqual(c['overseas_capitals'],[])
  e._arrive_reinforcements_v22()
  self.assertEqual(int(e.local_population.sum()),pop);self.assertEqual(int(e.local_soldiers.sum()),army)
  self.assertAlmostEqual(c['food'],food-30000*.18)
  self.assertEqual(c['fleet'],30);self.assertTrue(any('主動撤離' in m and '完成返航' in m for m in e.messages))

if __name__=='__main__':unittest.main(verbosity=2)
