import copy,random,tempfile,unittest
from pathlib import Path
import numpy as np
from diagnostic_test_support import settings,world,state
from war_engine import WarEngine

class RegionCacheTests(unittest.TestCase):
    def make(self):return WarEngine(world())
    def prime(self,e):
        for c in e.countries:
            for lm in e.world_state_cache.country_landmasses(c['id']):
                for field in ('population','soldiers','food'):e.world_state_cache.total(field,c['id'],lm)
                e.world_state_cache.regimes(lm)
    def test_scalar_change_keeps_unrelated_country_and_static_food(self):
        with settings(0):
            e=self.make();self.prime(e);h=e.world_state_cache
            c=e.countries[0];x,y=c['capital'];lm=int(e.world.continent[y,x])
            before=h.total('population',c['id'],lm);food=h.total('food',c['id'],lm)
            other=next(key for key in h._values if key[0]=='population' and key[1]!=c['id'])
            e.local_population[y,x]+=7;h.values_changed('population',(y,x))
            self.assertEqual(h.total('population',c['id'],lm),before+7)
            self.assertIn(other,h._values);self.assertEqual(h.total('food',c['id'],lm),food)
            h.debug_assert_consistent()
    def test_embark_disembark_and_population_move_invalidate(self):
        with settings(0):
            e=self.make();c=e.countries[0];cid=c['id'];lm=e._home_continent_id(c)
            self.prime(e);h=e.world_state_cache;army=h.total('soldiers',cid,lm)
            taken=e._take_local_soldiers(cid,lm,15)
            self.assertEqual(h.total('soldiers',cid,lm),army-taken)
            e._add_local_soldiers(cid,lm,taken)
            self.assertEqual(h.total('soldiers',cid,lm),army)
            mask=(e.world.territory==cid)&(e.world.continent==lm);x,y=c['capital']
            before=h.total('population',cid,lm);e._move_population_group(mask,y,x,20)
            self.assertEqual(h.total('population',cid,lm),before);h.debug_assert_consistent()
    def test_territory_change_and_new_country_pad_counts(self):
        with settings(0):
            e=self.make();self.prime(e);a,b=e.countries[:2];y,x=np.argwhere(e.world.territory==a['id'])[0];lm=int(e.world.continent[y,x])
            e.world_state_cache.landmass_ownership(lm);before=e.world_state_cache.total('population',b['id'],lm)
            e.world.territory[y,x]=b['id'];e._mark_world_changed(a['id'],b['id'],landmass_ids=[lm])
            self.assertEqual(e.world_state_cache.total('population',b['id'],lm),before+int(e.local_population[y,x]))
            e.world_state_cache.debug_assert_consistent();e.countries.append(dict(id=len(e.countries)+1))
            self.assertEqual(len(e.world_state_cache.landmass_ownership(lm)[1]),len(e.countries)+1)
    def test_queries_do_not_consume_rng_and_spatial_order_is_identical(self):
        with settings(0):
            e=self.make();rng=copy.deepcopy(e.rng.bit_generator.state);py=random.getstate()
            self.prime(e)
            for c in e.countries:
                for lm in e.world_state_cache.country_landmasses(c['id']):
                    expected=np.flatnonzero((e.world.territory==c['id'])&(e.world.continent==lm))
                    np.testing.assert_array_equal(e._spatial_indices(c['id'],lm),expected)
                    e.world_state_cache.region(c['id'],lm)
            self.assertEqual(rng,e.rng.bit_generator.state);self.assertEqual(py,random.getstate())
    def test_prime_every_year_and_assert_all_fields_for_300_years(self):
        with settings(0):
            e=self.make()
            for _ in range(300):
                self.prime(e);e.step(1);e.world_state_cache.debug_assert_consistent()
    def test_save_reload_then_continue_100_years(self):
        with settings(0),tempfile.TemporaryDirectory() as folder:
            e=self.make();e.step(50);self.prime(e);path=Path(folder)/'state.npz';e.save(path)
            loaded=WarEngine.load(copy.deepcopy(e.world),path)
            rng=random.getstate();e.step(100);random.setstate(rng);loaded.step(100)
            a,b=state(e),state(loaded)
            for key in a:
                if isinstance(a[key],np.ndarray):np.testing.assert_array_equal(a[key],b[key])
                else:self.assertEqual(a[key],b[key],key)

if __name__=='__main__':unittest.main()
