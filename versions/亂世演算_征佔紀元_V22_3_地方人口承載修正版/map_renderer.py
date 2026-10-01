"""將地形陣列渲染為具有簡單陰影的 PNG。"""

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from terrain_rules import TERRAIN_COLORS
from climate_rules import BIOME_COLORS, LAKE, RIVER


def render_map(terrain: np.ndarray, height: np.ndarray, output_path=None) -> Image.Image:
    rgb = TERRAIN_COLORS[terrain].astype(np.float32)

    # 高度梯度形成柔和地貌陰影；海洋降低陰影避免水面顯得髒亂。
    gy, gx = np.gradient(height.astype(np.float32))
    shade = np.clip(1.0 + (-gx * 1.8 - gy * 1.2), 0.72, 1.22)
    shade[terrain <= 1] = 1.0
    rgb *= shade[..., None]

    # 淺海依水深稍微調亮，讓海岸輪廓更清楚。
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    image = Image.fromarray(rgb, mode="RGB")
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, optimize=True)
    return image


def _gradient(values, stops):
    values = np.clip(values, 0.0, 1.0)
    positions = np.linspace(0.0, 1.0, len(stops), dtype=np.float32)
    colors = np.asarray(stops, dtype=np.float32)
    result = np.empty(values.shape + (3,), dtype=np.float32)
    for channel in range(3):
        result[..., channel] = np.interp(values, positions, colors[:, channel])
    return np.clip(result, 0, 255).astype(np.uint8)


def render_environment(world, layer="生態環境", output_path=None):
    """渲染V2圖層：生態、溫度、濕度、降雨或基礎地形。"""
    score_layers = {
        "農業價值": (world.agriculture, ((79, 52, 33), (184, 111, 47), (224, 194, 77), (104, 168, 75), (31, 111, 57))),
        "木材價值": (world.timber, ((225, 215, 174), (151, 172, 92), (71, 133, 67), (28, 91, 55), (11, 57, 39))),
        "礦產價值": (world.minerals, ((39, 42, 49), (84, 82, 80), (139, 119, 91), (196, 156, 83), (242, 211, 120))),
        "淡水供應": (world.freshwater, ((117, 80, 48), (188, 159, 91), (99, 170, 171), (40, 118, 177), (18, 55, 125))),
        "建城價值": (world.city_value, ((45, 29, 67), (91, 59, 125), (163, 103, 151), (226, 167, 100), (250, 230, 128))),
        "防禦價值": (world.defense_value, ((238, 225, 181), (195, 166, 105), (133, 116, 95), (87, 83, 85), (42, 48, 62))),
    }
    if layer in ("國家與領土", "純領土歸屬", "國家領土"):
        rgb = BIOME_COLORS[world.biome].astype(np.float32)
        rgb[world.terrain <= 1] = TERRAIN_COLORS[world.terrain[world.terrain <= 1]]
        rgb[world.water == LAKE] = (39, 128, 184)
        rgb[world.water == RIVER] = (53, 151, 210)
        alpha = float(getattr(__import__("map_config"), "TERRITORY_ALPHA", 0.34))
        if layer == "純領土歸屬":
            rgb[world.terrain >= 2] = (105, 105, 105)
            alpha = 1.0
        for country in world.countries:
            mask = world.territory == int(country["id"])
            color = np.asarray(country["color"], dtype=np.float32)
            rgb[mask] = rgb[mask] * (1.0 - alpha) + color * alpha
        rgb[world.border > 0] = (31, 27, 35)
        rgb[world.roads > 0] = (111, 72, 40)
        rgb[world.sea_routes > 0] = (91, 220, 235)
        capital = ndimage.binary_dilation(world.settlement == 1, iterations=3)
        city = ndimage.binary_dilation(world.settlement == 2, iterations=2)
        port = ndimage.binary_dilation(world.settlement == 3, iterations=2)
        barracks = ndimage.binary_dilation(world.settlement == 4, iterations=2)
        rgb[city] = (244, 241, 222)
        rgb[port] = (61, 220, 235)
        rgb[barracks] = (220, 72, 64)
        rgb[capital] = (255, 209, 54)
        image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    elif layer in score_layers:
        values, colors = score_layers[layer]
        rgb = _gradient(values.astype(np.float32) / 100.0, colors)
        rgb[world.terrain <= 1] = TERRAIN_COLORS[world.terrain[world.terrain <= 1]]
        image = Image.fromarray(rgb, mode="RGB")
    elif layer == "移動成本":
        normalized = np.where(world.movement_cost == 255, 1.0, np.clip((world.movement_cost.astype(np.float32) - 1.0) / 19.0, 0.0, 1.0))
        rgb = _gradient(normalized, ((55, 145, 75), (176, 190, 81), (230, 181, 69), (185, 81, 48), (65, 54, 68)))
        rgb[world.movement_cost == 255] = TERRAIN_COLORS[0]
        image = Image.fromarray(rgb, mode="RGB")
    elif layer == "基礎地形":
        image = render_map(world.terrain, world.height)
    elif layer == "溫度":
        normalized = np.clip((world.temperature + 25.0) / 65.0, 0.0, 1.0)
        rgb = _gradient(normalized, ((35, 70, 160), (100, 190, 220), (235, 238, 190), (226, 145, 55), (155, 38, 32)))
        image = Image.fromarray(rgb, mode="RGB")
    elif layer == "濕度":
        rgb = _gradient(world.humidity, ((145, 104, 62), (205, 181, 116), (100, 166, 132), (38, 106, 145), (22, 55, 112)))
        rgb[world.terrain <= 1] = TERRAIN_COLORS[world.terrain[world.terrain <= 1]]
        image = Image.fromarray(rgb, mode="RGB")
    elif layer == "降雨":
        rgb = _gradient(world.rainfall / 3600.0, ((222, 193, 132), (151, 191, 126), (70, 160, 155), (42, 100, 170), (73, 45, 137)))
        rgb[world.terrain <= 1] = TERRAIN_COLORS[world.terrain[world.terrain <= 1]]
        image = Image.fromarray(rgb, mode="RGB")
    else:
        rgb = BIOME_COLORS[world.biome].copy()
        rgb[world.terrain <= 1] = TERRAIN_COLORS[world.terrain[world.terrain <= 1]]
        rgb[world.water == LAKE] = (39, 128, 184)
        rgb[world.water == RIVER] = (53, 151, 210)
        image = Image.fromarray(rgb, mode="RGB")
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, optimize=True)
    return image
