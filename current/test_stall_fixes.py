import json,unittest
from unittest.mock import patch
from diagnostic_test_support import settings
import test_province_tasks as task_tests
from province_tasks import update,progress
from combat_feasibility import legal_actions,province_assessment

class StallFixTests(unittest.TestCase):
 def test_understrength_tactical_fractions_are_removed(self):
  with settings(0):
   e,c,g=task_tests.TaskTests().prepare();c['morale']=1.
   with patch('combat_feasibility.defense',return_value=300.):
    actions=legal_actions(e,c,2,(0,0),1000)
   self.assertNotIn('ATTACK:18',actions);self.assertNotIn('ATTACK:28',actions)
   self.assertIn('ATTACK:40',actions);self.assertIn('ATTACK:70',actions)
 def test_no_fraction_passes_when_maximum_force_is_insufficient(self):
  with settings(0):
   e,c,g=task_tests.TaskTests().prepare();c['morale']=1.
   with patch('combat_feasibility.defense',return_value=1000.):
    self.assertEqual(legal_actions(e,c,2,(0,0),1000),[])
 def test_blocked_task_replans_immediately_and_is_not_reselected(self):
  with settings(0):
   e,c,g=task_tests.TaskTests().prepare();pid=c['province_task']['province_id']
   with patch('province_tasks.province_assessment',return_value={'feasible':False,'reason':'INSUFFICIENT_COMMITTABLE_FORCE'}):update(e,c,g)
   self.assertIsNone(c['province_task']);self.assertEqual(c['province_task_history'][-1]['status'],'REPLAN')
   self.assertGreater(c['province_task_cooldowns'][str(pid)],e.year)
 def test_assessment_can_be_serialized_into_save(self):
  with settings(0):
   e,c,g=task_tests.TaskTests().prepare();a=province_assessment(e,c,2,c['province_task']['province_id'],g['target_landmass'])
   self.assertIs(type(a['feasible']),bool);json.dumps(a)
 def test_neighbor_support_is_capped_by_available_island_force(self):
  with settings(0):
   e,c,g=task_tests.TaskTests().prepare();m=progress(e,c,c['province_task'])
   self.assertGreaterEqual(m['support_army'],0)
   self.assertLessEqual(m['support_army'],e._theatre_committable(e._home_soldiers(c['id'],g['target_landmass'])))

if __name__=='__main__':unittest.main()
