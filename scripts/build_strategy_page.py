"""ルールを覚えた人向けの戦略ガイド docs/strategy.html を作る。

    py scripts/build_strategy_page.py

タイルの枚数や「この穴に合うタイルは何枚か」は data/tiles.json からその場で数える。
本文の言い切り（例: 都市・道・都市・道に囲まれた穴は埋まらない）はここで確かめ、食い違えば止まる。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from board_svg import tile_svg
from site_nav import NAV_CSS, nav_html

from carcassonne.tiles import CITY, FIELD, ROAD, load_tileset

TS = load_tileset()
EDGE_JA = {CITY: "都市", ROAD: "道", FIELD: "草原", None: "空き"}
# 穴の上・右・下・左にある隣のタイルが、穴に向けている辺の番号
FACING = [2, 3, 0, 1]
NEIGHBOR_CELL = [(1, 0), (2, 1), (1, 2), (0, 1)]


def check(actual, expected, what: str) -> None:
    if actual != expected:
        raise SystemExit(
            f"{what}: 数えると {actual}、本文は {expected}。本文か数え方を直してください"
        )


def fits(pattern) -> list[tuple[object, object]]:
    """pattern（上・右・下・左の辺の種類、None は空き）に合うタイル種別と、合う向き。"""
    out = []
    for t in TS.types:
        for v in t.variants:
            if all(p is None or v.edges[i] == p for i, p in enumerate(pattern)):
                out.append((t, v))
                break
    return out


def n_fit(pattern) -> int:
    return sum(t.count for t, _ in fits(pattern))


def neighbor_variant(side: int, edge: str):
    """穴の side 側に置く隣のタイル（穴に向いた辺が edge）。都市は1辺都市、道と草原はまっすぐな道。"""
    tid = "city_top" if edge == CITY else "straight_road"
    for v in TS.types[TS.index[tid]].variants:
        if v.edges[FACING[side]] == edge:
            return v
    raise AssertionError((side, edge))


def tile_thumb(v, count: int, S: int = 48) -> str:
    return (
        f'<span class="tt"><svg viewBox="0 0 {S} {S}" width="{S}" height="{S}" role="img">'
        f"{tile_svg(v, 0, 0, S)}</svg><small>×{count}</small></span>"
    )


def hole_svg(pattern, S: int = 52) -> str:
    """穴（中央）と、その周りに置かれたタイル（上下左右）を描く。"""
    W = 3 * S
    parts = [f'<svg viewBox="0 0 {W} {W}" xmlns="http://www.w3.org/2000/svg" role="img">']
    parts.append(f'<rect width="{W}" height="{W}" fill="var(--board-bg, #efe9dc)"/>')
    for side, edge in enumerate(pattern):
        if edge is None:
            continue
        cx, cy = NEIGHBOR_CELL[side]
        parts.append(tile_svg(neighbor_variant(side, edge), cx * S, cy * S, S))
    mark = "×" if n_fit(pattern) == 0 else "?"
    parts.append(
        f'<rect x="{S + 3}" y="{S + 3}" width="{S - 6}" height="{S - 6}" fill="none" '
        f'stroke="#f5b400" stroke-width="3" stroke-dasharray="6 4" rx="3"/>'
        f'<text x="{1.5 * S}" y="{1.5 * S + 9}" text-anchor="middle" font-size="26" '
        f'font-weight="700" fill="var(--ink, #222)">{mark}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def pattern_label(pattern) -> str:
    return "・".join(EDGE_JA[p] for p in pattern)


def hole_figure(pattern, caption: str) -> str:
    matches = fits(pattern)
    n = sum(t.count for t, _ in matches)
    thumbs = "".join(tile_thumb(v, t.count) for t, v in matches) or "<em>なし</em>"
    return (
        '<figure class="hole">'
        f'<div class="board">{hole_svg(pattern)}</div>'
        f'<figcaption><span class="k">上・右・下・左 ＝ {pattern_label(pattern)}</span>'
        f"<span>合うタイルは<b>{n}枚</b>。{caption}</span>"
        f'<span class="thumbs">{thumbs}</span></figcaption>'
        "</figure>"
    )


def gallery(types) -> str:
    return (
        '<div class="gallery">'
        + "".join(tile_thumb(t.variants[0], t.count) for t in types)
        + "</div>"
    )


def build() -> str:
    C, R, F, N = CITY, ROAD, FIELD, None
    types = TS.types
    total = TS.total
    placed = total - 1  # 開始タイルは最初から置かれている
    city_t = [t for t in types if any(p.kind == CITY for p in t.variants[0].pieces)]
    mon_t = [t for t in types if any(p.kind == "M" for p in t.variants[0].pieces)]
    road_t = [t for t in types if t not in city_t and t not in mon_t]
    n_city = sum(t.count for t in city_t)
    n_mon = sum(t.count for t in mon_t)
    n_road = sum(t.count for t in road_t)
    check(n_city + n_mon + n_road, total, "タイルの内訳の合計")
    n_shield = sum(
        t.count for t in types if any(p.kind == CITY and p.pennant for p in t.variants[0].pieces)
    )

    # 本文で言い切っていること
    check(total, 72, "タイルの総数")
    check(n_fit((C, R, C, R)), 0, "都市・道・都市・道の穴")
    check(n_fit((C, C, C, C)), 1, "四方が都市の穴")
    check(n_fit((R, R, R, R)), 1, "四方が道の穴")
    check(n_fit((C, N, C, N)) > n_fit((C, F, C, F)), True, "囲まれるほど合うタイルが減る")
    check(n_fit((C, C, C, N)) > n_fit((C, C, C, F)), True, "囲まれるほど合うタイルが減る")
    check(n_fit((C, F, F, F)) < 10, True, "1辺都市・3辺草原の穴は10枚未満")

    table_rows = []
    for pat, note in [
        ((C, N, N, N), "都市の口が1つ空いているだけ（隣は空き）"),
        ((C, N, C, N), "上下が都市、左右は空き"),
        ((C, C, N, N), "上と右が都市、ほかは空き"),
        ((C, F, F, F), "都市の口のまわりを草原で囲まれた"),
        ((C, C, C, F), "3方向が都市、残りが草原"),
        ((C, C, C, R), "3方向が都市、残りが道"),
        ((C, C, C, C), "4方向が都市"),
        ((R, R, R, R), "4方向が道"),
        ((C, R, C, R), "上下が都市、左右が道"),
    ]:
        n = n_fit(pat)
        cls = ' class="zero"' if n == 0 else (' class="few"' if n <= 5 else "")
        table_rows.append(
            f"<tr{cls}><th>{pattern_label(pat)}</th><td>{note}</td><td class='n'>{n}枚</td></tr>"
        )

    sub = {
        "__NAV_CSS__": NAV_CSS,
        "__NAV__": nav_html("strategy.html"),
        "__TOTAL__": str(total),
        "__PLACED__": str(placed),
        "__TURN_LO__": str(placed // 2),
        "__TURN_HI__": str(placed - placed // 2),
        "__N_CITY__": str(n_city),
        "__N_ROAD__": str(n_road),
        "__N_MON__": str(n_mon),
        "__N_SHIELD__": str(n_shield),
        "__GAL_CITY__": gallery(city_t),
        "__GAL_ROAD__": gallery(road_t),
        "__GAL_MON__": gallery(mon_t),
        "__HOLE_A__": hole_figure(
            (C, N, C, N), "左右が空いているうちは、都市を3方向に持つタイルなども入ります。"
        ),
        "__HOLE_B__": hole_figure(
            (C, F, C, F),
            "左右にもタイルが置かれて草原と決まると、合うタイルはぐっと減ります。",
        ),
        "__HOLE_C__": hole_figure(
            (C, C, C, F), "3方向から都市が迫る穴は、自分の都市に作るとなかなか閉じません。"
        ),
        "__HOLE_D__": hole_figure(
            (C, R, C, R),
            "こういう穴はどのタイルでも埋まりません。上下の都市は、この穴がある限り<b>もう完成しません</b>。",
        ),
        "__HOLE_TABLE__": "".join(table_rows),
        "__N_CFFF__": str(n_fit((C, F, F, F))),
    }
    html = PAGE
    for k, v in sub.items():
        html = html.replace(k, v)
    return html


PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>カルカソンヌ戦略ガイド</title>
<meta name="description" content="ルールを覚えたカルカソンヌ初心者向けの戦略ガイド。考え方の土台、タイルの内訳、穴の埋まりやすさ、序盤・中盤・終盤の方針、割り込みと守り、農民、よくある失敗、用語集。">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
:root {
  --bg: #f1f3ee; --paper: #ffffff; --ink: #1d2620; --muted: #5c6a60; --line: #d5dccf;
  --field: #2f6b3a; --city: #9a6436; --red: #d64541; --blue: #2f6fd6; --board-bg: #e6e2d6; --warn: #b3261e;
  --font-display: "Dela Gothic One", "Zen Kaku Gothic New", "Hiragino Sans", sans-serif;
  --font-body: "Zen Kaku Gothic New", "Hiragino Sans", "Yu Gothic", "Noto Sans JP", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #141a16; --paper: #1c241f; --ink: #e6ece6; --muted: #9aa89d; --line: #2e3a32;
    --field: #7cc48a; --city: #d9a571; --red: #f06a62; --blue: #6c9cf0; --board-bg: #2a312c; --warn: #f2938c; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #141a16; --paper: #1c241f; --ink: #e6ece6; --muted: #9aa89d; --line: #2e3a32;
  --field: #7cc48a; --city: #d9a571; --red: #f06a62; --blue: #6c9cf0; --board-bg: #2a312c; --warn: #f2938c; color-scheme: dark;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); font-size: 16px; line-height: 1.85; padding-inline: 16px; padding-block: 0 64px; }
.wrap { max-width: 760px; margin: 0 auto; }
header.hero { padding-block: 40px 20px; display: grid; gap: 12px; }
.eyebrow { font-size: 13px; letter-spacing: .12em; color: var(--muted); font-weight: 700; }
h1 { font-family: var(--font-display); font-weight: 400; font-size: clamp(30px, 6vw, 44px); line-height: 1.25; margin: 0; }
h1 .accent { color: var(--field); }
.lede { margin: 0; max-width: 36em; }
.toc { display: flex; flex-wrap: wrap; gap: 6px 8px; margin: 0; padding: 0; list-style: none; font-size: 14px; }
.toc a { display: inline-block; padding: 3px 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--ink); text-decoration: none; }
.toc a:hover, .toc a:focus-visible { border-color: var(--field); outline: none; }
section { padding-block: 28px 4px; border-top: 1px solid var(--line); margin-top: 20px; display: grid; gap: 14px; }
h2 { font-family: var(--font-display); font-weight: 400; font-size: 22px; margin: 0; display: flex; gap: 12px; align-items: baseline; }
h2 .no { font-family: var(--font-body); font-weight: 700; font-size: 12px; letter-spacing: .1em; color: var(--paper); background: var(--field); padding: 2px 8px; border-radius: 3px; }
h3 { font-size: 18px; margin: 6px 0 0; }
p { margin: 0; max-width: 38em; }
.box { background: var(--paper); border: 1px solid var(--line); border-radius: 6px; padding: 14px 18px; }
.box ul, .box ol { margin: 0; padding-left: 1.3em; display: grid; gap: 6px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
.card { background: var(--paper); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; display: grid; gap: 6px; align-content: start; }
.card b.t { font-size: 16.5px; }
.card .when { font-size: 12.5px; color: var(--muted); font-weight: 700; letter-spacing: .06em; }
.card ul { margin: 0; padding-left: 1.2em; font-size: 15px; display: grid; gap: 4px; }
.big { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.big div { background: var(--paper); border: 1px solid var(--line); border-radius: 6px; padding: 10px 14px; }
.big b { display: block; font-size: 26px; line-height: 1.2; color: var(--field); }
.big small { color: var(--muted); font-size: 13px; }
.gallery { display: flex; flex-wrap: wrap; gap: 8px; }
.tt { display: inline-grid; justify-items: center; gap: 0; }
.tt svg { display: block; border-radius: 3px; }
.tt small { font-size: 12.5px; color: var(--muted); font-weight: 700; }
figure.hole { margin: 0; display: grid; grid-template-columns: minmax(0, 156px) minmax(0, 1fr); gap: 16px; align-items: start; }
figure .board { border-radius: 6px; overflow: hidden; border: 1px solid var(--line); background: var(--board-bg); }
figure .board svg { display: block; width: 100%; height: auto; }
figcaption { font-size: 14.5px; line-height: 1.75; display: grid; gap: 6px; }
figcaption .k { display: block; font-size: 12px; letter-spacing: .06em; color: var(--muted); font-weight: 700; }
figcaption .thumbs { display: flex; flex-wrap: wrap; gap: 6px; }
@media (max-width: 560px) { figure.hole { grid-template-columns: 1fr; } figure .board { max-width: 180px; } }
.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; min-width: 480px; background: var(--paper); border: 1px solid var(--line); border-radius: 6px; font-size: 15px; }
th, td { padding: 8px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
thead th { font-size: 13px; color: var(--muted); font-weight: 700; }
tbody th { color: var(--ink); font-size: 15px; white-space: nowrap; }
td.n { text-align: right; white-space: nowrap; font-weight: 700; }
tr.few td.n { color: var(--city); }
tr.zero td.n { color: var(--warn); }
tr:last-child td, tr:last-child th { border-bottom: 0; }
dl.terms { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; }
dl.terms dt { font-weight: 700; }
dl.terms dd { margin: 0; }
@media (max-width: 560px) { dl.terms { grid-template-columns: 1fr; } dl.terms dd { margin-bottom: 6px; } }
.next { display: flex; flex-wrap: wrap; gap: 10px; }
.next a { display: inline-block; padding: 8px 16px; border-radius: 6px; background: var(--field); color: var(--paper); text-decoration: none; font-weight: 700; }
.next a.sub { background: var(--paper); color: var(--ink); border: 1px solid var(--line); }
.note { font-size: 14px; color: var(--muted); }
a { color: var(--field); }
:focus-visible { outline: 2px solid var(--field); outline-offset: 2px; }
__NAV_CSS__
</style>
</head>
<body>
<div class="wrap">
__NAV__
<header class="hero">
  <span class="eyebrow">カルカソンヌ ・ 基本ルール ・ ルールを覚えた人へ</span>
  <h1>勝つための<span class="accent">考え方</span></h1>
  <p class="lede">ルールは分かったけれど、何を考えて置けばいいか分からない。そんな人のための戦略ガイドです。考え方の土台から、タイルの内訳、序盤・中盤・終盤の方針、よくある失敗までを順番にまとめました。</p>
  <ul class="toc">
    <li><a href="#base">考え方の土台</a></li>
    <li><a href="#first">まず覚える5つ</a></li>
    <li><a href="#tiles">タイルの内訳</a></li>
    <li><a href="#holes">穴の埋まりやすさ</a></li>
    <li><a href="#phase">序盤・中盤・終盤</a></li>
    <li><a href="#attack">割り込みと守り</a></li>
    <li><a href="#farm">農民</a></li>
    <li><a href="#mistakes">よくある失敗</a></li>
    <li><a href="#terms">用語集</a></li>
    <li><a href="#practice">練習のしかた</a></li>
  </ul>
</header>

<section id="base">
  <h2><span class="no">1</span>考え方の土台</h2>
  <div class="big">
    <div><b>__PLACED__枚</b><small>1局で置くタイル（全__TOTAL__枚から開始タイルを除く）</small></div>
    <div><b>__TURN_LO__〜__TURN_HI__手</b><small>2人対戦で1人が置く回数</small></div>
    <div><b>7個</b><small>1人のミープル。これを何回使い回せるかが勝負</small></div>
  </div>
  <div class="box"><ul>
    <li><b>点差で考える。</b>2人対戦では「自分の点−相手の点」が大きいほど勝ちに近づきます。自分が3点取る手と、相手の3点を消す手は同じ価値です。相手に5点入る手は、自分が5点失うのと同じです。</li>
    <li><b>完成させると倍になる。</b>都市は完成すれば1タイル2点、未完成のまま終わると1点です。修道院も完成すれば9点ですが、未完成だと周りの埋まり具合しだいです。道だけは完成してもしなくても1タイル1点です。</li>
    <li><b>ミープルは早く戻すほど得。</b>完成すればミープルは手元に戻り、また別の場所で点を生みます。7個を「置いたまま動かない」状態にしないことが、点を伸ばすいちばんの近道です。</li>
  </ul></div>
</section>

<section id="first">
  <h2><span class="no">2</span>まず覚える5つ</h2>
  <p>最初の数ゲームは、この5つだけ意識すれば十分です。</p>
  <div class="box"><ol>
    <li><b>小さな都市を作って、すぐ閉じる。</b>2〜3枚の都市は閉じやすく、確実に点とミープルが戻ってきます。</li>
    <li><b>道に乗せるのは、すぐ終わる道だけ。</b>道は安く、端が決まらないといつまでも戻ってきません。</li>
    <li><b>修道院は、周りが埋まりやすい場所に。</b>盤の真ん中寄り、すでにタイルが多いところに置くと9点に届きやすくなります。</li>
    <li><b>ミープルを1〜2個は手元に残す。</b>相手の都市に割り込む、終盤に農民を置くなど、あとで大きな点になる場面に使えます。</li>
    <li><b>置く前に「相手が得をしないか」を見る。</b>相手の都市を完成させてしまうと、相手に点が入りミープルも戻ります。自分の得と相手の得を比べてから置きましょう。</li>
  </ol></div>
</section>

<section id="tiles">
  <h2><span class="no">3</span>タイルの内訳を知る</h2>
  <p>山札の中身は決まっています。どんなタイルが何枚あるかを知っていると、「この形はあと何枚残っているか」を考えられるようになります。上級者が強いのは、この数え方ができるからです。</p>
  <div class="big">
    <div><b>__N_CITY__枚</b><small>都市があるタイル（うち盾つき__N_SHIELD__枚）</small></div>
    <div><b>__N_ROAD__枚</b><small>道と草原だけのタイル</small></div>
    <div><b>__N_MON__枚</b><small>修道院のタイル</small></div>
  </div>
  <h3>都市があるタイル</h3>
  __GAL_CITY__
  <h3>道と草原だけのタイル</h3>
  __GAL_ROAD__
  <h3>修道院のタイル</h3>
  __GAL_MON__
  <p class="note">数字は基本セット全体の枚数で、開始タイル（上が都市・左右に道）の1枚も含みます。</p>
</section>

<section id="holes">
  <h2><span class="no">4</span>穴の埋まりやすさ</h2>
  <p>都市を完成させるには、口（開いている辺）をすべてタイルで埋める必要があります。ところが、まわりにタイルが増えるほど、その穴に合うタイルは減っていきます。どんな穴が埋まりにくいかを知ると、<b>自分の都市を危ない形にしない</b>ことと、<b>相手の都市を閉じにくくする</b>ことの両方に使えます。</p>
  __HOLE_A__
  __HOLE_B__
  __HOLE_C__
  __HOLE_D__
  <div class="tablewrap"><table>
    <thead><tr><th>上・右・下・左</th><th>どんな穴か</th><th>合うタイル</th></tr></thead>
    <tbody>__HOLE_TABLE__</tbody>
  </table></div>
  <div class="box"><ul>
    <li><b>合う枚数から、もう出た枚数を引く。</b>表は山札全体の枚数です。同じ形がすでに盤に出ていれば、その分だけ残りは少なくなります。</li>
    <li><b>2人対戦では、相手が引くかもしれない。</b>合うタイルが残っていても、それを相手が引けば、相手は自分のために使います。合う枚数が少ない穴は「ほぼ閉じない」と考えて、ミープルを置きすぎないようにしましょう。</li>
    <li><b>シンプルな穴でも意外と少ない。</b>都市の口のまわりを草原で囲まれただけの穴でも、合うのは__N_CFFF__枚（1辺だけ都市のタイル）しかありません。</li>
  </ul></div>
</section>

<section id="phase">
  <h2><span class="no">5</span>序盤・中盤・終盤の方針</h2>
  <div class="cards">
    <div class="card">
      <span class="when">序盤（最初の3分の1）</span>
      <b class="t">土台を作る</b>
      <ul>
        <li>新しい小さな都市を自分で始めて閉じる。</li>
        <li>修道院は引いたら置きやすい場所へ。</li>
        <li>農民は置いても1〜2個まで。</li>
        <li>ミープルを一気に使い切らない。</li>
      </ul>
    </div>
    <div class="card">
      <span class="when">中盤</span>
      <b class="t">相手との関わり</b>
      <ul>
        <li>相手の大きな都市に割り込んで分け合う。</li>
        <li>自分の修道院の周りを自分で埋める。</li>
        <li>相手の都市の隣に、埋まりにくい穴ができる置き方を考える。</li>
        <li>自分の都市は口を増やさず、早めに閉じる。</li>
      </ul>
    </div>
    <div class="card">
      <span class="when">終盤（残り十数枚）</span>
      <b class="t">取り切る</b>
      <ul>
        <li>もう閉じない都市や道に、新しくミープルを置かない。</li>
        <li>余ったミープルは、完成した都市にたくさん接する草原へ。</li>
        <li>修道院は未完成でも周りの数だけ点になる。</li>
        <li>最後の1枚まで、相手の完成を止める手を探す。</li>
      </ul>
    </div>
  </div>
  <p>「強いAIに学ぶコツ」では、強いAIの対局を集計して、ミープルを使うペースや農民を置く時期を数字で確かめています。</p>
</section>

<section id="attack">
  <h2><span class="no">6</span>割り込みと守り</h2>
  <h3>攻め：相手の都市に割り込む</h3>
  <p>相手のミープルがいる都市には直接置けませんが、<b>すぐ隣に自分の小さな都市を作ってミープルを置き、あとで1枚でつなげる</b>と合流できます。ミープルの数が同じなら両方が満点、自分の方が多ければ自分だけが点をもらえます。相手の大きな都市ほど、割り込む価値があります。</p>
  <h3>攻め：相手の都市を閉じにくくする</h3>
  <p>相手の都市の口の隣に置くとき、上の表で「合うタイルが少ない」穴になるように向きを選びます。都市・道・都市・道のように<b>どのタイルでも埋まらない穴</b>を作れれば、その都市はもう完成しません。完成すれば1タイル2点の都市が1点に下がり、相手のミープルも最後まで戻りません。</p>
  <h3>守り：割り込まれない・塞がれない都市にする</h3>
  <div class="box"><ul>
    <li>自分の都市の口は少なく保ち、閉じられるときに閉じる。大きく育てるほど、割り込みと塞ぎの的になります。</li>
    <li>相手が自分の都市の近くに別の都市を作り始めたら、割り込みの合図です。先に閉じるか、つながらない形にしましょう。</li>
    <li>自分で3方向から都市が迫る穴を作らない。引けるタイルが少なくなります。</li>
  </ul></div>
</section>

<section id="farm">
  <h2><span class="no">7</span>農民（草原）の基本</h2>
  <div class="box"><ul>
    <li><b>草原は道と都市で区切られる。</b>道の両側は別々の草原です。農民を置く前に、その草原がどこまで広がっているかを確かめましょう。</li>
    <li><b>完成しそうな都市にたくさん接する草原を選ぶ。</b>点になるのは終了時に完成している都市だけで、1つにつき3点です。小さな都市がいくつも接している草原は強い場所です。</li>
    <li><b>草原も多数決。</b>都市と同じく、つながった草原では農民が多い人が点をもらい、同じ数なら両方が満点です。相手の大きな草原に、別の草原から割り込むこともできます。</li>
    <li><b>農民は最後まで戻らない。</b>序盤に置きすぎると都市に使うミープルが足りなくなります。序盤は1〜2個、残りは終盤に。</li>
  </ul></div>
</section>

<section id="mistakes">
  <h2><span class="no">8</span>よくある失敗</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>失敗</th><th>なぜ損か</th><th>代わりに</th></tr></thead>
    <tbody>
      <tr><th>序盤にミープルを全部置く</th><td>大事な場面で置けない。割り込みにも使えない</td><td>1〜2個は手元に残す</td></tr>
      <tr><th>長い道にミープルを乗せる</th><td>道は安いうえ、なかなか戻らない</td><td>端が決まっている短い道だけに乗せる</td></tr>
      <tr><th>大きな都市を欲張って閉じない</th><td>未完成で終わると半分の点。割り込まれやすい</td><td>閉じられるときに閉じる</td></tr>
      <tr><th>相手の都市を完成させる</th><td>相手に点が入り、ミープルも戻る</td><td>自分の得が上回るときだけにする</td></tr>
      <tr><th>盤の端に修道院を置く</th><td>周りが埋まらず9点に届かない</td><td>タイルが多い場所の近くに置く</td></tr>
      <tr><th>埋まりにくい穴がある都市に乗せる</th><td>合うタイルが残っていないと完成しない</td><td>穴に合うタイルの枚数を数える</td></tr>
      <tr><th>終盤に新しい都市を始める</th><td>閉じる前に山札がなくなる</td><td>草原や、すぐ閉じる場所に使う</td></tr>
      <tr><th>自分の点だけ見て置く</th><td>相手が大きく得をする手を見逃す</td><td>置く前に相手の得も比べる</td></tr>
    </tbody>
  </table></div>
</section>

<section id="terms">
  <h2><span class="no">9</span>用語集</h2>
  <div class="box"><dl class="terms">
    <dt>タイル</dt><dd>地図のかけら。全__TOTAL__枚。1枚ずつ引いて、辺の絵が合うように置く。</dd>
    <dt>ミープル</dt><dd>人の形をした自分のコマ。1人7個。置く場所によって呼び名が変わる。</dd>
    <dt>騎士・盗賊・修道士・農民</dt><dd>都市・道・修道院・草原に置いたミープルの呼び名。</dd>
    <dt>特徴</dt><dd>都市・道・修道院・草原のこと。つながったものは1つの特徴として数える。</dd>
    <dt>盾</dt><dd>都市のタイルについている紋章。完成した都市なら1つにつき2点増える。</dd>
    <dt>口</dt><dd>都市や道の、まだタイルが置かれていない開いた辺。全部埋まると完成。</dd>
    <dt>割り込み（合流）</dt><dd>別々に作った都市や草原をつないで、相手と同じ特徴に自分のミープルを入れること。</dd>
    <dt>多数決</dt><dd>1つの特徴に複数のミープルがいるとき、多い人が点をもらう（同数なら全員満点）。</dd>
    <dt>完成不能</dt><dd>どのタイルでも埋まらない穴があって、もう完成しない状態。</dd>
    <dt>終了時の得点</dt><dd>山札がなくなったあと、未完成の都市・道・修道院と農民を数える得点。</dd>
  </dl></div>
</section>

<section id="practice">
  <h2><span class="no">10</span>練習のしかた</h2>
  <div class="box"><ol>
    <li><b>次の一手クイズの入門編を解く。</b>「すぐ閉じる」「ミープルを残す」など、このページの考え方を局面で確かめられます。</li>
    <li><b>AIと対戦する（初心者モード）。</b>自分の手が何点損だったかが表示されます。損が大きかった手だけ振り返れば十分です。</li>
    <li><b>強いAIに学ぶコツを読む。</b>実戦の図で、割り込みや相手の都市を閉じにくくする手を見られます。</li>
    <li><b>クイズの実戦編に進む。</b>迷う局面で、点差で考える練習になります。</li>
  </ol></div>
  <div class="next">
    <a href="quiz.html">次の一手クイズ</a>
    <a class="sub" href="play.html">AIと対戦</a>
    <a class="sub" href="ai_tips.html">強いAIに学ぶコツ</a>
  </div>
</section>

<section id="about">
  <h2>このページについて</h2>
  <p class="note">基本セット（72枚）の現行ルールで、2人対戦を想定しています。タイルの枚数と「穴に合うタイルの枚数」は、このプロジェクトのタイル定義（data/tiles.json）から数えています。向きを回して辺の種類（都市・道・草原）が合えば「合う」としていて、都市が穴の中でつながるかどうかは区別していません（scripts/build_strategy_page.py）。</p>
</section>
</div>
</body>
</html>
"""


def main() -> None:
    html = build()
    if "__" in html.replace("__init__", ""):
        raise SystemExit("置き換え忘れのプレースホルダがあります")
    out = ROOT / "docs" / "strategy.html"
    out.write_text(html, encoding="utf-8")
    print(f"{out} を書き出しました（{len(html) // 1024} KB）")


if __name__ == "__main__":
    main()
