"""可持續存檔的國家級 Expected SARSA(lambda) 大腦與自創戰術庫。"""

from __future__ import annotations

import copy
import numpy as np


# 戰略層採 12 維離散狀態。刻意不用原始地圖像素，避免 Q 表狀態爆炸；
# 地圖資訊先壓縮成「本土控制、鄰國威脅、海外機會、海外駐軍缺口」等可解釋特徵。
STATE_DIMENSIONS = 6
PASS_ACTION = "PASS"


def action_kind(action: str) -> str:
    """把帶目標參數的原子動作壓成戰術庫可理解的動作類型。"""
    if action.startswith("ATTACK:"):
        return "ATTACK_NAVAL" if action.endswith(":naval") else "ATTACK_LAND"
    if action == "COLONIZE":
        return "COLONIZE"
    if action == "REINFORCE_OVERSEAS":
        return "REINFORCE_OVERSEAS"
    if action == "REST_AND_REPRODUCE":
        return "REST"
    return "PASS"


class CountryBrain:
    """單一國家的獨立 Q 表、探索亂數、資格跡線與 AI 自創戰術庫。

    戰術庫不是人類寫死的「人格」：它只記錄這個國家自己反覆嘗試後，
    發現有正回報的動作序列。使用時仍由當前 Q 值與合法動作共同決定。
    """

    def __init__(self, seed: int):
        self.rng = np.random.default_rng(int(seed))
        self.q_values: dict[str, float] = {}
        self.eligibility: dict[str, float] = {}
        self.tactical_q_values: dict[str, float] = {}

        # 自創戰術：plan_id -> {sequence, score, uses, successes}
        self.tactical_library: dict[str, dict] = {}
        self.tactical_history: list[str] = []
        self.current_plan: list[str] = []
        self.current_plan_id: str | None = None
        self._next_plan_id = 1

        self.pending: dict | None = None
        self.decisions = 0
        self.updates = 0

    @staticmethod
    def tactical_key(state, action: str) -> str:
        return ",".join(str(int(x)) for x in state) + "|" + str(action)

    def select_tactical(self, state, actions, epsilon: float) -> str:
        if not actions:
            return ""
        keys = [self.tactical_key(state, action) for action in actions]
        values = np.asarray([self.tactical_q_values.get(key, 0.0) for key in keys])
        best = np.flatnonzero(np.isclose(values, values.max(), rtol=1e-9, atol=1e-12))
        if self.rng.random() < float(np.clip(epsilon, 0.0, 1.0)):
            index = int(self.rng.integers(len(actions)))
        else:
            index = int(self.rng.choice(best))
        return actions[index]

    def learn_tactical(self, state, action: str, reward: float,
                       alpha: float = 0.10) -> None:
        key = self.tactical_key(state, action)
        old = float(self.tactical_q_values.get(key, 0.0))
        self.tactical_q_values[key] = old + float(alpha) * (float(reward) - old)
        self.updates += 1

    def record_strategy_step(self, action: str, reward: float,
                             max_history: int = 8,
                             min_len: int = 2, max_len: int = 6) -> str | None:
        """從自己的實際決策歷史中萃取高回報動作序列。

        不預先指定「弱國先打」或「先殖民」等答案；AI 只有在自己的序列
        產生正回報時才會把它整理進自己的戰術庫。
        """
        kind = action_kind(action)
        if kind == "PASS":
            return None
        self.tactical_history.append(kind)
        self.tactical_history = self.tactical_history[-max_history:]
        if reward <= 0 or len(self.tactical_history) < min_len:
            return None

        # 把連續相同動作壓成一個步驟，讓「休養數年後再進攻」形成
        # REST→ATTACK，而不是污染戰術庫的 REST→REST→REST→ATTACK。
        compressed = []
        for item in self.tactical_history:
            if not compressed or compressed[-1] != item:
                compressed.append(item)
        if len(compressed) < min_len:
            return None

        # 同一尾端序列若已有記錄就更新，不重複建立。
        for length in range(min(max_len, len(compressed)), min_len - 1, -1):
            seq = compressed[-length:]
            if len(set(seq)) == 1:
                continue
            key = "→".join(seq)
            existing = self.tactical_library.get(key)
            if existing:
                existing["uses"] = int(existing.get("uses", 0)) + 1
                existing["score"] = 0.85 * float(existing.get("score", 0.0)) + 0.15 * float(reward)
                existing["successes"] = int(existing.get("successes", 0)) + 1
                return key
            # 新戰術只有在至少兩步且本次結果為正時產生。
            self.tactical_library[key] = {
                "sequence": list(seq),
                "score": float(reward),
                "uses": 1,
                "successes": 1,
                "created_decision": int(self.decisions),
                "source": "self_discovered",
            }
            # 偶爾把兩個自己已驗證過的套路接合；不指定結果，
            # 只有當後續實際執行並取得正回報，這個新組合才會留在庫裡。
            if len(self.tactical_library) >= 2 and self.rng.random() < 0.25:
                plans = list(self.tactical_library.values())
                a = plans[int(self.rng.integers(len(plans)))]
                b = plans[int(self.rng.integers(len(plans)))]
                left, right = list(a.get("sequence", [])), list(b.get("sequence", []))
                if left and right and left != right:
                    split_a = max(1, len(left) // 2)
                    split_b = max(1, len(right) // 2)
                    merged = left[:split_a] + right[split_b:]
                    compact = []
                    for item in merged:
                        if not compact or compact[-1] != item:
                            compact.append(item)
                    if min_len <= len(compact) <= max_len and len(set(compact)) >= 2:
                        merged_key = "→".join(compact)
                        if merged_key not in self.tactical_library:
                            self.tactical_library[merged_key] = {
                                "sequence": compact, "score": 0.0, "uses": 0,
                                "successes": 0, "created_decision": int(self.decisions),
                                "source": "self_composed", "validated": False,
                            }
            return key
        return None

    def choose_plan_action(self, state, legal_actions, epsilon: float) -> str | None:
        """從自己的戰術庫提出下一步，再用目前Q值挑選同類型具體目標。

        current_plan 永遠保存「尚未執行」的完整剩餘序列；本次選出的
        第一個動作只有在實際執行成功後才由 finish_plan_step() 移除。
        """
        if not legal_actions or not self.tactical_library:
            return None

        legal_by_kind = {}
        for action in legal_actions:
            legal_by_kind.setdefault(action_kind(action), []).append(action)

        def pick(kind):
            choices = legal_by_kind.get(kind, [])
            if not choices:
                return None
            self.ensure_actions(state, choices)
            values = np.asarray([self.value(state, a) for a in choices], dtype=float)
            best = np.flatnonzero(np.isclose(values, values.max(), rtol=1e-9, atol=1e-12))
            if self.rng.random() < float(np.clip(epsilon, 0.0, 1.0)):
                return choices[int(self.rng.integers(len(choices)))]
            return choices[int(self.rng.choice(best))]

        if self.current_plan:
            chosen = pick(self.current_plan[0])
            if chosen is not None:
                return chosen
            self.current_plan = []
            self.current_plan_id = None

        candidates = []
        for key, plan in self.tactical_library.items():
            seq = list(plan.get("sequence", []))
            if not seq or seq[0] not in legal_by_kind:
                continue
            score = float(plan.get("score", 0.0)) + 0.03 * int(plan.get("uses", 0))
            candidates.append((score, key, seq))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        if self.rng.random() < float(np.clip(epsilon, 0.0, 1.0)) and len(candidates) > 1:
            _, key, seq = candidates[int(self.rng.integers(len(candidates)))]
        else:
            _, key, seq = candidates[0]
        self.current_plan_id = key
        self.current_plan = list(seq)
        return pick(seq[0])

    def finish_plan_step(self):
        if self.current_plan:
            self.current_plan.pop(0)
        if not self.current_plan:
            self.current_plan_id = None

    @staticmethod
    def key(state, action: str) -> str:
        if len(state) != STATE_DIMENSIONS:
            raise ValueError(f"state 必須恰有 {STATE_DIMENSIONS} 個維度")
        return ",".join(str(int(x)) for x in state) + "|" + str(action)

    def ensure_actions(self, state, actions):
        for action in actions:
            key = self.key(state, action)
            self.q_values.setdefault(key, 0.0)

    def value(self, state, action: str) -> float:
        return float(self.q_values.get(self.key(state, action), 0.0))

    def select_action(self, state, actions, epsilon: float, action_biases=None) -> str:
        if not actions:
            return PASS_ACTION
        unseen = [self.key(state, action) not in self.q_values for action in actions]
        self.ensure_actions(state, actions)
        values = np.asarray([self.value(state, action) for action in actions], dtype=float)
        biases = action_biases or {}
        # 未嘗試動作給極小「資訊價值」加成，讓殖民、海戰、增援都能被看見；
        # 這不是人格權重，而是避免新動作永遠因初始Q=0被既有策略壓死。
        novelty_values = []
        for flag, action in zip(unseen, actions):
            if not flag:
                novelty_values.append(0.0)
            elif action == "COLONIZE":
                novelty_values.append(0.10)
            elif action == "REINFORCE_OVERSEAS" or (action.startswith("ATTACK:") and action.endswith(":naval")):
                novelty_values.append(0.05)
            else:
                novelty_values.append(0.015)
        novelty = np.asarray(novelty_values, dtype=float)
        preferences = values + np.asarray([float(biases.get(a, 0.0)) for a in actions]) + novelty
        best = np.flatnonzero(np.isclose(preferences, preferences.max(), rtol=1e-9, atol=1e-12))
        if self.rng.random() < float(np.clip(epsilon, 0.0, 1.0)):
            index = int(self.rng.integers(len(actions)))
        else:
            index = int(self.rng.choice(best))
        self.decisions += 1
        return actions[index]

    def expected_value(self, state, actions, epsilon: float, action_biases=None) -> float:
        if not actions:
            return 0.0
        self.ensure_actions(state, actions)
        values = np.asarray([self.value(state, action) for action in actions], dtype=float)
        biases = action_biases or {}
        preferences = values + np.asarray([float(biases.get(a, 0.0)) for a in actions])
        best = np.isclose(preferences, preferences.max(), rtol=1e-9, atol=1e-12)
        eps = float(np.clip(epsilon, 0.0, 1.0))
        probs = np.full(len(actions), eps / len(actions))
        probs[best] += (1.0 - eps) / int(best.sum())
        return float(np.dot(probs, values))

    def update(self, state, action: str, reward: float, next_state=None,
               next_actions=(), epsilon: float = 0.0, alpha: float = 0.12,
               gamma: float = 0.92, trace_lambda: float = 0.65,
               next_action_biases=None, terminal: bool = False):
        key = self.key(state, action)
        target = float(reward)
        if not terminal and next_state is not None:
            target += float(gamma) * self.expected_value(
                next_state, next_actions, epsilon, next_action_biases
            )
        delta = target - self.value(state, action)
        self.eligibility[key] = 1.0
        for trace_key, eligibility in list(self.eligibility.items()):
            self.q_values[trace_key] = self.q_values.get(trace_key, 0.0) + float(alpha) * delta * eligibility
            decayed = eligibility * float(gamma) * float(trace_lambda)
            if terminal or decayed < 1e-5:
                self.eligibility.pop(trace_key, None)
            else:
                self.eligibility[trace_key] = decayed
        self.updates += 1

    def to_dict(self) -> dict:
        return {
            "state_dimensions": STATE_DIMENSIONS,
            "q_values": self.q_values,
            "eligibility": self.eligibility,
            "tactical_q_values": self.tactical_q_values,
            "tactical_library": self.tactical_library,
            "tactical_history": self.tactical_history,
            "current_plan": self.current_plan,
            "current_plan_id": self.current_plan_id,
            "next_plan_id": self._next_plan_id,
            "pending": self.pending,
            "decisions": self.decisions,
            "updates": self.updates,
            "rng_state": self.rng.bit_generator.state,
        }

    def load_dict(self, data: dict):
        self.q_values = {str(k): float(v) for k, v in data.get("q_values", {}).items()}
        self.eligibility = {str(k): float(v) for k, v in data.get("eligibility", {}).items()}
        self.tactical_q_values = {
            str(k): float(v) for k, v in data.get("tactical_q_values", {}).items()
        }
        self.tactical_library = copy.deepcopy(data.get("tactical_library", {}))
        self.tactical_history = [str(x) for x in data.get("tactical_history", [])][-8:]
        self.current_plan = [str(x) for x in data.get("current_plan", [])]
        self.current_plan_id = data.get("current_plan_id")
        self._next_plan_id = int(data.get("next_plan_id", 1))
        self.pending = copy.deepcopy(data.get("pending"))
        pending_state = self.pending.get("state") if isinstance(self.pending, dict) else None
        if pending_state is not None and len(pending_state) != STATE_DIMENSIONS:
            self.pending = None
            self.eligibility = {}
        self.decisions = int(data.get("decisions", 0))
        self.updates = int(data.get("updates", 0))
        if data.get("rng_state"):
            self.rng.bit_generator.state = data["rng_state"]
