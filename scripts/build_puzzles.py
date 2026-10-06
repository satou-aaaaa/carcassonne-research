"""練習問題のデータ data/puzzles.json から、1ファイルで動くクイズページ web/quiz.html を作る。

    py scripts/build_puzzles.py
    py scripts/build_puzzles.py --src runs/puzzles/cands.jsonl --out runs/puzzles/preview.html  # 候補の下見

data/puzzles.json は scripts/make_puzzles.py の候補から採用した局面に、題名・問題文・解説を
書き足したもの。選択肢の並びは問題ごとに固定の乱数で入れ替える（正解がいつもAにならないように）。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.webplay import tile_library

KEEP = (
    "id", "turn", "deck_left", "player", "scores", "supply", "current", "remaining", "board",
    "meeples", "title", "prompt", "explain", "lesson",
)  # fmt: skip


def load(src: Path) -> list[dict]:
    if src.suffix == ".jsonl":
        recs = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line]
        for r in recs:  # 下見用の仮の文面
            r.setdefault("title", f"{r['id']}（差 {r['gap']}点・訪問 {r['share']:.0%}）")
            r.setdefault("prompt", "どこに置く？")
            r.setdefault("explain", [])
            r.setdefault("lesson", "")
        return recs
    return json.loads(src.read_text(encoding="utf-8"))


def to_page(p: dict) -> dict:
    out = {k: p[k] for k in KEEP}
    opts = [dict(o) for o in p["options"]]  # 先頭が最善手
    for o, note in zip(opts, p.get("notes", [])):
        o["note"] = note
    order = list(range(len(opts)))
    random.Random(p["id"]).shuffle(order)
    out["options"] = [
        {k: opts[i][k] for k in ("move", "diff", "facts", "note") if k in opts[i]} for i in order
    ]
    out["best"] = order.index(0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "data" / "puzzles.json"))
    ap.add_argument("--out", default=str(ROOT / "web" / "quiz.html"))
    ap.add_argument("--fragment", action="store_true", help="<html>等で包まない（Artifact公開用）")
    args = ap.parse_args()
    data = {"tiles": tile_library(), "puzzles": [to_page(p) for p in load(Path(args.src))]}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body = (ROOT / "web" / "quiz_template.html").read_text(encoding="utf-8")
    body = body.replace("__QUIZ_DATA__", blob)
    if not args.fragment:
        body = (
            '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + body
        )
        head, rest = body.split("</style>", 1)
        body = head + "</style>\n</head>\n<body>" + rest + "</body>\n</html>\n"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(body, encoding="utf-8")
    print(f"{len(data['puzzles'])} 問を {args.out} に書き出しました")


if __name__ == "__main__":
    main()
