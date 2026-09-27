"""將地形陣列渲染為具有簡單陰影的 PNG。"""

from pathlib import Path

import numpy as np
from PIL import Image

from terrain_rules import TERRAIN_COLORS


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

