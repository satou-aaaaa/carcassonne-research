"""新しい特徴を、値の尺度を保つ学び方（TD(λ)）で入れる（BACKLOG R-026）。

R-025 では「置いたミープルが戻る見込み」3特徴（NF=41）を順位だけで学ぶと、最強の探索で負けた。順位の学習は
兄弟の手の並びしか決めず、深い探索の葉で別の局面どうしを比べる値の尺度が崩れるためと考えた。ここでは
`scripts/rank_learn.py gen` が保存した最強の自己対戦（山札と手順つき）を作り直して今の特徴（NF）を計算し直し、

  td:  今の自己対戦ループと同じ TD(λ) の目標へ、チャンピオンの重みに引き戻すリッジ回帰（`selfplay_loop._train`）
  mix: 同じ TD(λ) 回帰に、順位の損失を小さく混ぜる（`rank_learn.fit --td` と同じ形）

で重みを作り、検証（後ろ2割の対局）の終局R²と、先生の手との一致率をチャンピオンと比べる。

  python scripts/td_feature_fit.py build --data runs/r025/d0.npz --out runs/r026/x41_d0.npz  # 1ファイルずつ
  python scripts/td_feature_fit.py fit --cache runs/r026/x41_*.npz --out-dir runs/r026
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import rank_learn as rl
from feature_screen import agreement

from carcassonne.fast import SC_PL, apply_move, copy_state
from carcassonne.fast_eval import NF, features, load_eval
from carcassonne.ridge_stats import solve_ridge, stats_of
from carcassonne.selfplay_loop import eval_np
from carcassonne.td import td_lambda_targets


def build(a) -> None:
    """保存した局面を作り直し、全局面の特徴 X と兄弟の手の着手後の特徴 C を今の NF で計算し直す。"""
    from carcassonne.fast_mcts import FastMCTSAgent

    fast = FastMCTSAgent(n_sims=10, eval_path="models/eval_champion.npy").fast
    T, P, sc = fast.T, fast.P, fast.scratch
    t0 = time.time()
    Xs, ys, ps, gs, Cs, ns = [], [], [], [], [], []
    f = np.zeros(NF)
    for fi, path in enumerate(sorted(a.data)):
        d = np.load(path)
        y, p, g = d["y"], d["p"], d["g"] + fi * 10_000_000
        decks, hist = d["decks"], d["hist"]
        # 全局面: 対局ごとに手順をたどる（X の行は対局順・手数順に並んでいる）
        X = np.zeros((len(y), NF))
        row = 0
        for gi in range(len(decks)):
            S = fast.new_game([int(t) for t in decks[gi]])
            for cell, gg, pc in hist[gi]:
                if cell == -2:
                    break
                features(S, T, P, int(S[10][SC_PL]), f)
                X[row] = f
                row += 1
                apply_move(
                    S,
                    T,
                    P,
                    int(cell),
                    int(gg),
                    int(pc),
                    sc.stamp,
                    sc.stamp_box,
                    sc.out_cell,
                    sc.out_g,
                )
        assert row == len(y), (path, row, len(y))
        # 古い特徴の列が保存したものと一致すること（作り直しの確かめ）
        old = d["X"].astype(float)
        assert np.allclose(X[:, : old.shape[1]], old, atol=1e-3), path
        # 兄弟の手
        n = d["n"]
        st = np.concatenate([[0], np.cumsum(n)])
        C = np.zeros((int(n.sum()), NF))
        for i in range(len(n)):
            gi = int(d["pos_game"][i])
            S = rl.replay(fast, decks[gi], hist[gi], int(d["pos_ply"][i]))
            me = int(S[10][SC_PL])
            Y = copy_state(S)
            for r in range(st[i], st[i + 1]):
                for u, v in zip(Y, S, strict=True):
                    u[...] = v
                cell, gg, pc = (int(v) for v in d["cand"][r])
                apply_move(Y, T, P, cell, gg, pc, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
                features(Y, T, P, me, f)
                C[r] = f
        Xs.append(X)
        ys.append(y)
        ps.append(p)
        gs.append(g)
        Cs.append(C)
        ns.append(n)
        print(f"{path}: {len(y)}局面 兄弟 {len(n)}組（{time.time() - t0:.0f}秒）", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        a.out, X=np.concatenate(Xs), y=np.concatenate(ys), p=np.concatenate(ps),
        g=np.concatenate(gs), C=np.concatenate(Cs), n=np.concatenate(ns),
    )  # fmt: skip


def fit(a) -> None:
    # build を1ファイルずつ回したものを並べる（対局番号はファイルごとに重ならないようずらす）
    ds = [np.load(f) for f in sorted(a.cache)]
    X, y, p, C, n = (np.concatenate([d[k] for d in ds]) for k in ("X", "y", "p", "C", "n"))
    g = np.concatenate([d["g"] + i * 100_000_000 for i, d in enumerate(ds)])
    champ, mode = load_eval(a.prior)
    assert mode == 1, "線形のチャンピオンだけ"
    w0 = np.zeros(NF)
    w0[: len(champ)] = champ[:NF]
    # 検証: 局面は後ろ2割の対局、兄弟の組は後ろ2割（どちらもファイル順＝対局順）
    va = g >= np.quantile(g, 0.8)
    k = int(len(n) * 0.8)
    off = int(n[:k].sum())
    Cv, nv = C[off:], n[k:]

    def r2(w):
        pred = X[va] @ w
        return 1 - ((y[va] - pred) ** 2).sum() / ((y[va] - y[va].mean()) ** 2).sum()

    def report(name, w):
        print(
            f"{name}: 終局R²（検証）{r2(w):.4f} 一致率（検証）{agreement(w, Cv, nv):.4f}"
            f" 新しい特徴の重み {np.round(w[NF - 3 :], 3).tolist()}",
            flush=True,
        )

    report("チャンピオン", w0)
    tr = ~va
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for ridge in a.ridge:
        # 今のループと同じ: チャンピオンの値で TD(λ) の目標を作り、チャンピオンへ引き戻すリッジ
        t = td_lambda_targets(eval_np(w0, 1, X), y, p, g, a.lam)
        w = solve_ridge(stats_of(X[tr], t[tr]), ridge, w0)
        report(f"td ridge={ridge:g}", w)
        np.save(out / f"td_r{ridge:g}.npy", w)
    # 順位を混ぜる: TD 回帰（チャンピオンの値の尺度）に順位の損失を mix 倍で足し、学習は検証を除いた部分だけ
    t = td_lambda_targets(eval_np(w0, 1, X), y, p, g, a.lam)
    Ct, nt = C[:off], n[:k]
    Xt, tt = X[tr], t[tr]
    var_t = tt.var()
    sd = np.maximum(C.std(0), 1e-6)
    for mix in a.mix:
        w = w0.copy()
        m1 = np.zeros(NF)
        m2 = np.zeros(NF)
        for it in range(1, a.iters + 1):
            r = Xt @ w - tt
            grad = (Xt.T @ r) / len(r) / var_t + a.l2 * (w - w0) * sd**2
            if mix > 0:
                _, gr = rl.rank_loss(w, Ct, nt, a.temp)
                grad = grad + mix * gr
            m1 = 0.9 * m1 + 0.1 * grad
            m2 = 0.999 * m2 + 0.001 * grad**2
            w -= a.lr / sd * (m1 / (1 - 0.9**it)) / (np.sqrt(m2 / (1 - 0.999**it)) + 1e-12)
        report(f"mix={mix:g}", w)
        np.save(out / f"mix{mix:g}.npy", w)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("--data", nargs="+", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("fit")
    s.add_argument("--cache", nargs="+", required=True)
    s.add_argument("--prior", default="models/eval_champion.npy")
    s.add_argument("--lam", type=float, default=0.7)
    s.add_argument("--ridge", type=float, nargs="+", default=[1000.0])
    s.add_argument("--mix", type=float, nargs="+", default=[0.0, 0.1, 0.3])
    s.add_argument("--temp", type=float, default=3.0)
    s.add_argument("--l2", type=float, default=1e-3)
    s.add_argument("--lr", type=float, default=0.01)
    s.add_argument("--iters", type=int, default=2000)
    s.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    {"build": build, "fit": fit}[a.cmd](a)


if __name__ == "__main__":
    main()
