"""《亂世演算_征佔紀元》獨立世界地形生成器。"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

import map_config as cfg
from map_renderer import render_environment
from environment_generator import generate_environment
from habitability_generator import generate_habitability
from country_generator import generate_countries
from terrain_rules import (
    BEACH,
    DEEP_OCEAN,
    HIGH_MOUNTAIN,
    HILL,
    MOUNTAIN,
    PLAIN,
    SHALLOW_OCEAN,
)

PROJECT_DIR = Path(__file__).resolve().parent
SAVES_DIR = PROJECT_DIR / "saves"
SAVES_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class MapSettings:
    width: int = cfg.MAP_WIDTH
    height: int = cfg.MAP_HEIGHT
    seed: int = cfg.MAP_SEED
    world_style: str = cfg.WORLD_STYLE
    target_ocean_ratio: float = cfg.TARGET_OCEAN_RATIO

    def validated(self) -> "MapSettings":
        width = max(128, min(8000, int(self.width)))
        height = max(128, min(8000, int(self.height)))
        ocean = float(np.clip(self.target_ocean_ratio, 0.45, 0.90))
        style = str(self.world_style or "RANDOM").upper()
        allowed = {"RANDOM", *cfg.WORLD_STYLE_OPTIONS}
        if style not in allowed:
            style = "RANDOM"
        return MapSettings(width, height, int(self.seed), style, ocean)


@dataclass
class GeneratedMap:
    settings: MapSettings
    height: np.ndarray
    terrain: np.ndarray
    continent: np.ndarray
    plate: np.ndarray
    temperature: np.ndarray
    humidity: np.ndarray
    rainfall: np.ndarray
    biome: np.ndarray
    water: np.ndarray
    agriculture: np.ndarray
    timber: np.ndarray
    minerals: np.ndarray
    freshwater: np.ndarray
    city_value: np.ndarray
    defense_value: np.ndarray
    movement_cost: np.ndarray
    territory: np.ndarray
    border: np.ndarray
    settlement: np.ndarray
    roads: np.ndarray
    sea_routes: np.ndarray
    countries: list
    sea_level: float
    world_style: str
    generation_seconds: float


STYLE_PROFILES = {
    "BALANCED": dict(cores=(3, 6), ocean_delta=0.00, core_scale=1.00, islands=1.00, inland=(1, 2), peninsulas=(4, 8), bays=(3, 7), chains=(2, 4)),
    "SUPERCONTINENT": dict(cores=(2, 3), ocean_delta=-0.05, core_scale=1.42, islands=0.55, inland=(1, 2), peninsulas=(5, 9), bays=(4, 7), chains=(1, 2)),
    "ARCHIPELAGO": dict(cores=(6, 10), ocean_delta=0.08, core_scale=0.68, islands=1.75, inland=(0, 1), peninsulas=(3, 6), bays=(2, 5), chains=(5, 8)),
    "FRACTURED": dict(cores=(5, 9), ocean_delta=0.02, core_scale=0.82, islands=1.25, inland=(0, 2), peninsulas=(6, 11), bays=(6, 11), chains=(3, 6)),
    "INLAND_SEAS": dict(cores=(2, 4), ocean_delta=-0.04, core_scale=1.30, islands=0.75, inland=(3, 5), peninsulas=(5, 8), bays=(4, 8), chains=(1, 3)),
    "TWIN_CONTINENTS": dict(cores=(2, 2), ocean_delta=0.00, core_scale=1.38, islands=0.85, inland=(1, 2), peninsulas=(4, 7), bays=(3, 6), chains=(2, 4)),
}


def _normalize(array: np.ndarray) -> np.ndarray:
    array = array.astype(np.float32, copy=False)
    lo = float(array.min())
    hi = float(array.max())
    if hi - lo < 1e-9:
        return np.zeros_like(array, dtype=np.float32)
    return (array - lo) / (hi - lo)


def _resized_noise(rng, height, width, cells_y, cells_x, order=3):
    source = rng.normal(0.0, 1.0, (max(2, cells_y), max(2, cells_x))).astype(np.float32)
    zoom = (height / source.shape[0], width / source.shape[1])
    result = ndimage.zoom(source, zoom, order=order, mode="wrap", prefilter=order > 1)
    return _normalize(result[:height, :width]) * 2.0 - 1.0


def _fractal_noise(rng, height, width):
    result = np.zeros((height, width), dtype=np.float32)
    total = 0.0
    for cells, weight in ((5, 0.48), (11, 0.26), (25, 0.15), (57, 0.075), (119, 0.035)):
        aspect = width / max(1, height)
        cells_x = max(3, int(round(cells * aspect)))
        result += _resized_noise(rng, height, width, cells, cells_x) * weight
        total += weight
    return result / total


def _warped(array, rng, strength):
    height, width = array.shape
    warp_y = _resized_noise(rng, height, width, 9, max(3, int(9 * width / height)), order=3)
    warp_x = _resized_noise(rng, height, width, 9, max(3, int(9 * width / height)), order=3)
    yy, xx = np.indices((height, width), dtype=np.float32)
    scale = min(height, width) * float(strength)
    coords = np.array((yy + warp_y * scale, xx + warp_x * scale), dtype=np.float32)
    coords[0] = np.clip(coords[0], 0, height - 1)
    coords[1] %= width
    return ndimage.map_coordinates(array, coords, order=1, mode="wrap").astype(np.float32)


def _continent_field(rng, height, width, profile):
    yy, xx = np.indices((height, width), dtype=np.float32)
    field = np.full((height, width), -1.3, dtype=np.float32)
    core_min, core_max = profile["cores"]
    core_count = int(rng.integers(core_min, core_max + 1))

    if core_count == 2 and profile is STYLE_PROFILES["TWIN_CONTINENTS"]:
        centers = [(height * 0.48, width * 0.28), (height * 0.52, width * 0.72)]
    else:
        # Maximin 候選取樣：保留隨機性，但避免所有大陸核心擠在同一角。
        centers = [(rng.uniform(height * 0.18, height * 0.82), rng.uniform(0, width))]
        while len(centers) < core_count:
            candidates = [
                (rng.uniform(height * 0.14, height * 0.86), rng.uniform(0, width))
                for _ in range(48)
            ]

            def nearest_distance(candidate):
                cy, cx = candidate
                distances = []
                for py, px in centers:
                    dx = min(abs(cx - px), width - abs(cx - px)) / width
                    dy = abs(cy - py) / height
                    distances.append(dx * dx + dy * dy)
                return min(distances)

            centers.append(max(candidates, key=nearest_distance))

    base = min(height, width) * 0.19 * profile["core_scale"]
    core_shapes = []
    for cy, cx in centers:
        # 強制部分大陸具有清楚長軸，不再全是近圓形。
        aspect = rng.uniform(1.45, 2.65)
        short = base * rng.uniform(0.56, 0.88)
        rx = short * aspect
        ry = short
        if rng.random() < 0.5:
            rx, ry = ry, rx
        angle = rng.uniform(0, math.tau)
        core_shapes.append((cy, cx, rx, ry, angle))
        dx = ((xx - cx + width / 2) % width) - width / 2
        dy = yy - cy
        xr = dx * math.cos(angle) + dy * math.sin(angle)
        yr = -dx * math.sin(angle) + dy * math.cos(angle)
        blob = np.exp(-((xr / rx) ** 2 + (yr / ry) ** 2) * 1.65)
        field = np.maximum(field, blob.astype(np.float32) * 2.0 - 1.0)

    # 半島：從主大陸外緣向外伸展的逐漸縮小地塊。
    peninsula_count = int(rng.integers(profile["peninsulas"][0], profile["peninsulas"][1] + 1))
    for _ in range(peninsula_count):
        cy, cx, rx, ry, angle = core_shapes[int(rng.integers(0, len(core_shapes)))]
        direction = angle + rng.choice((-1, 1)) * rng.uniform(0.45, 1.25)
        start_r = min(rx, ry) * rng.uniform(0.58, 0.86)
        length = base * rng.uniform(0.38, 0.82)
        segments = int(rng.integers(3, 6))
        bend = rng.uniform(-0.5, 0.5)
        for step in range(segments):
            t = (step + 1) / segments
            local_angle = direction + bend * t
            py = cy + math.sin(local_angle) * (start_r + length * t)
            px = cx + math.cos(local_angle) * (start_r + length * t)
            radius = base * (0.25 - 0.12 * t) * rng.uniform(0.82, 1.18)
            dx = ((xx - px + width / 2) % width) - width / 2
            blob = np.exp(-((dx / (radius * 1.25)) ** 2 + ((yy - py) / radius) ** 2) * 1.8)
            field = np.maximum(field, blob.astype(np.float32) * (1.45 - 0.18 * t) - 0.72)

    # 海灣：從外緣向陸地切入的長形低地。
    bay_count = int(rng.integers(profile["bays"][0], profile["bays"][1] + 1))
    for _ in range(bay_count):
        cy, cx, rx, ry, angle = core_shapes[int(rng.integers(0, len(core_shapes)))]
        direction = angle + rng.uniform(-math.pi, math.pi)
        py = cy + math.sin(direction) * min(rx, ry) * rng.uniform(0.65, 1.0)
        px = cx + math.cos(direction) * min(rx, ry) * rng.uniform(0.65, 1.0)
        long_r = base * rng.uniform(0.22, 0.48)
        short_r = long_r * rng.uniform(0.20, 0.42)
        dx = ((xx - px + width / 2) % width) - width / 2
        dy = yy - py
        xr = dx * math.cos(direction) + dy * math.sin(direction)
        yr = -dx * math.sin(direction) + dy * math.cos(direction)
        cut = np.exp(-((xr / long_r) ** 2 + (yr / short_r) ** 2) * 1.7)
        field -= cut.astype(np.float32) * rng.uniform(0.42, 0.72)

    # 內海：放在大陸腹地，形狀刻意不完全對稱。
    inland_count = int(rng.integers(profile["inland"][0], profile["inland"][1] + 1))
    for _ in range(inland_count):
        cy, cx, rx, ry, _angle = core_shapes[int(rng.integers(0, len(core_shapes)))]
        cy += rng.uniform(-ry * 0.20, ry * 0.20)
        cx += rng.uniform(-rx * 0.20, rx * 0.20)
        r = base * rng.uniform(0.10, 0.21)
        dx = ((xx - cx + width / 2) % width) - width / 2
        basin = np.exp(-((dx / (r * rng.uniform(0.8, 1.5))) ** 2 + ((yy - cy) / (r * rng.uniform(0.65, 1.15))) ** 2) * 1.5)
        field -= basin.astype(np.float32) * rng.uniform(0.72, 1.05)

    # 島弧：主島鏈會斷裂、偏移，並可伴隨不完整的副島弧。
    chain_count = int(rng.integers(profile["chains"][0], profile["chains"][1] + 1))
    for _ in range(chain_count):
        anchor_y, anchor_x = centers[int(rng.integers(0, len(centers)))]
        direction = rng.uniform(0, math.tau)
        distance = base * rng.uniform(1.05, 1.65)
        start_y = anchor_y + math.sin(direction) * distance
        start_x = anchor_x + math.cos(direction) * distance
        island_count = int(rng.integers(7, 14))
        curve = rng.uniform(-0.85, 0.85)
        gap_probability = rng.uniform(0.12, 0.28)
        has_secondary_arc = rng.random() < 0.48
        secondary_offset = base * rng.uniform(0.10, 0.22) * rng.choice((-1.0, 1.0))
        for index in range(island_count):
            # 首尾之間隨機留白，避免島嶼像等距珍珠項鍊。
            if 0 < index < island_count - 1 and rng.random() < gap_probability:
                continue
            t = index / max(1, island_count - 1)
            local_angle = direction + math.pi / 2 + curve * (t - 0.5) + rng.normal(0.0, 0.045)
            spacing = base * (0.145 * index + 0.018 * index * index / island_count)
            normal_angle = local_angle + math.pi / 2
            jitter = base * rng.uniform(-0.055, 0.055)
            iy = start_y + math.sin(local_angle) * spacing + math.sin(normal_angle) * jitter
            ix = start_x + math.cos(local_angle) * spacing + math.cos(normal_angle) * jitter

            # 多數為小島，但偶爾出現一、兩座主島。
            major_island = rng.random() < 0.16
            radius = base * rng.uniform(0.055, 0.105) if major_island else base * rng.uniform(0.022, 0.064)
            island_angle = local_angle + rng.uniform(-0.55, 0.55)
            aspect = rng.uniform(1.15, 2.05)
            dx = ((xx - ix + width / 2) % width) - width / 2
            dy = yy - iy
            xr = dx * math.cos(island_angle) + dy * math.sin(island_angle)
            yr = -dx * math.sin(island_angle) + dy * math.cos(island_angle)
            island = np.exp(-((xr / (radius * aspect)) ** 2 + (yr / radius) ** 2) * 1.9)

            # 叠加一個偏心小葉片，讓單島輪廓不是完美椭圓。
            lobe_shift = radius * rng.uniform(0.35, 0.75)
            lx = ix + math.cos(island_angle) * lobe_shift
            ly = iy + math.sin(island_angle) * lobe_shift
            ldx = ((xx - lx + width / 2) % width) - width / 2
            lobe = np.exp(-((ldx / (radius * 0.75)) ** 2 + ((yy - ly) / (radius * 0.62)) ** 2) * 2.0)
            shape = np.maximum(island, lobe * 0.92)
            field = np.maximum(field, shape.astype(np.float32) * 1.30 - 0.64)

            # 副島弧只保留部分節點，並與主島弧稍微平行。
            if has_secondary_arc and rng.random() < 0.48 and 0.12 < t < 0.9:
                sy = iy + math.sin(normal_angle) * secondary_offset
                sx = ix + math.cos(normal_angle) * secondary_offset
                sr = radius * rng.uniform(0.34, 0.62)
                sdx = ((xx - sx + width / 2) % width) - width / 2
                secondary = np.exp(-((sdx / (sr * rng.uniform(1.0, 1.55))) ** 2 + ((yy - sy) / sr) ** 2) * 2.0)
                field = np.maximum(field, secondary.astype(np.float32) * 1.26 - 0.66)

    # 上下邊界保持海洋，左右可視為環繞世界。
    latitude_edge = np.sin(np.linspace(0, np.pi, height, dtype=np.float32))[:, None]
    field += (latitude_edge - 0.55) * 0.85
    return field, centers


def _plate_layers(rng, height, width):
    count = int(rng.integers(cfg.TECTONIC_PLATE_MIN, cfg.TECTONIC_PLATE_MAX + 1))
    yy, xx = np.indices((height, width), dtype=np.float32)
    best = np.full((height, width), np.inf, dtype=np.float32)
    labels = np.zeros((height, width), dtype=np.uint8)
    for index in range(count):
        cy = rng.uniform(0, height)
        cx = rng.uniform(0, width)
        dx = np.minimum(np.abs(xx - cx), width - np.abs(xx - cx))
        dy = yy - cy
        distance = dx * dx + dy * dy
        take = distance < best
        best[take] = distance[take]
        labels[take] = index + 1

    boundary = np.zeros((height, width), dtype=bool)
    boundary[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    boundary[1:, :] |= labels[1:, :] != labels[:-1, :]
    boundary[:, 0] |= labels[:, 0] != labels[:, -1]
    ridge = ndimage.gaussian_filter(boundary.astype(np.float32), sigma=cfg.MOUNTAIN_WIDTH)
    ridge = _normalize(ridge)
    return labels, ridge


def _remove_tiny_land(land, minimum_area):
    labels, count = ndimage.label(land, structure=np.ones((3, 3), dtype=np.uint8))
    if count <= 0:
        return land
    sizes = np.bincount(labels.ravel())
    keep = sizes >= int(minimum_area)
    keep[0] = False
    return keep[labels]


def _classify(heightmap, land, sea_level):
    terrain = np.full(heightmap.shape, DEEP_OCEAN, dtype=np.uint8)
    terrain[(~land) & (heightmap >= sea_level - cfg.DEEP_OCEAN_DEPTH)] = SHALLOW_OCEAN

    above = heightmap - sea_level
    coast_distance = ndimage.distance_transform_edt(land)
    beach = land & ((above < cfg.BEACH_HEIGHT) | (coast_distance <= 2.0))
    interior = land & ~beach
    terrain[beach] = BEACH
    terrain[interior] = PLAIN
    terrain[interior & (above >= cfg.PLAIN_HEIGHT)] = HILL
    terrain[interior & (above >= cfg.HILL_HEIGHT)] = MOUNTAIN
    terrain[interior & (above >= cfg.MOUNTAIN_HEIGHT)] = HIGH_MOUNTAIN
    return terrain


def generate_world(settings: MapSettings, progress=None) -> GeneratedMap:
    settings = settings.validated()
    started = time.perf_counter()
    rng = np.random.default_rng(settings.seed)
    style = settings.world_style
    if style == "RANDOM":
        style = str(rng.choice(cfg.WORLD_STYLE_OPTIONS))
    profile = STYLE_PROFILES[style]
    height, width = settings.height, settings.width

    def report(value, message):
        if progress:
            progress(float(value), str(message))

    report(0.05, "建立大陸骨架")
    continent_base, _centers = _continent_field(rng, height, width, profile)
    report(0.20, "生成多尺度海岸")
    noise = _fractal_noise(rng, height, width)
    noise = _warped(noise, rng, cfg.DOMAIN_WARP_STRENGTH)
    coast_detail = _resized_noise(rng, height, width, 83, max(3, int(83 * width / height)), order=1)

    report(0.42, "推演板塊與山系")
    plates, ridges = _plate_layers(rng, height, width)
    island_noise = _resized_noise(rng, height, width, 37, max(3, int(37 * width / height)), order=3)

    raw = (
        continent_base
        + noise * cfg.CONTINENT_NOISE_STRENGTH
        + coast_detail * cfg.COAST_DETAIL_STRENGTH
        + np.maximum(0.0, island_noise - 0.58)
        * cfg.ISLAND_CHAIN_STRENGTH
        * profile["islands"]
    )
    raw = _normalize(raw)

    target_ocean = float(np.clip(settings.target_ocean_ratio + profile["ocean_delta"], 0.48, 0.86))
    sea_level = float(np.quantile(raw, target_ocean))
    land = raw >= sea_level

    report(0.60, "清理碎斑與修整海岸")
    if cfg.COAST_SMOOTHING_ITERATIONS > 0:
        structure = ndimage.generate_binary_structure(2, 1)
        land = ndimage.binary_closing(land, structure=structure, iterations=cfg.COAST_SMOOTHING_ITERATIONS)
        land = ndimage.binary_opening(land, structure=structure, iterations=1)
    land = _remove_tiny_land(land, cfg.MIN_ISLAND_AREA)

    # 海岸形狀與陸地高度分離，避免每個大陸核心都變成同心圓高山。
    inland_distance = ndimage.distance_transform_edt(land).astype(np.float32)
    inland_scale = max(8.0, min(height, width) * 0.075)
    inland = np.clip(inland_distance / inland_scale, 0.0, 1.0)
    relief_noise = _normalize(noise * 0.72 + coast_detail * 0.28)
    mountain_mask = ndimage.gaussian_filter(land.astype(np.float32), sigma=4.0)
    above_sea = (
        0.006
        + np.sqrt(inland) * 0.16
        + relief_noise * 0.075
        + ridges * mountain_mask * cfg.MOUNTAIN_STRENGTH
    )
    heightmap = np.where(
        land,
        sea_level + above_sea,
        np.minimum(raw, sea_level - 0.0005),
    )
    heightmap = np.clip(heightmap, 0.0, 1.0)

    report(0.76, "辨識大陸與島嶼")
    continent, _count = ndimage.label(land, structure=np.ones((3, 3), dtype=np.uint8))
    continent = continent.astype(np.int32)
    terrain = _classify(heightmap, land, sea_level)

    environment = generate_environment(terrain, heightmap, sea_level, settings.seed, report)
    partial_world = GeneratedMap(
        settings=settings,
        height=heightmap.astype(np.float32),
        terrain=terrain,
        continent=continent,
        plate=plates,
        temperature=environment.temperature,
        humidity=environment.humidity,
        rainfall=environment.rainfall,
        biome=environment.biome,
        water=environment.water,
        agriculture=np.zeros_like(terrain, dtype=np.uint8),
        timber=np.zeros_like(terrain, dtype=np.uint8),
        minerals=np.zeros_like(terrain, dtype=np.uint8),
        freshwater=np.zeros_like(terrain, dtype=np.uint8),
        city_value=np.zeros_like(terrain, dtype=np.uint8),
        defense_value=np.zeros_like(terrain, dtype=np.uint8),
        movement_cost=np.full_like(terrain, 255, dtype=np.uint8),
        territory=np.zeros_like(terrain, dtype=np.uint16),
        border=np.zeros_like(terrain, dtype=np.uint8),
        settlement=np.zeros_like(terrain, dtype=np.uint8),
        roads=np.zeros_like(terrain, dtype=np.uint8),
        sea_routes=np.zeros_like(terrain, dtype=np.uint8),
        countries=[],
        sea_level=sea_level,
        world_style=style,
        generation_seconds=0.0,
    )
    habitability = generate_habitability(partial_world, report)
    partial_world.agriculture = habitability.agriculture
    partial_world.timber = habitability.timber
    partial_world.minerals = habitability.minerals
    partial_world.freshwater = habitability.freshwater
    partial_world.city_value = habitability.city
    partial_world.defense_value = habitability.defense
    partial_world.movement_cost = habitability.movement_cost
    political = generate_countries(partial_world, report)
    partial_world.territory = political.territory
    partial_world.border = political.border
    partial_world.settlement = political.settlement
    partial_world.roads = political.roads
    partial_world.sea_routes = political.sea_routes
    partial_world.countries = political.countries
    partial_world.generation_seconds = time.perf_counter() - started
    report(1.0, "完成國家、領土與交通網")
    return partial_world


def save_world(world: GeneratedMap, save_dir=SAVES_DIR):
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    data_path = save_dir / cfg.DATA_FILENAME
    preview_path = save_dir / cfg.PREVIEW_FILENAME
    info_path = save_dir / cfg.INFO_FILENAME

    np.savez_compressed(
        data_path,
        height=world.height,
        terrain=world.terrain,
        continent=world.continent,
        plate=world.plate,
        temperature=world.temperature,
        humidity=world.humidity,
        rainfall=world.rainfall,
        biome=world.biome,
        water=world.water,
        agriculture=world.agriculture,
        timber=world.timber,
        minerals=world.minerals,
        freshwater=world.freshwater,
        city_value=world.city_value,
        defense_value=world.defense_value,
        movement_cost=world.movement_cost,
        territory=world.territory,
        border=world.border,
        settlement=world.settlement,
        roads=world.roads,
        sea_routes=world.sea_routes,
        sea_level=np.float32(world.sea_level),
        seed=np.int64(world.settings.seed),
    )
    render_environment(world, "國家與領土", preview_path)

    land = world.terrain >= BEACH
    continent_ids, counts = np.unique(world.continent[land], return_counts=True)
    areas = sorted(
        (int(area) for cid, area in zip(continent_ids, counts) if int(cid) > 0),
        reverse=True,
    )
    info = {
        "game": "亂世演算_征佔紀元",
        "version": "V13_殖民航線與航行船隊版",
        "width": world.settings.width,
        "height": world.settings.height,
        "seed": world.settings.seed,
        "world_style": world.world_style,
        "target_ocean_ratio": world.settings.target_ocean_ratio,
        "actual_ocean_ratio": round(float(1.0 - land.mean()), 6),
        "sea_level": round(float(world.sea_level), 6),
        "landmass_count": len(areas),
        "largest_landmasses": areas[:12],
        "generation_seconds": round(float(world.generation_seconds), 3),
        "average_land_temperature_c": round(float(world.temperature[land].mean()), 3),
        "average_land_humidity": round(float(world.humidity[land].mean()), 4),
        "average_land_rainfall_mm": round(float(world.rainfall[land].mean()), 2),
        "lake_cells": int((world.water == 1).sum()),
        "river_cells": int((world.water == 2).sum()),
        "average_agriculture": round(float(world.agriculture[land].mean()), 2),
        "average_timber": round(float(world.timber[land].mean()), 2),
        "average_minerals": round(float(world.minerals[land].mean()), 2),
        "average_freshwater": round(float(world.freshwater[land].mean()), 2),
        "average_city_value": round(float(world.city_value[land].mean()), 2),
        "average_defense_value": round(float(world.defense_value[land].mean()), 2),
        "average_movement_cost": round(float(world.movement_cost[land & (world.movement_cost < 255)].mean()), 2),
        "country_count": len(world.countries),
        "claimed_land_ratio": round(float((world.territory[land] > 0).mean()), 5),
        "capital_count": int((world.settlement == 1).sum()),
        "city_count": int((world.settlement == 2).sum()),
        "port_count": int((world.settlement == 3).sum()),
        "road_cells": int((world.roads > 0).sum()),
        "sea_route_cells": int((world.sea_routes > 0).sum()),
        "countries": world.countries,
        "files": {
            "data": cfg.DATA_FILENAME,
            "preview": cfg.PREVIEW_FILENAME,
        },
    }
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return data_path, preview_path, info_path


def load_world(save_dir=SAVES_DIR) -> GeneratedMap:
    save_dir = Path(save_dir)
    info = json.loads((save_dir / cfg.INFO_FILENAME).read_text(encoding="utf-8"))
    with np.load(save_dir / cfg.DATA_FILENAME) as data:
        settings = MapSettings(
            width=int(info["width"]),
            height=int(info["height"]),
            seed=int(info["seed"]),
            world_style=str(info["world_style"]),
            target_ocean_ratio=float(info["target_ocean_ratio"]),
        )
        return GeneratedMap(
            settings=settings,
            height=data["height"].copy(),
            terrain=data["terrain"].copy(),
            continent=data["continent"].copy(),
            plate=data["plate"].copy(),
            temperature=data["temperature"].copy(),
            humidity=data["humidity"].copy(),
            rainfall=data["rainfall"].copy(),
            biome=data["biome"].copy(),
            water=data["water"].copy(),
            agriculture=data["agriculture"].copy(),
            timber=data["timber"].copy(),
            minerals=data["minerals"].copy(),
            freshwater=data["freshwater"].copy(),
            city_value=data["city_value"].copy(),
            defense_value=data["defense_value"].copy(),
            movement_cost=data["movement_cost"].copy(),
            territory=data["territory"].copy(),
            border=data["border"].copy(),
            settlement=data["settlement"].copy(),
            roads=data["roads"].copy(),
            sea_routes=data["sea_routes"].copy(),
            countries=list(info.get("countries", [])),
            sea_level=float(data["sea_level"]),
            world_style=str(info["world_style"]),
            generation_seconds=float(info.get("generation_seconds", 0.0)),
        )


if __name__ == "__main__":
    chosen = MapSettings()
    print(f"生成 {chosen.width}×{chosen.height} 世界，Seed={chosen.seed}…")
    generated = generate_world(chosen, lambda p, m: print(f"{p:>5.0%} {m}"))
    paths = save_world(generated)
    print(f"完成：{generated.world_style}｜{generated.generation_seconds:.2f} 秒")
    for path in paths:
        print(path)
