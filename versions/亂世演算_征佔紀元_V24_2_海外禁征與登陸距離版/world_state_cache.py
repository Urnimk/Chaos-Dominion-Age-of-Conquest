"""Short-lived derived world statistics keyed by the territory revision.

The world arrays remain authoritative. This cache stores only deterministic
summaries that are repeatedly derived from them during a stable territory
revision; it is intentionally excluded from saves.
"""
from __future__ import annotations

import numpy as np


class WorldStateCache:
    def __init__(self, engine):
        self.engine = engine
        self._landmass_owners: dict[int, tuple[int, np.ndarray, frozenset[int]]] = {}
        self._country_landmasses: dict[int, frozenset[int]] = {}
        self.hits = 0
        self.misses = 0

    def invalidate(self, country_ids=(), landmass_ids=None):
        """Invalidate only touched countries/landmasses; None means unknown/global."""
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
            return cached
        self.misses += 1
        land = ((self.engine.world.continent == lm)
                & (self.engine.world.terrain >= 2))
        owners = self.engine.world.territory[land].ravel()
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
        ids = np.unique(continent[territory == cid])
        result = frozenset(int(lm) for lm in ids if int(lm) > 0)
        self._country_landmasses[cid] = result
        return result

    def debug_assert_consistent(self):
        """Re-scan populated entries; intended for tests/debug, never yearly release work."""
        t, c, terrain = (self.engine.world.territory,
                         self.engine.world.continent,
                         self.engine.world.terrain)
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
