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
from map_renderer import render_map
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
    sea_level: float
    world_style: str
    generation_seconds: float


STYLE_PROFILES = {
    "BALANCED": dict(cores=(4, 8), ocean_delta=0.00, core_scale=1.00, islands=1.00, inland=0),
    "SUPERCONTINENT": dict(cores=(2, 4), ocean_delta=-0.04, core_scale=1.35, islands=0.55, inland=0),
    "ARCHIPELAGO": dict(cores=(7, 12), ocean_delta=0.08, core_scale=0.72, islands=1.75, inland=0),
    "FRACTURED": dict(cores=(7, 11), ocean_delta=0.02, core_scale=0.84, islands=1.25, inland=0),
    "INLAND_SEAS": dict(cores=(3, 6), ocean_delta=-0.03, core_scale=1.22, islands=0.75, inland=3),
    "TWIN_CONTINENTS": dict(cores=(2, 2), ocean_delta=0.00, core_scale=1.35, islands=0.85, inland=0),
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
    for cy, cx in centers:
        rx = base * rng.uniform(0.72, 1.42)
        ry = base * rng.uniform(0.62, 1.28)
        angle = rng.uniform(0, math.tau)
        dx = ((xx - cx + width / 2) % width) - width / 2
        dy = yy - cy
        xr = dx * math.cos(angle) + dy * math.sin(angle)
        yr = -dx * math.sin(angle) + dy * math.cos(angle)
        blob = np.exp(-((xr / rx) ** 2 + (yr / ry) ** 2) * 1.65)
        field = np.maximum(field, blob.astype(np.float32) * 2.0 - 1.0)

    # 內海型在大陸核心內壓出數個低地，不直接照抄任何現實海岸。
    for _ in range(int(profile["inland"])):
        cy, cx = centers[int(rng.integers(0, len(centers)))]
        cy += rng.uniform(-base * 0.35, base * 0.35)
        cx += rng.uniform(-base * 0.35, base * 0.35)
        r = base * rng.uniform(0.13, 0.25)
        dx = ((xx - cx + width / 2) % width) - width / 2
        basin = np.exp(-((dx / r) ** 2 + ((yy - cy) / (r * 0.8)) ** 2) * 1.5)
        field -= basin.astype(np.float32) * 0.75

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

    elapsed = time.perf_counter() - started
    report(0.90, "完成地形分類")
    return GeneratedMap(
        settings=settings,
        height=heightmap.astype(np.float32),
        terrain=terrain,
        continent=continent,
        plate=plates,
        sea_level=sea_level,
        world_style=style,
        generation_seconds=elapsed,
    )


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
        sea_level=np.float32(world.sea_level),
        seed=np.int64(world.settings.seed),
    )
    render_map(world.terrain, world.height, preview_path)

    land = world.terrain >= BEACH
    continent_ids, counts = np.unique(world.continent[land], return_counts=True)
    areas = sorted(
        (int(area) for cid, area in zip(continent_ids, counts) if int(cid) > 0),
        reverse=True,
    )
    info = {
        "game": "亂世演算_征佔紀元",
        "version": "V1_世界地形實驗版",
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
