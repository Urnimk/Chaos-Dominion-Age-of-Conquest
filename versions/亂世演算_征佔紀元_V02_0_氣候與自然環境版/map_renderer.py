"""將地形陣列渲染為具有簡單陰影的 PNG。"""

from pathlib import Path

import numpy as np
from PIL import Image

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
    if layer == "基礎地形":
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
