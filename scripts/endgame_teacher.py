"""終盤の厳密値（勝率）を教師に、勝率を予測する評価関数を学ぶ（BACKLOG R-001）。

3つの段階:

- ``collect``: AI同士の棋譜（records.py の npz）を再生し、山札の残りが ``--max-bag`` 枚以下の各局面を
  `endgame.solve`（OBJ_WIN）で読み切る。局面の特徴量（手番側と相手側の2行）と、その視点の厳密な勝率を
  npz に書く（1局1ファイル。途中で止めても続きから）。
- ``fit``: 勝率をロジスティック回帰（特徴量は評価関数と同じ ``NF`` 個）で学ぶ。局単位で学習と検証に分け、
  チャンピオンの評価（探索と同じ ``0.5+0.5*tanh(v/30)`` で勝率に読み替え）と対数損失・Brier で比べる。
  学んだ重みは ``w * scale/2`` にして「点差の評価関数」と同じ形で保存する。探索の報酬
  ``0.5+0.5*tanh(v/scale)`` は ``sigmoid(w·f)`` と一致するので、探索のコードはそのまま使える。
- ``split``: チャンピオンの重みと終盤用の重みをつないだ「切り替え型」の評価関数を作る
  （山札の残りが ``--late-bag`` 枚以下の局面だけ終盤用。`fast_eval.eval_value` の mode=-1）。

例:
    py scripts/endgame_teacher.py collect --records 'runs/rec_*.npz' --max-bag 4 --out runs/eg_teacher
    py scripts/endgame_teacher.py fit --data runs/eg_teacher --out models/eval_eg_win.npy
    py scripts/endgame_teacher.py split --late models/eval_eg_win.npy --late-bag 4 --out models/eval_eg_split.npy
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

SCALE = 30.0  # 探索の報酬の尺度（FastMCTSAgent の reward_scale 既定）


def _job(args):
    path, gi, max_bag, out = args
    from carcassonne.endgame import OBJ_WIN, bag_left, solve
    from carcassonne.fast import SC_OVER, SC_PL, Fast, apply_move
    from carcassonne.fast_eval import NF, eval_value, features, load_eval
    from carcassonne.webplay import champion_eval_path

    f = Fast()
    sc = f.scratch
    cw, cm = load_eval(champion_eval_path())
    d = np.load(path)
    S = f.new_game([int(t) for t in d["deck"][gi]])
    X, y, bags, champ = [], [], [], []
    fb = np.zeros(NF)
    for k in range(int(d["nmoves"][gi])):
        if S[10][SC_OVER]:
            break
        rec = tuple(int(x) for x in d["moves"][gi, k])
        bag = bag_left(S)
        if bag <= max_bag:
            pl = int(S[10][SC_PL])
            v, _rows, _n = solve(f, S, OBJ_WIN)  # 先手視点の勝率
            for me in (pl, 1 - pl):
                features(S, f.T, f.P, me, fb)
                X.append(fb.copy())
                y.append(v if me == 0 else 1.0 - v)
                bags.append(bag)
                champ.append(eval_value(cw, cm, fb))
        apply_move(S, f.T, f.P, *rec, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    np.savez_compressed(
        out,
        X=np.array(X).reshape(-1, NF),
        y=np.array(y),
        bag=np.array(bags, np.int32),
        champ=np.array(champ),
    )
    return len(y)


def collect(a) -> None:
    files = sorted(p for pat in a.records for p in glob.glob(pat))
    od = Path(a.out)
    od.mkdir(parents=True, exist_ok=True)
    jobs = []
    for p in files:
        n = len(np.load(p)["nmoves"])
        for gi in range(n):
            out = od / f"{Path(p).stem}_{gi:03d}.npz"
            if len(jobs) < a.games and not out.exists():
                jobs.append((p, gi, a.max_bag, str(out)))
    with ProcessPoolExecutor(a.workers) as ex:
        futs = [ex.submit(_job, j) for j in jobs]
        for i, fu in enumerate(as_completed(futs)):
            print(f"{i + 1}/{len(jobs)} rows={fu.result()}", flush=True)


def load(data: list[str]):
    """教師のフォルダ（複数可）を読む。同じ局のファイルは先に書いたフォルダのものを使う。"""
    seen: dict[str, Path] = {}
    for dd in data:
        for p in sorted(Path(dd).glob("*.npz")):
            seen.setdefault(p.name, p)
    parts = [np.load(seen[k]) for k in sorted(seen)]
    gid = np.concatenate([np.full(len(z["y"]), i) for i, z in enumerate(parts)])
    cat = {k: np.concatenate([z[k] for z in parts]) for k in ("X", "y", "bag", "champ")}
    return cat, gid


def fit_logistic(X, y, l2: float = 1e-3, iters: int = 200):
    """ラベルが確率（0〜1）のロジスティック回帰をニュートン法で解く。列は標準化してから戻す。"""
    mu = X.mean(0)
    sd = X.std(0)
    const = sd < 1e-9
    mu[const] = 0.0
    sd[const] = 1.0
    Z = (X - mu) / sd
    Z[:, const] = X[:, const]  # 定数列（bias）はそのまま
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z @ w, -30, 30)))
        g = Z.T @ (p - y) / len(y) + l2 * w
        H = (Z * (p * (1 - p))[:, None]).T @ Z / len(y) + l2 * np.eye(len(w))
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-10:
            break
    # 標準化を戻す: w·(x-mu)/sd = (w/sd)·x - sum(w*mu/sd)
    wx = w / sd
    wx[const] = w[const]
    bias = -np.sum(w[~const] * mu[~const] / sd[~const])
    return wx, bias


def metrics(p, y) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    ll = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    yh = -np.mean(y * np.log(np.clip(y, 1e-6, 1)) + (1 - y) * np.log(np.clip(1 - y, 1e-6, 1)))
    return {
        "logloss": round(float(ll), 4),
        "excess_logloss": round(float(ll - yh), 4),  # 教師そのもの（下限）からの差
        "brier": round(float(np.mean((p - y) ** 2)), 4),
        "sign_acc": round(float(np.mean((p > 0.5) == (y > 0.5))), 4),
    }


def fit(a) -> None:
    from carcassonne.fast_eval import FEATURE_NAMES

    d, gid = load(a.data)
    X, y, bag, champ = d["X"], d["y"], d["bag"], d["champ"]
    bias_idx = FEATURE_NAMES.index("bias")
    games = np.unique(gid)
    rng = np.random.default_rng(a.seed)
    val_g = set(rng.choice(games, size=max(1, len(games) // 5), replace=False).tolist())
    va = np.array([g in val_g for g in gid])
    tr = ~va
    w, b = fit_logistic(X[tr], y[tr], l2=a.l2)
    w[bias_idx] += b
    p_new = 1 / (1 + np.exp(-(X @ w)))
    p_champ = 0.5 + 0.5 * np.tanh(champ / SCALE)
    res = {
        "positions_rows": len(y),
        "games": len(games),
        "val_games": len(val_g),
        "by_bag_rows": {str(k): int((bag == k).sum()) for k in sorted(set(bag.tolist()))},
        "val": {"learned": metrics(p_new[va], y[va]), "champion": metrics(p_champ[va], y[va])},
        "val_by_bag": {
            str(k): {
                "learned": metrics(p_new[va & (bag == k)], y[va & (bag == k)]),
                "champion": metrics(p_champ[va & (bag == k)], y[va & (bag == k)]),
            }
            for k in sorted(set(bag.tolist()))
            if (va & (bag == k)).any()
        },
        "train": {"learned": metrics(p_new[tr], y[tr]), "champion": metrics(p_champ[tr], y[tr])},
    }
    # 全データで学び直したものを保存（点差の評価関数と同じ形: w*scale/2）
    w_all, b_all = fit_logistic(X, y, l2=a.l2)
    w_all[bias_idx] += b_all
    res["weights_logit"] = {n: round(float(v), 5) for n, v in zip(FEATURE_NAMES, w_all)}
    if a.out:
        np.save(a.out, w_all * SCALE / 2)
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if a.report:
        Path(a.report).write_text(text + "\n", encoding="utf-8")
    print(text)


def split(a) -> None:
    from carcassonne.fast_eval import NF, load_eval, split_eval_params
    from carcassonne.webplay import champion_eval_path

    main_w, mode = load_eval(a.main or champion_eval_path())
    if mode != 1:
        raise SystemExit("切り替え型は線形の評価関数どうしだけ")
    late_w, mode2 = load_eval(a.late)
    assert mode2 == 1 and len(late_w) == NF
    np.save(a.out, split_eval_params(main_w, late_w, a.late_bag))
    print(f"wrote {a.out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--records", nargs="+", required=True)
    c.add_argument("--games", type=int, default=400)
    c.add_argument("--max-bag", type=int, default=4)
    c.add_argument("--workers", type=int, default=4)
    c.add_argument("--out", required=True)
    f = sub.add_parser("fit")
    f.add_argument(
        "--data", nargs="+", required=True, help="教師のフォルダ（同じ局は先のものを使う）"
    )
    f.add_argument("--l2", type=float, default=1e-3)
    f.add_argument("--seed", type=int, default=1)
    f.add_argument("--out")
    f.add_argument("--report")
    s = sub.add_parser("split")
    s.add_argument("--late", required=True)
    s.add_argument("--late-bag", type=int, default=4)
    s.add_argument("--main", help="省略時は今のチャンピオン")
    s.add_argument("--out", required=True)
    a = ap.parse_args()
    {"collect": collect, "fit": fit, "split": split}[a.cmd](a)


if __name__ == "__main__":
    main()
