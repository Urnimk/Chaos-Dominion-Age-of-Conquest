import copy,tempfile,unittest
from pathlib import Path
import numpy as np
from diagnostic_test_support import settings,world
from war_engine import WarEngine
from province_tasks import update,progress

class TaskTests(unittest.TestCase):
 def prepare(self):
  e=WarEngine(world());land=e.world.terrain>=2;ids,count=np.unique(e.world.continent[land],return_counts=True);lm=int(ids[np.argmax(count)])
  mask=land&(e.world.continent==lm);ys,xs=np.where(mask);grid=np.indices(mask.shape)[1]
  e.world.territory[mask]=1;e.world.territory[mask&(grid>np.median(xs))]=2;e._mark_world_changed(1,2)
  e.countries[0]['alliance']=0;e.countries[1]['alliance']=0
  e.legal_targets=lambda cid:[dict(id=2,mode='land',landmass_id=lm)]
  point=tuple(np.argwhere(e.world.territory==1)[0]);e.local_population[point]+=1000000;e.local_soldiers[point]+=200000
  e.world_state_cache.values_changed('population');e.world_state_cache.values_changed('soldiers')
  c=e.countries[0];g=dict(target_landmass=lm,commitment_id=99,target_country=2)
  update(e,c,g);self.assertIsNotNone(c['province_task']);return e,c,g
 def test_task_persists_and_only_real_land_gain_refreshes_progress(self):
  with settings(0):
   e,c,g=self.prepare();first=copy.deepcopy(c['province_task']);e.year+=1;update(e,c,g)
   self.assertEqual(first['province_id'],c['province_task']['province_id']);self.assertEqual(first['last_progress_year'],c['province_task']['last_progress_year'])
   pid=first['province_id'];idx=e.world_state_cache.provinces.layout.indices[pid];foreign=idx[e.world.territory.ravel()[idx]==2];e.world.territory.ravel()[foreign[0]]=1;e._mark_world_changed(1,2)
   e.year+=1;update(e,c,g);self.assertEqual(c['province_task']['last_progress_year'],e.year)
 def test_timeout_replans_with_cooldown_and_bounded_history(self):
  with settings(0):
   e,c,g=self.prepare();pid=c['province_task']['province_id'];e.year+=41;update(e,c,g)
   self.assertEqual(c['province_task_history'][-1]['status'],'REPLAN');self.assertGreater(c['province_task_cooldowns'][str(pid)],e.year)
   self.assertTrue(c['province_task'] is None or c['province_task']['province_id']!=pid)
 def test_parent_change_cancels_task(self):
  with settings(0):
   e,c,g=self.prepare();g['commitment_id']=100;update(e,c,g)
   self.assertEqual(c['province_task_history'][-1]['status'],'CANCELLED');self.assertEqual(c['province_task']['parent_commitment'],100)
 def test_tactical_front_is_confined_to_task(self):
  with settings(0):
   e,c,g=self.prepare();points=e.world_state_cache.provinces.select_front(1,2,g['target_landmass'],'ATTACK_FRONT')
   self.assertGreater(len(points),0);self.assertTrue(np.all(e.world_state_cache.provinces.layout.ids[points[:,0],points[:,1]]==c['province_task']['province_id']))
 def test_completion_does_not_require_last_remote_cell(self):
  with settings(0):
   e,c,g=self.prepare();task=c['province_task'];pid=task['province_id'];idx=e.world_state_cache.provinces.layout.indices[pid]
   e.world.territory.ravel()[idx]=1;e.world.territory.ravel()[idx[-1]]=2;e.world.settlement.ravel()[idx]=0;e.local_soldiers.ravel()[idx]=0;e._mark_world_changed(1,2)
   update(e,c,g);self.assertEqual(c['province_task_history'][-1]['status'],'COMPLETED')
 def test_task_survives_save_and_load(self):
  with settings(0),tempfile.TemporaryDirectory() as folder:
   e,c,g=self.prepare();task=copy.deepcopy(c['province_task']);path=Path(folder)/'war.npz';e.save(path)
   loaded=WarEngine.load(copy.deepcopy(e.world),path);self.assertEqual(task,loaded.countries[0]['province_task'])

if __name__=='__main__':unittest.main()
