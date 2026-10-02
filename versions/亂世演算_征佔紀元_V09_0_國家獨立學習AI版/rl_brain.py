"""小型、可持續存檔的 Expected SARSA(lambda) 國家大腦。"""

from __future__ import annotations

import copy
import numpy as np


STATE_DIMENSIONS = 4
PASS_ACTION = "PASS"


class CountryBrain:
    """單一國家的獨立 Q 表、探索亂數與資格跡線。"""

    def __init__(self, seed: int):
        self.rng = np.random.default_rng(int(seed))
        self.q_values: dict[str, float] = {}
        self.eligibility: dict[str, float] = {}
        self.pending: dict | None = None
        self.decisions = 0
        self.updates = 0

    @staticmethod
    def key(state, action: str) -> str:
        if len(state) != STATE_DIMENSIONS:
            raise ValueError(f"state 必須恰有 {STATE_DIMENSIONS} 個維度")
        return ",".join(str(int(x)) for x in state) + "|" + str(action)

    def ensure_actions(self, state, actions, priors=None):
        priors = priors or {}
        for action in actions:
            key = self.key(state, action)
            self.q_values.setdefault(key, float(priors.get(action, 0.0)))

    def value(self, state, action: str) -> float:
        return float(self.q_values.get(self.key(state, action), 0.0))

    def select_action(self, state, actions, epsilon: float, priors=None) -> str:
        if not actions:
            return PASS_ACTION
        self.ensure_actions(state, actions, priors)
        values = np.asarray([self.value(state, action) for action in actions], dtype=float)
        best = np.flatnonzero(np.isclose(values, values.max(), rtol=1e-9, atol=1e-12))
        if self.rng.random() < float(np.clip(epsilon, 0.0, 1.0)):
            index = int(self.rng.integers(len(actions)))
        else:
            index = int(self.rng.choice(best))
        self.decisions += 1
        return actions[index]

    def expected_value(self, state, actions, epsilon: float, priors=None) -> float:
        if not actions:
            return 0.0
        self.ensure_actions(state, actions, priors)
        values = np.asarray([self.value(state, action) for action in actions], dtype=float)
        best = np.isclose(values, values.max(), rtol=1e-9, atol=1e-12)
        probs = np.full(len(actions), float(np.clip(epsilon, 0.0, 1.0)) / len(actions))
        probs[best] += (1.0 - float(np.clip(epsilon, 0.0, 1.0))) / int(best.sum())
        return float(np.dot(probs, values))

    def update(self, state, action: str, reward: float, next_state=None,
               next_actions=(), epsilon: float = 0.0, alpha: float = 0.12,
               gamma: float = 0.92, trace_lambda: float = 0.65,
               next_priors=None, terminal: bool = False):
        key = self.key(state, action)
        target = float(reward)
        if not terminal and next_state is not None:
            target += float(gamma) * self.expected_value(
                next_state, next_actions, epsilon, next_priors
            )
        delta = target - self.value(state, action)
        # replacing trace：同一狀態行動再次出現時，跡線重設為 1。
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
            "q_values": self.q_values,
            "eligibility": self.eligibility,
            "pending": self.pending,
            "decisions": self.decisions,
            "updates": self.updates,
            "rng_state": self.rng.bit_generator.state,
        }

    def load_dict(self, data: dict):
        self.q_values = {str(k): float(v) for k, v in data.get("q_values", {}).items()}
        self.eligibility = {str(k): float(v) for k, v in data.get("eligibility", {}).items()}
        self.pending = copy.deepcopy(data.get("pending"))
        self.decisions = int(data.get("decisions", 0))
        self.updates = int(data.get("updates", 0))
        if data.get("rng_state"):
            self.rng.bit_generator.state = data["rng_state"]
