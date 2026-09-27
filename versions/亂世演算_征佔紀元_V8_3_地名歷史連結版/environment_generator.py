"""由地形推導氣候、生態區、湖泊與河流。"""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

import map_config as cfg
from climate_rules import DESERT, FOREST, GRASSLAND, LAKE, OCEAN, RIVER, SNOW, SWAMP, TUNDRA


@dataclass
class EnvironmentLayers:
    temperature: np.ndarray
    humidity: np.ndarray
    rainfall: np.ndarray
    biome: np.ndarray
    water: np.ndarray


def _normalize(a):
    a = a.astype(np.float32, copy=False)
    lo, hi = float(a.min()), float(a.max())
    return np.zeros_like(a) if hi - lo < 1e-7 else (a - lo) / (hi - lo)


def _noise(rng, height, width, scales=(6, 15, 39, 91)):
    result = np.zeros((height, width), dtype=np.float32)
    total = 0.0
    for cells, weight in zip(scales, (0.48, 0.28, 0.16, 0.08)):
        cells_x = max(3, int(round(cells * width / max(1, height))))
        source = rng.normal(size=(cells, cells_x)).astype(np.float32)
        layer = ndimage.zoom(source, (height / cells, width / cells_x), order=3, mode="wrap")[:height, :width]
        result += (_normalize(layer) * 2.0 - 1.0) * weight
        total += weight
    return result / total


def _make_lakes(rng, land, elevation, rainfall):
    height, width = land.shape
    inland = ndimage.distance_transform_edt(land)
    local_low = elevation <= ndimage.minimum_filter(elevation, size=max(9, min(height, width) // 90), mode="nearest") + 0.022
    candidates = np.argwhere(land & local_low & (rainfall > 1050.0) & (inland > max(5, min(height, width) * 0.012)))
    lake = np.zeros_like(land, dtype=bool)
    if not len(candidates):
        return lake
    rng.shuffle(candidates)
    target = max(4, int(cfg.LAKE_COUNT * (height * width) / (2000 * 2000)))
    centers = []
    min_gap2 = (min(height, width) * 0.035) ** 2
    yy_full, xx_full = np.ogrid[:height, :width]
    for y, x in candidates:
        if len(centers) >= target:
            break
        if any((y - py) ** 2 + min(abs(x - px), width - abs(x - px)) ** 2 < min_gap2 for py, px in centers):
            continue
        centers.append((int(y), int(x)))
        ry = max(2, int(min(height, width) * rng.uniform(0.0025, 0.0065)))
        rx = max(2, int(ry * rng.uniform(0.75, 1.65)))
        dy = (yy_full - y) / ry
        dx = np.minimum(np.abs(xx_full - x), width - np.abs(xx_full - x)) / rx
        blob = (dx * dx + dy * dy) <= 1.0
        lake |= (
            blob
            & land
            & (elevation <= elevation[y, x] + rng.uniform(0.018, 0.042))
            & (rainfall >= rainfall[y, x] * rng.uniform(0.72, 0.90))
        )
    return lake


def _make_rivers(rng, land, lake, elevation, rainfall):
    height, width = land.shape
    flow_land = land & ~lake
    outlet_distance = ndimage.distance_transform_edt(flow_land)
    flow_noise = _noise(rng, height, width, scales=(12, 31, 73, 131))
    wet_cut = float(np.quantile(rainfall[land], 0.55)) if land.any() else 0.0
    source_mask = flow_land & (elevation > 0.15) & (rainfall >= wet_cut) & (outlet_distance > max(8, min(height, width) * 0.020))
    candidates = np.argwhere(source_mask)
    river = np.zeros_like(land, dtype=np.uint8)
    if not len(candidates):
        return river
    score_map = elevation * 0.58 + rainfall / 3000.0 * 0.42 + flow_noise * 0.035
    score_map[~source_mask] = -10.0
    source_target = max(10, int(cfg.RIVER_SOURCE_COUNT * (height * width) / (2000 * 2000)))
    # 從全圖候選點分層抽樣，避免所有源頭擠在單一最高山系。
    sample_size = min(len(candidates), max(5000, source_target * 700))
    sample_ids = rng.choice(len(candidates), size=sample_size, replace=False)
    sampled = candidates[sample_ids]
    rng.shuffle(sampled)
    ranked = sampled
    sources = []
    gap2 = (min(height, width) * 0.032) ** 2
    for y, x in ranked:
        y, x = int(y), int(x)
        if any((y - py) ** 2 + min(abs(x - px), width - abs(x - px)) ** 2 < gap2 for py, px in sources):
            continue
        sources.append((y, x))
        if len(sources) >= source_target:
            break

    neighbors = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
    for source_y, source_x in sources:
        y, x = source_y, source_x
        for _step in range(height + width):
            if not flow_land[y, x]:
                break
            river[y, x] = min(255, int(river[y, x]) + 1)
            current_distance = outlet_distance[y, x]
            choices = []
            for dy, dx in neighbors:
                ny = y + dy
                nx = (x + dx) % width
                if 0 <= ny < height and outlet_distance[ny, nx] < current_distance - 0.01:
                    cost = elevation[ny, nx] + flow_noise[ny, nx] * 0.045
                    choices.append((cost, ny, nx))
            if not choices:
                break
            _cost, y, x = min(choices)
            if lake[y, x] or not land[y, x]:
                break
    # 匯流兩次以上的主河道略為加寬，支流仍保留單格。
    main_channel = river >= 2
    if main_channel.any():
        widened = ndimage.binary_dilation(main_channel, iterations=1) & flow_land
        river[widened & (river == 0)] = 1
    return river


def generate_environment(terrain, heightmap, sea_level, seed, progress=None):
    rng = np.random.default_rng(int(seed) ^ 0x5EEDC1A7)
    height, width = terrain.shape
    land = terrain >= 2

    def report(value, message):
        if progress:
            progress(value, message)

    report(0.80, "計算溫度與緯度帶")
    latitude = np.abs(np.linspace(-1.0, 1.0, height, dtype=np.float32))[:, None]
    elevation = np.clip((heightmap - sea_level) / max(1e-5, 1.0 - sea_level), 0.0, 1.0)
    temperature_noise = _noise(rng, height, width)
    temperature = 34.0 - latitude * 42.0 - elevation * 26.0 + temperature_noise * 4.5
    temperature[~land] = 27.0 - latitude.repeat(width, axis=1)[~land] * 30.0 + temperature_noise[~land] * 2.0

    report(0.84, "模擬濕度、降雨與雨影")
    coast_distance = ndimage.distance_transform_edt(land)
    coastal_moisture = np.exp(-coast_distance / max(8.0, min(height, width) * 0.105))
    moisture_noise = _noise(rng, height, width, scales=(5, 13, 33, 79))
    east_slope = np.gradient(elevation, axis=1)
    windward = np.clip(east_slope * 9.0, -0.22, 0.22)
    tropical = 1.0 - latitude
    humidity = np.clip(0.16 + coastal_moisture * 0.54 + moisture_noise * 0.24 + tropical * 0.15 - elevation * 0.16 + windward, 0.0, 1.0)
    humidity[~land] = 1.0
    warm_factor = np.clip((temperature + 10.0) / 38.0, 0.25, 1.0)
    rainfall = np.clip(120.0 + 2850.0 * humidity * warm_factor + windward * 1200.0, 0.0, 3600.0).astype(np.float32)
    rainfall[~land] = 0.0

    report(0.88, "形成湖泊與河網")
    lake = _make_lakes(rng, land, elevation, rainfall)
    river_strength = _make_rivers(rng, land, lake, elevation, rainfall)
    water = np.zeros_like(terrain, dtype=np.uint8)
    water[lake] = LAKE
    water[(river_strength > 0) & ~lake] = RIVER

    report(0.94, "分類自然生態區")
    biome = np.full_like(terrain, OCEAN, dtype=np.uint8)
    biome[land] = GRASSLAND
    biome[land & ((temperature < -9.0) | ((temperature < -2.0) & (elevation > 0.58)))] = SNOW
    biome[land & (temperature >= -9.0) & (temperature < -2.0)] = TUNDRA
    biome[land & (temperature >= -2.0) & ((rainfall < 760.0) | (humidity < 0.38))] = DESERT
    biome[land & (temperature >= -2.0) & (humidity >= 0.57) & (rainfall >= 1150.0)] = FOREST
    flatness = np.hypot(np.gradient(elevation, axis=0), np.gradient(elevation, axis=1))
    swamp = land & (temperature > 7.0) & (humidity > 0.78) & (rainfall > 1650.0) & (elevation < 0.34) & (flatness < 0.018)
    swamp |= land & (ndimage.distance_transform_edt(~lake) <= 4) & (temperature > 5.0) & (humidity > 0.68)
    biome[swamp & ~lake] = SWAMP

    return EnvironmentLayers(
        temperature=temperature.astype(np.float32),
        humidity=humidity.astype(np.float32),
        rainfall=rainfall,
        biome=biome,
        water=water,
    )
