import numpy as np

from carcassonne import State
from carcassonne.fast import Fast
from carcassonne.fast_eval import (
    FEATURE_NAMES,
    NF,
    collect,
    eval_value,
    fit_mlp,
    fit_ridge,
    load_eval,
)

FAST = Fast()


def test_feature_names_match_nf():
    assert len(FEATURE_NAMES) == NF


def test_features_are_antisymmetric_for_difference_features():
    from carcassonne.fast_eval import features

    st = State.new_game(5)
    S = FAST.new_game(st.deck)
    import random

    rng = random.Random(0)
    for _ in range(25):
        m = rng.choice(st.legal_moves())
        ti = st.current
        st.apply(m)
        FAST.apply(S, m.x, m.y, ti, m.variant, m.piece)
    a, b = np.zeros(NF), np.zeros(NF)
    features(S, FAST.T, FAST.P, 0, a)
    features(S, FAST.T, FAST.P, 1, b)
    names = list(FEATURE_NAMES)
    for n in (
        "score_diff",
        "proj_diff",
        "proj_city",
        "proj_road",
        "proj_field",
        "proj_monastery",
        "city_bonus",
        "supply_x_remaining",
        "proj_field_x_remaining",
        "proj_city_x_remaining",
        "monastery_room_x_remaining",
        "dead_city_bonus",
        "hard_city_bonus",
        "dead_x_remaining",
        "field_open_cities",
        "field_open_cities_x_remaining",
    ):
        i = names.index(n)
        assert abs(a[i] + b[i]) < 1e-12, n
    # 自分/相手の開放端数・置きっぱなしのミープルは入れ替わる
    assert a[names.index("open_city_mine")] == b[names.index("open_city_theirs")]
    assert a[names.index("stuck_mine")] == b[names.index("stuck_theirs")]
    assert a[names.index("dead_mine")] == b[names.index("dead_theirs")]


def _random_game_cells(seed):
    """ランダムに1局指し、各手番の (状態のコピー, 空きマスと合う残りタイル枚数の辞書) と最後の盤を返す。"""
    from carcassonne.fast import SC_N, SC_OVER, apply_move, copy_state, random_move, seed_rng
    from carcassonne.fast_eval import n_fit, remaining_counts

    rng = np.random.default_rng(seed)
    seed_rng(seed)
    sc = FAST.scratch
    deck = [i for i, t in enumerate(FAST.ts.types) for _ in range(t.count)]
    deck.remove(FAST.ts.start)
    S = FAST.new_game(list(rng.permutation(deck)))
    req = np.empty(4, np.int8)
    snaps = []
    while not S[10][SC_OVER]:
        cnt = remaining_counts(S, FAST.T)
        cells = {}
        for t in range(S[10][SC_N]):
            for d in (1, -1, 145, -145):
                c = int(S[2][t]) + d
                if S[0][c] == 0:
                    cells[c] = n_fit(S, FAST.T, c, cnt, req)
        snaps.append((copy_state(S), cnt, cells))
        cell, g, piece = random_move(
            S, FAST.T, FAST.P, 0.5, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
        )
        apply_move(S, FAST.T, FAST.P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    return snaps, S


def test_n_fit_counts_remaining_tiles_that_can_be_placed():
    """空きマスに合う残りタイル枚数が、合法配置の列挙と一致し、0 のマスは最後まで埋まらない。"""
    from carcassonne.fast import gen_placements

    sc = FAST.scratch
    n_dead = 0
    for seed in range(3):
        snaps, end = _random_game_cells(seed)
        for S, cnt, cells in snaps[::5]:
            ok = {c: 0 for c in cells}
            for ti in np.nonzero(cnt)[0]:
                sc.stamp_box[0] += 1
                k = gen_placements(
                    S, FAST.T, ti, sc.stamp, sc.stamp_box[0], sc.out_cell, sc.out_g, False
                )
                for c in set(sc.out_cell[:k].tolist()):
                    ok[c] += int(cnt[ti])
            assert cells == ok
        for _, _, cells in snaps:
            for c, n in cells.items():
                if n == 0:
                    n_dead += 1
                    assert end[0][c] == 0
    assert n_dead > 0


def test_dead_features_flag_meeples_that_never_return():
    """完成不能と判定された都市・道・修道院のミープルは、終局まで戻らない（手持ちが増えない限り）。"""
    from carcassonne.fast_eval import features

    seen = 0
    f = np.zeros(NF)
    names = list(FEATURE_NAMES)
    for seed in range(4):
        snaps, end = _random_game_cells(seed)
        for S, _, _ in snaps:
            features(S, FAST.T, FAST.P, 0, f)
            dead0 = f[names.index("dead_mine")]
            if dead0 > 0:
                seen += 1
                # 盤上の未完成のミープルのうち、少なくとも dead0 体は最後まで盤に残る
                left = end[9].reshape(-1, 2)[:, 0].sum()
                assert left >= dead0
    assert seen > 0


def test_mlp_numba_forward_matches_numpy(tmp_path):
    X, y = collect(FAST, 40, seed=7)
    p, _ = fit_mlp(X, y, hidden=8, epochs=3)
    path = tmp_path / "m.npy"
    np.save(path, p)
    w, mode = load_eval(str(path))
    assert mode == 8
    mean, std = w[:NF], w[NF : 2 * NF]
    H = 8
    off = 2 * NF
    W1 = w[off : off + NF * H].reshape(NF, H)
    b1 = w[off + NF * H : off + NF * H + H]
    W2 = w[off + NF * H + H : off + NF * H + 2 * H]
    b2 = w[-1]
    for row in X[:20]:
        ref = np.maximum(((row - mean) / std) @ W1 + b1, 0) @ W2 + b2
        assert abs(eval_value(w, mode, row) - ref) < 1e-6


def test_linear_ridge_and_padding(tmp_path):
    X, y = collect(FAST, 60, seed=3)
    m = fit_ridge(X, y, 1.0)
    assert m.w.shape == (NF,)
    old = np.arange(14, dtype=float)
    path = tmp_path / "old.npy"
    np.save(path, old)
    w, mode = load_eval(str(path))
    assert mode == 1 and len(w) == NF and np.all(w[14:] == 0)


def test_legacy_mlp_is_padded(tmp_path):
    """特徴量22個の旧MLPを読むと、追加特徴量の値によらず旧特徴量だけの出力になる。"""
    from carcassonne.fast_eval import NF_V6

    rng = np.random.default_rng(0)
    H = 4
    old = np.concatenate(
        [
            rng.normal(size=NF_V6),
            rng.uniform(0.5, 2.0, NF_V6),
            rng.normal(size=NF_V6 * H + 2 * H + 1),
        ]
    )
    path = tmp_path / "old_mlp.npy"
    np.save(path, old)
    w, mode = load_eval(str(path))
    assert mode == H
    f = rng.normal(size=NF)
    g = f.copy()
    g[NF_V6:] = rng.normal(size=NF - NF_V6) * 100
    assert abs(eval_value(w, mode, f) - eval_value(w, mode, g)) < 1e-9
    mean, std = old[:NF_V6], old[NF_V6 : 2 * NF_V6]
    off = 2 * NF_V6
    W1 = old[off : off + NF_V6 * H].reshape(NF_V6, H)
    b1 = old[off + NF_V6 * H : off + NF_V6 * H + H]
    W2 = old[off + NF_V6 * H + H : off + NF_V6 * H + 2 * H]
    ref = np.maximum(((f[:NF_V6] - mean) / std) @ W1 + b1, 0) @ W2 + old[-1]
    assert abs(eval_value(w, mode, f) - ref) < 1e-9
