"""V5快速回歸測試：執行後應顯示「全部通過」。"""

from pathlib import Path
import tempfile

import numpy as np

from map_generator import MapSettings, generate_world
from war_engine import WarEngine


def run():
    settings = MapSettings(width=256, height=256, seed=50505, world_style="BALANCED")
    first_world = generate_world(settings)
    second_world = generate_world(settings)
    first = WarEngine(first_world)
    second = WarEngine(second_world)
    first.step(60)
    second.step(60)

    assert np.array_equal(first_world.territory, second_world.territory)
    assert first.countries == second.countries
    assert np.all(first_world.territory[first_world.terrain <= 1] == 0)
    assert all(0 <= c["soldiers"] <= c["population"] for c in first.countries)
    for country in first.countries:
        committed = sum(x.soldiers for x in first.campaigns if x.attacker == country["id"] and x.status == "marching")
        assert committed <= country["soldiers"]

    for country in first.countries:
        country["fleet"] = 0
        assert not any(t["mode"] == "naval" for t in first.legal_targets(country["id"]))

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "war"
        second.save(path)
        restored = WarEngine.load(second_world, path)
        restored.step(10)
        assert restored.year == 71

    print("V5戰爭核心測試：全部通過")


if __name__ == "__main__":
    run()
