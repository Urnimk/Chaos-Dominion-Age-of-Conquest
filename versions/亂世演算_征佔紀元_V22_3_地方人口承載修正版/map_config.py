"""《亂世演算_征佔紀元》V21.1 海外殖民探索修正版。"""
import random

MAP_WIDTH = 1200
MAP_HEIGHT = 1200
COUNTRY_COUNT = 16  # 開局國家數量；調高會增加地圖生成、外交、戰爭與UI運算量。
MAP_CELL_SIZE_KM = 1.0     # 每個地圖格代表 1 公里；預設地圖寬度約 2,000 公里。
OVERSEAS_EXPEDITION_LIMIT = 10000           # 僅保留為歷史統計相容欄位；V21 不再作為終身出海上限。
OVERSEAS_CAPITAL_MAX_PER_COUNTRY = 99    # 相容舊存檔欄位；實際出海名額依本土／海外統一階段動態計算。
OVERSEAS_REGION_CONTROL_SHARE_REQUIRED = 0.80 # 海外/本土均以至少80%且無其他政權判定完整控制。 # 本島／海外陸塊控制須嚴格超過八成，且無其他政權。
OVERSEAS_INITIAL_EXPEDITION_SLOTS = 1   # 本土統一後先取得一個海外擴張名額。
OVERSEAS_MAJOR_LANDMASS_MIN_CELLS = 3000 # 海外大島門檻：陸塊至少包含此數量土地格。
OVERSEAS_COLONY_MIN_LANDMASS_CELLS = 300 # 一般殖民可選無人小島的最低面積；小於此值只作緊急後撤。
OVERSEAS_MAJOR_LANDMASS_LARGEST_RATIO = 0.015 # 或至少達最大陸塊面積的此比例，即視為大島。
OVERSEAS_PREFERRED_LANDMASS_COUNT = 3   # 從合格陸塊中優先考慮面積最大的幾處。
OVERSEAS_RETREAT_HOME_MAX_CELLS = 300   # 本土剩餘格數降至此值以下時，可把小島作緊急後撤點。
OVERSEAS_RETREAT_INITIAL_HOME_SHARE = 0.25 # 本土低於開局面積此比例時，開始評估緊急後撤。
OVERSEAS_RETREAT_LAST_CAPITAL_MAX_CELLS = 1000 # 本土少於此格、只剩首都且沒有城市時，額外觸發緊急後撤。
OVERSEAS_RETREAT_BASE_CHANCE = 0.42     # 後撤基礎成功率；安全港口與艦隊可提高，避免危局時過低。
OVERSEAS_RETREAT_PORT_THREAT_RADIUS = 4 # 敵軍控制區距港口此格數內，視為港口受威脅。
OVERSEAS_EXPANSION_REQUIRES_HOMELAND_UNIFIED = True # 本島沒有其他政權後，才可殖民或發動海外征服。
LATE_GAME_SMALL_TERRITORY_CLEANUP_YEAR = 3000 # 世界年曆到此年份後開始清除微型領土。
LATE_GAME_SMALL_LANDMASS_MAX_CELLS = 3000 # 年滿3000年後，地理陸塊小於此格數即清空其領土。
TERRITORY_SPLIT_MIN_FRACTION = 0.25 # 任一分裂主體達原國土1/4即可保留並形成新政權。 # 領土分裂後，任一部分小於分裂前總面積此比例即清空。
# ANNUAL_POPULATION_GROWTH = 0.01         # 基礎人口成長率降為每年0.2%。
POPULATION_GROWTH = 10                   # 每年生10人
REST_BIRTH_GROWTH_MULTIPLIER = 3        # 休養生息時提高出生速度，仍受糧食承載量限制。




# MAP_WIDTH = 200
# MAP_HEIGHT = 200
# COUNTRY_COUNT = 2  # 開局國家數量；調高會增加地圖生成、外交、戰爭與UI運算量。


# 每次啟動都產生新種子；需要重現世界時，改成固定整數即可。
MAP_SEED = random.SystemRandom().randint(1, 2**31 - 1)

WORLD_STYLE_OPTIONS = (
    "BALANCED",        # 均衡世界
    "SUPERCONTINENT",  # 超級大陸
    "ARCHIPELAGO",     # 群島世界
    "FRACTURED",       # 破碎大陸
    "INLAND_SEAS",     # 內海世界
    "TWIN_CONTINENTS", # 雙大陸世界
    "EARTH_MAP",       # 仿地球大陸輪廓
)


# # 相同 Seed 固定抽到相同風格，不影響世界生成器後續的亂數序列。
# WORLD_STYLE = random.Random(MAP_SEED).choice(WORLD_STYLE_OPTIONS)

WORLD_STYLE = "ARCHIPELAGO"


# 海陸、大陸與島嶼。
TARGET_OCEAN_RATIO = 0.70
CONTINENT_CORE_MIN = 4
CONTINENT_CORE_MAX = 9
MIN_ISLAND_AREA = 24
COAST_SMOOTHING_ITERATIONS = 1

# 地形形狀。
DOMAIN_WARP_STRENGTH = 0.055
CONTINENT_NOISE_STRENGTH = 0.42
COAST_DETAIL_STRENGTH = 0.18
ISLAND_CHAIN_STRENGTH = 0.12

# 板塊與山系。
TECTONIC_PLATE_MIN = 9
TECTONIC_PLATE_MAX = 16
MOUNTAIN_STRENGTH = 0.22
MOUNTAIN_WIDTH = 9.0

# 地形分類相對海平面的高度。
DEEP_OCEAN_DEPTH = 0.12
BEACH_HEIGHT = 0.025
PLAIN_HEIGHT = 0.16
HILL_HEIGHT = 0.30
MOUNTAIN_HEIGHT = 0.34

# 顯示與存檔。
CHUNK_SIZE = 256
PREVIEW_FILENAME = "world_map_preview.png"
DATA_FILENAME = "world_map.npz"
INFO_FILENAME = "world_map_info.json"

# 第二階段：水文密度（以2000×2000為基準，小地圖會按面積縮放）。
LAKE_COUNT = 18
RIVER_SOURCE_COUNT = 85

# 第四階段：國家、領土與交通。
COUNTRY_MIN_DISTANCE_RATIO = 0.075
MIN_COUNTRY_LANDMASS_CELLS = 12000
TERRITORY_RADIUS_RATIO = 0.42
TERRITORY_ALPHA = 0.34
TERRITORY_CELLS_PER_CITY = 45000
MAX_CITIES_PER_COUNTRY = 5
PORTS_PER_COUNTRY = 2
CITY_MIN_DISTANCE = 60              # 城市與首都間至少相隔的地圖格數。
BARRACKS_MIN_DISTANCE = 20          # 兵營彼此至少相隔的地圖格數。

# 第五階段：時間、人口、資源與軍事。
WAR_START_YEAR = 1
INITIAL_POPULATION_PER_CELL = 2.4
INITIAL_SOLDIER_RATIO = 0.001
INITIAL_FLEET_PER_PORT = 18

REST_DURATION_YEARS = 10                  # 選擇休養後，至少40年不發起新戰爭。
REST_EXHAUSTION_RECOVERY = 0.025          # 休養時每年恢復的戰爭疲乏。
PASSIVE_EXHAUSTION_RECOVERY = 0.002      # 平時緩慢恢復戰爭疲乏。
REST_MORALE_RECOVERY = 0.012              # 休養時每年士氣恢復幅度。
WAR_EXHAUSTION_PER_BATTLE = 0.12          # 每場戰爭至少累積的疲乏。
WAR_EXHAUSTION_CASUALTY_WEIGHT = 0.35     # 傷亡越重，疲乏越高。
WAR_EXHAUSTION_RECRUIT_PENALTY = 0.65     # 疲乏降低徵兵效率。
REST_ACTION_BASE_BIAS = 0.08              # 讓AI能考慮和平休養。
ANNUAL_RECRUIT_RATIO = 0.005          # 基礎徵兵速度下調，減少長期兵力快速回補。
RECRUIT_SLOWDOWN_START_YEAR = 1000    # 後期徵兵自此逐步放慢。
RECRUIT_SLOWDOWN_FULL_YEAR = 5000     # 到此年份降至後期最低倍率。
LATE_GAME_RECRUIT_MIN_MULTIPLIER = 0.25
MIN_GARRISON_RATIO = 0.035

# 糧食經濟：所有已控制的可居住格都按農業值生產，人口成長受承載量限制。
FOOD_PRODUCTION_MULTIPLIER = 1.15
FOOD_CONSUMPTION_PER_PERSON = 0.18
FOOD_GROWTH_RESERVE_RATIO = 0.90
CITY_FOOD_PRODUCTIVITY_BONUS = 0.015
MAX_CITY_FOOD_PRODUCTIVITY_BONUS = 0.30
FOOD_CAPACITY_BONUS_PER_PERSON = 100_000  # 每十萬人口糧食承載量提供100%成長與徵兵加成。

# 行軍與補給。距離以地圖格計，1回合等於1年。
LAND_MARCH_CELLS_PER_YEAR = 38.0
SEA_MARCH_CELLS_PER_YEAR = 75.0
NAVAL_OPERATION_RANGE = 620.0
SUPPLY_PER_SOLDIER_CELL = 0.000018
SUPPLY_SHORTAGE_ATTRITION = 0.12
MOUNTAIN_DEFENSE_BONUS = 0.55
HILL_DEFENSE_BONUS = 0.22
RIVER_DEFENSE_BONUS = 0.12
AMPHIBIOUS_ATTACK_PENALTY = 0.28

# AI與戰爭節奏。
AI_MODE = "SARSA_LAMBDA"  # RULE 保留目前AI；SARSA_LAMBDA 使用各國獨立 Expected SARSA(lambda) 大腦，納入遠征與殖民選擇。
AI_RL_ALPHA = 0.12
AI_RL_GAMMA = 0.92
AI_RL_TRACE_LAMBDA = 0.65
AI_RL_EPSILON = 0.12
AI_RL_MIN_EPSILON = 0.04
AI_RL_EPSILON_DECAY_DECISIONS = 300
OVERSEAS_MIN_FLEET = 301           # 嚴格大於 300 艘才可殖民或發動海外戰爭。
OVERSEAS_RL_REWARD_MULTIPLIER = 2.0 # SARSA 海外戰爭與殖民行動的轉移獎勵倍率。
AI_RL_NAVAL_ACTION_BIAS = 0.05       # SARSA海外征戰探索先驗；實際選擇仍由Q值與探索率決定。
AI_RL_COLONY_ACTION_BIAS = 0.05       # 未嘗試殖民的資訊價值；不是永久人格偏好。
AI_RL_COLONY_OPENING_BIAS = 0.45      # 最低探索加成；另依舊 Q 值補足，避免殖民永遠輸給休養。
AI_RL_OVERSEAS_REINFORCE_BIAS = 0.35 # 已有海外戰區且缺兵時，優先鞏固戰區而非到處另開登陸點。     # SARSA殖民探索先驗；與海戰先驗同級，避免固定偏向任一行動。

# V21 長期戰略學習：事件完成後才回饋原始決策。
AI_RL_DELAYED_COLONY_SUCCESS_REWARD = 1.20
AI_RL_DELAYED_REINFORCEMENT_SUCCESS_REWARD = 0.45
AI_RL_DELAYED_OVERSEAS_PACIFY_REWARD = 1.60
AI_RL_WORLD_PROGRESS_REWARD_WEIGHT = 0.75
AI_RL_WORLD_PROGRESS_MILESTONE_STEP = 0.10
AI_RL_UNSEEN_COLONY_NOVELTY = 0.10
AI_RL_UNSEEN_OVERSEAS_NOVELTY = 0.05

AI_OVERSEAS_EXPANSION_PRIORITY = True # RULE模式使用海外行動評分；SARSA模式由Q值在殖民與征戰間學習選擇。
AI_WAR_CHECK_INTERVAL = 1
AI_BASE_WAR_CHANCE = 0.10 # 舊RULE模式保留；SARSA模式改由20年內強制決策控制。
AI_MIN_ATTACK_SOLDIERS = 20          # 800人門檻高於多數國家的早期軍隊規模，會使AI永遠無法開戰。
AI_MIN_POWER_RATIO = 0.85             # AI 允許以低於對手總戰力的兵力開戰，戰果由局部防守與戰場波動決定。
AI_UNIFICATION_MIN_POWER_RATIO = 0.55 # 統一世界目標下，只跳過遠低於自身戰力的自殺式攻勢。
AI_UNIFICATION_TARGET_LAND_WEIGHT = 1.2 # 持續把AI導向可逐步吞併的對手。
AI_MAX_ACTIVE_CAMPAIGNS = 2
COALITION_THREAT_SHARE = 0.16
COALITION_MAX_MEMBERS = 5
CAPTURE_RADIUS_MIN = 10
CAPTURE_RADIUS_MAX = 36
BATTLE_RANDOMNESS = 0.22             # 優勢兵力仍可能因地形與戰況波動落敗。
BATTLE_BASE_GARRISON_SHARE = 0.22    # 每場戰鬥至少投入的本土防守兵力比例。
BATTLE_LOCAL_POPULATION_WEIGHT = 0.35 # 戰區人口占比提高當地可集結的守軍比例。
BATTLE_MAX_LOCAL_GARRISON_SHARE = 0.75
BATTLE_LEARNED_GARRISON_SHARES = (0.10, 0.25, 0.40, 0.55, 0.70)
TACTICAL_ATTACK_FRACTIONS = (0.18, 0.28, 0.40, 0.55, 0.70)
TACTICAL_LEARNING_ALPHA = 0.10
TACTICAL_EXPLORATION = 0.08
TACTICAL_WEAK_FRONT_WEIGHT = 1.0          # 目標選擇優先攻擊守備較薄弱的接壤地區。
BARRACKS_BATTLE_RADIUS = 24          # 戰區附近此距離內的兵營可支援防守。
BARRACKS_GARRISON_SHARE_BONUS = 0.08 # 每座附近兵營增加的當地守軍比例。
BARRACKS_GARRISON_MAX_BONUS = 0.24
BARRACKS_POSITION_DEFENSE_BONUS = 0.06
CITY_POSITION_DEFENSE_BONUS = 0.06

# 聯盟援軍需要實際行軍；援助比例不會瞬間加到戰場。
ALLIANCE_COUNT = 6
ALLIANCE_REINFORCEMENT_RATIO = 0.18

# V6時間與UI：1回合=1年，正常速度每2秒推進1年。
SECONDS_PER_YEAR = 0.5
AUTO_RUN_ON_START = True
COUNTRY_NAME_FONT_SIZE = 12
COUNTRY_NAME_FONT_BOLD = True
COUNTRY_NAME_OUTLINE_WIDTH = 2
MAP_BUILDING_ICON_SIZE = 1               # 首都、兵營與港口的地圖圖示尺寸。
LEFT_PANEL_WIDTH = 330
RIGHT_PANEL_WIDTH = 430
UI_REFRESH_EVERY_YEARS = 1

# V7 國家延續、遷都、分裂與君主制度（皆為可調整的全域變數）。
CAPITAL_RELOCATION_MIN_CITIES = 2       # 首都失守後，至少需多少座剩餘城市才能推舉新王。
CAPITAL_RELOCATION_CITY_RADIUS = 80     # 判斷城市群密集程度的半徑（地圖格）。
CAPITAL_RELOCATION_MIN_TERRITORY = 50  # 允許遷都的最低剩餘領土格數。
CAPITAL_RELOCATION_MIN_POPULATION = 80 # 允許遷都的最低剩餘人口。
TERRITORY_SPLIT_GRACE_YEARS = 10       # 主要領土斷裂持續幾年後才正式分裂。
TERRITORY_SPLIT_CHECK_INTERVAL = 20    # 每隔幾年檢查領土斷裂與本土小飛地。
TERRITORY_SPLIT_MIN_CELLS = 12         # 每個分裂主體至少需要的領土格數。
TERRITORY_SPLIT_MIN_SHARE = 0.25       # 每個分裂主體至少占原國領土的比例。
KING_REIGN_MIN_YEARS = 5               # 國王最短在位年數。
KING_REIGN_MAX_YEARS = 80              # 國王最長在位年數；每任隨機落在5～80年。

# V8 地理命名、強國分裂與海外殖民。
GEOGRAPHIC_LABEL_MIN_CELLS = 120       # 地圖上直接顯示名稱的最小地理區域；小區域仍可點擊查詢。
GEOGRAPHIC_MAX_VISIBLE_LABELS = 80      # 同一畫面最多顯示的地理名稱，避免文字淹沒地圖。
POWER_SPLIT_CHECK_INTERVAL = 25         # 每隔幾年檢查一次強國內部分裂事件。
POWER_SPLIT_TOP_RANKS = 1               # 只有領土排名前幾名可能發生內部分裂。
POWER_SPLIT_CHANCE = 0.003              # 每次檢查時每個強國的分裂機率。
POWER_SPLIT_MIN_TERRITORY = 80000       # 強國至少擁有多少格領土才可能分裂。
REGIME_SPLIT_PROTECTED_TOP_RANKS = 0 # 不再因「前三名」直接免疫分裂。   # 國力前三名不因長期領土分隔而觸發政權分裂。
COLONY_CHECK_INTERVAL = 5               # 每隔幾年檢查海外殖民行動。
COLONY_FOUND_CHANCE = 0.90              # 有港口、艦隊與資源時，更積極啟動殖民遠征。
COLONY_COOLDOWN_YEARS = 40              # 所有 AI 模式共用的殖民間隔。
COLONY_MAX_PER_COUNTRY = 99             # 相容舊存檔欄位；實際擴張名額由海外陸塊平定進度動態控制。
COLONY_SHIP_SPEED_KM_PER_YEAR = 10.0    # 殖民船每模擬年航行 10 公里（預設每年十格）。
COLONY_MIN_FLEET = 8                    # 發起殖民所需的最低可用艦隊。
COLONY_TRANSPORT_FLEET = 5              # 每次殖民轉為殖民地駐留艦隊的數量。
COLONY_SETTLER_POPULATION = 30          # 每次海外殖民預計運送的移民人數。
COLONY_INITIAL_CELLS = 24               # 殖民地開局占領的最大土地格數。
COLONY_MIN_DISTANCE = 60                # 殖民地與本國首都的最低距離（地圖格）；小型群島世界也能殖民。
COLONY_PRIORITIZE_EMPTY_ISLANDS = True  # 優先派艦隊前往尚無任何國家落腳的大陸或島嶼。
COLONY_AUTO_PORT = True                 # 海外殖民地成立時自動建立殖民港，供艦隊補給與敵軍登陸。
COLONY_FOOD_COST = 80.0                 # 殖民遠征消耗的糧食。
COLONY_TIMBER_COST = 60.0               # 殖民船隊與據點消耗的木材。
COLONY_INDEPENDENCE_MIN_YEARS = 1000    # 殖民地成立多久後才可能獨立。
COLONY_INDEPENDENCE_CHECK_INTERVAL = 20 # 每隔幾年檢查殖民地獨立。
COLONY_INDEPENDENCE_CHANCE = 0.001      # 成熟殖民地每次檢查的獨立機率。

# V8_4 海外戰爭：有港口的攻方可直接對敵國沿海領土實施登陸。
NAVAL_COASTAL_LANDING_ENABLED = True    # 守方即使沒有港口，也能被敵方艦隊選為沿海登陸目標。
AI_NAVAL_TARGET_BONUS = 0.35            # AI評估可跨海目標時的額外分數，避免所有國家長期龜在本土。

# V6拓荒：開局只有首都周圍的小型核心領土。
INITIAL_TERRITORY_RADIUS = 7
INITIAL_TERRITORY_MAX_CELLS = 150
EXPANSION_INTERVAL_YEARS = 5            # 每年被動檢查；國土鄰接空地且有資源即自動拓荒。
BASE_EXPANSION_CELLS = 6                # 每次拓荒的基本格數，並受人口、資源與邊境候選限制。
EXPANSION_CELLS_PER_SOLDIER = 6         # 軍力支援的領土容量。
EXPANSION_FOOD_COST_PER_CELL = 0.5      # 每拓一格的糧食成本。
EXPANSION_TIMBER_COST_PER_CELL = 0.2    # 每拓一格的木材成本。
SETTLER_POPULATION_PER_CELL = 1

# 建築會增加影響範圍或軍事拓荒能力。
BUILDING_CHECK_INTERVAL_YEARS = 50
CITY_AREA_PER_BUILDING = 180
BARRACKS_AREA_PER_BUILDING = 130
FRONTIER_LEVEL_AREA_PER_LEVEL = 100       # 每累積此面積，可提升一級拓荒等級。
CITY_EXPANSION_BONUS = 2
BARRACKS_EXPANSION_BONUS = 3
FRONTIER_LEVEL_EXPANSION_BONUS = 5       # 每級增加每次陸上拓荒可取得的格數。
CITY_COST = (80.0, 120.0, 45.0)       # 糧食、木材、礦產
BARRACKS_COST = (55.0, 75.0, 90.0)
FRONTIER_LEVEL_COST = (35.0, 55.0, 25.0) # 拓荒等級升級成本：糧食、木材、礦產。
PORT_COST = (60.0, 130.0, 70.0)
FLEET_CAPACITY_PER_PORT = 180         # 兩座港口可蓄至360艘，能跨過既有301艘海外門檻。
FLEET_BUILD_BATCH = 18                # 每次補充的艦艇數量，縮短海外遠征前的等待。
FLEET_BUILD_COST = (12.0, 30.0, 18.0) # 糧食、木材、礦產。
OVERSEAS_SOLDIERS_PER_SHIP = 1000      # 每艘艦艇一次可運送的士兵數，出海軍隊不得超出艦隊載量。
OVERSEAS_POPULATION_PER_SHIP = 1000    # 每艘艦艇一次可運送的人口數；建立海外首都需運送本國人口四分之一。
OVERSEAS_REINFORCEMENT_CHECK_YEARS = 10 # AI每隔此年數檢查海外駐軍，依缺口決定是否派艦增援。
OVERSEAS_GARRISON_TARGET_RATIO = 0.015
# V20.2 戰略AI：積極決策節奏與海外登陸規則
AI_DECISION_MIN_YEARS = 1
AI_DECISION_MAX_YEARS = 20
AI_DECISION_FORCE_ACTIVE = True
OVERSEAS_INITIAL_CAPTURE_CELLS = 400       # 第一次成功海外登陸直接建立400格灘頭。
OVERSEAS_INITIAL_POPULATION_RATIO = 1 / 3  # 首次海外征戰勝利後運送本島人口的1/3。
OVERSEAS_REINFORCEMENT_MAX_ISLAND_POP_RATIO = 0.50  # 海外駐軍最多占該島人口一半。
OVERSEAS_REINFORCEMENT_HOME_MIN_POP_RATIO = 0.50    # 本島至少保留一半人口，不得為增援抽乾。
OVERSEAS_REINFORCEMENT_MAX_SOLDIER_RATIO = 0.50     # 同一海外陸塊最多累積至其人口一半的駐軍。
AI_STRATEGIC_STATE_DIMENSIONS = 6
AI_TACTIC_MIN_SEQUENCE = 2
AI_TACTIC_MAX_SEQUENCE = 6
AI_TACTIC_POSITIVE_REWARD = 0.15
 # 海外駐軍目標：該陸塊人口的1.5%，上限仍受本島可用兵與艦隊載量限制。

# V22: explicit theatre state/actions (9 dimensions), no country-specific bonuses.
AI_STRATEGIC_STATE_DIMENSIONS = 9
COLONY_AUTO_PORT = False  # Overseas ports are paid, explicit strategic actions.
OVERSEAS_COLONY_MIN_LANDMASS_CELLS = MIN_ISLAND_AREA
OVERSEAS_PEACE_GARRISON_RATIO = 0.12
OVERSEAS_ENEMY_GARRISON_RATIO = 0.65
OVERSEAS_PORT_MAX_DISTANCE = 60
OVERSEAS_SECOND_PORT_MIN_DISTANCE = 12
OVERSEAS_SUPPLY_BUFFER_YEARS = 20
OVERSEAS_SUPPLY_GRACE_YEARS = 10
OVERSEAS_ISOLATION_ATTRITION = 0.02
OVERSEAS_DEFENSE_DURATION = 12
AI_STRATEGIC_REVIEW_YEARS = 60
AI_INFORMATION_REVIEW_BIAS = 0.6
ALLIANCE_STRATEGIC_REVIEW_YEARS = 100

OVERSEAS_FOOD_PER_SHIP = 10000.0  # capacity for actual transported food stocks
