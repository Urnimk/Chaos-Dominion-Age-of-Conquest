"""Short-lived derived world statistics keyed by the territory revision.

The world arrays remain authoritative. This cache stores only deterministic
summaries that are repeatedly derived from them during a stable territory
revision; it is intentionally excluded from saves.
"""
from __future__ import annotations

import numpy as np
from province_strategy import ProvinceCache


class WorldStateCache:
    def __init__(self, engine):
        self.engine = engine
        self.provinces = ProvinceCache(engine)
        self._landmass_owners: dict[int, tuple[int, np.ndarray, frozenset[int]]] = {}
        self._country_landmasses: dict[int, frozenset[int]] = {}
        self._landmass_stride = int(engine.world.continent.max(initial=0))+1
        self._geographic_indices = {}
        self._values = {}
        self.value_revisions = {}
        self.value_hits = 0
        self.value_misses = 0
        self.value_invalidations = 0
        self.hits = 0
        self.misses = 0

    def invalidate(self, country_ids=(), landmass_ids=None):
        """Invalidate only touched countries/landmasses; None means unknown/global."""
        if landmass_ids is not None:landmass_ids=tuple(landmass_ids)
        self.provinces.invalidate(country_ids,landmass_ids)
        countries=set(map(int,country_ids));landmasses=None if landmass_ids is None else set(map(int,landmass_ids))
        for key in list(self._values):
            _,cid,lm=key
            if landmasses is None or key[0]=='regimes' and lm in landmasses or cid in countries and (lm is None or lm in landmasses):self._values.pop(key,None)
        if landmass_ids is None:
            self._landmass_owners.clear()
            self._country_landmasses.clear()
            return
        for lm in landmass_ids:
            self._landmass_owners.pop(int(lm), None)
        for cid in country_ids:
            self._country_landmasses.pop(int(cid), None)

    def landmass_ownership(self, landmass_id: int):
        """Return (land cells, cells by country, positive owners) for one landmass."""
        lm = int(landmass_id)
        cached = self._landmass_owners.get(lm)
        if cached is not None:
            self.hits += 1
            if len(cached[1])<len(self.engine.countries)+1:
                counts=np.pad(cached[1],(0,len(self.engine.countries)+1-len(cached[1])))
                cached=(cached[0],counts,cached[2]);self._landmass_owners[lm]=cached
            return cached
        self.misses += 1
        indices=self.geographic_indices(lm)
        indices=indices[self.engine.world.terrain.ravel()[indices]>=2]
        owners=self.engine.world.territory.ravel()[indices]
        counts = np.bincount(
            owners.astype(np.int32, copy=False),
            minlength=len(self.engine.countries) + 1,
        )
        stats = (int(owners.size), counts,
                 frozenset(int(cid) for cid in np.flatnonzero(counts[1:]) + 1))
        self._landmass_owners[lm] = stats
        return stats

    def country_landmasses(self, country_id: int) -> frozenset[int]:
        """Return positive landmass IDs currently occupied by a country."""
        cid = int(country_id)
        cached = self._country_landmasses.get(cid)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        territory = self.engine.world.territory
        continent = self.engine.world.continent
        ids = np.unique(continent.ravel()[self.engine._spatial_indices(cid)])
        result = frozenset(int(lm) for lm in ids if int(lm) > 0)
        self._country_landmasses[cid] = result
        return result

    def geographic_indices(self, landmass_id):
        """Immutable row-major geographic index; ownership never rebuilds it."""
        lm=int(landmass_id)
        if lm not in self._geographic_indices:
            indices=np.flatnonzero(self.engine.world.continent==lm)
            indices.flags.writeable=False
            self._geographic_indices[lm]=indices
        return self._geographic_indices[lm]

    def total(self, field, country_id, landmass_id=None):
        """Exact same dtype, row order and numpy reducer as uncached queries."""
        cid=int(country_id);lm=None if landmass_id is None else int(landmass_id)
        key=(field,cid,lm)
        if key in self._values:
            self.value_hits+=1;return self._values[key]
        self.value_misses+=1
        array=getattr(self.engine,{'population':'local_population','soldiers':'local_soldiers','food':'food_yield'}[field])
        result=array.ravel()[self.engine._spatial_indices(cid,lm)].sum()
        value=float(result) if field=='food' else int(result)
        self._values[key]=value
        return value

    def regimes(self, landmass_id):
        # Keep the original exact continent selection, including any lake cells.
        key=('regimes',0,int(landmass_id))
        if key not in self._values:
            idx=self.geographic_indices(landmass_id)
            self._values[key]=tuple(int(v) for v in np.unique(self.engine.world.territory.ravel()[idx]))
        return self._values[key]

    def region(self, country_id, landmass_id):
        """AI's derived regional view. No authoritative state lives in this dict."""
        cid,lm=int(country_id),int(landmass_id)
        neighbors=set()
        for pair,points in self.engine.land_contacts.items():
            if cid in pair and any(int(self.engine.world.continent[y,x])==lm for y,x in points):
                neighbors.update(v for v in pair if v!=cid)
        return dict(country_id=cid,landmass_id=lm,cells=len(self.engine._spatial_indices(cid,lm)),
                    population=self.total('population',cid,lm),soldiers=self.total('soldiers',cid,lm),
                    food_output=self.total('food',cid,lm),regimes=self.regimes(lm),neighbors=tuple(sorted(neighbors)))

    def values_changed(self, field, index=None, flat=False, country_id=None, landmass_id=None):
        """Called immediately after each authoritative array write.

        Scalar writes cost O(1). Bulk writes only invalidate owners/islands at
        the touched coordinates; no numerical totals are recomputed here.
        """
        self.provinces.values_changed(field,index,flat,country_id,landmass_id)
        self.value_revisions[field]=self.value_revisions.get(field,0)+1
        if not self._values:return
        self.value_invalidations+=1
        if country_id is not None:
            cid=int(country_id)
            if landmass_id is None:
                for key in list(self._values):
                    if key[0]==field and key[1]==cid:self._values.pop(key,None)
            else:
                self._values.pop((field,cid,int(landmass_id)),None)
                self._values.pop((field,cid,None),None)
            return
        if index is None:
            self._values={k:v for k,v in self._values.items() if k[0]!=field};return
        territory=self.engine.world.territory;continent=self.engine.world.continent
        if flat:territory=territory.ravel();continent=continent.ravel()
        owners=territory[index];islands=continent[index]
        if np.ndim(owners)==0:
            pairs=((int(owners),int(islands)),)
        else:
            stride=self._landmass_stride
            pairs=((int(k)//stride,int(k)%stride) for k in np.unique(owners.astype(np.int64)*stride+islands))
        for cid,lm in pairs:
            self._values.pop((field,cid,lm),None);self._values.pop((field,cid,None),None)

    def debug_assert_consistent(self):
        """Re-scan populated entries; intended for tests/debug, never yearly release work."""
        t, c, terrain = (self.engine.world.territory,
                         self.engine.world.continent,
                         self.engine.world.terrain)
        for (field,cid,lm),value in self._values.items():
            if field=='regimes':
                assert value==tuple(int(v) for v in np.unique(t[c==lm]));continue
            array=getattr(self.engine,{'population':'local_population','soldiers':'local_soldiers','food':'food_yield'}[field])
            mask=t==cid
            if lm is not None:mask &= c==lm
            expected=array.ravel()[np.flatnonzero(mask)].sum()
            assert value==expected,(field,cid,lm,value,expected)
        for lm, (total, counts, owners) in self._landmass_owners.items():
            land = (c == lm) & (terrain >= 2)
            expected = np.bincount(t[land].ravel().astype(np.int32, copy=False),
                                   minlength=len(self.engine.countries) + 1)
            assert total == int(land.sum())
            np.testing.assert_array_equal(counts, expected)
            assert owners == frozenset(int(cid) for cid in np.flatnonzero(expected[1:]) + 1)
        for cid, landmasses in self._country_landmasses.items():
            expected = frozenset(int(lm) for lm in np.unique(c[t == cid]) if int(lm) > 0)
            assert landmasses == expected


class StrategicSnapshot:
    """Ephemeral per-country decision view; never serialized into a save."""
    __slots__ = ("country_id", "year", "territory_epoch", "values", "memo")

    def __init__(self, country_id, year, territory_epoch, values):
        self.country_id = int(country_id)
        self.year = int(year)
        self.territory_epoch = int(territory_epoch)
        self.values = values
        self.memo = {}

    def get_or_compute(self, key, factory):
        if key not in self.memo:
            self.memo[key] = factory()
        return self.memo[key]


from diagnostic_logger import install_cache
install_cache(WorldStateCache)
