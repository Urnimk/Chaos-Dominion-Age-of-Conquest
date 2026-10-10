"""Run: python -m unittest test_overseas_restrictions -v"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import map_config as cfg
from war_engine import WarEngine, Campaign

class OverseasRestrictionTests(unittest.TestCase):
    def setUp(self):
        self.e = e = WarEngine.__new__(WarEngine)
        e.year = 100
        e.world = SimpleNamespace(settings=SimpleNamespace(width=1000,height=700),
            territory=np.zeros((700,1000),dtype=np.int32),
            continent=np.full((700,1000),2,dtype=np.int32),
            terrain=np.full((700,1000),2,dtype=np.int8),
            settlement=np.zeros((700,1000),dtype=np.int8))
        e.countries = [dict(id=1,alive=True,alliance=0,capital=[900,600],fleet=0),
                       dict(id=2,alive=True,alliance=0,capital=[0,0],overseas_capitals=[])]
        e.country = lambda cid:e.countries[cid-1]
        self.c=e.countries[0]
        e.world.territory[0,0]=2
        e._home_continent_id = lambda c:1
        e._log=Mock()
    def test_expiry_exact_boundary_and_country_isolation(self):
        e=self.e;e._record_overseas_failure(self.c,2)
        e.year=50099
        self.assertTrue(e._overseas_attack_banned(self.c,2))
        self.assertFalse(e._overseas_attack_banned(self.c,3))
        self.assertFalse(e._overseas_attack_banned(e.country(2),2))
        e.year=50100;self.assertFalse(e._overseas_attack_banned(self.c,2))
    def test_returning_remains_blocked_until_arrival(self):
        self.c['reinforcement_voyage']=dict(returning=True,continent_id=2,return_reason='strategic_evacuation')
        self.e.year=999999
        self.assertTrue(self.e._overseas_attack_banned(self.c,2))
        self.e._record_overseas_failure(self.c,2)
        self.c['reinforcement_voyage']=None
        self.assertEqual(self.c['overseas_attack_bans']['2'],1049999)
    def test_home_failure_not_recorded(self):
        self.e._record_overseas_failure(self.c,1)
        self.assertNotIn('overseas_attack_bans',self.c)
    def test_configured_distance_boundary_and_wrapping(self):
        d=cfg.OVERSEAS_LANDING_CAPITAL_MIN_DISTANCE
        cells=np.array([[0,d-1],[0,d],[0,d+1],[0,999],[d,0]])
        np.testing.assert_array_equal(self.e._safe_overseas_landing_cells(1,cells),cells[[1,2,4]])
    def test_other_enemy_overseas_capital_and_allies(self):
        self.e.countries.append(dict(id=3,alive=True,alliance=0,capital=[800,600],
            overseas_capitals=[dict(anchor=[400,400])]))
        self.e.world.territory[400,400]=3
        cells=np.array([[400,401]])
        self.assertEqual(len(self.e._safe_overseas_landing_cells(1,cells)),0)
        self.c['alliance']=7;self.e.country(3)['alliance']=7
        self.assertEqual(len(self.e._safe_overseas_landing_cells(1,cells)),1)
    def test_no_safe_landing_returns_none(self):
        e=self.e;e.world.territory[0,1:50]=2
        self.assertIsNone(e._objective(1,2,'naval',2))
    def test_banned_objective_and_launch_even_with_cached_options(self):
        e=self.e;e._record_overseas_failure(self.c,2)
        self.assertIsNone(e._objective(1,2,'naval',2))
        e.legal_targets=lambda cid:[dict(id=2,mode='naval',landmass_id=2,distance=1)]
        self.assertIsNone(e.launch_campaign(1,2,'land'))
        # Sorting helpers run before the launch gate; supply harmless fixtures.
        e._spatial_indices=lambda *a:[];e._home_soldiers=lambda *a:0
        self.assertIsNone(e.launch_campaign(1,2,'naval'))
    def test_unsafe_inflight_cancelled_without_battle_or_defeat(self):
        e=self.e;e.world.territory[0,10]=2
        e._add_local_soldiers=Mock();e._sync_army_totals=Mock()
        c=Campaign(1,1,2,'naval',(600,900),(0,10),500,3,20,0,0,origin_landmass=1)
        e._battle([c])
        self.assertEqual(c.status,'cancelled');self.assertEqual(self.c['fleet'],3)
        self.assertNotIn('overseas_attack_bans',self.c)
        e._add_local_soldiers.assert_called_once()

if __name__=='__main__':unittest.main()
