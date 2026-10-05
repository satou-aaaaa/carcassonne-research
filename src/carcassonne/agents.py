"""ベースラインのエージェント。

`Agent.act(state, rng)` は合法手の1つを返す。エージェントは状態を変更してはならない。
"""

from __future__ import annotations

import random
from typing import Protocol

from .state import Move, State


class Agent(Protocol):
    name: str

    def act(self, state: State, rng: random.Random) -> Move: ...


class RandomAgent:
    """合法手から一様ランダムに選ぶ。"""

    name = "random"

    def act(self, state: State, rng: random.Random) -> Move:
        return rng.choice(state.legal_moves())


class GreedyAgent:
    """1手先の「予測得点差」が最大の手を選ぶ。

    予測得点差 = 今終局した場合の（自分−相手）得点。ミープルを置くこと自体に
    `meeple_cost` 点のコストを課し、無闇に手持ちを使い切らないようにする。
    """

    def __init__(self, meeple_cost: float = 0.5) -> None:
        self.meeple_cost = meeple_cost
        self.name = f"greedy({meeple_cost:g})"

    def act(self, state: State, rng: random.Random) -> Move:
        me = state.player
        best: list[Move] = []
        best_value = float("-inf")
        for m in state.legal_moves():
            nxt = state.copy()
            nxt.apply(m)
            s = nxt.projected_scores()
            value = (s[me] - s[1 - me]) - (self.meeple_cost if m.piece is not None else 0.0)
            if value > best_value + 1e-9:
                best, best_value = [m], value
            elif abs(value - best_value) <= 1e-9:
                best.append(m)
        return rng.choice(best)
