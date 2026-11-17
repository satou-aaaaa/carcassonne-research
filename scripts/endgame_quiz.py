"""終盤クイズの問題の候補を作る（BACKLOG R-007）。

`data/endgame_puzzles.jsonl`（scripts/endgame_puzzles.py）の局面から、次の一手クイズ（data/puzzles.json）と
同じ形の候補を作る。選択肢は 最善手・目先の点の手・次善の手（・最強AIの探索の手）で、どれも厳密な勝率
（`win`、読み切り）を持つ。解説を書くための材料として、選択肢ごとに「相手が次に引くタイルの種類ごとの勝率」
（`draws`）も付ける（ページには出さない）。

    py scripts/endgame_quiz.py rec_1002_g11_p67 rec_1002_g8_p68 --out runs/endgame_quiz.jsonl --svg runs/endgame_quiz

採用した問題は、題名・問題文・解説（日英）を書き足して data/puzzles.json に入れる（"exact": true）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from carcassonne.puzzles import move_facts, snapshot, track_meeples
from carcassonne.state import Move, State

SRC = ROOT / "data" / "endgame_puzzles.jsonl"
EPS = 1e-9


def pid(r: dict) -> str:
    return f"{r['file'][:-4]}_g{r['game']}_p{r['ply']}"


def replay(r: dict) -> tuple[State, list[dict]]:
    """Python の State で局面を再現する（ミープルの位置も追う）。"""
    st = State(r["deck"])
    meeples: list[dict] = []
    for x, y, _ti, vi, piece in r["history"]:
        mv = Move(x, y, vi, piece)
        pl = st.player
        st.apply(mv)
        meeples = track_meeples(st, meeples, mv, pl)
    return st, meeples


def fast_state(fast, r: dict):
    S = fast.new_game(r["deck"])
    for x, y, ti, vi, piece in r["history"]:
        fast.apply(S, x, y, ti, vi, piece)
    return S


def _cell(x, y):
    from carcassonne.fast import C0, G

    return (x + C0) * G + (y + C0)


def exact_win(fast, S, move: list) -> float:
    """手番側がこの手を指したときの厳密な勝率（読み切り）。"""
    from carcassonne.endgame import OBJ_WIN, solve
    from carcassonne.fast import SC_PL

    pl = int(S[10][SC_PL])
    _, rows, _ = solve(fast, S, OBJ_WIN)
    x, y, ti, vi, piece = move
    g = int(fast.T[11][ti]) + vi
    pc = -1 if piece is None else piece
    hit = np.nonzero((rows[:, 0] == _cell(x, y)) & (rows[:, 1] == g) & (rows[:, 2] == pc))[0]
    v = float(rows[hit[0], 3])
    return v if pl == 0 else 1.0 - v


def draws(fast, S, move: list, names: list[str]) -> list[dict]:
    """この手のあと、相手が引くタイルの種類ごとの確率・勝率（手番側から見た値）と、相手の最善の返し手。"""
    from carcassonne.endgame import OBJ_WIN, _apply_nodraw, _chance, solve
    from carcassonne.fast import (
        SC_CUR,
        SC_DISC,
        SC_DRAW,
        SC_END,
        SC_PL,
        SC_S0,
        copy_state,
        gen_placements,
    )

    sc = fast.scratch
    me = int(S[10][SC_PL])
    x, y, ti, vi, piece = move
    X = copy_state(S)
    _apply_nodraw(
        X, fast.T, fast.P, _cell(x, y), int(fast.T[11][ti]) + vi, -1 if piece is None else piece
    )
    lo, end = int(X[10][SC_DRAW]), int(X[10][SC_END])
    out = []
    if lo >= end:
        v = _chance(
            X,
            fast.T,
            fast.P,
            OBJ_WIN,
            0.0,
            1.0,
            sc.stamp,
            sc.stamp_box,
            sc.out_cell,
            sc.out_g,
            np.zeros(1, np.int64),
        )
        return [{"tile": None, "p": 1.0, "win": round(v if me == 0 else 1 - v, 6)}]
    kinds = [int(t) for t in X[11][lo:end]]
    for t in sorted(set(kinds)):
        j = lo + kinds.index(t)
        Y = copy_state(X)
        Y[11][j] = Y[11][lo]
        Y[11][lo] = t
        Y[10][SC_DRAW] = lo + 1
        sc.stamp_box[0] += 1
        row = {"tile": t, "name": names[t], "p": round(kinds.count(t) / len(kinds), 6)}
        if gen_placements(Y, fast.T, t, sc.stamp, sc.stamp_box[0], sc.out_cell, sc.out_g, True) > 0:
            Y[10][SC_CUR] = t
            v, rows, _ = solve(fast, Y, OBJ_WIN)
            opp = 1 - me
            ow = rows[:, 3] if opp == 0 else 1.0 - rows[:, 3]
            k = int(np.argmax(ow))
            from endgame_puzzles import _decode
            from endgame_puzzles import move_facts as fmove_facts

            row["reply"] = _decode(fast, *map(int, rows[k, :3]))
            row["reply_facts"] = fmove_facts(fast, Y, *map(int, rows[k, :3]))
            row["pv"] = line(fast, Y, *map(int, rows[k, :3]))
            row["win"] = round(v if me == 0 else 1 - v, 6)
        else:
            Y[10][SC_DISC] += 1
            v = _chance(
                Y,
                fast.T,
                fast.P,
                OBJ_WIN,
                0.0,
                1.0,
                sc.stamp,
                sc.stamp_box,
                sc.out_cell,
                sc.out_g,
                np.zeros(1, np.int64),
            )
            row["discard"] = True
            row["win"] = round(v if me == 0 else 1 - v, 6)
        row["score_after"] = [int(Y[10][SC_S0 + me]), int(Y[10][SC_S0 + 1 - me])]
        out.append(row)
    return out


KINDS = ("city", "road", "field", "monastery")


def projected_by_kind(fast, S) -> dict:
    """今終局したときの見込み点を、特徴の種類ごと・手番ごとに（{種類: [先手, 後手]}、得点済みは含まない）。"""
    from carcassonne.fast import NT, end_points, find

    pts = np.zeros(NT * fast.P, np.int32)
    end_points(S, fast.T, fast.P, pts)
    parent, meep, kind = S[3], S[9], S[4]
    out = {k: [0, 0] for k in KINDS}
    for r in np.nonzero(pts)[0]:
        if find(parent, r) != r:
            continue
        m0, m1 = int(meep[r * 2]), int(meep[r * 2 + 1])
        top = max(m0, m1)
        for pl, m in ((0, m0), (1, m1)):
            if top > 0 and m == top:
                out[KINDS[int(kind[r])]][pl] += int(pts[r])
    return out


def line(fast, S, cell: int, g: int, piece: int) -> list[dict]:
    """S で (cell, g, piece) を指したあと、両者が勝率最善で進めた筋（引きは山札の残りが1種類のときだけ続ける）。

    各手: 着手 [x, y, 種別, 向き, 断片]・指した人・即時得点・指したあとの見込み点、最後に終局の得点。
    """
    from endgame_puzzles import _decode

    from carcassonne.endgame import OBJ_WIN, _apply_nodraw, solve
    from carcassonne.fast import (
        SC_CUR,
        SC_DRAW,
        SC_END,
        SC_PL,
        SC_S0,
        copy_state,
        finish,
        gen_placements,
        projected,
    )  # fmt: skip

    sc = fast.scratch
    X = copy_state(S)
    out = []
    while True:
        pl = int(X[10][SC_PL])
        before = [int(X[10][SC_S0]), int(X[10][SC_S0 + 1])]
        _apply_nodraw(X, fast.T, fast.P, cell, g, piece)
        pr = projected(X, fast.T, fast.P)
        bk = projected_by_kind(fast, X)
        out.append(
            {
                "player": pl,
                "move": _decode(fast, cell, g, piece),
                "gain": [int(X[10][SC_S0]) - before[0], int(X[10][SC_S0 + 1]) - before[1]],
                "projected": [int(pr[0]), int(pr[1])],
                "by_kind": {k: v for k, v in bk.items() if v != [0, 0]},
            }
        )
        lo, end = int(X[10][SC_DRAW]), int(X[10][SC_END])
        if lo >= end or len({int(t) for t in X[11][lo:end]}) > 1:
            break
        t = int(X[11][lo])
        X[10][SC_DRAW] = lo + 1
        sc.stamp_box[0] += 1
        if (
            gen_placements(X, fast.T, t, sc.stamp, sc.stamp_box[0], sc.out_cell, sc.out_g, True)
            == 0
        ):
            break
        X[10][SC_CUR] = t
        _, rows, _ = solve(fast, X, OBJ_WIN)
        w = rows[:, 3] if int(X[10][SC_PL]) == 0 else 1.0 - rows[:, 3]
        cell, g, piece = map(int, rows[int(np.argmax(w)), :3])
    if int(X[10][SC_DRAW]) >= int(X[10][SC_END]):
        X[10][SC_CUR] = -1
        finish(X, fast.T, fast.P)
        out.append({"final": [int(X[10][SC_S0]), int(X[10][SC_S0 + 1])]})
    return out


def candidate(r: dict, fast, names: list[str], n_opts: int = 3) -> dict:
    from endgame_puzzles import _decode
    from endgame_puzzles import move_facts as fmove_facts

    from carcassonne.endgame import OBJ_WIN, solve
    from carcassonne.fast import SC_PL

    st, meeples = replay(r)
    S = fast_state(fast, r)
    picks = [r["best_move"]["move"], r["greedy"]["move"]]
    for k in ("champ", "diff"):
        if r.get(k):
            picks.append(r[k]["move"])
    # 足りなければ、ほかのマスの手から目先の点（見込み点差）の大きい順に足す
    pl = int(S[10][SC_PL])
    _, rows, _ = solve(fast, S, OBJ_WIN)
    others = []
    for j in range(len(rows)):
        m = _decode(fast, *map(int, rows[j, :3]))
        f = fmove_facts(fast, S, *map(int, rows[j, :3]))
        w = rows[j, 3] if pl == 0 else 1 - rows[j, 3]
        others.append((-(f["proj_me"] - f["proj_opp"]), -w, m))
    for _, _, m in sorted(others, key=lambda t: t[:2]):
        picks.append(m)
    opts, seen, cells = [], set(), set()
    for m in picks:
        key = tuple(m)
        if key in seen or len(opts) >= n_opts:
            continue
        if len(opts) >= 2 and (m[0], m[1]) in cells:  # 3つ目からは別のマスの手だけ
            continue
        seen.add(key)
        cells.add((m[0], m[1]))
        x, y, _ti, vi, piece = m
        mv = Move(x, y, vi, piece)
        opts.append(
            {
                "move": [x, y, vi, piece],
                "win": round(exact_win(fast, S, m), 6),
                "facts": move_facts(st, mv),
                "draws": draws(fast, S, m, names),
            }
        )
    best = opts[0]["win"]
    assert abs(best - r["best"]) < 1e-6, (pid(r), best, r["best"])
    return {
        "id": pid(r),
        "exact": True,
        "by_kind": {k: v for k, v in projected_by_kind(fast, S).items() if v != [0, 0]},
        "history": [[x, y, ti, vi, p] for x, y, ti, vi, p in r["history"]],
        "deck": r["deck"],
        **snapshot(st, meeples),
        "options": opts,
    }


def render_svg(c: dict, path: Path) -> None:
    """盤面全体と選択肢の位置（A, B, ...）を SVG に描く（解説を書くときに見る）。"""
    from board_svg import board_svg

    st, meeples = replay({"deck": c["deck"], "history": c["history"]})
    xs = [b["x"] for b in c["board"]] + [o["move"][0] for o in c["options"]]
    ys = [b["y"] for b in c["board"]] + [o["move"][1] for o in c["options"]]
    cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
    rad = max(max(xs) - min(xs), max(ys) - min(ys)) // 2 + 1
    labels = [(o["move"][0], o["move"][1], "ABCD"[i]) for i, o in enumerate(c["options"])]
    hl = [(o["move"][0], o["move"][1], "#e0a000") for o in c["options"]]
    svg = board_svg(st, meeples, (cx, cy), radius=rad, S=48, highlight=hl, labels=labels)
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", required=True)
    ap.add_argument("--svg", help="盤面の SVG を書くフォルダ")
    ap.add_argument("--options", type=int, default=3, help="選択肢の数")
    a = ap.parse_args()
    from carcassonne.webplay import make_agent

    fast = make_agent("strong").fast
    names = [t.id for t in State.new_game(0).ts.types]
    rows = {
        pid(r): r for r in map(json.loads, Path(a.src).read_text(encoding="utf-8").splitlines())
    }
    cands = [candidate(rows[i], fast, names, a.options) for i in a.ids]
    Path(a.out).write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cands), encoding="utf-8"
    )
    if a.svg:
        Path(a.svg).mkdir(parents=True, exist_ok=True)
        for c in cands:
            render_svg(c, Path(a.svg) / f"{c['id']}.svg")
    print(f"{len(cands)} 問の候補を {a.out} に書き出しました")


if __name__ == "__main__":
    main()
