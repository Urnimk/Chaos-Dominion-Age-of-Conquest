"""Deterministic native Canvas heraldry. No files, fonts, RNG or save migration needed."""
import math
from functools import lru_cache

OVERSEAS_FRAME = '#00cfff'

@lru_cache(maxsize=4096)
def emblem_style(country_id):
    cid = int(country_id)
    # Bijective base-160 RGB palette for the first 4,096,000 positive IDs.
    n = ((cid - 1) * 1731047 + 231017) % (160 ** 3)
    rgb = (80 + n // 25600, 80 + (n // 160) % 160, 80 + n % 160)
    color = '#%02x%02x%02x' % rgb
    return color, cid % 6


def draw_emblem(canvas, x, y, size, country_id, overseas=False):
    color, motif = emblem_style(country_id)
    r = size / 2
    def shield(scale):
        a = r * scale
        return [x-a*.83,y-a, x+a*.83,y-a, x+a*.8,y+a*.3,
                x,y+a, x-a*.8,y+a*.3]
    tags = ('country_emblem', 'country_emblem_%s' % country_id,
            'overseas_capital' if overseas else 'home_capital')
    if overseas:
        canvas.create_polygon(*shield(1.30), fill='#072435', outline=OVERSEAS_FRAME,
                              width=3, tags=tags)
    canvas.create_polygon(*shield(1), fill=color, outline='#f9e5b2', width=1.5, tags=tags)
    # Contrasting upper field creates a coat of arms rather than a plain map dot.
    canvas.create_polygon(x-r*.78,y-r*.9, x+r*.78,y-r*.9,
                          x+r*.77,y-r*.48, x-r*.77,y-r*.48,
                          fill='#1c2539', outline='', tags=tags)
    fg = '#fff4cf'; a=r*.43; cy=y+r*.02
    if motif == 0:  # sun
        canvas.create_oval(x-a*.65,cy-a*.65,x+a*.65,cy+a*.65,fill=fg,outline='',tags=tags)
        for i in range(8):
            t=i*math.pi/4
            canvas.create_line(x+math.cos(t)*a*.8,cy+math.sin(t)*a*.8,
                               x+math.cos(t)*a*1.15,cy+math.sin(t)*a*1.15,
                               fill=fg,width=1.5,tags=tags)
    elif motif == 1:  # diamond
        canvas.create_polygon(x,cy-a,x+a,cy,x,cy+a,x-a,cy,fill=fg,outline='',tags=tags)
    elif motif == 2:  # cross
        canvas.create_line(x-a,cy,x+a,cy,fill=fg,width=max(2,r*.25),tags=tags)
        canvas.create_line(x,cy-a,x,cy+a,fill=fg,width=max(2,r*.25),tags=tags)
    elif motif == 3:  # chevrons
        for dy in (-a*.35,a*.4):
            canvas.create_line(x-a,cy+dy+a*.3,x,cy+dy-a*.4,x+a,cy+dy+a*.3,
                               fill=fg,width=2,tags=tags)
    elif motif == 4:  # star, vector shape (no glyph dependency)
        points=[]
        for i in range(10):
            t=-math.pi/2+i*math.pi/5;rr=a if i%2==0 else a*.43
            points.extend((x+math.cos(t)*rr,cy+math.sin(t)*rr))
        canvas.create_polygon(*points,fill=fg,outline='',tags=tags)
    else:  # three pearls
        for dx,dy in ((-a*.5,-a*.3),(a*.5,-a*.3),(0,a*.55)):
            b=a*.3
            canvas.create_oval(x+dx-b,cy+dy-b,x+dx+b,cy+dy+b,fill=fg,outline='',tags=tags)
