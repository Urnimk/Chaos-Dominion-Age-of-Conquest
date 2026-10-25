"""Exact caches for the existing periodic building-spacing and coast rules.
No RNG, candidate reordering, game fields or save-schema changes.
"""
import numpy as np
from scipy import ndimage

def _count(engine,name):
    d=getattr(engine,'diagnostics',None)
    if d is not None and d.enabled_for('performance'):d.count(name)

def coastal_neighbors(engine,sea):
    cache=getattr(engine,'_building_coast_cache',None)
    if cache is not None and np.array_equal(cache[0],sea):
        _count(engine,'building_coast_cache_hits');return cache[1]
    result=ndimage.binary_dilation(sea,iterations=1)
    engine._building_coast_cache=(sea.copy(),result)
    _count(engine,'building_coast_rebuilds');return result

def spacing_allowed(engine,code,spacing_mask,min_gap):
    width=engine.world.settings.width
    cache=getattr(engine,'_building_spacing_cache',None)
    if cache is None:cache=engine._building_spacing_cache={}
    key=(int(code),int(min_gap),spacing_mask.shape,width)
    old=cache.get(key)
    if old is not None and np.array_equal(old[0],spacing_mask):
        _count(engine,'building_spacing_cache_hits');return old[1]
    if old is not None and not np.any(old[0]&~spacing_mask):
        additions=np.argwhere(spacing_mask&~old[0])
        if len(additions)<=64:
            allowed=old[1]
            height=spacing_mask.shape[0]
            # Distance threshold is strict: distance == min_gap is legal.
            for y,x in additions:
                if min_gap<=0:continue
                ys=np.arange(max(0,y-min_gap+1),min(height,y+min_gap))
                if 2*min_gap-1>=width:
                    xs=np.arange(width);dx=np.minimum(abs(xs-x),width-abs(xs-x))
                else:
                    dx=np.arange(-min_gap+1,min_gap);xs=(x+dx)%width
                blocked=(ys[:,None]-y)**2+dx[None,:]**2 < min_gap**2
                idx=np.ix_(ys,xs);allowed[idx]=allowed[idx]&~blocked
            cache[key]=(spacing_mask.copy(),allowed)
            _count(engine,'building_spacing_incremental_updates');return allowed
    padded=np.concatenate((spacing_mask,spacing_mask,spacing_mask),axis=1)
    distance=ndimage.distance_transform_edt(~padded)[:,width:2*width]
    allowed=distance>=min_gap
    # At most one active spacing configuration per building type.
    for stale in list(cache):
        if stale[0]==int(code):cache.pop(stale)
    cache[key]=(spacing_mask.copy(),allowed)
    _count(engine,'building_spacing_full_rebuilds');return allowed
