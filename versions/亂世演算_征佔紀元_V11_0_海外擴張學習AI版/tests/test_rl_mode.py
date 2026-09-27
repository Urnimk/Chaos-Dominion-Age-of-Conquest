"""V11 海外攻擊、殖民行動與獨立 Q 表 JSON 回歸測試。"""

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import map_config as cfg
from map_generator import MapSettings, generate_world
from rl_brain import CountryBrain, PASS_ACTION
from war_engine import WarEngine


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
        cfg.AI_MIN_POWER_RATIO = 1.08

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
            self.assertEqual(saved_payload["version"], "V11_海外擴張學習AI版")
            self.assertNotIn("rl_brains", saved_payload)
            brains_path = WarEngine._rl_brains_path(save_path)
            self.assertTrue(brains_path.exists())
            brain_payload = json.loads(brains_path.read_text(encoding="utf-8"))
            self.assertEqual(brain_payload["game_version"], "V11_海外擴張學習AI版")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
