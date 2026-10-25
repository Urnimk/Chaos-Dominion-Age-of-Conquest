import copy,json,random,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import numpy as np
from diagnostic_test_support import settings,world
from war_engine import WarEngine
from province_naming import initialize_names,visible_labels,ProvinceLabel
from simulation_runtime import capture_view
from map_viewer import MapViewer

class ProvinceNameTests(unittest.TestCase):
 def test_names_unique_deterministic_and_anchors_inside_each_province(self):
  with settings(0):
   e=WarEngine(world());before=copy.deepcopy(e.rng.bit_generator.state);py=random.getstate();names=dict(e.province_names)
   initialize_names(e);self.assertEqual(names,e.province_names)
   self.assertEqual(before,e.rng.bit_generator.state);self.assertEqual(py,random.getstate())
   self.assertEqual(len(names),len(set(names.values())))
   for label in e.province_labels:
    self.assertTrue(label.name.endswith('省'));self.assertEqual(e.world_state_cache.provinces.layout.ids[label.y,label.x],label.province_id)
 def test_save_restores_names_and_old_save_generates_them(self):
  with settings(0),tempfile.TemporaryDirectory() as temp:
   e=WarEngine(world());path=Path(temp)/'war.npz';first=e.province_labels[0]
   saved=dict(e.province_names);saved[first.key]='羅森堡省';initialize_names(e,saved);e.save(path)
   loaded=WarEngine.load(copy.deepcopy(e.world),path);self.assertEqual(e.province_names,loaded.province_names)
   self.assertEqual(loaded.province_labels[0].name,'羅森堡省')
   f=path.with_suffix('.json');data=json.loads(f.read_text());data.pop('province_names');f.write_text(json.dumps(data))
   old=WarEngine.load(copy.deepcopy(e.world),path);self.assertEqual(len(old.province_names),len(e.province_names))
 def test_names_survive_ownership_changes_and_snapshot_isolation(self):
  with settings(0):
   e=WarEngine(world());view=capture_view(e);names=dict(e.province_names);labels=e.province_labels
   idx=e.world_state_cache.provinces.layout.indices[1][0];y,x=divmod(int(idx),e.world.terrain.shape[1]);e.world.territory[y,x]=2;e._mark_world_changed(1,2)
   self.assertEqual(names,e.province_names);self.assertIs(view.province_labels,labels)
   e.province_names[labels[0].key]='測試省';self.assertNotEqual(view.province_names,e.province_names)
 def test_screen_culling_avoids_overlap_and_reserved_capital_area(self):
  a=ProvinceLabel(1,'a','羅森堡省',50,50,1000,40,40);b=ProvinceLabel(2,'b','貝爾蒙省',55,50,900,40,40)
  result=visible_labels([a,b],1,0,0,100,100,0,0);self.assertEqual([p.province_id for p,_,_ in result],[1])
  self.assertFalse(visible_labels([a],1,0,0,100,100,0,0,[(30,30,70,70)]))
  self.assertFalse(visible_labels([a],.01,0,0,100,100,0,0))
 def test_label_toggle_preserves_all_other_overlay_commands(self):
  import map_viewer as ui
  from test_map_visual_style import Recorder
  with settings(0):
   e=WarEngine(world());v=MapViewer.__new__(MapViewer);v.war=capture_view(e);v.world=v.war.world
   v.show_geographic_names=False;v.zoom=4.;v._runtime_options=dict(vars(ui))
   v.layer_var=SimpleNamespace(get=lambda:'省區分界');v.visual_style_var=SimpleNamespace(get=lambda:'羊皮紙地圖')
   outputs=[];count=0
   for enabled in (False,True):
    v.show_province_names=enabled;v.canvas=Recorder();v._draw_overlays(0,0,512,512,512,512)
    outputs.append([call for call in v.canvas.calls if call[2].get('tags')!='province_name'])
    count+=sum(call[2].get('tags')=='province_name' for call in v.canvas.calls)
   self.assertGreater(count,0);self.assertEqual(outputs[0],outputs[1])
 def test_button_toggles_only_canvas_redraw(self):
  v=MapViewer.__new__(MapViewer);v.show_province_names=False;v.province_name_button=mock.Mock();v.redraw=mock.Mock()
  v.toggle_province_names();self.assertTrue(v.show_province_names);v.province_name_button.configure.assert_called_with(text='隱藏省名')
  v.toggle_province_names();self.assertFalse(v.show_province_names);v.province_name_button.configure.assert_called_with(text='顯示省名');self.assertEqual(v.redraw.call_count,2)

if __name__=='__main__':unittest.main()
