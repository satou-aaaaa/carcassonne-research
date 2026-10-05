"""決定化（determinization）付きMCTS（PIMC-UCT）エージェント。

山札の残りの並びだけが隠れた情報なので、探索のたびに山札の未公開部分をシャッフルした
「決定化状態」を作り、その上で通常のUCTを行う（根並列）。根の各手の訪問数を決定化をまたいで
合算し、最多訪問の手を選ぶ。手元の1枚と残りタイルの内訳は公開情報として扱う。

木の形は2通り選べる。
- flat（`factored=False`）: 「配置＋ミープル」を1手として1段で展開する（分岐100超）。
- factored（既定）: 配置ノード→ミープルノードの2段（Jappert 2022 に倣う）。分岐が
  「配置十数＋ミープル数個」に減り、同じ配置の下でミープル選択の統計が共有される。

ロールアウトは一様ランダムの配置とミープル確率 `meeple_prob` の方策。報酬は
勝ち=1/引分=0.5/負け=0、`reward_scale` を指定すると 0.5+0.5*tanh(得点差/reward_scale)。
`rollout_depth` を指定すると、その手数で打ち切り「今終局した場合の予測得点差」で評価する。

参考:
- Ameneyro, Galván, Kuri Morales (2020) https://arxiv.org/abs/2009.12974
- Jappert (2022) https://ai.dmi.unibas.ch/papers/theses/jappert-bachelor-22.pdf
"""

from __future__ import annotations

import math
import random

from .state import Move, State


class _Node:
    """flat木では手の節点、factored木では配置節点（placement=None）とミープル節点を兼ねる。"""

    __slots__ = ("children", "key", "mover", "n", "placement", "state", "untried", "w")

    def __init__(self, state: State, key, mover: int | None, placement=None) -> None:
        self.state = state  # 配置節点・flatの手節点では「その局面」、ミープル節点では配置前の局面
        self.key = key  # この節点に至る選択（flat: Move、配置: (x,y,vi)、ミープル: 断片index/None）
        self.mover = mover  # この節点に至る選択をしたプレイヤー
        self.placement = placement  # ミープル節点でのみ設定
        self.children: list[_Node] = []
        self.untried: list = []
        self.n = 0
        self.w = 0.0  # mover から見た報酬の合計


def determinize(state: State, rng: random.Random) -> State:
    """山札の未公開部分をシャッフルした複製を返す（手元のタイルと盤面は不変）。"""
    s = state.copy()
    rest = s.deck[s.draw_pos :]
    rng.shuffle(rest)
    s.deck = s.deck[: s.draw_pos] + rest
    return s


def meeple_options(state: State, x: int, y: int, vi: int) -> list[int | None]:
    """(x,y,vi) に置く手番のミープル選択肢（置かない=None を含む）。"""
    out: list[int | None] = [None]
    if state.supply[state.player] > 0:
        v = state.ts.types[state.current].variants[vi]
        out += [pi for pi in range(len(v.pieces)) if not state._occupied((x, y), v, pi)]
    return out


class MCTSAgent:
    def __init__(
        self,
        n_sims: int = 400,
        n_det: int = 1,
        c: float = 0.5,
        reward_scale: float | None = 30.0,
        meeple_prob: float = 0.3,
        factored: bool = True,
        rollout_depth: int | None = None,
    ) -> None:
        self.n_sims = n_sims
        self.n_det = n_det
        self.c = c
        self.reward_scale = reward_scale
        self.meeple_prob = meeple_prob
        self.factored = factored
        self.rollout_depth = rollout_depth
        self.name = (
            f"mcts(sims={n_sims},det={n_det},c={c:g},scale={reward_scale},mp={meeple_prob:g},"
            f"fact={int(factored)},depth={rollout_depth})"
        )

    # ---- 報酬・ロールアウト ----------------------------------------------------

    def _reward(self, scores: list[int], player: int) -> float:
        diff = scores[player] - scores[1 - player]
        if self.reward_scale is None:
            return 1.0 if diff > 0 else 0.5 if diff == 0 else 0.0
        return 0.5 + 0.5 * math.tanh(diff / self.reward_scale)

    def _evaluate(self, state: State, rng: random.Random) -> list[int]:
        """節点の局面から方策に従って進め、（予測）最終得点を返す。"""
        if state.over:
            return state.scores
        s = state.copy()
        steps = 0
        while not s.over:
            if self.rollout_depth is not None and steps >= self.rollout_depth:
                return s.projected_scores()
            s.apply(s.random_move(rng, self.meeple_prob))
            steps += 1
        return s.scores

    # ---- 探索 ---------------------------------------------------------------

    def _select(self, node: _Node) -> _Node:
        log_n = math.log(node.n + 1)
        c = self.c
        return max(node.children, key=lambda ch: ch.w / ch.n + c * math.sqrt(log_n / ch.n))

    def _new_place_node(self, state: State, key, mover, rng: random.Random) -> _Node:
        nd = _Node(state, key, mover)
        if not state.over:
            if self.factored:
                nd.untried = state.placements()
            else:
                nd.untried = state.legal_moves()
            rng.shuffle(nd.untried)
        return nd

    def _search(self, root_state: State, sims: int, rng: random.Random) -> dict[Move, int]:
        root = self._new_place_node(root_state, None, None, rng)
        for _ in range(sims):
            node = root
            path = [node]
            while not node.untried and node.children:
                node = self._select(node)
                path.append(node)
            if node.untried:
                opt = node.untried.pop()
                if not self.factored:
                    cs = node.state.copy()
                    mover = cs.player
                    cs.apply(opt)
                    child = self._new_place_node(cs, opt, mover, rng)
                elif node.placement is None:  # 配置節点 -> ミープル節点
                    x, y, vi = opt
                    child = _Node(node.state, opt, node.state.player, placement=opt)
                    child.untried = meeple_options(node.state, x, y, vi)
                    rng.shuffle(child.untried)
                else:  # ミープル節点 -> 次の配置節点
                    cs = node.state.copy()
                    mover = cs.player
                    cs.apply(Move(*node.placement, opt))
                    child = self._new_place_node(cs, opt, mover, rng)
                node.children.append(child)
                node = child
                path.append(node)
            final = self._evaluate(node.state, rng) if node.placement is None else None
            if final is None:  # ミープル節点が葉: 未展開の選択肢の期待は不明なので配置後を1回評価
                mv = Move(*node.placement, None)
                cs = node.state.copy()
                cs.apply(mv)
                final = self._evaluate(cs, rng)
            for nd in path:
                nd.n += 1
                if nd.mover is not None:
                    nd.w += self._reward(final, nd.mover)
        return self._root_visits(root)

    def _root_visits(self, root: _Node) -> dict[Move, int]:
        out: dict[Move, int] = {}
        if not self.factored:
            return {ch.key: ch.n for ch in root.children}
        for pl in root.children:
            for m in pl.children:
                out[Move(*pl.key, m.key)] = m.n
            # ミープル節点が未展開の配置は「置かない」の訪問として扱う
            if not pl.children:
                out[Move(*pl.key, None)] = pl.n
        return out

    def act(self, state: State, rng: random.Random) -> Move:
        moves = state.legal_moves()
        if len(moves) == 1:
            return moves[0]
        sims = max(1, self.n_sims // self.n_det)
        visits: dict[Move, int] = {}
        place: dict[tuple, int] = {}
        for _ in range(self.n_det):
            for mv, n in self._search(determinize(state, rng), sims, rng).items():
                visits[mv] = visits.get(mv, 0) + n
                place[mv[:3]] = place.get(mv[:3], 0) + n
        if self.factored:  # まず配置を訪問数で選び、その配置の下でミープル選択を訪問数で選ぶ
            top = max(place.values())
            pl = rng.choice([p for p, n in place.items() if n == top])
            visits = {m: n for m, n in visits.items() if m[:3] == pl}
        best = max(visits.values())
        return rng.choice([m for m, n in visits.items() if n == best])
