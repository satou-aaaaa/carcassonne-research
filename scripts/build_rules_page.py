"""ルールを知らない人向けの入門ページ docs/rules.html を作る。

    py scripts/build_rules_page.py

盤面図はルールエンジン（src/carcassonne/state.py）で実際に手を進めた局面を描いたもの。
本文に書く点数はエンジンの得点計算で確かめ、食い違えば止まる（ルールと解説がずれないように）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from board_svg import board_svg
from site_nav import NAV_CSS, nav_html

from carcassonne.state import Move, State

GOLD = "#f5b400"


def play(deck: list[int], moves: list[tuple]) -> tuple[State, list[dict]]:
    """deck の順に引き、moves (x, y, 向き, 断片) を指した局面と、盤上のミープル一覧。"""
    st = State(deck + [0] * 4)  # 末尾は終局しないための詰め物
    meeples: list[dict] = []
    for x, y, vi, piece in moves:
        player = st.player
        st.apply(Move(x, y, vi, piece))
        if piece is not None:
            meeples.append({"x": x, "y": y, "piece": piece, "player": player})
        meeples = [
            m
            for m in meeples
            if st.meeples[st._find(st.tile_nodes[(m["x"], m["y"])][m["piece"]])][m["player"]] > 0
        ]
    return st, meeples


def check(actual, expected, what: str) -> None:
    if actual != expected:
        raise SystemExit(
            f"{what}: エンジンは {actual}、本文は {expected}。本文か局面を直してください"
        )


def figures() -> dict[str, str]:
    figs = {}

    # 1. 置き方: 開始タイルの右に、道がつながるようにまっすぐな道を置く
    st, mp = play([22], [])
    figs["place"] = board_svg(
        st, mp, (0, 0), radius=1, ghost=[(1, 0, 0, GOLD)], highlight=[(1, 0, GOLD)]
    )

    # 2. 都市: 赤が盾つき都市に騎士を置き、次の手番で1枚足して閉じる（3枚＋盾1つ＝8点）
    city_deck = [10, 22, 14]
    city_moves = [(0, 1, 1, 0), (-1, 0, 0, 1)]
    st, mp = play(city_deck, city_moves)
    figs["city"] = board_svg(
        st, mp, (0, 1), radius=1, ghost=[(1, 1, 3, GOLD)], highlight=[(1, 1, GOLD)]
    )
    done, _ = play(city_deck, city_moves + [(1, 1, 3, None)])
    check(done.scores[0], 8, "都市の完成点")
    check(done.supply[0], 7, "都市のミープルが戻る")

    # 3. 道: 赤が十字路から伸びる道に乗せ、反対側も十字路で閉じる（3枚＝3点）
    road_deck = [23, 22, 23]
    road_moves = [(-1, 0, 0, 0), (0, -1, 0, None)]
    st, mp = play(road_deck, road_moves)
    figs["road"] = board_svg(
        st, mp, (0, 0), radius=1, ghost=[(1, 0, 0, GOLD)], highlight=[(1, 0, GOLD)]
    )
    done, _ = play(road_deck, road_moves + [(1, 0, 0, None)])
    check(done.scores[0], 3, "道の完成点")

    # 4. 修道院: 赤が修道院に置き、周りが5マス埋まった局面（今終わると1＋5＝6点）
    mon_deck = [1, 22, 0, 0, 9]
    mon_moves = [
        (0, -1, 0, 1), (1, 0, 0, None), (1, -1, 3, None), (-1, 0, 2, None), (-1, -1, 2, None)
    ]  # fmt: skip
    st, mp = play(mon_deck, mon_moves)
    figs["monastery"] = board_svg(st, mp, (0, -1), radius=1, highlight=[(0, -1, GOLD)])
    check(st.projected_scores()[0], 6, "未完成の修道院の点")

    # 5. 農民: 2の都市が完成したあと、青の農民はその都市に接している（終局時に3点）
    st, mp = play(city_deck, city_moves + [(1, 1, 3, None)])
    figs["farm"] = board_svg(st, mp, (0, 0), radius=1, highlight=[(-1, 0, GOLD)])
    check(st.projected_scores()[1], 3, "農民の点")
    return figs


PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>カルカソンヌ ルール入門</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
:root {
  --bg: #f1f3ee; --paper: #ffffff; --ink: #1d2620; --muted: #5c6a60; --line: #d5dccf;
  --field: #2f6b3a; --city: #9a6436; --red: #d64541; --blue: #2f6fd6; --board-bg: #e6e2d6;
  --font-display: "Dela Gothic One", "Zen Kaku Gothic New", "Hiragino Sans", sans-serif;
  --font-body: "Zen Kaku Gothic New", "Hiragino Sans", "Yu Gothic", "Noto Sans JP", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #141a16; --paper: #1c241f; --ink: #e6ece6; --muted: #9aa89d; --line: #2e3a32;
    --field: #7cc48a; --city: #d9a571; --red: #f06a62; --blue: #6c9cf0; --board-bg: #2a312c; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #141a16; --paper: #1c241f; --ink: #e6ece6; --muted: #9aa89d; --line: #2e3a32;
  --field: #7cc48a; --city: #d9a571; --red: #f06a62; --blue: #6c9cf0; --board-bg: #2a312c; color-scheme: dark;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); font-size: 16px; line-height: 1.85; padding-inline: 16px; padding-block: 0 64px; }
.wrap { max-width: 760px; margin: 0 auto; }
header.hero { padding-block: 40px 20px; display: grid; gap: 12px; }
.eyebrow { font-size: 13px; letter-spacing: .12em; color: var(--muted); font-weight: 700; }
h1 { font-family: var(--font-display); font-weight: 400; font-size: clamp(30px, 6vw, 44px); line-height: 1.25; margin: 0; }
h1 .accent { color: var(--field); }
.lede { margin: 0; max-width: 36em; }
section { padding-block: 28px 4px; border-top: 1px solid var(--line); margin-top: 20px; display: grid; gap: 14px; }
h2 { font-family: var(--font-display); font-weight: 400; font-size: 22px; margin: 0; display: flex; gap: 12px; align-items: baseline; }
h2 .no { font-family: var(--font-body); font-weight: 700; font-size: 12px; letter-spacing: .1em; color: var(--paper); background: var(--field); padding: 2px 8px; border-radius: 3px; }
h3 { font-size: 18px; margin: 6px 0 0; }
p { margin: 0; max-width: 38em; }
ol.steps { margin: 0; padding-left: 1.4em; display: grid; gap: 6px; }
figure { margin: 0; display: grid; grid-template-columns: minmax(0, 240px) minmax(0, 1fr); gap: 18px; align-items: start; }
figure .board { border-radius: 6px; overflow: hidden; border: 1px solid var(--line); background: var(--board-bg); }
figure .board svg { display: block; width: 100%; height: auto; }
figcaption { font-size: 14.5px; line-height: 1.75; }
figcaption .k { display: block; font-size: 12px; letter-spacing: .1em; color: var(--muted); font-weight: 700; }
@media (max-width: 560px) { figure { grid-template-columns: 1fr; } figure .board { max-width: 280px; } }
.red { color: var(--red); font-weight: 700; }
.blue { color: var(--blue); font-weight: 700; }
.gold { color: #b98500; font-weight: 700; }
.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; min-width: 480px; background: var(--paper); border: 1px solid var(--line); border-radius: 6px; font-size: 15px; }
th, td { padding: 8px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { font-size: 13px; color: var(--muted); font-weight: 700; }
tbody th { color: var(--ink); font-size: 15px; white-space: nowrap; }
tr:last-child td, tr:last-child th { border-bottom: 0; }
.box { background: var(--paper); border: 1px solid var(--line); border-radius: 6px; padding: 14px 18px; }
.box ul { margin: 0; padding-left: 1.2em; display: grid; gap: 4px; }
.next { display: flex; flex-wrap: wrap; gap: 10px; }
.next a { display: inline-block; padding: 8px 16px; border-radius: 6px; background: var(--field); color: var(--paper); text-decoration: none; font-weight: 700; }
.next a.sub { background: var(--paper); color: var(--ink); border: 1px solid var(--line); }
a { color: var(--field); }
:focus-visible { outline: 2px solid var(--field); outline-offset: 2px; }
__NAV_CSS__
</style>
</head>
<body>
<div class="wrap">
__NAV__
<header class="hero">
  <span class="eyebrow">カルカソンヌ ・ 基本ルール ・ 2〜5人</span>
  <h1>はじめての<span class="accent">カルカソンヌ</span></h1>
  <p class="lede">タイルを1枚ずつつなげて地図を広げ、できあがった都市や道に置いた自分のコマ（ミープル）で点を取るゲームです。このページでは、遊ぶのに必要なルールを図つきで説明します。</p>
</header>

<section id="flow">
  <h2><span class="no">1</span>手番にやること</h2>
  <ol class="steps">
    <li><b>タイルを1枚引いて置く。</b>すでにあるタイルの隣に、辺の絵がつながるように置きます。</li>
    <li><b>ミープルを置いてもよい。</b>今置いたタイルの上の都市・道・修道院・草原のどれか1か所に、自分のミープルを1個置けます。置かなくてもかまいません。</li>
    <li><b>完成したら得点。</b>都市・道・修道院が完成したら、そこにミープルを置いている人が点をもらい、ミープルは手元に戻ります。</li>
  </ol>
  <p>山札がなくなったらゲーム終了です。最後に、完成していないものと草原の点を数え、合計点の多い人が勝ちです。</p>
</section>

<section id="place">
  <h2><span class="no">2</span>タイルの置き方</h2>
  <figure>
    <div class="board">__FIG_place__</div>
    <figcaption><span class="k">例</span>最初のタイルの右に、<span class="gold">黄色の枠</span>のタイルを置きました。道は道に、草原は草原につながっています。都市の辺の隣には都市、道の隣には道しか置けません。向きは自由に回せます。</figcaption>
  </figure>
  <p>どこにも置けないタイルを引いたら、そのタイルは使わずに箱へ戻し、もう1枚引きます。</p>
</section>

<section id="meeple">
  <h2><span class="no">3</span>ミープルの置き方</h2>
  <div class="box"><ul>
    <li>ミープルは1人7個。置けるのは<b>今置いたタイルの上だけ</b>です。</li>
    <li>つながった都市や道に<b>すでに誰かのミープルがいたら、そこには置けません</b>（自分のものでも）。</li>
    <li>別々に置いた都市があとでつながって、1つの都市に複数のミープルがいることになるのはかまいません。そのときは<b>ミープルが多い人が点をもらい、同じ数なら全員が満点</b>をもらいます。</li>
    <li>置いたミープルは、その場所が完成するまで戻ってきません。草原のミープル（農民）は最後まで戻りません。</li>
  </ul></div>
</section>

<section id="score">
  <h2><span class="no">4</span>点の数え方</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>場所</th><th>完成したとき（すぐ）</th><th>終了時に未完成なら</th></tr></thead>
    <tbody>
      <tr><th>都市</th><td>1タイル2点＋盾1つにつき2点</td><td>1タイル1点＋盾1つにつき1点</td></tr>
      <tr><th>道</th><td>1タイル1点</td><td>1タイル1点</td></tr>
      <tr><th>修道院</th><td>周りの8マスが全部埋まったら9点</td><td>1点＋周りの埋まったマス1つにつき1点</td></tr>
      <tr><th>草原（農民）</th><td>途中では数えない</td><td>接している<b>完成した</b>都市1つにつき3点</td></tr>
    </tbody>
  </table></div>

  <h3>都市</h3>
  <figure>
    <div class="board">__FIG_city__</div>
    <figcaption><span class="k">例</span><span class="red">赤</span>は盾のある都市にミープルを置いています。<span class="gold">黄色の枠</span>に都市のタイルを置くと、3枚の都市が閉じて完成します。3枚×2点＋盾1つ×2点で<b>8点</b>。ミープルは手元に戻ります。</figcaption>
  </figure>

  <h3>道</h3>
  <figure>
    <div class="board">__FIG_road__</div>
    <figcaption><span class="k">例</span>道は、十字路・修道院・都市などで両端が止まると完成です。<span class="red">赤</span>の道は左端が十字路で止まっていて、<span class="gold">黄色の枠</span>にもう1つ十字路を置くと完成。3枚で<b>3点</b>です。</figcaption>
  </figure>

  <h3>修道院</h3>
  <figure>
    <div class="board">__FIG_monastery__</div>
    <figcaption><span class="k">例</span><span class="red">赤</span>の修道院（<span class="gold">黄色の枠</span>）の周りの8マスのうち、5マスが埋まっています。全部埋まれば9点ですが、このまま終わると修道院の1点＋5マスで<b>6点</b>です。</figcaption>
  </figure>

  <h3>草原（農民）</h3>
  <figure>
    <div class="board">__FIG_farm__</div>
    <figcaption><span class="k">例</span><span class="blue">青</span>は<span class="gold">黄色の枠</span>のタイルの上側の草原にミープルを置いています（草原のミープルを農民と呼びます）。この草原は、さっき完成した都市に接しているので、終了時に<b>3点</b>入ります。都市が完成していなければ0点です。</figcaption>
  </figure>
</section>

<section id="end">
  <h2><span class="no">5</span>ゲームの終わり</h2>
  <p>最後のタイルを置いて得点したら終了です。盤上に残っているミープルについて、上の表の「終了時」の点を数えて足します。合計点が多い人の勝ちです。</p>
</section>

<section id="first">
  <h2><span class="no">6</span>はじめての人へのヒント</h2>
  <div class="box"><ul>
    <li>まずは<b>小さな都市を作って閉じる</b>のがいちばん確実に点になります。</li>
    <li>ミープルは7個しかありません。<b>なかなか完成しない長い道</b>に置くと、しばらく戻ってきません。</li>
    <li>迷ったら、<b>今すぐ完成させられるもの</b>がないか探しましょう。点が入り、ミープルも戻ります。</li>
  </ul></div>
  <div class="next">
    <a href="ai_tips.html">次は：強いAIに学ぶコツ</a>
    <a class="sub" href="quiz.html">次の一手クイズで練習する</a>
  </div>
</section>

<section id="notes">
  <h2>このページのルールについて</h2>
  <p style="font-size:14.5px;color:var(--muted)">基本セット（72枚）の現行ルールです。農民は完成した都市1つにつき3点で数えます（古い版には別の数え方があります）。図はこのプロジェクトのルールエンジンで実際に手を進めた局面で、本文の点数もエンジンの得点計算で確かめています（<code>scripts/build_rules_page.py</code>）。2人対戦で説明していますが、2〜5人で同じルールで遊べます。</p>
</section>
</div>
</body>
</html>
"""


def main() -> None:
    html = PAGE.replace("__NAV_CSS__", NAV_CSS).replace("__NAV__", nav_html("rules.html"))
    for k, svg in figures().items():
        html = html.replace(f"__FIG_{k}__", svg)
    if "__" in html.replace("__init__", ""):
        raise SystemExit("置き換え忘れのプレースホルダがあります")
    out = ROOT / "docs" / "rules.html"
    out.write_text(html, encoding="utf-8")
    print(f"{out} を書き出しました（{len(html) // 1024} KB）")


if __name__ == "__main__":
    main()
