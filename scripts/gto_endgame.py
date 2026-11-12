"""終盤の厳密解（GTO）とAIの手を比べる。

AI同士の対戦の棋譜（records.py の npz: deck・moves・nmoves）を再生し、山札の残りが
``--max-bag`` 枚以下の各局面で:

- 勝率最大の厳密解（`endgame.solve`, OBJ_WIN）で全着手の勝率を出す
- 最新チャンピオン（対戦ページの「最強」と同じ設定）と、棋譜に残る当時のAIの手の勝率を引く
- 点差最大の厳密解（OBJ_DIFF、残り2枚以下）の手が、勝率でどれだけ損かを見る

結果は1局面1行の JSONL。集計は ``--summary``。

例:
    py scripts/gto_endgame.py --records runs/rec_*.npz --games 100 --workers 4 --out runs/gto.jsonl
    py scripts/gto_endgame.py --summary runs/gto.jsonl --out docs/results/gto_endgame.json
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

EPS = 1e-9


def _mover(v: np.ndarray, pl: int, obj: int) -> np.ndarray:
    """先手視点の値を手番側視点に。"""
    from carcassonne.endgame import OBJ_WIN

    if pl == 0:
        return v
    return 1.0 - v if obj == OBJ_WIN else -v


def _idx(rows, cell, g, piece) -> int:
    hit = np.nonzero((rows[:, 0] == cell) & (rows[:, 1] == g) & (rows[:, 2] == piece))[0]
    return int(hit[0]) if len(hit) else -1


def _job(args):
    path, gi, max_bag, diff_bag, seed = args
    from carcassonne.endgame import OBJ_DIFF, OBJ_WIN, bag_left, solve
    from carcassonne.fast import SC_OVER, SC_PL, SC_S0, SC_S1, apply_move, copy_state, seed_rng
    from carcassonne.webplay import make_agent

    agent = make_agent("strong")
    f = agent.fast
    sc = f.scratch
    d = np.load(path)
    S = f.new_game([int(t) for t in d["deck"][gi]])
    out = []
    for k in range(int(d["nmoves"][gi])):
        if S[10][SC_OVER]:
            break
        rec = tuple(int(x) for x in d["moves"][gi, k])
        bag = bag_left(S)
        if bag <= max_bag:
            pl = int(S[10][SC_PL])
            _, rows, _n = solve(f, S, OBJ_WIN)
            win = _mover(rows[:, 3], pl, OBJ_WIN)
            seed_rng(seed + k)
            ch = agent.choose_search(copy_state(S))
            ic = _idx(rows, *ch)
            ir = _idx(rows, *rec)
            row = {
                "file": Path(path).name,
                "game": gi,
                "ply": k,
                "bag": bag,
                "mover": pl,
                "lead": int(S[10][SC_S0 + pl] - S[10][SC_S1 - pl]),
                "moves": len(rows),
                "best": float(win.max()),
                "worst": float(win.min()),
                "n_best": int((win >= win.max() - EPS).sum()),
                "champ": float(win[ic]) if ic >= 0 else None,
                "record": float(win[ir]) if ir >= 0 else None,
            }
            if bag <= diff_bag:
                _, rd, _ = solve(f, S, OBJ_DIFF)
                dv = _mover(rd[:, 3], pl, OBJ_DIFF)
                # 点差最大の手（複数あれば勝率の悪いほう＝点差だけ見て選ぶと起こりうる最悪）
                cand = np.nonzero(dv >= dv.max() - EPS)[0]
                wi = [win[_idx(rows, *rd[j, :3])] for j in cand]
                row["diff_move_win"] = float(min(wi))
                row["diff_move_win_best"] = float(max(wi))
                row["best_diff"] = float(dv.max())
                gto = np.nonzero(win >= win.max() - EPS)[0]
                row["gto_move_diff"] = float(max(dv[_idx(rd, *rows[j, :3])] for j in gto))
                row["champ_diff"] = float(dv[_idx(rd, *ch)]) if ic >= 0 else None
            out.append(row)
        apply_move(S, f.T, f.P, *rec, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    return out


def summarize(path: str) -> dict:
    """JSONL を、データページ（stats.html の「終盤を読み切ると」）が使う集計にする。"""
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines()]
    games = {(r["file"], r["game"]) for r in rows}

    def dec(r):  # 手の選び方で勝つ確率が変わる局面
        return r["best"] - r["worst"] > EPS

    def part(rs):
        d = [r for r in rs if dec(r)]
        return {
            "positions": len(rs),
            "decisive": len(d),
            "champ_optimal": sum(r["best"] - r["champ"] <= EPS for r in d),
            "record_optimal": sum(r["best"] - r["record"] <= EPS for r in d),
            "champ_loss": round(sum(r["best"] - r["champ"] for r in rs), 6),
        }

    res = {
        "source": Path(path).name,
        "games": len(games),
        "all": part(rows),
        "by_bag": {
            str(b): part([r for r in rows if r["bag"] == b])
            for b in sorted({r["bag"] for r in rows})
        },
        # 着手前の得点差（盤上の未完成分は含まない）で分けた、勝ち負けが動く局面
        "by_lead": {
            "close": part([r for r in rows if abs(r["lead"]) <= 20]),
            "far": part([r for r in rows if abs(r["lead"]) > 20]),
        },
    }
    dm = [r for r in rows if "diff_move_win" in r]
    res["diff_vs_win"] = {
        "positions": len(dm),
        "conflict": sum(r["best"] - r["diff_move_win"] > EPS for r in dm),
        "max_bag": max(r["bag"] for r in dm) if dm else None,
    }
    res["champ_loss_per_game"] = round(res["all"]["champ_loss"] / max(1, len(games)), 6)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--records", nargs="*", default=[])
    ap.add_argument("--games", type=int, default=50, help="使う局数（ファイルを順にまたぐ）")
    ap.add_argument("--max-bag", type=int, default=2)
    ap.add_argument("--diff-bag", type=int, default=2, help="点差の厳密解も出す残り枚数の上限")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ai", help="比べたAIの世代名（集計に残す。省略時は今のチャンピオン）")
    ap.add_argument("--out")
    ap.add_argument("--summary", help="集計する JSONL（--out に JSON を書く。無ければ表示）")
    a = ap.parse_args()
    if a.summary:
        from carcassonne.webplay import champion_info

        res = {"ai": a.ai or champion_info()["name"]} | summarize(a.summary)
        text = json.dumps(res, ensure_ascii=False, indent=1) + "\n"
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return
    files = sorted(p for pat in a.records for p in glob.glob(pat))
    jobs = []
    for p in files:
        n = len(np.load(p)["nmoves"])
        for gi in range(n):
            if len(jobs) < a.games:
                jobs.append(
                    (
                        p,
                        gi,
                        a.max_bag,
                        a.diff_bag,
                        random.Random(a.seed + len(jobs)).getrandbits(30),
                    )
                )
    done = set()
    if Path(a.out).exists():
        for x in Path(a.out).read_text(encoding="utf-8").splitlines():
            r = json.loads(x)
            done.add((r["file"], r["game"]))
    jobs = [j for j in jobs if (Path(j[0]).name, j[1]) not in done]
    with ProcessPoolExecutor(a.workers) as ex, open(a.out, "a", encoding="utf-8") as fo:
        for out in ex.map(_job, jobs):
            for r in out:
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            fo.flush()
            print(f"game done: {len(out)} positions", flush=True)


if __name__ == "__main__":
    main()
