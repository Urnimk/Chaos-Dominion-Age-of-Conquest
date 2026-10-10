import unittest
from unittest.mock import Mock
from types import SimpleNamespace
import numpy as np
import map_config as cfg
from overseas_strategy import OverseasStrategyMixin
import test_theatre_logistics as theatre_tests

class TransportPriorityTests(unittest.TestCase):
    def setUp(self):
        fixture=theatre_tests.LogisticsTests();fixture.setUp()
        self.e,self.c,self.t=fixture.e,fixture.c,fixture.t
        self.e.year=1000

    def test_only_inbound_matching_transport_counts_as_wait(self):
        for returning,lm,expected in [(False,7,True),(False,8,False),(True,7,False),(True,8,False)]:
            self.c['reinforcement_voyage']=dict(returning=returning,continent_id=lm)
            self.assertEqual(self.e._voyage_supports_theatre(self.c,7),expected)
        self.c['reinforcement_voyage']=None
        self.assertFalse(self.e._voyage_supports_theatre(self.c,7))

    def return_fixture(self):
        e=self.e;site=dict(continent_id=7,supply_food=0)
        self.c['overseas_capitals']=[site]
        e._overseas_landmass_is_pacified=lambda *a:True
        e._theatre=lambda *a:dict(self.t,army=300,population=1000,target=120,enemies=[])
        e.food_yield=np.zeros((1,2))
        return site

    def test_front_need_prevents_return_even_if_unfunded(self):
        site=self.return_fixture();self.c['overseas_capitals'].append(dict(continent_id=8))
        self.e._theatre=lambda c,s:dict(self.t,enemies=[2] if s['continent_id']==8 else [],gap=90)
        self.assertFalse(self.e._return_peacetime_surplus(self.c,site))
        self.assertNotIn('peacetime_shortage_since_year',site)

    def test_stock_supported_population_does_not_trigger_return(self):
        site=self.return_fixture();site['supply_food']=10000
        self.assertFalse(self.e._return_peacetime_surplus(self.c,site))
        self.assertNotIn('peacetime_shortage_since_year',site)

    def test_shortage_duration_and_cooldown(self):
        site=self.return_fixture()
        self.assertFalse(self.e._return_peacetime_surplus(self.c,site))
        self.assertEqual(site['peacetime_shortage_since_year'],1000)
        self.e.year=1029
        self.assertFalse(self.e._return_peacetime_surplus(self.c,site))
        site['last_peacetime_return_year']=1000;self.e.year=1030
        self.assertFalse(self.e._return_peacetime_surplus(self.c,site))

    def test_one_soldier_surplus_does_not_launch(self):
        site=self.return_fixture();site['peacetime_shortage_since_year']=900
        self.e._theatre=lambda *a:dict(self.t,army=121,population=1000,target=120,enemies=[])
        self.assertFalse(self.e._return_peacetime_surplus(self.c,site))
        self.assertNotIn('reinforcement_voyage',self.c)

    def test_overseas_donor_uses_its_own_food_and_keeps_reserve(self):
        e=self.e;site=dict(continent_id=1,logistics_port=[0,0],supply_food=10000)
        e._logistics_port=lambda *a:(0,0)
        e.food_yield=np.zeros((1,2))
        self.c['food']=0
        m=e._reinforcement_manifest_from(self.c,self.t,site)
        self.assertIsNotNone(m)
        self.assertIs(m['source_site'],site)
        self.assertEqual(m['home'],1)
        self.assertLessEqual(m['amount'],300-120)
        site['supply_food']=100
        self.assertIsNone(e._reinforcement_manifest_from(self.c,self.t,site))

    def test_near_pacified_base_can_be_selected(self):
        e=self.e;site=dict(continent_id=8)
        self.c['overseas_capitals']=[site]
        e._overseas_landmass_is_pacified=lambda *a:True
        def manifest(c,t,source_site=None):
            return dict(amount=90,supply=100,years=2 if source_site else 10,source_site=source_site)
        e._reinforcement_manifest_from=manifest
        self.assertIs(e._reinforcement_manifest(self.c,self.t)['source_site'],site)

if __name__=='__main__':unittest.main()
