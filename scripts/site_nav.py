"""公開ページ（docs/）の共通ナビゲーション。各ページの組み立てスクリプトが差し込む。

ページは docs/ 直下に並べる（GitHub Pages で docs/ を公開する想定）。
CSS は各ページの色トークン（--paper, --ink, --muted, --line, --field）を使う。
"""

from __future__ import annotations

PAGES = [
    ("index.html", "トップ"),
    ("rules.html", "ルール入門"),
    ("ai_tips.html", "強いAIのコツ"),
    ("quiz.html", "次の一手クイズ"),
]

NAV_CSS = """
nav.site { display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 14px; }
nav.site .home { font-weight: 700; margin-right: 8px; color: var(--ink); text-decoration: none; }
nav.site a.p { color: var(--muted); text-decoration: none; padding: 3px 10px; border-radius: 999px; }
nav.site a.p:hover, nav.site a.p:focus-visible { color: var(--ink); background: var(--paper); outline: none; }
nav.site a.p[aria-current="page"] { color: var(--paper); background: var(--field); }
"""


def nav_html(current: str) -> str:
    """current はそのページのファイル名（例 "rules.html"）。"""
    links = []
    for href, label in PAGES[1:]:
        cur = ' aria-current="page"' if href == current else ""
        links.append(f'<a class="p" href="{href}"{cur}>{label}</a>')
    return (
        '<nav class="site" aria-label="サイト内のページ">'
        '<a class="home" href="index.html">カルカソンヌ入門</a>' + "".join(links) + "</nav>"
    )
