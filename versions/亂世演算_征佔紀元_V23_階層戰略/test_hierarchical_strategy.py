"""Small deterministic controller fixtures; separate from the real 500-year run."""
import copy,unittest
from unittest.mock import patch
from pathlib import Path
from map_generator import load_world
from war_engine import WarEngine
from hierarchical_strategy import GOALS
import map_config as cfg

class StrategyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import os
  save=Path(os.environ['V23_TEST_SAVE'])
  cls.engine=WarEngine.load(load_world(save),save/'war_state.npz')
 def setUp(self):
  self.e=self.engine;self.c=copy.deepcopy(self.e.country(2));self.e.year=9000
  for key in ('macro_goal','strategic_commitment','macro_history','macro_credit','macro_credit_initialized','macro_completed_islands'):
   self.c.pop(key,None)
  self.m={'cells':100,'control':.2,'army':500,'rivals':[7],'base':True,'port':True,'pacified':False}
 def test_target_commitment_and_phase_completion(self):
  e,c=self.e,self.c
  with patch.object(e,'_macro_measure',side_effect=lambda *args:dict(self.m)),patch.object(e,'_homeland_is_critical',return_value=False),patch.object(e,'_homeland_is_unified',return_value=True),patch.object(e,'_theatre',return_value={'gap':0,'supply_need':0}),patch.object(e,'_macro_candidates',return_value=[(99,32,'CONQUER',15)]):
   e._macro_new_commitment(c,1,'CONQUER',7)
   for year in (9000,9020,9100,9250):
    e.year=year;goal=e._macro_update(c);self.assertEqual(goal['target_landmass'],1)
   self.m.update(control=.81,rivals=[],pacified=True)
   self.assertEqual(e._macro_update(c)['goal_type'],'PREPARE_NEXT_EXPEDITION')
   self.m.update(control=0.,cells=0,rivals=[15],pacified=False,base=False,port=False)
   self.assertEqual(e._macro_update(c)['target_landmass'],32)
   self.assertEqual([h['event'] for h in c['macro_history'] if h['event'] in ('COMMIT','COMPLETE')],['COMMIT','COMPLETE','COMMIT'])
 def test_stall_exception_and_cooldown(self):
  e,c=self.e,self.c
  with patch.object(e,'_macro_measure',return_value=self.m),patch.object(e,'_homeland_is_critical',return_value=False),patch.object(e,'_homeland_is_unified',return_value=True):
   e._macro_new_commitment(c,1,'CONQUER',7);e.year+=cfg.MACRO_STALL_YEARS
   goal=e._macro_update(c)
   self.assertEqual(goal['switch_reason'],'LONG_NO_PROGRESS');self.assertIsNone(c['strategic_commitment'])
   self.assertGreater(c['macro_target_cooldowns']['1'],e.year)
 def test_home_emergency_suspends_target(self):
  e,c=self.e,self.c
  with patch.object(e,'_macro_measure',return_value=self.m):
   e._macro_new_commitment(c,1,'CONQUER',7)
   with patch.object(e,'_homeland_is_critical',return_value=True),patch.object(e,'_homeland_is_unified',return_value=False):
    goal=e._macro_update(c);self.assertEqual(goal['goal_type'],'UNIFY_HOMELAND');self.assertEqual(c['strategic_commitment']['target_landmass'],1);self.assertEqual(c['strategic_commitment']['status'],'SUSPENDED')
 def test_supply_manifest_never_spends_and_zero_food_blocks(self):
  e=self.e;c=copy.deepcopy(e.country(2));site=c['overseas_capitals'][0];t=e._theatre(c,site)
  c['food']=0;t.update(gap=5000,supply_need=1000)
  before=copy.deepcopy(c);self.assertIsNone(e._reinforcement_manifest(c,t));self.assertEqual(c,before)
 def test_milestone_cannot_be_farmed_by_rebuilding(self):
  e,c=self.e,self.c;c['macro_goal']={'target_landmass':1};c['macro_credit_initialized']=True
  c['macro_credit']={'1':{'control':.2,'base':True,'port':True,'supply':False}}
  with patch.object(e,'_macro_measure',side_effect=lambda *args:dict(self.m)),patch.object(e,'_site',return_value=None):
   first=e._macro_metrics(c,{})['macro_credit']
   self.m.update(base=False,port=False,control=.1);e._macro_metrics(c,{})
   self.m.update(base=True,port=True,control=.2)
   self.assertEqual(e._macro_metrics(c,{})['macro_credit'],first)
   self.m['control']=.3;self.assertGreater(e._macro_metrics(c,{})['macro_credit'],first)
 def test_all_goal_schemas_and_legacy_q_archive(self):
  e,c=self.e,self.c
  for kind in GOALS:
   g=e._macro_stage(c,kind,0,None,'TEST_FIXTURE')
   self.assertTrue({'goal_type','target_country','target_landmass','started_year','last_progress_year','progress','success_condition','failure_condition','switch_reason'}<=set(g))
  from rl_brain import CountryBrain
  b=CountryBrain(1);legacy={'0,0,0,0,0,0,0,0,0|ATTACK:7:naval':1.25}
  b.load_dict({'state_dimensions':9,'q_values':legacy})
  self.assertEqual(b.legacy_q_values,legacy);self.assertFalse(b.q_values);self.assertIsNone(b.pending)
  s=(0,)*12;b.update(s,'ATTACK_OVERSEAS',1,terminal=True)
  self.assertTrue(all(':' not in k.split('|')[-1] for k in b.q_values))
if __name__=='__main__':unittest.main()
