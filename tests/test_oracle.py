"""増分エンジンと素朴オラクルの得点を、ランダム対戦の全手で突き合わせる差分テスト。"""

import random

import pytest

from carcassonne import State, load_tileset
from carcassonne.tiles import MONASTERY

from .oracle import Oracle


def monastery_greedy(st: State, rng: random.Random):
    """修道院の完成を狙う方策。完成・農民・道/都市の完成といった稀な状況を多く発生させる。"""
    ts = st.ts
    best, best_score = None, -1.0
    for m in st.legal_moves():
        v = ts.types[st.current].variants[m.variant]
        score = rng.random()
        if m.piece is not None and v.pieces[m.piece].kind == MONASTERY:
            score += 3
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                mp = (m.x + dx, m.y + dy)
                if mp in st.monasteries and any(st.meeples[st._find(st.monasteries[mp])]):
                    score += 2
        if score > best_score:
            best, best_score = m, score
    return best


def play_and_compare(seed: int, policy_seed: int, greedy: bool = False) -> int:
    """全手でエンジンとオラクルの得点を比較する。完成した修道院（9点）の数を返す。"""
    ts = load_tileset()
    rng = random.Random(policy_seed)
    st = State.new_game(seed)
    oracle = Oracle(ts)
    oracle.board[(0, 0)] = (ts.start, 0)
    while not st.over:
        move = monastery_greedy(st, rng) if greedy else rng.choice(st.legal_moves())
        ti, player = st.current, st.player
        st.apply(move)
        oracle.place((move.x, move.y), ti, move.variant, player, move.piece)
        if not st.over:  # 終局処理前の途中経過が一致する
            assert st.scores == oracle.scores, (seed, len(st.board))
    oracle.finish()
    assert st.scores == oracle.scores, (seed, st.scores, oracle.scores)
    return sum(1 for pos in st.monasteries if st._surrounded(pos))


@pytest.mark.parametrize("seed", range(60))
def test_engine_matches_oracle(seed):
    play_and_compare(seed, seed + 1000)


@pytest.mark.parametrize("seed", range(40))
def test_engine_matches_oracle_with_monastery_greedy_policy(seed):
    play_and_compare(seed, seed + 2000, greedy=True)


def test_greedy_policy_actually_completes_monasteries():
    total = sum(play_and_compare(s, s + 2000, greedy=True) for s in range(40))
    assert total > 0
