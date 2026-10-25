import copy,random,unittest
from types import SimpleNamespace
import numpy as np
from scipy import ndimage
import map_config as cfg
from province_strategy import ProvinceLayout,layout_for


def plain(h=160,w=224,seed=2026):
 return SimpleNamespace(terrain=np.full((h,w),2,np.uint8),continent=np.ones((h,w),np.int32),
    height=np.zeros((h,w),np.float32),water=np.zeros((h,w),np.uint8),settings=SimpleNamespace(seed=seed))

class IrregularProvinceTests(unittest.TestCase):
 def test_plain_mainland_has_nonrectangular_provinces_without_grid_seams(self):
  w=plain();p=ProvinceLayout.build(w,32);fill=[];cross=0
  for idx in p.indices[1:]:
   ys,xs=np.divmod(idx,w.terrain.shape[1]);fill.append(len(idx)/((ys.max()-ys.min()+1)*(xs.max()-xs.min()+1)))
   cross+=int(len(np.unique(xs//32))>1 or len(np.unique(ys//32))>1)
   mask=np.zeros((ys.max()-ys.min()+1,xs.max()-xs.min()+1),bool);mask[ys-ys.min(),xs-xs.min()]=1
   self.assertEqual(ndimage.label(mask)[1],1)
  self.assertLess(float(np.median(fill)),.85)
  self.assertGreater(cross/len(fill),.8)
 def test_build_is_repeatable_does_not_consume_rng_or_mutate_terrain(self):
  w=plain();before={k:getattr(w,k).copy() for k in ('terrain','continent','height','water')}
  py=random.getstate();nr=np.random.get_state();a=ProvinceLayout.build(w,32);b=ProvinceLayout.build(w,32)
  np.testing.assert_array_equal(a.ids,b.ids);self.assertEqual(py,random.getstate())
  after=np.random.get_state();self.assertEqual(nr[0],after[0]);np.testing.assert_array_equal(nr[1],after[1]);self.assertEqual(nr[2:],after[2:])
  for k,v in before.items():np.testing.assert_array_equal(v,getattr(w,k))
  w.settings.seed=731;c=ProvinceLayout.build(w,32);self.assertFalse(np.array_equal(a.ids,c.ids))
 def test_no_crossing_sea_or_island_ids_and_tiny_islands_remain(self):
  w=plain(80,128);w.terrain[:,60:68]=0;w.continent[:,60:68]=0;w.continent[:,68:]=2
  # An isolated one-cell island and a diagonal-only pair have no traversable bridge.
  w.terrain[20:25,20:25]=0;w.continent[20:25,20:25]=0
  w.terrain[22,22]=2;w.continent[22,22]=3
  p=ProvinceLayout.build(w,20);np.testing.assert_array_equal(p.ids>0,w.terrain>=2)
  tiny=int(p.ids[22,22]);self.assertEqual(len(p.indices[tiny]),1)
  for pid,idx in enumerate(p.indices[1:],1):self.assertTrue(np.all(w.continent.ravel()[idx]==p.islands[pid]))
  for pid in range(1,len(p.indices)):
   for neighbor in p.neighbors[pid]:self.assertEqual(p.islands[pid],p.islands[neighbor])
 def test_empty_map_single_cell_and_diagonal_cells(self):
  w=plain(16,16);w.terrain[:]=0;w.continent[:]=0;p=ProvinceLayout.build(w,8);self.assertEqual(len(p.indices),1)
  w.terrain[5,5]=w.terrain[6,6]=2;w.continent[5,5]=w.continent[6,6]=1
  p=ProvinceLayout.build(w,8);self.assertNotEqual(p.ids[5,5],p.ids[6,6]);self.assertEqual(len(p.indices),3)
 def test_layout_cache_tracks_seed_terrain_tuning_and_reuses_static_layout(self):
  w=plain();a=layout_for(w);self.assertIs(a,layout_for(w))
  old=cfg.PROVINCE_BOUNDARY_ROUGHNESS
  try:
   cfg.PROVINCE_BOUNDARY_ROUGHNESS=old+.4;b=layout_for(w);self.assertIsNot(a,b)
   self.assertIs(b,layout_for(w))
  finally:cfg.PROVINCE_BOUNDARY_ROUGHNESS=old
  w.settings.seed+=1;self.assertIsNot(b,layout_for(w))

if __name__=='__main__':unittest.main()
