"""Headless continuation with periodic checkpoints and reload verification."""
from pathlib import Path
import argparse
import collections
import copy
import hashlib
import json
import shutil
import time

import numpy as np

from map_generator import load_world
from war_engine import WarEngine


def file_hashes(folder):
    return {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest()
        for f in folder.iterdir() if f.is_file()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", type=Path, required=True, help="原始存檔資料夾")
    parser.add_argument("--output", type=Path, required=True, help="輸出及檢查點資料夾")
    parser.add_argument("--years", type=int, default=500, help="總共推進年數")
    parser.add_argument("--checkpoint-every", type=int, default=100)
    parser.add_argument("--resume", action="store_true", help="由 output 中最近檢查點續跑")
    parser.add_argument("--cache-assert-every", type=int, default=0,
                        help="Debug：每 N 年全掃描並核對已建立的 WorldStateCache；0 表示停用")
    args = parser.parse_args()
    if args.years < 0 or args.checkpoint_every < 1 or args.cache_assert_every < 0:
        raise SystemExit("years 必須非負、checkpoint-every 必須大於 0，cache-assert-every 必須非負")
    if args.save.resolve() == args.output.resolve():
        raise SystemExit("output 必須與原始存檔不同")

    source_hashes = file_hashes(args.save)
    progress_path = args.output / "simulation_progress.json"
    args.output.mkdir(parents=True, exist_ok=True)
    if args.resume:
        if not progress_path.exists() or not (args.output / "war_state.json").exists():
            raise SystemExit("找不到可續跑的檢查點")
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        origin_year = int(progress["start_year"])
        engine = WarEngine.load(load_world(args.output), args.output / "war_state.npz")
    else:
        if any(args.output.iterdir()):
            raise SystemExit("輸出資料夾非空；如要接續請加 --resume")
        for name in ("world_map.npz", "world_map_info.json"):
            shutil.copyfile(args.save / name, args.output / name)
        engine = WarEngine.load(load_world(args.save), args.save / "war_state.npz")
        origin_year = int(engine.year)
        progress = {"start_year": origin_year, "target_years": args.years}

    if engine.year < origin_year:
        raise SystemExit("檢查點年份早於原始起始年")
    completed = engine.year - origin_year
    if completed > args.years:
        raise SystemExit("檢查點已超過指定總年數")

    started = time.perf_counter()
    actions = collections.Counter()
    executions = []
    phase_years = collections.Counter()
    initial_alive = sum(bool(c["alive"]) for c in engine.countries)
    initial_counters = {
        c["id"]: dict(c.get("strategy_counters", {})) for c in engine.countries
    }
    remaining = args.years - completed
    checkpoint_at = completed + args.checkpoint_every

    for offset in range(remaining):
        engine.step(1)
        if args.cache_assert_every and (engine.year - origin_year) % args.cache_assert_every == 0:
            engine.world_state_cache.debug_assert_consistent()
        assert np.all(engine.local_population >= 0)
        assert np.all(engine.local_soldiers >= 0)
        assert np.all(engine.local_soldiers <= engine.local_population)
        for country in engine.countries:
            if not country["alive"]:
                continue
            assert country["food"] >= -1e-6 and country["fleet"] >= 0
            goal = country.get("macro_goal", {})
            phase_years[(country["id"], goal.get("goal_type", "PENDING"))] += 1
            event = country.get("macro_last_execution", {})
            if event.get("year") == engine.year:
                actions[event["policy"]] += 1
                executions.append({"id": country["id"], **event})

        total_done = engine.year - origin_year
        if total_done >= checkpoint_at or offset + 1 == remaining:
            engine.save(args.output / "war_state.npz")
            progress = {
                "start_year": origin_year,
                "target_years": args.years,
                "completed_years": total_done,
                "current_year": engine.year,
                "checkpoint_seconds_this_session": round(time.perf_counter() - started, 2),
            }
            progress_path.write_text(
                json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"checkpoint +{total_done}y year={engine.year}", flush=True)
            checkpoint_at = total_done + args.checkpoint_every

    elapsed = time.perf_counter() - started
    for brain in engine.rl_brains.values():
        for key in brain.q_values:
            assert ":" not in key.split("|")[-1], key

    engine.save(args.output / "war_state.npz")
    reloaded = WarEngine.load(load_world(args.output), args.output / "war_state.npz")
    assert [c.get("macro_goal") for c in engine.countries] == [
        c.get("macro_goal") for c in reloaded.countries
    ]
    assert [c.get("strategic_commitment") for c in engine.countries] == [
        c.get("strategic_commitment") for c in reloaded.countries
    ]
    final_countries = copy.deepcopy(engine.countries)
    engine.step(2)
    reloaded.step(2)
    np.testing.assert_array_equal(engine.world.territory, reloaded.world.territory)
    np.testing.assert_array_equal(engine.local_population, reloaded.local_population)
    np.testing.assert_array_equal(engine.local_soldiers, reloaded.local_soldiers)
    assert engine.countries == reloaded.countries
    assert engine.rng.bit_generator.state == reloaded.rng.bit_generator.state
    assert all(
        brain.to_dict() == reloaded.rl_brains[cid].to_dict()
        for cid, brain in engine.rl_brains.items()
    )
    assert file_hashes(args.save) == source_hashes

    report = {
        "start_year": origin_year,
        "end_year": origin_year + args.years,
        "years": args.years,
        "seconds_this_session": round(elapsed, 2),
        "initial_alive": initial_alive,
        "actions": dict(actions),
        "executions": executions,
        "phase_years": {f"{cid}:{phase}": n for (cid, phase), n in phase_years.items()},
        "original_unchanged": True,
        "reload_plus_2_years_equivalent": True,
        "target_free_q_keys": True,
        "world_state_cache": {
            "hits": engine.world_state_cache.hits,
            "misses": engine.world_state_cache.misses,
            "debug_assert_every_years": args.cache_assert_every,
        },
        "countries": [
            {
                "id": c["id"], "name": c["name"], "alive": c["alive"],
                "territory": c.get("territory_cells"), "population": c.get("population"),
                "soldiers": c.get("soldiers"), "fleet": c.get("fleet"),
                "goal": c.get("macro_goal"),
                "commitment": c.get("strategic_commitment"),
                "history": c.get("macro_history", []),
                "counters": {
                    key: value - initial_counters.get(c["id"], {}).get(key, 0)
                    for key, value in c.get("strategy_counters", {}).items()
                },
            }
            for c in final_countries if c["alive"]
        ],
    }
    (args.output / "sanity_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("PASS", round(elapsed, 2), dict(actions), flush=True)


if __name__ == "__main__":
    main()
