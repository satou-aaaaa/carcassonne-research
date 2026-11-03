"""練習問題のデータ data/puzzles.json から、1ファイルで動くクイズページ docs/quiz.html を作る。

    py scripts/build_puzzles.py
    py scripts/build_puzzles.py --src runs/puzzles/cands.jsonl --out runs/puzzles/preview.html  # 候補の下見

data/puzzles.json は scripts/make_puzzles.py の候補から採用した局面に、題名・問題文・解説を
書き足したもの。英語ページ（docs/en/quiz.html）の文は各問題の "en"（title・prompt・explain・lesson・notes）。
"level": "入門" の問題は先頭にまとめて出す（無ければ実戦編）。選択肢の並びは問題ごとに固定の乱数で入れ替える（正解がいつもAにならないように）。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from i18n import to_english_page, translate, write_pair
from site_nav import NAV_CSS, nav_html, support_html

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


TEXT_KEYS = ("title", "prompt", "explain", "lesson", "notes")
KIND_EN = {"C": "city", "R": "road", "F": "field", "M": "monastery"}


def to_page(p: dict, lang: str = "ja") -> dict:
    if lang == "en":
        en = p.get("en") or {}
        missing = [k for k in TEXT_KEYS if not en.get(k)]
        if missing:
            raise SystemExit(
                f'{p["id"]}: 英語の文（"en": {missing}）がありません。data/puzzles.json に足してください'
            )
        p = {**p, **en}
    out = {k: p[k] for k in KEEP}
    out["level"] = "intro" if p.get("level") == "入門" else "real"
    opts = [json.loads(json.dumps(o)) for o in p["options"]]  # 先頭が最善手
    for o, note in zip(opts, p.get("notes", [])):
        o["note"] = note
        m = (o.get("facts") or {}).get("meeple")
        if lang == "en" and m:
            m["kind_ja"] = KIND_EN[m["kind"]]
    order = list(range(len(opts)))
    random.Random(p["id"]).shuffle(order)
    out["options"] = [
        {k: opts[i][k] for k in ("move", "diff", "facts", "note") if k in opts[i]} for i in order
    ]
    out["best"] = order.index(0)
    return out


def ai_note(puzzles: list[dict], lang: str = "ja") -> str:
    """どのAIで答えを確かめたかの一文（scripts/recheck_puzzles.py が書く checked_by から）。"""
    names = {(p.get("checked_by") or {}).get("name") for p in puzzles}
    if len(names) != 1 or None in names:
        return ""
    by = next(p["checked_by"] for p in puzzles)
    if lang == "en":
        when = f", adopted {by['date']}" if by.get("date") else ""
        return (
            f"The answers and point gaps were rechecked with the same latest AI as the play page ({by['name']}{when}). "
            "We recheck every time the AI gets stronger, and problems whose answer changed are removed until reviewed."
        )
    when = f"、{by['date']} 採用" if by.get("date") else ""
    return (
        f"答えと点差は、対戦ページと同じ最新のAI（{by['name']}{when}）で確かめ直したものです。"
        "AIが強くなるたびに確かめ直し、答えが変わった問題は見直すまで外しています。"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "data" / "puzzles.json"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "quiz.html"))
    ap.add_argument("--fragment", action="store_true", help="<html>等で包まない（Artifact公開用）")
    args = ap.parse_args()
    raw = [
        p for p in load(Path(args.src)) if not p.get("disputed")
    ]  # 最新AIと答えが食い違う問題は出さない
    tpl = (ROOT / "web" / "quiz_template.html").read_text(encoding="utf-8")

    def page(lang: str) -> str:
        puzzles = [to_page(p, lang) for p in raw]
        puzzles.sort(key=lambda p: p["level"] != "intro")  # 安定ソート: 入門編を先に
        data = {"tiles": tile_library(), "puzzles": puzzles}
        blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        body = tpl if lang == "ja" else translate(tpl, "quiz")
        body = body.replace("__QUIZ_DATA__", blob).replace("__AI_NOTE__", ai_note(raw, lang))
        body = body.replace("__TILE_ART__", (ROOT / "web" / "tile_art.js").read_text(encoding="utf-8"))
        nav = "" if args.fragment else nav_html("quiz.html", lang)
        body = body.replace("__SITE_NAV_CSS__", NAV_CSS).replace("__SITE_NAV__", nav)
        body = body.replace("__SITE_SUPPORT__", "" if args.fragment else support_html(lang))
        if not args.fragment:
            body = (
                f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + body
            )
            head, rest = body.split("</style>", 1)
            body = head + "</style>\n</head>\n<body>" + rest + "</body>\n</html>\n"
        return body

    body = page("ja")
    if args.fragment or Path(args.out) != ROOT / "docs" / "quiz.html":
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(body, encoding="utf-8")
    else:
        write_pair("quiz.html", body, to_english_page(page("en"), "quiz.html", "none"))
    print(f"{len(raw)} 問を {args.out} に書き出しました")


if __name__ == "__main__":
    main()
