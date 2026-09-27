"""V12.1 地圖定位、殖民限制、海權與獨立 Q 表 JSON 回歸測試。"""

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy import ndimage
import map_config as cfg
from map_generator import MapSettings, generate_world
from rl_brain import CountryBrain, PASS_ACTION
from war_engine import Campaign, WarEngine
from country_generator import BARRACKS, PORT
from map_viewer import _capital_landmass_mask


class CountryBrainTests(unittest.TestCase):
    def test_state_rejects_more_than_four_dimensions(self):
        with self.assertRaises(ValueError):
            CountryBrain.key((0, 1, 2, 3, 4), PASS_ACTION)

    def test_country_brains_have_independent_values_and_updates(self):
        first = CountryBrain(100)
        second = CountryBrain(200)
        state = (0, 1, 2, 3)
        first.update(state, PASS_ACTION, reward=1.0, terminal=True)
        self.assertNotEqual(first.q_values, second.q_values)
        self.assertEqual(second.value(state, PASS_ACTION), 0.0)

    def test_action_bias_applies_even_when_q_values_already_exist(self):
        brain = CountryBrain(300)
        state = (0, 0, 0, 0)
        brain.q_values[CountryBrain.key(state, PASS_ACTION)] = 0.08
        brain.q_values[CountryBrain.key(state, "ATTACK:2:naval")] = 0.03
        selected = brain.select_action(
            state, [PASS_ACTION, "ATTACK:2:naval"], epsilon=0.0,
            action_biases={"ATTACK:2:naval": 0.06},
        )
        self.assertEqual(selected, "ATTACK:2:naval")


class MapFocusTests(unittest.TestCase):
    def test_capital_focus_excludes_colony_even_when_same_country_owns_it(self):
        territory = np.zeros((8, 12), dtype=np.int32)
        continent = np.zeros_like(territory)
        territory[1:4, 1:4] = 1
        continent[1:4, 1:4] = 7
        territory[1:4, 8:11] = 1
        continent[1:4, 8:11] = 9
        focus = _capital_landmass_mask(territory, continent, 1, (2, 2))
        self.assertEqual(int(focus.sum()), 9)
        self.assertFalse(focus[:, 8:].any())


class RLEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_count = cfg.COUNTRY_COUNT
        cls.old_mode = cfg.AI_MODE
        cls.old_epsilon = cfg.AI_RL_EPSILON
        cls.old_min_epsilon = cfg.AI_RL_MIN_EPSILON
        cls.old_power_ratio = cfg.AI_MIN_POWER_RATIO
        cfg.COUNTRY_COUNT = 8
        cfg.AI_RL_EPSILON = 0.0
        cfg.AI_RL_MIN_EPSILON = 0.0
        cfg.AI_MIN_POWER_RATIO = 0.85

    @classmethod
    def tearDownClass(cls):
        cfg.COUNTRY_COUNT = cls.old_count
        cfg.AI_MODE = cls.old_mode
        cfg.AI_RL_EPSILON = cls.old_epsilon
        cfg.AI_RL_MIN_EPSILON = cls.old_min_epsilon
        cfg.AI_MIN_POWER_RATIO = cls.old_power_ratio

    def make_engine(self, seed=20260927):
        world = generate_world(MapSettings(width=256, height=256, seed=seed, world_style="BALANCED"))
        return WarEngine(world)

    def setUp(self):
        cfg.AI_MODE = "RULE"

    def test_rule_mode_remains_default_and_rl_mode_updates_each_brain(self):
        engine = self.make_engine()
        self.assertEqual(cfg.AI_MODE, "RULE")
        self.assertEqual(len(engine.rl_brains), len(engine.countries))

        cfg.AI_MODE = "RULE"
        engine.step(25)
        self.assertEqual(sum(brain.decisions for brain in engine.rl_brains.values()), 0)

        cfg.AI_MODE = "SARSA_LAMBDA"
        engine.step(100)
        self.assertTrue(all(len(engine._rl_state_and_actions(c["id"])[0]) == 4 for c in engine.countries if c["alive"]))
        self.assertTrue(all(brain.decisions > 0 for cid, brain in engine.rl_brains.items() if engine.country(cid)["alive"]))
        self.assertGreater(sum(brain.updates for brain in engine.rl_brains.values()), 0)
        self.assertEqual(len({id(brain) for brain in engine.rl_brains.values()}), len(engine.rl_brains))
        self.assertTrue(all(c[k] >= 0 for c in engine.countries for k in ("food", "timber", "minerals")))

        with tempfile.TemporaryDirectory() as temp:
            save_path = Path(temp) / "rl_smoke"
            engine.save(save_path)
            saved_payload = json.loads(save_path.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(saved_payload["version"], "V12_1_本島定位與殖民節奏版")
            self.assertNotIn("rl_brains", saved_payload)
            brains_path = WarEngine._rl_brains_path(save_path)
            self.assertTrue(brains_path.exists())
            brain_payload = json.loads(brains_path.read_text(encoding="utf-8"))
            self.assertEqual(brain_payload["game_version"], "V12_1_本島定位與殖民節奏版")
            self.assertEqual(set(brain_payload["brains"]), {str(cid) for cid in engine.rl_brains})
            saved_payload["rl_brains"] = {}
            save_path.with_suffix(".json").write_text(
                json.dumps(saved_payload, ensure_ascii=False), encoding="utf-8"
            )
            loaded = WarEngine.load(engine.world, save_path)
            self.assertEqual(len(loaded.rl_brains), len(engine.rl_brains))
            self.assertEqual(
                {cid: brain.to_dict()["q_values"] for cid, brain in loaded.rl_brains.items()},
                {cid: brain.to_dict()["q_values"] for cid, brain in engine.rl_brains.items()},
            )
            payload = json.loads(save_path.with_suffix(".json").read_text(encoding="utf-8"))
            payload["rl_brains"] = {
                str(cid): {"q_values": {"old|legacy": 999.0}}
                for cid in engine.rl_brains
            }
            payload.pop("rl_brains_snapshot_id", None)
            payload["version"] = "V9_國家獨立學習AI版"
            save_path.with_suffix(".json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            brains_path.unlink()
            legacy_v9_loaded = WarEngine.load(engine.world, save_path)
            self.assertEqual(
                {cid: brain.to_dict()["q_values"] for cid, brain in legacy_v9_loaded.rl_brains.items()},
                {cid: {} for cid in engine.rl_brains},
            )
            # V8.4 世界／戰局資料仍可載入，但舊內嵌 Q 表一律不讀。
            json_path = save_path.with_suffix(".json")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            payload.pop("rl_brains", None)
            payload["version"] = "V8_4_海外登陸戰版"
            json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            old_save_loaded = WarEngine.load(engine.world, save_path)
            self.assertEqual(len(old_save_loaded.rl_brains), len(old_save_loaded.countries))
            self.assertTrue(all(not brain.q_values for brain in old_save_loaded.rl_brains.values()))

        q_before_rule_switch = {cid: dict(brain.q_values) for cid, brain in engine.rl_brains.items()}
        updates_before_rule_switch = sum(brain.updates for brain in engine.rl_brains.values())
        cfg.AI_MODE = "RULE"
        engine.step(25)
        self.assertEqual(sum(brain.updates for brain in engine.rl_brains.values()), updates_before_rule_switch)
        self.assertEqual({cid: brain.q_values for cid, brain in engine.rl_brains.items()}, q_before_rule_switch)

    def test_rl_can_choose_a_target_and_new_country_gets_new_brain(self):
        engine = self.make_engine(seed=20260928)
        first, second = engine.countries[:2]
        first["population"] = 5000
        first["soldiers"] = 2500
        first["fleet"] = 100
        second["population"] = 1000
        second["soldiers"] = 100
        first_capital = tuple(reversed(first["capital"]))
        second_capital = tuple(reversed(second["capital"]))
        engine.maritime_links[(first["id"], second["id"])] = (1.0, first_capital, second_capital)
        state, actions, _biases = engine._rl_state_and_actions(first["id"])
        attack = f"ATTACK:{second['id']}:naval"
        self.assertIn(attack, actions)
        engine.rl_brains[first["id"]].q_values[CountryBrain.key(state, attack)] = 100.0
        cfg.AI_MODE = "SARSA_LAMBDA"
        engine.year = cfg.AI_WAR_CHECK_INTERVAL
        engine._ai_decisions()
        self.assertTrue(any(c.attacker == first["id"] and c.defender == second["id"] for c in engine.campaigns))

        # 分裂新增的政權取得全新 Q 表，不複製母國學習資料。
        mask = engine.world.territory == first["id"]
        yy, xx = mask.nonzero()
        split_x = int(sorted(xx)[len(xx) // 2])
        separated = mask.copy()
        separated[:, :split_x] = False
        retained = mask & ~separated
        if not separated.any() or not retained.any():
            self.skipTest("固定 Seed 的初始領土不足以切成兩個非空區塊")
        old_count = len(engine.countries)
        engine._split_country(first, retained, separated, rename_old=False, forced_new_name="測試新國")
        new_id = old_count + 1
        self.assertIn(new_id, engine.rl_brains)
        self.assertIsNot(engine.rl_brains[new_id], engine.rl_brains[first["id"]])
        self.assertEqual(engine.rl_brains[new_id].q_values, {})

    def test_rl_can_choose_colonization_as_an_action(self):
        engine = self.make_engine(seed=20260929)
        country = engine.countries[0]
        cid = int(country["id"])
        country["ports"] = max(1, int(country.get("ports", 0)))
        country["fleet"] = max(20, int(country["fleet"]))
        country["food"] = max(500.0, float(country["food"]))
        country["timber"] = max(500.0, float(country["timber"]))
        engine.year = cfg.COLONY_CHECK_INTERVAL
        context = {
            "neutral": engine.world.territory == 0,
            "coastal": engine.world.territory == 0,
            "occupied_continents": set(),
        }
        candidate = np.array([[0, 0]], dtype="int32")
        with patch.object(engine, "_colony_context", return_value=context), \
                patch.object(engine, "_colony_candidates", return_value=candidate), \
                patch.object(engine, "_found_overseas_colonies", return_value={cid}) as found:
            state, actions, biases = engine._rl_state_and_actions(cid, colony_available=True)
            self.assertIn("COLONIZE", actions)
            self.assertGreater(biases["COLONIZE"], biases[PASS_ACTION])
            engine.rl_brains[cid].q_values[CountryBrain.key(state, "COLONIZE")] = 100.0
            cfg.AI_MODE = "SARSA_LAMBDA"
            engine._rl_war_decisions([country])
            self.assertEqual(engine.rl_brains[cid].pending["action"], "COLONIZE")
            found.assert_called_once_with(
                selected_country_ids={cid}, force=True, deterministic=True, context=context
            )

    def test_colony_cooldown_and_six_colony_cap_apply_to_both_ai_modes(self):
        engine = self.make_engine(seed=20260930)
        country = engine.countries[0]
        cid = int(country["id"])
        country.update(ports=1, fleet=100, food=1000.0, timber=1000.0)
        owned_yx = np.argwhere(engine.world.territory == cid)
        self.assertGreaterEqual(len(owned_yx), cfg.COLONY_MAX_PER_COUNTRY)
        anchors = []
        for y, x in owned_yx[:cfg.COLONY_MAX_PER_COUNTRY]:
            anchors.append({"anchor": [int(x), int(y)], "founded_year": 100})
        country["colonies"] = anchors[:1]
        country["last_colony_founded_year"] = 100
        for mode in ("RULE", "SARSA_LAMBDA"):
            cfg.AI_MODE = mode
            country["colonies"] = anchors[:1]
            engine.year = 179
            self.assertFalse(engine._colony_country_eligible(country))
            engine.year = 180
            self.assertTrue(engine._colony_country_eligible(country))
            country["colonies"] = []
            engine.year = 179
            self.assertFalse(engine._colony_country_eligible(country))
            country["colonies"] = anchors
            self.assertFalse(engine._colony_country_eligible(country))

    def test_coastal_country_builds_port_before_more_frontier_buildings(self):
        engine = self.make_engine(seed=551)
        country = next(c for c in engine.countries if c["alive"])
        cid = country["id"]
        owned = engine.world.territory == cid
        engine.world.settlement[owned] = 0
        sea = engine.world.terrain <= 1
        coast = ndimage.binary_dilation(sea, iterations=1) & (engine.world.terrain >= 2)
        y, x = map(int, np.argwhere(coast)[0])
        engine.world.territory[y, x] = cid
        engine.world.settlement[y, x] = 0
        engine.world.countries[cid - 1]["ports"] = []
        country.update(ports=0, fleet=0, food=100000.0, timber=100000.0, minerals=100000.0)
        old_port_limit = cfg.PORTS_PER_COUNTRY
        cfg.PORTS_PER_COUNTRY = 1
        try:
            engine._construct_building(country)
            self.assertEqual(int(engine.world.settlement[y, x]), PORT)
            self.assertEqual(country["ports"], 1)
            self.assertEqual(country["fleet"], cfg.INITIAL_FLEET_PER_PORT)

            before = country["fleet"]
            engine._construct_building(country)
            self.assertEqual(country["fleet"], min(
                before + cfg.FLEET_BUILD_BATCH, cfg.FLEET_CAPACITY_PER_PORT
            ))
        finally:
            cfg.PORTS_PER_COUNTRY = old_port_limit

    def test_local_population_and_barracks_raise_defensive_garrison(self):
        engine = self.make_engine(seed=552)
        defender = next(c for c in engine.countries if c["alive"])
        cid = defender["id"]
        y, x = map(int, np.argwhere(engine.world.territory == cid)[0])
        engine.local_population[:] = 0
        engine.local_population[y, x] = 100
        defender.update(population=100, soldiers=1000)
        without_barracks = engine._local_garrison_share(defender, (y, x))
        engine.world.settlement[y, x] = BARRACKS
        with_barracks = engine._local_garrison_share(defender, (y, x))
        self.assertGreater(with_barracks, without_barracks)
        self.assertGreaterEqual(cfg.BATTLE_RANDOMNESS, 0.20)

    def test_battle_randomness_can_reverse_a_narrow_power_edge(self):
        def result_for_rolls(rolls):
            engine = self.make_engine(seed=553)
            attacker, defender = engine.countries[:2]
            attacker.update(alive=True, morale=1.0, population=1000, soldiers=500)
            defender.update(alive=True, morale=1.0, population=1000, soldiers=1000)
            class FixedRng:
                def __init__(self, values):
                    self.values = iter(values)
                def uniform(self, _low, _high):
                    return next(self.values)
            engine.rng = FixedRng(rolls)
            campaign = Campaign(1, attacker['id'], defender['id'], 'land', (0, 0), (0, 0),
                                250, 0, 1.0, 1, 0.0)
            with patch.object(engine, '_local_garrison_share', return_value=0.22), \
                    patch.object(engine, '_terrain_defense', return_value=1.0), \
                    patch.object(engine, '_remove_population'), \
                    patch.object(engine, '_capture_area', return_value=0), \
                    patch.object(engine, '_resolve_capital_crisis'), \
                    patch.object(engine, '_refresh_survival'):
                engine._battle([campaign])
            return attacker['wars_won'] == 1

        self.assertTrue(result_for_rolls((1.22, 0.78)))
        self.assertFalse(result_for_rolls((0.78, 1.22)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
