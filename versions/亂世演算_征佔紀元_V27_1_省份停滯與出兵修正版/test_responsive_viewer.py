"""Exercise the real viewer adapter without an X server; no fake engine."""
import heapq,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from PIL import Image
import map_viewer as ui
from diagnostic_test_support import settings,world
from war_engine import WarEngine
from simulation_runtime import capture_view
from test_simulation_runtime import FakeTree

class MainThreadRoot:
    def __init__(self):self.main=threading.get_ident();self.pending=[];self.seq=0;self.closed=False
    def check(self):assert threading.get_ident()==self.main,'Tk called outside main thread'
    def after(self,ms,func,*args):
        self.check();self.seq+=1;heapq.heappush(self.pending,(time.perf_counter()+ms/1000,self.seq,func,args))
    def after_idle(self,func):self.after(0,func)
    def destroy(self):self.check();self.closed=True
    def pump(self,condition,seconds=8):
        end=time.perf_counter()+seconds
        while time.perf_counter()<end and not condition():
            if self.pending and self.pending[0][0]<=time.perf_counter():
                _,_,fn,args=heapq.heappop(self.pending);fn(*args)
            else:time.sleep(.001)
        assert condition(),'UI event loop timeout'

class Var:
    def __init__(self,root,value=''):self.root=root;self.value=value
    def get(self):self.root.check();return self.value
    def set(self,value):self.root.check();self.value=value
    def configure(self,**kw):self.root.check()

class ViewerTests(unittest.TestCase):
    def test_territory_list_uses_exact_snapshot_totals_without_rebuilding(self):
        with settings(0):
            e=WarEngine(world());v=ui.MapViewer.__new__(ui.MapViewer)
            v.war=capture_view(e);v.world=v.war.world
            class TerritoryTree(FakeTree):
                def yview(self):return (.2,.8)
                def yview_moveto(self,value):pass
            v.colony_links=TerritoryTree();v.colony_voyages=SimpleNamespace(configure=lambda **kw:None)
            c=v.war.countries[0];v._refresh_colony_links(c)
            self.assertTrue(v.colony_links.rows)
            values=next(iter(v.colony_links.rows.values()))['values'];lm=v.war._home_continent_id(c)
            mask=(v.world.territory==c['id'])&(v.world.continent==lm)
            self.assertEqual(values[3],f"{int(v.war.local_population[mask].sum()):,}")
            self.assertEqual(values[4],f"{int(v.war.local_soldiers[mask].sum()):,}")
            v.colony_links.writes=0;v._refresh_colony_links(c);self.assertEqual(v.colony_links.writes,0)
    def test_repeated_load_requests_are_coalesced(self):
        v=ui.MapViewer.__new__(ui.MapViewer);v._runtime_pending={}
        v._runtime=SimpleNamespace(submit=mock.Mock(return_value=7))
        self.assertEqual(v._runtime_submit('load',path='state'),7)
        self.assertEqual(v._runtime_submit('load',path='state'),7)
        self.assertEqual(v._runtime.submit.call_count,1)
    def test_auto_save_failure_backoff_does_not_block_manual_retry(self):
        v=ui.MapViewer.__new__(ui.MapViewer)
        v._runtime_options=dict(AUTO_SAVE_ENABLED=True,AUTO_SAVE_EVERY_YEARS=100,SAVES_DIR=Path('saves'))
        v.war=SimpleNamespace(year=100);v._save_pending=False;v._closing=False
        v._last_auto_save_year=None;v._save_retry_after=time.perf_counter()+60;v._runtime_submit=mock.Mock()
        v._maybe_auto_save();v._runtime_submit.assert_not_called()
        v._maybe_auto_save(force=True);v._runtime_submit.assert_called_once()
    def test_milestone_capture_runs_after_redraw_and_releases_hold(self):
        v=ui.MapViewer.__new__(ui.MapViewer);events=[]
        v._closing=False;v._snapshot_hold=True;v._displayed_raster_key=(0,'map',1,500)
        v.war=SimpleNamespace(year=500);v._redraw_pending=True
        v._redraw_now=lambda:events.append('draw')
        v._maybe_save_map_snapshot=lambda **kw:events.append('snapshot')
        v._flush_redraw();self.assertEqual(events,['draw','snapshot']);self.assertFalse(v._snapshot_hold)
    def test_no_new_simulation_job_while_milestone_is_being_presented(self):
        v=ui.MapViewer.__new__(ui.MapViewer);v.war=object();v.war_busy=False;v._closing=False;v._snapshot_hold=True
        v._runtime_submit=mock.Mock();v.advance_war(1);v._runtime_submit.assert_not_called()
    def test_wheel_drag_panels_and_close_respond_during_long_batch(self):
        with settings(0):
            v=ui.MapViewer.__new__(ui.MapViewer);root=v.root=MainThreadRoot()
            for name in ('seed_var','width_var','height_var','style_var','layer_var','year_var','status'):
                setattr(v,name,Var(root,'國家與領土' if name=='layer_var' else ''))
            v.war=v.world=v.full_image=None;v.war_busy=False;v.running=False
            v._last_ui_refresh=v._last_map_refresh=0.;v._last_auto_save_year=None;v._last_map_snapshot_year=0
            v._sim_years_completed_window=0;v._map_has_been_fitted=True
            v.zoom=1.;v.center_x=v.center_y=50.;v.drag_start=(0,0,50,50)
            events=[];renders=[]
            def panels():root.check();events.append(('panel',v.war.year))
            def redraw():root.check();events.append(('draw',v.war.year))
            def render(world,layer):renders.append(threading.get_ident());return Image.new('RGB',(128,128))
            v.refresh_panels=panels;v._redraw_now=redraw
            v.fit_world=lambda:setattr(v,'_map_has_been_fitted',True)
            opts=dict(vars(ui),AUTO_SAVE_ENABLED=False,MAP_SNAPSHOT_ENABLED=False,render_environment=render)
            v._init_runtime(opts)
            v._runtime_submit('initialize',world=world(),path='unused-test-state',load_last=False)
            errors=[]
            with mock.patch('responsive_viewer.messagebox.showerror',side_effect=lambda *args:errors.append(args)):
                root.pump(lambda:v.war is not None and not v.war_busy and v.full_image is not None)
                original=WarEngine.step
                def slow(engine,years=1):
                    end=time.perf_counter()+.018
                    while time.perf_counter()<end:pass
                    return original(engine,years)
                clicks=[]
                def interact():
                    if not v.war_busy:return
                    ui.MapViewer.on_wheel(v,SimpleNamespace(delta=120))
                    ui.MapViewer.on_drag(v,SimpleNamespace(x=10,y=15));clicks.append(v.war.year)
                    root.after(5,interact)
                with mock.patch.object(WarEngine,'step',slow):
                    v.advance_war(20);root.after(0,interact)
                    root.pump(lambda:not v.war_busy)
                self.assertGreater(len(clicks),5);self.assertGreater(v.zoom,1.)
                self.assertGreater(sum(kind=='draw' for kind,_ in events),3)
                self.assertEqual(v.war.year,21);self.assertEqual(v._sim_years_completed_window,20)
                self.assertTrue(all(t!=root.main for t in renders));self.assertFalse(errors)
                v._on_close();root.pump(lambda:root.closed)

if __name__=='__main__':unittest.main()
