"""Stable European-style provincial names and immutable map-label metadata."""
from dataclasses import dataclass
import hashlib
import numpy as np
from scipy import ndimage

PREFIX=('艾爾','阿爾','奧斯','貝爾','布蘭','布雷','卡爾','達爾','德爾','埃森','法爾','費爾','格蘭','格雷','哈爾','赫爾','霍恩','伊森','凱爾','克倫','蘭登','雷文','里昂','洛森','盧恩','梅爾','蒙特','諾爾','奧爾','普雷','羅森','薩爾','塞爾','斯托','泰爾','托倫','瓦爾','韋斯','溫德','澤爾')
CORE=('登','倫','德','蒙','維','斯','克','納','瓦','洛','森','特','里','恩','芬','頓','雷','格','諾','文')
ENDING=('堡','海姆','福特','布魯克','貝格','維克','多夫','里亞','尼亞','圖爾','蘭','沃德','斯坦','菲爾德','霍芬','斯特')

@dataclass(frozen=True)
class ProvinceLabel:
    province_id:int
    key:str
    name:str
    x:int
    y:int
    size:int
    width:int
    height:int


def initialize_names(engine,saved=None):
    layout=engine.world_state_cache.provinces.layout
    world=engine.world;w=world.terrain.shape[1]
    saved=saved if isinstance(saved,dict) else {}
    prepared=[]
    for pid,idx in enumerate(layout.indices[1:],1):
        key=hashlib.blake2b(np.asarray(idx,dtype='<i8').tobytes(),digest_size=12,
            person=b'province-key').hexdigest()
        prepared.append((pid,idx,key))
    current={key:str(saved[key]).strip() for _,_,key in prepared
             if isinstance(saved.get(key),str) and 0<len(saved[key].strip())<=40}
    used=set(current.values());labels=[]
    for pid,idx,key in prepared:
        name=current.get(key)
        if name is None:
            attempt=0
            while True:
                digest=hashlib.blake2b(f'{world.settings.seed}:{key}:{attempt}'.encode(),digest_size=12).digest()
                n=int.from_bytes(digest,'big');name=PREFIX[n%len(PREFIX)];n//=len(PREFIX)
                name+=CORE[n%len(CORE)];n//=len(CORE)
                name+=ENDING[n%len(ENDING)]+'省'
                if name not in used:break
                attempt+=1
            current[key]=name;used.add(name)
        ys,xs=np.divmod(idx,w);x0,x1=int(xs.min()),int(xs.max());y0,y1=int(ys.min()),int(ys.max())
        mask=np.zeros((y1-y0+3,x1-x0+3),bool);mask[ys-y0+1,xs-x0+1]=True
        distance=ndimage.distance_transform_edt(mask)
        # Deepest interior point is guaranteed to be inside this province.
        best=int(np.argmax(distance[ys-y0+1,xs-x0+1]));x,y=int(xs[best]),int(ys[best])
        labels.append(ProvinceLabel(pid,key,name,x,y,len(idx),x1-x0+1,y1-y0+1))
    engine.province_names=current
    engine.province_labels=tuple(labels)


def visible_labels(labels,zoom,left,top,cw,ch,ox,oy,reserved=(),limit=80):
    """Cull offscreen/tiny labels and screen-space collisions; no Tk rebuild."""
    occupied=list(reserved);result=[]
    for label in sorted(labels,key=lambda p:(-p.size,p.province_id)):
        sx,sy=ox+(label.x-left)*zoom,oy+(label.y-top)*zoom
        if not (0<=sx<=cw and 0<=sy<=ch):continue
        if label.size*zoom*zoom<100 or max(label.width,label.height)*zoom<16:continue
        half=max(18,len(label.name)*7.0);box=(sx-half-3,sy-9,sx+half+3,sy+9)
        if any(box[0]<b[2] and box[2]>b[0] and box[1]<b[3] and box[3]>b[1] for b in occupied):continue
        result.append((label,sx,sy));occupied.append(box)
        if len(result)>=limit:break
    return result
