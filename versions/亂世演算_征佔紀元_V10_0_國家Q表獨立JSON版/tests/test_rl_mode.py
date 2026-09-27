"""V10 國家獨立 Q 表 JSON 存取與 Expected SARSA(lambda) 回歸測試。"""

import tempfile
import unittest
import json
from pathlib import Path

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
            self.assertEqual(saved_payload["version"], "V10_國家Q表獨立JSON版")
            brains_path = WarEngine._rl_brains_path(save_path)
            self.assertTrue(brains_path.exists())
            brain_payload = json.loads(brains_path.read_text(encoding="utf-8"))
            self.assertEqual(brain_payload["game_version"], "V10_國家Q表獨立JSON版")
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
                str(cid): brain.to_dict() for cid, brain in engine.rl_brains.items()
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
                {cid: brain.to_dict()["q_values"] for cid, brain in engine.rl_brains.items()},
            )
            # 沒有 rl_brains 欄位的舊 V8.4 存檔仍可載入，並建立空白獨立大腦。
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
        state, actions, _priors = engine._rl_state_and_actions(first["id"])
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
