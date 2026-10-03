import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from war_engine import WarEngine
from map_generator import load_world
import map_config as cfg
SAVE=Path(sys.argv.pop(1)) if len(sys.argv)>1 else Path('saves')
class ProgressTests(unittest.TestCase):
 def setUp(self):self.e=WarEngine.load(load_world(SAVE),SAVE/'war_state.npz')
 def test_progress_beats_defense_and_food(self):
  e=self.e;c=e.country(10);state,actions,bias=e._strategic_state_actions(10,False)
  attacks=[a for a in actions if a.endswith(('ATTACK_FRONT','CUT_OFF','ENCIRCLE_CAPITAL'))]
  self.assertTrue(attacks)
  values={a:e.rl_brains[10].value(state,a)+bias.get(a,0) for a in actions}
  self.assertGreater(max(values[a] for a in attacks),max(v for a,v in values.items() if a not in attacks))
 def test_preflight_no_mutation_and_reserve(self):
  e=self.e;c=e.country(14);pop=e.local_population.copy();army=e.local_soldiers.copy();r=repr(e.rng.bit_generator.state)
  e._viable_theatre_targets(c,23)
  np.testing.assert_array_equal(pop,e.local_population);np.testing.assert_array_equal(army,e.local_soldiers);self.assertEqual(r,repr(e.rng.bit_generator.state))
  e.local_soldiers[:]=0;self.assertEqual([],e._viable_theatre_targets(c,23))
 def test_recovery_prevents_attack(self):
  e=self.e;c=e.country(10);c['recovery_until_year']=e.year+1;self.assertEqual([],e._viable_theatre_targets(c,23))
 def test_expansion_paid_and_population_conserved(self):
  e=self.e;c=e.country(12);before=int(e.local_population.sum());food=c['food'];wood=c['timber'];land=int((e.world.territory==12).sum())
  self.assertTrue(e._can_expand_theatre(c,9));self.assertTrue(e._expand_theatre(c,9))
  self.assertEqual(before,int(e.local_population.sum()));gain=int((e.world.territory==12).sum())-land
  self.assertGreater(gain,0);self.assertAlmostEqual(food-c['food'],gain*cfg.EXPANSION_FOOD_COST_PER_CELL);self.assertAlmostEqual(wood-c['timber'],gain*cfg.EXPANSION_TIMBER_COST_PER_CELL)
 def test_peaceful_demobilization_conserves_population_and_reserve(self):
  e=self.e;c=e.country(6);before=int(e.local_population.sum());army=e._home_soldiers(6,8);pop=e._theatre(c,e._site(c,8))['population']
  self.assertTrue(e._can_expand_theatre(c,8));self.assertTrue(e._expand_theatre(c,8))
  self.assertEqual(before,int(e.local_population.sum()));self.assertLess(e._home_soldiers(6,8),army);self.assertGreaterEqual(e._home_soldiers(6,8),int(pop*cfg.MIN_GARRISON_RATIO))
 def test_failure_retry_and_decision_log(self):
  e=self.e;c=e.country(2);c['next_ai_decision_year']=e.year;e.rl_brains[2].select_action=lambda *args:'THEATRE:23:REQUEST_REINFORCEMENTS';e._theatre_action=lambda *args:False
  e._rl_war_decisions([c]);self.assertFalse(c['last_ai_action_success']);self.assertEqual(e.year+1,c['next_ai_decision_year'])
if __name__=='__main__':unittest.main()
