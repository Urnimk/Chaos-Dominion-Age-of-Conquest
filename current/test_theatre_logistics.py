"""Regression tests: python -m unittest test_theatre_logistics -v"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import map_config as cfg
from overseas_strategy import OverseasStrategyMixin
from country_generator import PORT

class LogisticsTests(unittest.TestCase):
    def setUp(self):
        self.e=e=OverseasStrategyMixin()
        e.world=SimpleNamespace(territory=np.array([[1,1]]),continent=np.array([[1,7]]),
                                settlement=np.array([[PORT,PORT]]),settings=SimpleNamespace(width=2))
        e.local_population=np.array([[1000,177]])
        e.campaigns=[]
        e._home_continent_id=lambda c:1
        e._spatial_indices=lambda cid,lm:np.array([0 if lm==1 else 1])
        e._home_soldiers=lambda cid,lm:300
        e._wrapped_distance_cells=lambda *a:1
        e._sea_route=lambda *a:[(0,0),(1,0)]
        e._route_distance_km=lambda r:100
        e._overseas_population_budget=lambda *a:dict(capacity=553,safe_capacity=497,residents=526,incoming=0,people=0)
        e._transport_population_capacity=lambda fleet:1000 if fleet else 0
        e._transport_soldier_capacity=lambda fleet:1000 if fleet else 0
        self.c=dict(id=1,fleet=100,food=100000,morale=1.15)
        self.t=dict(lm=7,port=(1,0),army=31,population=177,gap=90,enemies=[2],supply_need=0)

    def test_overfull_island_accepts_funded_soldiers_only(self):
        m=self.e._reinforcement_manifest(self.c,self.t)
        self.assertEqual(m['amount'],90)
        self.assertEqual(m['people'],m['amount'])
        self.assertGreater(m['supply'],0)
        self.assertEqual(m['budget']['people'],0)

    def test_peace_keeps_civilian_capacity_limit(self):
        self.t['enemies']=[]
        self.assertIsNone(self.e._reinforcement_manifest(self.c,self.t))

    def test_food_fleet_home_reserve_and_duplicate_voyage(self):
        for key,value in [('food',0),('fleet',0),('reinforcement_voyage',{'soldiers':10})]:
            with self.subTest(key=key):
                self.assertIsNone(self.e._reinforcement_manifest(dict(self.c,**{key:value}),self.t))
        self.e._home_soldiers=lambda *a:35
        self.assertIsNone(self.e._reinforcement_manifest(self.c,self.t))

    def test_marching_troops_do_not_free_military_capacity(self):
        self.e.campaigns=[SimpleNamespace(attacker=1,status='marching',mode='land',origin_landmass=7,soldiers=245)]
        self.assertIsNone(self.e._reinforcement_manifest(self.c,self.t))

    def test_small_gap_is_not_permanently_ignored(self):
        self.t['gap']=5
        self.assertEqual(self.e._reinforcement_manifest(self.c,self.t)['amount'],5)

    def test_offensive_requirement_includes_new_residents_and_rounding(self):
        self.e._theatre_defenses=lambda *a:[(41.6392,dict(id=2))]
        self.c['recovery_until_year']=99999
        total=self.e._offensive_theatre_target(self.c,7,349,62)
        self.assertGreater(total,62)
        def power(n):
            return self.e._theatre_committable(n-int((349+max(0,n-62))*cfg.MIN_GARRISON_RATIO))*self.c['morale']
        required=41.6392*cfg.AI_OFFENSIVE_SAFETY_RATIO
        self.assertGreaterEqual(power(total),required)
        self.assertLess(power(total-1),required)

if __name__=='__main__':unittest.main()
