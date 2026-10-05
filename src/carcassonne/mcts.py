"""決定化（determinization）付きMCTS（PIMC-UCT）エージェント。

山札の残りの並びだけが隠れた情報なので、探索のたびに山札の未公開部分をシャッフルした
「決定化状態」を作り、その上で通常のUCTを行う（根並列）。根の各手の訪問数を決定化をまたいで
合算し、最多訪問の手を選ぶ。手元の1枚と残りタイルの内訳は公開情報として扱う。

ロールアウトは一様ランダム方策。終局報酬は勝ち=1/引分=0.5/負け=0。
`reward_scale` を指定すると 0.5+0.5*tanh(得点差/reward_scale) の連続報酬になる。
参考: Ameneyro, Galván, Kuri Morales (2020) "Playing Carcassonne with Monte Carlo Tree Search"
https://arxiv.org/abs/2009.12974
"""

from __future__ import annotations

import math
import random

from .state import Move, State


class _Node:
    __slots__ = ("children", "move", "mover", "n", "state", "untried", "w")

    def __init__(self, state: State, move: Move | None, mover: int | None, rng: random.Random):
        self.state = state
        self.move = move
        self.mover = mover  # この節点に至る手を指したプレイヤー
        self.children: list[_Node] = []
        self.untried: list[Move] = state.legal_moves() if not state.over else []
        rng.shuffle(self.untried)
        self.n = 0
        self.w = 0.0  # mover から見た報酬の合計


def determinize(state: State, rng: random.Random) -> State:
    """山札の未公開部分をシャッフルした複製を返す（手元のタイルと盤面は不変）。"""
    s = state.copy()
    rest = s.deck[s.draw_pos :]
    rng.shuffle(rest)
    s.deck = s.deck[: s.draw_pos] + rest
    return s


class MCTSAgent:
    def __init__(
        self,
        n_sims: int = 400,
        n_det: int = 8,
        c: float = 0.7,
        reward_scale: float | None = None,
    ) -> None:
        self.n_sims = n_sims
        self.n_det = n_det
        self.c = c
        self.reward_scale = reward_scale
        self.name = f"mcts(sims={n_sims},det={n_det},c={c:g})"

    # ---- 報酬 ---------------------------------------------------------------

    def _reward(self, state: State, player: int) -> float:
        diff = state.scores[player] - state.scores[1 - player]
        if self.reward_scale is None:
            return 1.0 if diff > 0 else 0.5 if diff == 0 else 0.0
        return 0.5 + 0.5 * math.tanh(diff / self.reward_scale)

    def _rollout(self, state: State, rng: random.Random) -> State:
        s = state.copy()
        while not s.over:
            s.apply(rng.choice(s.legal_moves()))
        return s

    # ---- 探索 ---------------------------------------------------------------

    def _search(self, root_state: State, sims: int, rng: random.Random) -> dict[Move, int]:
        root = _Node(root_state, None, None, rng)
        for _ in range(sims):
            node = root
            path = [node]
            # 選択
            while not node.untried and node.children:
                log_n = math.log(node.n + 1)
                node = max(
                    node.children,
                    key=lambda ch, ln=log_n: ch.w / ch.n + self.c * math.sqrt(ln / ch.n),
                )
                path.append(node)
            # 展開
            if node.untried:
                move = node.untried.pop()
                child_state = node.state.copy()
                mover = child_state.player
                child_state.apply(move)
                child = _Node(child_state, move, mover, rng)
                node.children.append(child)
                node = child
                path.append(node)
            # シミュレーション
            final = node.state if node.state.over else self._rollout(node.state, rng)
            # 逆伝播
            for nd in path:
                nd.n += 1
                if nd.mover is not None:
                    nd.w += self._reward(final, nd.mover)
        return {ch.move: ch.n for ch in root.children}

    def act(self, state: State, rng: random.Random) -> Move:
        moves = state.legal_moves()
        if len(moves) == 1:
            return moves[0]
        sims = max(1, self.n_sims // self.n_det)
        visits: dict[Move, int] = {}
        for _ in range(self.n_det):
            for mv, n in self._search(determinize(state, rng), sims, rng).items():
                visits[mv] = visits.get(mv, 0) + n
        best = max(visits.values())
        return rng.choice([m for m, n in visits.items() if n == best])
