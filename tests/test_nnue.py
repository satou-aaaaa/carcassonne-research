"""NNUE 風の評価（R-027）: 探索用の numba の値と学習用の numpy の値が一致し、視点を替えると符号が反転する。"""

import numpy as np

from carcassonne.fast import SC_OVER, apply_move, random_move, seed_rng
from carcassonne.fast_eval import NF, load_eval
from carcassonne.fast_mcts import FastMCTSAgent
from carcassonne.nnue import MAXTOK, MODE, NTOK, Net, evaluate, nnue_value, tokens


def _positions(fast, n_games=2, seed=3):
    T, P, sc = fast.T, fast.P, fast.scratch
    seed_rng(seed)
    rng = np.random.default_rng(seed)
    base = [i for i, t in enumerate(fast.ts.types) for _ in range(t.count)]
    base.remove(fast.ts.start)
    out = []
    for _ in range(n_games):
        deck = list(rng.permutation(base))
        S = fast.new_game([int(t) for t in deck])
        k = 0
        while not S[10][SC_OVER]:
            if k % 7 == 3:
                out.append(tuple(a.copy() for a in S))
            c, g, pc = random_move(
                S, T, P, 0.5, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
            )
            apply_move(S, T, P, c, g, pc, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
            k += 1
    return out


def test_numba_matches_numpy_and_antisymmetric(tmp_path):
    fast = FastMCTSAgent(n_sims=10, eval_path="models/eval_champion.npy").fast
    T, P = fast.T, fast.P
    lin, mode = load_eval("models/eval_champion.npy")
    assert mode == 1
    net = Net(lin[:NF], H=8, H2=4, seed=1)
    net.E += np.random.default_rng(2).normal(0, 0.3, net.E.shape)
    p = net.pack()
    path = tmp_path / "n.npy"
    np.save(path, p)
    w, m = load_eval(str(path))
    assert m == MODE
    f = np.zeros(NF)
    buf = np.empty(MAXTOK, np.int64)
    for S in _positions(fast):
        for me in (0, 1):
            v = nnue_value(S, T, P, me, f, w)
            assert np.isclose(v, evaluate(S, T, P, me, f, w, m))
            F = f.reshape(1, -1).copy()
            km = tokens(S, T, P, me, buf)
            tm = buf[:km].copy()
            kt = tokens(S, T, P, 1 - me, buf)
            tt = buf[:kt].copy()
            assert tm.max() < NTOK and tt.max() < NTOK
            ref, _ = net.forward(F, tm, np.array([0, km]), tt, np.array([0, kt]), np.array([0]))
            assert np.isclose(v, ref[0])
        # 網の補正は視点を替えると符号が反転する（線形の部分を除いて）
        a = nnue_value(S, T, P, 0, f, w) - f @ lin[:NF]
        b = nnue_value(S, T, P, 1, f, w) - f @ lin[:NF]
        assert np.isclose(a, -b)


def test_backward_matches_finite_difference():
    rng = np.random.default_rng(0)
    net = Net(rng.normal(0, 1, NF), H=4, H2=3, nt=20, seed=0)
    net.E = rng.normal(0, 0.4, net.E.shape)
    F = rng.normal(0, 1, (3, NF))
    tm = rng.integers(0, 20, 9)
    tt = rng.integers(0, 20, 7)
    om, ot = np.array([0, 3, 6, 9]), np.array([0, 2, 5, 7])
    rows = np.arange(3)
    v, c = net.forward(F, tm, om, tt, ot, rows)
    g = net.backward(np.ones(3), c)
    for name, idx in (("W1", (1, 2)), ("E", (int(tm[0]), 1)), ("b0", (2,)), ("w2", (0,))):
        arr = getattr(net, name)
        old = arr[idx]
        arr[idx] = old + 1e-6
        vp, _ = net.forward(F, tm, om, tt, ot, rows)
        arr[idx] = old
        assert np.isclose(g[name][idx], (vp - v).sum() / 1e-6, atol=1e-4), name
