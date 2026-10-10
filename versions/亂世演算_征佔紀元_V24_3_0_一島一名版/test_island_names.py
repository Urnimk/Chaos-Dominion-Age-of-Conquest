import unittest, copy
from types import SimpleNamespace
import numpy as np
from war_engine import WarEngine

class IslandNameTests(unittest.TestCase):
    def setUp(self):
        self.e=WarEngine.__new__(WarEngine)
        land=np.array([[1,1,0,3,3],[1,1,0,3,0],[0,0,0,0,0]],dtype=np.int32)
        self.e.world=SimpleNamespace(continent=land,settings=SimpleNamespace(width=5,height=3))
        self.e.rng=np.random.default_rng(42)
        self.e._initialize_island_names()
    def test_one_name_per_island_and_ocean(self):
        e=self.e
        self.assertEqual(len(e.islands),2)
        self.assertEqual(e.geographic_name_at(0,0),e.geographic_name_at(1,1))
        self.assertEqual(e.geographic_name_at(0,2),'海域')
        self.assertNotEqual(e.landmass_place_name(1),e.landmass_place_name(3))
        self.assertEqual(e.landmass_place_name(3,{'capital':[0,0]}),e.geographic_name_at(0,3))
    def test_centers_on_correct_land_and_compatibility(self):
        for r in self.e.geographic_regions:
            x,y=r['center'];self.assertEqual(self.e.world.continent[y,x],r['id'])
        np.testing.assert_array_equal(self.e.geographic_region_id,self.e.world.continent)
    def test_migrate_largest_region_and_history_aliases(self):
        ids=np.array([[1,1,0,3,3],[1,2,0,3,0],[0,0,0,0,0]],dtype=np.int32)
        regions=[dict(id=1,name='晨曦平原'),dict(id=2,name='暮色山地'),dict(id=3,name='碧玉海岸')]
        self.e._initialize_island_names(legacy_regions=regions,legacy_ids=ids)
        self.assertEqual(self.e.landmass_place_name(1),'晨曦島')
        self.assertEqual(self.e.island_display_text('暮色山地：島1，陸塊3'), '晨曦島：晨曦島，碧玉海岸')
    def test_stable_reload_and_rng(self):
        state=copy.deepcopy(self.e.rng.bit_generator.state)
        saved=copy.deepcopy(self.e.islands)
        self.e._initialize_island_names(saved=saved)
        self.assertEqual(self.e.islands,saved)
        self.assertEqual(self.e.rng.bit_generator.state,state)
    def test_duplicate_legacy_roots_get_unique_names(self):
        saved=[dict(id=1,name='晨曦島'),dict(id=3,name='晨曦島')]
        self.e._initialize_island_names(saved=saved)
        self.assertEqual(len(set(self.e.island_names.values())),2)
    def test_link_aliases_use_island_centers(self):
        from map_viewer import MapViewer
        view=MapViewer.__new__(MapViewer);view.war=self.e
        self.e.countries=[];view._alliance_groups=lambda:[]
        links=view._entity_aliases(include_places=True)
        self.assertEqual(len(links),2)
        for name,kind,(x,y,label) in links:
            self.assertEqual(kind,'place');self.assertEqual(name,label)
            self.assertEqual(self.e.island_name_at(y,x),name)

if __name__=='__main__':unittest.main()
