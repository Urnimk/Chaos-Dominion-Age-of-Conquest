import copy,random,tempfile,time,threading,unittest
from pathlib import Path
from unittest import mock
import numpy as np
from diagnostic_test_support import settings,world,state
from war_engine import WarEngine
from simulation_runtime import capture_view,SimulationRuntime,RasterRuntime,sync_tree_rows

def wait_for(runtime,token,timeout=10):
    deadline=time.perf_counter()+timeout
    while time.perf_counter()<deadline:
        for packet in runtime.poll():
            if packet['token']==token and packet['done']:
                if packet.get('error'):raise AssertionError(packet['error'])
                return packet
        time.sleep(.002)
    raise AssertionError('worker timeout')

class RuntimeTests(unittest.TestCase):
    def test_ui_metrics_are_forwarded_without_sharing_diagnostic_timer_stack(self):
        with settings(2),tempfile.TemporaryDirectory() as folder:
            runtime=SimulationRuntime()
            try:
                first=wait_for(runtime,runtime.submit('initialize',world=world(),path=Path(folder)/'state',load_last=False))
                proxy=first['view'].diagnostics;self.assertIsNotNone(proxy)
                proxy.count('UI_refreshes');proxy.push_timer('ui:ranking_log_panels');proxy.pop_timer()
                self.assertEqual(runtime.engine.diagnostics.stack,[])
                wait_for(runtime,runtime.submit('advance',years=1))
                d=runtime.engine.diagnostics
                self.assertGreaterEqual(d.counts['UI_refreshes'],1)
                self.assertGreaterEqual(d.counts['presentation_snapshots'],1)
                self.assertEqual(d.stack,[])
            finally:wait_for(runtime,runtime.submit('close',save=False))
    def test_frozen_view_is_independent_and_reuses_unchanged_map_arrays(self):
        with settings(0):
            e=WarEngine(world());v=capture_view(e);again=capture_view(e,v)
            self.assertIs(v.world.territory,again.world.territory)
            old_population=v.local_population.copy();name=v.countries[0]['name']
            e.step(10);e.countries[0]['name']='backend only'
            np.testing.assert_array_equal(v.local_population,old_population)
            self.assertEqual(v.countries[0]['name'],name)
            with self.assertRaises(ValueError):v.local_population[0,0]=7
            self.assertIsNot(v.world_state_cache,e.world_state_cache)
    def test_worker_batch_matches_direct_engine_including_q_and_rng(self):
        with settings(0),tempfile.TemporaryDirectory() as folder:
            base=world();rng=random.getstate();direct=WarEngine(copy.deepcopy(base));direct.step(100);expected=state(direct)
            random.setstate(rng);runtime=SimulationRuntime()
            try:
                wait_for(runtime,runtime.submit('initialize',world=copy.deepcopy(base),path=Path(folder)/'state',load_last=False))
                result=wait_for(runtime,runtime.submit('advance',years=100));self.assertEqual(result['result'],100)
                actual=state(runtime.engine)
                for key in expected:
                    if isinstance(expected[key],np.ndarray):np.testing.assert_array_equal(expected[key],actual[key])
                    else:self.assertEqual(expected[key],actual[key],key)
            finally:wait_for(runtime,runtime.submit('close',save=False))
    def test_queued_save_is_after_complete_year_and_worker_recovers_from_error(self):
        with settings(0),tempfile.TemporaryDirectory() as folder:
            runtime=SimulationRuntime();path=Path(folder)/'state.npz'
            try:
                first=wait_for(runtime,runtime.submit('initialize',world=world(),path=path,load_last=False))
                initial_year=first['view'].year
                advance=runtime.submit('advance',years=30);save=runtime.submit('save',path=path)
                saved=wait_for(runtime,save);self.assertEqual(saved['result'],initial_year+30)
                loaded=WarEngine.load(copy.deepcopy(first['view'].world),path)
                self.assertEqual(loaded.year,initial_year+30)
                bad=runtime.submit('unknown');deadline=time.perf_counter()+3;error=False
                while time.perf_counter()<deadline and not error:
                    error=any(p['token']==bad and p.get('error') for p in runtime.poll());time.sleep(.002)
                self.assertTrue(error);wait_for(runtime,runtime.submit('advance',years=1))
            finally:wait_for(runtime,runtime.submit('close',save=False))
    def test_raster_requests_are_coalesced_and_stale_result_is_rejected(self):
        started=threading.Event();release=threading.Event();calls=[]
        def render(world,layer):
            calls.append(world)
            if world==0:started.set();release.wait(3)
            return world
        raster=RasterRuntime(render)
        try:
            raster.request(0,'map');self.assertTrue(started.wait(2))
            for i in range(1,101):token=raster.request(i,'map')
            release.set();deadline=time.perf_counter()+3;result=None
            while time.perf_counter()<deadline and result is None:result=raster.poll();time.sleep(.002)
            self.assertEqual(result[0],token);self.assertEqual(result[2],100);self.assertEqual(calls,[0,100])
        finally:raster.stop()

class FakeTree:
    def __init__(self):self.rows={};self.order=[];self.writes=0
    def get_children(self):return tuple(self.order)
    def exists(self,i):return i in self.rows
    def item(self,i,**kw):
        if kw:self.rows[i].update(kw);self.writes+=1
        return self.rows[i]
    def insert(self,parent,index,iid,text,values):
        self.rows[iid]=dict(text=text,values=values);self.order.insert(index,iid);self.writes+=1
    def move(self,i,parent,index):self.order.remove(i);self.order.insert(index,i);self.writes+=1
    def delete(self,i):self.order.remove(i);self.rows.pop(i);self.writes+=1

class TreeTests(unittest.TestCase):
    def test_unchanged_rows_do_not_rebuild_and_sort_uses_existing_ids(self):
        tree=FakeTree();rows=[('1','one',(1,2)),('2','two',(3,4))];sync_tree_rows(tree,rows)
        tree.writes=0;sync_tree_rows(tree,rows);self.assertEqual(tree.writes,0)
        sync_tree_rows(tree,list(reversed(rows)));self.assertEqual(tree.order,['2','1']);self.assertEqual(tree.writes,1)

if __name__=='__main__':unittest.main()
