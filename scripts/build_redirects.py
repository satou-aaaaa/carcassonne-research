"""古い置き場所（docs/rules.html など）に、新しい置き場所へ移る転送ページを書く。

    py scripts/build_redirects.py

2026-11-24 にサイトを「講座」learn/・「研究」research/ に分けた。X の投稿やブックマークなど外からのリンクを
切らないよう、古い URL は転送ページとして残す（# 以降と ? 以降もそのまま引き継ぐ）。
GitHub Pages ではサーバー側の転送が使えないので、Google が勧める meta refresh と JavaScript の転送を両方入れ、
検索結果には新しい URL が出るよう canonical を付ける。
  https://developers.google.com/search/docs/crawling-indexing/301-redirects
"""

from __future__ import annotations

import html as _html
import json
from pathlib import Path

from i18n import MOVED, out_path, page_url

ROOT = Path(__file__).resolve().parents[1]

TEMPLATE = """<!doctype html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__MSG__</title>
<meta name="robots" content="noindex">
<link rel="canonical" href="__URL__">
<meta http-equiv="refresh" content="0; url=__REL__">
<script>location.replace(__RELJS__+location.search+location.hash)</script>
<style>body{font-family:sans-serif;margin:40px 16px;line-height:1.8}</style>
</head>
<body>
<p><a href="__REL__">__MSG__</a></p>
</body>
</html>
"""


def stub(page: str, lang: str) -> str:
    rel = out_path(page)
    msg = "新しいページへ移動しました" if lang == "ja" else "This page has moved"
    return (
        TEMPLATE.replace("__LANG__", lang)
        .replace("__MSG__", msg)
        .replace("__URL__", page_url(page, lang))
        .replace("__RELJS__", json.dumps(rel))
        .replace("__REL__", _html.escape(rel))
    )


def main() -> None:
    for page in MOVED:
        if "/" in page:  # 新しく作ったページ（learn/index.html など）は古い場所がない
            continue
        for lang, d in (("ja", ROOT / "docs"), ("en", ROOT / "docs" / "en")):
            (d / page).write_text(stub(page, lang), encoding="utf-8")
    print("古い置き場所の転送ページを書き出しました")


if __name__ == "__main__":
    main()
