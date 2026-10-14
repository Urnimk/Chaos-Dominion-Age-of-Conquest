"""依地形、氣候、生態與水文計算每格的可居住性。"""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from climate_rules import DESERT, FOREST, GRASSLAND, LAKE, RIVER, SNOW, SWAMP, TUNDRA
from terrain_rules import BEACH, HIGH_MOUNTAIN, HILL, MOUNTAIN, PLAIN


@dataclass
class HabitabilityLayers:
    agriculture: np.ndarray
    timber: np.ndarray
    minerals: np.ndarray
    freshwater: np.ndarray
    city: np.ndarray
    defense: np.ndarray
    movement_cost: np.ndarray


def _normalize(a):
    a = a.astype(np.float32, copy=False)
    lo, hi = float(a.min()), float(a.max())
    return np.zeros_like(a) if hi - lo < 1e-8 else (a - lo) / (hi - lo)


def _geology_noise(seed, height, width):
    rng = np.random.default_rng(int(seed) ^ 0xA17E2026)
    result = np.zeros((height, width), dtype=np.float32)
    for cells, weight in ((9, 0.50), (27, 0.30), (71, 0.20)):
        cells_x = max(3, int(round(cells * width / max(1, height))))
        source = rng.normal(size=(cells, cells_x)).astype(np.float32)
        layer = ndimage.zoom(source, (height / cells, width / cells_x), order=3, mode="wrap")[:height, :width]
        result += (_normalize(layer) * 2.0 - 1.0) * weight
    return _normalize(result)


def _score(values, land):
    result = np.clip(np.rint(values), 0, 100).astype(np.uint8)
    result[~land] = 0
    return result


def generate_habitability(world, progress=None):
    terrain = world.terrain
    land = terrain >= BEACH
    height, width = terrain.shape

    def report(value, message):
        if progress:
            progress(value, message)

    report(0.955, "計算淡水與地形難度")
    elevation = np.clip((world.height - world.sea_level) / max(1e-6, 1.0 - world.sea_level), 0.0, 1.0)
    gy, gx = np.gradient(elevation)
    slope = np.clip(np.hypot(gx, gy) * min(height, width) * 0.22, 0.0, 1.0)

    fresh_mask = (world.water == LAKE) | (world.water == RIVER)
    if fresh_mask.any():
        fresh_distance = ndimage.distance_transform_edt(~fresh_mask)
        freshwater_raw = 82.0 * np.exp(-fresh_distance / max(5.0, min(height, width) * 0.018))
    else:
        freshwater_raw = np.zeros((height, width), dtype=np.float32)
    freshwater_raw += np.clip(world.rainfall / 3600.0, 0.0, 1.0) * 23.0
    freshwater_raw += (world.biome == SWAMP) * 14.0
    freshwater_raw[fresh_mask] = 100.0
    freshwater = _score(freshwater_raw, land)

    report(0.965, "評估農業、木材與礦產")
    temperature_fit = np.clip(1.0 - np.abs(world.temperature - 19.0) / 24.0, 0.0, 1.0)
    rain_fit = np.clip(1.0 - np.abs(world.rainfall - 1250.0) / 1350.0, 0.0, 1.0)
    terrain_farm = np.select(
        [terrain == PLAIN, terrain == BEACH, terrain == HILL, terrain == MOUNTAIN, terrain == HIGH_MOUNTAIN],
        [1.0, 0.62, 0.52, 0.16, 0.03],
        default=0.0,
    )
    biome_farm = np.select(
        [world.biome == GRASSLAND, world.biome == FOREST, world.biome == SWAMP, world.biome == DESERT, world.biome == TUNDRA, world.biome == SNOW],
        [1.0, 0.70, 0.38, 0.20, 0.12, 0.02],
        default=0.0,
    )
    agriculture_raw = 100.0 * (
        temperature_fit * 0.30
        + rain_fit * 0.22
        + terrain_farm * 0.20
        + biome_farm * 0.18
        + freshwater.astype(np.float32) / 100.0 * 0.10
    ) * (1.0 - slope * 0.62)
    agriculture = _score(agriculture_raw, land & ~fresh_mask)

    biome_wood = np.select(
        [world.biome == FOREST, world.biome == SWAMP, world.biome == GRASSLAND, world.biome == TUNDRA],
        [1.0, 0.66, 0.30, 0.16],
        default=0.03,
    )
    timber_raw = 100.0 * (
        biome_wood * 0.62
        + np.clip(world.humidity, 0.0, 1.0) * 0.17
        + np.clip(world.rainfall / 2200.0, 0.0, 1.0) * 0.13
        + temperature_fit * 0.08
    ) * (1.0 - (terrain == HIGH_MOUNTAIN) * 0.55)
    timber = _score(timber_raw, land & ~fresh_mask)

    plate_edge = np.zeros_like(land, dtype=bool)
    plate_edge[:, 1:] |= world.plate[:, 1:] != world.plate[:, :-1]
    plate_edge[1:, :] |= world.plate[1:, :] != world.plate[:-1, :]
    plate_edge[:, 0] |= world.plate[:, 0] != world.plate[:, -1]
    plate_signal = _normalize(ndimage.gaussian_filter(plate_edge.astype(np.float32), sigma=max(2.0, min(height, width) * 0.006)))
    geology = _geology_noise(world.settings.seed, height, width)
    terrain_mineral = np.select(
        [terrain == HIGH_MOUNTAIN, terrain == MOUNTAIN, terrain == HILL, terrain == PLAIN, terrain == BEACH],
        [1.0, 0.86, 0.58, 0.24, 0.12],
        default=0.0,
    )
    minerals_raw = 100.0 * (terrain_mineral * 0.46 + plate_signal * 0.29 + geology * 0.25)
    minerals = _score(minerals_raw, land & ~fresh_mask)

    report(0.978, "計算防禦、移動與建城價值")
    rough_terrain = np.select(
        [terrain == HIGH_MOUNTAIN, terrain == MOUNTAIN, terrain == HILL, terrain == PLAIN, terrain == BEACH],
        [1.0, 0.82, 0.55, 0.18, 0.08],
        default=0.0,
    )
    coast_distance = ndimage.distance_transform_edt(land)
    coast_defense = np.exp(-coast_distance / max(3.0, min(height, width) * 0.008))
    defense_raw = 100.0 * (elevation * 0.36 + slope * 0.27 + rough_terrain * 0.27 + coast_defense * 0.10)
    defense = _score(defense_raw, land & ~fresh_mask)

    terrain_move = np.select(
        [terrain == BEACH, terrain == PLAIN, terrain == HILL, terrain == MOUNTAIN, terrain == HIGH_MOUNTAIN],
        [1.25, 1.0, 2.2, 4.4, 7.5],
        default=255.0,
    ).astype(np.float32)
    biome_move = np.select(
        [world.biome == GRASSLAND, world.biome == FOREST, world.biome == DESERT, world.biome == TUNDRA, world.biome == SNOW, world.biome == SWAMP],
        [0.0, 1.3, 1.0, 1.4, 3.0, 4.5],
        default=0.0,
    )
    movement_raw = terrain_move + biome_move + slope * 6.0 + (world.water == RIVER) * 1.8
    movement_cost = np.clip(np.rint(movement_raw), 1, 20).astype(np.uint8)
    movement_cost[(~land) | (world.water == LAKE)] = 255

    climate_comfort = np.clip(1.0 - np.abs(world.temperature - 18.0) / 30.0, 0.0, 1.0) * 100.0
    accessibility = np.where(movement_cost == 255, 0.0, np.clip(110.0 - movement_cost.astype(np.float32) * 9.0, 0.0, 100.0))
    flood_risk = ((world.biome == SWAMP) * 22.0 + (world.water == RIVER) * 12.0).astype(np.float32)
    city_raw = (
        agriculture.astype(np.float32) * 0.27
        + freshwater.astype(np.float32) * 0.22
        + timber.astype(np.float32) * 0.07
        + minerals.astype(np.float32) * 0.06
        + defense.astype(np.float32) * 0.10
        + accessibility * 0.19
        + climate_comfort * 0.09
        - flood_risk
    )
    city = _score(city_raw, land & ~fresh_mask & (terrain != HIGH_MOUNTAIN))

    report(0.99, "完成可居住性評分")
    return HabitabilityLayers(agriculture, timber, minerals, freshwater, city, defense, movement_cost)
