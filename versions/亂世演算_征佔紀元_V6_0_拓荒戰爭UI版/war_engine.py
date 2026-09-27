"""V5 空間戰爭核心：合法目標、行軍、補給、戰鬥、占領與聯盟援軍。"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path

import numpy as np
from scipy import ndimage

import map_config as cfg
from climate_rules import RIVER
from terrain_rules import HILL, MOUNTAIN, HIGH_MOUNTAIN
from country_generator import CAPITAL, CITY, PORT, BARRACKS, OUTPOST


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
        self.campaigns: list[Campaign] = []
        self.events: list[str] = []
        self.alerts: list[str] = []
        self.country_events: dict[int, list[str]] = {int(c["id"]): [] for c in world.countries}
        self.battles = 0
        self.initial_territory = world.territory.copy()
        self._initialize_local_economy()
        self._initialize_countries()
        self._build_geography()

    def _initialize_local_economy(self):
        land = self.world.territory > 0
        base = (0.35 + self.world.city_value.astype(np.float32) / 100.0)
        self.local_population = np.where(
            land,
            np.maximum(1, np.rint(base * cfg.INITIAL_POPULATION_PER_CELL)),
            0,
        ).astype(np.int32)
        self.food_yield = np.where(land, self.world.agriculture / 100.0, 0).astype(np.float32)
        self.timber_yield = np.where(land, self.world.timber / 100.0, 0).astype(np.float32)
        self.mineral_yield = np.where(land, self.world.minerals / 100.0, 0).astype(np.float32)

    def _initialize_countries(self):
        count = len(self.world.countries)
        self.countries = []
        # 聯盟以地理相近群組初始化，之後援軍仍需自行行軍。
        alliance_size = max(2, math.ceil(count / max(1, cfg.ALLIANCE_COUNT)))
        for country in self.world.countries:
            cid = int(country["id"])
            mask = self.world.territory == cid
            population = int(self.local_population[mask].sum())
            food = float(self.food_yield[mask].sum() * 5.0)
            timber = float(self.timber_yield[mask].sum() * 3.0)
            minerals = float(self.mineral_yield[mask].sum() * 2.0)
            ports = len(country.get("ports", []))
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
                "alliance": 1 + (cid - 1) // alliance_size,
                "wars_won": 0,
                "wars_lost": 0,
                "territory_cells": int(mask.sum()),
                "cities": 0,
                "barracks": 0,
                "outposts": 0,
                "ports": 0,
            })

    def _log(self, cid: int, message: str):
        line = f"第{self.year}年｜{message}"
        bucket = self.country_events.setdefault(int(cid), [])
        bucket.append(line)
        if len(bucket) > 300:
            del bucket[:-300]

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
            if tid == attacker or not target["alive"] or target["alliance"] == source["alliance"]:
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
        self.alerts.append(f"{self.country(defender)['name']}獲報：{a['name']}正集結{soldiers:,}人，預計{years}年抵達。")
        self.events.append(f"第{self.year}年｜{a['name']}向{self.country(defender)['name']}發起{option['mode']}遠征。")
        self._log(attacker, f"向{self.country(defender)['name']}集結{soldiers:,}名士兵，預計{years}年抵達。")
        self._log(defender, f"警報：{a['name']}正集結進攻，預計{years}年抵達。")
        return campaign

    def _economic_year(self):
        ids = self.world.territory.ravel().astype(np.int32, copy=False)
        size = len(self.countries) + 1
        populations = np.bincount(ids, weights=self.local_population.ravel(), minlength=size)
        food_output = np.bincount(ids, weights=self.food_yield.ravel(), minlength=size)
        timber_output = np.bincount(ids, weights=self.timber_yield.ravel(), minlength=size)
        mineral_output = np.bincount(ids, weights=self.mineral_yield.ravel(), minlength=size)
        areas = np.bincount(ids, minlength=size)
        for c in self.countries:
            if not c["alive"]:
                continue
            cid = c["id"]
            if areas[cid] <= 0:
                c["alive"] = False
                continue
            growth = max(0, int(populations[cid] * cfg.ANNUAL_POPULATION_GROWTH))
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
            c["food"] += float(food_output[cid] * 0.90 - c["population"] * 0.18)
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
        per = max(1, int(math.ceil(amount / len(coords))))
        current = self.local_population[coords[:, 0], coords[:, 1]]
        loss = np.minimum(current, per)
        self.local_population[coords[:, 0], coords[:, 1]] -= loss

    def _ai_decisions(self):
        if self.year % cfg.AI_WAR_CHECK_INTERVAL:
            return
        alive = [c for c in self.countries if c["alive"]]
        total_cells = sum(c["territory_cells"] for c in alive) or 1
        hegemons = [c for c in alive if c["territory_cells"] / total_cells >= cfg.COALITION_THREAT_SHARE]
        for hegemon in hegemons:
            candidates = [c for c in alive if c["id"] != hegemon["id"] and c["alliance"] != hegemon["alliance"]
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
            c["territory_cells"] = int(areas[cid])
            c["population"] = int(populations[cid])
            c["soldiers"] = min(c["soldiers"], c["population"])
            if areas[cid] <= 0 or c["population"] <= 0:
                if c["alive"]:
                    self.events.append(f"第{self.year}年｜{c['name']}滅亡。")
                c["alive"] = False
                c["soldiers"] = 0
                c["fleet"] = 0

    def step(self, years: int = 1):
        for _ in range(max(1, int(years))):
            self.year += 1
            self.alerts.clear()
            self._economic_year()
            self._ai_decisions()
            self._advance_campaigns()
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
            "version": "V6_拓荒戰爭UI版",
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
        }
        path.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, world, path: Path):
        path = Path(path)
        payload = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if payload.get("version") != "V6_拓荒戰爭UI版":
            raise ValueError("只支援V6戰爭存檔")
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
        engine.countries = list(payload["countries"])
        engine.campaigns = []
        for raw in payload["campaigns"]:
            raw["origin"] = tuple(raw["origin"])
            raw["objective"] = tuple(raw["objective"])
            engine.campaigns.append(Campaign(**raw))
        engine.events = list(payload.get("events", []))
        engine.country_events = {int(k): list(v) for k, v in payload.get("country_events", {}).items()}
        engine.battles = int(payload.get("battles", 0))
        if payload.get("rng_state"):
            engine.rng.bit_generator.state = payload["rng_state"]
        engine._build_geography()
        return engine
