"""V5 空間戰爭核心：合法目標、行軍、補給、戰鬥、占領與聯盟援軍。"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import heapq
import json
import uuid
import math
import random
import copy
import threading
from pathlib import Path

import numpy as np
from scipy import ndimage

import map_config as cfg
from climate_rules import LAKE, RIVER
from terrain_rules import HILL, MOUNTAIN, HIGH_MOUNTAIN, TERRAIN_NAMES
from country_generator import CAPITAL, CITY, PORT, BARRACKS, OUTPOST
from rl_brain import CountryBrain, PASS_ACTION


ALLIANCE_NAME_PREFIXES = [
    "真理","正義","和平","神聖","狂熱","英勇","至高","不朽","榮耀","天譴",
    "極光","創世","黎明","終焉","永恆","烈焰","寒冰","雷霆","風暴","大地",
    "深海","流沙","微風","怒濤","烈日","新月","繁星","熔線","霜狼","蒼穹",
    "黑鐵","白銀","黃金","水晶","秘銀","鋼鐵","赤紅","漆黑","青銅","黑曜",
    "巨石","戰歌","破曉","先鋒","鐵衛","征服","庇護","守護","堅壁","裁決"
]
ALLIANCE_NAME_SUFFIXES = [
    "戰線","憲章","宣言","條約","體系","陣營","安保體系","互助會","同盟會","連線",
    "共識","密約","協議","議定書","盟約","維和部隊","聯合防衛線","合作社","防衛圈",
    "夥伴關係","防衛協議","公約國","戰術聯盟","聯合會"
]

ROYAL_SURNAMES = (
    "馬克", "史密斯", "約翰遜", "威廉斯", "布朗", "瓊斯", "米勒", "戴維斯", "威爾遜", "泰勒",
    "安德森", "托馬斯", "摩爾", "傑克森", "馬丁", "湯普森", "懷特", "哈里斯", "克拉克", "路易斯",
    "沃克", "霍爾", "艾倫", "楊格", "金恩", "萊特", "史考特", "格林", "貝克", "亞當斯",
    "尼爾森", "卡特", "米契爾", "羅伯茲", "菲利普斯", "坎貝爾", "帕克", "埃文斯", "愛德華茲", "柯林斯",
    "史都華", "莫里斯", "羅傑斯", "庫克", "摩根", "貝爾", "墨菲", "貝利", "庫柏", "理查森",
    "馮哈布斯堡", "馮霍亨索倫", "波旁", "瓦盧瓦", "都鐸", "斯圖亞特", "溫莎", "薩伏依", "奧蘭治", "羅曼諾夫",
    "梅迪奇", "斯福爾扎", "維特爾斯巴赫", "韋廷", "格里馬爾迪", "盧森堡", "洛林", "卡佩", "安茹", "巴騰堡",
)
ROYAL_GIVEN_NAMES = (
    "威廉", "亨利", "愛德華", "喬治", "查理", "亞瑟", "理查", "約翰", "詹姆斯", "羅伯特",
    "亞歷山大", "尼可拉斯", "麥可", "大衛", "丹尼爾", "馬修", "安德魯", "湯瑪斯", "班傑明", "克里斯多福",
    "腓力", "路易", "法蘭西斯", "查爾斯", "阿爾伯特", "奧古斯都", "斐迪南", "利奧波德", "腓特烈", "康拉德",
    "奧托", "卡爾", "馬克西米連", "海因里希", "路德維希", "約瑟夫", "彼得", "伊凡", "德米特里", "米哈伊爾",
    "斯特凡", "卡西米爾", "拉迪斯勞", "博萊斯瓦夫", "雅蓋沃", "西吉斯蒙德", "馬提亞斯", "安德拉斯", "貝拉", "拉斯洛",
    "阿方索", "費利佩", "卡洛斯", "費爾南多", "曼努埃爾", "若昂", "佩德羅", "塞巴斯蒂安", "恩里克", "羅德里戈",
    "維克多", "雨果", "朱利安", "安東尼", "雷蒙德", "西蒙", "文森特", "加布里埃爾", "拉斐爾", "塞繆爾",
)

GEOGRAPHIC_ROOTS = (
    "諾亞", "凱撒", "阿卡迪亞", "奧古斯都", "亞歷山大", "赫克托", "雅典娜", "阿波羅", "奧林匹亞", "特洛伊",
    "維多利亞", "阿爾比恩", "卡美洛", "諾曼第", "勃艮第", "洛林", "薩伏依", "巴伐利亞", "薩克森", "普魯士",
    "伊比利亞", "盧西塔尼亞", "卡斯提爾", "亞拉岡", "托斯卡納", "倫巴底", "西西里", "達爾馬提亞", "摩拉維亞", "波希米亞",
    "斯堪地亞", "日德蘭", "諾德", "瓦爾哈拉", "尼伯龍根", "萊茵", "多瑙", "伏爾加", "第聶伯", "塞納",
    "泰晤士", "易北", "羅亞爾", "阿爾卑斯", "庇里牛斯", "喀爾巴阡", "烏拉爾", "亞得里亞", "波羅的", "愛琴",
)
REGION_SUFFIXES = {0: "深海", 1: "淺海", 2: "海岸", 3: "平原", 4: "高地", 5: "山地", 6: "山脈", 7: "湖", 8: "河"}
REGION_QUALIFIERS = ("", "北境", "南境", "東境", "西境", "上游", "下游", "內域", "外域", "晨曦", "暮色", "蒼穹")
STATE_PREFIXES = ("新", "後", "上", "下", "大", "小", "自由", "聯合", "復興", "新生", "北境", "南境", "海東", "海西")

def generate_awesome_alliance_name(rng, is_anti_hegemon=False, target_name=""):
    if is_anti_hegemon and target_name:
        return f"【=反{target_name}聯合戰線=】"
    return f"【={rng.choice(ALLIANCE_NAME_PREFIXES)}{rng.choice(ALLIANCE_NAME_SUFFIXES)}=】"


@dataclass
class Campaign:
    id: int
    attacker: int
    defender: int
    mode: str
    origin: tuple[int, int]
    objective: tuple[int, int]
    soldiers: int
    fleet: int
    distance: float
    years_left: int
    supply: float
    coalition_id: int = 0
    reinforcement_for: int = 0
    status: str = "marching"


def _border_mask(territory: np.ndarray) -> np.ndarray:
    result = np.zeros_like(territory, dtype=np.uint8)
    result[:, 1:] |= ((territory[:, 1:] != territory[:, :-1]) & (territory[:, 1:] > 0))
    result[:, :-1] |= ((territory[:, 1:] != territory[:, :-1]) & (territory[:, :-1] > 0))
    result[1:, :] |= ((territory[1:, :] != territory[:-1, :]) & (territory[1:, :] > 0))
    result[:-1, :] |= ((territory[1:, :] != territory[:-1, :]) & (territory[:-1, :] > 0))
    result[:, 0] |= ((territory[:, 0] != territory[:, -1]) & (territory[:, 0] > 0))
    result[:, -1] |= ((territory[:, 0] != territory[:, -1]) & (territory[:, -1] > 0))
    return result


class WarEngine:
    """一回合等於一年。所有遠征軍必須先在地圖上完成行軍。"""

    def __init__(self, world, state_path: Path | None = None):
        self.world = world
        # Simulation steps and map snapshots share mutable world arrays.
        self._state_lock = threading.RLock()
        self.state_path = Path(state_path) if state_path else None
        self.year = cfg.WAR_START_YEAR
        self.rng = np.random.default_rng(int(world.settings.seed) ^ 0x5A7719)
        self.next_campaign_id = 1
        self.next_coalition_id = 1
        alliance_rng = random.Random(int(world.settings.seed) ^ 0xA11A11CE)
        self.alliance_names = {}
        self._alliance_name_rng = alliance_rng
        self.campaigns: list[Campaign] = []
        self.events: list[str] = []
        self.history_events: list[str] = []
        self.alerts: list[str] = []
        self.country_events: dict[int, list[str]] = {int(c["id"]): [] for c in world.countries}
        self.battles = 0
        self.disconnected_since: dict[int, int] = {}
        self.territory_dirty: set[int] = {int(c["id"]) for c in world.countries}
        self._land_totals_dirty = True
        self._cached_areas = None
        self._cached_food_output = None
        self._cached_timber_output = None
        self._cached_mineral_output = None
        self.visual_revision = 0
        self.initial_territory = world.territory.copy()
        self._initialize_local_economy()
        self._initialize_countries()
        self.rl_brains: dict[int, CountryBrain] = {}
        self._ensure_all_country_brains()
        self._initialize_geographic_regions()
        self.name_prefix_history: dict[str, list[str]] = {}
        alliance_ids = sorted({int(c.get("alliance", 0)) for c in self.countries if int(c.get("alliance", 0)) > 0})
        used = set()
        for aid in alliance_ids:
            for _ in range(200):
                name = generate_awesome_alliance_name(self._alliance_name_rng)
                if name not in used:
                    used.add(name)
                    self.alliance_names[aid] = name
                    break
            else:
                self.alliance_names[aid] = f"【=第{aid}聯盟=】"
        self._build_geography()

    def _initialize_local_economy(self):
        owned = self.world.territory > 0
        productive_land = (self.world.terrain >= 2) & (self.world.movement_cost < 255)
        base = (0.35 + self.world.city_value.astype(np.float32) / 100.0)
        self.local_population = np.where(
            owned,
            np.maximum(1, np.rint(base * cfg.INITIAL_POPULATION_PER_CELL)),
            0,
        ).astype(np.int32)
        # 產能屬於土地本身；拓荒後藉 territory 歸屬立即計入該國。
        self.food_yield = np.where(productive_land, self.world.agriculture / 100.0, 0).astype(np.float32)
        self.timber_yield = np.where(productive_land, self.world.timber / 100.0, 0).astype(np.float32)
        self.mineral_yield = np.where(productive_land, self.world.minerals / 100.0, 0).astype(np.float32)

    def _initialize_geographic_regions(self):
        """讓每個地圖格隸屬一個具名的連續地理區域。"""
        region_class = self.world.terrain.astype(np.int16, copy=True)
        region_class[self.world.water == LAKE] = 7
        region_class[self.world.water == RIVER] = 8
        self.geographic_region_id = np.zeros_like(self.world.terrain, dtype=np.int32)
        self.geographic_regions = []
        next_id = 1
        for code in range(9):
            labels, count = ndimage.label(region_class == code, structure=np.ones((3, 3), dtype=np.uint8))
            if count <= 0:
                continue
            sizes = np.bincount(labels.ravel())
            objects = ndimage.find_objects(labels)
            for label in range(1, count + 1):
                slc = objects[label - 1]
                if slc is None:
                    continue
                local = labels[slc] == label
                yy, xx = np.where(local)
                y0, x0 = slc[0].start, slc[1].start
                root = GEOGRAPHIC_ROOTS[(next_id - 1) % len(GEOGRAPHIC_ROOTS)]
                cycle = (next_id - 1) // len(GEOGRAPHIC_ROOTS)
                # 地名只使用文字修飾詞，不再出現「某某2高地」之類的編號。
                qualifier = REGION_QUALIFIERS[cycle % len(REGION_QUALIFIERS)]
                if cycle >= len(REGION_QUALIFIERS):
                    qualifier += REGION_QUALIFIERS[(cycle // len(REGION_QUALIFIERS)) % len(REGION_QUALIFIERS)]
                root = root + qualifier
                name = root + REGION_SUFFIXES[code]
                self.geographic_region_id[slc][local] = next_id
                self.geographic_regions.append({
                    "id": next_id, "name": name, "type": REGION_SUFFIXES[code],
                    "size": int(sizes[label]),
                    "center": [int(round(x0 + xx.mean())), int(round(y0 + yy.mean()))],
                })
                next_id += 1

    def geographic_name_at(self, y: int, x: int) -> str:
        rid = int(self.geographic_region_id[int(y), int(x)])
        return self.geographic_regions[rid - 1]["name"] if 0 < rid <= len(self.geographic_regions) else "未命名區域"

    def _history(self, category: str, message: str):
        self.history_events.append(f"第{self.year}年｜【{category}】{message}")
        self.history_events = self.history_events[-1000:]

    def _initialize_countries(self):
        self.countries = []
        # 新世界各國獨立開局；結盟留給後續外交決策。
        for country in self.world.countries:
            cid = int(country["id"])
            mask = self.world.territory == cid
            population = int(self.local_population[mask].sum())
            food = float(self.food_yield[mask].sum() * 5.0)
            timber = float(self.timber_yield[mask].sum() * 3.0)
            minerals = float(self.mineral_yield[mask].sum() * 2.0)
            ports = len(country.get("ports", []))
            surname = str(self.rng.choice(ROYAL_SURNAMES))
            given = str(self.rng.choice(ROYAL_GIVEN_NAMES))
            self.countries.append({
                "id": cid,
                "name": country["name"],
                "alive": bool(mask.any()),
                "population": population,
                "soldiers": min(population, max(20, int(population * cfg.INITIAL_SOLDIER_RATIO))),
                "fleet": ports * cfg.INITIAL_FLEET_PER_PORT,
                "food": food,
                "timber": timber,
                "minerals": minerals,
                "morale": 1.0,
                "alliance": 0,
                "wars_won": 0,
                "wars_lost": 0,
                "territory_cells": int(mask.sum()),
                "cities": 0,
                "barracks": 0,
                "outposts": 0,
                "ports": 0,
                "capital": list(country["capital"]),
                "base_name": country["name"],
                "extinction_year": 0,
                "ever_extinct": False,
                "royal_surname": surname,
                "king_name": given + "．" + surname,
                "king_number": 1,
                "king_since_year": self.year,
                "king_next_year": self.year + int(self.rng.integers(cfg.KING_REIGN_MIN_YEARS, cfg.KING_REIGN_MAX_YEARS + 1)),
            "colonies": [],
            "colonization_voyage": None,
            })

    def _ensure_country_brain(self, cid: int):
        """每個國家使用自己的 Q 表與亂數狀態；新分裂國也獲得獨立大腦。"""
        cid = int(cid)
        if cid not in self.rl_brains:
            seed = (int(self.world.settings.seed) * 1_000_003 + cid * 97_409) % (2**63 - 1)
            self.rl_brains[cid] = CountryBrain(seed)

    def _ensure_all_country_brains(self):
        for country in self.countries:
            self._ensure_country_brain(int(country["id"]))

    def _log(self, cid: int, message: str):
        line = f"第{self.year}年｜{message}"
        bucket = self.country_events.setdefault(int(cid), [])
        bucket.append(line)
        if len(bucket) > 300:
            del bucket[:-300]

    def _mark_world_changed(self, *country_ids: int):
        self.territory_dirty.update(int(cid) for cid in country_ids if int(cid) > 0)
        self._land_totals_dirty = True
        self.visual_revision += 1

    def _refresh_land_totals(self):
        size = len(self.countries) + 1
        ids = self.world.territory.ravel().astype(np.int32, copy=False)
        self._cached_areas = np.bincount(ids, minlength=size)
        self._cached_food_output = np.bincount(ids, weights=self.food_yield.ravel(), minlength=size)
        self._cached_timber_output = np.bincount(ids, weights=self.timber_yield.ravel(), minlength=size)
        self._cached_mineral_output = np.bincount(ids, weights=self.mineral_yield.ravel(), minlength=size)
        for cid in list(self.territory_dirty):
            if 0 < cid <= len(self.countries):
                c = self.country(cid)
                owned = self.world.territory == cid
                c["cities"] = int((owned & (self.world.settlement == CITY)).sum())
                c["barracks"] = int((owned & (self.world.settlement == BARRACKS)).sum())
                c["outposts"] = int((owned & (self.world.settlement == OUTPOST)).sum())
                c["ports"] = int((owned & (self.world.settlement == PORT)).sum())
        self._land_totals_dirty = False

    def _new_king(self, country: dict, reset: bool = False, reason: str = "王位更替"):
        previous_name = country.get("king_name", "")
        if reset or not country.get("royal_surname"):
            country["royal_surname"] = str(self.rng.choice(ROYAL_SURNAMES))
        country["king_number"] = 1 if reset else int(country.get("king_number", 0)) + 1
        choices = [name for name in ROYAL_GIVEN_NAMES if name + "．" + country["royal_surname"] != previous_name]
        country["king_name"] = str(self.rng.choice(choices)) + "．" + country["royal_surname"]
        country["king_since_year"] = self.year
        country["king_next_year"] = self.year + int(
            self.rng.integers(cfg.KING_REIGN_MIN_YEARS, cfg.KING_REIGN_MAX_YEARS + 1)
        )
        self._log(country["id"], f"{reason}：第{country['king_number']}任國王{country['king_name']}即位。")

    def _update_monarchs(self):
        for country in self.countries:
            if country["alive"] and self.year >= int(country.get("king_next_year", self.year + 1)):
                self._new_king(country, reason="前王退位／駕崩")

    @staticmethod
    def _plain_country_name(name: str) -> str:
        # 先檢查長前綴，避免「新生」被誤判成單字「新」。
        for prefix in sorted(("東", "西", "南", "北", *STATE_PREFIXES), key=len, reverse=True):
            if name.startswith(prefix) and len(name) > 1:
                return name[len(prefix):]
        return name

    def _direction_prefix(self, origin, destination) -> str:
        ox, oy = origin
        dx = destination[0] - ox
        # 世界左右相接，採最短經度方向。
        if abs(dx) > self.world.settings.width / 2:
            dx = dx - math.copysign(self.world.settings.width, dx)
        dy = destination[1] - oy
        if abs(dx) >= abs(dy):
            return "東" if dx >= 0 else "西"
        return "南" if dy >= 0 else "北"

    def _reserve_prefix(self, base: str, preferred: str) -> str:
        used = self.name_prefix_history.setdefault(base, [])
        options = [preferred, *STATE_PREFIXES]
        prefix = next((item for item in options if item not in used), None)
        if prefix is None:
            prefix = f"新{len(used) + 1}"
        used.append(prefix)
        return prefix

    def _split_prefix_pair(self, base: str, first: str, second: str):
        return self._reserve_prefix(base, first), self._reserve_prefix(base, second)

    def _best_capital_site(self, cid: int):
        cities = np.argwhere((self.world.territory == cid) & (self.world.settlement == CITY))
        if len(cities) < cfg.CAPITAL_RELOCATION_MIN_CITIES:
            return None
        best = None
        for y, x in cities:
            dy = cities[:, 0] - y
            dx = np.minimum(abs(cities[:, 1] - x), self.world.settings.width - abs(cities[:, 1] - x))
            dense = int((dy * dy + dx * dx <= cfg.CAPITAL_RELOCATION_CITY_RADIUS ** 2).sum())
            local_pop = int(self.local_population[int(y), int(x)])
            score = dense * 10000 + local_pop * 10 + int(self.world.city_value[int(y), int(x)])
            if best is None or score > best[0]:
                best = (score, dense, int(x), int(y))
        return best if best and best[1] >= cfg.CAPITAL_RELOCATION_MIN_CITIES else None

    def _resolve_capital_crisis(self, country: dict, conqueror: int | None = None):
        cid = country["id"]
        old_capital = tuple(country.get("capital", self.world.countries[cid - 1]["capital"]))
        ox, oy = old_capital
        if self.world.territory[oy, ox] == cid:
            return False
        remaining = self.world.territory == cid
        remaining_area = int(remaining.sum())
        remaining_population = int(self.local_population[remaining].sum())
        site = self._best_capital_site(cid)
        if (site and remaining_area >= cfg.CAPITAL_RELOCATION_MIN_TERRITORY
                and remaining_population >= cfg.CAPITAL_RELOCATION_MIN_POPULATION):
            _score, _dense, nx, ny = site
            self.world.settlement[remaining & (self.world.settlement == CAPITAL)] = CITY
            self.world.settlement[ny, nx] = CAPITAL
            country["capital"] = [nx, ny]
            meta = self.world.countries[cid - 1]
            meta["capital"] = [nx, ny]
            base = country.get("base_name", self._plain_country_name(country["name"]))
            country["base_name"] = base
            country["name"] = self._reserve_prefix(base, self._direction_prefix(old_capital, (nx, ny))) + base
            meta["name"] = country["name"]
            self._new_king(country, reason="首都失守後由城市議會推舉新王")
            self.visual_revision += 1
            message = f"{country['name']}遷都至({nx},{ny})，政權得以延續。"
            self.events.append(f"第{self.year}年｜{message}")
            self._log(cid, message)
            return True
        self._extinguish_country(country, conqueror, "首都失守且無足夠城市推舉新王")
        return False

    def _extinguish_country(self, country: dict, conqueror: int | None, reason: str):
        if not country.get("alive", False):
            return
        cid = country["id"]
        remaining = self.world.territory == cid
        vanished = int(remaining.sum())
        self.world.territory[remaining] = 0
        self.world.settlement[remaining] = 0
        self.local_population[remaining] = 0
        self._mark_world_changed(cid)
        country.update({
            "alive": False, "ever_extinct": True, "extinction_year": self.year,
            "territory_cells": 0, "population": 0, "soldiers": 0, "fleet": 0,
        })
        for campaign in self.campaigns:
            if campaign.status == "marching" and (campaign.attacker == cid or campaign.defender == cid):
                campaign.status = "cancelled"
        victor = f"；由{self.country(conqueror)['name']}迫使投降" if conqueror else ""
        message = f"{country['name']}滅亡（{reason}{victor}），剩餘{vanished:,}格領土成為無主地。"
        self.events.append(f"第{self.year}年｜{message}")
        self._history("滅亡", message)
        if conqueror:
            winner = self.country(conqueror)
            if winner.get("alive") and winner.get("base_name") == country.get("base_name"):
                self._history("統一", f"{winner['name']}擊敗同源政權{country['name']}，完成國家再統一。")
        self._log(cid, message)
        self.world.border = _border_mask(self.world.territory)
        self._build_geography()

    def _territory_components(self, cid: int):
        coords = np.argwhere(self.world.territory == cid)
        if not len(coords):
            return []
        y0, x0 = coords.min(axis=0)
        y1, x1 = coords.max(axis=0) + 1
        local_owned = self.world.territory[y0:y1, x0:x1] == cid
        labels, count = ndimage.label(
            local_owned,
            structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8),
        )
        if count <= 1:
            return []
        sizes = np.bincount(labels.ravel())[1:]
        return [(int(label), int(sizes[label - 1]), int(y0), int(x0), labels == label)
                for label in np.argsort(sizes)[::-1] + 1]

    def _full_component_mask(self, part) -> np.ndarray:
        _label, _size, y0, x0, local_mask = part
        result = np.zeros_like(self.world.territory, dtype=bool)
        y1, x1 = y0 + local_mask.shape[0], x0 + local_mask.shape[1]
        result[y0:y1, x0:x1] = local_mask
        return result

    def _check_territorial_splits(self):
        if self.year % max(1, cfg.TERRITORY_SPLIT_CHECK_INTERVAL):
            return
        check_ids = set(self.territory_dirty) | set(self.disconnected_since)
        for cid in sorted(check_ids):
            if not (0 < cid <= len(self.countries)):
                continue
            country = self.country(cid)
            cid = country["id"]
            if not country["alive"]:
                self.disconnected_since.pop(cid, None)
                continue
            parts = self._territory_components(cid)
            total = sum(part[1] for part in parts)
            colony_anchors = [tuple(colony["anchor"]) for colony in country.get("colonies", [])]
            def is_colony_part(part):
                _label, _size, y0, x0, local = part
                return any(y0 <= ay < y0 + local.shape[0] and x0 <= ax < x0 + local.shape[1]
                           and local[ay - y0, ax - x0] for ax, ay in colony_anchors)
            eligible = [part for part in parts
                        if part[1] >= cfg.TERRITORY_SPLIT_MIN_CELLS
                        and part[1] / max(1, total) >= cfg.TERRITORY_SPLIT_MIN_SHARE
                        and not is_colony_part(part)]
            if len(eligible) < 2:
                self.disconnected_since.pop(cid, None)
                continue
            since = self.disconnected_since.setdefault(cid, self.year)
            if self.year - since < cfg.TERRITORY_SPLIT_GRACE_YEARS:
                continue
            capital = tuple(country["capital"])
            retained = next((part for part in eligible
                             if part[2] <= capital[1] < part[2] + part[4].shape[0]
                             and part[3] <= capital[0] < part[3] + part[4].shape[1]
                             and part[4][capital[1] - part[2], capital[0] - part[3]]), eligible[0])
            separated = max((part for part in eligible if part[0] != retained[0]), key=lambda p: p[1])
            self._split_country(country, self._full_component_mask(retained), self._full_component_mask(separated))
            self.disconnected_since.pop(cid, None)
        self.territory_dirty.difference_update(check_ids)

    def _split_country(self, country: dict, retained: np.ndarray, separated: np.ndarray,
                       rename_old: bool = True, forced_new_name: str | None = None,
                       reason: str = "領土長期斷裂"):
        old_id, new_id = country["id"], len(self.countries) + 1
        old_center = (float(np.argwhere(retained)[:, 1].mean()), float(np.argwhere(retained)[:, 0].mean()))
        new_center = (float(np.argwhere(separated)[:, 1].mean()), float(np.argwhere(separated)[:, 0].mean()))
        dx, dy = new_center[0] - old_center[0], new_center[1] - old_center[1]
        base = country.get("base_name", self._plain_country_name(country["name"]))
        if rename_old:
            if abs(dx) >= abs(dy):
                old_prefix, new_prefix = (("西", "東") if old_center[0] <= new_center[0] else ("東", "西"))
            else:
                old_prefix, new_prefix = (("北", "南") if old_center[1] <= new_center[1] else ("南", "北"))
            old_prefix, new_prefix = self._split_prefix_pair(base, old_prefix, new_prefix)
            old_name, new_name = old_prefix + base, new_prefix + base
        else:
            old_name = country["name"]
            new_name = forced_new_name or self._reserve_prefix(base, "新") + base
        old_pop = int(self.local_population[retained].sum())
        new_pop = int(self.local_population[separated].sum())
        share = new_pop / max(1, old_pop + new_pop)
        original_soldiers = int(country["soldiers"])
        original_fleet = int(country["fleet"])
        new_country = dict(country)
        self.world.territory[separated] = new_id
        coords = np.argwhere(separated)
        existing_cities = coords[self.world.settlement[coords[:, 0], coords[:, 1]] == CITY]
        choices = existing_cities if len(existing_cities) else coords
        scores = self.world.city_value[choices[:, 0], choices[:, 1]]
        cy, cx = map(int, choices[int(np.argmax(scores))])
        self.world.settlement[cy, cx] = CAPITAL
        color = [int((v + shift) % 176 + 50) for v, shift in zip(self.world.countries[old_id - 1]["color"], (31, 67, 103))]
        self.world.countries.append({"id": new_id, "name": new_name, "color": color,
                                     "capital": [cx, cy], "cities": [], "ports": [],
                                     "territory_cells": int(separated.sum())})
        self.world.countries[old_id - 1]["name"] = old_name
        old_colonies, new_colonies = [], []
        for colony in country.get("colonies", []):
            ax, ay = colony["anchor"]
            (new_colonies if separated[ay, ax] else old_colonies).append(dict(colony))
        country.update({"name": old_name, "base_name": base, "population": old_pop,
                        "soldiers": original_soldiers - int(round(original_soldiers * share)),
                        "fleet": original_fleet - int(round(original_fleet * share)),
                        "colonies": old_colonies})
        new_base = self._plain_country_name(new_name) if not rename_old else base
        new_country.update({"id": new_id, "name": new_name, "base_name": new_base, "alive": True,
                            "capital": [cx, cy], "population": new_pop,
                            "soldiers": int(round(original_soldiers * share)),
                            "fleet": int(round(original_fleet * share)), "alliance": 0,
                            "wars_won": 0, "wars_lost": 0, "territory_cells": int(separated.sum()),
                            "extinction_year": 0, "ever_extinct": False, "colonies": new_colonies,
                            "colonization_voyage": None})
        for key in ("food", "timber", "minerals"):
            total_resource = float(country[key])
            new_country[key] = total_resource * share
            country[key] = total_resource - new_country[key]
        # 舊政權雖改國名，但原國王與剩餘任期保持不變。
        self.countries.append(new_country)
        self._ensure_country_brain(new_id)
        self.country_events[new_id] = []
        self._new_king(new_country, reset=True, reason="國家分裂後建立新王統")
        self._mark_world_changed(old_id, new_id)
        self.world.border = _border_mask(self.world.territory)
        self._build_geography()
        message = f"{base}因{reason}，形成{old_name}與{new_name}。"
        self.events.append(f"第{self.year}年｜{message}")
        self._history("獨立" if not rename_old else "分裂", message)
        self._log(old_id, message); self._log(new_id, message)

    def _check_power_splits(self):
        if self.year % max(1, cfg.POWER_SPLIT_CHECK_INTERVAL):
            return
        ranked = sorted((c for c in self.countries if c["alive"]),
                        key=lambda c: c["territory_cells"], reverse=True)[:cfg.POWER_SPLIT_TOP_RANKS]
        for country in ranked:
            if country["territory_cells"] < cfg.POWER_SPLIT_MIN_TERRITORY or self.rng.random() >= cfg.POWER_SPLIT_CHANCE:
                continue
            cid = country["id"]
            owned = self.world.territory == cid
            coords = np.argwhere(owned)
            if len(coords) < cfg.TERRITORY_SPLIT_MIN_CELLS * 2:
                continue
            axis = 1 if np.ptp(coords[:, 1]) >= np.ptp(coords[:, 0]) else 0
            cut = float(np.median(coords[:, axis]))
            grid = np.indices(owned.shape)[axis]
            first, second = owned & (grid <= cut), owned & (grid > cut)
            cx, cy = country["capital"]
            retained, separated = (first, second) if first[cy, cx] else (second, first)
            if min(int(retained.sum()), int(separated.sum())) < cfg.TERRITORY_SPLIT_MIN_CELLS:
                continue
            self._split_country(country, retained, separated, reason="強盛後爆發低機率王位與地方繼承危機")

    def _colony_context(self):
        neutral = (self.world.territory == 0) & (self.world.terrain >= 2) & (self.world.movement_cost < 255)
        coastal = neutral & ndimage.binary_dilation(self.world.terrain <= 1, iterations=1)
        occupied_continents = set(int(v) for v in np.unique(
            self.world.continent[self.world.territory > 0]
        ) if int(v) > 0)
        return {"neutral": neutral, "coastal": coastal, "occupied_continents": occupied_continents}

    def _colony_country_eligible(self, country: dict) -> bool:
        if (not country["alive"] or country.get("ports", 0) <= 0
                or country["fleet"] < cfg.COLONY_MIN_FLEET
                or country["food"] < cfg.COLONY_FOOD_COST
                or country["timber"] < cfg.COLONY_TIMBER_COST
                or country.get("colonization_voyage")):
            return False
        cid = int(country["id"])
        colonies = []
        for colony in country.get("colonies", []):
            ax, ay = map(int, colony.get("anchor", (-1, -1)))
            if (0 <= ay < self.world.settings.height and 0 <= ax < self.world.settings.width
                    and int(self.world.territory[ay, ax]) == cid):
                colonies.append(colony)
        if len(colonies) >= cfg.COLONY_MAX_PER_COUNTRY:
            return False
        latest_founding = max(
            int(country.get("last_colony_founded_year", -10**9)),
            max((int(colony.get("founded_year", 0)) for colony in colonies), default=-10**9),
        )
        return self.year - latest_founding >= cfg.COLONY_COOLDOWN_YEARS

    @staticmethod
    def _wrapped_distance_cells(first, second, width):
        x0, y0 = first
        x1, y1 = second
        dx = abs(int(x1) - int(x0))
        dx = min(dx, int(width) - dx)
        return math.hypot(dx, int(y1) - int(y0))

    def _water_neighbors(self, x, y):
        height, width = self.world.terrain.shape
        neighbors = []
        for dy in (-1, 0, 1):
            ny = y + dy
            if not 0 <= ny < height:
                continue
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx = (x + dx) % width
                if self.world.terrain[ny, nx] > 1:
                    continue
                if dx and dy:
                    # 船隻不能斜切陸角。
                    if (self.world.terrain[y, nx] > 1
                            or self.world.terrain[ny, x] > 1):
                        continue
                neighbors.append((nx, ny, math.sqrt(2.0) if dx and dy else 1.0))
        return neighbors

    def _sea_route(self, origin_port, target_land):
        """Find a water-only route from a coastal port to the destination island."""
        width, height = self.world.settings.width, self.world.settings.height
        ox, oy = map(int, origin_port)
        tx, ty = map(int, target_land)

        def adjacent_water(point):
            px, py = point
            values = []
            for dy in (-1, 0, 1):
                ny = py + dy
                if not 0 <= ny < height:
                    continue
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx = (px + dx) % width
                    if self.world.terrain[ny, nx] <= 1:
                        values.append((nx, ny))
            return values

        starts, goals = adjacent_water((ox, oy)), set(adjacent_water((tx, ty)))
        if not starts or not goals:
            return None

        def heuristic(point):
            return min(self._wrapped_distance_cells(point, goal, width) for goal in goals)

        frontier = []
        came_from = {}
        cost_so_far = {}
        for start in starts:
            cost_so_far[start] = 1.0
            came_from[start] = None
            heapq.heappush(frontier, (1.0 + heuristic(start), 1.0, start))
        end = None
        max_expansions = 150_000
        expansions = 0
        while frontier and expansions < max_expansions:
            _score, current_cost, current = heapq.heappop(frontier)
            if current_cost != cost_so_far.get(current):
                continue
            if current in goals:
                end = current
                break
            expansions += 1
            for nx, ny, step_cost in self._water_neighbors(*current):
                neighbor = (nx, ny)
                new_cost = current_cost + step_cost
                if new_cost >= cost_so_far.get(neighbor, float("inf")):
                    continue
                cost_so_far[neighbor] = new_cost
                came_from[neighbor] = current
                heapq.heappush(frontier, (new_cost + heuristic(neighbor), new_cost, neighbor))
        if end is None:
            return None

        sea_path = []
        current = end
        while current is not None:
            sea_path.append(current)
            current = came_from[current]
        sea_path.reverse()
        route = [(ox, oy)] + sea_path + [(tx, ty)]
        compact = []
        for point in route:
            if not compact or point != compact[-1]:
                compact.append(point)
        return [[int(x), int(y)] for x, y in compact]

    def _route_distance_km(self, route):
        if len(route) < 2:
            return 0.0
        width = self.world.settings.width
        cell_km = float(cfg.MAP_CELL_SIZE_KM)
        total_cells = 0.0
        for first, second in zip(route, route[1:]):
            total_cells += self._wrapped_distance_cells(first, second, width)
        return total_cells * cell_km

    def _route_position(self, route, travelled_km, cell_size_km=None):
        if not route:
            return None
        if len(route) == 1 or travelled_km <= 0:
            return float(route[0][0]), float(route[0][1])
        remaining = float(travelled_km) / float(cell_size_km or cfg.MAP_CELL_SIZE_KM)
        width = self.world.settings.width
        for first, second in zip(route, route[1:]):
            x0, y0 = map(float, first)
            x1, y1 = map(float, second)
            dx = x1 - x0
            if dx > width / 2:
                dx -= width
            elif dx < -width / 2:
                dx += width
            dy = y1 - y0
            length = math.hypot(dx, dy)
            if length <= 0:
                continue
            if remaining <= length:
                ratio = remaining / length
                return (x0 + dx * ratio) % width, y0 + dy * ratio
            remaining -= length
        x, y = route[-1]
        return float(x), float(y)

    def _colony_candidates(self, country: dict, context: dict) -> np.ndarray:
        if not self._colony_country_eligible(country):
            return np.empty((0, 2), dtype=np.int32)
        cx, cy = country["capital"]
        home_continent = int(self.world.continent[cy, cx])
        candidates = np.argwhere(context["coastal"] & (self.world.continent != home_continent))
        if not len(candidates):
            return candidates
        dy = candidates[:, 0] - cy
        dx = np.minimum(abs(candidates[:, 1] - cx), self.world.settings.width - abs(candidates[:, 1] - cx))
        candidates = candidates[dy * dy + dx * dx >= cfg.COLONY_MIN_DISTANCE ** 2]
        if not len(candidates):
            return candidates
        if cfg.COLONY_PRIORITIZE_EMPTY_ISLANDS:
            empty = np.array([
                int(self.world.continent[y, x]) not in context["occupied_continents"]
                for y, x in candidates
            ], dtype=bool)
            if empty.any():
                candidates = candidates[empty]
        return candidates

    def _found_overseas_colonies(self, selected_country_ids=None, force=False,
                                 deterministic=False, context=None):
        if not force and self.year % max(1, cfg.COLONY_CHECK_INTERVAL):
            return set()
        context = context or self._colony_context()
        neutral = context["neutral"]
        coastal = context["coastal"]
        launched = set()
        for country in list(self.countries):
            cid = int(country["id"])
            if selected_country_ids is not None and cid not in selected_country_ids:
                continue
            if not self._colony_country_eligible(country):
                continue
            if not force and self.rng.random() >= cfg.COLONY_FOUND_CHANCE:
                continue
            candidates = self._colony_candidates(country, context)
            if not len(candidates):
                continue
            values = self.world.city_value[candidates[:, 0], candidates[:, 1]]
            top = candidates[np.argsort(values)[-min(100, len(candidates)):]]
            if deterministic:
                top_values = self.world.city_value[top[:, 0], top[:, 1]]
                ay, ax = map(int, top[int(np.argmax(top_values))])
            else:
                ay, ax = map(int, top[int(self.rng.integers(0, len(top)))])
            # Use an existing coastal port as the departure point; never teleport to the island.
            port_mask = ((self.world.territory == cid)
                         & (self.world.settlement == PORT))
            py, px = np.where(port_mask)
            if not len(px):
                continue
            ports = sorted(
                ((int(x), int(y)) for y, x in zip(py, px)),
                key=lambda point: self._wrapped_distance_cells(
                    point, (ax, ay), self.world.settings.width
                ),
            )
            route = None
            for port in ports[:12]:
                route = self._sea_route(port, (ax, ay))
                if route:
                    break
            if not route:
                continue
            route_distance_km = self._route_distance_km(route)
            if route_distance_km <= 0:
                continue
            if (country["food"] < cfg.COLONY_FOOD_COST
                    or country["timber"] < cfg.COLONY_TIMBER_COST
                    or country["fleet"] < max(cfg.COLONY_MIN_FLEET, cfg.COLONY_TRANSPORT_FLEET)):
                continue
            country["food"] -= cfg.COLONY_FOOD_COST
            country["timber"] -= cfg.COLONY_TIMBER_COST
            country["fleet"] -= cfg.COLONY_TRANSPORT_FLEET
            eta = max(1, math.ceil(route_distance_km / max(0.1, cfg.COLONY_SHIP_SPEED_KM_PER_YEAR)))
            estimated_arrival_year = int(self.year + eta - 1)
            country["colonization_voyage"] = {
                "anchor": [ax, ay],
                "route": route,
                "route_distance_km": route_distance_km,
                "travelled_km": 0.0,
                "position": list(route[0]),
                "launched_year": int(self.year),
                "estimated_arrival_year": estimated_arrival_year,
                "transport_fleet": int(cfg.COLONY_TRANSPORT_FLEET),
                "cell_size_km": float(cfg.MAP_CELL_SIZE_KM),
                "speed_km_per_year": float(cfg.COLONY_SHIP_SPEED_KM_PER_YEAR),
            }
            self.visual_revision += 1
            region = self.geographic_name_at(ay, ax)
            self._log(cid, f"殖民船隊自港口啟航，沿航線前往{region}海岸；航程約{route_distance_km:,.0f}公里，預計於第{estimated_arrival_year}年抵達。")
            launched.add(cid)
        return launched

    def _cancel_colony_voyage(self, country, voyage, reason):
        if country["alive"]:
            country["food"] += float(cfg.COLONY_FOOD_COST)
            country["timber"] += float(cfg.COLONY_TIMBER_COST)
            country["fleet"] += int(voyage.get("transport_fleet", cfg.COLONY_TRANSPORT_FLEET))
        country["colonization_voyage"] = None
        self._log(country["id"], f"殖民船隊航行中止：{reason}；船隊與遠征物資已返還。")
        self.visual_revision += 1

    def _complete_colony_voyage(self, country, voyage):
        cid = int(country["id"])
        ax, ay = map(int, voyage["anchor"])
        if (not country["alive"] or self.world.territory[ay, ax] != 0
                or self.world.terrain[ay, ax] < 2):
            self._cancel_colony_voyage(country, voyage, "目的地已無法登陸")
            return False
        continent_id = int(self.world.continent[ay, ax])
        island_neutral = ((self.world.territory == 0) & (self.world.terrain >= 2)
                          & (self.world.continent == continent_id))
        yy, xx = np.where(island_neutral)
        if not len(xx):
            self._cancel_colony_voyage(country, voyage, "島上已沒有可登陸土地")
            return False
        dx = np.minimum(abs(xx - ax), self.world.settings.width - abs(xx - ax))
        order = np.argsort((yy - ay) ** 2 + dx ** 2)
        max_cells = min(cfg.COLONY_INITIAL_CELLS,
                        cfg.COLONY_SETTLER_POPULATION // max(1, cfg.SETTLER_POPULATION_PER_CELL))
        chosen = np.column_stack((yy[order[:max_cells]], xx[order[:max_cells]])).astype(np.int32)
        moved = self._move_settlers(cid, chosen)
        if moved <= 0:
            self._cancel_colony_voyage(country, voyage, "沒有足夠移民可登陸")
            return False
        chosen = chosen[:moved]
        self.world.territory[chosen[:, 0], chosen[:, 1]] = cid
        country["colonies"].append({
            "id": len(country.get("colonies", [])) + 1,
            "anchor": [ax, ay],
            "founded_year": int(self.year),
            "fleet": int(voyage.get("transport_fleet", cfg.COLONY_TRANSPORT_FLEET)),
        })
        country["last_colony_founded_year"] = int(self.year)
        country["colonization_voyage"] = None
        if cfg.COLONY_AUTO_PORT:
            self.world.settlement[ay, ax] = PORT
            country["ports"] = int(country.get("ports", 0)) + 1
            self.world.countries[cid - 1].setdefault("ports", []).append([ax, ay])
        self._mark_world_changed(cid)
        self.world.border = _border_mask(self.world.territory)
        self._build_geography()
        region = self.geographic_name_at(ay, ax)
        travel_years = max(1, int(self.year) - int(voyage.get("launched_year", self.year)) + 1)
        self._log(cid, f"殖民船隊航行{voyage['route_distance_km']:,.0f}公里、歷時{travel_years}年，抵達{region}海岸並建立殖民地。")
        self._history("殖民", f"{country['name']}的殖民船隊航行至{region}並建立海外殖民地。")
        self.visual_revision += 1
        return True

    def _advance_colony_voyages(self):
        for country in list(self.countries):
            voyage = country.get("colonization_voyage")
            if not voyage:
                continue
            if not country["alive"]:
                self._cancel_colony_voyage(country, voyage, "出航國已滅亡")
                continue
            speed = max(0.0, float(voyage.get("speed_km_per_year", cfg.COLONY_SHIP_SPEED_KM_PER_YEAR)))
            if speed <= 0:
                continue
            voyage.setdefault("cell_size_km", float(cfg.MAP_CELL_SIZE_KM))
            voyage["travelled_km"] = min(
                float(voyage["route_distance_km"]),
                float(voyage.get("travelled_km", 0.0)) + speed,
            )
            # 航程只更新模擬資料；地圖上的航線固定顯示，不逐年重畫移動船標。
            if voyage["travelled_km"] >= float(voyage["route_distance_km"]):
                self._complete_colony_voyage(country, voyage)

    def _check_colony_independence(self):
        if self.year % max(1, cfg.COLONY_INDEPENDENCE_CHECK_INTERVAL):
            return
        for country in list(self.countries):
            if not country["alive"] or not country.get("colonies"):
                continue
            for colony in list(country["colonies"]):
                if self.year - colony["founded_year"] < cfg.COLONY_INDEPENDENCE_MIN_YEARS:
                    continue
                ax, ay = colony["anchor"]
                if self.world.territory[ay, ax] != country["id"]:
                    country["colonies"].remove(colony)
                    continue
                parts = self._territory_components(country["id"])
                target = next((p for p in parts if p[2] <= ay < p[2] + p[4].shape[0]
                               and p[3] <= ax < p[3] + p[4].shape[1]
                               and p[4][ay - p[2], ax - p[3]]), None)
                if target is None:  # 已與本土連成一片，正式整合。
                    country["colonies"].remove(colony)
                    continue
                if target[1] < cfg.TERRITORY_SPLIT_MIN_CELLS or self.rng.random() >= cfg.COLONY_INDEPENDENCE_CHANCE:
                    continue
                separated = self._full_component_mask(target)
                retained = (self.world.territory == country["id"]) & ~separated
                base = self.geographic_name_at(ay, ax)
                existing = {c["name"] for c in self.countries}
                prefix = next((p for p in STATE_PREFIXES if p + base not in existing), f"新{len(self.countries)+1}")
                new_name = prefix + base
                self._split_country(country, retained, separated, rename_old=False,
                                    forced_new_name=new_name, reason="海外殖民地宣告獨立")
                new_country = self.countries[-1]
                new_country["fleet"] += int(colony.get("fleet", 0))
                new_country["colonies"] = []
                country["colonies"] = [
                    c for c in country.get("colonies", [])
                    if c.get("anchor") != colony.get("anchor")
                ]
                break

    def _build_geography(self):
        self.land_contacts: dict[tuple[int, int], list[tuple[int, int]]] = {}
        t = self.world.territory
        pairs = []
        a, b = t[:, 1:], t[:, :-1]
        ys, xs = np.where((a != b) & (a > 0) & (b > 0))
        pairs.extend((int(b[y, x]), int(a[y, x]), (int(y), int(x + 1))) for y, x in zip(ys, xs))
        a, b = t[1:, :], t[:-1, :]
        ys, xs = np.where((a != b) & (a > 0) & (b > 0))
        pairs.extend((int(b[y, x]), int(a[y, x]), (int(y + 1), int(x))) for y, x in zip(ys, xs))
        for c1, c2, point in pairs:
            key = tuple(sorted((c1, c2)))
            bucket = self.land_contacts.setdefault(key, [])
            if len(bucket) < 300:
                bucket.append(point)
        # 單向航線：(攻方, 守方) -> (航程, 攻方港口, 守方沿海登陸點)。
        self.maritime_links: dict[tuple[int, int], tuple[float, tuple[int, int], tuple[int, int]]] = {}
        if not hasattr(self, "_sea_labels"):
            self._sea_labels, _ = ndimage.label(self.world.terrain <= 1, structure=np.ones((3, 3), dtype=np.uint8))
        countries = self.world.countries
        ports_by_country = {}
        coasts_by_country = {}
        sea = self.world.terrain <= 1
        coastal_land = ndimage.binary_dilation(sea, iterations=1) & ~sea
        for country in countries:
            cid = int(country["id"])
            py, px = np.where((self.world.settlement == PORT) & (self.world.territory == cid))
            ports_by_country[cid] = [(int(y), int(x)) for y, x in zip(py, px)]
            cy, cx = np.where(coastal_land & (self.world.territory == cid))
            coasts_by_country[cid] = np.column_stack((cy, cx)).astype(np.int32)
        if cfg.NAVAL_COASTAL_LANDING_ENABLED:
            for first in countries:
                source_id = int(first["id"])
                if not ports_by_country[source_id]:
                    continue
                for second in countries:
                    target_id = int(second["id"])
                    if source_id == target_id or not len(coasts_by_country[target_id]):
                        continue
                    targets = coasts_by_country[target_id]
                    # 大型海岸線均勻取樣，避免每次領土變動造成平方級運算。
                    if len(targets) > 1600:
                        sample = np.linspace(0, len(targets) - 1, 1600, dtype=int)
                        targets = targets[sample]
                    best = None
                    for y1, x1 in ports_by_country[source_id]:
                        dy = targets[:, 0] - y1
                        dx = np.minimum(abs(targets[:, 1] - x1), self.world.settings.width - abs(targets[:, 1] - x1))
                        distances = np.hypot(dy, dx)
                        idx = int(np.argmin(distances))
                        distance = float(distances[idx])
                        if distance <= cfg.NAVAL_OPERATION_RANGE and (best is None or distance < best[0]):
                            y2, x2 = map(int, targets[idx])
                            best = (distance, (y1, x1), (y2, x2))
                    if best:
                        self.maritime_links[(source_id, target_id)] = best
        else:
            for i, first in enumerate(countries):
                for second in countries[i + 1:]:
                    # 舊制保留開關：必須雙方都有港口。
                    if not ports_by_country[int(first["id"])] or not ports_by_country[int(second["id"])]:
                        continue
                    y1, x1 = ports_by_country[int(first["id"])][0]
                    y2, x2 = ports_by_country[int(second["id"])][0]
                    dx = min(abs(x2 - x1), self.world.settings.width - abs(x2 - x1))
                    distance = math.hypot(y2 - y1, dx)
                    if distance <= cfg.NAVAL_OPERATION_RANGE:
                        self.maritime_links[(int(first["id"]), int(second["id"]))] = (distance, (y1, x1), (y2, x2))
                        self.maritime_links[(int(second["id"]), int(first["id"]))] = (distance, (y2, x2), (y1, x1))

    def country(self, cid: int) -> dict:
        return self.countries[cid - 1]

    def legal_targets(self, attacker: int) -> list[dict]:
        source = self.country(attacker)
        if not source["alive"]:
            return []
        result = []
        for target in self.countries:
            tid = target["id"]
            same_alliance = source["alliance"] > 0 and target["alliance"] == source["alliance"]
            if tid == attacker or not target["alive"] or same_alliance:
                continue
            land_key = tuple(sorted((attacker, tid)))
            sea_key = (attacker, tid)
            if land_key in self.land_contacts:
                result.append({"id": tid, "mode": "land", "distance": 1.0})
            elif sea_key in self.maritime_links and source["fleet"] >= 5:
                result.append({"id": tid, "mode": "naval", "distance": self.maritime_links[sea_key][0]})
        return result

    def _country_strength(self, cid: int) -> float:
        c = self.country(cid)
        active = sum(x.soldiers for x in self.campaigns if x.attacker == cid and x.status == "marching")
        return max(0.0, c["soldiers"] - active) * c["morale"] + c["fleet"] * 18.0

    def _objective(self, attacker: int, defender: int, mode: str):
        if mode == "land":
            points = self.land_contacts.get(tuple(sorted((attacker, defender))), [])
            owned = [p for p in points if self.world.territory[p] == defender]
            if not owned:
                owned = points
            if not owned:
                return None
            return owned[int(self.rng.integers(0, len(owned)))]
        link = self.maritime_links.get((attacker, defender))
        if not link:
            return None
        return link[2]

    def _origin(self, attacker: int, defender: int, objective, mode: str):
        if mode == "naval":
            return self.maritime_links[(attacker, defender)][1]
        ys, xs = np.where(self.world.territory == attacker)
        if not len(ys):
            return objective
        sample = np.linspace(0, len(ys) - 1, min(1200, len(ys)), dtype=int)
        dy = ys[sample] - objective[0]
        dx = np.minimum(abs(xs[sample] - objective[1]), self.world.settings.width - abs(xs[sample] - objective[1]))
        idx = sample[int(np.argmin(dy * dy + dx * dx))]
        return int(ys[idx]), int(xs[idx])

    def launch_campaign(self, attacker: int, defender: int, mode: str | None = None,
                        coalition_id: int = 0, reinforcement_for: int = 0) -> Campaign | None:
        options = [x for x in self.legal_targets(attacker) if x["id"] == defender]
        if not options:
            return None
        option = next((x for x in options if mode is None or x["mode"] == mode), None)
        if not option:
            return None
        a = self.country(attacker)
        if sum(1 for x in self.campaigns if x.attacker == attacker and x.status == "marching") >= cfg.AI_MAX_ACTIVE_CAMPAIGNS:
            return None
        committed = sum(x.soldiers for x in self.campaigns if x.attacker == attacker and x.status == "marching")
        available = max(0, a["soldiers"] - int(a["population"] * cfg.MIN_GARRISON_RATIO) - committed)
        soldiers = min(available, max(cfg.AI_MIN_ATTACK_SOLDIERS, int(a["soldiers"] * 0.34)))
        if soldiers < cfg.AI_MIN_ATTACK_SOLDIERS:
            return None
        objective = self._objective(attacker, defender, option["mode"])
        if objective is None:
            return None
        origin = self._origin(attacker, defender, objective, option["mode"])
        dx = min(abs(origin[1] - objective[1]), self.world.settings.width - abs(origin[1] - objective[1]))
        raw_distance = max(1.0, math.hypot(origin[0] - objective[0], dx))
        friction = 1.0 if option["mode"] == "naval" else float(np.clip(self.world.movement_cost[origin], 1, 20)) / 4.0
        distance = raw_distance * max(1.0, friction)
        speed = cfg.SEA_MARCH_CELLS_PER_YEAR if option["mode"] == "naval" else cfg.LAND_MARCH_CELLS_PER_YEAR
        years = max(1, int(math.ceil(distance / speed)))
        supply = soldiers * distance * cfg.SUPPLY_PER_SOLDIER_CELL
        fleet = max(5, int(a["fleet"] * 0.35)) if option["mode"] == "naval" else 0
        campaign = Campaign(self.next_campaign_id, attacker, defender, option["mode"], origin,
                            objective, soldiers, fleet, distance, years, supply,
                            coalition_id, reinforcement_for)
        self.next_campaign_id += 1
        self.campaigns.append(campaign)
        self.visual_revision += 1
        self.alerts.append(f"{self.country(defender)['name']}獲報：{a['name']}正集結{soldiers:,}人，預計{years}年抵達。")
        self.events.append(f"第{self.year}年｜{a['name']}向{self.country(defender)['name']}發起{option['mode']}遠征。")
        self._log(attacker, f"向{self.country(defender)['name']}集結{soldiers:,}名士兵，預計{years}年抵達。")
        self._log(defender, f"警報：{a['name']}正集結進攻，預計{years}年抵達。")
        return campaign

    def _economic_year(self):
        ids = self.world.territory.ravel().astype(np.int32, copy=False)
        size = len(self.countries) + 1
        populations = np.bincount(ids, weights=self.local_population.ravel(), minlength=size)
        if self._land_totals_dirty or self._cached_areas is None or len(self._cached_areas) < size:
            self._refresh_land_totals()
        food_output = self._cached_food_output
        timber_output = self._cached_timber_output
        mineral_output = self._cached_mineral_output
        areas = self._cached_areas
        for c in self.countries:
            if not c["alive"]:
                # 滅亡是不可逆狀態；任何殘留或舊存檔帶回的領土一律清除，杜絕重生。
                stray = self.world.territory == c["id"]
                self.world.territory[stray] = 0
                self.world.settlement[stray] = 0
                self.local_population[stray] = 0
                if stray.any():
                    self._mark_world_changed(c["id"])
                continue
            cid = c["id"]
            if areas[cid] <= 0:
                self._extinguish_country(c, None, "已無有效領土")
                continue
            productivity_bonus = min(
                cfg.MAX_CITY_FOOD_PRODUCTIVITY_BONUS,
                int(c.get("cities", 0)) * cfg.CITY_FOOD_PRODUCTIVITY_BONUS,
            )
            annual_food_output = float(
                food_output[cid] * cfg.FOOD_PRODUCTION_MULTIPLIER * (1.0 + productivity_bonus)
            )
            food_capacity = annual_food_output / max(0.0001, cfg.FOOD_CONSUMPTION_PER_PERSON)
            growth_limit = max(0, int(food_capacity * cfg.FOOD_GROWTH_RESERVE_RATIO - populations[cid]))
            growth = min(
                max(0, int(populations[cid] * cfg.ANNUAL_POPULATION_GROWTH)),
                growth_limit,
            )
            if growth:
                cx, cy = self.world.countries[cid - 1]["capital"]
                if self.world.territory[cy, cx] != cid:
                    owned = np.argwhere(self.world.territory == cid)
                    cy, cx = map(int, owned[len(owned) // 2])
                self.local_population[cy, cx] += growth
            c["population"] = int(populations[cid] + growth)
            c["soldiers"] = min(c["soldiers"], c["population"])
            desired_army = int(c["population"] * 0.18)
            recruits = min(int(c["population"] * cfg.ANNUAL_RECRUIT_RATIO), max(0, desired_army - c["soldiers"]))
            c["soldiers"] += recruits
            annual_food_consumption = float(c["population"] * cfg.FOOD_CONSUMPTION_PER_PERSON)
            annual_food_balance = annual_food_output - annual_food_consumption
            c["last_food_production"] = annual_food_output
            c["last_food_consumption"] = annual_food_consumption
            c["last_food_balance"] = annual_food_balance
            c["food_capacity"] = int(food_capacity)
            c["food"] += annual_food_balance
            c["timber"] += float(timber_output[cid] * 0.42)
            c["minerals"] += float(mineral_output[cid] * 0.24)
            if c["food"] < 0:
                shortage = min(0.025, -c["food"] / max(1.0, c["population"] * 30.0))
                losses = int(c["population"] * shortage)
                self._remove_population(c["id"], losses)
                c["morale"] = max(0.55, c["morale"] - 0.03)
                c["food"] = 0.0
            else:
                c["morale"] = min(1.15, c["morale"] + 0.005)
            c["territory_cells"] = int(areas[cid])

        if self.year % cfg.BUILDING_CHECK_INTERVAL_YEARS == 0:
            for c in self.countries:
                if c["alive"]:
                    self._construct_building(c)
        if self.year % cfg.EXPANSION_INTERVAL_YEARS == 0:
            self._expand_all_countries()

    def _can_pay(self, country, cost):
        return country["food"] >= cost[0] and country["timber"] >= cost[1] and country["minerals"] >= cost[2]

    def _pay(self, country, cost):
        country["food"] -= cost[0]; country["timber"] -= cost[1]; country["minerals"] -= cost[2]

    def _construct_building(self, country):
        cid = country["id"]
        mask = self.world.territory == cid
        area = int(mask.sum())
        if not area:
            return
        occupied = self.world.settlement > 0
        candidates = np.argwhere(mask & ~occupied)
        if not len(candidates):
            return
        sea = self.world.terrain <= 1
        coast = mask & ndimage.binary_dilation(sea, iterations=1) & ~occupied
        port_limit = max(0, int(cfg.PORTS_PER_COUNTRY))
        if (coast.any() and int(country.get("ports", 0)) < port_limit
                and self._can_pay(country, cfg.PORT_COST)):
            coords = np.argwhere(coast)
            scores = self.world.city_value[coords[:, 0], coords[:, 1]]
            y, x = map(int, coords[int(np.argmax(scores))])
            self.world.settlement[y, x] = PORT
            self.visual_revision += 1
            country["ports"] = int(country.get("ports", 0)) + 1
            country["fleet"] += cfg.INITIAL_FLEET_PER_PORT
            self._pay(country, cfg.PORT_COST)
            self.world.countries[cid - 1].setdefault("ports", []).append([x, y])
            self._log(cid, f"在({x},{y})建成港口，開始建立艦隊。")
            self._build_geography()
            return

        port_count = int(country.get("ports", 0))
        fleet_capacity = port_count * int(cfg.FLEET_CAPACITY_PER_PORT)
        if (port_count > 0 and int(country["fleet"]) < fleet_capacity
                and self._can_pay(country, cfg.FLEET_BUILD_COST)):
            ships = min(int(cfg.FLEET_BUILD_BATCH), fleet_capacity - int(country["fleet"]))
            country["fleet"] += ships
            self._pay(country, cfg.FLEET_BUILD_COST)
            self._log(cid, f"港口補充{ships}艘艦艇，現有艦隊{country['fleet']}艘。")
            return

        desired = [
            (CITY, "城市", "cities", max(0, area // cfg.CITY_AREA_PER_BUILDING), cfg.CITY_COST),
            (BARRACKS, "兵營", "barracks", max(1, area // cfg.BARRACKS_AREA_PER_BUILDING), cfg.BARRACKS_COST),
            (OUTPOST, "拓荒站", "outposts", max(1, area // cfg.OUTPOST_AREA_PER_BUILDING), cfg.OUTPOST_COST),
        ]
        build = next((item for item in desired if country[item[2]] < item[3] and self._can_pay(country, item[4])), None)
        if build is None:
            return
        code, label, key, _target, cost = build
        if code == OUTPOST:
            neutral = self.world.territory == 0
            near_frontier = mask & ndimage.binary_dilation(neutral, iterations=1)
            chosen = np.argwhere(near_frontier & ~occupied)
            if len(chosen): candidates = chosen
            score_map = self.world.defense_value
        elif code == BARRACKS:
            score_map = self.world.defense_value
        else:
            score_map = self.world.city_value
        scores = score_map[candidates[:, 0], candidates[:, 1]]
        y, x = map(int, candidates[int(np.argmax(scores))])
        self.world.settlement[y, x] = code
        self.visual_revision += 1
        country[key] += 1
        self._pay(country, cost)
        self._log(cid, f"在({x},{y})建成{label}。")

    def _expand_all_countries(self):
        territory = self.world.territory
        neutral = (territory == 0) & (self.world.terrain >= 2) & (self.world.movement_cost < 255)
        candidates = {c["id"]: set() for c in self.countries if c["alive"]}
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = np.roll(territory, shift=(dy, dx), axis=(0, 1))
            valid = neutral & (neighbor > 0)
            ys, xs = np.where(valid)
            for y, x in zip(ys.tolist(), xs.tolist()):
                cid = int(neighbor[y, x])
                if cid in candidates:
                    candidates[cid].add((y, x))
        changed = False
        for country in self.countries:
            cid = country["id"]
            frontier = list(candidates.get(cid, ()))
            if not frontier:
                continue
            area = int((territory == cid).sum())
            capacity = cfg.INITIAL_TERRITORY_MAX_CELLS + country["soldiers"] * cfg.EXPANSION_CELLS_PER_SOLDIER
            room = max(0, capacity - area)
            amount = min(
                room,
                cfg.BASE_EXPANSION_CELLS + country["cities"] * cfg.CITY_EXPANSION_BONUS
                + country["barracks"] * cfg.BARRACKS_EXPANSION_BONUS
                + country["outposts"] * cfg.OUTPOST_EXPANSION_BONUS,
                int(country["food"] / cfg.EXPANSION_FOOD_COST_PER_CELL),
                int(country["timber"] / cfg.EXPANSION_TIMBER_COST_PER_CELL),
                len(frontier),
            )
            if amount <= 0:
                continue
            coords = np.asarray(frontier, dtype=np.int32)
            score = (self.world.city_value[coords[:, 0], coords[:, 1]] * 0.42
                     + self.world.agriculture[coords[:, 0], coords[:, 1]] * 0.25
                     + self.world.freshwater[coords[:, 0], coords[:, 1]] * 0.18
                     - np.minimum(self.world.movement_cost[coords[:, 0], coords[:, 1]], 20) * 0.8)
            chosen = coords[np.argsort(score)[-amount:]]
            settlers = self._move_settlers(cid, chosen)
            if settlers <= 0:
                continue
            chosen = chosen[:settlers]
            territory[chosen[:, 0], chosen[:, 1]] = cid
            self._mark_world_changed(cid)
            country["food"] -= settlers * cfg.EXPANSION_FOOD_COST_PER_CELL
            country["timber"] -= settlers * cfg.EXPANSION_TIMBER_COST_PER_CELL
            country["territory_cells"] += settlers
            self._log(cid, f"士兵護送移民拓展{settlers}格領土。")
            changed = True
        if changed:
            self.world.border = _border_mask(territory)
            self._build_geography()

    def _move_settlers(self, cid: int, destinations: np.ndarray) -> int:
        needed = len(destinations) * cfg.SETTLER_POPULATION_PER_CELL
        mask = (self.world.territory == cid) & (self.local_population > 1)
        sources = np.argwhere(mask)
        if not len(sources):
            return 0
        order = np.argsort(self.local_population[sources[:, 0], sources[:, 1]])[::-1]
        moved = 0
        for idx in order:
            y, x = map(int, sources[idx])
            take = min(int(self.local_population[y, x] - 1), needed - moved)
            self.local_population[y, x] -= take
            moved += take
            if moved >= needed:
                break
        cells = min(len(destinations), moved // cfg.SETTLER_POPULATION_PER_CELL)
        for y, x in destinations[:cells]:
            self.local_population[int(y), int(x)] = cfg.SETTLER_POPULATION_PER_CELL
        return cells

    def _remove_population(self, cid: int, amount: int):
        if amount <= 0:
            return
        mask = self.world.territory == cid
        coords = np.argwhere(mask & (self.local_population > 0))
        if not len(coords):
            return
        remaining = int(amount)
        order = np.argsort(self.local_population[coords[:, 0], coords[:, 1]])[::-1]
        for idx in order:
            y, x = map(int, coords[idx])
            loss = min(remaining, int(self.local_population[y, x]))
            self.local_population[y, x] -= loss
            remaining -= loss
            if remaining <= 0:
                break

    def _rl_state_and_actions(self, cid: int, colony_available: bool = False):
        """回傳恰有四個離散維度的策略狀態與合法戰爭選項。"""
        country = self.country(cid)
        population = max(1, int(country["population"]))
        soldier_ratio = float(country["soldiers"]) / population
        security_bin = 0 if soldier_ratio < 0.05 else 1 if soldier_ratio < 0.10 else 2 if soldier_ratio < 0.20 else 3

        annual_food_need = max(1.0, population * cfg.FOOD_CONSUMPTION_PER_PERSON)
        food_years = max(0.0, float(country["food"])) / annual_food_need
        food_bin = 0 if food_years < 1.0 else 1 if food_years < 3.0 else 2 if food_years < 8.0 else 3

        total_cells = max(1, sum(int(c["territory_cells"]) for c in self.countries if c["alive"]))
        territory_share = float(country["territory_cells"]) / total_cells
        power_bin = 0 if territory_share < 0.01 else 1 if territory_share < 0.03 else 2 if territory_share < 0.10 else 3

        legal = self.legal_targets(cid)
        target_ratios = {
            int(option["id"]): self._country_strength(cid) / max(1.0, self._country_strength(int(option["id"])))
            for option in legal
        }
        best_ratio = max(target_ratios.values(), default=0.0)
        opportunity_bin = (
            0 if not legal else 1 if best_ratio < 0.75
            else 2 if best_ratio < cfg.AI_MIN_POWER_RATIO else 3
        )
        state = (security_bin, food_bin, power_bin, opportunity_bin)
        actions = [PASS_ACTION]
        action_biases = {PASS_ACTION: 0.0}
        country = self.country(cid)
        active_campaigns = sum(
            1 for campaign in self.campaigns
            if campaign.attacker == cid and campaign.status == "marching"
        )
        committed_soldiers = sum(
            campaign.soldiers for campaign in self.campaigns
            if campaign.attacker == cid and campaign.status == "marching"
        )
        available_soldiers = max(
            0, int(country["soldiers"])
            - int(country["population"] * cfg.MIN_GARRISON_RATIO)
            - committed_soldiers
        )
        can_launch = (
            active_campaigns < cfg.AI_MAX_ACTIVE_CAMPAIGNS
            and available_soldiers >= cfg.AI_MIN_ATTACK_SOLDIERS
        )
        if colony_available:
            action = "COLONIZE"
            actions.append(action)
            action_biases[action] = float(cfg.AI_RL_COLONY_ACTION_BIAS)
        for option in legal:
            target_id = int(option["id"])
            ratio = target_ratios[target_id]
            # 允許承擔適度劣勢；實際勝負由戰區守軍、地形與戰場波動結算。
            if ratio < cfg.AI_MIN_POWER_RATIO or not can_launch:
                continue
            action = f"ATTACK:{target_id}:{option['mode']}"
            actions.append(action)
            prior = float(np.clip((ratio - cfg.AI_MIN_POWER_RATIO) * 0.08, 0.0, 0.12))
            if option["mode"] == "naval":
                prior += float(cfg.AI_RL_NAVAL_ACTION_BIAS)
            action_biases[action] = float(np.clip(prior, 0.0, 0.20))
        return state, actions, action_biases

    @staticmethod
    def _rl_metrics(country: dict) -> dict:
        return {
            "alive": bool(country["alive"]),
            "territory": int(country["territory_cells"]),
            "population": int(country["population"]),
            "food": float(country["food"]),
            "wars_won": int(country["wars_won"]),
            "wars_lost": int(country["wars_lost"]),
        }

    @staticmethod
    def _rl_reward(before: dict, after: dict) -> float:
        if not after.get("alive", False):
            return -4.0
        area_change = math.log1p(max(0, after["territory"])) - math.log1p(max(0, before["territory"]))
        population_change = math.log1p(max(0, after["population"])) - math.log1p(max(0, before["population"]))
        before_food = before["food"] / max(1.0, before["population"] * cfg.FOOD_CONSUMPTION_PER_PERSON)
        after_food = after["food"] / max(1.0, after["population"] * cfg.FOOD_CONSUMPTION_PER_PERSON)
        food_change = float(np.clip(after_food - before_food, -5.0, 5.0))
        war_change = 0.30 * (after["wars_won"] - before["wars_won"]) - 0.40 * (after["wars_lost"] - before["wars_lost"])
        reward = 1.4 * area_change + 0.35 * population_change + 0.10 * food_change + war_change
        return float(np.clip(reward, -4.0, 4.0))

    def _rl_epsilon(self, brain: CountryBrain) -> float:
        fraction = min(1.0, brain.decisions / max(1, cfg.AI_RL_EPSILON_DECAY_DECISIONS))
        return float(cfg.AI_RL_EPSILON + (cfg.AI_RL_MIN_EPSILON - cfg.AI_RL_EPSILON) * fraction)

    def _rl_war_decisions(self, alive: list[dict]):
        colony_due = (
            self.year % max(1, cfg.COLONY_CHECK_INTERVAL) == 0
            and self.year % max(1, cfg.AI_WAR_CHECK_INTERVAL) == 0
        )
        colony_context = self._colony_context() if colony_due else None
        for country in alive:
            cid = int(country["id"])
            brain = self.rl_brains[cid]
            colony_available = bool(
                colony_context is not None and len(self._colony_candidates(country, colony_context))
            )
            state, actions, action_biases = self._rl_state_and_actions(cid, colony_available)
            metrics = self._rl_metrics(country)
            epsilon = self._rl_epsilon(brain)
            if brain.pending:
                previous = brain.pending
                reward = self._rl_reward(previous["metrics"], metrics)
                brain.update(
                    previous["state"], previous["action"], reward,
                    next_state=state, next_actions=actions, epsilon=epsilon,
                    alpha=cfg.AI_RL_ALPHA, gamma=cfg.AI_RL_GAMMA,
                    trace_lambda=cfg.AI_RL_TRACE_LAMBDA,
                    next_action_biases=action_biases,
                )
            action = brain.select_action(state, actions, epsilon, action_biases)
            if action == "COLONIZE":
                founded = self._found_overseas_colonies(
                    selected_country_ids={cid}, force=True,
                    deterministic=True, context=colony_context,
                )
                if cid not in founded:
                    action = PASS_ACTION
            elif action.startswith("ATTACK:"):
                _kind, target_id, mode = action.split(":", 2)
                campaign = self.launch_campaign(cid, int(target_id), mode)
                if campaign:
                    self._dispatch_allied_reinforcements(cid, int(target_id), campaign.id)
                else:
                    action = PASS_ACTION
            brain.pending = {"state": list(state), "action": action, "metrics": metrics}

    def _finalize_extinct_rl_brains(self):
        for country in self.countries:
            cid = int(country["id"])
            brain = self.rl_brains.get(cid)
            if brain is None or not brain.pending or country["alive"]:
                continue
            previous = brain.pending
            brain.update(
                previous["state"], previous["action"],
                self._rl_reward(previous["metrics"], self._rl_metrics(country)),
                alpha=cfg.AI_RL_ALPHA, gamma=cfg.AI_RL_GAMMA,
                trace_lambda=cfg.AI_RL_TRACE_LAMBDA, terminal=True,
            )
            brain.pending = None

    def _ai_decisions(self):
        if self.year % cfg.AI_WAR_CHECK_INTERVAL:
            return
        alive = [c for c in self.countries if c["alive"]]
        total_cells = sum(c["territory_cells"] for c in alive) or 1
        hegemons = [c for c in alive if c["territory_cells"] / total_cells >= cfg.COALITION_THREAT_SHARE]
        for hegemon in hegemons:
            candidates = [c for c in alive if c["id"] != hegemon["id"]
                          and not (c["alliance"] > 0 and c["alliance"] == hegemon["alliance"])
                          and any(t["id"] == hegemon["id"] for t in self.legal_targets(c["id"]))]
            if len(candidates) >= 2 and not any(x.defender == hegemon["id"] and x.coalition_id for x in self.campaigns):
                coalition = self.next_coalition_id
                self.next_coalition_id += 1
                for member in sorted(candidates, key=lambda c: self._country_strength(c["id"]), reverse=True)[:cfg.COALITION_MAX_MEMBERS]:
                    self.launch_campaign(member["id"], hegemon["id"], coalition_id=coalition)
        if str(cfg.AI_MODE).upper() == "SARSA_LAMBDA":
            self._rl_war_decisions(alive)
            return
        for c in alive:
            if self.rng.random() > cfg.AI_BASE_WAR_CHANCE:
                continue
            options = self.legal_targets(c["id"])
            scored = []
            for option in options:
                target = self.country(option["id"])
                ratio = self._country_strength(c["id"]) / max(1.0, self._country_strength(target["id"]))
                resource_value = (target["food"] + target["timber"] + target["minerals"]) / max(1.0, target["population"])
                naval_bonus = cfg.AI_NAVAL_TARGET_BONUS if option["mode"] == "naval" else 0.0
                score = ratio * 2.0 + resource_value * 0.01 - option["distance"] / 900.0 + naval_bonus + self.rng.random() * 0.18
                if ratio >= cfg.AI_MIN_POWER_RATIO:
                    scored.append((score, option))
            if scored:
                _score, choice = max(scored, key=lambda x: x[0])
                campaign = self.launch_campaign(c["id"], choice["id"], choice["mode"])
                if campaign:
                    self._dispatch_allied_reinforcements(c["id"], choice["id"], campaign.id)

    def _dispatch_allied_reinforcements(self, leader: int, defender: int, campaign_id: int):
        alliance = self.country(leader)["alliance"]
        if alliance <= 0:
            return
        for ally in self.countries:
            if ally["id"] == leader or not ally["alive"] or ally["alliance"] != alliance:
                continue
            if any(t["id"] == defender for t in self.legal_targets(ally["id"])):
                sent = self.launch_campaign(ally["id"], defender, reinforcement_for=campaign_id)
                if sent:
                    sent.soldiers = min(sent.soldiers, int(ally["soldiers"] * cfg.ALLIANCE_REINFORCEMENT_RATIO))
                    sent.supply = sent.soldiers * sent.distance * cfg.SUPPLY_PER_SOLDIER_CELL

    def _advance_campaigns(self):
        arrivals = []
        for campaign in self.campaigns:
            if campaign.status != "marching":
                continue
            attacker = self.country(campaign.attacker)
            if not attacker["alive"]:
                campaign.status = "cancelled"
                continue
            yearly_supply = campaign.supply / max(1, campaign.years_left)
            if attacker["food"] >= yearly_supply:
                attacker["food"] -= yearly_supply
            else:
                campaign.soldiers = int(campaign.soldiers * (1.0 - cfg.SUPPLY_SHORTAGE_ATTRITION))
                attacker["food"] = 0.0
            campaign.years_left -= 1
            if campaign.years_left <= 0:
                arrivals.append(campaign)
        # 同一目標、同一聯軍在同年到達者共同結算，但仍各自走完路程。
        handled = set()
        for campaign in arrivals:
            if campaign.id in handled or campaign.status != "marching":
                continue
            group = [campaign]
            if campaign.coalition_id:
                group += [x for x in arrivals if x.id != campaign.id and x.coalition_id == campaign.coalition_id and x.defender == campaign.defender]
            handled.update(x.id for x in group)
            self._battle(group)
        if arrivals:
            self.visual_revision += 1
        # 即時佇列只保留仍在行軍者；歷史結果已寫入事件與戰績，不必逐年反覆掃描。
        self.campaigns = [c for c in self.campaigns if c.status == "marching"]

    def _terrain_defense(self, point) -> float:
        y, x = point
        code = int(self.world.terrain[y, x])
        bonus = float(self.world.defense_value[y, x]) / 250.0
        if code in (MOUNTAIN, HIGH_MOUNTAIN):
            bonus += cfg.MOUNTAIN_DEFENSE_BONUS
        elif code == HILL:
            bonus += cfg.HILL_DEFENSE_BONUS
        if self.world.water[y, x] == RIVER:
            bonus += cfg.RIVER_DEFENSE_BONUS
        settlement = int(self.world.settlement[y, x])
        if settlement == BARRACKS:
            bonus += cfg.BARRACKS_POSITION_DEFENSE_BONUS
        elif settlement == OUTPOST:
            bonus += cfg.OUTPOST_POSITION_DEFENSE_BONUS
        elif settlement in (CITY, CAPITAL):
            bonus += cfg.CITY_POSITION_DEFENSE_BONUS
        return 1.0 + bonus

    def _local_garrison_share(self, defender: dict, point) -> float:
        """Estimate troops available near a battle from local population and barracks."""
        radius = max(1, int(cfg.BARRACKS_BATTLE_RADIUS))
        y, x = map(int, point)
        height, width = self.world.territory.shape
        y_offsets = np.arange(-radius, radius + 1)
        ys = y + y_offsets
        valid_y = (ys >= 0) & (ys < height)
        ys = ys[valid_y]
        dy = y_offsets[valid_y]
        x_offsets = np.arange(-radius, radius + 1)
        xs = (x + x_offsets) % width
        disk = dy[:, None] ** 2 + x_offsets[None, :] ** 2 <= radius ** 2
        region = np.ix_(ys, xs)
        owned = (self.world.territory[region] == int(defender["id"])) & disk
        local_population = int(self.local_population[region][owned].sum())
        barracks = int(((self.world.settlement[region] == BARRACKS) & owned).sum())
        population_share = local_population / max(1, int(defender.get("population", 0)))
        barracks_bonus = min(
            float(cfg.BARRACKS_GARRISON_MAX_BONUS),
            barracks * float(cfg.BARRACKS_GARRISON_SHARE_BONUS),
        )
        share = (
            float(cfg.BATTLE_BASE_GARRISON_SHARE)
            + min(1.0, population_share) * float(cfg.BATTLE_LOCAL_POPULATION_WEIGHT)
            + barracks_bonus
        )
        return float(np.clip(share, 0.10, cfg.BATTLE_MAX_LOCAL_GARRISON_SHARE))

    def _battle(self, attackers: list[Campaign]):
        lead = attackers[0]
        defender = self.country(lead.defender)
        if not defender["alive"]:
            for c in attackers: c.status = "cancelled"
            return
        attack_power = 0.0
        for c in attackers:
            country = self.country(c.attacker)
            modifier = country["morale"]
            if c.mode == "naval":
                modifier *= 1.0 - cfg.AMPHIBIOUS_ATTACK_PENALTY
            attack_power += c.soldiers * modifier
        away = sum(x.soldiers for x in self.campaigns if x.attacker == defender["id"] and x.status == "marching")
        home_soldiers = max(0, defender["soldiers"] - away)
        local_share = self._local_garrison_share(defender, lead.objective)
        local_share = min(
            float(cfg.BATTLE_MAX_LOCAL_GARRISON_SHARE),
            local_share + max(0, len(attackers) - 1) * 0.04,
        )
        defending_soldiers = min(home_soldiers, max(200, int(home_soldiers * local_share)))
        defense_power = defending_soldiers * defender["morale"] * self._terrain_defense(lead.objective)
        attack_power *= self.rng.uniform(1.0 - cfg.BATTLE_RANDOMNESS, 1.0 + cfg.BATTLE_RANDOMNESS)
        defense_power *= self.rng.uniform(1.0 - cfg.BATTLE_RANDOMNESS, 1.0 + cfg.BATTLE_RANDOMNESS)
        attacker_wins = attack_power > defense_power
        total_attackers = max(1, sum(c.soldiers for c in attackers))
        attack_loss_rate = np.clip(0.14 + defense_power / max(attack_power, 1.0) * 0.24, 0.10, 0.72)
        defense_loss_rate = np.clip(0.18 + attack_power / max(defense_power, 1.0) * 0.28, 0.12, 0.88)
        attack_losses = 0
        for c in attackers:
            loss = min(c.soldiers, int(c.soldiers * attack_loss_rate))
            self.country(c.attacker)["soldiers"] = max(0, self.country(c.attacker)["soldiers"] - loss)
            self._remove_population(c.attacker, loss)
            attack_losses += loss
            c.status = "won" if attacker_wins else "lost"
        defense_losses = min(defending_soldiers, int(defending_soldiers * defense_loss_rate))
        defender["soldiers"] = max(0, defender["soldiers"] - defense_losses)
        self._remove_population(defender["id"], defense_losses)
        self.battles += 1
        if attacker_wins:
            winner = max(attackers, key=lambda c: c.soldiers).attacker
            captured = self._capture_area(winner, defender["id"], lead.objective, total_attackers)
            self.country(winner)["wars_won"] += 1
            defender["wars_lost"] += 1
            outcome = f"{self.country(winner)['name']}勝，奪取{captured:,}格"
            self._resolve_capital_crisis(defender, winner)
        else:
            defender["wars_won"] += 1
            for c in attackers:
                self.country(c.attacker)["wars_lost"] += 1
            outcome = f"{defender['name']}守住陣地"
        self.events.append(f"第{self.year}年｜戰役結束：{outcome}；攻方傷亡{attack_losses:,}、守方傷亡{defense_losses:,}。")
        for campaign in attackers:
            self._log(campaign.attacker, f"對{defender['name']}戰役：{outcome}；我軍傷亡約{int(campaign.soldiers * attack_loss_rate):,}。")
        self._log(defender["id"], f"遭受進攻：{outcome}；守軍傷亡{defense_losses:,}。")
        self._refresh_survival()

    def _capture_area(self, winner: int, loser: int, center, soldiers: int) -> int:
        radius = int(np.clip(math.sqrt(max(1, soldiers)) / 5.0, cfg.CAPTURE_RADIUS_MIN, cfg.CAPTURE_RADIUS_MAX))
        y, x = center
        yy, xx = np.ogrid[:self.world.settings.height, :self.world.settings.width]
        dx = np.minimum(abs(xx - x), self.world.settings.width - abs(xx - x))
        disk = (yy - y) ** 2 + dx ** 2 <= radius * radius
        capture = disk & (self.world.territory == loser)
        count = int(capture.sum())
        self.world.territory[capture] = winner
        if count:
            self._mark_world_changed(winner, loser)
        self.world.border = _border_mask(self.world.territory)
        self._build_geography()
        return count

    def _refresh_survival(self):
        ids = self.world.territory.ravel().astype(np.int32, copy=False)
        size = len(self.countries) + 1
        areas = np.bincount(ids, minlength=size)
        populations = np.bincount(ids, weights=self.local_population.ravel(), minlength=size)
        for c in self.countries:
            cid = c["id"]
            if not c["alive"]:
                c["territory_cells"] = 0
                c["population"] = 0
                c["soldiers"] = 0
                c["fleet"] = 0
                continue
            c["territory_cells"] = int(areas[cid])
            c["population"] = int(populations[cid])
            c["soldiers"] = min(c["soldiers"], c["population"])
            if areas[cid] <= 0 or c["population"] <= 0:
                self._extinguish_country(c, None, "領土或人口歸零")

    def step(self, years: int = 1):
        with self._state_lock:
            return self._step_locked(years)

    def _step_locked(self, years: int = 1):
        for _ in range(max(1, int(years))):
            self.year += 1
            self.alerts.clear()
            self._economic_year()
            self._ensure_all_country_brains()
            if str(cfg.AI_MODE).upper() == "SARSA_LAMBDA":
                self._finalize_extinct_rl_brains()
            self._update_monarchs()
            self._ai_decisions()
            if str(cfg.AI_MODE).upper() != "SARSA_LAMBDA":
                self._found_overseas_colonies()
            self._advance_campaigns()
            self._advance_colony_voyages()
            self._check_territorial_splits()
            self._check_power_splits()
            self._check_colony_independence()
        return self.summary()

    def map_render_snapshot(self):
        """Return a consistent map and overlay snapshot for a background renderer."""
        with self._state_lock:
            render_world = copy.copy(self.world)
            # These arrays can change during simulation; static terrain and
            # climate arrays are shared to avoid copying the full world.
            for name in ("territory", "border", "settlement"):
                setattr(render_world, name, getattr(self.world, name).copy())
            render_world.countries = [
                {"id": int(country["id"]), "color": list(country["color"])}
                for country in self.world.countries
            ]

            overlays = {
                "regions": [
                    {"size": int(region["size"]), "center": tuple(region["center"]),
                     "name": str(region["name"])}
                    for region in self.geographic_regions
                ],
                "campaigns": [
                    {"status": campaign.status, "origin": tuple(campaign.origin),
                     "objective": tuple(campaign.objective), "mode": campaign.mode}
                    for campaign in self.campaigns
                ],
                "countries": [
                    {"id": int(country["id"]), "name": str(country["name"]),
                     "capital": tuple(country.get("capital", (0, 0)))}
                    for country in self.countries
                ],
                "voyages": [
                    {"route": [tuple(point) for point in voyage["route"]]}
                    for country in self.countries
                    if (voyage := country.get("colonization_voyage"))
                ],
                "revision": int(self.visual_revision),
            }
            return render_world, overlays

    def summary(self):
        alive = sum(1 for c in self.countries if c["alive"])
        marching = sum(1 for c in self.campaigns if c.status == "marching")
        colonizing = sum(bool(c.get("colonization_voyage")) for c in self.countries)
        return {"year": self.year, "alive": alive, "campaigns": marching,
                "colonizing_voyages": colonizing, "battles": self.battles}

    @staticmethod
    def _rl_brains_path(path: Path) -> Path:
        return path.with_name(f"{path.stem}_rl_brains.json")

    def save(self, path: Path | None = None):
        selected = path or self.state_path
        if selected is None:
            raise ValueError("未指定戰爭存檔路徑")
        path = Path(selected)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path.with_suffix(".npz"),
            territory=self.world.territory,
            border=self.world.border,
            settlement=self.world.settlement,
            local_population=self.local_population,
            geographic_region_id=self.geographic_region_id,
        )
        snapshot_id = uuid.uuid4().hex
        payload = {
            "version": "V13_4_Pygame視窗版",
            "rl_brains_snapshot_id": snapshot_id,
            "seed": self.world.settings.seed,
            "year": self.year,
            "next_campaign_id": self.next_campaign_id,
            "next_coalition_id": self.next_coalition_id,
            "countries": self.countries,
            "campaigns": [asdict(c) for c in self.campaigns],
            "events": self.events[-500:],
            "history_events": self.history_events[-1000:],
            "battles": self.battles,
            "rng_state": self.rng.bit_generator.state,
            "country_events": self.country_events,
            "alliance_names": self.alliance_names,
            "world_countries": self.world.countries,
            "disconnected_since": self.disconnected_since,
            "visual_revision": self.visual_revision,
            "geographic_regions": self.geographic_regions,
            "name_prefix_history": self.name_prefix_history,
        }
        path.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        brain_path = self._rl_brains_path(path)
        brain_payload = {
            "format_version": 1,
            "game_version": "V13_4_Pygame視窗版",
            "snapshot_id": snapshot_id,
            "seed": int(self.world.settings.seed),
            "year": int(self.year),
            "brains": {str(cid): brain.to_dict() for cid, brain in self.rl_brains.items()},
        }
        temporary_brain_path = brain_path.with_suffix(brain_path.suffix + ".tmp")
        temporary_brain_path.write_text(
            json.dumps(brain_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_brain_path.replace(brain_path)

    @classmethod
    def load(cls, world, path: Path):
        path = Path(path)
        payload = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if payload.get("version") not in ("V6_拓荒戰爭UI版", "V7_王統分裂與遷都版", "V7_1_效能優化版", "V7_2_歐洲王室命名版", "V8_地理殖民與政權演化版", "V8_1_地名切換與歷史事件版", "V8_2_本土定位與殖民地連結版", "V8_3_地名歷史連結版", "V8_4_海外登陸戰版", "V9_國家獨立學習AI版", "V10_國家Q表獨立JSON版", "V11_海外擴張學習AI版", "V12_海權與戰區防禦版", "V12_1_本島定位與殖民節奏版", "V13_殖民航線與航行船隊版", "V13_1_十年批次推進版", "V13_2_靜態航線與抵達日誌版", "V13_3_背景地圖渲染版", "V13_4_Pygame視窗版"):
            raise ValueError("不支援此版本的戰爭存檔")
        if int(payload.get("seed", -1)) != int(world.settings.seed):
            raise ValueError("戰爭存檔與目前世界Seed不一致")
        engine = cls(world, path)
        with np.load(path.with_suffix(".npz")) as data:
            world.territory = data["territory"].copy()
            world.border = data["border"].copy()
            world.settlement = data["settlement"].copy()
            engine.local_population = data["local_population"].copy()
            if "geographic_region_id" in data.files:
                engine.geographic_region_id = data["geographic_region_id"].copy()
        engine.year = int(payload["year"])
        engine.next_campaign_id = int(payload["next_campaign_id"])
        engine.next_coalition_id = int(payload["next_coalition_id"])
        initialized = {c["id"]: c for c in engine.countries}
        engine.countries = list(payload["countries"])
        world.countries = list(payload.get("world_countries", world.countries))
        for c in engine.countries:
            defaults = initialized.get(c["id"], {})
            meta = world.countries[c["id"] - 1]
            c.setdefault("capital", list(meta["capital"]))
            c.setdefault("base_name", c["name"])
            c.setdefault("extinction_year", 0)
            c.setdefault("ever_extinct", not bool(c.get("alive", True)))
            c.setdefault("royal_surname", defaults.get("royal_surname", str(engine.rng.choice(ROYAL_SURNAMES))))
            c.setdefault("king_name", defaults.get("king_name", str(engine.rng.choice(ROYAL_GIVEN_NAMES)) + "．" + c["royal_surname"]))
            c.setdefault("king_number", defaults.get("king_number", 1))
            c.setdefault("king_since_year", defaults.get("king_since_year", engine.year))
            c.setdefault("king_next_year", defaults.get("king_next_year", engine.year + 80))
            c.setdefault("colonies", [])
            c.setdefault("colonization_voyage", None)
            if "．" not in str(c.get("king_name", "")):
                c["royal_surname"] = str(engine.rng.choice(ROYAL_SURNAMES))
                c["king_name"] = str(engine.rng.choice(ROYAL_GIVEN_NAMES)) + "．" + c["royal_surname"]
        engine.campaigns = []
        for raw in payload["campaigns"]:
            raw["origin"] = tuple(raw["origin"])
            raw["objective"] = tuple(raw["objective"])
            engine.campaigns.append(Campaign(**raw))
        engine.events = list(payload.get("events", []))
        engine.history_events = list(payload.get("history_events", []))
        engine.country_events = {int(k): list(v) for k, v in payload.get("country_events", {}).items()}
        engine.battles = int(payload.get("battles", 0))
        engine.alliance_names = {int(k): str(v) for k, v in payload.get("alliance_names", engine.alliance_names).items()}
        engine.disconnected_since = {int(k): int(v) for k, v in payload.get("disconnected_since", {}).items()}
        engine.territory_dirty = {int(c["id"]) for c in engine.countries}
        engine._land_totals_dirty = True
        engine.visual_revision = int(payload.get("visual_revision", 0))
        engine.geographic_regions = list(payload.get("geographic_regions", engine.geographic_regions))
        for region in engine.geographic_regions:
            region["name"] = "".join(ch for ch in str(region.get("name", "")) if not ch.isdigit())
        engine.name_prefix_history = {str(k): list(v) for k, v in payload.get("name_prefix_history", {}).items()}
        engine._ensure_all_country_brains()
        # Q 表只從獨立 sidecar 讀取；舊主戰局 JSON 內的 rl_brains 不再使用。
        saved_brains = {}
        brain_path = cls._rl_brains_path(path)
        if payload.get("rl_brains_snapshot_id") and brain_path.exists():
            try:
                brain_payload = json.loads(brain_path.read_text(encoding="utf-8"))
                if (
                    isinstance(brain_payload, dict)
                    and brain_payload.get("format_version") == 1
                    and brain_payload.get("snapshot_id") == payload["rl_brains_snapshot_id"]
                    and int(brain_payload.get("seed", -1)) == int(payload["seed"])
                    and int(brain_payload.get("year", -1)) == int(payload["year"])
                    and isinstance(brain_payload.get("brains"), dict)
                ):
                    saved_brains = brain_payload.get("brains", {})
            except (OSError, ValueError, TypeError, AttributeError):
                # Sidecar 異常或對不上這份戰局時，使用空白大腦，不讀舊內嵌 Q 表。
                pass
        for cid_text, brain_data in saved_brains.items():
            cid = int(cid_text)
            engine._ensure_country_brain(cid)
            engine.rl_brains[cid].load_dict(brain_data)
        if payload.get("rng_state"):
            engine.rng.bit_generator.state = payload["rng_state"]
        engine._build_geography()
        return engine
