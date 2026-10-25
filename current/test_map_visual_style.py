import copy,random,unittest
from types import SimpleNamespace
from unittest import mock
import numpy as np
import map_config as cfg
import map_viewer as ui
from map_renderer import render_environment
from cartographic_style import visual_style,VISUAL_STYLE_CODES
from diagnostic_test_support import settings,world,state
from simulation_runtime import capture_view
from war_engine import WarEngine

class Recorder:
    def __init__(self):self.calls=[]
    def __getattr__(self,name):
        if name.startswith('create_'):
            def record(*args,**kw):self.calls.append((name,args,kw))
            return record
        raise AttributeError(name)

class VisualTests(unittest.TestCase):
    def test_two_styles_keep_dimensions_arrays_and_rng_unchanged(self):
        with settings(0):
            w=world();before={k:v.copy() for k,v in vars(w).items() if isinstance(v,np.ndarray)}
            countries=copy.deepcopy(w.countries);py=random.getstate();np_rng=np.random.get_state()
            a=render_environment(w,'國家與領土',visual_style='CLASSIC')
            b=render_environment(w,'國家與領土',visual_style='PARCHMENT')
            self.assertEqual(a.size,b.size);self.assertFalse(np.array_equal(a,b))
            for key,value in before.items():np.testing.assert_array_equal(getattr(w,key),value)
            self.assertEqual(countries,w.countries);self.assertEqual(py,random.getstate())
            after=np.random.get_state();self.assertEqual(np_rng[0],after[0]);np.testing.assert_array_equal(np_rng[1],after[1]);self.assertEqual(np_rng[2:],after[2:])
    def test_generation_is_identical_across_visual_styles(self):
        with settings(0):
            with mock.patch.object(cfg,'MAP_VISUAL_STYLE','CLASSIC'):a=world()
            with mock.patch.object(cfg,'MAP_VISUAL_STYLE','PARCHMENT'):b=world()
            for key,value in vars(a).items():
                if isinstance(value,np.ndarray):np.testing.assert_array_equal(value,getattr(b,key))
            self.assertEqual(a.countries,b.countries)
    def test_paper_texture_is_deterministic_and_analytical_layers_are_unchanged(self):
        with settings(0):
            w=world()
            a=render_environment(w,'國家與領土',visual_style='PARCHMENT')
            b=render_environment(w,'國家與領土',visual_style='PARCHMENT')
            np.testing.assert_array_equal(a,b)
            for layer in ('農業價值','木材價值','礦產價值','淡水供應','建城價值','防禦價值','移動成本','溫度','濕度','降雨'):
                np.testing.assert_array_equal(render_environment(w,layer,visual_style='CLASSIC'),render_environment(w,layer,visual_style='PARCHMENT'))
    def test_invalid_parameter_is_reported(self):
        self.assertEqual(visual_style('原版地形'),'CLASSIC')
        with self.assertRaisesRegex(ValueError,'MAP_VISUAL_STYLE'):visual_style('wrong')
    def test_decorative_frame_does_not_overwrite_capital_marker_at_edge(self):
        with settings(0):
            w=world();w.settlement[2,2]=1
            for style in ('CLASSIC','PARCHMENT'):
                image=np.asarray(render_environment(w,'國家與領土',visual_style=style))
                self.assertEqual(tuple(image[2,2]),(255,209,54))
    def test_all_icon_commands_are_identical_between_styles(self):
        with settings(0):
            e=WarEngine(world());v=ui.MapViewer.__new__(ui.MapViewer);v.war=capture_view(e);v.world=v.war.world
            c=v.war.countries[0];y,x=np.argwhere(v.world.territory==c['id'])[-1]
            c['overseas_capitals']=[dict(anchor=[int(x),int(y)],continent_id=int(v.world.continent[y,x]),type='海外首都')]
            v.show_geographic_names=False;v.zoom=1.;v._runtime_options=dict(vars(ui));v.layer_var=SimpleNamespace(get=lambda:'國家與領土')
            names={c['name'] for c in v.world.countries};results=[]
            for label in ('原版地形','羊皮紙地圖'):
                v.visual_style_var=SimpleNamespace(get=lambda label=label:label);v.canvas=Recorder()
                v._draw_overlays(0,0,128,128,128,128)
                results.append([call for call in v.canvas.calls if not (call[0]=='create_text' and call[2].get('text') in names)])
            self.assertTrue(results[0]);self.assertEqual(results[0],results[1])
            self.assertTrue(any(kind=='create_oval' and kw.get('outline')=='#b7f9ff' for kind,args,kw in results[0]))
    def test_style_requests_have_distinct_keys_and_do_not_edit_global_config(self):
        v=ui.MapViewer.__new__(ui.MapViewer);v.war=SimpleNamespace(visual_revision=1,year=20);v.world=object()
        v._closing=False;v._snapshot_hold=False;v._world_generation=1;v._requested_raster_key=None;v._last_map_refresh=0
        v._runtime_options=dict(VISUAL_STYLE_CODES=VISUAL_STYLE_CODES,MAP_REFRESH_SECONDS=.5)
        v.layer_var=SimpleNamespace(get=lambda:'國家與領土');v._raster=SimpleNamespace(request=mock.Mock(return_value=1))
        before=cfg.MAP_VISUAL_STYLE
        for label in ('原版地形','羊皮紙地圖'):
            v.visual_style_var=SimpleNamespace(get=lambda label=label:label);v._request_raster(force=True)
        selections=[c.args[1] for c in v._raster.request.call_args_list]
        self.assertEqual(selections,[('國家與領土','CLASSIC'),('國家與領土','PARCHMENT')]);self.assertEqual(cfg.MAP_VISUAL_STYLE,before)
    def test_rendering_between_years_does_not_change_simulation_results(self):
        with settings(0):
            base=world();rng=random.getstate();a=WarEngine(copy.deepcopy(base));a.step(50);expected=state(a)
            random.setstate(rng);b=WarEngine(copy.deepcopy(base))
            for _ in range(5):b.step(10);render_environment(b.world,'國家與領土',visual_style='PARCHMENT')
            actual=state(b)
            for key,value in expected.items():
                if isinstance(value,np.ndarray):np.testing.assert_array_equal(value,actual[key])
                else:self.assertEqual(value,actual[key],key)

if __name__=='__main__':unittest.main()
