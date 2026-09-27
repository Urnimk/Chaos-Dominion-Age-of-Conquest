"""地形代碼、名稱與顏色。所有格子只存 uint8 代碼。"""

import numpy as np

DEEP_OCEAN = 0
SHALLOW_OCEAN = 1
BEACH = 2
PLAIN = 3
HILL = 4
MOUNTAIN = 5
HIGH_MOUNTAIN = 6

TERRAIN_NAMES = {
    DEEP_OCEAN: "深海",
    SHALLOW_OCEAN: "淺海",
    BEACH: "海灘",
    PLAIN: "平原",
    HILL: "丘陵",
    MOUNTAIN: "山地",
    HIGH_MOUNTAIN: "高山",
}

# RGB 配色刻意採自然但具遊戲辨識度的色階。
TERRAIN_COLORS = np.array(
    [
        (15, 47, 87),    # 深海
        (31, 99, 145),   # 淺海
        (218, 201, 139), # 海灘
        (91, 151, 82),   # 平原
        (118, 126, 72),  # 丘陵
        (105, 91, 78),   # 山地
        (222, 224, 221), # 高山
    ],
    dtype=np.uint8,
)


def terrain_name(code: int) -> str:
    return TERRAIN_NAMES.get(int(code), f"未知地形({code})")

