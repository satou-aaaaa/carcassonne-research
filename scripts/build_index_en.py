"""手書きのトップページ docs/index.html から、英語版 docs/en/index.html を作る。

    py scripts/build_index_en.py

文は web/i18n/en/index.json で訳す。docs/index.html のナビと <head> の言語切り替えは
scripts/site_nav.py・scripts/i18n.py の出力と同じにしておく（違えば止まる）。
"""

from __future__ import annotations

from pathlib import Path

from i18n import lang_head, to_english_page
from site_nav import nav_html

ROOT = Path(__file__).resolve().parents[1]
PAGE = "index.html"


def main() -> None:
    html = (ROOT / "docs" / PAGE).read_text(encoding="utf-8")
    head_ja, head_en = lang_head(PAGE, "ja"), lang_head(PAGE, "en")
    if head_ja not in html:
        raise SystemExit(
            "docs/index.html の </head> の直前に、次の言語切り替えを入れてください:\n" + head_ja
        )
    en = to_english_page(
        html.replace(head_ja, ""), PAGE, "index", nav_html(PAGE), nav_html(PAGE, "en")
    )
    en = en.replace("</head>", head_en + "</head>", 1)
    out = ROOT / "docs" / "en" / PAGE
    out.parent.mkdir(exist_ok=True)
    out.write_text(en, encoding="utf-8")
    print(f"{out} を書き出しました")


if __name__ == "__main__":
    main()
