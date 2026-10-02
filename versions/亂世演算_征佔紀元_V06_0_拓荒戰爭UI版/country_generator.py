"""依V3可居住性建立國家、領土、聚落與交通網。"""

from dataclasses import dataclass
import colorsys
import math

import numpy as np
from scipy import ndimage

import map_config as cfg

NONE = 0
CAPITAL = 1
CITY = 2
PORT = 3
BARRACKS = 4
OUTPOST = 5


@dataclass
class CountryLayers:
    territory: np.ndarray
    border: np.ndarray
    settlement: np.ndarray
    roads: np.ndarray
    sea_routes: np.ndarray
    countries: list


def _country_names(count):
    prefixes = ("曜日", "蒼海", "玄峰", "星原", "白露", "赤川", "青嶺", "雲澤", "金穹", "風島", "霜河", "明砂")
    suffixes = ("共和國", "聯邦", "王國", "公國", "同盟", "自治領")
    return [prefixes[i % len(prefixes)] + suffixes[(i // len(prefixes) + i) % len(suffixes)] for i in range(count)]


def _colors(count):
    result = []
    golden = 0.61803398875
    for i in range(count):
        hue = (0.07 + i * golden) % 1.0
        sat = 0.58 + 0.12 * ((i * 7) % 3) / 2
        val = 0.90
        result.append(tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, sat, val)))
    return result


def _select_capitals(world, rng, count):
    usable = (world.terrain >= 2) & (world.water == 0) & (world.movement_cost < 255)
    continent_sizes = np.bincount(world.continent.ravel())
    area_scale = world.terrain.size / (2000 * 2000)
    minimum_landmass = max(300, int(cfg.MIN_COUNTRY_LANDMASS_CELLS * area_scale))
    large_enough = continent_sizes[np.clip(world.continent, 0, len(continent_sizes) - 1)] >= minimum_landmass
    usable &= large_enough
    threshold = max(42, int(np.quantile(world.city_value[usable], 0.62))) if usable.any() else 100
    candidates = np.argwhere(usable & (world.city_value >= threshold))
    if not len(candidates):
        return []
    scores = (
        world.city_value[candidates[:, 0], candidates[:, 1]].astype(np.float32)
        + world.freshwater[candidates[:, 0], candidates[:, 1]] * 0.16
        + rng.random(len(candidates)) * 9.0
    )
    order = np.argsort(scores)[::-1]
    height, width = world.terrain.shape
    min_gap = max(18.0, min(height, width) * cfg.COUNTRY_MIN_DISTANCE_RATIO)
    selected = []
    for idx in order:
        y, x = map(int, candidates[idx])
        continent = int(world.continent[y, x])
        if continent <= 0:
            continue
        if any((y - py) ** 2 + min(abs(x - px), width - abs(x - px)) ** 2 < min_gap ** 2 for py, px in selected):
            continue
        selected.append((y, x))
        if len(selected) >= count:
            break
    return selected


def _expand_territories(world, capitals):
    height, width = world.terrain.shape
    territory = np.zeros((height, width), dtype=np.uint16)
    best = np.full((height, width), np.inf, dtype=np.float32)
    yy, xx = np.indices((height, width), dtype=np.float32)
    radius = min(height, width) * cfg.TERRITORY_RADIUS_RATIO
    for country_id, (cy, cx) in enumerate(capitals, start=1):
        continent_id = world.continent[cy, cx]
        valid = world.continent == continent_id
        dx = np.minimum(np.abs(xx - cx), width - np.abs(xx - cx))
        dy = yy - cy
        distance = np.hypot(dx, dy)
        local_friction = 1.0 + np.minimum(world.movement_cost.astype(np.float32), 20.0) / 45.0
        cost = distance * local_friction - world.city_value * 0.52 - world.freshwater * 0.10
        take = valid & (distance <= radius) & (cost < best)
        best[take] = cost[take]
        territory[take] = country_id
    # 極端地形保留為無主地，形成邊疆而非強制塗滿全陸地。
    hostile = (world.movement_cost >= 17) & (world.city_value < 12)
    territory[hostile] = 0
    return territory


def _initial_territories(world, capitals):
    """只建立首都周圍的小型核心領土，其他陸地留待遊戲中拓荒。"""
    height, width = world.terrain.shape
    territory = np.zeros((height, width), dtype=np.uint16)
    radius = max(2, int(cfg.INITIAL_TERRITORY_RADIUS))
    yy, xx = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    offsets = np.argwhere(yy * yy + xx * xx <= radius * radius) - radius
    offsets = sorted(offsets.tolist(), key=lambda p: p[0] * p[0] + p[1] * p[1])
    for country_id, (cy, cx) in enumerate(capitals, start=1):
        claimed = 0
        continent_id = world.continent[cy, cx]
        for dy, dx in offsets:
            y, x = cy + int(dy), (cx + int(dx)) % width
            if not (0 <= y < height) or claimed >= cfg.INITIAL_TERRITORY_MAX_CELLS:
                continue
            if world.continent[y, x] != continent_id or world.terrain[y, x] < 2 or territory[y, x] != 0:
                continue
            territory[y, x] = country_id
            claimed += 1
    return territory


def _border_mask(territory):
    border = np.zeros_like(territory, dtype=bool)
    border[:, 1:] |= (territory[:, 1:] != territory[:, :-1]) & (territory[:, 1:] > 0)
    border[:, :-1] |= (territory[:, 1:] != territory[:, :-1]) & (territory[:, :-1] > 0)
    border[1:, :] |= (territory[1:, :] != territory[:-1, :]) & (territory[1:, :] > 0)
    border[:-1, :] |= (territory[1:, :] != territory[:-1, :]) & (territory[:-1, :] > 0)
    border[:, 0] |= (territory[:, 0] != territory[:, -1]) & (territory[:, 0] > 0)
    border[:, -1] |= (territory[:, 0] != territory[:, -1]) & (territory[:, -1] > 0)
    return border.astype(np.uint8)


def _pick_cities(world, territory, country_id, capital, target):
    mask = (territory == country_id) & (world.water == 0) & (world.city_value >= 48)
    if not mask.any() or target <= 0:
        return []
    peaks = mask & (world.city_value >= ndimage.maximum_filter(world.city_value, size=31, mode="nearest"))
    coords = np.argwhere(peaks)
    if not len(coords):
        return []
    values = world.city_value[coords[:, 0], coords[:, 1]]
    result = []
    min_gap2 = (min(world.terrain.shape) * 0.022) ** 2
    for idx in np.argsort(values)[::-1]:
        y, x = map(int, coords[idx])
        if (y - capital[0]) ** 2 + (x - capital[1]) ** 2 < min_gap2:
            continue
        if any((y - py) ** 2 + (x - px) ** 2 < min_gap2 for py, px in result):
            continue
        result.append((y, x))
        if len(result) >= target:
            break
    return result


def _pick_ports(world, territory, country_id, occupied, target):
    sea = world.terrain <= 1
    coast = (territory == country_id) & ndimage.binary_dilation(sea, iterations=2) & (world.water == 0)
    coords = np.argwhere(coast & (world.city_value >= 24))
    if not len(coords):
        return []
    score = world.city_value[coords[:, 0], coords[:, 1]] + world.freshwater[coords[:, 0], coords[:, 1]] * 0.12
    result = []
    gap2 = (min(world.terrain.shape) * 0.025) ** 2
    for idx in np.argsort(score)[::-1]:
        point = tuple(map(int, coords[idx]))
        if any((point[0] - y) ** 2 + (point[1] - x) ** 2 < gap2 for y, x in occupied + result):
            continue
        result.append(point)
        if len(result) >= target:
            break
    return result


def _greedy_route(world, territory, country_id, start, goal):
    height, width = territory.shape
    y, x = start
    path = [(y, x)]
    visited = {(y, x)}
    for _ in range((height + width) * 2):
        if abs(y - goal[0]) <= 1 and min(abs(x - goal[1]), width - abs(x - goal[1])) <= 1:
            path.append(goal)
            return path
        choices = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0:
                    continue
                ny, nx = y + dy, (x + dx) % width
                if not (0 <= ny < height) or territory[ny, nx] != country_id or (ny, nx) in visited:
                    continue
                ddx = min(abs(nx - goal[1]), width - abs(nx - goal[1]))
                distance = math.hypot(ny - goal[0], ddx)
                cost = distance + min(int(world.movement_cost[ny, nx]), 30) * 1.35
                choices.append((cost, ny, nx))
        if not choices:
            break
        _cost, y, x = min(choices)
        visited.add((y, x))
        path.append((y, x))
    return []


def _line_points(start, end, height, width):
    y0, x0 = start; y1, x1 = end
    dx_wrap = ((x1 - x0 + width / 2) % width) - width / 2
    steps = max(1, int(max(abs(y1 - y0), abs(dx_wrap))))
    result = []
    for i in range(steps + 1):
        t = i / steps
        y = int(round(y0 + (y1 - y0) * t))
        x = int(round(x0 + dx_wrap * t)) % width
        if 0 <= y < height:
            result.append((y, x))
    return result


def generate_countries(world, progress=None):
    rng = np.random.default_rng(int(world.settings.seed) ^ 0xC0A7A1E5)
    height, width = world.terrain.shape
    area_scale = height * width / (2000 * 2000)
    count = max(8, int(round(cfg.COUNTRY_COUNT * area_scale)))
    if progress: progress(0.992, "選擇國家出生點與首都")
    capitals = _select_capitals(world, rng, count)
    territory = _initial_territories(world, capitals)
    border = _border_mask(territory)
    settlement = np.zeros((height, width), dtype=np.uint8)
    roads = np.zeros((height, width), dtype=np.uint8)
    sea_routes = np.zeros((height, width), dtype=np.uint8)
    names, colors = _country_names(len(capitals)), _colors(len(capitals))
    countries = []

    if progress: progress(0.995, "建立城市、港口與道路")
    all_ports = []
    for country_id, capital in enumerate(capitals, start=1):
        settlement[capital] = CAPITAL
        area = int((territory == country_id).sum())
        cities = []
        ports = []
        countries.append({
            "id": country_id,
            "name": names[country_id - 1],
            "color": list(colors[country_id - 1]),
            "capital": [capital[1], capital[0]],
            "cities": [[x, y] for y, x in cities],
            "ports": [[x, y] for y, x in ports],
            "territory_cells": area,
        })

    if progress: progress(0.998, "連接海上航線")
    sea = world.terrain <= 1
    used_pairs = set()
    for country_id, point in all_ports:
        others = [(oid, op) for oid, op in all_ports if oid != country_id]
        if not others:
            continue
        oid, target = min(others, key=lambda item: (item[1][0] - point[0]) ** 2 + min(abs(item[1][1] - point[1]), width - abs(item[1][1] - point[1])) ** 2)
        pair = tuple(sorted((country_id, oid)))
        if pair in used_pairs:
            continue
        used_pairs.add(pair)
        for y, x in _line_points(point, target, height, width):
            if sea[y, x]:
                sea_routes[y, x] = 1
    return CountryLayers(territory, border, settlement, roads, sea_routes, countries)
