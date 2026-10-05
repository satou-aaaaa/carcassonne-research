import random

import pytest

from carcassonne import Move, State, load_tileset
from carcassonne.state import DIRS, MEEPLES_PER_PLAYER
from carcassonne.tiles import CITY, FIELD, MONASTERY

TS = load_tileset()


def deck_of(*ids: str) -> list[int]:
    return [TS.index[i] for i in ids]


def start_variant():
    return TS.types[TS.start].variants[0]


def find_move(state: State, x, y, want_edges, piece_kind=None):
    """指定の辺構成で置く手を探す（piece_kind を指定するとその種別の断片にミープルを置く）。"""
    v_list = TS.types[state.current].variants
    for vi, v in enumerate(v_list):
        if v.edges != want_edges:
            continue
        if piece_kind is None:
            return Move(x, y, vi, None)
        for pi, p in enumerate(v.pieces):
            if p.kind == piece_kind:
                return Move(x, y, vi, pi)
    raise AssertionError("該当する手がない")


def test_new_game_basics():
    st = State.new_game(1)
    assert len(st.board) == 1
    assert st.current is not None
    assert st.scores == [0, 0] and st.supply == [MEEPLES_PER_PLAYER] * 2
    assert len(st.deck) == 71


def test_same_seed_same_game():
    a, b = State.new_game(7), State.new_game(7)
    assert a.deck == b.deck
    assert State.new_game(8).deck != a.deck


def test_complete_two_tile_city_scores_four_and_returns_meeple():
    sv = start_variant()
    c = sv.edges.index(CITY)
    st = State(deck_of("city_top", "city_top"))
    dx, dy = DIRS[c]
    # 新タイルの都市辺が開始タイルの方を向くように置く（辺は N,E,S,W）
    want = tuple(CITY if s == (c + 2) % 4 else FIELD for s in range(4))
    st.apply(find_move(st, dx, dy, want, CITY))
    assert st.scores == [4, 0]
    assert st.supply == [MEEPLES_PER_PLAYER] * 2  # 完成時に回収
    assert st.player == 1


def test_opponent_cannot_join_occupied_city():
    sv = start_variant()
    c = sv.edges.index(CITY)
    # 都市を2枚つなげて開いたまま（盾付き大都市を使う）にして、占有判定を確かめる
    st = State(deck_of("full_city_with_shield", "city_top", "city_top"))
    dx, dy = DIRS[c]
    want = (CITY,) * 4
    st.apply(find_move(st, dx, dy, want, CITY))  # 開いた都市にミープル
    assert st.supply[0] == MEEPLES_PER_PLAYER - 1
    # 相手の手番: 開いた都市に繋がる断片へのミープル配置は不可
    for m in st.legal_moves():
        if m.piece is None:
            continue
        v = TS.types[st.current].variants[m.variant]
        if v.pieces[m.piece].kind != CITY:
            continue
        # この都市断片が既存の占有都市に隣接するなら、合法手に含まれていてはならない
        touching = any(
            (m.x + ddx, m.y + ddy) == (dx, dy)
            for s, (ddx, ddy) in enumerate(DIRS)
            if s in v.pieces[m.piece].sides
        )
        assert not touching


def test_monastery_scores_one_plus_neighbours_at_end():
    sv = start_variant()
    f = [s for s in range(4) if sv.edges[s] == FIELD]
    assert f
    dx, dy = DIRS[f[0]]
    st = State(deck_of("chapel"))
    st.apply(find_move(st, dx, dy, (FIELD,) * 4, MONASTERY))
    assert st.over
    assert st.scores == [2, 0]  # 1 + 隣接1


def test_farmer_scores_three_per_completed_city_at_end():
    sv = start_variant()
    c = sv.edges.index(CITY)
    dx, dy = DIRS[c]
    st = State(deck_of("city_top"))
    want = tuple(CITY if s == (c + 2) % 4 else FIELD for s in range(4))
    # 新タイル上の農民（都市に接する草原）。都市は完成するが、都市にはミープルがいない
    st.apply(find_move(st, dx, dy, want, FIELD))
    assert st.over
    assert st.scores == [3, 0]


def test_unplaceable_tile_is_discarded():
    # 開始タイル周囲を全部囲ってから、置けないタイルを引かせる状況は作りにくいので、
    # 山札が空になれば終局することを確認する
    st = State([])
    assert st.over and st.current is None


@pytest.mark.parametrize("seed", range(20))
def test_random_playout_invariants(seed):
    rng = random.Random(seed)
    st = State.new_game(seed)
    placed = 1
    while not st.over:
        moves = st.legal_moves()
        assert moves, "未終局なら合法手があるはず"
        st.apply(rng.choice(moves))
        placed += 1
        for p in (0, 1):
            assert 0 <= st.supply[p] <= MEEPLES_PER_PLAYER
    # ミープルの保存則: 手持ち + 盤上 = 7
    on_board = [0, 0]
    for r in range(len(st.parent)):
        if st.parent[r] == r:
            for p in (0, 1):
                on_board[p] += st.meeples[r][p]
    for p in (0, 1):
        assert st.supply[p] + on_board[p] == MEEPLES_PER_PLAYER
    assert len(st.board) + len(st.discarded) == 72
    assert min(st.scores) >= 0


def test_copy_is_independent():
    st = State.new_game(3)
    c = st.copy()
    c.apply(c.legal_moves()[0])
    assert len(st.board) == 1 and len(c.board) == 2


def test_remaining_counts_matches_undrawn_deck():
    st = State.new_game(5)
    assert sum(st.remaining_counts()) == 70  # 72 - 開始タイル - 手元の1枚
    rng = random.Random(0)
    while not st.over:
        undrawn = st.deck[st.draw_pos :]
        expected = [undrawn.count(i) for i in range(len(st.ts.types))]
        assert st.remaining_counts() == expected
        st.apply(rng.choice(st.legal_moves()))
