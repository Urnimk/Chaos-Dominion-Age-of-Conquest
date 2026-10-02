"""V5 空間戰爭核心：合法目標、行軍、補給、戰鬥、占領與聯盟援軍。"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import math
import random
from pathlib import Path

import numpy as np
from scipy import ndimage

import map_config as cfg
from climate_rules import RIVER
from terrain_rules import HILL, MOUNTAIN, HIGH_MOUNTAIN
from country_generator import CAPITAL, CITY, PORT, BARRACKS, OUTPOST


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
    "王", "李", "張", "劉", "陳", "楊", "趙", "黃", "周", "吳", "徐", "孫",
    "朱", "馬", "胡", "郭", "林", "何", "高", "梁", "鄭", "羅", "宋", "謝",
)
ROYAL_GIVEN_NAMES = (
    "景安", "承遠", "世昌", "弘毅", "德昭", "文烈", "武成", "明哲", "元祐", "紹寧",
    "秉鈞", "克勤", "宣和", "建中", "隆泰", "永熙", "昭武", "懷仁", "定邦", "興國",
)

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
                "king_name": surname + given,
                "king_number": 1,
                "king_since_year": self.year,
                "king_next_year": self.year + int(self.rng.integers(cfg.KING_REIGN_MIN_YEARS, cfg.KING_REIGN_MAX_YEARS + 1)),
            })

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
        choices = [name for name in ROYAL_GIVEN_NAMES if country["royal_surname"] + name != previous_name]
        country["king_name"] = country["royal_surname"] + str(self.rng.choice(choices))
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
        for prefix in ("東", "西", "南", "北"):
            if name.startswith(prefix) and len(name) > 1:
                return name[1:]
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
            country["name"] = self._direction_prefix(old_capital, (nx, ny)) + base
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
            eligible = [part for part in parts
                        if part[1] >= cfg.TERRITORY_SPLIT_MIN_CELLS
                        and part[1] / max(1, total) >= cfg.TERRITORY_SPLIT_MIN_SHARE]
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

    def _split_country(self, country: dict, retained: np.ndarray, separated: np.ndarray):
        old_id, new_id = country["id"], len(self.countries) + 1
        old_center = (float(np.argwhere(retained)[:, 1].mean()), float(np.argwhere(retained)[:, 0].mean()))
        new_center = (float(np.argwhere(separated)[:, 1].mean()), float(np.argwhere(separated)[:, 0].mean()))
        dx, dy = new_center[0] - old_center[0], new_center[1] - old_center[1]
        if abs(dx) >= abs(dy):
            old_prefix, new_prefix = (("西", "東") if old_center[0] <= new_center[0] else ("東", "西"))
        else:
            old_prefix, new_prefix = (("北", "南") if old_center[1] <= new_center[1] else ("南", "北"))
        base = country.get("base_name", self._plain_country_name(country["name"]))
        old_name, new_name = old_prefix + base, new_prefix + base
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
        country.update({"name": old_name, "base_name": base, "population": old_pop,
                        "soldiers": original_soldiers - int(round(original_soldiers * share)),
                        "fleet": original_fleet - int(round(original_fleet * share))})
        new_country.update({"id": new_id, "name": new_name, "base_name": base, "alive": True,
                            "capital": [cx, cy], "population": new_pop,
                            "soldiers": int(round(original_soldiers * share)),
                            "fleet": int(round(original_fleet * share)), "alliance": 0,
                            "wars_won": 0, "wars_lost": 0, "territory_cells": int(separated.sum()),
                            "extinction_year": 0, "ever_extinct": False})
        for key in ("food", "timber", "minerals"):
            total_resource = float(country[key])
            new_country[key] = total_resource * share
            country[key] = total_resource - new_country[key]
        self._new_king(country, reset=True, reason="國家分裂後建立新王統")
        self.countries.append(new_country)
        self.country_events[new_id] = []
        self._new_king(new_country, reset=True, reason="國家分裂後建立新王統")
        self._mark_world_changed(old_id, new_id)
        self.world.border = _border_mask(self.world.territory)
        self._build_geography()
        message = f"{base}因領土長期斷裂，分裂為{old_name}與{new_name}。"
        self.events.append(f"第{self.year}年｜{message}")
        self._log(old_id, message); self._log(new_id, message)

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
        self.maritime_links: dict[tuple[int, int], tuple[float, tuple[int, int], tuple[int, int]]] = {}
        if not hasattr(self, "_sea_labels"):
            self._sea_labels, _ = ndimage.label(self.world.terrain <= 1, structure=np.ones((3, 3), dtype=np.uint8))
        countries = self.world.countries
        ports_by_country = {}
        port_seas = {}
        for country in countries:
            cid = int(country["id"])
            py, px = np.where((self.world.settlement == PORT) & (self.world.territory == cid))
            ports_by_country[cid] = [(int(y), int(x)) for y, x in zip(py, px)]
            for y, x in ports_by_country[cid]:
                y0, y1 = max(0, y - 2), min(self.world.settings.height, y + 3)
                xs = [(x + dx) % self.world.settings.width for dx in range(-2, 3)]
                labels = set(int(v) for v in self._sea_labels[y0:y1, :][:, xs].ravel() if int(v) > 0)
                port_seas[(y, x)] = labels
        for i, first in enumerate(countries):
            for second in countries[i + 1:]:
                best = None
                for y1, x1 in ports_by_country[int(first["id"])]:
                    for y2, x2 in ports_by_country[int(second["id"])]:
                        if not (port_seas[(y1, x1)] & port_seas[(y2, x2)]):
                            continue
                        dx = min(abs(x2 - x1), self.world.settings.width - abs(x2 - x1))
                        distance = math.hypot(y2 - y1, dx)
                        if distance <= cfg.NAVAL_OPERATION_RANGE and (best is None or distance < best[0]):
                            best = (distance, (y1, x1), (y2, x2))
                if best:
                    self.maritime_links[(int(first["id"]), int(second["id"]))] = best

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
            key = tuple(sorted((attacker, tid)))
            if key in self.land_contacts:
                result.append({"id": tid, "mode": "land", "distance": 1.0})
            elif key in self.maritime_links and source["fleet"] > 0 and source["fleet"] >= 5:
                result.append({"id": tid, "mode": "naval", "distance": self.maritime_links[key][0]})
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
        link = self.maritime_links.get(tuple(sorted((attacker, defender))))
        if not link:
            return None
        _distance, p1, p2 = link
        return p2 if self.world.territory[p2] == defender else p1

    def _origin(self, attacker: int, defender: int, objective, mode: str):
        if mode == "naval":
            link = self.maritime_links[tuple(sorted((attacker, defender)))]
            return link[1] if self.world.territory[link[1]] == attacker else link[2]
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
        desired = [
            (CITY, "城市", "cities", max(0, area // cfg.CITY_AREA_PER_BUILDING), cfg.CITY_COST),
            (BARRACKS, "兵營", "barracks", max(1, area // cfg.BARRACKS_AREA_PER_BUILDING), cfg.BARRACKS_COST),
            (OUTPOST, "拓荒站", "outposts", max(1, area // cfg.OUTPOST_AREA_PER_BUILDING), cfg.OUTPOST_COST),
        ]
        build = next((item for item in desired if country[item[2]] < item[3] and self._can_pay(country, item[4])), None)
        # 控制沿海領土後，才允許建港與生產艦隊。
        sea = self.world.terrain <= 1
        coast = mask & ndimage.binary_dilation(sea, iterations=1) & ~occupied
        if build is None and country["ports"] == 0 and coast.any() and self._can_pay(country, cfg.PORT_COST):
            coords = np.argwhere(coast)
            scores = self.world.city_value[coords[:, 0], coords[:, 1]]
            y, x = map(int, coords[int(np.argmax(scores))])
            self.world.settlement[y, x] = PORT
            self.visual_revision += 1
            country["ports"] += 1
            country["fleet"] += cfg.INITIAL_FLEET_PER_PORT
            self._pay(country, cfg.PORT_COST)
            self.world.countries[cid - 1].setdefault("ports", []).append([x, y])
            self._log(cid, f"在({x},{y})建成港口，開始建立艦隊。")
            self._build_geography()
            return
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
        for c in alive:
            if self.rng.random() > cfg.AI_BASE_WAR_CHANCE:
                continue
            options = self.legal_targets(c["id"])
            scored = []
            for option in options:
                target = self.country(option["id"])
                ratio = self._country_strength(c["id"]) / max(1.0, self._country_strength(target["id"]))
                resource_value = (target["food"] + target["timber"] + target["minerals"]) / max(1.0, target["population"])
                score = ratio * 2.0 + resource_value * 0.01 - option["distance"] / 900.0 + self.rng.random() * 0.18
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
        return 1.0 + bonus

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
        local_share = min(0.62, 0.22 + len(attackers) * 0.06)
        away = sum(x.soldiers for x in self.campaigns if x.attacker == defender["id"] and x.status == "marching")
        home_soldiers = max(0, defender["soldiers"] - away)
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
        for _ in range(max(1, int(years))):
            self.year += 1
            self.alerts.clear()
            self._economic_year()
            self._update_monarchs()
            self._ai_decisions()
            self._advance_campaigns()
            self._check_territorial_splits()
        return self.summary()

    def summary(self):
        alive = sum(1 for c in self.countries if c["alive"])
        marching = sum(1 for c in self.campaigns if c.status == "marching")
        return {"year": self.year, "alive": alive, "campaigns": marching, "battles": self.battles}

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
        )
        payload = {
            "version": "V7_1_效能優化版",
            "seed": self.world.settings.seed,
            "year": self.year,
            "next_campaign_id": self.next_campaign_id,
            "next_coalition_id": self.next_coalition_id,
            "countries": self.countries,
            "campaigns": [asdict(c) for c in self.campaigns],
            "events": self.events[-500:],
            "battles": self.battles,
            "rng_state": self.rng.bit_generator.state,
            "country_events": self.country_events,
            "alliance_names": self.alliance_names,
            "world_countries": self.world.countries,
            "disconnected_since": self.disconnected_since,
            "visual_revision": self.visual_revision,
        }
        path.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, world, path: Path):
        path = Path(path)
        payload = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if payload.get("version") not in ("V6_拓荒戰爭UI版", "V7_王統分裂與遷都版", "V7_1_效能優化版"):
            raise ValueError("不支援此版本的戰爭存檔")
        if int(payload.get("seed", -1)) != int(world.settings.seed):
            raise ValueError("戰爭存檔與目前世界Seed不一致")
        engine = cls(world, path)
        with np.load(path.with_suffix(".npz")) as data:
            world.territory = data["territory"].copy()
            world.border = data["border"].copy()
            world.settlement = data["settlement"].copy()
            engine.local_population = data["local_population"].copy()
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
            c.setdefault("king_name", defaults.get("king_name", c["royal_surname"] + str(engine.rng.choice(ROYAL_GIVEN_NAMES))))
            c.setdefault("king_number", defaults.get("king_number", 1))
            c.setdefault("king_since_year", defaults.get("king_since_year", engine.year))
            c.setdefault("king_next_year", defaults.get("king_next_year", engine.year + 80))
        engine.campaigns = []
        for raw in payload["campaigns"]:
            raw["origin"] = tuple(raw["origin"])
            raw["objective"] = tuple(raw["objective"])
            engine.campaigns.append(Campaign(**raw))
        engine.events = list(payload.get("events", []))
        engine.country_events = {int(k): list(v) for k, v in payload.get("country_events", {}).items()}
        engine.battles = int(payload.get("battles", 0))
        engine.alliance_names = {int(k): str(v) for k, v in payload.get("alliance_names", engine.alliance_names).items()}
        engine.disconnected_since = {int(k): int(v) for k, v in payload.get("disconnected_since", {}).items()}
        engine.territory_dirty = {int(c["id"]) for c in engine.countries}
        engine._land_totals_dirty = True
        engine.visual_revision = int(payload.get("visual_revision", 0))
        if payload.get("rng_state"):
            engine.rng.bit_generator.state = payload["rng_state"]
        engine._build_geography()
        return engine
