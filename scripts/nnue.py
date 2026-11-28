"""NNUE 風の評価を学び、チャンピオンと比べる（BACKLOG R-027）。仕組みは `carcassonne.nnue`。

build: `scripts/rank_learn.py gen` が保存した自己対戦（山札と手順つき）を作り直し、局面ごとの
       今の38特徴・トークン（自分視点・相手視点）・終局得点差と、兄弟の手の着手後のものを保存する
fit:   チャンピオンの線形評価に網の補正を足す形で学ぶ（目標は今のループと同じ TD(λ)、または終局得点差）。
       検証（後ろ2割の対局）の終局R²と、先生の手との一致率をチャンピオンと比べ、重みを保存する

python scripts/nnue.py build --data runs/r025/d0.npz --out runs/r027/t_d0.npz
python scripts/nnue.py fit --cache runs/r027/t_*.npz --out runs/r027/nnue.npy
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from carcassonne.fast import SC_PL, apply_move, copy_state
from carcassonne.fast_eval import NF, features, load_eval
from carcassonne.nnue import MAXTOK, Net, tokens
from carcassonne.selfplay_loop import eval_np
from carcassonne.td import td_lambda_targets


class _Rows:
    def __init__(self):
        self.F, self.tm, self.tt, self.om, self.ot = [], [], [], [0], [0]
        self.f = np.zeros(NF)
        self.buf = np.empty(MAXTOK, np.int64)

    def add(self, S, T, P, me):
        features(S, T, P, me, self.f)
        self.F.append(self.f.astype(np.float32).copy())
        for who, lst, off in ((me, self.tm, self.om), (1 - me, self.tt, self.ot)):
            k = tokens(S, T, P, who, self.buf)
            lst.append(self.buf[:k].astype(np.int16).copy())
            off.append(off[-1] + k)

    def arrays(self, pre):
        return {
            pre + "F": np.array(self.F, np.float32),
            pre + "tm": np.concatenate(self.tm),
            pre + "om": np.array(self.om, np.int64),
            pre + "tt": np.concatenate(self.tt),
            pre + "ot": np.array(self.ot, np.int64),
        }


def build(a) -> None:
    from carcassonne.fast_mcts import FastMCTSAgent

    import rank_learn as rl

    fast = FastMCTSAgent(n_sims=10, eval_path="models/eval_champion.npy").fast
    T, P, sc = fast.T, fast.P, fast.scratch
    t0 = time.time()
    d = np.load(a.data)
    y, p, g = d["y"], d["p"], d["g"]
    decks, hist = d["decks"], d["hist"]
    pos = _Rows()
    for gi in range(len(decks)):
        S = fast.new_game([int(t) for t in decks[gi]])
        for cell, gg, pc in hist[gi]:
            if cell == -2:
                break
            pos.add(S, T, P, int(S[10][SC_PL]))
            apply_move(
                S, T, P, int(cell), int(gg), int(pc), sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g
            )
    assert len(pos.F) == len(y)
    assert np.allclose(np.array(pos.F)[:, : d["X"].shape[1]], d["X"], atol=1e-3)
    sib = _Rows()
    n = d["n"]
    st = np.concatenate([[0], np.cumsum(n)])
    lim = len(n) if a.max_sib <= 0 else min(len(n), a.max_sib)
    for i in range(lim):
        gi = int(d["pos_game"][i])
        S = rl.replay(fast, decks[gi], hist[gi], int(d["pos_ply"][i]))
        me = int(S[10][SC_PL])
        Y = copy_state(S)
        for r in range(st[i], st[i + 1]):
            for u, v in zip(Y, S, strict=True):
                u[...] = v
            cell, gg, pc = (int(v) for v in d["cand"][r])
            apply_move(Y, T, P, cell, gg, pc, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
            sib.add(Y, T, P, me)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out, y=y, p=p, g=g, n=n[:lim], **pos.arrays(""), **sib.arrays("s"))
    print(f"{a.data}: {len(y)}局面 兄弟 {lim}組 {time.time() - t0:.0f}秒", flush=True)


def _cat_csr(ds, tk, ok):
    toks, offs, base = [], [0], 0
    for d in ds:
        toks.append(d[tk].astype(np.int64))
        offs.append(d[ok][1:] + base)
        base += d[ok][-1]
    return np.concatenate(toks), np.concatenate([np.array([0])] + offs[1:])


def load_cache(paths):
    ds = [np.load(f) for f in sorted(paths)]
    D = {k: np.concatenate([d[k] for d in ds]) for k in ("y", "p", "F", "sF", "n")}
    D["g"] = np.concatenate([d["g"] + i * 100_000_000 for i, d in enumerate(ds)])
    for pre in ("", "s"):
        D[pre + "tm"], D[pre + "om"] = _cat_csr(ds, pre + "tm", pre + "om")
        D[pre + "tt"], D[pre + "ot"] = _cat_csr(ds, pre + "tt", pre + "ot")
    # 兄弟の組がどのファイルの何局目か（検証の対局と重ならないよう、ファイルごとの後ろ2割を検証にする）
    D["file_of_pos"] = np.concatenate([np.full(len(d["y"]), i) for i, d in enumerate(ds)])
    D["file_of_sib"] = np.concatenate([np.full(len(d["n"]), i) for i, d in enumerate(ds)])
    return D


def agreement_vals(s, n) -> float:
    start = np.concatenate([[0], np.cumsum(n)[:-1]])
    mx = np.maximum.reduceat(s, start)
    top = np.isclose(s, np.repeat(mx, n), atol=1e-6)
    return float(np.mean(top[start] / np.add.reduceat(top.astype(int), start)))


def predict(net, F, tm, om, tt, ot, rows=None, bs=8192):
    rows = np.arange(len(F)) if rows is None else rows
    out = np.empty(len(rows))
    for i in range(0, len(rows), bs):
        r = rows[i : i + bs]
        out[i : i + bs], _ = net.forward(F, tm, om, tt, ot, r)
    return out


def fit(a) -> None:
    D = load_cache(a.cache)
    y, p, g, F = D["y"], D["p"], D["g"], D["F"].astype(float)
    champ, mode = load_eval(a.prior)
    assert mode == 1
    lin = champ[:NF].copy()
    # 検証: 各ファイルの後ろ2割の対局。兄弟の組も同じ割合で後ろ2割
    va = np.zeros(len(y), bool)
    for fi in np.unique(D["file_of_pos"]):
        m = D["file_of_pos"] == fi
        gg = g[m]
        va[m] = gg >= np.quantile(gg, 0.8)
    vs = np.zeros(len(D["n"]), bool)
    for fi in np.unique(D["file_of_sib"]):
        idx = np.where(D["file_of_sib"] == fi)[0]
        vs[idx[int(len(idx) * 0.8) :]] = True
    sstart = np.concatenate([[0], np.cumsum(D["n"])])
    srows = np.concatenate([np.arange(sstart[i], sstart[i + 1]) for i in np.where(vs)[0]])
    nv = D["n"][vs]
    sF = D["sF"].astype(float)

    def r2(pred, m):
        return 1 - ((y[m] - pred) ** 2).sum() / ((y[m] - y[m].mean()) ** 2).sum()

    v0 = F @ lin
    print(
        f"チャンピオン: 終局R²（検証）{r2(v0[va], va):.4f} 一致率（検証）{agreement_vals(sF[srows] @ lin, nv):.4f}"
        f" 局面 {len(y)}（検証 {va.sum()}） 兄弟の組 {len(D['n'])}（検証 {vs.sum()}）",
        flush=True,
    )
    tgt = (
        td_lambda_targets(eval_np(np.concatenate([lin]), 1, F), y, p, g, a.lam) if a.lam < 1 else y
    )
    tr = np.where(~va)[0]
    vrows = np.where(va)[0]
    net = Net(lin, a.H, a.H2, seed=a.seed)
    names = ["E", "b0", "W1", "b1", "w2"]
    m1 = {k: np.zeros_like(getattr(net, k)) for k in names}
    m2 = {k: np.zeros_like(getattr(net, k)) for k in names}
    rng = np.random.default_rng(a.seed)
    step = 0
    best = (-1e9, None)
    args = (F, D["tm"], D["om"], D["tt"], D["ot"])
    sargs = (sF, D["stm"], D["som"], D["stt"], D["sot"])
    t0 = time.time()
    for ep in range(a.epochs):
        perm = rng.permutation(tr)
        lr = a.lr * (0.5 ** (ep // max(1, a.decay)))
        for i in range(0, len(perm), a.bs):
            rows = perm[i : i + a.bs]
            v, c = net.forward(*args, rows)
            dv = 2 * (v - tgt[rows]) / len(rows)
            gr = net.backward(dv, c)
            gr["E"] += a.l2 * net.E
            gr["W1"] += a.l2 * net.W1
            step += 1
            for k in names:
                m1[k] = 0.9 * m1[k] + 0.1 * gr[k]
                m2[k] = 0.999 * m2[k] + 0.001 * gr[k] ** 2
                upd = lr * (m1[k] / (1 - 0.9**step)) / (np.sqrt(m2[k] / (1 - 0.999**step)) + 1e-8)
                setattr(net, k, getattr(net, k) - upd)
        pv = predict(net, *args, vrows)
        sv = predict(net, *sargs, srows)
        rv, ag = r2(pv, va), agreement_vals(sv, nv)
        ptr = predict(net, *args, tr[:20000])
        rt = (
            1
            - ((y[tr[:20000]] - ptr) ** 2).sum()
            / ((y[tr[:20000]] - y[tr[:20000]].mean()) ** 2).sum()
        )
        print(
            f"ep {ep + 1}: 終局R² 学習 {rt:.4f} 検証 {rv:.4f} 一致率 {ag:.4f} lr {lr:.1e}"
            f" {time.time() - t0:.0f}秒",
            flush=True,
        )
        if rv > best[0]:
            best = (rv, net.pack())
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.save(a.out, best[1])
    print(f"保存: {a.out}（検証R² {best[0]:.4f}）")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("--data", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--max-sib", type=int, default=0, help="兄弟の組をこの数まで（0 なら全部）")
    s = sub.add_parser("fit")
    s.add_argument("--cache", nargs="+", required=True)
    s.add_argument("--prior", default="models/eval_champion.npy")
    s.add_argument("--out", required=True)
    s.add_argument("--H", type=int, default=32)
    s.add_argument("--H2", type=int, default=32)
    s.add_argument("--lam", type=float, default=0.7, help="TD(λ) の λ（1 なら終局得点差そのもの）")
    s.add_argument("--epochs", type=int, default=12)
    s.add_argument("--decay", type=int, default=4, help="この数のエポックごとに学習率を半分に")
    s.add_argument("--bs", type=int, default=256)
    s.add_argument("--lr", type=float, default=1e-3)
    s.add_argument("--l2", type=float, default=1e-4)
    s.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    {"build": build, "fit": fit}[a.cmd](a)


if __name__ == "__main__":
    main()
