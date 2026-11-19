"""人の棋譜から「人が外しやすい局面」の型を数える（BACKLOG R-005）。

    py scripts/human_weak_spots.py        # docs/results/human_weak_spots.json を作り直して表示する

人の手の採点は `scripts/human_games.py report` が作る採点キャッシュ
（docs/results/human_findings_cache.json、最新チャンピオンのコーチ）をそのまま使う。
ここでは採点し直さず、型（ミープルを置かなかった・置きすぎた・別の特徴・置き場所）と、
終盤（各自の最後の6手番）と、そのとき手元に残っていたミープルの数で分ける。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne import human_games as hg
from carcassonne.human_findings import BAD
from carcassonne.state import Move, State
from carcassonne.tiles import load_tileset

GAMES = ROOT / "data" / "human_games.jsonl"
CACHE = ROOT / "docs" / "results" / "human_findings_cache.json"
OUT = ROOT / "docs" / "results" / "human_weak_spots.json"
LAST = 12  # 盤面全体の最後の12手（各自の最後の6手番）


def analyze(games: list[dict], cache: dict) -> dict:
    ts = load_tileset()
    bad = []
    left = {"human": [], "ai": []}  # 終局の直前（最後の1手の前）に手元に残っていたミープル
    for r in games:
        c = cache.get(hg.key(r))
        if c is None:
            continue
        scored = {m["ply"]: m for m in c["moves"] if m["loss"] is not None and m["loss"] >= BAD}
        st = State(r["deck"], ts)
        hs, n = r["human_seat"], len(r["moves"])
        for ply, (x, y, v, p) in enumerate(r["moves"]):
            if ply == n - 1:
                left["human"].append(st.supply[hs])
                left["ai"].append(st.supply[1 - hs])
            if ply in scored:
                m = scored[ply]
                bad.append(
                    {
                        "last": ply >= n - LAST,
                        "cat": m["cat"],
                        "best": m["best"],
                        "supply": st.supply[hs],
                        "loss": m["loss"],
                    }
                )
            st.apply(Move(x, y, v, None if p < 0 else p))

    def loss(rows):
        return round(sum(b["loss"] for b in rows), 1)

    n_games = len(left["human"])
    last = [b for b in bad if b["last"]]
    last_nm = [b for b in last if b["cat"] == "no_meeple"]
    return {
        "games": n_games,
        "bad_moves": len(bad),
        "bad_loss": loss(bad),
        "by_type": {
            f"{b_cat}:{best or '-'}": n
            for (b_cat, best), n in Counter((b["cat"], b["best"]) for b in bad).most_common()
        },
        "last6": {"bad": len(last), "loss": loss(last)},
        "last6_no_meeple": {
            "bad": len(last_nm),
            "loss": loss(last_nm),
            "loss_per_game": round(loss(last_nm) / n_games, 1) if n_games else None,
            "supply": dict(sorted(Counter(b["supply"] for b in last_nm).items())),
            "best": dict(Counter(b["best"] for b in last_nm).most_common()),
        },
        "no_meeple_supply": dict(
            sorted(Counter(b["supply"] for b in bad if b["cat"] == "no_meeple").items())
        ),
        "unused_at_end": {
            k: {"mean": round(sum(v) / len(v), 2), "games_with_any": sum(x > 0 for x in v)}
            for k, v in left.items()
            if v
        },
    }


def main() -> None:
    games = hg.load(GAMES)
    cache = dict(
        json.loads(line) for line in CACHE.read_text(encoding="utf-8").splitlines() if line
    )
    res = analyze(games, cache)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
