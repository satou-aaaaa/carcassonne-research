"""データページ（docs/stats.html）用の集計。対局の記録から docs/results/game_stats.json を作る。

    py scripts/summarize_game_stats.py runs/stats --out docs/results/game_stats.json

入力（runs/stats/ に置く）:
- selfplay.jsonl: 最新チャンピオン同士の対局の記録（scripts/collect_game_stats.py）。
  同じ山札を2回ずつ指している（山札の運の大きさを測るため）。
- <名前>.jsonl: AIの強さ別の対戦（scripts/run_match.py --log）。LADDER の組み合わせ。

先手の勝率は引き分けを0.5勝として、Wilson区間と両側の二項検定（引き分けを除く）で評価する。
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from first_player import binom_two_sided

from carcassonne.arena import wilson
from carcassonne.webplay import champion_info

KINDS = ["C", "R", "M", "F"]
# AIの強さ別の対戦（強い方, 弱い方, ファイル名）。名前はページの表に出すキー
LADDER = [
    ("greedy", "random", "greedy_vs_random"),
    ("standard", "greedy", "std_vs_greedy"),
    ("strong", "standard", "strong_vs_std"),
]
CHECKPOINTS = [0.25, 0.5, 0.75]  # 局面の何割まで進んだところで「リードしている側」を見るか


def _r(x: float, nd: int = 3) -> float:
    return round(float(x), nd)


def first_player(games: list[dict]) -> dict:
    n = len(games)
    w = sum(1 for g in games if g["scores"][0] > g["scores"][1])
    loss = sum(1 for g in games if g["scores"][0] < g["scores"][1])
    d = n - w - loss
    score = (w + 0.5 * d) / n
    lo, hi = wilson(w + 0.5 * d, n)
    diffs = [g["scores"][0] - g["scores"][1] for g in games]
    mean = statistics.fmean(diffs)
    se = statistics.stdev(diffs) / math.sqrt(n)
    return {
        "games": n,
        "wins": w,
        "losses": loss,
        "draws": d,
        "score": _r(score, 4),
        "ci": [_r(lo, 4), _r(hi, 4)],
        "p_value": float(f"{binom_two_sided(w, w + loss):.3g}"),
        "mean_diff": _r(mean, 2),
        "se_diff": _r(se, 2),
        "draw_rate": _r(d / n, 4),
    }


def scores(games: list[dict]) -> dict:
    pts = [s for g in games for s in g["scores"]]
    margins = [abs(g["scores"][0] - g["scores"][1]) for g in games]
    win = [max(g["scores"]) for g in games]
    lose = [min(g["scores"]) for g in games]
    hist = Counter(min(m // 5, 10) for m in margins)  # 5点刻み、50点以上はまとめる
    return {
        "mean": _r(statistics.fmean(pts), 1),
        "median": statistics.median(pts),
        "min": min(pts),
        "max": max(pts),
        "winner_mean": _r(statistics.fmean(win), 1),
        "loser_mean": _r(statistics.fmean(lose), 1),
        "margin_mean": _r(statistics.fmean(margins), 1),
        "margin_median": statistics.median(margins),
        "close5": _r(sum(m <= 5 for m in margins) / len(margins), 4),
        "close10": _r(sum(m <= 10 for m in margins) / len(margins), 4),
        "margin_hist": [hist.get(i, 0) for i in range(11)],
        "plies": _r(statistics.fmean(len(g["moves"]) for g in games), 2),
        "discarded_rate": _r(sum(g["discarded"] > 0 for g in games) / len(games), 4),
    }


def sources(games: list[dict]) -> dict:
    """得点源の内訳（全得点に対する割合）と、ミープルを置いた所が未完成で終わった割合。"""
    pts = defaultdict(float)  # (kind, end) -> 点（両者合計）
    cnt = defaultdict(int)  # (kind, end) -> 件数
    total = 0.0
    for g in games:
        for players, kind, p, end, _ply in g["awards"]:
            pts[(kind, end)] += p * len(players)
            cnt[(kind, end)] += 1
            total += p * len(players)
        assert abs(sum(g["scores"]) - sum(p * len(pl) for pl, _k, p, _e, _ in g["awards"])) < 1e-9
    n = len(games)
    out = {}
    for k in KINDS:
        done, left = cnt[(k, 0)], cnt[(k, 1)]
        out[k] = {
            "share": _r((pts[(k, 0)] + pts[(k, 1)]) / total, 4),
            "share_end": _r(pts[(k, 1)] / total, 4),
            "per_game": _r((pts[(k, 0)] + pts[(k, 1)]) / n / 2, 2),  # 1人あたり
            "completed": done,
            "unfinished": left,
            "unfinished_rate": _r(left / (done + left), 4) if done + left else None,
        }
    out["end_share"] = _r(sum(pts[(k, 1)] for k in KINDS) / total, 4)
    return out


def trajectory(games: list[dict]) -> dict:
    """手数ごとの平均得点（確定点と、いま終わったらの見込み点）と、途中でリードしていた側の勝率。"""
    L = min(len(g["moves"]) for g in games)
    sc = [[0.0, 0.0] for _ in range(L)]
    pj = [[0.0, 0.0] for _ in range(L)]
    for g in games:
        for i in range(L):
            m = g["moves"][i]
            for p in (0, 1):
                sc[i][p] += m["sc"][p]
                pj[i][p] += m["proj"][p]
    n = len(games)
    final = [statistics.fmean(g["scores"][p] for g in games) for p in (0, 1)]
    curve = {
        # 最後の要素は終局後の得点（置けないタイルを捨てた対局は手数が短いので、手数ごとの値とは別に足す）
        "score": [[_r(a / n, 2), _r(b / n, 2)] for a, b in sc]
        + [[_r(final[0], 2), _r(final[1], 2)]],
        "proj": [[_r(a / n, 2), _r(b / n, 2)] for a, b in pj],
    }
    # 途中で見込み点がリードしていた側が勝つ割合（同点・引き分けは除く）
    lead_wins = []
    for frac in CHECKPOINTS:
        res = {"proj": [0, 0], "sc": [0, 0]}
        for g in games:
            fin = g["scores"][0] - g["scores"][1]
            if fin == 0:
                continue
            m = g["moves"][int(len(g["moves"]) * frac) - 1]
            for key in ("proj", "sc"):
                lead = m[key][0] - m[key][1]
                if lead == 0:
                    continue
                res[key][0] += (lead > 0) == (fin > 0)
                res[key][1] += 1
        lead_wins.append(
            {
                "frac": frac,
                "ply": int(L * frac),
                "proj": _r(res["proj"][0] / res["proj"][1], 4),
                "score": _r(res["sc"][0] / res["sc"][1], 4),
            }
        )
    # 半分の時点の見込み点のリード（5点刻み）ごとの、リード側の勝率（引き分けは0.5勝）
    buckets = defaultdict(lambda: [0.0, 0])
    for g in games:
        m = g["moves"][len(g["moves"]) // 2 - 1]
        lead = m["proj"][0] - m["proj"][1]
        fin = g["scores"][0] - g["scores"][1]
        if lead == 0:
            continue
        sign = 1 if lead > 0 else -1
        b = min(abs(lead) // 5, 6)
        buckets[b][0] += 1.0 if fin * sign > 0 else 0.5 if fin == 0 else 0.0
        buckets[b][1] += 1
    by_lead = [
        {"from": b * 5, "to": None if b == 6 else b * 5 + 4, "games": c, "win": _r(w / c, 4)}
        for b, (w, c) in sorted(buckets.items())
    ]
    # 最後の5手までに見込み点で負けていた側が勝った割合（大逆転）
    comeback = 0
    for g in games:
        fin = g["scores"][0] - g["scores"][1]
        m = g["moves"][len(g["moves"]) // 2 - 1]
        lead = m["proj"][0] - m["proj"][1]
        if abs(lead) >= 15 and fin * lead < 0:
            comeback += 1
    big = sum(
        1
        for g in games
        if abs(
            g["moves"][len(g["moves"]) // 2 - 1]["proj"][0]
            - g["moves"][len(g["moves"]) // 2 - 1]["proj"][1]
        )
        >= 15
    )
    lead_changes = []
    for g in games:
        signs = [(m["proj"][0] > m["proj"][1]) - (m["proj"][0] < m["proj"][1]) for m in g["moves"]]
        signs = [s for s in signs if s != 0]
        lead_changes.append(sum(1 for a, b in itertools.pairwise(signs) if a != b))
    return {
        "curve": curve,
        "lead_wins": lead_wins,
        "by_lead_half": by_lead,
        "comeback15": {
            "games": big,
            "comebacks": comeback,
            "rate": _r(comeback / big, 4) if big else None,
        },
        "lead_changes_mean": _r(statistics.fmean(lead_changes), 2),
    }


def meeples(games: list[dict]) -> dict:
    L = min(len(g["moves"]) for g in games)
    sup = [[0.0, 0.0] for _ in range(L)]
    placed = Counter()
    turns = 0
    empty = 0  # 手番でミープルが0個だった
    for g in games:
        for i, m in enumerate(g["moves"]):
            p = m["p"]
            turns += 1
            if m["sup"][p] == 0:
                empty += 1
            if m["m"] is not None:
                placed[m["m"]] += 1
            if i < L:
                sup[i][0] += m["sup"][0]
                sup[i][1] += m["sup"][1]
    n = len(games)
    total = sum(placed.values())
    stuck = [
        sum(len(pl) for pl, k, _p, end, _ in g["awards"] if end and k != "F") / 2 for g in games
    ]  # 終局時に未完成の場所に残っていた（1人あたり、同点の共有は両者に数える）
    farmers = [sum(len(pl) for pl, k, _p, end, _ in g["awards"] if k == "F") / 2 for g in games]
    return {
        "per_game": _r(total / n / 2, 2),  # 1人1局あたり置いた数
        "place_rate": _r(total / turns, 4),
        "kind_share": {k: _r(placed[k] / total, 4) for k in KINDS},
        "empty_rate": _r(empty / turns, 4),
        "supply_curve": [[_r(a / n, 2), _r(b / n, 2)] for a, b in sup],
        "farmers_scored": _r(statistics.fmean(farmers), 2),
        "unfinished_at_end": _r(statistics.fmean(stuck), 2),
    }


def tiles(games: list[dict]) -> list[dict]:
    """タイルの種類ごとの、引いた人にとっての価値（置いた手で動いた見込み点の差、自分−相手）。"""
    val = defaultdict(list)
    for g in games:
        for m in g["moves"]:
            p = m["p"]
            val[m["t"]].append(m["gain"][p] - m["gain"][1 - p])
    out = [
        {
            "tile": t,
            "n": len(v),
            "value": _r(statistics.fmean(v), 2),
            "se": _r(statistics.stdev(v) / math.sqrt(len(v)), 2),
        }
        for t, v in val.items()
    ]
    return sorted(out, key=lambda d: -d["value"])


def complexity(games: list[dict]) -> dict:
    """1手の選択肢の数（配置×ミープル）と、ゲーム木の大きさの目安（log10）。"""
    legal = [m["legal"] for g in games for m in g["moves"]]
    places = [m["places"] for g in games for m in g["moves"]]
    kinds = [m["kinds"] for g in games for m in g["moves"]]
    tree = [sum(math.log10(m["legal"]) for m in g["moves"]) for g in games]
    chance = [sum(math.log10(max(m["kinds"], 1)) for m in g["moves"]) for g in games]
    return {
        "legal_mean": _r(statistics.fmean(legal), 1),
        "legal_median": statistics.median(legal),
        "legal_max": max(legal),
        "places_mean": _r(statistics.fmean(places), 1),
        "kinds_mean": _r(statistics.fmean(kinds), 1),
        "tree_log10": _r(statistics.fmean(tree), 0),
        "tree_with_chance_log10": _r(statistics.fmean(t + c for t, c in zip(tree, chance)), 0),
    }


def deck_luck(games: list[dict]) -> dict:
    """同じ山札を2回指した組で、結果がどれだけそろうか（山札の運の大きさ）。"""
    by = defaultdict(dict)
    for g in games:
        by[g["seed"]][g["play"]] = g["scores"][0] - g["scores"][1]
    pairs = [(d[0], d[1]) for d in by.values() if 0 in d and 1 in d]
    a = [x for x, _ in pairs]
    b = [y for _, y in pairs]
    corr = statistics.correlation(a, b)
    same = sum(1 for x, y in pairs if x * y > 0)
    decided = sum(1 for x, y in pairs if x * y != 0)
    return {
        "pairs": len(pairs),
        "diff_corr": _r(corr, 3),  # 得点差のばらつきのうち、山札で決まる割合の目安（級内相関）
        "same_winner": _r(same / decided, 4),
        "diff_sd": _r(statistics.stdev(a + b), 1),
    }


def ladder(d: Path) -> list[dict]:
    out = []
    for strong, weak, name in LADDER:
        path = d / f"{name}.jsonl"
        if not path.exists():
            continue
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        # run_match.py のログは前半が A 先手、後半が B 先手
        h = len(rows) // 2
        diffs = [r["scores"][0] - r["scores"][1] for r in rows[:h]] + [
            r["scores"][1] - r["scores"][0] for r in rows[h:]
        ]
        n = len(diffs)
        w = sum(1.0 if x > 0 else 0.5 if x == 0 else 0.0 for x in diffs)
        lo, hi = wilson(w, n)
        p = w / n
        elo = None if p in (0.0, 1.0) else _r(-400 * math.log10(1 / p - 1), 0)
        out.append(
            {
                "strong": strong,
                "weak": weak,
                "games": n,
                "score": _r(p, 4),
                "ci": [_r(lo, 4), _r(hi, 4)],
                "upset": _r(sum(x < 0 for x in diffs) / n, 4),
                "mean_diff": _r(statistics.fmean(diffs), 1),
                "elo": elo,
            }
        )
    return out


# 先後の差をなくすルールの実験（名前, ファイル）。基準は selfplay.jsonl（コミなし・71枚）
FAIRNESS = [("komi4", "komi4"), ("tiles70", "tiles70")]


def fairness(d: Path, games: list[dict]) -> dict:
    """ルールを変えて実際に指した結果と、基準の対局の点差に後手の加点を足した試算。"""
    rows = [{"rule": "base", **first_player(games)}]
    for name, fname in FAIRNESS:
        path = d / f"{fname}.jsonl"
        if path.exists():
            gs = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
            rows.append({"rule": name, **first_player(gs)})
    diffs = [g["scores"][0] - g["scores"][1] for g in games]
    n = len(diffs)
    sim = []
    for k in range(0, 8):
        w = sum(x > k for x in diffs)
        t = sum(x == k for x in diffs)
        sim.append({"komi": k, "score": _r((w + 0.5 * t) / n, 4), "draw": _r(t / n, 4)})
    return {"played": rows, "komi_sim": sim}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("dir", help="runs/stats など")
    ap.add_argument("--out", default=str(ROOT / "docs" / "results" / "game_stats.json"))
    args = ap.parse_args()
    d = Path(args.dir)
    games = [
        json.loads(x)
        for x in (d / "selfplay.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    stats = {
        "ai": champion_info(),
        "agent": "standard",
        "first_player": first_player(games),
        "scores": scores(games),
        "sources": sources(games),
        "trajectory": trajectory(games),
        "meeples": meeples(games),
        "tiles": tiles(games),
        "complexity": complexity(games),
        "deck_luck": deck_luck(games),
        "ladder": ladder(d),
        "fairness": fairness(d, games),
    }
    Path(args.out).write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    fp = stats["first_player"]
    print(
        f"{fp['games']}局 先手 {fp['wins']}勝 {fp['losses']}敗 {fp['draws']}分 "
        f"勝率 {fp['score']} {fp['ci']} p={fp['p_value']} 平均差 {fp['mean_diff']}±{fp['se_diff']}"
    )


if __name__ == "__main__":
    main()
