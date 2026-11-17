"""次の一手クイズ（data/puzzles.json）の答えを、いまの最新AI（チャンピオン）で確かめ直す。

    py scripts/recheck_puzzles.py            # 全問を解析し直して data/puzzles.json を書き換える
    py scripts/recheck_puzzles.py --only s0t48

各問の局面を、問題を作ったときと同じ深い探索（12000回×5・4決定化・10手のロールアウト）で
最新AIに解析させ、選択肢ごとの「AIの予想点差」を書き直す。
最新AIが選択肢の中で一番よいとした手が、問題の正解（options の先頭）と違う問題は
`disputed` を付けて公開ページから外す（解説が正解の手を前提に書かれているため）。
付けた問題は人が見直し、解説を書き直すか差し替える。

終盤編の問題（"exact": true）は、AIではなく終局までの読み切り（`endgame.solve`）で各選択肢の勝つ確率を
計算し直す。答えはAIの強さに依らないが、ルールやエンジンを変えたときの確かめになる。
"""

from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from carcassonne.state import Move, State

SRC = ROOT / "data" / "puzzles.json"


def recheck(p: dict, sims: int = 12000) -> dict:
    from carcassonne.fast_mcts import FastMCTSAgent
    from carcassonne.puzzles import analyze
    from carcassonne.webplay import champion_eval_path

    st = State.new_game(p["seed"])
    for x, y, _ti, vi, piece in p["history"]:
        st.apply(Move(x, y, vi, piece))
    deep = FastMCTSAgent(n_sims=sims * 5, n_det=4, rollout_depth=10, eval_path=champion_eval_path())
    opts = analyze(deep, st, p["seed"] * 1000 + p["turn"] + 500)
    total = sum(o.visits for o in opts)
    by_move = {(o.move.x, o.move.y, o.move.variant, o.move.piece): o for o in opts}
    diffs, visits = [], []
    for o in p["options"]:
        hit = by_move.get(tuple(o["move"]))
        # 一度も探索されなかった手は「最悪の手」とみなす（点差は前の値を残す）
        diffs.append(round(hit.diff, 2) if hit else None)
        visits.append(round(hit.visits / total, 4) if hit else 0.0)
    scored = [(d if d is not None else -1e9, i) for i, d in enumerate(diffs)]
    top = max(scored, key=lambda t: (t[0], -t[1]))[1]  # 同点なら先頭（正解）の選択肢を優先
    m = opts[0].move
    top_move = (m.x, m.y, m.variant, m.piece)
    listed = any(tuple(o["move"]) == top_move for o in p["options"])
    return {
        "id": p["id"],
        "diffs": diffs,
        "visits": visits,
        # AIが一番よく選ぶ手が選択肢の外なら、「AIならどの手？」の答えも成り立たない
        "best_ok": top == 0 and listed,
        "top": top,
        "ai_top_listed": listed,
    }


def recheck_exact(p: dict) -> dict:
    """終盤編の問題を読み切り直す（各選択肢の勝つ確率。正解＝先頭の選択肢が最大のままか）。"""
    import endgame_quiz

    from carcassonne.webplay import make_agent

    fast = make_agent("strong").fast
    S = endgame_quiz.fast_state(fast, p)
    wins = [
        round(endgame_quiz.exact_win(fast, S, [x, y, p["current"], vi, piece]), 6)
        for x, y, vi, piece in (o["move"] for o in p["options"])
    ]
    top = max(range(len(wins)), key=lambda i: (wins[i], -i))
    return {
        "id": p["id"],
        "wins": wins,
        "best_ok": top == 0 and all(w < wins[0] for w in wins[1:]),
        "top": top,
    }


def reason(r: dict) -> str:
    """正解が成り立たなくなった理由（選択肢の中の点差と、AIが一番よく選ぶ手の両方を見る）。"""
    out = []
    if r["top"] != 0:
        out.append(f"選択肢{r['top'] + 1}の点差が最大")
    if not r.get("ai_top_listed", True):
        out.append("一番よく選ぶ手は選択肢の外")
    return "、".join(out)


def apply_results(puzzles: list[dict], results: list[dict], ai: dict) -> list[str]:
    """解析結果を問題に書き込み、正解が変わった問題の id を返す。"""
    res = {r["id"]: r for r in results}
    bad = []
    for p in puzzles:
        r = res.get(p["id"])
        if r is None:
            continue
        if "wins" in r:  # 終盤編（読み切り）
            for o, w in zip(p["options"], r["wins"]):
                o["win"] = w
            p["checked_by"] = {"name": "読み切り", "date": ai.get("date")}
            if r["best_ok"]:
                p.pop("disputed", None)
            else:
                p["disputed"] = f"読み切り: 選択肢{r['top'] + 1}の勝つ確率が最大"
                bad.append(p["id"])
            continue
        for o, d, v in zip(p["options"], r["diffs"], r["visits"]):
            if d is not None:
                o["diff"] = d
            o["visits"] = v
        p["checked_by"] = {"name": ai["name"], "date": ai.get("date")}
        if r["best_ok"]:
            p.pop("disputed", None)
        else:
            p["disputed"] = f"{ai['name']}: {reason(r)}"
            bad.append(p["id"])
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--sims", type=int, default=12000)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    from carcassonne.webplay import champion_info

    ai = champion_info()
    src = Path(args.src)
    puzzles = json.loads(src.read_text(encoding="utf-8"))
    todo = [p for p in puzzles if not args.only or p["id"] in args.only]
    with Pool(args.workers) as pool:
        results = pool.starmap(recheck, [(p, args.sims) for p in todo if not p.get("exact")])
        results += pool.map(recheck_exact, [p for p in todo if p.get("exact")])
    for r in results:
        if "wins" in r:
            print(
                f"{r['id']}: {'OK' if r['best_ok'] else 'NG'} 勝つ確率 {r['wins']}（読み切り）",
                flush=True,
            )
            continue
        mark = "OK" if r["best_ok"] else f"NG（{reason(r)}）"
        extra = "" if r["ai_top_listed"] else "（AIの一番手は選択肢の外）"
        print(f"{r['id']}: {mark} 点差 {r['diffs']}{extra}", flush=True)
    bad = apply_results(puzzles, results, ai)
    src.write_text(json.dumps(puzzles, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{ai['name']} で {len(results)} 問を確かめた。正解が変わった問題: {bad or 'なし'}")


if __name__ == "__main__":
    main()
