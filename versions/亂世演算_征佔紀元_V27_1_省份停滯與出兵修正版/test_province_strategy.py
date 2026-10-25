import copy,random,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy import ndimage
import map_config as cfg
from diagnostic_test_support import settings,world,state
from war_engine import WarEngine
from province_strategy import ProvinceLayout,layout_for
from simulation_runtime import capture_view
from map_renderer import render_environment

class ProvinceTests(unittest.TestCase):
    def test_partition_exact_connected_deterministic(self):
        with settings(0):
            e=WarEngine(world());w=e.world;a=layout_for(w);b=ProvinceLayout.build(w,cfg.PROVINCE_SIDE_CELLS)
            np.testing.assert_array_equal(a.ids,b.ids)
            np.testing.assert_array_equal(a.ids>0,w.terrain>=2)
            all_idx=np.concatenate(a.indices[1:]);self.assertEqual(len(all_idx),len(np.unique(all_idx)))
            for pid,idx in enumerate(a.indices[1:],1):
                self.assertTrue(np.all(w.continent.ravel()[idx]==a.islands[pid]))
                ys,xs=np.divmod(idx,w.terrain.shape[1]);mask=np.zeros((ys.max()-ys.min()+1,xs.max()-xs.min()+1),bool);mask[ys-ys.min(),xs-xs.min()]=1
                self.assertEqual(ndimage.label(mask)[1],1)
                self.assertFalse(idx.flags.writeable)
                for n in a.neighbors[pid]:self.assertIn(pid,a.neighbors[n])
            self.assertFalse(a.ids.flags.writeable)
    def test_frontier_exact_all_pairs_and_horizontal_wrap(self):
        with settings(0):
            e=WarEngine(world());p=e.world_state_cache.provinces
            for a in e.countries:
                for b in e.countries:
                    if a==b:continue
                    for lm in [None,*sorted(e.world_state_cache.country_landmasses(b['id']))]:
                        mask=(e.world.territory==b['id'])&e._adjacent_land_mask(e.world.territory==a['id'])
                        if lm is not None:mask &= e.world.continent==lm
                        expected=np.flatnonzero(mask)
                        groups=p.frontier(a['id'],b['id'],lm)
                        actual=np.sort(np.concatenate(list(groups.values()))) if groups else np.empty(0,int)
                        np.testing.assert_array_equal(actual,expected)
            # Synthetic seam and top/bottom: wrap only in x.
            e.world.territory[:]=0;e.world.territory[10,0]=1;e.world.territory[10,-1]=2
            e.world.territory[0,50]=1;e.world.territory[-1,50]=2
            # Use known land coordinates for ids in this synthetic territory test.
            ids=p.layout.ids.copy();ids[10,-1]=1;ids[-1,50]=1
            p._layout=SimpleNamespace(ids=ids);e._mark_world_changed(1,2)
            front=p.frontier(1,2);points=np.concatenate(list(front.values()))
            self.assertIn(10*e.world.territory.shape[1]+e.world.territory.shape[1]-1,points)
            self.assertNotIn(e.world.territory.size-e.world.territory.shape[1]+50,points)
    def test_targeted_invalidation_and_buildings(self):
        with settings(0):
            e=WarEngine(world());p=e.world_state_cache.provinces;pid=1;idx=p.layout.indices[pid];point=int(idx[0]);y,x=divmod(point,e.world.terrain.shape[1]);cid=int(e.world.territory[y,x])
            s=p.summary(pid);before=s['population'].get(cid,0);food=p.totals(pid,'food')
            other=next(q for q in range(2,len(p.layout.indices)));unchanged=p.totals(other,'population')
            e.local_population[y,x]+=9;e.world_state_cache.values_changed('population',(y,x))
            self.assertEqual(p.totals(pid,'population').get(cid,0),before+9)
            self.assertIs(p.totals(other,'population'),unchanged);self.assertIs(p.totals(pid,'food'),food)
            e.world.settlement[y,x]=2;self.assertEqual(p.summary(pid)['buildings'],int(np.count_nonzero(e.world.settlement.ravel()[idx])))
            before=p.totals(pid,'population');owner=next(c['id'] for c in e.countries if c['id']!=cid)
            e.world.territory[y,x]=owner;e._mark_world_changed(cid,owner,landmass_ids=[p.layout.islands[pid]])
            self.assertEqual(p.totals(pid,'population').get(owner,0),before.get(owner,0)+int(e.local_population[y,x]))
    def test_country_bulk_unknown_and_flat_invalidation(self):
        with settings(0):
            e=WarEngine(world());p=e.world_state_cache.provinces
            for mode in ('country','flat','unknown'):
                for pid in range(1,len(p.layout.indices)):p.summary(pid)
                c=e.countries[0];idx=e._spatial_indices(c['id']);e.local_soldiers.ravel()[idx]=0
                if mode=='country':e.world_state_cache.values_changed('soldiers',country_id=c['id'])
                elif mode=='flat':e.world_state_cache.values_changed('soldiers',idx,flat=True)
                else:e.world_state_cache.values_changed('soldiers')
                for pid in range(1,len(p.layout.indices)):
                    owned=p.layout.indices[pid];owned=owned[e.world.territory.ravel()[owned]==c['id']]
                    self.assertEqual(p.totals(pid,'soldiers').get(c['id'],0),int(e.local_soldiers.ravel()[owned].sum()))
    def test_selection_is_legal_bounded_and_no_rng_mutation(self):
        with settings(0):
            e=WarEngine(world());p=e.world_state_cache.provinces;selected=0
            # Establish a real land border; initial generated realms may be separated by neutral land.
            land=np.argwhere(e.world.terrain>=2);island=int(e.world.continent[tuple(land[len(land)//2])])
            mask=(e.world.continent==island)&(e.world.terrain>=2);ys,xs=np.where(mask)
            e.world.territory[mask]=1;e.world.territory[mask & (np.indices(mask.shape)[1]>np.median(xs))]=2
            e._mark_world_changed(1,2);e._build_geography();before=state(e)
            for (a,b) in e.land_contacts:
                groups=p.frontier(a,b)
                if not groups:continue
                points=p.select_front(a,b,None,'ATTACK_FRONT');selected+=1
                self.assertGreater(len(points),0)
                self.assertLessEqual(len(np.unique(p.layout.ids[points[:,0],points[:,1]])),cfg.PROVINCE_FRONT_CANDIDATES)
                self.assertTrue(np.all(e.world.territory[points[:,0],points[:,1]]==b))
                self.assertTrue(np.all(e._adjacent_land_mask(e.world.territory==a)[points[:,0],points[:,1]]))
                for tactic in ('ATTACK_FRONT','ENCIRCLE_CAPITAL','RECOVER_PORT','CUT_OFF'):
                    e._selected_theatre=(a,int(e.world.continent[tuple(points[0])]),tactic)
                    obj=e._objective(a,b,'land');self.assertIsNotNone(obj);self.assertEqual(e.world.territory[obj],b)
            self.assertGreater(selected,0)
            after=state(e)
            for key in before:
                if isinstance(before[key],np.ndarray):np.testing.assert_array_equal(before[key],after[key])
                else:self.assertEqual(before[key],after[key],key)
    def test_snapshot_shares_geometry_not_dynamic_cache(self):
        with settings(0):
            e=WarEngine(world());p=e.world_state_cache.provinces;p.summary(1)
            view=capture_view(e);q=view.world_state_cache.provinces
            self.assertIs(q.layout,p.layout);self.assertIsNot(q._values,p._values)
            before=q.summary(1);idx=p.layout.indices[1][0];e.local_population.ravel()[idx]+=20;e.world_state_cache.values_changed('population',idx,flat=True)
            self.assertEqual(q.summary(1),before)
    def test_overlay_preserves_building_pixels_and_world(self):
        with settings(0):
            e=WarEngine(world());before=state(e)
            for style in ('CLASSIC','PARCHMENT'):
                base=np.asarray(render_environment(e.world,'國家與領土',visual_style=style))
                overlay=np.asarray(render_environment(e.world,'省區分界',visual_style=style))
                mask=ndimage.binary_dilation(e.world.settlement==1,iterations=3)|ndimage.binary_dilation((e.world.settlement>=2)&(e.world.settlement<=4),iterations=2);np.testing.assert_array_equal(base[mask],overlay[mask])
                self.assertTrue(np.any(base!=overlay))
            np.testing.assert_array_equal(before['territory'],e.world.territory);self.assertEqual(before['rng'],e.rng.bit_generator.state)
    def test_frontier_cache_tracks_expansion_and_cell_capture(self):
        from map_generator import generate_world,MapSettings
        with settings(0):
            cfg.COUNTRY_COUNT=12;random.seed(2026)
            e=WarEngine(generate_world(MapSettings(384,256,2026,'RANDOM',.7)))
            p=e.world_state_cache.provinces;seen=False
            for year in range(400):
                if year%20==0:
                    for (a,b) in e.land_contacts:
                        expected=np.flatnonzero((e.world.territory==b)&e._adjacent_land_mask(e.world.territory==a))
                        groups=p.frontier(a,b)
                        actual=np.sort(np.concatenate(list(groups.values()))) if groups else np.empty(0,int)
                        np.testing.assert_array_equal(expected,actual);seen |= bool(len(actual))
                e.step(1)
            self.assertTrue(seen);self.assertGreater(e.battles,0)
            (a,b)=next(pair for pair in e.land_contacts if p.frontier(*pair))
            point=next(iter(p.frontier(a,b).values()))[0];center=divmod(int(point),e.world.territory.shape[1])
            before=e.world.territory.copy();count=e._capture_nearest_loser_cell(a,b,center)
            self.assertEqual(count,1);self.assertEqual(np.count_nonzero(before!=e.world.territory),1)

    def test_save_load_geometry_and_continuation(self):
        with settings(0),tempfile.TemporaryDirectory() as temp:
            e=WarEngine(world());e.step(30);path=Path(temp)/'save.npz';e.save(path)
            loaded=WarEngine.load(copy.deepcopy(e.world),path)
            np.testing.assert_array_equal(e.world_state_cache.provinces.layout.ids,loaded.world_state_cache.provinces.layout.ids)
            rng=random.getstate();e.step(100);random.setstate(rng);loaded.step(100)
            for key,value in state(e).items():
                actual=state(loaded)[key]
                if isinstance(value,np.ndarray):np.testing.assert_array_equal(value,actual)
                else:self.assertEqual(value,actual,key)
    def test_statistics_consistent_during_200_years(self):
        with settings(0):
            e=WarEngine(world());p=e.world_state_cache.provinces
            for year in range(200):
                for pid in range(1,len(p.layout.indices)):
                    for field in ('population','soldiers','food'):
                        values=p.totals(pid,field);idx=p.layout.indices[pid];owners=e.world.territory.ravel()[idx]
                        arr=getattr(e,{'population':'local_population','soldiers':'local_soldiers','food':'food_yield'}[field]).ravel()
                        expected={int(cid):float(arr[idx[owners==cid]].sum()) if field=='food' else int(arr[idx[owners==cid]].sum()) for cid in np.unique(owners)}
                        self.assertEqual(dict(values),expected,(year,pid,field))
                e.step(1)

if __name__=='__main__':unittest.main()
