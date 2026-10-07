import random

import numpy as np
import pytest

from carcassonne.fast import Fast, apply_move, random_move, seed_rng
from carcassonne.fast_eval import NF
from carcassonne.nn_encode import NC, NG, NPOL, R, encode, policy_index


def _positions(n_moves=20, seed=0):
    f = Fast()
    sc = f.scratch
    rng = random.Random(seed)
    seed_rng(seed)
    deck = [i for i, t in enumerate(f.ts.types) for _ in range(t.count)]
    deck.remove(f.ts.start)
    rng.shuffle(deck)
    S = f.new_game(deck)
    planes = np.zeros((NC, R, R), np.float32)
    glob = np.zeros(NG, np.float32)
    fbuf = np.zeros(NF)
    out = []
    for _ in range(n_moves):
        x0, y0, k = encode(
            S, f.T, f.P, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, planes, glob, fbuf
        )
        legal = {
            policy_index(sc.out_cell[j], sc.out_g[j], S[10][8], x0, y0, f.T[11]) for j in range(k)
        }
        out.append((planes.copy(), glob.copy(), legal))
        c, g, p = random_move(
            S, f.T, f.P, 0.3, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
        )
        apply_move(S, f.T, f.P, c, g, p, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    return out


def test_legal_planes_match_policy_indices():
    for planes, _, legal in _positions():
        marked = set(np.flatnonzero(planes[25:29].reshape(-1)))
        assert marked == {i for i in legal if i >= 0}
        assert all(0 <= i < NPOL for i in marked)


def test_numpy_inference_matches_torch(tmp_path):
    torch = pytest.importorskip("torch")
    from carcassonne.nn_model import PolicyValueNet
    from carcassonne.nn_torch import Net, export

    torch.manual_seed(0)
    net = Net(8, 1)
    with torch.no_grad():  # BatchNorm の統計を既定値以外にして、畳み込みへの畳み込みを確かめる
        for m in net.modules():
            if isinstance(m, torch.nn.BatchNorm2d):
                m.running_mean.uniform_(-0.5, 0.5)
                m.running_var.uniform_(0.5, 2.0)
                m.weight.uniform_(0.5, 1.5)
                m.bias.uniform_(-0.2, 0.2)
    pos = _positions(5)
    planes = np.stack([p for p, _, _ in pos])
    glob = np.stack([g for _, g, _ in pos])
    g_mean, g_std = glob.mean(0), glob.std(0) + 1e-3
    export(net, g_mean, g_std, str(tmp_path / "m.npz"))
    lg, v = PolicyValueNet(str(tmp_path / "m.npz")).forward(planes, glob)
    net.eval()
    with torch.no_grad():
        tl, tv = net(
            torch.from_numpy(planes), torch.from_numpy(((glob - g_mean) / g_std).astype(np.float32))
        )
    legal = np.isfinite(lg)
    assert np.allclose(lg[legal], tl.numpy()[legal], atol=1e-3)
    assert np.allclose(v, tv.numpy() * 30.0, atol=1e-2)
