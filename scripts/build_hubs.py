"""入口のページ（トップ docs/index.html・講座の目次 docs/learn/・研究の目次 docs/research/）を作る。

    py scripts/build_hubs.py

サイトは「講座」「研究」「対戦」の3部（2026-11-24 の構造の整理）。この3枚は各部へ案内するだけのページなので、
本文はこのファイルに書き、英語版は対訳表 web/i18n/en/index.json・learn.json・research.json で訳す。
リンクは論理名（"rules.html" など）で書く。置き場所への相対リンクには i18n.write_pair が直す。
"""

from __future__ import annotations

from i18n import to_english_page, write_pair
from site_nav import NAV_CSS, nav_html, support_html

CSS = """
:root {
  --bg: #f1f3ee; --paper: #ffffff; --ink: #1d2620; --muted: #5c6a60; --line: #d5dccf; --field: #2f6b3a;
  --font-display: "Dela Gothic One", "Zen Kaku Gothic New", "Hiragino Sans", sans-serif;
  --font-body: "Zen Kaku Gothic New", "Hiragino Sans", "Yu Gothic", "Noto Sans JP", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg: #141a16; --paper: #1c241f; --ink: #e6ece6; --muted: #9aa89d; --line: #2e3a32; --field: #7cc48a; color-scheme: dark; }
}
:root[data-theme="dark"] { --bg: #141a16; --paper: #1c241f; --ink: #e6ece6; --muted: #9aa89d; --line: #2e3a32; --field: #7cc48a; color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); font-size: 16px; line-height: 1.8; padding-inline: 16px; padding-block: 0 64px; }
.wrap { max-width: 760px; margin: 0 auto; }
header.hero { padding-block: 40px 20px; display: grid; gap: 12px; }
.eyebrow { font-size: 13px; letter-spacing: .12em; color: var(--muted); font-weight: 700; margin: 0; }
h1 { font-family: var(--font-display); font-weight: 400; font-size: clamp(32px, 7vw, 48px); line-height: 1.2; margin: 0; }
h1 span { color: var(--field); }
h2 { font-family: var(--font-display); font-weight: 400; font-size: 21px; margin: 32px 0 12px; }
.lede { margin: 0; max-width: 34em; }
.cta { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; }
.cta a { display: inline-flex; align-items: center; justify-content: center; min-height: 48px; padding: 0 22px; border-radius: 999px; font-weight: 700; text-decoration: none; border: 1px solid var(--field); }
.cta a.main { background: var(--field); color: var(--paper); }
.cta a.sub { background: var(--paper); color: var(--ink); border-color: var(--line); }
.cta a:hover, .cta a:focus-visible { outline: 2px solid var(--field); outline-offset: 2px; }
ul.parts { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
ul.parts a { display: grid; gap: 6px; align-content: start; height: 100%; padding: 18px; background: var(--paper); border: 1px solid var(--line); border-top: 4px solid var(--field); border-radius: 8px; color: var(--ink); text-decoration: none; }
ul.parts a:hover, ul.parts a:focus-visible { border-color: var(--field); outline: none; }
ul.parts b { font-size: 19px; }
ul.parts small { color: var(--muted); font-size: 14px; line-height: 1.7; }
ul.parts .go { color: var(--field); font-weight: 700; font-size: 14px; }
ol.cards, ul.cards { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; counter-reset: step; }
ol.cards li { counter-increment: step; }
ol.cards a, ul.cards a { display: grid; grid-template-columns: 44px 1fr; gap: 4px 14px; padding: 16px 18px; background: var(--paper); border: 1px solid var(--line); border-radius: 8px; color: var(--ink); text-decoration: none; }
ul.cards a { grid-template-columns: 1fr; }
ol.cards a:hover, ol.cards a:focus-visible, ul.cards a:hover, ul.cards a:focus-visible { border-color: var(--field); outline: none; }
ol.cards a::before { content: counter(step); grid-row: span 2; width: 36px; height: 36px; border-radius: 50%; background: var(--field); color: var(--paper); display: grid; place-items: center; font-weight: 700; }
ol.cards li.finish a::before { content: "★"; }
ol.cards b, ul.cards b { font-size: 18px; }
ol.cards small, ul.cards small { color: var(--muted); font-size: 14px; }
.more { margin-top: 24px; font-size: 14.5px; color: var(--muted); }
.more a { color: var(--field); }
"""

HEAD = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>__CSS__</style>
</head>
<body>
<div class="wrap">
__NAV__
"""
FOOT = """__SUPPORT__
</div>
</body>
</html>
"""

INDEX = """<header class="hero">
  <h1>はじめての<span>カルカソンヌ</span></h1>
  <p class="lede">タイルをつなげて地図を作るボードゲーム「カルカソンヌ」を、ルールを知らないところから一歩ずつ。このプロジェクトで作った強いAIと対戦でき、その対局から分かったコツと練習問題もあります。</p>
  <div class="cta"><a class="main" href="play.html">AIと対戦する</a><a class="sub" href="learn/index.html">講座を1章から読む</a></div>
</header>
<h2>3つの部</h2>
<ul class="parts">
  <li><a href="learn/index.html"><b>講座</b><small>ルール入門・戦略ガイド・強いAIのコツ・次の一手クイズの4章。ルールを知らない人から、上達したい人まで。</small><span class="go">講座の目次へ</span></a></li>
  <li><a href="research/index.html"><b>研究</b><small>強いAIどうし・人とAIの対局を集計して分かったこと。先手の有利、点の出どころ、人が外しやすい局面。</small><span class="go">研究の目次へ</span></a></li>
  <li><a href="play.html"><b>AIと対戦</b><small>いちばん強いAIと1対1で遊べます。インストール不要。初心者モードでは自分の手が何点損だったかも分かります。</small><span class="go">対戦をはじめる</span></a></li>
</ul>
<p class="more">おすすめの進め方: 講座の1章「ルール入門」で遊び方を覚えたら、2章「戦略ガイド」の「まず覚える5つ」を読み、4章のクイズの入門編を解いてから、AIと対戦（初心者モード）で損した手を振り返ってください。</p>
<p class="more">AIはお使いのブラウザの中で考えます（最強設定は1手に数秒かかることがあります）。ルールは基本セット（72枚）の現行ルールです。「カルカソンヌ」は Hans im Glück の商標で、このサイトは非公式のファンサイトです。</p>
"""

LEARN = """<header class="hero">
  <p class="eyebrow">COURSE</p>
  <h1>カルカソンヌ<span>講座</span></h1>
  <p class="lede">ルールを知らないところから、強いAIのような打ち方まで、4つの章で順に進みます。各章の終わりに次の章へのリンクがあります。</p>
</header>
<ol class="cards">
  <li><a href="rules.html"><b>1章 ルール入門</b><small>手番の流れ、タイルとミープルの置き方、点の数え方を図で説明します。</small></a></li>
  <li><a href="strategy.html"><b>2章 戦略ガイド</b><small>ルールを覚えたら次はここ。点差で考える土台、タイルの内訳、埋まりにくい穴、序盤・中盤・終盤の方針、よくある失敗、用語集。</small></a></li>
  <li><a href="ai_tips.html"><b>3章 強いAIに学ぶコツ</b><small>強いAI同士の対局を集計して分かった、初心者がまねしやすい打ち方。</small></a></li>
  <li><a href="quiz.html"><b>4章 次の一手クイズ</b><small>入門編から実戦編まで。AIならどこに置くかを当てて、解説を読みます。</small></a></li>
  <li class="finish"><a href="play.html"><b>仕上げ AIと対戦</b><small>初心者モードで対戦すると、自分の手のあとにAIならどこに置いたかと何点損したかが出ます。</small></a></li>
</ol>
<p class="more">急ぐ人は、1章のあと2章の「まず覚える5つ」だけ読んで、4章の入門編に進んでもかまいません。慣れてきたら3章と4章の実戦編へ。</p>
"""

RESEARCH = """<header class="hero">
  <p class="eyebrow">RESEARCH</p>
  <h1>カルカソンヌを<span>研究する</span></h1>
  <p class="lede">このプロジェクトで作った強いAIどうしの対局と、対戦ページで人がAIと指した対局を集計して分かったことをまとめています。</p>
</header>
<ul class="cards">
  <li><a href="stats.html"><b>データで見る</b><small>先手はどれくらい有利？ 点はどこから来る？ 強いAI同士の対局から測ったデータと、チェス・囲碁など他のゲームとの比較。</small></a></li>
  <li><a href="games.html"><b>みんなの対局</b><small>ほかの人がAIと指した対局を、盤面で一手ずつ再生して見られます。</small></a></li>
  <li><a href="games.html#findings"><b>研究ノート</b><small>人との対局から分かった、人が外しやすい局面と悪手の傾向。</small></a></li>
</ul>
<p class="more">研究の手順と、効かなかった試みも含めた記録は <a href="https://github.com/satou-aaaaa/carcassonne-research">GitHub のリポジトリ</a> にあります。</p>
"""

PAGES = {
    "index.html": (
        "index",
        "カルカソンヌ入門",
        "ボードゲーム「カルカソンヌ」の講座（ルール入門・戦略ガイド・強いAIのコツ・次の一手クイズ）、対局の研究、強いAIとの対戦。",
        INDEX,
    ),
    "learn/index.html": (
        "learn",
        "カルカソンヌ講座 | カルカソンヌ入門",
        "ボードゲーム「カルカソンヌ」を4章で学ぶ講座。ルール入門、戦略ガイド、強いAIに学ぶコツ、次の一手クイズ。",
        LEARN,
    ),
    "research/index.html": (
        "research",
        "カルカソンヌの研究 | カルカソンヌ入門",
        "強いAIどうし・人とAIのカルカソンヌの対局を集計して分かったこと。データ、みんなの対局、研究ノート。",
        RESEARCH,
    ),
}


def build(page: str) -> tuple[str, str]:
    name, title, desc, body = PAGES[page]
    ja = (
        HEAD.replace("__TITLE__", title)
        .replace("__DESC__", desc)
        .replace("__CSS__", CSS + NAV_CSS)
        .replace("__NAV__", nav_html(page))
        + body
        + FOOT.replace("__SUPPORT__", support_html())
    )
    en = to_english_page(ja, page, name, nav_html(page), nav_html(page, "en"))
    return ja, en


def main() -> None:
    for page in PAGES:
        write_pair(page, *build(page))
        print(f"docs/{page} と docs/en/{page} を書き出しました")


if __name__ == "__main__":
    main()
