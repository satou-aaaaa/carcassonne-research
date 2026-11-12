"""「みんなの対局」ページ（docs/games.html）を組み立てる。

    py scripts/build_games_page.py

対局の一覧は、ページを開いたときにブラウザが docs/human_games.json（scripts/human_games.py report が書く。
名前などを落とした検査済みの棋譜）を読んで並べるので、棋譜が増えてもこのページを作り直す必要はない。
押すと対戦ページ（play.html#replay=番号）で一手ずつ再生する。英語版は対訳表 web/i18n/en/games.json。
"""

from __future__ import annotations

from pathlib import Path

from i18n import to_english_page, write_pair
from site_nav import NAV_CSS, nav_html, support_html

ROOT = Path(__file__).resolve().parents[1]
PAGE = "games.html"


def main() -> None:
    tpl = (ROOT / "web" / "games_template.html").read_text(encoding="utf-8")
    ja = (
        tpl.replace("__NAV_CSS__", NAV_CSS)
        .replace("__NAV__", nav_html(PAGE))
        .replace("__SUPPORT__", support_html())
    )
    en = to_english_page(ja, PAGE, "games", nav_html(PAGE), nav_html(PAGE, "en"))
    write_pair(PAGE, ja, en)
    print("docs/games.html と docs/en/games.html を書き出しました")


if __name__ == "__main__":
    main()
