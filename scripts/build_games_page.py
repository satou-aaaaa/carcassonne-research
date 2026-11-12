"""「みんなの対局」ページ（docs/games.html）を組み立てる。

    py scripts/build_games_page.py

対局の一覧は、ページを開いたときにブラウザが docs/human_games.json（scripts/human_games.py report が書く。
名前などを落とした検査済みの棋譜）を読んで並べるので、棋譜が増えてもこのページを作り直す必要はない。
押すと対戦ページ（play.html#replay=番号）で一手ずつ再生する。英語版は対訳表 web/i18n/en/games.json。
"""

from __future__ import annotations

import json
from pathlib import Path

from i18n import to_english_page, write_pair
from site_nav import NAV_CSS, nav_html, support_html

ROOT = Path(__file__).resolve().parents[1]
PAGE = "games.html"
FORM = ROOT / "data" / "human_games_form.json"  # 棋譜を送るフォーム。消してほしいという依頼も同じフォームで受ける


def form_js() -> str:
    f = json.loads(FORM.read_text(encoding="utf-8"))
    if not f.get("form") or not f.get("entry"):
        return "null"
    return json.dumps({"url": f["form"], "entry": f["entry"]})


def main() -> None:
    tpl = (ROOT / "web" / "games_template.html").read_text(encoding="utf-8")
    ja = (
        tpl.replace("__NAV_CSS__", NAV_CSS)
        .replace("__NAV__", nav_html(PAGE))
        .replace("__SUPPORT__", support_html())
        .replace("__FORM__", form_js())
    )
    en = to_english_page(ja, PAGE, "games", nav_html(PAGE), nav_html(PAGE, "en"))
    write_pair(PAGE, ja, en)
    print("docs/games.html と docs/en/games.html を書き出しました")


if __name__ == "__main__":
    main()
