import unittest
from types import SimpleNamespace
import numpy as np
from country_emblems import draw_emblem, emblem_style, OVERSEAS_FRAME
from map_viewer import MapViewer

class Canvas:
    def __init__(self):self.calls=[]
    def __getattr__(self,name):
        return lambda *args,**kw:self.calls.append((name,args,kw))

class EmblemTests(unittest.TestCase):
    def test_unique_colors_and_stability(self):
        colors=[emblem_style(i)[0] for i in range(1,10001)]
        self.assertEqual(len(colors),len(set(colors)))
        a=emblem_style(17);emblem_style.cache_clear();self.assertEqual(a,emblem_style(17))
    def test_overseas_border_only_and_same_shield(self):
        a,b=Canvas(),Canvas();draw_emblem(a,0,0,24,7);draw_emblem(b,0,0,24,7,True)
        self.assertFalse(any(c[2].get('outline')==OVERSEAS_FRAME for c in a.calls))
        self.assertEqual(b.calls[0][2]['outline'],OVERSEAS_FRAME)
        self.assertEqual(a.calls[0][2]['fill'],b.calls[1][2]['fill'])
    def test_capital_labels_and_live_positions(self):
        v=MapViewer.__new__(MapViewer);v.zoom=1;v.canvas=Canvas()
        land=np.ones((20,20),dtype=int);land[4,4]=2;land[8,8]=3
        territory=np.ones((20,20),dtype=int)
        live=dict(id=1,name='COUNTRY',alive=True,capital=[2,2],overseas_capitals=[
            dict(anchor=[4,4]),dict(anchor=[8,8]),dict(anchor=[8,8])])
        v.world=SimpleNamespace(settings=SimpleNamespace(width=20,height=20),
            territory=territory,continent=land,countries=[dict(id=1,capital=[0,0],name='OLD')])
        v.war=SimpleNamespace(countries=[live],_major_landmass_ids=lambda:{1,3})
        labels=[];v._draw_capital_name=lambda *a:labels.append(a)
        v._draw_capital_emblems(0,0,200,200,0,0)
        self.assertEqual(len(labels),2)
        self.assertEqual({a[0] for a in labels},{2,8})
        frames=[c for c in v.canvas.calls if c[2].get('outline')==OVERSEAS_FRAME]
        self.assertEqual(len(frames),2)
        # Extinct countries draw neither emblems nor labels.
        live['alive']=False;v.canvas=Canvas();labels.clear()
        v._draw_capital_emblems(0,0,200,200,0,0)
        self.assertFalse(v.canvas.calls);self.assertFalse(labels)
    def test_motifs_render_at_zoom_limits(self):
        for cid in range(1,7):
            for size in (18,34):
                c=Canvas();draw_emblem(c,30,30,size,cid,True)
                self.assertGreater(len(c.calls),3)

if __name__=='__main__':unittest.main()
