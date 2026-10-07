"""人間 vs AI の対局記録（runs/human/games.jsonl）を集計する。

    py scripts/summarize_human.py                 # 全員・全強さを (名前, 強さ) ごとに集計
    py scripts/summarize_human.py --name 山田 --level strong

出力は人間側の視点。同じシードを先後入れ替えて2局指した「ペア」があれば、ペア単位の
得点差（2局の合計）も出す。山札の運と先手有利が打ち消されるため、こちらを主指標にする。
初心者モード（AIのヒントあり）の対局は強さの測定にならないので、既定では除く（--with-coach で含める）。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.arena import wilson


def mean_se(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / max(n - 1, 1)
    return m, math.sqrt(var / n)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--log", default=str(ROOT / "runs" / "human" / "games.jsonl"))
    ap.add_argument("--name")
    ap.add_argument("--level")
    ap.add_argument("--with-coach", action="store_true", help="初心者モードの対局も含める")
    args = ap.parse_args()
    path = Path(args.log)
    if not path.exists():
        raise SystemExit(f"記録がありません: {path}")
    recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    recs = [
        r
        for r in recs
        if (args.name is None or r["name"] == args.name)
        and (args.level is None or r["level"] == args.level)
        and (args.with_coach or not r.get("coach"))
    ]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in recs:
        groups[(r["name"] or "(無名)", r["level"])].append(r)
    for (name, level), rs in sorted(groups.items()):
        diffs = [r["diff_human"] for r in rs]
        wins = sum(1.0 if d > 0 else 0.5 if d == 0 else 0.0 for d in diffs)
        lo, hi = wilson(wins, len(rs))
        m, se = mean_se(diffs)
        first = [r["diff_human"] for r in rs if r["human_seat"] == 0]
        second = [r["diff_human"] for r in rs if r["human_seat"] == 1]
        print(f"■ {name} vs AI[{level}]  {len(rs)}局")
        print(
            f"  人間の勝率 {wins / len(rs):.3f} [{lo:.3f}, {hi:.3f}]  平均得点差 {m:+.2f}±{se:.2f}"
        )
        print(
            f"  先手のとき {len(first)}局 平均 {sum(first) / max(len(first), 1):+.1f} / "
            f"後手のとき {len(second)}局 平均 {sum(second) / max(len(second), 1):+.1f}"
        )
        by_seed: dict[int, dict[int, int]] = defaultdict(dict)
        for r in rs:
            by_seed[r["seed"]][r["human_seat"]] = r["diff_human"]
        pairs = [d[0] + d[1] for d in by_seed.values() if 0 in d and 1 in d]
        if pairs:
            pm, pse = mean_se(pairs)
            pw = sum(1.0 if p > 0 else 0.5 if p == 0 else 0.0 for p in pairs)
            print(
                f"  ペア（同一山札・先後入替）{len(pairs)}組: 人間が上回った割合 {pw / len(pairs):.2f}  "
                f"ペア合計得点差 平均 {pm:+.2f}±{pse:.2f}（0より大きければ人間が上）"
            )
        print(
            f"  人間の平均得点 {sum(r['human_score'] for r in rs) / len(rs):.1f} / "
            f"AIの平均得点 {sum(r['ai_score'] for r in rs) / len(rs):.1f}"
        )


if __name__ == "__main__":
    main()
