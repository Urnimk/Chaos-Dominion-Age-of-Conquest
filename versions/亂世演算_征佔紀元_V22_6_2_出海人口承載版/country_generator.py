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


# def _country_names(count):
#     prefixes = ("曜日", "蒼海", "玄峰", "星原", "白露", "赤川", "青嶺", "雲澤", "金穹", "風島", "霜河", "明砂")
#     suffixes = ("共和國", "聯邦", "王國", "公國", "同盟", "自治領")
#     return [prefixes[i % len(prefixes)] + suffixes[(i // len(prefixes) + i) % len(suffixes)] for i in range(count)]

#     names = []  # 初始化最終名稱串列
#     for name in custom_names:  # 優先從自訂名稱庫填入
#         if len(names) < n:  # 若數量尚未達到指定需求 n
#             names.append(name)  # 加入名稱
#         else:
#             break  # 已達數量則跳出迴圈

#     while len(names) < n:  # 若自訂名稱不夠 n 個，則透過前後綴組合隨機生成
#         p = random.choice(prefixes)  # 隨機選取前綴
#         s = random.choice(suffixes)  # 隨機選取後綴
#         generated_name = f"{p}{s}"  # 組合前後綴
#         if generated_name not in names:  # 確保名稱不重複
#             names.append(generated_name)  # 加入名稱串列

#     return names  # 回傳產生的國家名稱串列


def _country_names(n):
    """生成基本國家名稱列表"""
    custom_names = [  # 預設自訂特色名稱清單
        "挫蛋先鋒", "奶霜聯盟", "嗜血狂鯊", "霹靂暗雷", "地獄烈焰", "閃電戰狼", "虛擬幻影",
        "深淵巨妖", "夜城行者", "量子重力", "黑客帝國", "蒸汽朋克", "諸神黃昏", "冥府使者",
        "奧林帕斯", "北歐暴風", "絕對零度", "不死鳳凰", "黃金聖盾", "劇毒沼澤", "猩紅女巫",
        "合金重裝", "像素方塊", "末地使者", "戰地轟炸", "凋零風暴", "紅石科技", "摸魚大師",
        "肝帝連盟", "歐皇附體", "非酋救濟", "宵夜雷達",

        "終焉之刃", "極光幻滅", "暗夜孤狼", "雷霆萬鈞", "寒冰刺客", "烈焰風暴", "不滅戰魂",
        "幽冥狂瀾", "影疾風刃", "鋼鐵意志", "天譴黑翼", "星海游俠", "孤高遊俠", "狂暴巨獸",
        "瞬步暗殺", "虛空之眼", "星河戰隊", "破曉之光",

        "混沌領主", "聖殿騎士", "不朽傳奇", "迷霧幽靈", "惡魔獵手", "亞特蘭提", "煉金術士",
        "命運之輪", "深海歌姬", "精靈密語", "亡靈序曲", "星辰之子", "時空旅人", "永夜序曲",
        "符文刻印",

        "矩陣重組", "賽博浪人", "極限方塊", "潛影之貝", "凋零骷髏", "極限生存", "黑曜石牆",
        "指令方塊", "機械公敵", "光纖追蹤", "超頻驅動", "代碼漏洞", "量子糾纏", "引力坍塌",
        "核心熔毀",

        "薪水小偷", "熬夜冠軍", "外送達人", "起司漢堡", "肥宅快樂", "魔法防禦", "躺平精靈",
        "課金大佬", "戰力單位", "氣氛大師", "極限手殘", "路過鄉民", "珍珠奶茶", "爆米花隊",
        "火鍋戰隊", "咖啡因癮", "睡意襲來", "滿血復活", "絕地翻盤", "全村希望"
    ]

    prefixes = [  # 隨機生成名稱用的前綴字庫
        "阿斯", "貝洛", "塞勒", "多倫", "埃爾", "芬蘭", "格林", "海倫", "伊斯", "克倫",
        "拉斐", "馬爾", "諾斯", "奧林", "佩拉", "昆斯", "雷克", "索倫", "泰坦", "烏拉",
        "瓦爾", "溫斯", "薩克", "約克", "齊格", "阿爾", "博爾", "卡斯", "德拉", "福爾",
        "安地", "波斯", "迦太", "德魯", "伊特", "腓尼", "赫梯", "印加", "美索", "諾曼",
        "帕提", "斯巴", "特洛", "烏加", "梵蒂", "拜占", "瑪雅", "塞爾", "維京", "蘇美"
    ]
    suffixes = [  # 隨機生成名稱用的後綴字庫
        "蒂娜", "斯塔", "利亞", "尼西亞", "高地", "群島", "大路", "特區", "男爵領", "侯國",
        "公國", "聯邦", "帝國", "王國", "聖域", "自治領", "郡", "省", "堡", "關",
        "海峽", "半島", "平線", "谷地", "荒原",
        "之森", "之峰", "之海", "之嶺", "灣", "峽谷", "綠洲", "高原", "沼澤", "苔原",
        "丘陵", "雪原", "沃野", "裂谷", "凍土", "河口", "斷崖", "暗礁", "沙洲", "火山",
        "山脈", "盆地", "溪谷", "峭壁", "海灣"
    ]

    # 先使用自訂名稱；不足時再用前綴＋後綴穩定補足。
    names = []
    for name in custom_names:
        if len(names) >= n:
            break
        if name not in names:
            names.append(name)

    index = 0
    while len(names) < n:
        prefix = prefixes[index % len(prefixes)]
        suffix = suffixes[(index // len(prefixes) + index) % len(suffixes)]
        candidate = f"{prefix}{suffix}"
        if candidate not in names:
            names.append(candidate)
        index += 1

    return names


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
    # Rank habitability within each island, otherwise the global richest islands
    # monopolize every capital and lower-yield islands never get local competition.
    thresholds=np.full(len(continent_sizes),100,dtype=float)
    for island in np.unique(world.continent[usable]):
        values=world.city_value[usable & (world.continent==island)]
        if len(values):thresholds[int(island)]=max(20,float(np.quantile(values,.62)))
    candidates=np.argwhere(usable & (world.city_value>=thresholds[world.continent]))
    if not len(candidates):
        return []
    scores = (
        world.city_value[candidates[:, 0], candidates[:, 1]].astype(np.float32)
        + world.freshwater[candidates[:, 0], candidates[:, 1]] * 0.16
        + rng.random(len(candidates)) * 9.0
    )
    order = np.argsort(scores)[::-1]
    height, width = world.terrain.shape
    min_gap = max(float(getattr(cfg, "CITY_MIN_DISTANCE", 60)),
                  min(height, width) * cfg.COUNTRY_MIN_DISTANCE_RATIO)
    # V22: new worlds place 2--4 competing countries on each inhabited island
    # when geography and the requested total make that feasible. Existing saves are untouched.
    selected = []
    by_island = {}
    for idx in order:
        y,x=map(int,candidates[idx]);island=int(world.continent[y,x])
        if island > 0:by_island.setdefault(island,[]).append((y,x))
    viable=[]
    for island, points in by_island.items():
        spaced=[]
        for y,x in points:
            if all((y-py)**2+min(abs(x-px),width-abs(x-px))**2>=min_gap**2 for py,px in spaced):
                spaced.append((y,x))
                if len(spaced)>=4:break
        if len(spaced)>=2:viable.append((island,spaced))
    viable.sort(key=lambda row:int(continent_sizes[row[0]]),reverse=True)
    inhabited=min(len(viable),max(1,int(round(count/3))))
    while inhabited < min(len(viable),count//2) and sum(len(p) for _,p in viable[:inhabited]) < count:
        inhabited += 1
    if count>=2 and inhabited>0 and inhabited*2<=count<=sum(len(p) for _,p in viable[:inhabited]):
        quotas=[2]*inhabited
        remaining=count-sum(quotas)
        while remaining:
            for i,(_island,points) in enumerate(viable[:inhabited]):
                if remaining and quotas[i]<len(points):
                    quotas[i]+=1;remaining-=1
        for (_island,points),quota in zip(viable[:inhabited],quotas):
            selected.extend(points[:quota])
    # Constrained small maps may lack enough spaced sites; preserve a playable fallback.
    if len(selected)<count:
        for idx in order:
            y,x=map(int,candidates[idx])
            if any((y-py)**2+min(abs(x-px),width-abs(x-px))**2<min_gap**2 for py,px in selected):
                continue
            selected.append((y,x))
            if len(selected)>=count:break
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
    min_gap = float(getattr(cfg, "CITY_MIN_DISTANCE", 60))
    min_gap2 = min_gap ** 2
    for idx in np.argsort(values)[::-1]:
        y, x = map(int, coords[idx])
        dx = min(abs(x - capital[1]), world.terrain.shape[1] - abs(x - capital[1]))
        if (y - capital[0]) ** 2 + dx ** 2 < min_gap2:
            continue
        if any((y - py) ** 2 + min(abs(x - px), world.terrain.shape[1] - abs(x - px)) ** 2 < min_gap2 for py, px in result):
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
    # 開局國家數完全由 map_config.COUNTRY_COUNT 控制，不再隨地圖面積縮放或強制至少8國。
    count = max(1, int(cfg.COUNTRY_COUNT))
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
        ports = _pick_ports(
            world, territory, country_id, [capital], max(0, int(cfg.PORTS_PER_COUNTRY))
        )
        for y, x in ports:
            settlement[y, x] = PORT
            all_ports.append((country_id, (y, x)))
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
