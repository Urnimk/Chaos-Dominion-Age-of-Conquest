"""Procedural parchment presentation. Never edits the simulation or its RNG."""
from collections import OrderedDict
import threading
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage
import map_config as cfg

VISUAL_STYLE_LABELS={'CLASSIC':'原版地形','PARCHMENT':'羊皮紙地圖'}
VISUAL_STYLE_CODES={label:code for code,label in VISUAL_STYLE_LABELS.items()}
ARTISTIC_LAYERS=frozenset(('國家與領土','純領土歸屬','國家領土','生態環境','基礎地形'))
_cache=OrderedDict();_lock=threading.Lock()

def visual_style(value=None):
    value=getattr(cfg,'MAP_VISUAL_STYLE','CLASSIC') if value is None else value
    value=VISUAL_STYLE_CODES.get(value,str(value).upper())
    if value not in VISUAL_STYLE_LABELS:raise ValueError('MAP_VISUAL_STYLE 必須是 CLASSIC 或 PARCHMENT')
    return value

def is_parchment(layer,style=None):
    return visual_style(style)=='PARCHMENT' and layer in ARTISTIC_LAYERS

def _prepare(world):
    # Hold static arrays in cached values so Python cannot recycle their IDs.
    refs=(world.terrain,world.height,world.water)
    h,w=world.terrain.shape;grain=float(np.clip(getattr(cfg,'MAP_PARCHMENT_GRAIN',1.),0.,2.))
    key=tuple(id(v) for v in refs)+(int(world.settings.seed),h,w,grain)
    with _lock:
        entry=_cache.get(key)
        if entry is not None:_cache.move_to_end(key);return entry[1]
    rng=np.random.default_rng((int(world.settings.seed)^0x50415243484D454E)&((1<<64)-1))
    def noise(scale):
        a=rng.uniform(-1.,1.,(max(2,h//scale),max(2,w//scale))).astype(np.float32)
        return np.asarray(Image.fromarray(a).resize((w,h),resample=2))
    texture=(noise(100)*10.+noise(24)*5.+rng.uniform(-1.,1.,(h,w)).astype(np.float32)*3.0)*grain
    paper=np.clip(np.array([232.,215.,170.],dtype=np.float32)+texture[...,None],0,255)
    land=world.terrain>=2
    coast=land & ~ndimage.binary_erosion(land,structure=ndimage.generate_binary_structure(2,1),border_value=1)
    coastal_water=ndimage.binary_dilation(land,iterations=2)&~land
    gy,gx=np.gradient(world.height.astype(np.float32))
    relief=np.clip(1.+(-gx*.50-gy*.65)*min(h,w)*.025,.96,1.025)
    # Mountain marks follow real mountain cells; no decorative/fake provinces.
    ink=Image.new('L',(w,h));draw=ImageDraw.Draw(ink)
    spacing=max(12,round(min(h,w)/75));radius=max(2,min(5,spacing//4))
    for y in range(spacing//2,h-radius,spacing):
        for x in range(spacing//2,w-radius,spacing):
            xx=x+int(rng.integers(-2,3));yy=y+int(rng.integers(-2,3))
            patch=land[max(0,yy-radius):yy+radius+1,max(0,xx-radius):xx+radius+1]
            if world.terrain[yy,xx]>=5 and patch.all():
                draw.line((xx-radius,yy+radius,xx,yy-radius,xx+radius,yy+radius),fill=140,width=1)
                draw.line((xx,yy-radius,xx-1,yy+1),fill=70,width=1)
    prepared=dict(paper=paper,texture=texture,land=land,coast=coast,coastal_water=coastal_water,
                  relief=relief,mountains=np.asarray(ink,dtype=np.float32)/255.)
    with _lock:
        _cache[key]=(refs,prepared);_cache.move_to_end(key)
        while len(_cache)>2:_cache.popitem(last=False)
    return prepared

def render_parchment(world,layer):
    p=_prepare(world);land=p['land'];h,w=land.shape;rgb=p['paper'].copy()
    ground=rgb*np.array([.91,.94,.83],dtype=np.float32)
    political=layer in ('國家與領土','純領土歸屬','國家領土')
    if political:
        maximum=max(int(world.territory.max(initial=0)),max((int(c['id']) for c in world.countries),default=0))
        palette=np.empty((maximum+1,3),dtype=np.float32);palette[:]=[204.,197.,151.]
        for c in world.countries:
            color=np.asarray(c['color'],dtype=np.float32)
            luminance=float(color @ np.array([.299,.587,.114],dtype=np.float32))
            color=color*.75+luminance*.25
            palette[int(c['id'])]=color*.66+np.array([224.,202.,150.],dtype=np.float32)*.34
        owned=land&(world.territory>0)
        ground[owned]=palette[world.territory[owned]]+p['texture'][owned,None]*.45
    else:
        # Actual elevation remains readable beneath the hand-drawn mountains.
        tint=np.array([[232,215,170],[232,215,170],[225,207,158],[191,197,145],
                       [173,177,125],[174,160,125],[201,190,160]],dtype=np.float32)
        ground[land]=tint[world.terrain[land]]+p['texture'][land,None]*.5
    ground*=p['relief'][...,None];rgb[land]=ground[land]
    rgb[p['coastal_water']]=rgb[p['coastal_water']]*.87+np.array([126.,112.,80.],dtype=np.float32)*.13
    if bool(getattr(cfg,'MAP_PARCHMENT_GRID',True)):
        # A low-opacity graticule, not a new logical region/collision map.
        ink=np.array([105.,113.,92.],dtype=np.float32)
        rgb[:,::max(24,w//12)]=rgb[:,::max(24,w//12)]*.82+ink*.18
        rgb[::max(24,h//8),:]=rgb[::max(24,h//8),:]*.82+ink*.18
    mountains=p['mountains'][...,None]*.72
    rgb=rgb*(1.-mountains)+np.array([65.,60.,41.],dtype=np.float32)*mountains
    rgb[world.water==1]=[94.,139.,132.]  # LAKE
    rgb[world.water==2]=[75.,139.,132.]  # RIVER
    borders=(world.border>0)&land if political else np.zeros_like(land)
    rgb[borders]=[91.,83.,54.];rgb[p['coast']]=[69.,71.,48.]
    rgb[world.roads>0]=[134.,107.,64.]
    # Decorative frame stays below original markers, even at the map edge.
    for inset,color in ((2,(94,78,44)),(5,(139,119,75))):
        if min(h,w)>20:
            rgb[inset,inset:w-inset]=color;rgb[h-1-inset,inset:w-inset]=color
            rgb[inset:h-inset,inset]=color;rgb[inset:h-inset,w-1-inset]=color
    # Retain the original building raster marks, in their original order/colors.
    if political:
        for code,iterations,color in ((2,2,(244,241,222)),(3,2,(61,220,235)),(4,2,(220,72,64)),(1,3,(255,209,54))):
            rgb[ndimage.binary_dilation(world.settlement==code,iterations=iterations)]=color
    return Image.fromarray(np.clip(rgb,0,255).astype(np.uint8))
