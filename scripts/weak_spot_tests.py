"""人が外した局面のテスト問題（BACKLOG R-014）。

人の棋譜で、人が3点以上損した手（docs/results/human_findings_cache.json の採点）の局面を集め、
最強の探索（12000回・depth=10、乱数を変えて2回の平均）で答え（最善から1.5点以内の手）がはっきりした
局面だけを問題にする。候補の評価関数は、2000回の探索（自己対戦ループの判定と同じ）で各問題に1手ずつ答え、
正答率と平均の損（最強の探索の見積もりで、最善より何点損したか）を出す。200局の対戦（4コアで約15分）よりずっと速い（数十秒）ので、学習の改善を早く見分けられるかを確かめる。

    py scripts/weak_spot_tests.py build                       # data/weak_spot_tests.json を作る
    py scripts/weak_spot_tests.py score models/eval_champion.npy other.npy ...
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne import human_games as hg
from carcassonne.human_findings import BAD
from carcassonne.state import Move, State
from carcassonne.tiles import load_tileset

GAMES = ROOT / "data" / "human_games.jsonl"
CACHE = ROOT / "docs" / "results" / "human_findings_cache.json"
OUT = ROOT / "data" / "weak_spot_tests.json"
GOOD = 1.5  # 最善からこの点数以内の手を正解にする
CLEAR = 3.0  # 最善と人の手の差がこれ以上（2回の平均）の局面だけ問題にする
TOP = 40  # 問題ごとに予想点差を残す手の数


def _mv(m: Move) -> list[int]:
    return [m.x, m.y, m.variant, -1 if m.piece is None else m.piece]


def positions() -> list[dict]:
    games = {hg.key(r): r for r in hg.load(GAMES)}
    out = []
    for line in CACHE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        k, c = json.loads(line)
        r = games.get(k)
        if r is None:
            continue
        for m in c["moves"]:
            if m["loss"] is not None and m["loss"] >= BAD:
                out.append({"game": k, "ply": m["ply"], "human": r["moves"][m["ply"]]})
    return out


def state_at(rec: dict, ply: int) -> State:
    st = State(rec["deck"], load_tileset())
    for x, y, v, p in rec["moves"][:ply]:
        st.apply(Move(x, y, v, None if p < 0 else p))
    return st


_AGENTS: dict = {}


def _agent(sims: int, eval_path: str):
    from carcassonne.fast_mcts import FastMCTSAgent

    key = (sims, eval_path)
    if key not in _AGENTS:
        _AGENTS[key] = FastMCTSAgent(sims, eval_path=eval_path, rollout_depth=10)
    return _AGENTS[key]


def _build_one(job):
    pos, rec, eval_path = job
    from carcassonne.puzzles import analyze

    st = state_at(rec, pos["ply"])
    agent = _agent(12000, eval_path)
    vals: dict[tuple, list[float]] = {}
    for seed in (pos["ply"], pos["ply"] + 7919):
        for o in analyze(agent, st, seed):
            vals.setdefault(tuple(_mv(o.move)), []).append(o.diff)
    both = {m: sum(v) / 2 for m, v in vals.items() if len(v) == 2}
    if not both:
        return None
    best = max(both.values())
    human = both.get(tuple(pos["human"]))
    if human is None or best - human < CLEAR:
        return None
    good = sorted([list(m) for m, v in both.items() if v >= best - GOOD])
    # 損の物差し: 上位 TOP 手の予想点差（それより下の手は、表の一番下と同じ損とみなす）
    top = sorted(both.items(), key=lambda kv: -kv[1])[:TOP]
    vals = [[*m, round(v, 2)] for m, v in top]
    return {
        **pos,
        "best": round(best, 2),
        "human_loss": round(best - human, 2),
        "good": good,
        "vals": vals,
    }


def build(a) -> None:
    from carcassonne.webplay import champion_eval_path, champion_info

    games = {hg.key(r): r for r in hg.load(GAMES)}
    ev = champion_eval_path()
    jobs = [(p, games[p["game"]], ev) for p in positions()]
    with ProcessPoolExecutor(a.workers) as ex:
        res = [r for r in ex.map(_build_one, jobs, chunksize=1) if r is not None]
    OUT.write_text(
        json.dumps(
            {
                "teacher": champion_info().get("name"),
                "good_within": GOOD,
                "clear": CLEAR,
                "tests": res,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{OUT}: 候補 {len(jobs)} 局面のうち {len(res)} 問")


def _score_one(job):
    t, rec, eval_path, sims, seed = job
    from carcassonne.puzzles import analyze

    st = state_at(rec, t["ply"])
    mv = _mv(analyze(_agent(sims, eval_path), st, seed)[0].move)
    table = {tuple(v[:4]): v[4] for v in t["vals"]}
    loss = t["best"] - table.get(tuple(mv), min(table.values()))
    return mv in t["good"], mv == t["human"], loss


def score(paths: list[str], sims: int = 2000, workers: int = 4, seed: int = 1000) -> list[dict]:
    games = {hg.key(r): r for r in hg.load(GAMES)}
    tests = json.loads(OUT.read_text(encoding="utf-8"))["tests"]
    out = []
    for p in paths:
        jobs = [(t, games[t["game"]], str(p), sims, seed + i) for i, t in enumerate(tests)]
        with ProcessPoolExecutor(workers) as ex:
            r = list(ex.map(_score_one, jobs, chunksize=4))
        ok, same = sum(x for x, _, _ in r), sum(y for _, y, _ in r)
        loss = sum(z for _, _, z in r) / len(r)
        out.append(
            {
                "eval": str(p),
                "n": len(r),
                "correct": ok,
                "human_mistake": same,
                "mean_loss": round(loss, 3),
            }
        )
        print(
            f"{p}: 正解 {ok}/{len(r)}（{ok / len(r):.1%}） 平均の損 {loss:.2f}点 人と同じ悪手 {same}"
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("--workers", type=int, default=4)
    s = sub.add_parser("score")
    s.add_argument("evals", nargs="+")
    s.add_argument("--sims", type=int, default=2000)
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--seed", type=int, default=1000, help="探索の乱数（問題 i は seed+i）")
    s.add_argument("--out", help="結果の JSON")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a)
    else:
        res = score(a.evals, a.sims, a.workers, a.seed)
        if a.out:
            Path(a.out).write_text(
                json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
            )


if __name__ == "__main__":
    main()
