"""データページ「数字で見るカルカソンヌ」（docs/stats.html）を組み立てる。

    py scripts/build_stats_page.py

入力: docs/results/game_stats.json（scripts/summarize_game_stats.py）。
本文の数値はすべて集計値から入れる。「〜がいちばん多い」などの言い切りは check_claims で確かめ、
集計し直して合わなくなったら止まる（本文を直す）。
他のゲームの数字は OTHER_GAMES に出典つきで書く（出典で確かめた値だけを書く）。
英語ページは、決まった文を対訳表 web/i18n/en/stats.json で訳し、数値の入る文はここで英語を作る。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from board_svg import tile_svg
from i18n import to_english_page, write_pair
from site_nav import NAV_CSS, nav_html, support_html

from carcassonne.tiles import load_tileset

STATS = ROOT / "docs" / "results" / "game_stats.json"
TS = load_tileset()

KINDS = ["C", "R", "M", "F"]
KIND = {
    "ja": {"C": "都市", "R": "道", "M": "修道院", "F": "草原"},
    "en": {"C": "City", "R": "Road", "M": "Monastery", "F": "Field"},
}
TILE_NAME = {
    "bent_road": ("カーブした道", "Curved road"),
    "chapel": ("修道院", "Monastery"),
    "chapel_with_road": ("道つき修道院", "Monastery with road"),
    "city_bottom_grass": ("3辺の都市", "Three-sided city"),
    "city_bottom_grass_shield": ("3辺の都市（盾）", "Three-sided city (shield)"),
    "city_bottom_road": ("3辺の都市＋道", "Three-sided city + road"),
    "city_bottom_road_shield": ("3辺の都市＋道（盾）", "Three-sided city + road (shield)"),
    "city_diagonal_top_left_road": ("角の都市＋カーブ道", "Corner city + curved road"),
    "city_diagonal_top_left_shield_road": (
        "角の都市＋カーブ道（盾）",
        "Corner city + curved road (shield)",
    ),
    "city_diagonal_top_right": ("角の都市", "Corner city"),
    "city_diagonal_top_right_shield": ("角の都市（盾）", "Corner city (shield)"),
    "city_left_right": ("向かい合う2つの都市の端", "Two opposite city edges"),
    "city_narrow": ("筒形の都市", "City tube"),
    "city_narrow_shield": ("筒形の都市（盾）", "City tube (shield)"),
    "city_top": ("1辺の都市", "One city edge"),
    "city_top_crossroads": ("1辺の都市＋三差路", "City edge + junction"),
    "city_top_right": ("隣り合う2つの都市の端", "Two adjacent city edges"),
    "city_top_road_bend_left": ("1辺の都市＋カーブ道（左）", "City edge + curve (left)"),
    "city_top_road_bend_right": ("1辺の都市＋カーブ道（右）", "City edge + curve (right)"),
    "city_top_straight_road": ("1辺の都市＋まっすぐな道", "City edge + straight road"),
    "crossroads": ("十字路", "Crossroads"),
    "full_city_with_shield": ("4辺の都市（盾）", "Four-sided city (shield)"),
    "straight_road": ("まっすぐな道", "Straight road"),
    "three_split_road": ("三差路", "Junction"),
}
LEVEL = {
    "random": ("でたらめに置くAI", "Random AI"),
    "greedy": ("目先の点だけのAI", "Greedy AI"),
    "standard": ("対戦ページの「標準」", "“Standard” on the play page"),
    "strong": ("対戦ページの「最強」", "“Strongest” on the play page"),
}

# 他のゲームの数字（出典で確かめた値だけ。None は「確かめられた数字が無い」）
# 複雑さは Wikipedia「Game complexity」の表（log10 の切り上げ。表自身が「目安として扱う」と注意している）
WIKI_GC = "https://en.wikipedia.org/wiki/Game_complexity"
OTHER_GAMES = [
    {
        "game": ("チェス", "Chess"),
        "first": (
            "白（先手）の得点率 約55%（勝37.5%・引分34.9%・負27.6%）",
            "White scores about 55% (W 37.5%, D 34.9%, L 27.6%)",
        ),
        "first_src": "https://en.wikipedia.org/wiki/First-move_advantage_in_chess",
        "luck": ("なし", "None"),
        "branch": 35,
        "tree": 123,
        "ai": (
            "1997年 Deep Blue が世界王者カスパロフに3½–2½",
            "1997: Deep Blue beat world champion Kasparov 3½–2½",
        ),
        "ai_src": "https://en.wikipedia.org/wiki/Deep_Blue_versus_Garry_Kasparov",
    },
    {
        "game": ("囲碁", "Go"),
        "first": (
            "黒（先手）に有利なので白にコミ6目半（日本）を足す。コミ5目半の時代、黒の勝率は51.855%",
            "Black moves first, so White gets 6.5 points of komi (Japan). With 5.5 komi Black won 51.855%",
        ),
        "first_src": "https://en.wikipedia.org/wiki/Komi_(Go)",
        "luck": ("なし", "None"),
        "branch": 250,
        "tree": 505,
        "ai": ("2016年 AlphaGo がイ・セドルに4勝1敗", "2016: AlphaGo beat Lee Sedol 4–1"),
        "ai_src": "https://en.wikipedia.org/wiki/AlphaGo_versus_Lee_Sedol",
    },
    {
        "game": ("将棋", "Shogi"),
        "first": None,
        "first_src": None,
        "luck": ("なし", "None"),
        "branch": 92,
        "tree": 226,
        "ai": (
            "2017年 Ponanza が佐藤天彦名人に2連勝",
            "2017: Ponanza beat Meijin Amahiko Sato 2–0",
        ),
        "ai_src": "https://en.wikipedia.org/wiki/Computer_shogi",
    },
    {
        "game": ("オセロ", "Othello"),
        "first": (
            "双方が最善なら引き分け（2023年に解明）",
            "A draw with perfect play (solved in 2023)",
        ),
        "first_src": "https://arxiv.org/abs/2310.19387",
        "luck": ("なし", "None"),
        "branch": 10,
        "tree": 58,
        "ai": ("2023年 完全に解かれた（引き分け）", "2023: solved (a draw)"),
        "ai_src": "https://en.wikipedia.org/wiki/Reversi",
    },
    {
        "game": ("チェッカー", "Checkers"),
        "first": (
            "双方が最善なら引き分け（2007年に解明）",
            "A draw with perfect play (solved in 2007)",
        ),
        "first_src": "https://en.wikipedia.org/wiki/Game_complexity",
        "luck": ("なし", "None"),
        "branch": 2.8,
        "tree": 40,
        "ai": ("2007年 完全に解かれた（引き分け）", "2007: solved (a draw)"),
        "ai_src": "https://en.wikipedia.org/wiki/Game_complexity",
    },
    {
        "game": ("バックギャモン", "Backgammon"),
        "first": None,
        "first_src": None,
        "luck": ("サイコロ", "Dice"),
        "branch": 250,
        "tree": 144,
        "ai": (
            "1990年代 TD-Gammon がニューラルネットで自己学習",
            "1990s: TD-Gammon taught itself with a neural net",
        ),
        "ai_src": "https://en.wikipedia.org/wiki/Backgammon",
    },
    {
        "game": ("ポーカー（2人）", "Poker (heads-up)"),
        "first": None,
        "first_src": None,
        "luck": ("配られる札（相手の札は見えない）", "Cards dealt (hidden hands)"),
        "branch": None,
        "tree": None,
        "ai": ("2017年 Libratus がトップのプロ4人に勝利", "2017: Libratus beat four top pros"),
        "ai_src": "https://en.wikipedia.org/wiki/Libratus",
    },
]


def pct(x: float, nd: int = 1) -> str:
    return f"{x * 100:.{nd}f}%"


def signed(x: float, nd: int = 1) -> str:
    return f"{x:+.{nd}f}"


def tile_thumb(tid: str, S: int = 40) -> str:
    v = TS.types[TS.index[tid]].variants[0]
    return f'<svg viewBox="0 0 {S} {S}" width="{S}" height="{S}" aria-hidden="true">{tile_svg(v, 0, 0, S)}</svg>'


# ---------- 図 ----------


def record_bar(fp: dict, lang: str) -> str:
    """先手勝ち・引き分け・後手勝ちの割合（横に1本）。"""
    n = fp["games"]
    parts = [
        (fp["wins"] / n, "b-first", ("先手の勝ち", "First wins")),
        (fp["draws"] / n, "b-draw", ("引き分け", "Draws")),
        (fp["losses"] / n, "b-second", ("後手の勝ち", "Second wins")),
    ]
    li = 0 if lang == "ja" else 1
    W, H = 480, 116
    out = [
        f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{parts[0][2][li]} {pct(parts[0][0])}">'
    ]
    x = 0.0
    for frac, cls, name in parts:
        w = frac * W
        out.append(
            f'<rect x="{x + 1:.1f}" y="0" width="{max(w - 2, 0):.1f}" height="44" rx="4" class="{cls}"><title>{name[li]} {pct(frac)}</title></rect>'
        )
        x += w
    # 数値は下に、左（先手）と右（後手）だけ書く（引き分けは細いので凡例に回す）
    out.append(f'<text x="2" y="74" class="val">{parts[0][2][li]} {pct(parts[0][0])}</text>')
    out.append(f'<text x="2" y="104" class="tick">{parts[1][2][li]} {pct(parts[1][0])}</text>')
    out.append(
        f'<text x="{W - 2}" y="74" text-anchor="end" class="val">{parts[2][2][li]} {pct(parts[2][0])}</text>'
    )
    out.append("</svg>")
    return "".join(out)


def line_chart(
    series, ymax, ystep, xlabel, ylabel, lang, aria, legend_right=False, end_label=None
) -> str:
    """series: [(名前, cls, [値...])]。横軸は手数（0始まり）。end_label を渡すと、最後の値を「終了」として描く。"""
    W, H, L, R, T, B = 480, 300, 40, 12, 14, 58
    n = max(len(s[2]) for s in series)

    def px(i):
        return L + i / (n - 1) * (W - L - R)

    def py(v):
        return T + (1 - v / ymax) * (H - T - B)

    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{aria}">']
    v = 0
    while v <= ymax + 1e-9:
        y = py(v)
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end" class="tick">{v:g}</text>')
        v += ystep
    for i in range(0, n - (1 if end_label else 0), 10):
        out.append(
            f'<text x="{px(i):.1f}" y="{H - B + 22}" text-anchor="middle" class="tick">{i + 1}</text>'
        )
    if end_label:
        out.append(
            f'<text x="{px(n - 1):.1f}" y="{H - B + 22}" text-anchor="end" class="tick">{end_label}</text>'
        )
    out.append(
        f'<text x="{(L + W - R) / 2}" y="{H - 8}" text-anchor="middle" class="axis">{xlabel}</text>'
    )
    for name, cls, vals in series:
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(vals))
        out.append(f'<polyline points="{pts}" class="ln {cls}" fill="none"/>')
        marks = list(range(9, len(vals), 10)) + ([len(vals) - 1] if end_label else [])
        for i in marks:  # 10手ごと（と終了時）に点を打ち、触ると値が出る
            out.append(
                f'<circle cx="{px(i):.1f}" cy="{py(vals[i]):.1f}" r="5" class="pt {cls}"><title>{name}: {i + 1}{"手目" if lang == "ja" else ""} {vals[i]:.1f}</title></circle>'
            )
    # 凡例（左上）
    ly = T  # 右上（legend_right）か左上
    lx = (W - R - 150) if legend_right else L
    for k, (name, cls, _v) in enumerate(series):
        y = ly + 16 + k * 26
        out.append(
            f'<line x1="{lx + 14}" x2="{lx + 44}" y1="{y - 5}" y2="{y - 5}" class="ln {cls}"/>'
        )
        out.append(f'<text x="{lx + 52}" y="{y}" class="leg">{name}</text>')
    if ylabel:
        out.append(
            f'<text x="{lx + 14}" y="{ly + 16 + len(series) * 26}" class="tick">{ylabel}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def hbars(rows, maxv, unit, aria, cls="b-main", label_w=120) -> str:
    """rows: [(ラベル, 値, 表示文字列)]。横棒1本ずつ。"""
    W, rowh, R = 480, 36, 64
    L = label_w
    H = rowh * len(rows) + 4
    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{aria}">']
    for i, (label, v, txt) in enumerate(rows):
        y = i * rowh + 4
        w = max(v, 0) / maxv * (W - L - R)
        out.append(
            f'<text x="{L - 10}" y="{y + 19}" text-anchor="end" class="rowlbl">{label}</text>'
        )
        out.append(
            f'<rect x="{L}" y="{y}" width="{w:.1f}" height="26" rx="3" class="{cls}"><title>{label} {txt}</title></rect>'
        )
        out.append(f'<text x="{L + w + 8:.1f}" y="{y + 19}" class="val">{txt}{unit}</text>')
    out.append("</svg>")
    return "".join(out)


def stacked_sources(src: dict, lang: str) -> str:
    """得点源ごとの点（1人1局あたり）を、途中で完成した分と終了時の分に分けて横棒で。"""
    li = 0 if lang == "ja" else 1
    W, rowh, L, R, top = 480, 40, 90, 56, 40
    total_share = {k: src[k]["share"] for k in KINDS}
    maxv = max(src[k]["per_game"] for k in KINDS)
    H = top + rowh * 4
    names = (
        ("途中で完成した点", "Scored when completed"),
        ("ゲーム終了時の点", "Scored at game end"),
    )
    out = [
        f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{names[0][li]} / {names[1][li]}">'
    ]
    for k, (nm, cls) in enumerate(((names[0][li], "b-main"), (names[1][li], "b-end"))):
        x = L + k * 190
        out.append(f'<rect x="{x}" y="6" width="20" height="20" rx="3" class="{cls}"/>')
        out.append(f'<text x="{x + 28}" y="22" class="leg">{nm}</text>')
    for i, k in enumerate(KINDS):
        s = src[k]
        y = top + i * rowh
        pg = s["per_game"]
        end_part = pg * (s["share_end"] / total_share[k]) if total_share[k] else 0
        mid_part = pg - end_part
        sc = (W - L - R) / maxv
        out.append(
            f'<text x="{L - 10}" y="{y + 20}" text-anchor="end" class="rowlbl">{KIND[lang][k]}</text>'
        )
        out.append(
            f'<rect x="{L}" y="{y}" width="{max(mid_part * sc - 1, 0):.1f}" height="28" rx="3" class="b-main"><title>{KIND[lang][k]} {names[0][li]} {mid_part:.1f}</title></rect>'
        )
        out.append(
            f'<rect x="{L + mid_part * sc + 1:.1f}" y="{y}" width="{max(end_part * sc - 1, 0):.1f}" height="28" rx="3" class="b-end"><title>{KIND[lang][k]} {names[1][li]} {end_part:.1f}</title></rect>'
        )
        out.append(f'<text x="{L + pg * sc + 8:.1f}" y="{y + 20}" class="val">{pg:.1f}</text>')
    out.append("</svg>")
    return "".join(out)


def margin_hist(sc: dict, lang: str) -> str:
    hist = sc["margin_hist"]
    n = sum(hist)
    W, H, L, R, T, B = 480, 240, 10, 10, 10, 56
    bw = (W - L - R) / len(hist)
    mx = max(hist) / n
    out = [
        f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{"点差の分布" if lang == "ja" else "Distribution of final margins"}">'
    ]
    for i, c in enumerate(hist):
        f = c / n
        h = f / mx * (H - T - B)
        x = L + i * bw
        lab = f"{i * 5}–{i * 5 + 4}" if i < len(hist) - 1 else f"{i * 5}+"
        out.append(
            f'<rect x="{x + 2:.1f}" y="{H - B - h:.1f}" width="{bw - 4:.1f}" height="{h:.1f}" rx="3" class="b-main"><title>{lab}: {pct(f)}</title></rect>'
        )
        if i % 2 == 0:
            out.append(
                f'<text x="{x + bw / 2:.1f}" y="{H - B + 20}" text-anchor="middle" class="tick">{lab}</text>'
            )
    out.append(
        f'<text x="{(L + W - R) / 2}" y="{H - 8}" text-anchor="middle" class="axis">{"勝者と敗者の点差" if lang == "ja" else "Winning margin (points)"}</text>'
    )
    out.append("</svg>")
    return "".join(out)


# ---------- 表 ----------


def tile_table(tiles: list[dict], lang: str) -> str:
    li = 0 if lang == "ja" else 1
    mx = max(t["value"] for t in tiles)
    rows = []
    for t in tiles:
        w = max(t["value"], 0) / mx * 100
        count = TS.types[TS.index[t["tile"]]].count
        rows.append(
            f'<tr><td class="tile">{tile_thumb(t["tile"])}<span>{TILE_NAME[t["tile"]][li]}'
            f"<small>×{count}</small></span></td>"
            f'<td class="bar"><span class="bv" style="width:{w:.0f}%"></span><b>{t["value"]:+.1f}</b></td></tr>'
        )
    head = (
        ("タイル", "引いた人の得（点）") if lang == "ja" else ("Tile", "Gain for the drawer (pts)")
    )
    return (
        f'<div class="tablewrap"><table class="tiles"><thead><tr><th>{head[0]}</th><th>{head[1]}</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def ladder_table(ladder: list[dict], lang: str) -> str:
    li = 0 if lang == "ja" else 1
    head = (
        ("強い側", "弱い側", "局数", "強い側の勝率", "弱い側が勝った割合", "平均点差", "チェスなら")
        if lang == "ja"
        else (
            "Stronger",
            "Weaker",
            "Games",
            "Stronger scores",
            "Upsets",
            "Avg margin",
            "Chess Elo gap",
        )
    )
    rows = []
    for r in ladder:
        elo = "—" if r["elo"] is None else f"{r['elo']:+.0f}"
        cells = [LEVEL[r["weak"]][li], str(r["games"]), pct(r["score"]), pct(r["upset"]),
                 f"{r['mean_diff']:+.1f}", elo]  # fmt: skip
        rows.append(
            f"<tr><th>{LEVEL[r['strong']][li]}</th>"
            + "".join(
                f'<td data-label="{h}"><span>{c}</span></td>' for h, c in zip(head[1:], cells)
            )
            + "</tr>"
        )
    return (
        '<div class="tablewrap"><table class="cards"><thead><tr>'
        + "".join(f"<th>{h}</th>" for h in head)
        + f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


RULE = {
    "base": ("いまのルール（71枚・調整なし）", "Current rules (71 tiles, no adjustment)"),
    "komi4": ("後手に最初から4点（コミ4点）", "Second player starts with 4 points (komi 4)"),
    "tiles70": ("1枚伏せて70枚に（2人とも35枚ずつ）", "Remove 1 tile face-down (35 tiles each)"),
}


def fair(st: dict, rule: str) -> dict | None:
    rows = [r for r in st["fairness"]["played"] if r["rule"] == rule]
    return rows[0] if rows else None


def balanced(r: dict) -> bool:
    """先手の勝率の95%区間に50%が入るか（先後の差が検出されないか）。"""
    return r["ci"][0] <= 0.5 <= r["ci"][1]


def fairness_table(st: dict, lang: str) -> str:
    li = 0 if lang == "ja" else 1
    head = (
        ("ルール", "局数", "先手の勝率", "95%の範囲", "先手の平均点差")
        if lang == "ja"
        else ("Rule", "Games", "First player scores", "95% interval", "First player's avg margin")
    )
    rows = []
    for r in st["fairness"]["played"]:
        cells = [f"{r['games']:,}", pct(r["score"]), f"{pct(r['ci'][0])}–{pct(r['ci'][1])}",
                 f"{r['mean_diff']:+.1f}"]  # fmt: skip
        rows.append(
            f"<tr><th>{RULE[r['rule']][li]}</th>"
            + "".join(f'<td data-label="{h}"><span>{c}</span></td>' for h, c in zip(head[1:], cells))
            + "</tr>"
        )
    return (
        '<div class="tablewrap"><table class="cards"><thead><tr>'
        + "".join(f"<th>{h}</th>" for h in head)
        + f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def fairness_texts(st: dict, lang: str) -> dict[str, str]:
    """ルール変更の結果の文。勝率の区間に50%が入るかで言い方を変える。"""
    ja = lang == "ja"
    out = {}
    for rule in ("komi4", "tiles70"):
        r = fair(st, rule)
        name = RULE[rule][0 if ja else 1]
        if r is None:
            out[rule] = ""
            continue
        s, d = pct(r["score"]), f"{r['mean_diff']:+.1f}"
        if balanced(r):
            out[rule] = (
                f"「{name}」では先手の勝率が{s}（平均点差{d}）になり、先後の差は誤差の範囲に収まりました。"
                if ja
                else f"With “{name}”, the first player scored {s} (average margin {d}); the gap is within the margin of error."
            )
        elif r["score"] > 0.5:
            out[rule] = (
                f"「{name}」では先手の勝率が{s}（平均点差{d}）で、差は縮みましたが先手がまだ有利です。"
                if ja
                else f"With “{name}”, the first player scored {s} (average margin {d}): the gap shrank, but the first player is still ahead."
            )
        else:
            out[rule] = (
                f"「{name}」では先手の勝率が{s}（平均点差{d}）で、今度は後手が有利になりすぎました。"
                if ja
                else f"With “{name}”, the first player scored {s} (average margin {d}): now the second player is too far ahead."
            )
    return out


def games_table(st: dict, lang: str) -> str:
    li = 0 if lang == "ja" else 1
    cx, fp = st["complexity"], st["first_player"]
    head = (
        ("ゲーム", "先手の有利さ", "運の要素", "1手の選択肢", "ゲーム木の大きさ", "AIの到達点")
        if lang == "ja"
        else (
            "Game",
            "First-move advantage",
            "Luck",
            "Choices per move",
            "Game-tree size",
            "AI milestone",
        )
    )
    car = (
        (
            "カルカソンヌ",
            f"先手の勝率 {pct(fp['score'])}（このページの測定）",
            "引くタイルの順番（全員に見える）",
            f"約{cx['legal_mean']:.0f}（測定）",
            f"10<sup>{cx['tree_log10']:.0f}</sup>（測定・山札の分岐を除く）",
            "人間のトップに勝ったという公開の記録はまだ無い",
        )
        if lang == "ja"
        else (
            "Carcassonne",
            f"First player scores {pct(fp['score'])} (measured here)",
            "Order of the tiles drawn (public)",
            f"about {cx['legal_mean']:.0f} (measured)",
            f"10<sup>{cx['tree_log10']:.0f}</sup> (measured, draws excluded)",
            "No public record of beating top humans yet",
        )
    )
    rows = [
        '<tr class="me">'
        + f"<th>{car[0]}</th>"
        + "".join(f'<td data-label="{h}"><span>{c}</span></td>' for h, c in zip(head[1:], car[1:]))
        + "</tr>"
    ]
    for g in OTHER_GAMES:
        first = (
            "—"
            if g["first"] is None
            else f'{g["first"][li]} <a href="{g["first_src"]}" class="src">[*]</a>'
        )
        branch = "—" if g["branch"] is None else f"{g['branch']:g}"
        tree = "—" if g["tree"] is None else f"10<sup>{g['tree']}</sup>"
        ai = f'{g["ai"][li]} <a href="{g["ai_src"]}" class="src">[*]</a>'
        cells = [first, g["luck"][li], branch, tree, ai]
        rows.append(
            f"<tr><th>{g['game'][li]}</th>"
            + "".join(
                f'<td data-label="{h}"><span>{c}</span></td>' for h, c in zip(head[1:], cells)
            )
            + "</tr>"
        )
    return (
        '<div class="tablewrap wide"><table class="games cards"><thead><tr>'
        + "".join(f"<th>{h}</th>" for h in head)
        + f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


# ---------- 言い切りの確かめ ----------


def failed_claims(st: dict) -> list[str]:
    src, tr, mp, tiles = st["sources"], st["trajectory"], st["meeples"], st["tiles"]
    bad = []
    if max(KINDS, key=lambda k: src[k]["share"]) != "C":
        bad.append("都市がいちばんの得点源")
    if max(("C", "R", "M"), key=lambda k: src[k]["unfinished_rate"]) != "M":
        bad.append("修道院がいちばん未完成で終わりやすい")
    if not 0.3 <= src["end_share"] <= 0.55:
        bad.append("終了時の点が全体の3〜5割")
    if max(KINDS, key=lambda k: mp["kind_share"][k]) != "C":
        bad.append("ミープルをいちばん多く置く場所は都市")
    if not all(a["proj"] < b["proj"] for a, b in zip(tr["lead_wins"], tr["lead_wins"][1:])):
        bad.append("終盤ほどリードしている側が勝ちやすい")
    if tiles[0]["tile"] not in ("chapel", "chapel_with_road"):
        bad.append("修道院のタイルがいちばん得")
    if tr["comeback15"]["rate"] is None or not tr["comeback15"]["rate"] > 0.05:
        bad.append("15点差からの逆転がそれなりにある")
    fp, sc, cx = st["first_player"], st["scores"], st["complexity"]
    if not 0 < fp["mean_diff"] < 5:
        bad.append("先手の平均点差はプラスで数点（後手で数点負けはほぼ互角）")
    if not 0.53 <= fp["score"] <= 0.62:
        bad.append("先手の有利さはチェス（約55%）と同じくらいかやや大きめ")
    if not sc["close10"] >= 1 / 3:
        bad.append("3局に1局以上が10点差以内")
    if not tr["lead_wins"][0]["proj"] < 0.7:
        bad.append("序盤のリードはあまり当てにならない")
    if not 0.4 <= src["M"]["unfinished_rate"] <= 0.6:
        bad.append("修道院は半分近くが未完成で終わる")
    if not mp["per_game"] >= 14:
        bad.append("ミープルは7個なのに倍以上置く")
    if not cx["legal_mean"] > 35:
        bad.append("選べる手の多さはチェス（35）以上")
    if not 110 <= cx["tree_log10"] <= 140:
        bad.append("ゲーム木の大きさはチェス（10^123）と同じくらい")
    weak = {t["tile"] for t in tiles[-len(tiles) // 3 :]}
    if not {"straight_road", "bent_road"} & weak:
        bad.append("数が多い道のタイルは1枚の価値が小さい")
    sg = [r for r in st["ladder"] if (r["strong"], r["weak"]) == ("standard", "greedy")]
    if sg and not sg[0]["upset"] < 0.25:
        bad.append("標準が目先の点だけのAIに負けるのは少しだけ")
    sim = {k["komi"]: k["score"] for k in st["fairness"]["komi_sim"]}
    if not (sim[3] > 0.51 and sim[5] < 0.49):
        bad.append("試算で3点では足りず、5点では後手が有利")
    k4, t70 = fair(st, "komi4"), fair(st, "tiles70")
    if k4 is None or not balanced(k4):
        bad.append("コミ4点で先後の差が誤差の範囲に収まる（9節の「学び」）")
    if t70 is None or not balanced(t70) or abs(t70["mean_diff"]) > 1.5:
        bad.append("1枚抜いて枚数をそろえると先後の差がほぼ消える（1節・9節）")
    return bad


def check_claims(st: dict) -> None:
    bad = failed_claims(st)
    if bad:
        raise SystemExit(
            "集計値が本文の言い切りと合いません。scripts/build_stats_page.py の本文を直してください:\n  "
            + "\n  ".join(bad)
        )


# ---------- 文（数値入り） ----------


def texts(st: dict, lang: str) -> dict[str, str]:
    fp, sc, src, tr, mp, cx, dl = (
        st["first_player"], st["scores"], st["sources"], st["trajectory"],
        st["meeples"], st["complexity"], st["deck_luck"],
    )  # fmt: skip
    half = tr["lead_wins"][1]
    late = tr["lead_wins"][2]
    early = tr["lead_wins"][0]
    sig = fp["ci"][0] > 0.5
    top3 = st["tiles"][:3]
    low3 = st["tiles"][-3:]
    li = 0 if lang == "ja" else 1

    def names(ts: list[dict]) -> str:
        return ("、" if li == 0 else ", ").join(TILE_NAME[t["tile"]][li] for t in ts)

    first_tiles = (
        71 + 1
    ) // 2  # 開始タイルを除く71枚を交互に置く（置けずに捨てるタイルが無ければ）
    ld = {r["strong"] + "-" + r["weak"]: r for r in st["ladder"]}
    std_greedy = ld.get("standard-greedy")
    t = {
        "ai": st["ai"]["name"],
        "date": st["ai"]["date"],
        "games": f"{fp['games']:,}",
        "decks": f"{dl['pairs']:,}",
        "fp_score": pct(fp["score"]),
        "fp_diff": f"{fp['mean_diff']:+.1f}",
        "fp_se": f"{fp['se_diff']:.1f}",
        "fp_p": "p < 0.001" if fp["p_value"] < 0.001 else f"p = {fp['p_value']:.2g}",
        "draw": pct(fp["draw_rate"]),
        "first_tiles": str(first_tiles),
        "second_tiles": str(71 - first_tiles),
        "mean": f"{sc['mean']:.0f}",
        "win_mean": f"{sc['winner_mean']:.0f}",
        "lose_mean": f"{sc['loser_mean']:.0f}",
        "margin_med": f"{sc['margin_median']:.0f}",
        "close5": pct(sc["close5"], 0),
        "close10": pct(sc["close10"], 0),
        "end_share": pct(src["end_share"], 0),
        "city_share": pct(src["C"]["share"], 0),
        "field_share": pct(src["F"]["share"], 0),
        "unf_C": pct(src["C"]["unfinished_rate"], 0),
        "unf_R": pct(src["R"]["unfinished_rate"], 0),
        "unf_M": pct(src["M"]["unfinished_rate"], 0),
        "lead_early": pct(early["proj"], 0),
        "lead_half": pct(half["proj"], 0),
        "lead_late": pct(late["proj"], 0),
        "ply_early": str(early["ply"]),
        "ply_half": str(half["ply"]),
        "ply_late": str(late["ply"]),
        "comeback": pct(tr["comeback15"]["rate"], 0),
        "lead_changes": f"{tr['lead_changes_mean']:.0f}",
        "m_per_game": f"{mp['per_game']:.0f}",
        "m_rate": pct(mp["place_rate"], 0),
        "m_C": pct(mp["kind_share"]["C"], 0),
        "m_R": pct(mp["kind_share"]["R"], 0),
        "m_M": pct(mp["kind_share"]["M"], 0),
        "m_F": pct(mp["kind_share"]["F"], 0),
        "m_empty": pct(mp["empty_rate"], 0),
        "m_stuck": f"{mp['unfinished_at_end']:.1f}",
        "farmers": f"{mp['farmers_scored']:.1f}",
        "top_tiles": names(top3),
        "low_tiles": names(low3),
        "legal": f"{cx['legal_mean']:.0f}",
        "legal_max": f"{cx['legal_max']}",
        "places": f"{cx['places_mean']:.0f}",
        "kinds": f"{cx['kinds_mean']:.0f}",
        "tree": f"{cx['tree_log10']:.0f}",
        "tree_chance": f"{cx['tree_with_chance_log10']:.0f}",
        "same_winner": pct(dl["same_winner"], 0),
        "deck_corr": pct(dl["diff_corr"], 0),
        "sg_upset": pct(std_greedy["upset"], 0) if std_greedy else "—",
        "sg_score": pct(std_greedy["score"], 0) if std_greedy else "—",
    }
    if lang == "ja":
        t |= {
            "fp_ci": f"{pct(fp['ci'][0])}〜{pct(fp['ci'][1])}",
            "fp_record": f"先手{fp['wins']:,}勝・後手{fp['losses']:,}勝・引き分け{fp['draws']:,}",
            "fp_verdict": "先手がはっきり有利です（偶然でこれだけ偏る確率は小さい）。"
            if sig
            else "先手が有利そうですが、偶然の範囲を出るほどではありません。",
        }
    else:
        t |= {
            "fp_ci": f"{pct(fp['ci'][0])}–{pct(fp['ci'][1])}",
            "fp_record": f"first player {fp['wins']:,} wins, second player {fp['losses']:,} wins, {fp['draws']:,} draws",
            "fp_verdict": "The first player has a clear edge (very unlikely to be chance)."
            if sig
            else "The first player seems to have an edge, but it is within the range of chance.",
        }
    # 図と表
    ja = lang == "ja"
    t["chart_record"] = record_bar(fp, lang)
    t["chart_margin"] = margin_hist(sc, lang)
    t["chart_sources"] = stacked_sources(src, lang)
    t["chart_unfinished"] = hbars(
        [(KIND[lang][x], src[x]["unfinished_rate"] * 100, f"{src[x]['unfinished_rate'] * 100:.0f}") for x in ("C", "R", "M")],
        100, "%", "未完成で終わった割合" if ja else "Share left unfinished", label_w=100,
    )  # fmt: skip
    curve = tr["curve"]["score"]
    t["chart_score"] = line_chart(
        [
            ("先手" if ja else "First player", "s-first", [c[0] for c in curve]),
            ("後手" if ja else "Second player", "s-second", [c[1] for c in curve]),
        ],
        110, 10, "手数（2人合わせて何枚目のタイルか）" if ja else "Tile number (both players combined)",
        "平均の確定点" if ja else "Average banked score", lang,
        "手数ごとの平均得点" if ja else "Average score by turn",
        end_label="終了" if ja else "End",
    )  # fmt: skip
    t["chart_lead"] = hbars(
        [
            (
                (f"{b['from']}〜{b['to']}点" if b["to"] is not None else f"{b['from']}点以上")
                if ja
                else (f"{b['from']}–{b['to']} pts" if b["to"] is not None else f"{b['from']}+ pts"),
                b["win"] * 100,
                f"{b['win'] * 100:.0f}",
            )
            for b in tr["by_lead_half"]
        ],
        100, "%", "折り返し時点のリードと勝率" if ja else "Lead at halftime vs. win rate", label_w=120,
    )  # fmt: skip
    sup = mp["supply_curve"]
    t["chart_supply"] = line_chart(
        [
            ("先手" if ja else "First player", "s-first", [c[0] for c in sup]),
            ("後手" if ja else "Second player", "s-second", [c[1] for c in sup]),
        ],
        7, 1, "手数（2人合わせて何枚目のタイルか）" if ja else "Tile number (both players combined)",
        "手持ちのミープル" if ja else "Meeples in hand", lang,
        "手持ちミープルの推移" if ja else "Meeples in hand over the game",
        legend_right=True,
    )  # fmt: skip
    t["chart_mkind"] = hbars(
        [(KIND[lang][x], mp["kind_share"][x] * 100, f"{mp['kind_share'][x] * 100:.0f}") for x in KINDS],
        100, "%", "ミープルを置いた場所" if ja else "Where meeples were placed", label_w=100,
    )  # fmt: skip
    t["table_tiles"] = tile_table(st["tiles"], lang)
    t["table_ladder"] = ladder_table(st["ladder"], lang)
    t["table_games"] = games_table(st, lang)
    t["table_fair"] = fairness_table(st, lang)
    ft = fairness_texts(st, lang)
    t["fair_komi"], t["fair_tiles"] = ft["komi4"], ft["tiles70"]
    t["fair_games"] = f"{min(r['games'] for r in st['fairness']['played']):,}"
    t["chart_komi"] = hbars(
        [
            ((f"{k['komi']}点" if ja else f"{k['komi']} pts"), k["score"] * 100, f"{k['score'] * 100:.1f}")
            for k in st["fairness"]["komi_sim"]
        ],
        100, "%", "後手の加点と先手の勝率（試算）" if ja else "Points given to the second player vs. first player's score (estimate)",
        label_w=70,
    )  # fmt: skip
    return t


def fill(html: str, t: dict) -> str:
    for key, val in t.items():
        html = html.replace("{{" + key + "}}", val)
    if "{{" in html:
        i = html.index("{{")
        raise SystemExit(f"置き換え忘れ: {html[i : i + 40]}")
    return html


def main() -> None:
    st = json.loads(STATS.read_text(encoding="utf-8"))
    check_claims(st)
    tpl = (ROOT / "web" / "stats_template.html").read_text(encoding="utf-8")
    base = (
        tpl.replace("__NAV_CSS__", NAV_CSS)
        .replace("__NAV__", nav_html("stats.html"))
        .replace("__SUPPORT__", support_html())
    )
    ja = fill(base, texts(st, "ja"))
    en = to_english_page(
        base, "stats.html", "stats", nav_html("stats.html"), nav_html("stats.html", "en")
    )
    en = fill(en, texts(st, "en"))
    write_pair("stats.html", ja, en)
    print(f"docs/stats.html と docs/en/stats.html を書き出しました（{len(ja) // 1024} KB）")


if __name__ == "__main__":
    main()
