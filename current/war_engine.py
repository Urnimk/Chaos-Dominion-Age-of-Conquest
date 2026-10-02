"""V20_2 空間戰爭核心：分區人口與駐軍、艦隊運輸、行軍、占領與增援。"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import heapq
import json
import uuid
import math
import random
from pathlib import Path

import numpy as np
from scipy import ndimage

import map_config as cfg
from climate_rules import LAKE, RIVER
from terrain_rules import HILL, MOUNTAIN, HIGH_MOUNTAIN, TERRAIN_NAMES
from country_generator import CAPITAL, CITY, PORT, BARRACKS, OUTPOST
from rl_brain import CountryBrain, PASS_ACTION, action_kind
from overseas_strategy import OverseasStrategyMixin


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
STATE_PREFIXES = (
    # ===== 原始 1～50 =====
    "新", "後", "上", "下", "大", "小", "自由", "聯合", "復興", "新生",
    "北境", "南境", "海東", "海西", "東方", "西方", "南方", "北方", "中央", "東境",
    "西境", "西北", "東南", "遠東", "遠西", "高原", "山地", "河谷", "沿海", "群島",
    "海上", "大洋", "曙光", "黎明", "永恆", "榮耀", "神聖", "正義", "和平", "獨立",
    "民主", "共和", "王家", "皇室", "帝國", "聯邦", "人民", "統一", "祖國", "新月",

    # ===== 時代／文明 51～90 =====
    "古老", "遠古", "太古", "上古", "中古", "近世", "新世", "盛世", "黃金", "白銀",
    "赤金", "蒼穹", "天空", "天際", "天穹", "星辰", "星海", "星河", "星環", "星耀",
    "星輝", "日耀", "日輪", "日昇", "日落", "月華", "月影", "月輪", "月桂", "月神",
    "晨曦", "晨星", "晨光", "暮光", "暮色", "暮星", "極光", "極夜", "極晝", "極地",

    # ===== 自然／元素 91～140 =====
    "北極", "南極", "冰原", "雪原", "雪域", "冰海", "寒冰", "霜雪", "霜原", "凍土",
    "烈焰", "火焰", "赤焰", "炎陽", "炎龍", "熔岩", "火山", "雷霆", "雷鳴", "迅雷",
    "風暴", "狂風", "疾風", "長風", "雲海", "雲端", "青雲", "白雲", "黑雲", "蒼雲",
    "碧海", "藍海", "滄海", "深海", "瀚海", "海洋", "海灣", "海峽", "海角", "海島",
    "大洋洲", "內海", "外海", "東海", "西海", "南海", "北海", "江南", "江北", "河東",

    # ===== 地理／疆域 141～190 =====
    "河西", "河北", "河南", "湖東", "湖西", "湖南", "湖北", "山東", "山西", "嶺南",
    "嶺北", "關東", "關西", "關中", "塞北", "塞外", "漠北", "漠南", "草原", "荒原",
    "荒漠", "沙海", "沙洲", "綠洲", "森林", "林海", "密林", "雨林", "平原", "丘陵",
    "山岳", "山脈", "峽谷", "盆地", "高地", "低地", "沃土", "豐饒", "富饒", "豐穰",
    "天府", "樂土", "樂園", "聖地", "聖域", "聖城", "聖山", "聖海", "神國", "神州",

    # ===== 神權／天命／帝國感 191～240 =====
    "神域", "神威", "神恩", "神佑", "天命", "天啟", "天選", "天授", "天賜", "天佑",
    "天朝", "天國", "天帝", "天王", "天龍", "龍騰", "龍興", "龍耀", "龍威", "龍旗",
    "龍冠", "鳳凰", "鳳鳴", "麒麟", "玄武", "白虎", "朱雀", "青龍", "蒼龍", "金龍",
    "銀龍", "黑龍", "赤龍", "獅心", "雄獅", "金獅", "銀鷹", "金鷹", "雄鷹", "蒼鷹",
    "戰鷹", "鐵鷹", "鐵血", "鋼鐵", "黑鐵", "赤鐵", "翡翠", "水晶", "琥珀", "瑪瑙",

    # ===== 國家理念／政治 241～280 =====
    "珍珠", "寶石", "紫晶", "青玉", "白玉", "黑曜", "曜石", "光明", "光輝", "光耀",
    "光復", "光榮", "光華", "希望", "理想", "真理", "公義", "公正", "平等", "博愛",
    "自治", "自主", "解放", "革新", "維新", "開明", "進步", "復國", "復古", "復明",
    "中興", "再興", "興國", "興邦", "強國", "富國", "護國", "衛國", "靖國", "安國",

    # ===== 世界／大國風格 281～300 =====
    "定國", "鎮國", "建國", "開國", "創國", "萬國", "天下", "四海", "九州", "五洲",
    "寰宇", "環球", "世界", "國際", "大陸", "海陸", "東陸", "西陸", "南陸", "北陸",
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
    origin_landmass: int = 0
    casualties: int = 0
    transported_population: int = 0
    status: str = "marching"
    tactical_state: tuple[int, ...] | None = None
    tactical_action: str = ""
    sea_route: list | None = None
    embarked_population: int = 0


def _border_mask(territory: np.ndarray) -> np.ndarray:
    result = np.zeros_like(territory, dtype=np.uint8)
    result[:, 1:] |= ((territory[:, 1:] != territory[:, :-1]) & (territory[:, 1:] > 0))
    result[:, :-1] |= ((territory[:, 1:] != territory[:, :-1]) & (territory[:, :-1] > 0))
    result[1:, :] |= ((territory[1:, :] != territory[:-1, :]) & (territory[1:, :] > 0))
    result[:-1, :] |= ((territory[1:, :] != territory[:-1, :]) & (territory[:-1, :] > 0))
    result[:, 0] |= ((territory[:, 0] != territory[:, -1]) & (territory[:, 0] > 0))
    result[:, -1] |= ((territory[:, 0] != territory[:, -1]) & (territory[:, -1] > 0))
    return result


class WarEngine(OverseasStrategyMixin):
    """一回合等於一年。所有遠征軍必須先在地圖上完成行軍。"""

    def __init__(self, world, state_path: Path | None = None):
        self.world = world
        land = (world.terrain >= 2) & (world.continent > 0)
        self._landmass_sizes = np.bincount(
            world.continent[land].astype(np.int32), minlength=int(world.continent.max()) + 1
        )
        self._largest_landmass_size = int(self._landmass_sizes.max(initial=0))
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
        self.building_owner = np.where(
            world.settlement > 0, world.territory, 0
        ).astype(np.int32)
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
        # 軍隊同樣按格網與陸塊分帳；國家總兵力只是這些駐軍加行軍部隊的合計。
        self.local_soldiers = np.zeros_like(self.local_population, dtype=np.int32)
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
            initial_soldiers = min(population, max(20, int(population * cfg.INITIAL_SOLDIER_RATIO)))
            self.countries.append({
                "id": cid,
                "name": country["name"],
                "alive": bool(mask.any()),
                "population": population,
                "soldiers": initial_soldiers,
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
                "frontier_level": 0,
                "ports": 0,
                "capital": list(country["capital"]),
                "capital_type": "本島首都",
                "base_name": country["name"],
                "extinction_year": 0,
                "ever_extinct": False,
                "royal_surname": surname,
                "king_name": given + "．" + surname,
                "king_number": 1,
                "king_since_year": self.year,
                "king_next_year": self.year + int(self.rng.integers(cfg.KING_REIGN_MIN_YEARS, cfg.KING_REIGN_MAX_YEARS + 1)),
                "colonies": [],
                "overseas_capital": None,
                "overseas_capitals": [],
                "overseas_expeditions_used": 0,
                "colonization_voyage": None,
                "reinforcement_voyage": None,
                "retreat_voyage_used": False,
                "war_goal": "UNIFY_WORLD",
                "war_exhaustion": 0.0,
                "recovery_until_year": 0,
                "next_ai_decision_year": self.year + int(self.rng.integers(
                    getattr(cfg, "AI_DECISION_MIN_YEARS", 1),
                    getattr(cfg, "AI_DECISION_MAX_YEARS", 20) + 1,
                )),
                "ai_decision_count": 0,
                "last_ai_action": "",
                "ai_decision_years": [],
            })
            coords = np.argwhere(mask & (self.local_population > 0))
            if len(coords) and initial_soldiers:
                weights = self.local_population[coords[:, 0], coords[:, 1]].astype(np.float64)
                allocation = np.floor(weights / max(1.0, weights.sum()) * initial_soldiers).astype(np.int32)
                remainder = initial_soldiers - int(allocation.sum())
                if remainder:
                    allocation[np.argsort(weights)[-remainder:]] += 1
                self.local_soldiers[coords[:, 0], coords[:, 1]] = allocation

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
        self._territory_epoch = getattr(self, "_territory_epoch", 0) + 1
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

    def _homeland_is_unified(self, country: dict) -> bool:
        """Require 80% homeland control and no other regime before overseas expansion."""
        cid = int(country["id"])
        home = self._home_continent_id(country)
        if home <= 0:
            return False
        island = (self.world.continent == home) & (self.world.terrain >= 2)
        owners = self.world.territory[island]
        return bool(
            owners.size
            and np.count_nonzero(owners == cid) / owners.size
                >= float(cfg.OVERSEAS_REGION_CONTROL_SHARE_REQUIRED)
            and not np.any((owners > 0) & (owners != cid))
        )

    def _relocate_to_overseas_capital(self, country: dict, old_capital):
        """本島城市全失時，把已登記且仍受控的海外首都升為國家首都。"""
        cid = int(country["id"])
        home = int(self.world.continent[int(old_capital[1]), int(old_capital[0])])
        home_cities = ((self.world.territory == cid)
                       & (self.world.continent == home)
                       & (self.world.settlement == CITY))
        if np.any(home_cities):
            return False
        for site in country.get("overseas_capitals", []):
            anchor = site.get("anchor", (-1, -1))
            if len(anchor) != 2:
                continue
            x, y = map(int, anchor)
            if (0 <= y < self.world.settings.height and 0 <= x < self.world.settings.width
                    and int(self.world.territory[y, x]) == cid
                    and int(self.world.continent[y, x]) != home):
                ox, oy = map(int, old_capital)
                if (0 <= oy < self.world.settings.height and 0 <= ox < self.world.settings.width
                        and self.world.settlement[oy, ox] == CAPITAL):
                    self.world.settlement[oy, ox] = CITY
                self.world.settlement[y, x] = CAPITAL
                country["capital"] = [x, y]
                self.world.countries[cid - 1]["capital"] = [x, y]
                self._new_king(country, reason="本島城市全失後由海外首都承接政權")
                self._sync_overseas_capitals(country)
                self.visual_revision += 1
                message = (f"{country['name']}本島已無城市，海外首都遷為新首都"
                           f"({x},{y})，政權延續。")
                self.events.append(f"第{self.year}年｜{message}")
                self._log(cid, message)
                return True
        return False

    def _resolve_capital_crisis(self, country: dict, conqueror: int | None = None):
        cid = country["id"]
        old_capital = tuple(country.get("capital", self.world.countries[cid - 1]["capital"]))
        ox, oy = old_capital
        if self.world.territory[oy, ox] == cid:
            return False
        remaining = self.world.territory == cid
        remaining_area = int(remaining.sum())
        remaining_population = int(self.local_population[remaining].sum())
        if self._relocate_to_overseas_capital(country, old_capital):
            return True
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
        # 建築記錄其興建政權；政權滅亡時，連已被攻佔的原建築也一併拆除。
        built_by_country = self.building_owner == cid
        self.world.settlement[built_by_country] = 0
        self.building_owner[built_by_country] = 0
        self.local_population[remaining] = 0
        self.local_soldiers[remaining] = 0
        self._mark_world_changed(cid)
        country.update({
            "alive": False, "ever_extinct": True, "extinction_year": self.year,
            "territory_cells": 0, "population": 0, "soldiers": 0, "fleet": 0,
            "cities": 0, "barracks": 0, "frontier_level": 0, "ports": 0,
            "colonies": [], "overseas_capital": None, "overseas_capitals": [],
            "colonization_voyage": None,
            "reinforcement_voyage": None,
        })
        if 0 < int(cid) <= len(self.world.countries):
            self.world.countries[int(cid) - 1]["ports"] = []
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

    def _is_small_homeland_fragment(self, part, cid: int, capital_landmass: int) -> bool:
        """Check whether a component is on the capital's landmass and lacks the capital."""
        full = self._full_component_mask(part)
        region_ids = self.world.continent[full]
        region_ids = region_ids[region_ids > 0]
        if not len(region_ids) or capital_landmass <= 0:
            return False
        if int(np.bincount(region_ids).argmax()) != capital_landmass:
            return False

        # Do not let a coast, a neutral cell, or a narrow sea edge exempt a
        # small detached homeland fragment from cleanup. Only registered
        # colonies and components on another landmass are preserved below.
        capital_x, capital_y = map(
            int, self.country(cid).get("capital", self.world.countries[cid - 1]["capital"])
        )
        return not bool(full[capital_y, capital_x])

    def _discard_split_fragment(self, country: dict, fragment: np.ndarray,
                                reason: str = "分裂後領土未達最低比例"):
        """清空未達面積門檻的分裂區塊，並維持原政權的首都與世界資料一致。"""
        cid = int(country["id"])
        cells = int(np.count_nonzero(fragment))
        if cells <= 0:
            return
        self.world.territory[fragment] = 0
        self.world.settlement[fragment] = 0
        self.building_owner[fragment] = 0
        self.local_population[fragment] = 0
        self.local_soldiers[fragment] = 0
        country["colonies"] = [
            colony for colony in country.get("colonies", [])
            if not (0 <= int(colony.get("anchor", (-1, -1))[1]) < fragment.shape[0]
                    and 0 <= int(colony.get("anchor", (-1, -1))[0]) < fragment.shape[1]
                    and fragment[int(colony["anchor"][1]), int(colony["anchor"][0])])
        ]
        country["overseas_capitals"] = [
            site for site in country.get("overseas_capitals", [])
            if not (0 <= int(site.get("anchor", (-1, -1))[1]) < fragment.shape[0]
                    and 0 <= int(site.get("anchor", (-1, -1))[0]) < fragment.shape[1]
                    and fragment[int(site["anchor"][1]), int(site["anchor"][0])])
        ]
        country["overseas_capital"] = (country["overseas_capitals"][0]
                                        if country["overseas_capitals"] else None)
        self._mark_world_changed(cid)
        self.world.border = _border_mask(self.world.territory)
        self._build_geography()
        capital_x, capital_y = map(int, country.get("capital", (0, 0)))
        if int(self.world.territory[capital_y, capital_x]) != cid:
            self._resolve_capital_crisis(country)
        if country.get("alive"):
            self._sync_overseas_capitals(country)
        self._refresh_survival()
        message = (f"{country['name']}因{reason}，釋出{cells:,}格領土為無主空地；"
                   "該區聚落、建築與人口一併清除。")
        self.events.append(f"第{self.year}年｜{message}")
        self._log(cid, message)

    def _check_territorial_splits(self):
        if self.year % max(1, cfg.TERRITORY_SPLIT_CHECK_INTERVAL):
            return
        self._cleanup_overseas_exclaves()
        check_ids = set(self.territory_dirty) | set(self.disconnected_since)
        power_ranked = sorted(
            (c for c in self.countries if c["alive"]),
            key=lambda c: self._country_strength(int(c["id"])), reverse=True,
        )
        protected = {int(c["id"]) for c in power_ranked[:max(0, int(cfg.REGIME_SPLIT_PROTECTED_TOP_RANKS))]}
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
            capital_x, capital_y = map(int, country.get("capital", (0, 0)))
            capital_landmass = int(self.world.continent[capital_y, capital_x])
            def is_overseas_part(part):
                full = self._full_component_mask(part)
                region_ids = self.world.continent[full]
                region_ids = region_ids[region_ids > 0]
                return bool(len(region_ids) and capital_landmass > 0
                            and int(np.bincount(region_ids).argmax()) != capital_landmass)

            # The normal split path ignores tiny components. Periodically clear
            # small detached same-homeland fragments below the one-third
            # threshold, including coastal pieces and fragments of top powers.
            min_fraction = max(0.0, float(getattr(cfg, "TERRITORY_SPLIT_MIN_FRACTION", 1 / 3)))
            if total and min_fraction > 0:
                for part in parts:
                    if (part[1] / total >= min_fraction or is_colony_part(part)
                            or is_overseas_part(part)
                            or not self._is_small_homeland_fragment(part, cid, capital_landmass)):
                        continue
                    self._discard_split_fragment(
                        country, self._full_component_mask(part),
                        reason="本土無首都的小飛地低於最低比例",
                    )
                    total -= part[1]
                    if not country.get("alive"):
                        break
                if not country.get("alive"):
                    self.disconnected_since.pop(cid, None)
                    continue
                if total != sum(part[1] for part in parts):
                    parts = self._territory_components(cid)
                    total = sum(part[1] for part in parts)
            if cid in protected:
                # 海外領土造成的地理分隔不應被誤認為本土政權分裂。
                self.disconnected_since.pop(cid, None)
                continue
            eligible = [part for part in parts
                        if part[1] >= cfg.TERRITORY_SPLIT_MIN_CELLS
                        and part[1] / max(1, total) >= cfg.TERRITORY_SPLIT_MIN_SHARE
                        and not is_colony_part(part) and not is_overseas_part(part)]
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
        # 分裂門檻以「分裂前整個政權」為母體計算，不再用 retained+separated
        # 的局部總和計算，避免第三塊飛地存在時把比例灌水。
        original_cells = int(np.count_nonzero(self.world.territory == int(country["id"])))
        min_fraction = max(0.0, float(getattr(cfg, "TERRITORY_SPLIT_MIN_FRACTION", 0.25)))
        retained_cells = int(np.count_nonzero(retained))
        separated_cells = int(np.count_nonzero(separated))
        min_cells = max(int(getattr(cfg, "TERRITORY_SPLIT_MIN_CELLS", 12)),
                        int(math.ceil(original_cells * min_fraction)))
        if original_cells and min_fraction > 0:
            if retained_cells < min_cells:
                self._discard_split_fragment(country, retained)
                return
            if separated_cells < min_cells:
                self._discard_split_fragment(country, separated)
                return
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
        inherited_buildings = separated & (self.building_owner == old_id)
        self.building_owner[inherited_buildings] = new_id
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
        old_sites, new_sites = [], []
        for site in country.get("overseas_capitals", []):
            ax, ay = site.get("anchor", (-1, -1))
            if 0 <= int(ay) < separated.shape[0] and 0 <= int(ax) < separated.shape[1]:
                (new_sites if separated[int(ay), int(ax)] else old_sites).append(dict(site))
        country.update({"name": old_name, "base_name": base, "population": old_pop,
                        "soldiers": original_soldiers - int(round(original_soldiers * share)),
                        "fleet": original_fleet - int(round(original_fleet * share)),
                        "colonies": old_colonies, "overseas_capitals": old_sites,
                        "overseas_capital": old_sites[0] if old_sites else None})
        new_base = self._plain_country_name(new_name) if not rename_old else base
        new_country.update({"id": new_id, "name": new_name, "base_name": new_base, "alive": True,
                            "capital": [cx, cy], "population": new_pop,
                            "soldiers": int(round(original_soldiers * share)),
                            "fleet": int(round(original_fleet * share)), "alliance": 0,
                            "wars_won": 0, "wars_lost": 0, "territory_cells": int(separated.sum()),
                            "extinction_year": 0, "ever_extinct": False, "colonies": new_colonies,
                            "overseas_capitals": new_sites,
                            "overseas_capital": new_sites[0] if new_sites else None,
                            "overseas_expeditions_used": len(new_sites),
                            "colonization_voyage": None,
                            "reinforcement_voyage": None,
                             "ai_decision_years": []})
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
                        key=lambda c: self._country_strength(int(c["id"])), reverse=True)
        protected = {int(c["id"]) for c in ranked[:max(0, int(cfg.REGIME_SPLIT_PROTECTED_TOP_RANKS))]}
        ranked = [c for c in ranked[:cfg.POWER_SPLIT_TOP_RANKS] if int(c["id"]) not in protected]
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
        epoch = getattr(self, "_territory_epoch", 0)
        if getattr(self, "_colony_epoch", -1) == epoch:
            return self._colony_cached
        self._colony_epoch = epoch
        self._colony_cached = self._colony_context_uncached()
        return self._colony_cached

    def _colony_context_uncached(self):
        neutral = (self.world.territory == 0) & (self.world.terrain >= 2) & (self.world.movement_cost < 255)
        coastal = neutral & ndimage.binary_dilation(self.world.terrain <= 1, iterations=1)
        occupied_continents = set(int(v) for v in np.unique(
            self.world.continent[self.world.territory > 0]
        ) if int(v) > 0)
        return {
            "neutral": neutral, "coastal": coastal,
            "occupied_continents": occupied_continents,
            "major_landmasses": self._major_landmass_ids(),
        }

    def _clear_small_late_game_landmasses(self):
        # V22: valid inhabited islands are never deleted by an age/area timer.
        return False

    def _cleanup_overseas_exclaves(self):
        signature = (getattr(self, "_territory_epoch", 0), tuple(
            (c["id"], tuple(c.get("capital", ())), tuple(tuple(s.get("anchor", ()))
            for s in c.get("overseas_capitals", []))) for c in self.countries if c.get("alive")))
        if getattr(self, "_cleanup_signature", None) == signature:
            return False
        result = self._cleanup_overseas_exclaves_uncached()
        self._cleanup_signature = signature
        return result

    def _cleanup_overseas_exclaves_uncached(self):
        """Clear detached overseas land that has no valid overseas capital anchor."""
        changed_ids = set()
        for country in self.countries:
            if not country.get("alive"):
                continue
            cid = int(country["id"])
            home = self._home_continent_id(country)
            owned = self.world.territory == cid
            overseas_ids = {int(v) for v in np.unique(self.world.continent[owned])
                            if int(v) > 0 and int(v) != home}
            anchors_by_land = {}
            for record in list(country.get("overseas_capitals", [])) + list(country.get("colonies", [])):
                ax, ay = map(int, record.get("anchor", (-1, -1)))
                if (0 <= ay < self.world.settings.height and 0 <= ax < self.world.settings.width
                        and int(self.world.territory[ay, ax]) == cid):
                    land = int(self.world.continent[ay, ax])
                    if land > 0 and land != home:
                        anchors_by_land.setdefault(land, set()).add((ay, ax))
            clearing = np.zeros_like(self.world.territory, dtype=bool)
            for land in overseas_ids:
                region_owned = owned & (self.world.continent == land)
                anchors = anchors_by_land.get(land, set())
                if not anchors:
                    clearing |= region_owned
                    continue
                ys,xs = np.where(region_owned)
                if not len(xs):
                    continue
                y0,y1=int(ys.min()),int(ys.max())+1
                width=self.world.settings.width
                wrap=bool(np.any(xs==0) and np.any(xs==width-1))
                x0,x1=(0,width) if wrap else (int(xs.min()),int(xs.max())+1)
                patch=region_owned[y0:y1,x0:x1]
                if wrap:patch=np.concatenate((patch,patch,patch),axis=1)
                labels,_=ndimage.label(patch,structure=np.array([[0,1,0],[1,1,1],[0,1,0]],dtype=np.uint8))
                if wrap:labels=labels[:,width:2*width]
                keep={int(labels[y-y0,x-x0]) for y,x in anchors if int(labels[y-y0,x-x0])>0}
                clearing[y0:y1,x0:x1] |= region_owned[y0:y1,x0:x1] & ~np.isin(labels,tuple(keep))
            cells = int(clearing.sum())
            if not cells:
                continue
            self.world.territory[clearing] = 0
            self.world.settlement[clearing] = 0
            self.building_owner[clearing] = 0
            self.local_population[clearing] = 0
            self.local_soldiers[clearing] = 0
            def anchor_survives(record):
                anchor = record.get("anchor", (-1, -1))
                if len(anchor) != 2:
                    return False
                ax, ay = map(int, anchor)
                return 0 <= ay < clearing.shape[0] and 0 <= ax < clearing.shape[1] and not clearing[ay, ax]
            country["colonies"] = [r for r in country.get("colonies", []) if anchor_survives(r)]
            country["overseas_capitals"] = [r for r in country.get("overseas_capitals", []) if anchor_survives(r)]
            country["overseas_capital"] = country["overseas_capitals"][0] if country["overseas_capitals"] else None
            changed_ids.add(cid)
            self._log(cid, f"定期清理沒有海外首都的飛地，釋出{cells:,}格土地。")
        if not changed_ids:
            return False
        self._mark_world_changed(*changed_ids)
        self.world.border = _border_mask(self.world.territory)
        self._build_geography()
        for cid in changed_ids:
            self._sync_overseas_capitals(self.country(cid))
        self._refresh_survival()
        # This housekeeping is deliberately omitted from history_events.
        self.events.append(f"第{self.year}年｜定期清理無海外首都飛地。")
        return True

    def _home_continent_id(self, country: dict) -> int:
        """目前本土首都所在大陸；海外據點不以殖民港所在大陸作為母國大陸。"""
        cid = int(country["id"])
        x, y = map(int, country.get("capital", self.world.countries[cid - 1]["capital"]))
        if 0 <= y < self.world.settings.height and 0 <= x < self.world.settings.width:
            return int(self.world.continent[y, x])
        return 0

    def _major_landmass_ids(self) -> set[int]:
        """依可調門檻辨識適合海外擴張的大陸／大島。"""
        threshold = max(
            int(cfg.OVERSEAS_MAJOR_LANDMASS_MIN_CELLS),
            int(self._largest_landmass_size * float(cfg.OVERSEAS_MAJOR_LANDMASS_LARGEST_RATIO)),
        )
        return {
            i for i, size in enumerate(self._landmass_sizes)
            if i > 0 and int(size) >= threshold
        }

    def _preferred_landmass_ids(self, landmass_ids) -> list[int]:
        return sorted(
            {int(i) for i in landmass_ids if int(i) > 0},
            key=lambda i: int(self._landmass_sizes[i]), reverse=True,
        )[:max(1, int(cfg.OVERSEAS_PREFERRED_LANDMASS_COUNT))]

    def _homeland_is_critical(self, country: dict) -> bool:
        """只在本土幾近失守時，允許 AI 把小島當作海外後撤據點。"""
        cid = int(country["id"])
        home = self._home_continent_id(country)
        if home <= 0:
            return False
        home_mask = self.world.continent == home
        initial = int(np.count_nonzero((self.initial_territory == cid) & home_mask))
        remaining = int(np.count_nonzero((self.world.territory == cid) & home_mask))
        threshold = min(
            int(cfg.OVERSEAS_RETREAT_HOME_MAX_CELLS),
            max(1, int(initial * float(cfg.OVERSEAS_RETREAT_INITIAL_HOME_SHARE))),
        )
        capital = country.get("capital", self.world.countries[cid - 1]["capital"])
        cx, cy = map(int, capital)
        capital_survives = (
            0 <= cy < self.world.settings.height
            and 0 <= cx < self.world.settings.width
            and int(self.world.territory[cy, cx]) == cid
            and int(self.world.settlement[cy, cx]) == CAPITAL
        )
        home_cities = int(np.count_nonzero(
            home_mask & (self.world.territory == cid) & (self.world.settlement == CITY)
        ))
        last_capital_crisis = (
            remaining < int(cfg.OVERSEAS_RETREAT_LAST_CAPITAL_MAX_CELLS)
            and capital_survives and home_cities == 0
        )
        return remaining <= threshold or last_capital_crisis

    def _overseas_landmass_is_pacified(self, country: dict, landmass_id: int) -> bool:
        """海外陸塊由本國控制至少八成，且沒有其他國家政權時，視為平定。"""
        cid = int(country["id"])
        land = (self.world.continent == int(landmass_id)) & (self.world.terrain >= 2)
        total = int(np.count_nonzero(land))
        if total <= 0:
            return False
        owned = int(np.count_nonzero(land & (self.world.territory == cid)))
        regimes = set(int(v) for v in np.unique(self.world.territory[land]) if int(v) > 0)
        required = float(getattr(cfg, "OVERSEAS_REGION_CONTROL_SHARE_REQUIRED", 0.80))
        return owned / total >= required and regimes == {cid}

    def _overseas_expansion_ready(self, country: dict) -> bool:
        """有海外領地時，必須先平定所有已持有的海外陸塊才能再向外擴張。"""
        landmasses = self._overseas_landmass_ids(country)
        return all(self._overseas_landmass_is_pacified(country, i) for i in landmasses)

    def _overseas_expansion_capacity(self, country: dict) -> int:
        """本土統一後先給一格；每平定一塊海外大陸，再解鎖一格。"""
        if (bool(getattr(cfg, "OVERSEAS_EXPANSION_REQUIRES_HOMELAND_UNIFIED", True))
                and not self._homeland_is_unified(country)):
            return 0
        home = self._home_continent_id(country)
        major_overseas = {i for i, size in enumerate(self._landmass_sizes)
                          if i > 0 and size >= cfg.OVERSEAS_COLONY_MIN_LANDMASS_CELLS} - {home}
        if not major_overseas:
            return 0
        initial = max(1, int(getattr(cfg, "OVERSEAS_INITIAL_EXPEDITION_SLOTS", 1)))
        pacified = sum(
            self._overseas_landmass_is_pacified(country, i)
            for i in (self._overseas_landmass_ids(country) & major_overseas)
        )
        return min(len(major_overseas), initial + pacified)

    def _major_overseas_site_count(self, country: dict) -> int:
        return len(self._overseas_landmass_ids(country))

    def _reserved_overseas_landmasses(self, country: dict) -> set[int]:
        """把航行中殖民船與已出征的海上戰役計入名額，避免同年超額派遣。"""
        cid = int(country["id"])
        home = self._home_continent_id(country)
        major = {i for i, size in enumerate(self._landmass_sizes)
                 if i > 0 and size >= cfg.OVERSEAS_COLONY_MIN_LANDMASS_CELLS} - {home}
        owned = self._overseas_landmass_ids(country)
        reserved = set()
        voyage = country.get("colonization_voyage")
        if voyage:
            ax, ay = map(int, voyage.get("anchor", (-1, -1)))
            if 0 <= ay < self.world.settings.height and 0 <= ax < self.world.settings.width:
                landmass = int(self.world.continent[ay, ax])
                if landmass in major and landmass not in owned:
                    reserved.add(landmass)
        for campaign in self.campaigns:
            if campaign.attacker != cid or campaign.status != "marching" or campaign.mode != "naval":
                continue
            y, x = map(int, campaign.objective)
            if 0 <= y < self.world.settings.height and 0 <= x < self.world.settings.width:
                landmass = int(self.world.continent[y, x])
                if landmass in major and landmass not in owned:
                    reserved.add(landmass)
        return reserved

    def _overseas_landmass_ids(self, country: dict) -> set[int]:
        cid = int(country["id"])
        owned = self.world.territory == cid
        landmasses = set(int(v) for v in np.unique(self.world.continent[owned]) if int(v) > 0)
        home = self._home_continent_id(country)
        landmasses.discard(home)
        return landmasses

    def _overseas_site_count(self, country: dict) -> int:
        """以實際持有的海外大陸數計數，殖民與征服同一大陸只算一處。"""
        landmasses = self._overseas_landmass_ids(country)
        registered = set()
        for site in country.get("overseas_capitals", []):
            anchor = site.get("anchor", (-1, -1))
            if len(anchor) != 2:
                continue
            x, y = map(int, anchor)
            if (0 <= y < self.world.settings.height and 0 <= x < self.world.settings.width
                    and int(self.world.territory[y, x]) == int(country["id"])):
                continent = int(self.world.continent[y, x])
                if continent > 0 and continent != self._home_continent_id(country):
                    registered.add(continent)
        legacy = country.get("overseas_capital")
        if legacy and not country.get("overseas_capitals"):
            x, y = map(int, legacy.get("anchor", (-1, -1)))
            if (0 <= y < self.world.settings.height and 0 <= x < self.world.settings.width
                    and int(self.world.territory[y, x]) == int(country["id"])):
                continent = int(self.world.continent[y, x])
                if continent > 0 and continent != self._home_continent_id(country):
                    registered.add(continent)
        # 舊存檔中已控制、但沒有海外首都紀錄的飛地也占用名額，載入時會補設首都。
        return max(len(landmasses), len(registered))

    def _sync_overseas_capitals(self, country: dict):
        """Keep only valid recorded overseas capitals; never invent one for an orphan enclave."""
        cid = int(country["id"])
        home = self._home_continent_id(country)
        owned = self.world.territory == cid
        landmasses = self._overseas_landmass_ids(country)
        sites = list(country.get("overseas_capitals", []))
        # 舊 V15 的單一征服首都升級為多據點清單。
        legacy = country.get("overseas_capital")
        if legacy and not sites:
            sites.append(dict(legacy))
        for colony in country.get("colonies", []):
            anchor = colony.get("anchor", (-1, -1))
            if len(anchor) == 2:
                x, y = map(int, anchor)
                if 0 <= y < self.world.settings.height and 0 <= x < self.world.settings.width:
                    continent = int(self.world.continent[y, x])
                    if continent > 0 and continent != home:
                        sites.append({
                            "anchor": [x, y], "continent_id": continent,
                            "founded_year": int(colony.get("founded_year", self.year)),
                            "type": "海外殖民首都",
                        })
        valid = {}
        for site in sites:
            anchor = site.get("anchor", (-1, -1))
            if len(anchor) != 2:
                continue
            x, y = map(int, anchor)
            if (not (0 <= y < self.world.settings.height and 0 <= x < self.world.settings.width)
                    or int(self.world.territory[y, x]) != cid):
                continue
            continent = int(self.world.continent[y, x])
            retreat_base = str(site.get("type", "")) in ("後撤基地", "撤退", "緊急後撤")
            if (continent <= 0 or (continent not in landmasses and not retreat_base)
                    or (continent == home and not retreat_base)
                    or (continent != home and retreat_base)):
                continue
            site["continent_id"] = continent
            legacy_type = str(site.get("type", ""))
            if legacy_type in ("征服", "征服首都", "海外"):
                site["type"] = "海外征戰首都"
            elif legacy_type in ("殖民", "殖民首都"):
                site["type"] = "海外殖民首都"
            elif legacy_type in ("撤退", "緊急後撤"):
                site["type"] = "後撤基地"
            valid.setdefault(continent, site)
        country["overseas_capitals"] = list(valid.values())
        country["overseas_capital"] = country["overseas_capitals"][0] if valid else None
        # Keep colony links attached to the actual owned coast if a war takes their old anchor.
        for colony in country.get("colonies", []):
            old = colony.get("anchor", (-1, -1))
            x, y = map(int, old)
            if (not (0 <= y < self.world.settings.height and 0 <= x < self.world.settings.width)
                    or int(self.world.territory[y, x]) != cid):
                colony["lost"] = True
        country["colonies"] = [c for c in country.get("colonies", []) if not c.get("lost")]

    def _overseas_expeditions_used(self, country: dict) -> int:
        if "overseas_expeditions_used" in country:
            return max(0, int(country.get("overseas_expeditions_used", 0)))
        # 舊存檔以已存在據點、殖民地及在途船隊推回最低已用次數。
        known_sites = max(
            len(country.get("colonies", [])),
            len(country.get("overseas_capitals", [])),
            int(bool(country.get("overseas_capital"))),
        )
        return min(
            int(cfg.OVERSEAS_EXPEDITION_LIMIT),
            known_sites + int(bool(country.get("colonization_voyage"))),
        )

    def _can_launch_overseas_expedition(self, country: dict, landmass_id: int | None = None) -> bool:
        # V20.3: overseas_expeditions_used is historical telemetry, not a lifetime lock.
        # Failed expeditions must not permanently remove a country's ability to pursue world unification.
        capacity = self._overseas_expansion_capacity(country)
        if capacity <= 0:
            return False
        # 已經落腳的海外陸塊遭到侵入時，仍可出兵平亂，不受新擴張名額與80%門檻阻擋。
        if landmass_id is not None and int(landmass_id) in self._overseas_landmass_ids(country):
            return True
        owned_sites = self._major_overseas_site_count(country)
        reserved = self._reserved_overseas_landmasses(country)
        return (
            self._overseas_expansion_ready(country)
            and (landmass_id is None or int(landmass_id) not in reserved)
            and owned_sites + len(reserved) < capacity
        )

    def _colony_country_eligible(self, country: dict) -> bool:
        retreat = self._homeland_is_critical(country)
        if (not country["alive"] or country.get("ports", 0) <= 0
                or (bool(getattr(cfg, "OVERSEAS_EXPANSION_REQUIRES_HOMELAND_UNIFIED", True))
                    and not self._homeland_is_unified(country) and not retreat)
                or (not retreat and self.year < int(country.get("recovery_until_year", 0)))
                or country["fleet"] < max(cfg.OVERSEAS_MIN_FLEET, cfg.COLONY_MIN_FLEET)
                or country["food"] < cfg.COLONY_FOOD_COST
                or country["timber"] < cfg.COLONY_TIMBER_COST
                or country.get("colonization_voyage")
                or (retreat and country.get("retreat_voyage_used", False))
                or (not retreat and not self._can_launch_overseas_expedition(country))
                ):
            return False
        cid = int(country["id"])
        colonies = []
        for colony in country.get("colonies", []):
            ax, ay = map(int, colony.get("anchor", (-1, -1)))
            if (0 <= ay < self.world.settings.height and 0 <= ax < self.world.settings.width
                    and int(self.world.territory[ay, ax]) == cid):
                colonies.append(colony)
        if (not retreat and len(colonies) >= self._overseas_expansion_capacity(country)):
            return False
        if retreat:
            return True
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
        key = (tuple(origin_port), tuple(target_land))
        cache = getattr(self, "_sea_route_cache", None)
        if cache is None:
            cache = self._sea_route_cache = {}
        if key not in cache:
            cache[key] = self._sea_route_uncached(origin_port, target_land)
        return cache[key]

    def _sea_route_uncached(self, origin_port, target_land):
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
        # 先排除任何已有國家領土的整塊陸地，避免其無主海岸搶走無人島的優先序。
        empty_ids = {
            int(self.world.continent[y, x]) for y, x in candidates
            if int(self.world.continent[y, x]) not in context["occupied_continents"]
        }
        if not empty_ids:
            return np.empty((0, 2), dtype=np.int32)
        candidates = candidates[np.array([
            int(self.world.continent[y, x]) in empty_ids for y, x in candidates
        ], dtype=bool)]
        candidate_ids = {int(self.world.continent[y, x]) for y, x in candidates}
        major_ids = candidate_ids & set(context.get("major_landmasses", self._major_landmass_ids()))
        # 緊急後撤優先小島；一般殖民另依可殖民面積門檻挑選無人陸塊。
        if self._homeland_is_critical(country):
            small_ids = candidate_ids - set(context.get("major_landmasses", self._major_landmass_ids()))
            eligible_ids = set(self._preferred_landmass_ids(small_ids))
            if not eligible_ids:
                return np.empty((0, 2), dtype=np.int32)
        else:
            # 平時也可前往合格的無人小島殖民；只排除過小地塊，避免全被大陸國家占有時永遠沒有殖民目標。
            min_cells = max(
                int(cfg.MIN_ISLAND_AREA),
                int(getattr(cfg, "OVERSEAS_COLONY_MIN_LANDMASS_CELLS", 300)),
            )
            colonizable_ids = {
                landmass for landmass in candidate_ids
                if int(self._landmass_sizes[landmass]) >= min_cells
            }
            eligible_ids = set(self._preferred_landmass_ids(colonizable_ids))
            if not eligible_ids:
                return np.empty((0, 2), dtype=np.int32)
        candidates = candidates[np.array([
            int(self.world.continent[y, x]) in eligible_ids for y, x in candidates
        ], dtype=bool)]
        if not len(candidates):
            return candidates
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
                         & (self.world.settlement == PORT)
                         & (self.world.continent == self._home_continent_id(country)))
            py, px = np.where(port_mask)
            if not len(px):
                continue
            ports = sorted(
                ((int(x), int(y)) for y, x in zip(py, px)),
                key=lambda point: self._wrapped_distance_cells(
                    point, (ax, ay), self.world.settings.width
                ),
            )
            retreat = self._homeland_is_critical(country)
            if retreat:
                radius = max(1, int(getattr(cfg, "OVERSEAS_RETREAT_PORT_THREAT_RADIUS", 4)))
                enemy_y, enemy_x = np.where((self.world.territory > 0) & (self.world.territory != cid))
                safe_ports = []
                for port_x, port_y in ports:
                    if len(enemy_x):
                        dx = np.minimum(np.abs(enemy_x - port_x), self.world.settings.width - np.abs(enemy_x - port_x))
                        dy = np.abs(enemy_y - port_y)
                        if np.any(dx * dx + dy * dy <= radius * radius):
                            continue
                    safe_ports.append((port_x, port_y))
                ports = safe_ports
                if not ports:
                    continue
            if not force:
                if retreat:
                    radius = max(1, int(getattr(cfg, "OVERSEAS_RETREAT_PORT_THREAT_RADIUS", 4)))
                    enemy_cells = (self.world.territory > 0) & (self.world.territory != cid)
                    enemy_y, enemy_x = np.where(enemy_cells)
                    safe_ports = 0
                    threatened_ports = 0
                    for port_x, port_y in ports:
                        if len(enemy_x):
                            dx = np.minimum(np.abs(enemy_x - port_x), self.world.settings.width - np.abs(enemy_x - port_x))
                            dy = np.abs(enemy_y - port_y)
                            threatened = bool(np.any(dx * dx + dy * dy <= radius * radius))
                        else:
                            threatened = False
                        threatened_ports += int(threatened)
                        safe_ports += int(not threatened)
                    chance = float(getattr(cfg, "OVERSEAS_RETREAT_BASE_CHANCE", 0.35))
                    chance += min(0.10, max(0, int(country.get("fleet", 0))) / 5000.0)
                    chance += 0.08 if safe_ports else 0.0
                    chance -= 0.18 if not safe_ports and threatened_ports else 0.0
                    chance = float(np.clip(chance, 0.10, 0.62))
                else:
                    chance = float(cfg.COLONY_FOUND_CHANCE)
                if self.rng.random() >= chance:
                    continue
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
            retreat = self._homeland_is_critical(country)
            home = self._home_continent_id(country)
            home_population = int(self.local_population[
                (self.world.territory == cid) & (self.world.continent == home)
            ].sum())
            transported_population = (int(home_population * 0.80) if retreat
                                     else int(home_population * 0.25))
            transported_population = min(transported_population, max(0, home_population - self._home_soldiers(cid, home)))
            transported_soldiers = (int(self._home_soldiers(cid) * 0.80) if retreat else 0)
            transport_fleet = max(
                int(cfg.COLONY_TRANSPORT_FLEET),
                int(math.ceil(transported_population / max(1, int(cfg.OVERSEAS_POPULATION_PER_SHIP)))),
                int(math.ceil(transported_soldiers / max(1, int(cfg.OVERSEAS_SOLDIERS_PER_SHIP)))),
            )
            if (country["fleet"] < cfg.OVERSEAS_MIN_FLEET
                    or country["food"] < cfg.COLONY_FOOD_COST
                    or country["timber"] < cfg.COLONY_TIMBER_COST
                    or country["fleet"] < max(cfg.COLONY_MIN_FLEET, transport_fleet)
                    or (not retreat and self._transport_population_capacity(transport_fleet) < transported_population)):
                continue
            initial_supply = transported_population * cfg.FOOD_CONSUMPTION_PER_PERSON * cfg.OVERSEAS_SUPPLY_BUFFER_YEARS
            if country["food"] < cfg.COLONY_FOOD_COST + initial_supply:
                continue
            transport_fleet = max(transport_fleet, int(math.ceil(initial_supply / cfg.OVERSEAS_FOOD_PER_SHIP)))
            if transport_fleet > country["fleet"]:
                continue
            source_mask = ((self.world.territory == cid) & (self.world.continent == home))
            embarked_people = self._remove_population_in_mask(source_mask, transported_population)
            if embarked_people != transported_population:
                hx, hy = country["capital"]
                self.local_population[hy, hx] += embarked_people
                continue
            country["food"] -= cfg.COLONY_FOOD_COST + initial_supply
            country["timber"] -= cfg.COLONY_TIMBER_COST
            country["fleet"] -= transport_fleet
            if not retreat:
                country["overseas_expeditions_used"] = self._overseas_expeditions_used(country) + 1
            else:
                country["retreat_voyage_used"] = True
            country["colonization_voyage"] = {
                "anchor": [ax, ay],
                "route": route,
                "route_distance_km": route_distance_km,
                "travelled_km": 0.0,
                "position": list(route[0]),
                "launched_year": int(self.year),
                "transport_fleet": int(transport_fleet),
                "transported_population": int(transported_population),
                "embarked_population": True,
                "initial_supply": initial_supply,
                "transported_soldiers": int(transported_soldiers),
                "cell_size_km": float(cfg.MAP_CELL_SIZE_KM),
                "speed_km_per_year": float(cfg.COLONY_SHIP_SPEED_KM_PER_YEAR),
                "retreat": bool(retreat),
            }
            self.visual_revision += 1
            region = self.geographic_name_at(ay, ax)
            eta = max(1, math.ceil(route_distance_km / max(0.1, cfg.COLONY_SHIP_SPEED_KM_PER_YEAR)))
            voyage_name = "緊急後撤船隊" if retreat else "殖民船隊"
            self._log(cid, f"{voyage_name}自港口啟航，沿航線前往{region}；航程約{route_distance_km:,.0f}公里，預計{eta}年抵達。")
            launched.add(cid)
        return launched

    def _cancel_colony_voyage(self, country, voyage, reason):
        if country["alive"]:
            country["food"] += float(cfg.COLONY_FOOD_COST) + float(voyage.get("initial_supply",0))
            country["timber"] += float(cfg.COLONY_TIMBER_COST)
            country["fleet"] += int(voyage.get("transport_fleet", cfg.COLONY_TRANSPORT_FLEET))
            if voyage.get("embarked_population"):
                hx, hy = country["capital"]
                self.local_population[hy, hx] += int(voyage.get("transported_population", 0))
        country["colonization_voyage"] = None
        if voyage.get("retreat"):
            country["retreat_voyage_used"] = False
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
        retreat = bool(voyage.get("retreat", False))
        if retreat:
            if not self._homeland_is_critical(country):
                country["retreat_voyage_used"] = False
                self._cancel_colony_voyage(country, voyage, "本島危局已解除")
                return False
            transported = int(voyage.get("transported_population", 0))
            max_cells = min(len(order), max(1, int(math.ceil(transported / max(1, cfg.SETTLER_POPULATION_PER_CELL)))))
            chosen = np.column_stack((yy[order[:max_cells]], xx[order[:max_cells]])).astype(np.int32)
            old_x, old_y = map(int, country.get("capital", self.world.countries[cid - 1]["capital"]))
            old_home = int(self.world.continent[old_y, old_x])
            home_mask = ((self.world.territory == cid) & (self.world.continent == old_home))
            removed = transported if voyage.get("embarked_population") else self._remove_population_in_mask(home_mask, transported)
            if removed != transported:
                if removed and self.world.territory[old_y, old_x] == cid:
                    self.local_population[old_y, old_x] += removed
                country["retreat_voyage_used"] = False
                self._cancel_colony_voyage(country, voyage, "本島可後撤人口不足運輸計畫數量")
                return False
            base, remainder = divmod(transported, max(1, len(chosen)))
            self.local_population[chosen[:, 0], chosen[:, 1]] = base
            if remainder:
                self.local_population[chosen[:remainder, 0], chosen[:remainder, 1]] += 1
            moved = len(chosen)
        else:
            transported = int(voyage.get("transported_population", 0))
            if transported <= 0:
                self._cancel_colony_voyage(country, voyage, "人口運輸量不足，無法建立海外據點")
                return False
            max_cells = min(
                len(order), int(cfg.COLONY_INITIAL_CELLS),
                max(1, int(math.ceil(transported / max(1, cfg.SETTLER_POPULATION_PER_CELL)))),
            )
            chosen = np.column_stack((yy[order[:max_cells]], xx[order[:max_cells]])).astype(np.int32)
            moved = len(chosen)
        self.world.territory[chosen[:, 0], chosen[:, 1]] = cid
        if not retreat:
            transported = int(voyage.get("transported_population", 0))
            home = self._home_continent_id(country)
            source = ((self.world.territory == cid) & (self.world.continent == home))
            removed = transported if voyage.get("embarked_population") else self._remove_population_in_mask(source, transported)
            if removed != transported:
                if removed:
                    home_cells = np.argwhere(source)
                    if len(home_cells):
                        hy, hx = map(int, home_cells[0])
                        self.local_population[hy, hx] += removed
                self.world.territory[chosen[:, 0], chosen[:, 1]] = 0
                self._cancel_colony_voyage(country, voyage, "本島可運送人口不足四分之一")
                return False
            base, remainder = divmod(transported, max(1, len(chosen)))
            self.local_population[chosen[:, 0], chosen[:, 1]] = base
            if remainder:
                self.local_population[chosen[:remainder, 0], chosen[:remainder, 1]] += 1
        if not retreat:
            country["colonies"].append({
            "id": len(country.get("colonies", [])) + 1,
            "anchor": [ax, ay],
            "founded_year": int(self.year),
            "fleet": int(voyage.get("transport_fleet", cfg.COLONY_TRANSPORT_FLEET)),
            "overseas_capital": True,
            "continent_id": continent_id,
            })
            country["last_colony_founded_year"] = int(self.year)
        country["colonization_voyage"] = None
        if retreat:
            old_x, old_y = map(int, country.get("capital", self.world.countries[cid - 1]["capital"]))
            old_home = int(self.world.continent[old_y, old_x])
            old_land = (self.world.continent == old_home)
            old_owned = old_land & (self.world.territory == cid)
            transported_soldiers = int(voyage.get("transported_soldiers", 0))
            troops = self._take_local_soldiers(cid, old_home, transported_soldiers)
            self.world.territory[old_owned] = 0
            self.local_population[old_owned] = 0
            self.local_soldiers[old_owned] = 0
            self.world.settlement[old_land] = 0
            self.building_owner[old_land] = 0
            self.world.settlement[ay, ax] = CAPITAL
            self.building_owner[ay, ax] = cid
            country["capital"] = [ax, ay]
            country["capital_type"] = "後撤基地"
            self.world.countries[cid - 1]["capital"] = [ax, ay]
            country["fleet"] += int(voyage.get("transport_fleet", cfg.COLONY_TRANSPORT_FLEET))
            self._add_local_soldiers(cid, continent_id, troops, near=(ay, ax))
            if cfg.COLONY_AUTO_PORT:
                coast = ((self.world.territory == cid)
                         & (self.world.continent == continent_id)
                         & ndimage.binary_dilation(self.world.terrain <= 1, iterations=1)
                         & (self.world.settlement == 0))
                port_cells = np.argwhere(coast)
                if len(port_cells):
                    py, px = map(int, port_cells[np.argmin(
                        (port_cells[:, 0] - ay) ** 2
                        + np.minimum(np.abs(port_cells[:, 1] - ax),
                                     self.world.settings.width - np.abs(port_cells[:, 1] - ax)) ** 2
                    )])
                    self.world.settlement[py, px] = PORT
                    self.building_owner[py, px] = cid
                    self.world.countries[cid - 1].setdefault("ports", []).append([px, py])
            country["overseas_expeditions_used"] = self._overseas_expeditions_used(country) + 1
            country["retreat_voyage_used"] = False
            country["colonies"] = [c for c in country.get("colonies", [])
                                   if int(c.get("continent_id", -1)) != old_home]
            country["overseas_capitals"] = [s for s in country.get("overseas_capitals", [])
                                            if int(s.get("continent_id", -1)) not in (old_home, continent_id)]
            country["overseas_capitals"].append({
                "anchor": [ax, ay], "continent_id": continent_id,
                "founded_year": int(self.year), "type": "後撤基地",
            })
            country["overseas_capital"] = country["overseas_capitals"][0] if country["overseas_capitals"] else None
            country["population"] = int(self.local_population[self.world.territory == cid].sum())
            self._sync_army_totals(cid)
            self.world.countries[cid - 1]["ports"] = [
                [int(x), int(y)] for x, y in self.world.countries[cid - 1].get("ports", [])
                if int(self.world.continent[int(y), int(x)]) != old_home
            ]
            country["ports"] = int(((self.world.territory == cid) & (self.world.settlement == PORT)).sum())
        else:
            self._sync_overseas_capitals(country)
        if cfg.COLONY_AUTO_PORT and not retreat:
            self.world.settlement[ay, ax] = PORT
            self.building_owner[ay, ax] = cid
            country["ports"] = int(country.get("ports", 0)) + 1
            self.world.countries[cid - 1].setdefault("ports", []).append([ax, ay])
        # 殖民地和征服據點共用同一套後勤規則：建海外首都時即指定
        # 固定增援港，後續增援只從本島港航行到這個港口。
        overseas_site = next((site for site in country.get("overseas_capitals", [])
                              if int(site.get("continent_id", -1)) == continent_id), None)
        if overseas_site is not None:
            overseas_site["supply_food"] = float(overseas_site.get("supply_food",0)) + float(voyage.get("initial_supply",0))
            self._ensure_overseas_logistics_port(country, overseas_site)
        self._mark_world_changed(cid)
        self.world.border = _border_mask(self.world.territory)
        self._build_geography()
        region = self.geographic_name_at(ay, ax)
        if retreat:
            self._log(cid, f"後撤船隊抵達{region}；{transported:,}名人口轉移至後撤基地，政權遷都並清除原本島建築。")
            self._history("後撤", f"{country['name']}將首都遷至{region}後撤基地，轉移八成人口並放棄原本島。")
        else:
            self._log(cid, f"殖民船隊航行{voyage['route_distance_km']:,.0f}公里、歷時{self.year-voyage['launched_year']}年，運送{transported:,}名人口抵達{region}並建立海外殖民首都。")
            self._history("殖民", f"{country['name']}的殖民船隊航行至{region}並建立海外首都與殖民地。")
        self.visual_revision += 1
        self._refresh_survival()
        if not retreat:
            self._apply_delayed_rl_credit(
                country, voyage,
                float(getattr(cfg, "AI_RL_DELAYED_COLONY_SUCCESS_REWARD", 1.20)),
                "殖民船抵達並建立海外基地與港口"
            )
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
            position = self._route_position(
                voyage["route"], voyage["travelled_km"], voyage["cell_size_km"]
            )
            voyage["position"] = [float(position[0]), float(position[1])]
            self.visual_revision += 1
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
        for dy, dx in ((0,1),(1,0)):
            neighbor = np.roll(t, (-dy,-dx), axis=(0,1))
            mask = (t != neighbor) & (t > 0) & (neighbor > 0)
            if dy: mask[-1,:] = False
            ys, xs = np.where(mask)
            for y,x in zip(ys,xs):
                c1,c2=int(t[y,x]),int(neighbor[y,x]);key=tuple(sorted((c1,c2)))
                bucket=self.land_contacts.setdefault(key,[])
                if len(bucket)<600:
                    bucket.extend(((int(y),int(x)),(int(y+dy),int((x+dx)%t.shape[1]))))
        # 單向航線：(攻方, 守方) -> (航程, 攻方港口, 守方沿海登陸點)。
        self.maritime_links: dict[tuple[int, int], tuple[float, tuple[int, int], tuple[int, int]]] = {}
        if not hasattr(self, "_sea_labels"):
            self._sea_labels, _ = ndimage.label(self.world.terrain <= 1, structure=np.ones((3, 3), dtype=np.uint8))
        countries = [c for c in self.world.countries if self.country(int(c["id"])).get("alive")]
        ports_by_country = {}
        coasts_by_country = {}
        sea = self.world.terrain <= 1
        if not hasattr(self, "_geographic_coast"):
            self._geographic_coast = ndimage.binary_dilation(sea, iterations=1) & ~sea
        coastal_land = self._geographic_coast
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

    def _army_total(self, cid: int) -> int:
        local = int(self.local_soldiers.ravel()[self._spatial_indices(cid)].sum())
        at_sea = sum(int(x.soldiers) for x in self.campaigns
                     if x.attacker == int(cid) and x.status == "marching")
        transport = int((self.country(int(cid)).get("reinforcement_voyage") or {}).get("soldiers", 0))
        return local + at_sea + transport

    def _sync_army_totals(self, *country_ids):
        ids = country_ids or tuple(int(c["id"]) for c in self.countries)
        for cid in ids:
            if 0 < int(cid) <= len(self.countries):
                country = self.country(int(cid))
                country["soldiers"] = min(int(country.get("population", 0)), self._army_total(int(cid)))

    def _landmass_soldiers(self, cid, landmass_id):
        return int(self.local_soldiers.ravel()[self._spatial_indices(cid, landmass_id)].sum())

    def _take_local_soldiers(self, cid: int, landmass_id: int, amount: int) -> int:
        """Embark troops only from the selected landmass; no cross-island teleporting."""
        amount = max(0, int(amount))
        mask = ((self.world.territory == int(cid))
                & (self.world.continent == int(landmass_id))
                & (self.local_soldiers > 0))
        coords = np.argwhere(mask)
        available = int(self.local_soldiers[mask].sum())
        take = min(amount, available)
        remaining = take
        if len(coords):
            order = np.argsort(self.local_soldiers[coords[:, 0], coords[:, 1]])[::-1]
            for index in order:
                y, x = map(int, coords[index])
                part = min(remaining, int(self.local_soldiers[y, x]))
                self.local_soldiers[y, x] -= part
                remaining -= part
                if remaining <= 0:
                    break
        return take - remaining

    def _add_local_soldiers(self, cid: int, landmass_id: int, amount: int, near=None):
        amount = max(0, int(amount))
        if not amount:
            return
        indices = self._spatial_indices(cid, landmass_id)
        coords = np.column_stack(np.unravel_index(indices, self.world.territory.shape))
        if not len(coords):
            return
        if near is not None:
            y, x = map(int, near)
            dx = np.minimum(np.abs(coords[:, 1] - x), self.world.settings.width - np.abs(coords[:, 1] - x))
            order = np.argsort((coords[:, 0] - y) ** 2 + dx ** 2)
            coords = coords[order]
        room = np.maximum(0, self.local_population[coords[:, 0], coords[:, 1]]
                - self.local_soldiers[coords[:, 0], coords[:, 1]])
        amount = min(amount, int(np.maximum(0, room).sum()))
        if not amount:
            return
        weights = np.maximum(0, room).astype(np.float64)
        if weights.sum() <= 0:
            return
        allocation = np.minimum(
            room,
            np.floor(weights / weights.sum() * amount).astype(np.int32),
        )
        remainder = amount - int(allocation.sum())
        while remainder > 0:
            available = np.flatnonzero(allocation < room)
            if not len(available):
                break
            order = available[np.argsort(-weights[available])]
            for index in order:
                allocation[index] += 1
                remainder -= 1
                if remainder <= 0:
                    break
        self.local_soldiers[coords[:, 0], coords[:, 1]] += allocation

    def _remove_population_in_mask(self, mask, amount):
        amount = max(0, int(amount))
        removable = np.maximum(0, self.local_population - self.local_soldiers)
        coords = np.argwhere(mask & (removable > 0))
        left = min(amount, int(removable[mask].sum()))
        planned = left
        if len(coords):
            order = np.argsort(removable[coords[:,0], coords[:,1]])[::-1]
            for i in order:
                y,x = map(int,coords[i]);take=min(left,int(removable[y,x]))
                self.local_population[y,x] -= take;left -= take
                if left <= 0:break
        return planned-left

    def _transport_population_capacity(self, fleet: int) -> int:
        return max(0, int(fleet)) * max(0, int(cfg.OVERSEAS_POPULATION_PER_SHIP))

    def _transport_soldier_capacity(self, fleet: int) -> int:
        return max(0, int(fleet)) * max(0, int(cfg.OVERSEAS_SOLDIERS_PER_SHIP))

    def _ensure_overseas_logistics_port(self, country, site):
        return self._logistics_port(country, site)

    def _send_overseas_reinforcements(self, selected_country_ids=None, force=False):
        return self._reinforce_v22(selected_country_ids, force)

    def _advance_overseas_reinforcements(self):
        self._arrive_reinforcements_v22()

    def legal_targets(self, attacker):
        c = self.country(attacker)
        if not c["alive"]:
            return []
        result = []
        home = self._home_continent_id(c)
        owned_islands = self._overseas_landmass_ids(c) | {home}
        for target in self.countries:
            tid = target["id"]
            if tid == attacker or not target["alive"] or (c["alliance"] > 0 and c["alliance"] == target["alliance"]):
                continue
            points = self.land_contacts.get(tuple(sorted((attacker, tid))), [])
            shared = sorted({int(self.world.continent[y,x]) for y,x in points} & owned_islands)
            for lm in shared:
                result.append({"id": tid, "mode": "land", "distance": 1., "landmass_id": lm})
            if c["fleet"] < cfg.OVERSEAS_MIN_FLEET or not self._homeland_is_unified(c):
                continue
            if (attacker, tid) not in self.maritime_links or not self._can_launch_overseas_expedition(c):
                continue
            islands = sorted(set(int(x) for x in np.unique(self.world.continent[self.world.territory == tid])) - owned_islands)
            for lm in islands:
                if lm <= 0 or not self._can_launch_overseas_expedition(c, lm):
                    continue
                result.append({"id": tid, "mode": "naval", "distance": self.maritime_links[(attacker,tid)][0], "landmass_id": lm})
        return result

    def _country_strength(self, cid: int) -> float:
        c = self.country(cid)
        active = sum(x.soldiers for x in self.campaigns if x.attacker == cid and x.status == "marching")
        return max(0.0, c["soldiers"] - active) * c["morale"] + c["fleet"] * 18.0

    def _home_soldiers(self, cid: int, landmass_id: int | None = None) -> int:
        """Return soldiers physically stationed on one landmass, defaulting to the homeland."""
        if landmass_id is None:
            landmass_id = self._home_continent_id(self.country(int(cid)))
        return self._landmass_soldiers(int(cid), int(landmass_id)) if int(landmass_id) > 0 else 0

    def _objective(self, attacker, defender, mode, landmass_id=None):
        if mode == "land":
            lm = landmass_id
            selected = getattr(self, "_selected_theatre", None)
            tactic = "ATTACK_FRONT"
            if selected and selected[0] == attacker:
                lm = selected[1]; tactic = selected[2]
            enemy = self.world.territory == defender
            mask = enemy & self._adjacent_land_mask(self.world.territory == attacker)
            if lm is not None:
                mask &= self.world.continent == lm
            cells = np.argwhere(mask)
            if not len(cells):
                return None
            if len(cells) > 96:
                cells = cells[np.linspace(0, len(cells)-1, 96, dtype=int)]
            scores = []
            ex, ey = self.country(defender)["capital"]
            for y, x in cells:
                point=(int(y),int(x)); island=int(self.world.continent[point])
                army=self._home_soldiers(defender,island)
                score=self._terrain_defense(point)*army*self._local_garrison_share(self.country(defender),point)
                if tactic == "ENCIRCLE_CAPITAL":
                    score *= .4 + self._wrapped_distance_cells((int(x),int(y)),(ex,ey),self.world.settings.width)/300.
                elif tactic == "RECOVER_PORT":
                    site=self._site(self.country(attacker),island)
                    port=(site or {}).get("logistics_port")
                    if port:
                        score *= .25 + self._wrapped_distance_cells((int(x),int(y)),port,self.world.settings.width)/200.
                elif tactic == "CUT_OFF":
                    radius=6; patch=self.world.territory[max(0,y-radius):y+radius+1,max(0,x-radius):x+radius+1]
                    score *= .5 + float(np.mean(patch==defender))
                scores.append(score)
            return tuple(map(int,cells[int(np.argmin(scores))]))
        home=self._home_continent_id(self.country(attacker))
        coast=(self.world.territory==defender)&self._adjacent_land_mask(self.world.terrain<=1)&(self.world.terrain>=2)
        if landmass_id is not None:
            coast &= self.world.continent==landmass_id
        cells=np.argwhere(coast)
        ports=np.argwhere((self.world.territory==attacker)&(self.world.settlement==PORT)&(self.world.continent==home))
        if not len(cells) or not len(ports):return None
        if len(cells)>96:cells=cells[np.linspace(0,len(cells)-1,96,dtype=int)]
        scores=[]
        for y,x in cells:
            d=min(self._wrapped_distance_cells((int(x),int(y)),(int(px),int(py)),self.world.settings.width) for py,px in ports)
            if d>cfg.NAVAL_OPERATION_RANGE:scores.append(float('inf'));continue
            point=(int(y),int(x));lm=int(self.world.continent[point])
            defense=self._home_soldiers(defender,lm)*self._local_garrison_share(self.country(defender),point)*self._terrain_defense(point)
            scores.append(defense + d*.01)
        if not np.isfinite(min(scores)):return None
        return tuple(map(int,cells[int(np.argmin(scores))]))

    def _origin(self, attacker, defender, objective, mode):
        lm = self._home_continent_id(self.country(attacker)) if mode == "naval" else int(self.world.continent[objective])
        mask = (self.world.territory == attacker) & (self.world.continent == lm)
        if mode == "naval":mask &= self.world.settlement == PORT
        else:
            one=np.zeros_like(mask);one[objective]=True
            mask &= self._adjacent_land_mask(one)
        cells=np.argwhere(mask)
        if not len(cells):return None
        dx=np.minimum(abs(cells[:,1]-objective[1]),self.world.settings.width-abs(cells[:,1]-objective[1]))
        i=int(np.argmin((cells[:,0]-objective[0])**2+dx**2))
        return tuple(map(int,cells[i]))

    def _tactical_region_state(self, owner_id: int, opponent_id: int, point, mode: str):
        """離散描述地形、戰力壓力、戰區價值與海陸進場方式。"""
        y, x = map(int, point)
        terrain = int(np.clip(self.world.terrain[y, x], 0, 6))
        defender = self.country(opponent_id)
        local_share = self._local_garrison_share(defender, point)
        landmass = int(self.world.continent[y, x])
        local_defense_soldiers = min(self._home_soldiers(opponent_id, landmass), max(200, int(defender["soldiers"] * local_share)))
        local_defense = local_defense_soldiers * float(defender.get("morale", 1.0)) * self._terrain_defense(point)
        opponent_pressure = local_defense / max(1.0, self._country_strength(owner_id))
        pressure_bin = 0 if opponent_pressure < 0.45 else 1 if opponent_pressure < 0.8 else 2 if opponent_pressure < 1.2 else 3
        value = int(self.world.city_value[y, x])
        value_bin = 0 if value < 25 else 1 if value < 50 else 2 if value < 75 else 3
        capital_x, capital_y = map(int, self.country(owner_id).get("capital", (x, y)))
        dx = min(abs(x - capital_x), self.world.settings.width - abs(x - capital_x))
        distance = math.hypot(y - capital_y, dx)
        distance_bin = 0 if distance < 30 else 1 if distance < 100 else 2 if distance < 300 else 3
        local_bin = 0 if local_share < 0.25 else 1 if local_share < 0.40 else 2 if local_share < 0.60 else 3
        return (terrain, local_bin, pressure_bin, value_bin, int(mode == "naval"), distance_bin)

    def _choose_tactical_action(self, country_id: int, state, actions) -> str:
        brain = self.rl_brains.get(int(country_id))
        if brain is None:
            self._ensure_country_brain(int(country_id))
            brain = self.rl_brains[int(country_id)]
        epsilon = float(cfg.TACTICAL_EXPLORATION)
        return brain.select_tactical(state, actions, epsilon)

    def _learn_tactical_action(self, country_id: int, state, action: str, reward: float):
        if not action or state is None:
            return
        self._ensure_country_brain(int(country_id))
        self.rl_brains[int(country_id)].learn_tactical(
            state, action, float(np.clip(reward, -2.0, 2.0)),
            alpha=float(cfg.TACTICAL_LEARNING_ALPHA),
        )

    def launch_campaign(self, attacker: int, defender: int, mode: str | None = None,
                        coalition_id: int = 0, reinforcement_for: int = 0) -> Campaign | None:
        options = [x for x in self.legal_targets(attacker) if x["id"] == defender]
        if not options:
            return None
        selected = getattr(self, "_selected_theatre", None)
        if selected and selected[0] == attacker:
            options = [x for x in options if x.get("landmass_id") == selected[1]]
        option = next((x for x in options if mode is None or x["mode"] == mode), None)
        if not option:
            return None
        a = self.country(attacker)
        if self.year < int(a.get("recovery_until_year", 0)):
            return None
        if option["mode"] == "naval" and not self._homeland_is_unified(a):
            return None
        if option["mode"] == "naval" and a["fleet"] < cfg.OVERSEAS_MIN_FLEET:
            return None
        if (option["mode"] == "naval"
                and not self._can_launch_overseas_expedition(a, option.get("landmass_id"))):
            return None
        if sum(1 for x in self.campaigns if x.attacker == attacker and x.status == "marching") >= cfg.AI_MAX_ACTIVE_CAMPAIGNS:
            return None
        objective = self._objective(attacker, defender, option["mode"], option.get("landmass_id"))
        if objective is None:
            return None
        target_landmass = int(self.world.continent[int(objective[0]), int(objective[1])])
        home_landmass = self._home_continent_id(a)
        existing_sites = {
            int(site.get("continent_id", -1)) for site in a.get("overseas_capitals", [])
        }
        transported_population = 0
        # 已在目標外島駐軍時，直接由該島出兵；否則必須從本島裝船遠征。
        source_landmass = target_landmass if option["mode"] == "land" else home_landmass
        if option["mode"] == "naval" and target_landmass in existing_sites:
            # Once a theatre exists, the motherland must use its supply port, not a fresh invasion.
            return None
        if option["mode"] == "naval" and target_landmass != home_landmass and target_landmass not in existing_sites:
            source_population = int(self.local_population[
                (self.world.territory == int(attacker))
                & (self.world.continent == source_landmass)
            ].sum())
            transported_population = int(source_population * float(getattr(cfg, "OVERSEAS_INITIAL_POPULATION_RATIO", 1 / 3)))
            if self._transport_population_capacity(a["fleet"]) < transported_population:
                return None
        local_available = self._home_soldiers(attacker, source_landmass)
        local_population = int(self.local_population[
            (self.world.territory == int(attacker))
            & (self.world.continent == int(source_landmass))
        ].sum())
        available = max(0, local_available - int(local_population * cfg.MIN_GARRISON_RATIO))
        if option["mode"] == "naval":
            available = min(available, self._transport_soldier_capacity(a["fleet"]))
        if available < cfg.AI_MIN_ATTACK_SOLDIERS:
            return None
        tactical_state = self._tactical_region_state(attacker, defender, objective, option["mode"])
        tactical_actions = [f"ATTACK:{int(round(fraction * 100))}" for fraction in cfg.TACTICAL_ATTACK_FRACTIONS]
        if option["mode"] == "naval":
            # A landing must budget troops against the actual destination island,
            # rather than send a tiny fraction of an already depleted home army.
            target = self.country(defender)
            defending_army = self._home_soldiers(defender, target_landmass)
            share = max(self._local_garrison_share(target, objective),
                        float(np.median(cfg.BATTLE_LEARNED_GARRISON_SHARES)))
            defenders = min(defending_army, max(200, int(defending_army * share)))
            estimated_defense = defenders * target["morale"] * self._terrain_defense(objective)
            unit_attack = max(.01, a["morale"] * (1.0-cfg.AMPHIBIOUS_ATTACK_PENALTY))
            tactical_actions = [action for action in tactical_actions
                                if min(available,max(cfg.AI_MIN_ATTACK_SOLDIERS,int(available*int(action.split(':')[1])/100))) * unit_attack >= estimated_defense]
            if not tactical_actions:
                if self.year-int(a.get("last_landing_deferred_log",-100))>=20:
                    self._log(attacker, "海外登陸暫緩：可運送兵力不足以對抗目標島預估守軍；保留兵力發展或另選目標。")
                    a["last_landing_deferred_log"]=self.year
                return None
        tactical_action = self._choose_tactical_action(attacker, tactical_state, tactical_actions)
        fraction = int(tactical_action.split(":", 1)[1]) / 100.0
        soldiers = min(available, max(cfg.AI_MIN_ATTACK_SOLDIERS, int(available * fraction)))
        if soldiers < cfg.AI_MIN_ATTACK_SOLDIERS:
            return None
        origin = self._origin(attacker, defender, objective, option["mode"])
        if origin is None:
            return None
        dx = min(abs(origin[1] - objective[1]), self.world.settings.width - abs(origin[1] - objective[1]))
        raw_distance = max(1.0, math.hypot(origin[0] - objective[0], dx))
        friction = 1.0 if option["mode"] == "naval" else float(np.clip(self.world.movement_cost[origin], 1, 20)) / 4.0
        distance = raw_distance * max(1.0, friction)
        sea_route = None
        if option["mode"] == "naval":
            sea_route = self._sea_route((origin[1], origin[0]), (objective[1], objective[0]))
            if not sea_route:
                return None
            distance = self._route_distance_km(sea_route)
        speed = cfg.SEA_MARCH_CELLS_PER_YEAR if option["mode"] == "naval" else cfg.LAND_MARCH_CELLS_PER_YEAR
        years = max(1, int(math.ceil(distance / speed)))
        supply = soldiers * distance * cfg.SUPPLY_PER_SOLDIER_CELL
        fleet = (min(int(a["fleet"]), max(
            1,
            int(math.ceil(soldiers / max(1, int(cfg.OVERSEAS_SOLDIERS_PER_SHIP)))),
            int(math.ceil(transported_population / max(1, int(cfg.OVERSEAS_POPULATION_PER_SHIP)))),
        )) if option["mode"] == "naval" else 0)
        embarked = self._take_local_soldiers(attacker, source_landmass, soldiers)
        if embarked < cfg.AI_MIN_ATTACK_SOLDIERS:
            self._add_local_soldiers(attacker, source_landmass, embarked)
            return None
        soldiers = embarked
        embarked_population = 0
        if option["mode"] == "naval":
            passengers = max(soldiers, transported_population)
            source_mask = ((self.world.territory == attacker) & (self.world.continent == source_landmass))
            embarked_population = self._remove_population_in_mask(source_mask, passengers)
            if embarked_population < passengers:
                hx,hy = a["capital"]
                self.local_population[hy,hx] += embarked_population
                self._add_local_soldiers(attacker, source_landmass, soldiers)
                return None
            a["fleet"] -= fleet
        campaign = Campaign(self.next_campaign_id, attacker, defender, option["mode"], origin,
                            objective, soldiers, fleet, distance, years, supply,
                            coalition_id, reinforcement_for,
                            origin_landmass=int(source_landmass),
                            transported_population=int(transported_population),
                            tactical_state=tactical_state, tactical_action=tactical_action,
                            sea_route=sea_route, embarked_population=embarked_population)
        self.next_campaign_id += 1
        self.campaigns.append(campaign)
        self._sync_army_totals(attacker)
        if option["mode"] == "naval":
            a["overseas_expeditions_used"] = self._overseas_expeditions_used(a) + 1
        self.visual_revision += 1
        self.alerts.append(f"{self.country(defender)['name']}獲報：{a['name']}正集結{soldiers:,}人，預計{years}年抵達。")
        campaign_name = "海外征戰" if option["mode"] == "naval" else "陸上征戰"
        self.events.append(f"第{self.year}年｜{a['name']}向{self.country(defender)['name']}發起{campaign_name}。")
        self._log(attacker, f"發起{campaign_name}，向{self.country(defender)['name']}集結{soldiers:,}名士兵，預計{years}年抵達。")
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
                # Extinction is irreversible; purge each dead ID once per loaded engine.
                if not hasattr(self, "_purged_dead_ids"):
                    self._purged_dead_ids = set()
                if c["id"] in self._purged_dead_ids:
                    continue
                self._purged_dead_ids.add(c["id"])
                # 滅亡是不可逆狀態；任何殘留或舊存檔帶回的領土一律清除，杜絕重生。
                stray = self.world.territory == c["id"]
                self.world.territory[stray] = 0
                self.world.settlement[stray] = 0
                built_by_country = self.building_owner == c["id"]
                self.world.settlement[built_by_country] = 0
                self.building_owner[built_by_country] = 0
                self.local_population[stray] = 0
                self.local_soldiers[stray] = 0
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
            resting = self.year <= int(c.get("recovery_until_year", 0))
            exhaustion = float(np.clip(c.get("war_exhaustion", 0.0), 0.0, 1.0))
            recovery_rate = cfg.REST_EXHAUSTION_RECOVERY if resting else cfg.PASSIVE_EXHAUSTION_RECOVERY
            c["war_exhaustion"] = max(0.0, exhaustion - float(recovery_rate))
            annual_food_output = float(
                food_output[cid] * cfg.FOOD_PRODUCTION_MULTIPLIER * (1.0 + productivity_bonus)
            )
            food_capacity = annual_food_output / max(0.0001, cfg.FOOD_CONSUMPTION_PER_PERSON)
            growth_limit = max(0, int(food_capacity * cfg.FOOD_GROWTH_RESERVE_RATIO - populations[cid]))
            # growth = min(
            #     max(0, int(populations[cid] * cfg.ANNUAL_POPULATION_GROWTH
            #                * (cfg.REST_BIRTH_GROWTH_MULTIPLIER if resting else 1.0))),
            #     growth_limit,
            # )

            capacity_bonus = max(0.0, food_capacity) / max(1.0, float(cfg.FOOD_CAPACITY_BONUS_PER_PERSON))
            # Birth speed depends on productive capacity; existing local stock only
            # raises the cap checked in _local_growth, never the growth bonus.
            growth = (cfg.POPULATION_GROWTH
                      * (cfg.REST_BIRTH_GROWTH_MULTIPLIER if resting else 1.0)
                      * (1.0 + capacity_bonus))

            growth = self._local_growth(c, growth)
            c["population"] = int(populations[cid] + growth)
            self._sync_army_totals(cid)
            c["soldiers"] = min(c["soldiers"], c["population"])
            desired_army = int(c["population"] * 0.18)
            slowdown_span = max(1, int(cfg.RECRUIT_SLOWDOWN_FULL_YEAR) - int(cfg.RECRUIT_SLOWDOWN_START_YEAR))
            slowdown_progress = float(np.clip(
                (self.year - int(cfg.RECRUIT_SLOWDOWN_START_YEAR)) / slowdown_span, 0.0, 1.0
            ))
            recruit_multiplier = 1.0 - slowdown_progress * (1.0 - float(cfg.LATE_GAME_RECRUIT_MIN_MULTIPLIER))
            recruits = min(
                int(c["population"] * cfg.ANNUAL_RECRUIT_RATIO * recruit_multiplier
                    * (1.0 - exhaustion * cfg.WAR_EXHAUSTION_RECRUIT_PENALTY)
                    * (1.0 + capacity_bonus)
                    * (1.15 if resting else 1.0)),
                max(0, desired_army - c["soldiers"]),
            )
            capital_x, capital_y = map(int, c.get("capital", self.world.countries[cid - 1]["capital"]))
            if int(self.world.territory[capital_y, capital_x]) != cid:
                owned = np.argwhere(self.world.territory == cid)
                if len(owned):
                    capital_y, capital_x = map(int, owned[len(owned) // 2])
            home = int(self.world.continent[capital_y, capital_x])
            self._local_recruits(c, int(recruits))
            self._sync_army_totals(cid)
            annual_food_consumption = float(c["population"] * cfg.FOOD_CONSUMPTION_PER_PERSON)
            annual_food_balance = annual_food_output - annual_food_consumption
            c["last_food_production"] = annual_food_output
            c["last_food_consumption"] = annual_food_consumption
            c["last_food_balance"] = annual_food_balance
            c["food_capacity"] = int(food_capacity)
            # Overseas food is produced/consumed in that site's own stock ledger.
            # Remove its net flow here, otherwise shipped food would be charged twice.
            overseas_net = 0.0
            for site in c.get("overseas_capitals", []):
                lm = int(site["continent_id"])
                idx = self._spatial_indices(cid, lm)
                local_output = float(self.food_yield.ravel()[idx].sum()) * cfg.FOOD_PRODUCTION_MULTIPLIER * (1.0 + productivity_bonus)
                local_consumption = int(self.local_population.ravel()[idx].sum()) * cfg.FOOD_CONSUMPTION_PER_PERSON
                local_balance = local_output - local_consumption
                overseas_net += local_balance
                site["food_shortfall_this_year"] = max(0.0, -(float(site.get("supply_food",0)) + local_balance))
                site["supply_food"] = max(0.0, float(site.get("supply_food",0)) + local_balance)
            c["food"] += annual_food_balance - overseas_net
            c["timber"] += float(timber_output[cid] * 0.42)
            c["minerals"] += float(mineral_output[cid] * 0.24)
            if c["food"] < 0:
                shortage = min(0.025, -c["food"] / max(1.0, c["population"] * 30.0))
                losses = int(c["population"] * shortage)
                home_mask = (self.world.territory == cid) & (self.world.continent == home)
                self._remove_population_in_mask(home_mask, losses)
                c["morale"] = max(0.55, c["morale"] - 0.03)
                c["food"] = 0.0
            else:
                c["morale"] = min(1.15, c["morale"] + (cfg.REST_MORALE_RECOVERY if resting else 0.002))
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

        # 拓荒等級屬於國家級發展能力，不應被港口、艦隊、城市或兵營
        # 的建設流程提前 return 而永久餓死。每次建設週期先檢查一次。
        frontier_target = max(1, area // int(cfg.FRONTIER_LEVEL_AREA_PER_LEVEL))
        if int(country.get("frontier_level", 0)) < frontier_target:
            if self._can_pay(country, cfg.FRONTIER_LEVEL_COST):
                country["frontier_level"] = max(
                    frontier_target, int(country.get("frontier_level", 0)) + 1
                )
                self._pay(country, cfg.FRONTIER_LEVEL_COST)
                # 不刷逐次升級 LOG；等級可由國家狀態／UI 直接讀取。
                return
        occupied = self.world.settlement > 0
        candidates = np.argwhere(mask & ~occupied)
        sea = self.world.terrain <= 1
        coast = mask & ndimage.binary_dilation(sea, iterations=1) & ~occupied
        port_limit = max(0, int(cfg.PORTS_PER_COUNTRY))
        home = self._home_continent_id(country)
        coast &= self.world.continent == home
        home_port_count = int(np.count_nonzero(mask & (self.world.continent == home) & (self.world.settlement == PORT)))
        if (coast.any() and home_port_count < port_limit
                and (self._homeland_is_unified(country) or bool(country.get("overseas_capitals")))
                and self._can_pay(country, cfg.PORT_COST)):
            coords = np.argwhere(coast)
            scores = self.world.city_value[coords[:, 0], coords[:, 1]]
            y, x = map(int, coords[int(np.argmax(scores))])
            self.world.settlement[y, x] = PORT
            self.building_owner[y, x] = cid
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
        ]
        for code, label, key, target, cost in desired:
            if country[key] >= target or not self._can_pay(country, cost):
                continue
            if code is None:
                country[key] += 1
                self._pay(country, cost)
                # 拓荒等級屬於內部經濟狀態，不再刷逐次升級LOG。
                # return
            build_candidates = candidates
            if code in (CITY, BARRACKS):
                if not len(build_candidates):
                    continue
                min_gap = int(cfg.CITY_MIN_DISTANCE if code == CITY else cfg.BARRACKS_MIN_DISTANCE)
                spacing_mask = ((self.world.settlement == CAPITAL) | (self.world.settlement == CITY)
                                if code == CITY else self.world.settlement == BARRACKS)
                if np.any(spacing_mask):
                    # Triple-width padding makes horizontal world wrapping count as adjacent.
                    padded = np.concatenate((spacing_mask, spacing_mask, spacing_mask), axis=1)
                    distance = ndimage.distance_transform_edt(~padded)[:, self.world.settings.width:2 * self.world.settings.width]
                    build_candidates = candidates[
                        distance[candidates[:, 0], candidates[:, 1]] >= min_gap
                    ]
                    # No legal location for this building must not block later types.
                    if not len(build_candidates):
                        continue
            if code == BARRACKS:
                score_map = self.world.defense_value
            else:
                score_map = self.world.city_value
            scores = score_map[build_candidates[:, 0], build_candidates[:, 1]]
            y, x = map(int, build_candidates[int(np.argmax(scores))])
            self.world.settlement[y, x] = code
            self.building_owner[y, x] = cid
            self.visual_revision += 1
            country[key] += 1
            self._pay(country, cost)
            self._log(cid, f"在({x},{y})建成{label}。")
            return

    def expansion_status(self, cid):
        c = self.country(int(cid)); lm = self._home_continent_id(c)
        home = (self.world.continent == lm) & (self.world.terrain >= 2)
        empty = home & (self.world.territory == 0)
        passable = empty & (self.world.movement_cost < 255)
        return (int(passable.sum()), int((empty & ~passable).sum()))

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
            amount = min(
                cfg.BASE_EXPANSION_CELLS + country["cities"] * cfg.CITY_EXPANSION_BONUS
                + country["barracks"] * cfg.BARRACKS_EXPANSION_BONUS
                + country["frontier_level"] * cfg.FRONTIER_LEVEL_EXPANSION_BONUS,
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
            # Only reserve candidate slots which their own island can populate.
            selected = []
            landmasses = self.world.continent[coords[:, 0], coords[:, 1]]
            for lm in np.unique(landmasses):
                idx = self._spatial_indices(cid, int(lm))
                civilians = np.maximum(0, self.local_population.ravel()[idx].astype(np.int64)
                                       - self.local_soldiers.ravel()[idx].astype(np.int64) - 1)
                slots = int(civilians.sum()) // max(1, int(cfg.SETTLER_POPULATION_PER_CELL))
                group = np.flatnonzero(landmasses == lm)
                if slots > 0:
                    selected.extend(group[np.argsort(score[group])[-min(slots, len(group)):]].tolist())
            if not selected:
                continue
            feasible = np.asarray(selected, dtype=np.int32)
            chosen = coords[feasible[np.argsort(score[feasible])[-amount:]]]
            settlers = 0
            claimed = []
            destination_landmasses = self.world.continent[chosen[:, 0], chosen[:, 1]]
            for landmass in np.unique(destination_landmasses):
                group = chosen[destination_landmasses == landmass]
                moved_here = self._move_settlers(cid, group)
                if moved_here:
                    claimed.append(group[:moved_here])
                    settlers += moved_here
            if settlers <= 0:
                continue
            chosen = np.concatenate(claimed, axis=0)
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
        # 每一批移民只能從目的地所在陸塊出發，海外人口不會憑空搬回本島。
        moved_cells = 0
        if not len(destinations):
            return 0
        landmasses = self.world.continent[destinations[:, 0], destinations[:, 1]]
        for landmass in np.unique(landmasses):
            group = destinations[landmasses == landmass]
            needed = len(group) * int(cfg.SETTLER_POPULATION_PER_CELL)
            mask = ((self.world.territory == int(cid))
                    & (self.world.continent == int(landmass))
                    & (self.local_population > self.local_soldiers + 1))
            sources = np.argwhere(mask)
            moved = 0
            if len(sources):
                order = np.argsort(self.local_population[sources[:, 0], sources[:, 1]])[::-1]
                for idx in order:
                    y, x = map(int, sources[idx])
                    take = min(int(self.local_population[y, x] - self.local_soldiers[y, x] - 1), needed - moved)
                    self.local_population[y, x] -= take
                    moved += take
                    if moved >= needed:
                        break
            cells = min(len(group), moved // max(1, int(cfg.SETTLER_POPULATION_PER_CELL)))
            for y, x in group[:cells]:
                self.local_population[int(y), int(x)] = int(cfg.SETTLER_POPULATION_PER_CELL)
            moved_cells += cells
        return moved_cells

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

    def _rl_state_and_actions(self, cid, colony_available=False):
        return self._strategic_state_actions(cid, colony_available)

    @staticmethod
    def _rl_metrics(country: dict) -> dict:
        return {
            "alive": bool(country["alive"]),
            "territory": int(country["territory_cells"]),
            "population": int(country["population"]),
            "food": float(country["food"]),
            "wars_won": int(country["wars_won"]),
            "wars_lost": int(country["wars_lost"]),
            "war_exhaustion": float(country.get("war_exhaustion", 0.0)),
            "morale": float(country.get("morale", 1.0)),
        }

    def _rl_metrics_for_country(self, country: dict) -> dict:
        metrics = self._rl_metrics(country)
        metrics["remaining_enemies"] = max(
            0, sum(1 for other in self.countries if other["alive"] and other["id"] != country["id"])
        )
        total_land = max(1, int(np.count_nonzero(self.world.terrain >= 2)))
        metrics["world_control_share"] = float(country.get("territory_cells", 0)) / total_land
        metrics["pacified_overseas"] = sum(
            self._overseas_landmass_is_pacified(country, lm)
            for lm in self._overseas_landmass_ids(country)
        )
        potential = 0.0
        for site in country.get("overseas_capitals", []):
            t = self._theatre(country, site)
            potential += .15 + .15 * bool(t["port"]) + .15 * min(1.0, t["army"] / max(1,t["target"]))
        metrics["strategic_potential"] = min(2.0, potential)
        return metrics

    def _priority_overseas_action(self, country: dict, colony_context=None) -> str | None:
        """本島達標且名額可用時，優先把統一世界目標轉成海外行動。"""
        if (not bool(getattr(cfg, "AI_OVERSEAS_EXPANSION_PRIORITY", True))
                or not country.get("alive", False)
                or self.year < int(country.get("recovery_until_year", 0))
                or not self._homeland_is_unified(country)
                or not self._can_launch_overseas_expedition(country)):
            return None

        active = sum(
            campaign.attacker == int(country["id"]) and campaign.status == "marching"
            for campaign in self.campaigns
        )
        committed = sum(
            campaign.soldiers for campaign in self.campaigns
            if campaign.attacker == int(country["id"]) and campaign.status == "marching"
        )
        available = max(
            0, int(country["soldiers"])
            - int(country["population"] * cfg.MIN_GARRISON_RATIO)
            - committed
        )
        if active < cfg.AI_MAX_ACTIVE_CAMPAIGNS and available >= cfg.AI_MIN_ATTACK_SOLDIERS:
            total_land = max(1, sum(int(c["territory_cells"]) for c in self.countries if c["alive"]))
            naval_options = []
            for option in self.legal_targets(int(country["id"])):
                if option["mode"] != "naval":
                    continue
                target = self.country(int(option["id"]))
                ratio = self._country_strength(int(country["id"])) / max(
                    1.0, self._country_strength(int(target["id"]))
                )
                if ratio < float(cfg.AI_UNIFICATION_MIN_POWER_RATIO):
                    continue
                score = (
                    ratio * 2.0
                    + min(0.8, int(target["territory_cells"]) / total_land
                          * float(cfg.AI_UNIFICATION_TARGET_LAND_WEIGHT))
                    - float(option["distance"]) / 900.0
                )
                naval_options.append((score, option))
            if naval_options:
                _score, target = max(naval_options, key=lambda item: item[0])
                return f"ATTACK:{int(target['id'])}:naval"

        if (colony_context is not None
                and self._colony_country_eligible(country)
                and len(self._colony_candidates(country, colony_context))):
            return "COLONIZE"
        return None

    def _rl_reward(self, before, after, action=PASS_ACTION):
        return self._strategic_reward(before, after, action)

    def _apply_delayed_rl_credit(self, country, event, reward, label):
        brain = self.rl_brains.get(int(country["id"]))
        state = event.get("rl_state") if event else None
        if brain is None or not state or len(state) != 9 or not event.get("rl_action"):
            return
        if event.get("credited"):
            return
        key = brain.key(state, event["rl_action"])
        brain.q_values[key] = brain.q_values.get(key, 0.0) + cfg.AI_RL_ALPHA * float(reward)
        event["credited"] = True
        brain.updates += 1
        self._log(country["id"], f"AI事件回饋：{label}，原始動作補充回饋{reward:+.2f}。")

    def _rl_epsilon(self, brain: CountryBrain) -> float:
        fraction = min(1.0, brain.decisions / max(1, cfg.AI_RL_EPSILON_DECAY_DECISIONS))
        return float(cfg.AI_RL_EPSILON + (cfg.AI_RL_MIN_EPSILON - cfg.AI_RL_EPSILON) * fraction)

    def _rl_war_decisions(self, alive: list[dict]):
        """每個國家獨立決策；最遲20年內必須選一次積極行動。

        海外殖民、海外征戰、海外增援與休養同屬戰略動作，
        SARSA 只在「合法動作集合」內學習，不再用固定海外優先序覆蓋Q值。
        """
        colony_context = self._colony_context()

        for country in alive:
            cid = int(country["id"])
            brain = self.rl_brains[cid]
            due = self.year >= int(country.get("next_ai_decision_year", self.year))
            if not due:
                continue

            colony_available = bool(len(self._colony_candidates(country, colony_context)))
            state, actions, action_biases = self._rl_state_and_actions(cid, colony_available)
            metrics = self._rl_metrics_for_country(country)
            epsilon = self._rl_epsilon(brain)

            reward = 0.0
            if brain.pending:
                previous = brain.pending
                reward = self._rl_reward(
                    previous["metrics"], metrics, previous.get("action", PASS_ACTION)
                )
                brain.update(
                    previous["state"], previous["action"], reward,
                    next_state=state, next_actions=actions, epsilon=epsilon,
                    alpha=cfg.AI_RL_ALPHA, gamma=cfg.AI_RL_GAMMA,
                    trace_lambda=cfg.AI_RL_TRACE_LAMBDA,
                    next_action_biases=action_biases,
                )
                new_plan = brain.record_strategy_step(
                    previous.get("action", PASS_ACTION),
                    reward,
                    min_len=int(getattr(cfg, "AI_TACTIC_MIN_SEQUENCE", 2)),
                    max_len=int(getattr(cfg, "AI_TACTIC_MAX_SEQUENCE", 6)),
                )
                if new_plan:
                    self._log(cid, f"AI自行整理出戰術：{new_plan}")

            action = brain.select_action(state, actions, epsilon, action_biases)
            visits = country.setdefault("action_visits", {})
            visits[action] = int(visits.get(action, 0)) + 1

            success = False
            if action.startswith(("THEATRE:", "BUILD_OVERSEAS_PORT:")):
                success = self._theatre_action(country, action)
            elif action == "COLONIZE":
                founded = self._found_overseas_colonies(
                    selected_country_ids={cid},
                    force=True,
                    deterministic=False,
                    context=colony_context,
                )
                success = cid in founded
                if success and country.get("colonization_voyage"):
                    country["colonization_voyage"]["rl_state"] = list(state)
                    country["colonization_voyage"]["rl_action"] = "COLONIZE"
            elif action == "REINFORCE_OVERSEAS":
                success = cid in self._send_overseas_reinforcements(
                    selected_country_ids={cid}, force=True
                )
                if success and country.get("reinforcement_voyage"):
                    country["reinforcement_voyage"]["rl_state"] = list(state)
                    country["reinforcement_voyage"]["rl_action"] = "REINFORCE_OVERSEAS"
            elif action == "REST_AND_REPRODUCE":
                country["recovery_until_year"] = max(
                    int(country.get("recovery_until_year", 0)),
                    int(self.year + cfg.REST_DURATION_YEARS),
                )
                self._log(
                    cid,
                    f"戰略決策：休養生息{cfg.REST_DURATION_YEARS}年，集中恢復士氣、兵力與人口。",
                )
                success = True
            elif action.startswith("ATTACK:"):
                _kind, target_id, mode = action.split(":", 2)
                campaign = self.launch_campaign(cid, int(target_id), mode)
                if campaign:
                    self._dispatch_allied_reinforcements(cid, int(target_id), campaign.id)
                    success = True
                else:
                    # 目標在同一年被其他戰役拿走等情況，重新選一次合法行動，
                    # 但不允許因此跳過本次20年內的積極決策。
                    fallback_actions = [a for a in actions if a != action]
                    if fallback_actions:
                        action = brain.select_action(state, fallback_actions, epsilon, action_biases)
                        if action == "REST_AND_REPRODUCE":
                            country["recovery_until_year"] = int(self.year + cfg.REST_DURATION_YEARS)
                            success = True
                        elif action == "COLONIZE":
                            success = cid in self._found_overseas_colonies(
                                selected_country_ids={cid}, force=True,
                                deterministic=False, context=colony_context
                            )
                        elif action == "REINFORCE_OVERSEAS":
                            success = cid in self._send_overseas_reinforcements(
                                selected_country_ids={cid}, force=True
                            )

            if success:
                self._telemetry(country, "successful_decisions")
                if country.get("reinforcement_voyage") and action in ("REINFORCE_OVERSEAS", f"THEATRE:{country.get('strategic_focus_island')}:REQUEST_REINFORCEMENTS"):
                    country["reinforcement_voyage"]["rl_state"] = list(state)
                    country["reinforcement_voyage"]["rl_action"] = action
                brain.finish_plan_step()
            else:
                self._telemetry(country, "failed_decisions")
                key = brain.key(state, action)
                brain.q_values[key] = brain.q_values.get(key, 0.0) - cfg.AI_RL_ALPHA * .1
                brain.current_plan = []
                brain.current_plan_id = None

            country["last_ai_action"] = str(action)
            country["ai_decision_count"] = int(country.get("ai_decision_count", 0)) + 1
            history = list(country.get("ai_decision_years", []))
            history.append(int(self.year))
            country["ai_decision_years"] = history[-200:]
            gap_min = int(getattr(cfg, "AI_DECISION_MIN_YEARS", 1))
            gap_max = int(getattr(cfg, "AI_DECISION_MAX_YEARS", 20))
            country["next_ai_decision_year"] = int(
                max(self.year + self.rng.integers(gap_min, gap_max + 1),
                    country.get("recovery_until_year", 0) if action == "REST_AND_REPRODUCE" else self.year + 1)
            )
            brain.pending = {
                "state": list(state),
                "action": action,
                "metrics": metrics,
            }

    def _finalize_extinct_rl_brains(self):
        for country in self.countries:
            cid = int(country["id"])
            brain = self.rl_brains.get(cid)
            if brain is None or not brain.pending or country["alive"]:
                continue
            previous = brain.pending
            brain.update(
                previous["state"], previous["action"],
                self._rl_reward(
                    previous["metrics"], self._rl_metrics_for_country(country),
                    previous.get("action", PASS_ACTION),
                ),
                alpha=cfg.AI_RL_ALPHA, gamma=cfg.AI_RL_GAMMA,
                trace_lambda=cfg.AI_RL_TRACE_LAMBDA, terminal=True,
            )
            brain.pending = None

    def _ai_decisions(self):
        if self.year % cfg.AI_WAR_CHECK_INTERVAL:
            return
        alive = [c for c in self.countries if c["alive"]]
        # SARSA模式由各國自己的戰略大腦決定攻防，不再被舊版「霸權聯軍」
        # 規則在每一年額外插入戰爭；這也避免每年重算所有合法目標造成模擬瓶頸。
        if str(cfg.AI_MODE).upper() == "SARSA_LAMBDA":
            self._rl_war_decisions(alive)
            return

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
        colony_context = (
            self._colony_context()
            if self.year % max(1, cfg.COLONY_CHECK_INTERVAL) == 0 else None
        )
        for c in alive:
            if self.year < int(c.get("recovery_until_year", 0)):
                continue
            overseas_action = self._priority_overseas_action(c, colony_context)
            if overseas_action == "COLONIZE":
                self._found_overseas_colonies(
                    selected_country_ids={int(c["id"])}, force=True,
                    deterministic=True, context=colony_context,
                )
                continue
            if overseas_action and overseas_action.startswith("ATTACK:"):
                _kind, target_id, mode = overseas_action.split(":", 2)
                campaign = self.launch_campaign(int(c["id"]), int(target_id), mode)
                if campaign:
                    self._dispatch_allied_reinforcements(int(c["id"]), int(target_id), campaign.id)
                    continue
            population = max(1, int(c.get("population", 0)))
            soldier_ratio = float(c.get("soldiers", 0)) / population
            rest_chance = float(cfg.REST_ACTION_BASE_BIAS) + float(c.get("war_exhaustion", 0.0)) * 0.60
            rest_chance += max(0.0, 0.12 - soldier_ratio) * 2.0
            if float(c.get("morale", 1.0)) < 0.85:
                rest_chance += 0.12
            if self.rng.random() < min(0.80, rest_chance):
                c["recovery_until_year"] = int(self.year + cfg.REST_DURATION_YEARS)
                self._log(int(c["id"]), f"選擇休養生息{cfg.REST_DURATION_YEARS}年：停止發動新戰爭，集中恢復士氣、兵力與人口。")
                continue
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
                if ratio >= cfg.AI_UNIFICATION_MIN_POWER_RATIO:
                    total_land = max(1, sum(int(x["territory_cells"]) for x in alive))
                    target_share = int(target["territory_cells"]) / total_land
                    score += min(0.8, target_share * float(cfg.AI_UNIFICATION_TARGET_LAND_WEIGHT))
                    if target["territory_cells"] >= max(int(x["territory_cells"]) for x in alive):
                        score += 0.25
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
                    keep = sent.soldiers if sent.embarked_population else min(sent.soldiers, int(ally["soldiers"] * cfg.ALLIANCE_REINFORCEMENT_RATIO))
                    returned = sent.soldiers - keep
                    sent.soldiers = keep
                    sent.supply = sent.soldiers * sent.distance * cfg.SUPPLY_PER_SOLDIER_CELL
                    self._add_local_soldiers(
                        int(ally["id"]), int(sent.origin_landmass or self._home_continent_id(ally)),
                        returned, near=sent.origin,
                    )
                    self._sync_army_totals(int(ally["id"]))
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
                campaign.supply = max(0.0, campaign.supply - yearly_supply)
            else:
                survivors = int(campaign.soldiers * (1.0 - cfg.SUPPLY_SHORTAGE_ATTRITION))
                campaign.casualties += campaign.soldiers - survivors
                campaign.soldiers = survivors
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
        local_landmass_population = int(self.local_population.ravel()[
            self._spatial_indices(defender["id"], int(self.world.continent[y,x]))].sum())
        population_share = local_population / max(1, local_landmass_population)
        barracks_bonus = min(
            float(cfg.BARRACKS_GARRISON_MAX_BONUS),
            barracks * float(cfg.BARRACKS_GARRISON_SHARE_BONUS),
        )
        share = (
            float(cfg.BATTLE_BASE_GARRISON_SHARE)
            + min(1.0, population_share) * float(cfg.BATTLE_LOCAL_POPULATION_WEIGHT)
            + barracks_bonus
        )
        for site in defender.get("overseas_capitals", []):
            if self.year <= int(site.get("defensive_until",0)):
                point_xy=site.get("logistics_port") if site.get("defensive_focus")=="DEFEND_PORT" else site.get("anchor")
                if point_xy and self._wrapped_distance_cells((x,y),point_xy,width) <= radius:
                    share += .08  # allocate more of the same local army, never create soldiers
        return float(np.clip(share, 0.10, cfg.BATTLE_MAX_LOCAL_GARRISON_SHARE))

    def _battle(self, attackers: list[Campaign]):
        lead = attackers[0]
        defender = self.country(lead.defender)
        if not defender["alive"] or int(self.world.territory[lead.objective]) != lead.defender:
            for c in attackers:
                c.status = "cancelled"
                if c.embarked_population:
                    py,px = c.origin
                    if int(self.world.territory[py,px]) == c.attacker:
                        self.local_population[py,px] += max(0,c.embarked_population-c.casualties)
                self._add_local_soldiers(
                    int(c.attacker), int(c.origin_landmass or self._home_continent_id(self.country(c.attacker))),
                    int(c.soldiers), near=c.origin,
                )
                self.country(int(c.attacker))["fleet"] += int(c.fleet)
                self._sync_army_totals(int(c.attacker))
            return
        attack_power = 0.0
        for c in attackers:
            country = self.country(c.attacker)
            modifier = country["morale"]
            if c.mode == "naval":
                modifier *= 1.0 - cfg.AMPHIBIOUS_ATTACK_PENALTY
            attack_power += c.soldiers * modifier
        y, x = map(int, lead.objective)
        battle_landmass = int(self.world.continent[y, x])
        first_overseas_landing = bool(
            lead.mode == "naval"
            and battle_landmass > 0
            and battle_landmass not in self._overseas_landmass_ids(self.country(lead.attacker))
        )
        local_defender_soldiers = self._home_soldiers(int(defender["id"]), battle_landmass)
        terrain_bin = int(np.clip(self.world.terrain[y, x], 0, 6))
        estimated_local_share = self._local_garrison_share(defender, lead.objective)
        local_bin = 0 if estimated_local_share < 0.25 else 1 if estimated_local_share < 0.40 else 2 if estimated_local_share < 0.60 else 3
        incoming_ratio = sum(c.soldiers for c in attackers) / max(1, local_defender_soldiers)
        pressure_bin = 0 if incoming_ratio < 0.15 else 1 if incoming_ratio < 0.35 else 2 if incoming_ratio < 0.65 else 3
        value = int(self.world.city_value[y, x])
        value_bin = 0 if value < 25 else 1 if value < 50 else 2 if value < 75 else 3
        capital_x, capital_y = map(int, defender.get("capital", (x, y)))
        dx = min(abs(x - capital_x), self.world.settings.width - abs(x - capital_x))
        distance = math.hypot(y - capital_y, dx)
        distance_bin = 0 if distance < 30 else 1 if distance < 100 else 2 if distance < 300 else 3
        defense_state = (terrain_bin, local_bin, pressure_bin, value_bin, int(lead.mode == "naval"), distance_bin)
        defense_actions = [
            f"DEFEND:{int(round(share * 100))}"
            for share in cfg.BATTLE_LEARNED_GARRISON_SHARES
        ]
        defense_action = self._choose_tactical_action(
            int(defender["id"]), defense_state, defense_actions
        )
        learned_share = int(defense_action.split(":", 1)[1]) / 100.0
        local_share = min(
            float(cfg.BATTLE_MAX_LOCAL_GARRISON_SHARE),
            max(learned_share, self._local_garrison_share(defender, lead.objective))
            + max(0, len(attackers) - 1) * 0.04,
        )
        defending_soldiers = min(local_defender_soldiers, max(200, int(local_defender_soldiers * local_share)))
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
            attacker_country = self.country(c.attacker)
            c.soldiers = max(0, int(c.soldiers) - loss)
            c.casualties = int(c.casualties) + loss
            shock = float(cfg.WAR_EXHAUSTION_PER_BATTLE) + float(cfg.WAR_EXHAUSTION_CASUALTY_WEIGHT) * loss / max(1, int(attacker_country["population"]))
            attacker_country["war_exhaustion"] = float(np.clip(attacker_country.get("war_exhaustion", 0.0) + shock, 0.0, 1.0))
            attacker_country["morale"] = max(0.50, float(attacker_country.get("morale", 1.0)) - min(0.16, 0.035 + attack_loss_rate * 0.18))
            attack_losses += loss
            c.status = "won" if attacker_wins else "lost"
        defense_losses = min(defending_soldiers, int(defending_soldiers * defense_loss_rate))
        self._take_local_soldiers(int(defender["id"]), battle_landmass, defense_losses)
        defender_land = ((self.world.territory == int(defender["id"]))
                         & (self.world.continent == battle_landmass))
        self._remove_population_in_mask(defender_land, defense_losses)
        defense_shock = float(cfg.WAR_EXHAUSTION_PER_BATTLE) + float(cfg.WAR_EXHAUSTION_CASUALTY_WEIGHT) * defense_losses / max(1, int(defender["population"]))
        defender["war_exhaustion"] = float(np.clip(defender.get("war_exhaustion", 0.0) + defense_shock, 0.0, 1.0))
        defender["morale"] = max(0.50, float(defender.get("morale", 1.0)) - min(0.16, 0.035 + defense_loss_rate * 0.18))
        self.battles += 1
        if attacker_wins:
            winning_campaign = max(attackers, key=lambda c: c.soldiers)
            winner = winning_campaign.attacker
            loser_id = int(defender["id"])
            capture_center = lead.objective
        else:
            losing_campaign = max(attackers, key=lambda c: c.soldiers)
            winner = int(defender["id"])
            loser_id = int(losing_campaign.attacker)
            # 防方勝出代表打回前線並奪取主攻國的邊境領土，不再以「守住」結案。
            capture_center = losing_campaign.origin

        naval_landing = lead.mode == "naval"
        captured = 0
        if attacker_wins or not naval_landing:
            captured = self._capture_area(
                winner, loser_id, capture_center, total_attackers, naval_landing,
                initial_overseas_landing=first_overseas_landing and attacker_wins,
            )
            if captured <= 0:
                captured = self._capture_nearest_loser_cell(winner, loser_id, capture_center, naval_landing)
        # 戰役結束後，存活遠征軍留駐於戰區；敗軍撤回原出發陸塊。
        for campaign in attackers:
            attacker_country = self.country(campaign.attacker)
            destination_landmass = (battle_landmass if attacker_wins
                                    else int(campaign.origin_landmass or self._home_continent_id(attacker_country)))
            if campaign.embarked_population:
                destination = ((self.world.territory == campaign.attacker) & (self.world.continent == destination_landmass))
                cells = np.argwhere(destination)
                people = max(0,campaign.embarked_population-campaign.casualties)
                if len(cells) and people:
                    py,px = (campaign.objective if attacker_wins else campaign.origin)
                    if int(self.world.territory[py,px]) != campaign.attacker:
                        py,px = map(int,cells[0])
                    self.local_population[py,px] += people
            elif attacker_wins and int(campaign.transported_population) > 0:
                home = self._home_continent_id(attacker_country)
                source = ((self.world.territory == int(campaign.attacker))
                          & (self.world.continent == home))
                transported = self._remove_population_in_mask(source, int(campaign.transported_population))
                destination = ((self.world.territory == int(campaign.attacker))
                               & (self.world.continent == destination_landmass))
                cells = np.argwhere(destination)
                if transported and len(cells):
                    base, remainder = divmod(transported, len(cells))
                    self.local_population[destination] += base
                    if remainder:
                        self.local_population[cells[:remainder, 0], cells[:remainder, 1]] += 1
                    self._log(campaign.attacker, f"遠征勝利後由本島運送{transported:,}名人口至海外陸塊發展。")
            population_mask = ((self.world.territory == int(campaign.attacker))
                               & (self.world.continent == destination_landmass))
            if not campaign.embarked_population:
                self._remove_population_in_mask(population_mask, int(campaign.casualties))
            self._add_local_soldiers(
                campaign.attacker, destination_landmass, int(campaign.soldiers),
                near=(campaign.objective if attacker_wins else campaign.origin),
            )
            attacker_country["fleet"] += int(campaign.fleet)
        self._sync_army_totals(*(int(c.attacker) for c in attackers), int(defender["id"]))
        if attacker_wins and winning_campaign.mode == "naval" and captured > 0:
            victor = self.country(winner)
            by, bx = map(int, lead.objective)
            conquered_continent = int(self.world.continent[by, bx])
            if int(self.world.territory[by,bx]) != winner:
                foothold=np.argwhere((self.world.territory==winner)&(self.world.continent==conquered_continent))
                if len(foothold):
                    dx=np.minimum(abs(foothold[:,1]-bx),self.world.settings.width-abs(foothold[:,1]-bx))
                    by,bx=map(int,foothold[int(np.argmin((foothold[:,0]-by)**2+dx**2))])
            if (conquered_continent > 0
                    and conquered_continent != self._home_continent_id(victor)
                    and int(self.world.territory[by, bx]) == winner):
                sites = victor.setdefault("overseas_capitals", [])
                site = next((site for site in sites
                             if int(site.get("continent_id", -1)) == conquered_continent), None)
                if site is None:
                    site = {"anchor": [bx, by], "continent_id": conquered_continent,
                            "founded_year": int(self.year), "type": "海外征戰首都"}
                    sites.append(site)
                    self._telemetry(victor,"conquest_capitals_established")
                # Existing theatre anchor is stable; reinforcement never moves its capital.
                victor["overseas_capital"] = sites[0] if sites else None
                logistics_port = self._ensure_overseas_logistics_port(victor, site)
                port_text = (f"，並於附近建立固定增援港口{logistics_port}" if logistics_port else "")
                self._log(winner, f"在{self.geographic_name_at(by, bx)}登陸並建立海外首都{port_text}；目前持有{self._overseas_site_count(victor)}處，下一階段名額上限{self._overseas_expansion_capacity(victor)}處。")
        if naval_landing and not attacker_wins:
            self._log(lead.attacker, "海外登陸失敗：未取得灘頭領土，因此未建立海外首都。")
        winner_country = self.country(winner)
        loser_country = self.country(loser_id)
        winner_country["wars_won"] += 1
        loser_country["wars_lost"] += 1
        if not attacker_wins:
            for campaign in attackers:
                attacker_country = self.country(campaign.attacker)
                if campaign.attacker != loser_id:
                    attacker_country["wars_lost"] += 1
        outcome = f"{winner_country['name']}勝，奪取{captured:,}格；{loser_country['name']}喪失領土"
        self._resolve_capital_crisis(loser_country, winner)
        for campaign in attackers:
            attrition = campaign.soldiers / max(1, total_attackers)
            tactical_reward = (0.8 + min(0.6, captured / 1000.0)) if attacker_wins else -0.7
            tactical_reward -= min(0.5, attrition * attack_loss_rate)
            self._learn_tactical_action(
                campaign.attacker, campaign.tactical_state, campaign.tactical_action,
                tactical_reward,
            )
        defense_reward = 0.9 if not attacker_wins else -0.9 - min(0.5, captured / 2000.0)
        self._learn_tactical_action(
            int(defender["id"]), defense_state, defense_action, defense_reward
        )
        self.events.append(f"第{self.year}年｜戰役結束：{outcome}；攻方傷亡{attack_losses:,}、守方傷亡{defense_losses:,}。")
        for campaign in attackers:
            self._log(campaign.attacker, f"對{defender['name']}戰役：{outcome}；我軍傷亡約{int(campaign.soldiers * attack_loss_rate):,}。")
        self._log(defender["id"], f"遭受進攻：{outcome}；守軍傷亡{defense_losses:,}。")
        self._refresh_survival()

    def _capture_area(self, winner: int, loser: int, center, soldiers: int,
                      naval_landing: bool = False, initial_overseas_landing: bool = False) -> int:
        radius = int(np.clip(math.sqrt(max(1, soldiers)) / 5.0, cfg.CAPTURE_RADIUS_MIN, cfg.CAPTURE_RADIUS_MAX))
        y, x = center
        yy, xx = np.ogrid[:self.world.settings.height, :self.world.settings.width]
        dx = np.minimum(abs(xx - x), self.world.settings.width - abs(xx - x))
        disk = (yy - y) ** 2 + dx ** 2 <= radius * radius
        loser_land = self.world.territory == int(loser)
        winner_land = self.world.territory == int(winner)
        adjacent = self._adjacent_land_mask(winner_land)
        eligible = disk & loser_land
        if naval_landing:
            landmass_id = int(self.world.continent[int(y), int(x)])
            land_mask = (self.world.continent == landmass_id) & (self.world.terrain >= 2)
            if initial_overseas_landing:
                # 第一次海外立足不只搶敵方既有格，也可以占領同一島上的無主地；
                # 初次灘頭不受原本戰鬥半徑限制，直接向整個陸塊逐層擴張至約400格。
                eligible = land_mask & ((self.world.territory == int(loser)) | (self.world.territory == 0))
            else:
                eligible &= land_mask
        if initial_overseas_landing:
            # 第一次海外登陸直接建立約400格灘頭，而不是只靠士兵數量換取一小圈土地。
            # 仍以登陸點向外逐層擴張，避免瞬間跳到島嶼另一端。
            reached = np.zeros_like(eligible, dtype=bool)
            if eligible[int(y), int(x)]:
                reached[int(y), int(x)] = True
            target_cells = min(
                min(int(getattr(cfg, "OVERSEAS_INITIAL_CAPTURE_CELLS", 400)), max(1, int(soldiers) // 2)),
                int(np.count_nonzero(eligible)),
            )
            while int(reached.sum()) < target_cells:
                frontier = eligible & self._adjacent_land_mask(reached) & ~reached
                if not frontier.any():
                    break
                remaining = target_cells - int(reached.sum())
                coords = np.argwhere(frontier)
                if len(coords) <= remaining:
                    reached[frontier] = True
                else:
                    dy = coords[:, 0] - y
                    dx_raw = np.abs(coords[:, 1] - x)
                    dx = np.minimum(dx_raw, self.world.settings.width - dx_raw)
                    order = np.argsort(dy * dy + dx * dx)
                    pick = coords[order[:remaining]]
                    reached[pick[:, 0], pick[:, 1]] = True
        else:
            reached = eligible & adjacent
            if naval_landing and eligible[int(y), int(x)]:
                reached[int(y), int(x)] = True
            # Grow from the front/beachhead only. Each iteration advances one cell.
            for _ in range(max(0, radius - 1)):
                frontier = eligible & self._adjacent_land_mask(reached) & ~reached
                if not frontier.any():
                    break
                reached |= frontier
        broken_overseas_capitals = []
        defeated = self.country(loser)
        for site in defeated.get("overseas_capitals", []):
            anchor = site.get("anchor", (-1, -1))
            if len(anchor) != 2:
                continue
            ax, ay = map(int, anchor)
            if (0 <= ay < self.world.settings.height and 0 <= ax < self.world.settings.width
                    and int(self.world.territory[ay, ax]) == loser
                    and bool(reached[ay, ax])):
                broken_overseas_capitals.append((ax, ay))
        capture = reached
        count = int(capture.sum())
        self._mark_world_changed(winner, loser)
        self.world.territory[capture] = winner
        self.local_soldiers[capture] = 0
        self.building_owner[capture & (self.world.settlement > 0)] = winner
        if count:
            for country in self.countries:
                if country.get("alive"):
                    self._sync_overseas_capitals(country)
            # If the overseas capital falls, clear any defeated enclaves left on that island.
            for ax, ay in broken_overseas_capitals:
                land_id = int(self.world.continent[ay, ax])
                orphaned = ((self.world.continent == land_id)
                            & (self.world.territory == loser))
                self.world.territory[orphaned] = 0
                self.world.settlement[orphaned] = 0
                self.building_owner[orphaned] = 0
                self.local_population[orphaned] = 0
                self.local_soldiers[orphaned] = 0
            self._mark_world_changed(winner, loser)
        if count:
            self.world.border = _border_mask(self.world.territory)
            self._build_geography()
        return count

    @staticmethod
    def _adjacent_land_mask(territory_mask):
        return (np.roll(territory_mask, 1, axis=1) | np.roll(territory_mask, -1, axis=1)
                | np.pad(territory_mask[1:, :], ((0, 1), (0, 0)))
                | np.pad(territory_mask[:-1, :], ((1, 0), (0, 0))))

    def _capture_nearest_loser_cell(self, winner: int, loser: int, center,
                                    naval_landing: bool = False) -> int:
        """Take the nearest reachable border cell, or the specific naval port beachhead."""
        y, x = map(int, center)
        loser_land = self.world.territory == int(loser)
        eligible = loser_land & self._adjacent_land_mask(self.world.territory == int(winner))
        if naval_landing:
            radius = int(cfg.CAPTURE_RADIUS_MAX)
            yy, xx = np.ogrid[:self.world.settings.height, :self.world.settings.width]
            dx = np.minimum(abs(xx - x), self.world.settings.width - abs(xx - x))
            eligible |= (loser_land & (self.world.continent == int(self.world.continent[y, x]))
                         & ((yy - y) ** 2 + dx ** 2 <= radius ** 2))
        coords = np.argwhere(eligible)
        if not len(coords):
            return 0
        width = self.world.settings.width
        dy = coords[:, 0] - y
        dx = np.minimum(np.abs(coords[:, 1] - x), width - np.abs(coords[:, 1] - x))
        iy, ix = map(int, coords[int(np.argmin(dy * dy + dx * dx))])
        self.world.territory[iy, ix] = int(winner)
        self.local_soldiers[iy, ix] = 0
        self._mark_world_changed(winner, loser)
        self.world.border = _border_mask(self.world.territory)
        self._build_geography()
        for country in self.countries:
            if country.get("alive"):
                self._sync_overseas_capitals(country)
        return 1

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
            transit = sum(max(0,x.embarked_population-x.casualties) for x in self.campaigns
                          if x.attacker == cid and x.status == "marching")
            for voyage_key in ("colonization_voyage", "reinforcement_voyage"):
                voyage = c.get(voyage_key) or {}
                if voyage.get("embarked_population"):
                    transit += int(voyage.get("transported_population",0))
            c["population"] = int(populations[cid]) + transit
            owned_indices = self._spatial_indices(cid)
            self.local_soldiers.ravel()[owned_indices] = np.minimum(
                self.local_soldiers.ravel()[owned_indices], self.local_population.ravel()[owned_indices]
            )
            self._sync_army_totals(cid)
            if areas[cid] <= 0 or c["population"] <= 0:
                self._extinguish_country(c, None, "領土或人口歸零")

    def step(self, years: int = 1):
        for _ in range(max(1, int(years))):
            self.year += 1
            self.alerts.clear()
            self._clear_small_late_game_landmasses()
            self._economic_year()
            self._ensure_all_country_brains()
            if str(cfg.AI_MODE).upper() == "SARSA_LAMBDA":
                self._finalize_extinct_rl_brains()
            self._update_monarchs()
            self._theatre_year()
            self._ai_decisions()
            if str(cfg.AI_MODE).upper() != "SARSA_LAMBDA":
                self._found_overseas_colonies()
            self._advance_campaigns()
            self._advance_colony_voyages()
            self._advance_overseas_reinforcements()
            self._cleanup_overseas_exclaves()
            self._check_territorial_splits()
            self._check_power_splits()
            self._check_colony_independence()
            self._refresh_survival()
        return self.summary()

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
            building_owner=self.building_owner,
            local_population=self.local_population,
            local_soldiers=self.local_soldiers,
            geographic_region_id=self.geographic_region_id,
        )
        snapshot_id = uuid.uuid4().hex
        payload = {
            "version": "V22_5_海運顯示與登陸修正版",
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
            "game_version": "V22_5_海運顯示與登陸修正版",
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
        if payload.get("version") not in ("V6_拓荒戰爭UI版", "V7_王統分裂與遷都版", "V7_1_效能優化版", "V7_2_歐洲王室命名版", "V8_地理殖民與政權演化版", "V8_1_地名切換與歷史事件版", "V8_2_本土定位與殖民地連結版", "V8_3_地名歷史連結版", "V8_4_海外登陸戰版", "V9_國家獨立學習AI版", "V10_國家Q表獨立JSON版", "V11_海外擴張學習AI版", "V12_海權與戰區防禦版", "V12_1_本島定位與殖民節奏版", "V13_殖民航線與航行船隊版", "V13_1_十年批次推進版", "V13_2_逐年回報修正版", "V13_2_靜態航線與抵達日誌版", "V13_2_1_海外艦隊門檻與SARSA獎勵版", "V14_戰術學習與世界統一版", "V14_1_殖民與海外攻佔上限版", "V15_弱點攻防與休養生息版", "V17_大島優先與危急後撤版", "V17_1_本島統一與海外首都守則版", "V17_2_分裂小領土清空版", "V17_3_本土小飛地清空版", "V17_4_積極拓荒與勝者得地版", "V18_本島統一與首都存續版", "V18_逐階海外拓展與撤退版", "V19_逐階海外拓展與撤退版", "V19_地球地圖與海外撤退規則版", "V19_1_拓荒等級版", "V19_2_海外資格與危急後撤版", "V20_海外分帳與艦隊運輸版", "V20.2_自主戰略AI與海外戰術庫版", "V21_海外戰區長期學習版", "V21.1_海外殖民探索修正版", "V22_海外港口戰區策略版", "V22_1_拓荒與補給修正版", "V22_2_地方人口承載修正版", "V22_3_全島共用人口加成版", "V22_4_在地存糧人口承載版", "V22_5_海運顯示與登陸修正版"):
            raise ValueError("不支援此版本的戰爭存檔")
        if int(payload.get("seed", -1)) != int(world.settings.seed):
            raise ValueError("戰爭存檔與目前世界Seed不一致")
        engine = cls(world, path)
        with np.load(path.with_suffix(".npz")) as data:
            world.territory = data["territory"].copy()
            world.border = data["border"].copy()
            world.settlement = data["settlement"].copy()
            if "building_owner" in data.files:
                engine.building_owner = data["building_owner"].copy().astype(np.int32)
            else:
                engine.building_owner = np.where(world.settlement > 0, world.territory, 0).astype(np.int32)
            engine.local_population = data["local_population"].copy()
            has_local_soldiers = "local_soldiers" in data.files
            if has_local_soldiers:
                engine.local_soldiers = data["local_soldiers"].copy().astype(np.int32)
            if "geographic_region_id" in data.files:
                engine.geographic_region_id = data["geographic_region_id"].copy()
        engine._territory_epoch = getattr(engine, "_territory_epoch", 0) + 1
        engine.year = int(payload["year"])
        engine.next_campaign_id = int(payload["next_campaign_id"])
        engine.next_coalition_id = int(payload["next_coalition_id"])
        initialized = {c["id"]: c for c in engine.countries}
        engine.countries = list(payload["countries"])
        legacy_outposts = world.settlement == OUTPOST
        legacy_levels = np.bincount(
            world.territory[legacy_outposts].astype(np.int32),
            minlength=len(engine.countries) + 1,
        ) if np.any(legacy_outposts) else np.zeros(len(engine.countries) + 1, dtype=np.int64)
        world.countries = list(payload.get("world_countries", world.countries))
        for c in engine.countries:
            defaults = initialized.get(c["id"], {})
            meta = world.countries[c["id"] - 1]
            c.setdefault("capital", list(meta["capital"]))
            c.setdefault("capital_type", "本島首都")
            c.setdefault("retreat_voyage_used", bool((c.get("colonization_voyage") or {}).get("retreat", False)))
            c.setdefault("base_name", c["name"])
            c.setdefault("extinction_year", 0)
            c.setdefault("ever_extinct", not bool(c.get("alive", True)))
            c.setdefault("royal_surname", defaults.get("royal_surname", str(engine.rng.choice(ROYAL_SURNAMES))))
            c.setdefault("king_name", defaults.get("king_name", str(engine.rng.choice(ROYAL_GIVEN_NAMES)) + "．" + c["royal_surname"]))
            c.setdefault("king_number", defaults.get("king_number", 1))
            c.setdefault("king_since_year", defaults.get("king_since_year", engine.year))
            c.setdefault("king_next_year", defaults.get("king_next_year", engine.year + 80))
            c.setdefault("colonies", [])
            c.setdefault("overseas_capital", None)
            c.setdefault("overseas_capitals", [])
            old_level = int(c.pop("outposts", 0))
            c["frontier_level"] = max(
                int(c.get("frontier_level", 0)), old_level,
                int(legacy_levels[int(c["id"])]),
            )
            c.setdefault("overseas_expeditions_used", 0)
            for colony in c.get("colonies", []):
                colony["overseas_capital"] = True
            engine._sync_overseas_capitals(c)
            # 舊存檔沒有出海計數時，以目前已持有的海外首都及在途船隊補設最低值。
            if not c.get("overseas_expeditions_used"):
                inferred = max(
                    len(c.get("overseas_capitals", [])),
                    int(bool(c.get("colonization_voyage"))),
                )
                c["overseas_expeditions_used"] = min(int(cfg.OVERSEAS_EXPEDITION_LIMIT), inferred)
            c.setdefault("colonization_voyage", None)
            c.setdefault("reinforcement_voyage", None)
            c.setdefault("war_goal", "UNIFY_WORLD")
            c.setdefault("war_exhaustion", 0.0)
            c.setdefault("recovery_until_year", 0)
            c.setdefault("next_ai_decision_year", engine.year + int(engine.rng.integers(getattr(cfg, "AI_DECISION_MIN_YEARS", 1), getattr(cfg, "AI_DECISION_MAX_YEARS", 20) + 1)))
            c.setdefault("ai_decision_count", 0)
            c.setdefault("last_ai_action", "")
            c.setdefault("ai_decision_years", [])
            if "．" not in str(c.get("king_name", "")):
                c["royal_surname"] = str(engine.rng.choice(ROYAL_SURNAMES))
                c["king_name"] = str(engine.rng.choice(ROYAL_GIVEN_NAMES)) + "．" + c["royal_surname"]
        engine.campaigns = []
        for raw in payload["campaigns"]:
            raw["origin"] = tuple(raw["origin"])
            raw["objective"] = tuple(raw["objective"])
            engine.campaigns.append(Campaign(**raw))
        if not has_local_soldiers:
            engine.local_soldiers = np.zeros_like(engine.local_population, dtype=np.int32)
            for c in engine.countries:
                cid = int(c["id"])
                at_sea = sum(int(x.soldiers) for x in engine.campaigns
                             if x.attacker == cid and x.status == "marching")
                stationed = max(0, int(c.get("soldiers", 0)) - at_sea)
                coords = np.argwhere((world.territory == cid) & (engine.local_population > 0))
                if not len(coords) or not stationed:
                    continue
                weights = engine.local_population[coords[:, 0], coords[:, 1]].astype(np.float64)
                allocation = np.floor(weights / max(1.0, weights.sum()) * stationed).astype(np.int32)
                remainder = stationed - int(allocation.sum())
                if remainder:
                    allocation[np.argsort(weights)[-remainder:]] += 1
                engine.local_soldiers[coords[:, 0], coords[:, 1]] = allocation
        engine.events = list(payload.get("events", []))
        engine.history_events = list(payload.get("history_events", []))
        engine.country_events = {int(k): list(v) for k, v in payload.get("country_events", {}).items()}
        engine.battles = int(payload.get("battles", 0))
        engine.alliance_names = {int(k): str(v) for k, v in payload.get("alliance_names", engine.alliance_names).items()}
        engine.disconnected_since = {int(k): int(v) for k, v in payload.get("disconnected_since", {}).items()}
        engine.territory_dirty = {int(c["id"]) for c in engine.countries}
        engine._land_totals_dirty = True
        engine.visual_revision = int(payload.get("visual_revision", 0))
        if np.any(legacy_outposts):
            world.settlement[legacy_outposts] = 0
            engine.building_owner[legacy_outposts] = 0
            engine.visual_revision += 1
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
        engine._sync_army_totals()
        engine._build_geography()
        return engine
