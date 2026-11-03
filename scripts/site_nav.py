"""公開ページ（docs/）の共通ナビゲーション。各ページの組み立てスクリプトが差し込む。

ページは docs/ 直下に並べる（GitHub Pages で docs/ を公開する想定）。
CSS は各ページの色トークン（--paper, --ink, --muted, --line, --field）を使う。
"""

from __future__ import annotations

PAGES = [
    ("index.html", "トップ"),
    ("rules.html", "ルール入門"),
    ("strategy.html", "戦略ガイド"),
    ("ai_tips.html", "強いAIのコツ"),
    ("quiz.html", "次の一手クイズ"),
    ("play.html", "AIと対戦"),
]

NAV_CSS = """
nav.site { display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 14px; }
nav.site .home { font-weight: 700; margin-right: 8px; color: var(--ink); text-decoration: none; }
nav.site a.p { color: var(--muted); text-decoration: none; padding: 3px 10px; border-radius: 999px; }
nav.site a.p:hover, nav.site a.p:focus-visible { color: var(--ink); background: var(--paper); outline: none; }
nav.site a.p[aria-current="page"] { color: var(--paper); background: var(--field); }
@media (pointer: coarse) { nav.site a { min-height: 44px; display: inline-flex; align-items: center; } }
/* 共通: 見出しを語の切れ目で折り返す・開閉の見出しを押しやすく */
h1, h2, h3 { word-break: auto-phrase; }
summary { padding-block: 6px; }
/* 共通: ページ下の支援リンク（Ko-fi）。目立ちすぎないよう枠線だけのボタンにする */
.support { margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 13.5px; color: var(--muted); display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.support a.kofi { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 16px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--ink); text-decoration: none; font-weight: 600; }
.support a.kofi:hover, .support a.kofi:focus-visible { border-color: var(--field); }
"""

# 作者の Ko-fi ページ（2026-11-03 satou さん設定）。外部スクリプト・外部画像は読み込まない
KOFI_URL = "https://ko-fi.com/satouaaaaa"


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


def support_html() -> str:
    """ページ下に置く支援リンク。全ページで同じものを使う（docs/index.html・web/play.html は手で合わせる）。"""
    return (
        '<div class="support">このサイトが役に立ったら、作者を応援できます。'
        f'<a class="kofi" href="{KOFI_URL}" target="_blank" rel="noopener">'
        '<span aria-hidden="true">☕</span>Ko-fiで応援する</a></div>'
    )
