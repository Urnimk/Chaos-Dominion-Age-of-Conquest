"""氣候、生態區與內陸水體代碼。"""

import numpy as np

OCEAN = 0
DESERT = 1
GRASSLAND = 2
FOREST = 3
SNOW = 4
TUNDRA = 5
SWAMP = 6

BIOME_NAMES = {
    OCEAN: "海洋",
    DESERT: "沙漠",
    GRASSLAND: "草原",
    FOREST: "森林",
    SNOW: "雪地",
    TUNDRA: "凍土",
    SWAMP: "沼澤",
}

BIOME_COLORS = np.array(
    [
        (20, 68, 112),    # 海洋
        (207, 177, 103),  # 沙漠
        (139, 174, 82),   # 草原
        (42, 112, 63),    # 森林
        (235, 241, 244),  # 雪地
        (156, 168, 151),  # 凍土
        (57, 108, 92),    # 沼澤
    ],
    dtype=np.uint8,
)

WATER_NONE = 0
LAKE = 1
RIVER = 2
WATER_NAMES = {WATER_NONE: "無", LAKE: "湖泊", RIVER: "河流"}


def biome_name(code):
    return BIOME_NAMES.get(int(code), f"未知生態({code})")


def water_name(code):
    return WATER_NAMES.get(int(code), f"未知水體({code})")
