"""終盤の厳密ソルバー（endgame.py）を、Pythonエンジンでの素朴な期待ミニマックスと突き合わせる。"""

import random

import pytest

from carcassonne import State
from carcassonne.endgame import OBJ_DIFF, OBJ_WIN, bag_left, solve
from carcassonne.fast import Fast

FAST = Fast()


def _terminal(st: State, obj: int) -> float:
    d = st.scores[0] - st.scores[1]
    if obj == OBJ_DIFF:
        return float(d)
    return 1.0 if d > 0 else 0.5 if d == 0 else 0.0


def _value(st: State, obj: int) -> float:
    """手番の局面の値（先手視点）。引きは残りの種類ごとに枚数で重み付けする。"""
    vals = []
    for m in st.legal_moves():
        rest = st.deck[st.draw_pos :]
        if not rest:
            x = st.copy()
            x.apply(m)
            vals.append(_terminal(x, obj))
            continue
        tot = 0.0
        for t in sorted(set(rest)):
            x = st.copy()
            r = list(rest)
            r.remove(t)
            x.deck = st.deck[: st.draw_pos] + [t] + r
            x.apply(m)
            assert not x.discarded or x.discarded == st.discarded  # 捨て札の出ない局面だけ使う
            tot += rest.count(t) * (_terminal(x, obj) if x.over else _value(x, obj))
        vals.append(tot / len(rest))
    return max(vals) if st.player == 0 else min(vals)


def _endgame_state(seed: int, bag: int) -> State:
    st = State.new_game(seed)
    rng = random.Random(seed)
    while len(st.deck) - st.draw_pos > bag:
        st.apply(st.random_move(rng))
    return st


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("bag", [0, 1])
@pytest.mark.parametrize("obj", [OBJ_WIN, OBJ_DIFF])
def test_matches_naive_expectiminimax(seed, bag, obj):
    st = _endgame_state(seed, bag)
    S = FAST.new_game(st.deck)
    for x, y, ti, vi, piece in st.history:
        FAST.apply(S, x, y, ti, vi, piece)
    assert bag_left(S) == bag
    v, rows, _ = solve(FAST, S, obj)
    assert v == pytest.approx(_value(st, obj))
    assert len(rows) == len(st.legal_moves())  # 根は全着手の値を返す


def test_two_tiles_left_is_weighted_by_draw():
    st = _endgame_state(4, 2)
    S = FAST.new_game(st.deck)
    for x, y, ti, vi, piece in st.history:
        FAST.apply(S, x, y, ti, vi, piece)
    v, _, _ = solve(FAST, S, OBJ_DIFF)
    assert v == pytest.approx(_value(st, OBJ_DIFF))
