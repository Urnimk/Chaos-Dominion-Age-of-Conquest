"""Connected, immutable planning districts; fine cells remain authoritative.

No RNG, province ownership, armies or serialized province state is introduced.
Irregular terrain-weighted provinces are clipped to islands and connected land. Frontiers are
queried from defender indices, never by constructing two full-world masks.
"""
from __future__ import annotations
from dataclasses import dataclass
from types import MappingProxyType
import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from PIL import Image
import map_config as cfg


@dataclass(frozen=True)
class ProvinceLayout:
    ids: np.ndarray
    indices: tuple
    islands: tuple
    neighbors: tuple
    boundary: np.ndarray

    @classmethod
    def build(cls, world, side):
        terrain, continent = world.terrain, world.continent
        h, w = terrain.shape
        side=max(4,int(side))
        ids,islands=_irregular_ids(world,side)
        # One stable grouping pass; per-province queries need no full-map scan.
        flat=ids.ravel();order=np.argsort(flat,kind='stable')
        counts=np.bincount(flat,minlength=len(islands));cuts=np.cumsum(counts)
        indices=[np.empty(0,dtype=np.int64)]
        for pid in range(1,len(islands)):
            item=order[cuts[pid-1]:cuts[pid]].copy();item.flags.writeable=False;indices.append(item)
        adjacent=[set() for _ in islands];boundary=np.zeros_like(ids,dtype=bool)
        for axis in (0,1):
            other=np.roll(ids,-1,axis=axis)
            mask=(ids>0)&(other>0)&(ids!=other)
            if axis==0:mask[-1]=False
            boundary |= mask
            pairs=np.unique(np.column_stack((ids[mask],other[mask])),axis=0)
            for a,b in pairs:
                if islands[a]==islands[b]:adjacent[a].add(int(b));adjacent[b].add(int(a))
        # Mark one side of each seam, excluding sea and all building cells when rendered.
        ids.flags.writeable=False;boundary.flags.writeable=False;indices[0].flags.writeable=False
        return cls(ids,tuple(indices),tuple(islands),tuple(tuple(sorted(v)) for v in adjacent),boundary)


def _irregular_ids(world,side):
    """Multi-source shortest-path growth; all scratch graph data dies after build."""
    terrain,continent=world.terrain,world.continent
    h,w=terrain.shape;land=terrain>=2;flat=np.flatnonzero(land);n=len(flat)
    ids=np.zeros((h,w),np.int32)
    if not n:return ids,[0]
    nodes=np.full((h,w),-1,np.int32);nodes.ravel()[flat]=np.arange(n,dtype=np.int32)
    seed=int(world.settings.seed)
    rng=np.random.default_rng(np.random.SeedSequence([seed,2601,side]))
    # Low-frequency local noise bends boundaries; no game/global RNG is touched.
    noise=rng.random((max(3,h//side+2),max(3,w//side+2))).astype(np.float32)
    noise=np.asarray(Image.fromarray(noise).resize((w,h),resample=2),dtype=np.float32)
    roughness=max(0.,float(getattr(cfg,'PROVINCE_BOUNDARY_ROUGHNESS',1.0)))
    terrain_weight=max(0.,float(getattr(cfg,'PROVINCE_TERRAIN_INFLUENCE',1.0)))
    resistance=.8+noise*(1.4*roughness)+(terrain>=5)*(.35*terrain_weight)
    height=np.asarray(world.height,dtype=np.float32)
    river=np.asarray(world.water)==2
    rows=[];cols=[];weights=[]
    yy,xx=np.indices((h,w))
    for dy,dx,length in ((0,1,1.),(1,0,1.),(1,1,2**.5),(1,-1,2**.5)):
        ny=yy+dy;nx=(xx+dx)%w
        valid=land & (ny<h)
        # The clipped index is used only for gathering; valid excludes bottom wrap.
        cy=np.minimum(ny,h-1)
        valid &= land[cy,nx] & (continent==continent[cy,nx])
        if dy and dx:
            # No diagonal path through sea, or through a different island.
            valid &= land[cy,xx]&land[yy,nx]&(continent==continent[cy,xx])&(continent==continent[yy,nx])
        y,x=np.where(valid);ty=y+dy;tx=(x+dx)%w
        a=nodes[y,x];b=nodes[ty,tx]
        cost=length*(resistance[y,x]+resistance[ty,tx])*.5
        cost += np.abs(height[y,x]-height[ty,tx])*(side*2.*terrain_weight)
        cost += (river[y,x]!=river[ty,tx])*(.6*terrain_weight)
        rows.extend((a,b));cols.extend((b,a));weights.extend((cost,cost))
    if rows:
        graph=coo_matrix((np.concatenate(weights),(np.concatenate(rows),np.concatenate(cols))),shape=(n,n)).tocsr()
    else:graph=coo_matrix((n,n)).tocsr()
    del rows,cols,weights,yy,xx,nodes,noise,resistance
    count,components=connected_components(graph,directed=False)
    ordered=np.argsort(components,kind='stable');sizes=np.bincount(components,minlength=count);cuts=np.cumsum(sizes)
    sources=[]
    for component in range(count):
        group=ordered[0 if component==0 else cuts[component-1]:cuts[component]]
        desired=max(1,int(round(len(group)/float(side*side))))
        candidates=rng.choice(group,size=min(len(group),max(1,desired*20)),replace=False)
        points=flat[candidates];ys,xs=np.divmod(points,w)
        # Farthest-point spreading with random priority gives non-grid province centers.
        priority=rng.uniform(.75,1.25,len(points));distance=np.full(len(points),np.inf)
        chosen=int(rng.integers(len(points)))
        for _ in range(desired):
            sources.append(int(candidates[chosen]))
            dx=np.abs(xs-xs[chosen]);dx=np.minimum(dx,w-dx)
            distance=np.minimum(distance,(ys-ys[chosen])**2+dx**2)
            distance[chosen]=-np.inf
            chosen=int(np.argmax(distance*priority))
    sources=np.asarray(sources,dtype=np.int32)
    _,_,nearest=dijkstra(graph,directed=True,indices=sources,min_only=True,return_predecessors=True)
    assert np.all(nearest>=0),'unseeded land component'
    lookup=np.zeros(n,np.int32);lookup[sources]=np.arange(1,len(sources)+1,dtype=np.int32)
    ids.ravel()[flat]=lookup[nearest]
    del graph,nearest,lookup,components,ordered
    # Split diagonal/cross-seam fragments so each actual province is four-connected
    # in the displayed map. Provinces on opposite edges still retain adjacency.
    connected=np.zeros_like(ids);islands=[0]
    for pid,box in enumerate(ndimage.find_objects(ids),1):
        if box is None:continue
        labels,parts=ndimage.label(ids[box]==pid)
        patch=connected[box]
        for part in range(1,parts+1):
            mask=labels==part;y,x=np.argwhere(mask)[0]
            islands.append(int(continent[box[0].start+y,box[1].start+x]))
            patch[mask]=len(islands)-1
    ids=connected
    # Small clipped fragments join an adjacent province on the same island.
    # Whole small islands have no eligible neighbor and remain single provinces.
    ordered=np.argsort(ids.ravel(),kind='stable');sizes=np.bincount(ids.ravel(),minlength=len(islands));cuts=np.cumsum(sizes)
    groups={pid:ordered[cuts[pid-1]:cuts[pid]].copy() for pid in range(1,len(islands))}
    minimum=max(2,int(side*side*.06))
    for pid in sorted(groups,key=lambda pid:(sizes[pid],pid)):
        if not 0<sizes[pid]<minimum:continue
        points=groups[pid];ys,xs=np.divmod(points,w);neighbors=[]
        for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
            ny,nx=ys+dy,xs+dx;valid=(ny>=0)&(ny<h)&(nx>=0)&(nx<w)
            neighbors.extend(ids[ny[valid],nx[valid]].tolist())
        values,counts=np.unique(neighbors,return_counts=True)
        targets=[(int(amount),int(other)) for other,amount in zip(values,counts)
                 if other>0 and other!=pid and islands[int(other)]==islands[pid]]
        if not targets:continue
        _,other=max(targets)
        ids.ravel()[points]=other;groups[other]=np.concatenate((groups[other],points));groups[pid]=np.empty(0,int)
        sizes[other]+=sizes[pid];sizes[pid]=0
    active=np.flatnonzero(sizes[1:])+1;remap=np.zeros(len(islands),np.int32);remap[active]=np.arange(1,len(active)+1)
    return remap[ids],[0]+[islands[int(pid)] for pid in active]


def layout_for(world):
    side=max(4,int(getattr(cfg,'PROVINCE_SIDE_CELLS',32)))
    key=(id(world.terrain),id(world.continent),id(world.height),id(world.water),side,
         int(world.settings.seed),float(getattr(cfg,'PROVINCE_BOUNDARY_ROUGHNESS',1.0)),
         float(getattr(cfg,'PROVINCE_TERRAIN_INFLUENCE',1.0)))
    cached=getattr(world,'_province_layout',None)
    if cached is None or getattr(world,'_province_layout_key',None)!=key:
        cached=ProvinceLayout.build(world,side)
        world._province_layout=cached;world._province_layout_key=key
    return cached


class ProvinceCache:
    def __init__(self,engine):
        self.engine=engine
        self._layout=None
        self._values={};self._fronts={}
        self.hits=0;self.misses=0;self.frontier_hits=0;self.frontier_misses=0
        self.last_choice={}

    @property
    def layout(self):
        if self._layout is None:self._layout=layout_for(self.engine.world)
        return self._layout

    def invalidate(self,country_ids=(),landmass_ids=None):
        if landmass_ids is None:
            self._values.clear();self._fronts.clear();return
        islands=set(map(int,landmass_ids))
        if self._layout is not None:
            self._values={k:v for k,v in self._values.items() if self._layout.islands[k[0]] not in islands}
        self._fronts={k:v for k,v in self._fronts.items() if k[2] is not None and k[2] not in islands}

    def values_changed(self,field,index=None,flat=False,country_id=None,landmass_id=None):
        if not self._values:return
        if country_id is not None:
            self._values={k:v for k,v in self._values.items()
                          if not (k[1]==field and int(country_id) in v and
                                  (landmass_id is None or self.layout.islands[k[0]]==int(landmass_id)))}
            return
        if index is None:
            self._values={k:v for k,v in self._values.items() if k[1]!=field};return
        ids=self.layout.ids.ravel() if flat else self.layout.ids
        touched=np.unique(ids[index])
        for pid in touched:self._values.pop((int(pid),field),None)

    def totals(self,pid,field):
        key=(int(pid),field)
        if key in self._values:self.hits+=1;return self._values[key]
        self.misses+=1;idx=self.layout.indices[int(pid)]
        owners=self.engine.world.territory.ravel()[idx]
        array=getattr(self.engine,{'population':'local_population','soldiers':'local_soldiers','food':'food_yield'}[field]).ravel()
        # Preserve integer exactness, no float weighted bincount for population.
        values={int(cid):float(array[idx[owners==cid]].sum()) if field=='food'
                else int(array[idx[owners==cid]].sum()) for cid in np.unique(owners)}
        value=MappingProxyType(values);self._values[key]=value;return value

    def summary(self,pid):
        idx=self.layout.indices[int(pid)];e=self.engine
        # Buildings queried live within this bounded district; no global scans
        # and no stale values when a building changes without territory changing.
        return dict(province_id=int(pid),landmass_id=self.layout.islands[int(pid)],cells=len(idx),
                    neighbors=self.layout.neighbors[int(pid)],
                    population=dict(self.totals(pid,'population')),soldiers=dict(self.totals(pid,'soldiers')),
                    food_output=dict(self.totals(pid,'food')),
                    owners=tuple(map(int,np.unique(e.world.territory.ravel()[idx]))),
                    buildings=int(np.count_nonzero(e.world.settlement.ravel()[idx])))

    def frontier(self,attacker,defender,lm=None):
        key=(int(attacker),int(defender),None if lm is None else int(lm))
        if key in self._fronts:self.frontier_hits+=1;return self._fronts[key]
        self.frontier_misses+=1;e=self.engine;t=e.world.territory.ravel();h,w=e.world.territory.shape
        idx=e._spatial_indices(defender,lm)
        ys,xs=np.divmod(idx,w)
        left=ys*w+(xs-1)%w;right=ys*w+(xs+1)%w
        hit=(t[left]==attacker)|(t[right]==attacker)
        up=ys>0;down=ys<h-1
        hit[up] |= t[idx[up]-w]==attacker
        hit[down] |= t[idx[down]+w]==attacker
        cells=idx[hit];pids=self.layout.ids.ravel()[cells]
        result={int(pid):cells[pids==pid] for pid in np.unique(pids) if pid>0}
        for points in result.values():points.flags.writeable=False
        if len(self._fronts)>=128:self._fronts.pop(next(iter(self._fronts)))
        self._fronts[key]=result;return result

    def select_front(self,attacker,defender,lm,tactic):
        """Choose districts first, then let the original tactical cell scorer act."""
        groups=self.frontier(attacker,defender,lm)
        if not groups:return np.empty((0,2),dtype=int)
        e=self.engine;h,w=e.world.territory.shape
        target=e.country(defender)['capital']
        if tactic=='RECOVER_PORT' and lm is not None:
            site=e._site(e.country(attacker),lm)
            target=(site or {}).get('logistics_port') or target
        ranked=[]
        for pid,points in groups.items():
            vicinity=(pid,)+self.layout.neighbors[pid]
            enemy=sum(self.totals(p,'soldiers').get(int(defender),0) for p in vicinity)
            own=sum(self.totals(p,'soldiers').get(int(attacker),0) for p in vicinity)
            ys,xs=np.divmod(points,w)
            dx=np.abs(xs-int(target[0]));dx=np.minimum(dx,w-dx)
            distance=float(np.min(np.hypot(ys-int(target[1]),dx)))
            value=float(np.mean(e.world.city_value.ravel()[points]))/100.
            pressure=np.log1p(enemy/max(200,own))
            score=float(getattr(cfg,'PROVINCE_PRESSURE_WEIGHT',1.0))*pressure
            score-=float(getattr(cfg,'PROVINCE_VALUE_WEIGHT',.15))*value
            if tactic in ('ENCIRCLE_CAPITAL','RECOVER_PORT'):
                score+=float(getattr(cfg,'PROVINCE_DISTANCE_WEIGHT',.5))*distance/max(1,int(getattr(cfg,'PROVINCE_SIDE_CELLS',32)))
            ranked.append((score,pid))
        count=max(1,int(getattr(cfg,'PROVINCE_FRONT_CANDIDATES',3)))
        chosen=[pid for _,pid in sorted(ranked)[:count]]
        points=np.sort(np.concatenate([groups[pid] for pid in chosen]))
        # Bounded telemetry: latest choice per attacker, never an ever-growing log.
        self.last_choice[int(attacker)]=dict(year=int(e.year),defender=int(defender),landmass_id=lm,
            evaluated_provinces=len(groups),selected_provinces=chosen,candidate_cells=len(points))
        d=getattr(e,'diagnostics',None)
        if d is not None and d.enabled_for('ai'):
            decision=getattr(d,'current',None)
            if decision is not None and decision.get('country_id')==int(attacker):
                decision['province_selection']={**self.last_choice[int(attacker)],
                    'tactic':tactic,'ranked_provinces':[{'province_id':pid,'score':score} for score,pid in sorted(ranked)],
                    'selection_rule':'lowest province pressure/value/tactical-distance score; original cell tactics within selected districts'}
        if d is not None and d.enabled_for('performance'):

            d.count('province_front_selections');d.count('province_front_candidates',len(groups))
        return np.column_stack(np.divmod(points,w))
