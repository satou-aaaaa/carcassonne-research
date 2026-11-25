"""強いAIが選んだ手を上に並べるように評価関数を学ぶ（BACKLOG R-024）。

これまでの評価の学習（TD(λ)・根の値・SPSA）は、どれも「終局の得点差を当てる」形だった。予測は良くなっても
探索に使うと手の選び方は良くならなかった（docs/EXPERIMENTS.md「R²の高さが強さに直結しない」・R-013）。
ここでは将棋の Bonanza 法（Hoki & Kaneko 2014, JAIR 49）と同じく、各局面で先生（「最強」の探索）が選んだ手の
着手後の評価が、ほかの合法手の着手後の評価より高くなるように重みを動かす（softmax の交差エントロピー）。
兄弟の手の間の「順位」だけを見るので、手番や残り枚数のように兄弟で同じ値の特徴はチャンピオンの値に残る。

  gen: 先生の自己対戦で、局面ごとに合法手（配置×ミープル）の着手後の特徴量と、先生の手の番号を保存する
  fit: 保存したデータで重みを学ぶ（チャンピオンへ L2 で引き戻す。--td で今のループの TD(λ) 回帰を混ぜる）

例:
  python scripts/rank_learn.py gen --games 8 --seed 1 --out runs/x/d1.npz
  python scripts/rank_learn.py fit --data runs/x/d*.npz --prior models/eval_champion.npy --out runs/x/w.npy
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.fast import (
    SC_CUR,
    SC_OVER,
    SC_PL,
    SC_S0,
    SC_S1,
    SC_SUP0,
    apply_move,
    copy_state,
    gen_placements,
    piece_free,
    random_move,
    seed_rng,
)
from carcassonne.fast_eval import NF, features, load_eval
from carcassonne.selfplay_loop import eval_np
from carcassonne.td import td_lambda_targets


def legal_moves(S, fast) -> list[tuple[int, int, int]]:
    """手番側の合法手（マス, 向きID, 断片。断片 -1 はミープルなし）をすべて。"""
    T, P, sc = fast.T, fast.P, fast.scratch
    sc.stamp_box[0] += 1
    k = gen_placements(S, T, S[10][SC_CUR], sc.stamp, sc.stamp_box[0], sc.out_cell, sc.out_g, False)
    can = S[10][SC_SUP0 + S[10][SC_PL]] > 0
    out = []
    for j in range(k):
        cell, g = int(sc.out_cell[j]), int(sc.out_g[j])
        out.append((cell, g, -1))
        if can:
            out.extend((cell, g, pi) for pi in range(T[1][g]) if piece_free(S, T, P, cell, g, pi))
    return out


def child_features(S, fast, moves, me: int) -> np.ndarray:
    """各手を指した直後の局面の特徴量（me 視点）。次に引くタイルは実際の山札のもの（兄弟で同じ）。"""
    T, P, sc = fast.T, fast.P, fast.scratch
    F = np.zeros((len(moves), NF))
    f = np.zeros(NF)
    X = copy_state(S)
    for i, (cell, g, pi) in enumerate(moves):
        for a, b in zip(X, S, strict=True):
            a[...] = b
        apply_move(X, T, P, cell, g, pi, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
        features(X, T, P, me, f)
        F[i] = f
    return F


def _play(args):
    level, n_games, seed, eps, neg = args
    from carcassonne.webplay import make_agent

    agent = make_agent(level)
    fast = agent.fast
    sc = fast.scratch
    rng = random.Random(seed)
    random.seed(seed)
    seed_rng(seed)
    base = [i for i, t in enumerate(fast.ts.types) for _ in range(t.count)]
    base.remove(fast.ts.start)
    f = np.zeros(NF)
    xs, ys, ps, gs = [], [], [], []
    cf, cn = [], []  # 局面ごとの兄弟の特徴量（先生の手が先頭）と兄弟の数
    for gi in range(n_games):
        deck = base[:]
        rng.shuffle(deck)
        S = fast.new_game(deck)
        players = []
        while not S[10][SC_OVER]:
            me = int(S[10][SC_PL])
            features(S, fast.T, fast.P, me, f)
            xs.append(f.copy())
            players.append(me)
            cell, g, piece = agent.choose(S)
            moves = legal_moves(S, fast)
            chosen = (int(cell), int(g), int(piece))
            if len(moves) > 1 and chosen in moves:
                best = moves.index(chosen)
                others = [m for i, m in enumerate(moves) if i != best]
                if len(others) > neg:
                    others = rng.sample(others, neg)
                F = child_features(S, fast, [moves[best], *others], me)
                cf.append(F)
                cn.append(len(F))
            if rng.random() < eps:  # 先生だけの道筋に偏らないよう、ときどき乱手で局面を散らす
                cell, g, piece = random_move(
                    S, fast.T, fast.P, 0.3, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
                )
            apply_move(
                S, fast.T, fast.P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g
            )
        d = int(S[10][SC_S0]) - int(S[10][SC_S1])
        ys.extend(d if me == 0 else -d for me in players)
        ps.extend(players)
        gs.extend([gi + seed * 10_000] * len(players))
        print(f"seed {seed} 対局 {gi + 1}/{n_games} 済み", flush=True)
    return (
        np.array(xs, np.float32),
        np.array(ys, float),
        np.array(ps),
        np.array(gs),
        np.concatenate(cf).astype(np.float32),
        np.array(cn),
    )


def gen(a) -> None:
    """workers 局ずつ回し、回ごとに out を上書き保存する（Actions の時間切れでも、それまでの局は残る）。"""
    t0 = time.time()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    parts = []
    done = 0
    rnd = 0
    with ProcessPoolExecutor(a.workers) as ex:
        while done < a.games and (a.minutes <= 0 or time.time() - t0 < a.minutes * 60):
            k = min(a.workers, a.games - done)
            jobs = [
                (a.level, 1, a.seed * 1000 + rnd * a.workers + i, a.eps, a.neg) for i in range(k)
            ]
            parts.extend(ex.map(_play, jobs))
            done += k
            rnd += 1
            X, y, p, g, C, n = (np.concatenate([q[i] for q in parts]) for i in range(6))
            np.savez_compressed(a.out, X=X, y=y, p=p, g=g, C=C, n=n)
            print(
                f"{a.out}: {done}局 {len(y)}局面 兄弟つき {len(n)}局面 {time.time() - t0:.0f}秒",
                flush=True,
            )


def load(paths):
    ds = [np.load(f) for f in paths]
    # 対局番号はファイルごとに重ならないよう、ファイルの番号を足す
    X = np.concatenate([d["X"] for d in ds]).astype(float)
    y = np.concatenate([d["y"] for d in ds])
    p = np.concatenate([d["p"] for d in ds])
    g = np.concatenate([d["g"] + i * 10_000_000 for i, d in enumerate(ds)])
    C = np.concatenate([d["C"] for d in ds]).astype(float)
    n = np.concatenate([d["n"] for d in ds])
    return X, y, p, g, C, n


def rank_loss(w, C, n, temp: float):
    """先生の手（各組の先頭）の softmax 交差エントロピーの平均と、w についての勾配。"""
    s = (C @ w) / temp
    start = np.concatenate([[0], np.cumsum(n)[:-1]])
    m = np.maximum.reduceat(s, start)
    e = np.exp(s - np.repeat(m, n))
    z = np.add.reduceat(e, start)
    loss = np.mean(np.log(z) + m - s[start])
    pr = e / np.repeat(z, n)
    pr[start] -= 1.0
    grad = (C.T @ pr) / temp / len(n)
    return loss, grad


def top1(w, C, n) -> float:
    s = C @ w
    start = np.concatenate([[0], np.cumsum(n)[:-1]])
    return float(np.mean(np.maximum.reduceat(s, start) <= s[start] + 1e-9))


def fit(a) -> None:
    X, y, p, g, C, n = load(a.data)
    champ, mode = load_eval(a.prior)
    assert mode == 1, "線形のチャンピオンだけ"
    w0 = np.zeros(NF)
    w0[: len(champ)] = champ[:NF]
    # 検証用に兄弟の組の後ろ2割を分ける（ファイルの順＝対局の順）
    k = int(len(n) * 0.8)
    off = int(n[:k].sum())
    Ct, nt, Cv, nv = C[:off], n[:k], C[off:], n[k:]
    # 特徴の尺度をそろえて学ぶ（兄弟の差の標準偏差）
    sd = np.maximum(C.std(0), 1e-6)
    if a.td > 0:
        tdt = td_lambda_targets(eval_np(w0, 1, X), y, p, g, a.lam)
        var_y = tdt.var()
    w = w0.copy()
    m1 = np.zeros(NF)
    m2 = np.zeros(NF)
    for it in range(1, a.iters + 1):
        loss, grad = rank_loss(w, Ct, nt, a.temp)
        grad = grad + a.l2 * (w - w0) * sd**2
        if a.td > 0:
            r = X @ w - tdt
            grad = grad + a.td * (X.T @ r) / len(r) / var_y
        m1 = 0.9 * m1 + 0.1 * grad
        m2 = 0.999 * m2 + 0.001 * grad**2
        step = a.lr / sd * (m1 / (1 - 0.9**it)) / (np.sqrt(m2 / (1 - 0.999**it)) + 1e-12)
        w -= step
        if it % 200 == 0 or it == a.iters:
            lv, _ = rank_loss(w, Cv, nv, a.temp)
            print(
                f"  反復{it} 学習{loss:.4f} 検証{lv:.4f} 検証の一致 {top1(w, Cv, nv):.3f}",
                flush=True,
            )
    va = g >= np.quantile(g, 0.8)

    def r2(pred):
        return 1 - ((y[va] - pred) ** 2).sum() / ((y[va] - y[va].mean()) ** 2).sum()

    lc, _ = rank_loss(w0, Cv, nv, a.temp)
    lw, _ = rank_loss(w, Cv, nv, a.temp)
    print(
        f"{a.out}: 兄弟つき {len(n)}局面（平均 {n.mean():.1f}手）"
        f" 先生の手と一致 チャンピオン {top1(w0, Cv, nv):.3f} → 学習後 {top1(w, Cv, nv):.3f}"
        f" 検証の損失 {lc:.4f} → {lw:.4f}"
        f" 終局R² {r2(eval_np(w0, 1, X[va])):.3f} → {r2(eval_np(w, 1, X[va])):.3f}"
    )
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.save(a.out, w)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("gen")
    s.add_argument("--level", default="strong", choices=["strong", "standard"])
    s.add_argument("--games", type=int, default=8)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--eps", type=float, default=0.05)
    s.add_argument(
        "--neg", type=int, default=24, help="1局面に残す先生以外の手の数（多ければ抽選）"
    )
    s.add_argument("--workers", type=int, default=4)
    s.add_argument(
        "--minutes",
        type=float,
        default=0,
        help="この分数を過ぎたら次の回を始めない（0 なら games 局まで）",
    )
    s.add_argument("--out", required=True)
    s = sub.add_parser("fit")
    s.add_argument("--data", nargs="+", required=True)
    s.add_argument("--prior", required=True)
    s.add_argument("--temp", type=float, default=3.0, help="softmax の温度（点）")
    s.add_argument("--l2", type=float, default=1e-3, help="チャンピオンへ引き戻す強さ")
    s.add_argument("--td", type=float, default=0.0, help="TD(λ) 回帰を混ぜる重み（0 なら順位だけ）")
    s.add_argument("--lam", type=float, default=0.7)
    s.add_argument("--lr", type=float, default=0.01)
    s.add_argument("--iters", type=int, default=2000)
    s.add_argument("--out", required=True)
    a = ap.parse_args()
    {"gen": gen, "fit": fit}[a.cmd](a)


if __name__ == "__main__":
    main()
