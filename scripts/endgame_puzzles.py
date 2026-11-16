"""終盤で「手の選び方で勝率が大きく動く」局面を、厳密解（GTO）から集める（BACKLOG R-002）。

AI同士の棋譜（records.py の npz）を再生し、山札の残りが ``--bags`` の枚数の各局面を
`endgame.solve`（勝率）で読み切る。最善手の勝率と、それに届かない手のうち一番良い手（次善手）の
勝率の差が ``--min-gap`` 以上の局面を、終盤クイズの材料として出す。

各局面には、人がやりがちな選び方の手も並べて、その手の厳密な勝率を付ける:

- ``greedy``: 今の盤面の見込み点差（未完成も今終わったものとして数える）が一番大きくなる手。
  同点の候補が複数あれば、代表は勝率の悪いほうで、``ties``（同点の数）・``win_mean``（同点の手の平均の勝率）・
  ``n_best``（同点の中の最善手の数）も付ける
- ``diff``: 点差の期待値が最大の厳密解（勝率でなく点差を目的にした場合）
- ``champ``: 最新チャンピオン「最強」の探索の手（読み切りなし）

出力は1局面1行の JSONL（局面の着手履歴 history は data/puzzles.json と同じ [x, y, 種別, 向き, 断片]）。
``--summary`` で学びどころの型ごとの集計と例を JSON にする。``--refresh`` は保存した局面だけを読み直す
（解析の項目を変えたとき、全局を再生し直さずに済む）。

例:
    py scripts/endgame_puzzles.py --records "runs/records/rec_*.npz" --games 400 --workers 4 \\
        --out runs/endgame_puzzles.jsonl
    py scripts/endgame_puzzles.py --refresh data/endgame_puzzles.jsonl --out runs/endgame_puzzles2.jsonl
    py scripts/endgame_puzzles.py --summary runs/endgame_puzzles.jsonl --out docs/results/endgame_puzzles.json
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
KIND_NAME = {0: "city", 1: "road", 2: "field", 3: "monastery"}
KIND_JA = {"city": "都市", "road": "道", "field": "草原", "monastery": "修道院", None: "なし"}


def gap_of(win: np.ndarray) -> tuple[float, float, int]:
    """(最善の勝率, 次善の勝率, 最善の手の数)。次善は最善に届かない手のうち最大（全部同じなら最善と同じ）。"""
    best = float(win.max())
    nb = int((win >= best - EPS).sum())
    rest = win[win < best - EPS]
    second = float(rest.max()) if len(rest) else best
    return best, second, nb


def _decode(fast, cell: int, g: int, piece: int) -> list:
    """Numba の着手 (マス, 向きID, 断片) を [x, y, 種別, 向き, 断片] に。"""
    from carcassonne.fast import C0, G

    starts = fast.T[11]
    ti = int(np.searchsorted(starts, g, side="right") - 1)
    return [cell // G - C0, cell % G - C0, ti, int(g - starts[ti]), None if piece < 0 else piece]


def move_facts(fast, S, cell: int, g: int, piece: int) -> dict:
    """着手の事実: 即時得点（自分・相手）、見込み点差の変化、ミープルの置き先の種類。"""
    from carcassonne.fast import SC_PL, SC_S0, apply_move, copy_state, find, projected

    sc = fast.scratch
    pl = int(S[10][SC_PL])
    p0 = projected(S, fast.T, fast.P)
    S2 = copy_state(S)
    apply_move(S2, fast.T, fast.P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    p1 = projected(S2, fast.T, fast.P)
    kind = None
    if piece >= 0:
        t = int(S2[0][cell]) - 1
        r = find(S2[3], t * fast.P + piece)
        kind = KIND_NAME.get(int(S2[4][r]))
    return {
        "gain_me": int(S2[10][SC_S0 + pl] - S[10][SC_S0 + pl]),
        "gain_opp": int(S2[10][SC_S0 + 1 - pl] - S[10][SC_S0 + 1 - pl]),
        "proj_me": int(p1[pl] - p0[pl]),
        "proj_opp": int(p1[1 - pl] - p0[1 - pl]),
        "meeple": kind,
    }


def _mover(v: np.ndarray, pl: int, obj: int) -> np.ndarray:
    from carcassonne.endgame import OBJ_WIN

    if pl == 0:
        return v
    return 1.0 - v if obj == OBJ_WIN else -v


def _idx(rows, cell, g, piece) -> int:
    hit = np.nonzero((rows[:, 0] == cell) & (rows[:, 1] == g) & (rows[:, 2] == piece))[0]
    return int(hit[0]) if len(hit) else -1


def analyze(agent, S, min_gap: float, seed: int) -> dict | None:
    """手番の局面 S を読み切り、最善と次善の勝率の差が min_gap 以上なら局面の記録を返す。"""
    from carcassonne.endgame import OBJ_DIFF, OBJ_WIN, bag_left, solve
    from carcassonne.fast import SC_PL, SC_S0, SC_SUP0, copy_state, seed_rng

    f = agent.fast
    pl = int(S[10][SC_PL])
    _, rows, _n = solve(f, S, OBJ_WIN)
    win = _mover(rows[:, 3], pl, OBJ_WIN)
    best, second, nb = gap_of(win)
    if best - second < min_gap - EPS:
        return None
    facts = [move_facts(f, S, *map(int, rows[j, :3])) for j in range(len(rows))]
    lead_now = np.array([x["proj_me"] - x["proj_opp"] for x in facts])
    # 目先の点（見込み点差）が一番大きい手。同点が複数あれば、人はその中から選ぶので平均の勝率も残す
    gc = np.nonzero(lead_now >= lead_now.max())[0]
    gw = int(gc[np.argmin(win[gc])])
    _, rd, _ = solve(f, S, OBJ_DIFF)
    dv = _mover(rd[:, 3], pl, OBJ_DIFF)
    dc = [_idx(rows, *rd[j, :3]) for j in np.nonzero(dv >= dv.max() - EPS)[0]]
    di = min(dc, key=lambda j: win[j])
    seed_rng(seed)
    ci = _idx(rows, *agent.choose_search(copy_state(S)))
    bi = [j for j in range(len(rows)) if win[j] >= best - EPS]
    # 最善の手が複数あるときは、見込み点差の変化が一番小さい（＝目先の点から一番離れた）手を代表に
    rep = min(bi, key=lambda j: lead_now[j])

    def mv(j):
        return {
            "move": _decode(f, *map(int, rows[j, :3])),
            "win": round(float(win[j]), 6),
            **facts[j],
        }

    return {
        "bag": bag_left(S),
        "mover": pl,
        "score_me": int(S[10][SC_S0 + pl]),
        "score_opp": int(S[10][SC_S0 + 1 - pl]),
        "meeples_me": int(S[10][SC_SUP0 + pl]),
        "meeples_opp": int(S[10][SC_SUP0 + 1 - pl]),
        "tile": _decode(f, *map(int, rows[0, :3]))[2],
        "moves": len(rows),
        "n_best": nb,
        "best": round(best, 6),
        "second": round(second, 6),
        "gap": round(best - second, 6),
        "best_move": mv(rep),
        "greedy": mv(gw)
        | {
            "ties": len(gc),
            "win_mean": round(float(win[gc].mean()), 6),
            "n_best": int((win[gc] >= best - EPS).sum()),
        },
        "diff": mv(di),
        "champ": mv(ci) if ci >= 0 else None,
    }


def _job(args):
    path, gi, bags, min_gap, seed = args
    from carcassonne.endgame import bag_left
    from carcassonne.fast import SC_OVER, apply_move
    from carcassonne.webplay import make_agent

    agent = make_agent("strong")
    f = agent.fast
    sc = f.scratch
    d = np.load(path)
    deck = [int(t) for t in d["deck"][gi]]
    S = f.new_game(deck)
    hist: list = []
    out = []
    for k in range(int(d["nmoves"][gi])):
        if S[10][SC_OVER]:
            break
        rec = tuple(int(x) for x in d["moves"][gi, k])
        if bag_left(S) in bags:
            r = analyze(agent, S, min_gap, seed + k)
            if r is not None:
                head = {"file": Path(path).name, "game": gi, "ply": k}
                out.append(head | r | {"deck": deck, "history": list(hist)})
        hist.append(_decode(f, *rec))
        apply_move(S, f.T, f.P, *rec, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    return out


def _refresh(args):
    """保存した局面（deck・history）から読み直す（解析の項目を足したとき、全局を再生し直さずに済む）。"""
    rows, min_gap, seed = args
    from carcassonne.webplay import make_agent

    agent = make_agent("strong")
    f = agent.fast
    out = []
    for r in rows:
        S = f.new_game(r["deck"])
        for x, y, ti, vi, piece in r["history"]:
            f.apply(S, x, y, ti, vi, piece)
        a = analyze(agent, S, min_gap, seed + r["ply"])
        if a is not None:
            head = {k: r[k] for k in ("file", "game", "ply")}
            out.append(head | a | {"deck": r["deck"], "history": r["history"]})
    return out


def lesson(r: dict) -> str:
    """最善手と「目先の点」の手の違いから、学びどころの型を決める（人が読む分類、厳密ではない）。"""
    b, g = r["best_move"], r["greedy"]
    if g["n_best"] == g["ties"]:
        return "目先の点で正解"
    if g["n_best"] > 0:
        return "点は同じ、置き場所で決まる"
    if b["meeple"] is None and g["meeple"] is not None:
        return "ミープルを置かない"
    if b["meeple"] is not None and g["meeple"] is None:
        return "最後のミープルを使う"
    if b["meeple"] != g["meeple"]:
        return "ミープルの置き先を変える"
    if b["proj_opp"] < g["proj_opp"]:
        return "相手の点を止める"
    return "目先の点を捨てる"


def summarize(path: str, n_examples: int = 3) -> dict:
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x]
    games = {(r["file"], r["game"]) for r in rows}

    def loss(rs, key):
        # 目先の点の手は、同点の中から選ぶので平均の勝率で数える
        v = [r["best"] - r[key].get("win_mean", r[key]["win"]) for r in rs if r.get(key)]
        return {
            "miss": sum(x > EPS for x in v),
            "mean_loss": round(sum(v) / max(1, len(v)), 4),
        }

    by_lesson: dict[str, list] = {}
    for r in rows:
        by_lesson.setdefault(lesson(r), []).append(r)
    res = {
        "source": Path(path).name,
        "games": len(games),
        "positions": len(rows),
        "by_bag": {
            str(b): sum(r["bag"] == b for r in rows) for b in sorted({r["bag"] for r in rows})
        },
        "unique_best": sum(r["n_best"] == 1 for r in rows),
        # クイズ向き: 最善手が合法手の4分の1以下（どこに置いても勝てる局面は問題にならない）
        "quiz_ready": sum(r["n_best"] <= r["moves"] / 4 for r in rows),
        "no_meeples": sum(r["meeples_me"] == 0 for r in rows),
        "close": sum(abs(r["score_me"] - r["score_opp"]) <= 20 for r in rows),
        "mean_gap": round(sum(r["gap"] for r in rows) / max(1, len(rows)), 4),
        "traps": {k: loss(rows, k) for k in ("greedy", "diff", "champ")},
        "lessons": {},
    }
    for name, rs in sorted(by_lesson.items(), key=lambda kv: -len(kv[1])):
        ex = sorted(rs, key=lambda r: (r["n_best"] / r["moves"], -r["gap"]))[:n_examples]
        res["lessons"][name] = {
            "count": len(rs),
            "greedy_loss": loss(rs, "greedy"),
            "examples": [
                {
                    "id": f"{r['file'][:-4]}_g{r['game']}_p{r['ply']}",
                    "bag": r["bag"],
                    "score": [r["score_me"], r["score_opp"]],
                    "meeples": [r["meeples_me"], r["meeples_opp"]],
                    "best": r["best"],
                    "n_best": [r["n_best"], r["moves"]],
                    "best_meeple": KIND_JA[r["best_move"]["meeple"]],
                    "best_proj": [r["best_move"]["proj_me"], r["best_move"]["proj_opp"]],
                    "greedy_win": r["greedy"]["win_mean"],
                    "greedy_meeple": KIND_JA[r["greedy"]["meeple"]],
                    "greedy_proj": [r["greedy"]["proj_me"], r["greedy"]["proj_opp"]],
                }
                for r in ex
            ],
        }
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--records", nargs="*", default=[])
    ap.add_argument("--games", type=int, default=50, help="使う局数（ファイルを順にまたぐ）")
    ap.add_argument("--bags", default="2,3", help="調べる山札の残り枚数（カンマ区切り）")
    ap.add_argument("--min-gap", type=float, default=0.15)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out")
    ap.add_argument("--summary", help="集計する JSONL（--out に JSON を書く。無ければ表示）")
    ap.add_argument("--refresh", help="この JSONL の局面だけを読み直して --out に書く")
    a = ap.parse_args()
    if a.refresh:
        rows = [
            json.loads(x) for x in Path(a.refresh).read_text(encoding="utf-8").splitlines() if x
        ]
        chunks = [(rows[i :: a.workers], a.min_gap, a.seed) for i in range(a.workers)]
        with ProcessPoolExecutor(a.workers) as ex:
            out = [r for part in ex.map(_refresh, chunks) for r in part]
        out.sort(key=lambda r: (r["file"], r["game"], r["ply"]))
        Path(a.out).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8"
        )
        print(f"{len(out)}/{len(rows)} positions", flush=True)
        return
    if a.summary:
        from carcassonne.webplay import champion_info

        res = {"ai": champion_info()["name"], "min_gap": a.min_gap} | summarize(a.summary)
        text = json.dumps(res, ensure_ascii=False, indent=1) + "\n"
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return
    bags = tuple(int(x) for x in a.bags.split(","))
    files = sorted(p for pat in a.records for p in glob.glob(pat))
    jobs = []
    for p in files:
        for gi in range(len(np.load(p)["nmoves"])):
            if len(jobs) < a.games:
                seed = random.Random(a.seed + len(jobs)).getrandbits(30)
                jobs.append((p, gi, bags, a.min_gap, seed))
    done = set()
    if Path(a.out).exists():
        for x in Path(a.out).read_text(encoding="utf-8").splitlines():
            r = json.loads(x)
            done.add((r["file"], r["game"]))
    jobs = [j for j in jobs if (Path(j[0]).name, j[1]) not in done]
    with ProcessPoolExecutor(a.workers) as ex, open(a.out, "a", encoding="utf-8") as fo:
        for n, out in enumerate(ex.map(_job, jobs), 1):
            for r in out:
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            fo.flush()
            print(f"{n}/{len(jobs)} games: +{len(out)}", flush=True)


if __name__ == "__main__":
    main()
