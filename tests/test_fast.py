"""Numba版エンジンとPythonエンジンの一致検証。"""

import random

import numpy as np
import pytest

from carcassonne import State, load_tileset
from carcassonne.fast import (
    C0,
    SC_CUR,
    SC_DISC,
    SC_OVER,
    SC_PL,
    SC_S0,
    SC_S1,
    SC_SUP0,
    SC_SUP1,
    Fast,
    G,
    projected,
    seed_rng,
)

TS = load_tileset()
FAST = Fast()


def snapshot(S):
    sc = S[10]
    return {
        "scores": [int(sc[SC_S0]), int(sc[SC_S1])],
        "supply": [int(sc[SC_SUP0]), int(sc[SC_SUP1])],
        "over": bool(sc[SC_OVER]),
        "player": int(sc[SC_PL]),
        "cur": int(sc[SC_CUR]),
        "disc": int(sc[SC_DISC]),
    }


def py_snapshot(st):
    return {
        "scores": list(st.scores),
        "supply": list(st.supply),
        "over": st.over,
        "player": st.player,
        "cur": -1 if st.current is None else st.current,
        "disc": len(st.discarded),
    }


def mirror_game(seed, policy_rng, pick):
    """Python側で手を選び、同じ手をNumba側へ適用して毎手の状態を比較する。"""
    st = State.new_game(seed)
    S = FAST.new_game(st.deck)
    assert snapshot(S) == py_snapshot(st)
    while not st.over:
        m = pick(st, policy_rng)
        ti = st.current
        st.apply(m)
        FAST.apply(S, m.x, m.y, ti, m.variant, m.piece)
        assert snapshot(S) == py_snapshot(st), (seed, len(st.board))
        p = projected(S, FAST.T, FAST.P)
        assert [int(p[0]), int(p[1])] == st.projected_scores(), (seed, len(st.board))
    return st


@pytest.mark.parametrize("seed", range(40))
def test_fast_matches_python_random_play(seed):
    mirror_game(seed, random.Random(seed), lambda st, r: r.choice(st.legal_moves()))


def monastery_pick(st, rng):
    best, best_score = None, -1.0
    for m in st.legal_moves():
        v = st.ts.types[st.current].variants[m.variant]
        score = rng.random()
        if m.piece is not None and v.pieces[m.piece].kind == "M":
            score += 3
        if score > best_score:
            best, best_score = m, score
    return best


@pytest.mark.parametrize("seed", range(30))
def test_fast_matches_python_with_monastery_policy(seed):
    mirror_game(seed + 500, random.Random(seed), monastery_pick)


@pytest.mark.parametrize("seed", range(30))
def test_fast_rollout_is_a_valid_game(seed):
    """Numba内のロールアウトが記録した着手列を、Pythonエンジンで再生して得点が一致する。"""
    rng = random.Random(seed)
    st = State.new_game(seed + 900)
    S = FAST.new_game(st.deck)
    # 途中まで同じ手で進めてからロールアウト
    for _ in range(rng.randrange(0, 30)):
        if st.over:
            break
        m = rng.choice(st.legal_moves())
        ti = st.current
        st.apply(m)
        FAST.apply(S, m.x, m.y, ti, m.variant, m.piece)
    if st.over:
        return
    seed_rng(seed)
    final = FAST.rollout(S, 0.3)
    n_steps = len(st.deck) - st.draw_pos  # 上限
    rec = FAST.scratch.rec
    ref = st.copy()
    k = 0
    base_scores = None
    while not ref.over:
        cell, g, piece = (int(v) for v in rec[k])
        x, y = cell // G - C0, cell % G - C0
        ti = ref.current
        vi = g - int(FAST.T[11][ti])
        from carcassonne import Move

        mv = Move(x, y, vi, None if piece < 0 else piece)
        assert mv in ref.legal_moves(), (seed, k)
        ref.apply(mv)
        k += 1
    assert [int(final[0]), int(final[1])] == ref.scores
    assert k <= n_steps + 2
    assert base_scores is None


def test_rollout_truncation_returns_projected():
    st = State.new_game(3)
    S = FAST.new_game(st.deck)
    seed_rng(1)
    s0, s1 = FAST.rollout(S, 0.3, max_steps=5)
    assert not bool(S[10][SC_OVER])
    p = projected(S, FAST.T, FAST.P)
    assert (int(s0), int(s1)) == (int(p[0]), int(p[1]))


def test_fast_is_much_faster_than_python():
    import time

    st = State.new_game(1)
    t = time.time()
    n = 300
    seed_rng(0)
    for _ in range(n):
        S = FAST.new_game(st.deck)
        FAST.rollout(S, 0.3)
    fast_rate = n / (time.time() - t)
    assert fast_rate > 300  # Pythonエンジンは約200局/秒（meeple列挙あり）。Numbaは桁違いに速いはず
    assert np is not None
