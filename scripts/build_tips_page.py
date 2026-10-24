"""集計結果と図版から、初心者向けの「強いAIに学ぶコツ」ページ（docs/ai_tips.html）を組み立てる。

例:
    py scripts/build_tips_page.py
入力: runs/habits_summary.json（summarize_habits.py）、runs/habits_examples.json（pick_examples.py）、
      web/ai_tips_template.html。本文の数値はテンプレートの {{key}} を集計値で置き換える。
      runs/ に無ければ、コミット済みの docs/results/ の同名ファイルを使う（再集計せずに文面だけ直せる）。

本文の「〜より多い」「半分以上」などの言い切りは、集計値で確かめてから書き出す（check_claims）。
最新AIで集計し直して傾向が変わったら、ここで止まるので、テンプレートの文を直す。
図の説明文（cap_*）は、選んだ局面の記録から組み立てる（局面が変わっても説明がずれない）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from site_nav import NAV_CSS, nav_html

ROOT = Path(__file__).resolve().parents[1]


def line_chart(strong: dict, greedy: dict) -> str:
    """手持ちミープル数の推移（横軸=残りタイル枚数、左が序盤）。"""
    W, H, L, R, T, B = 640, 320, 48, 16, 16, 62
    xs = sorted((int(k) for k in strong), reverse=True)
    x0, x1 = max(xs), min(xs)

    def px(v):
        return L + (x0 - v) / (x0 - x1) * (W - L - R)

    def py(v):
        return T + (1 - v / 7) * (H - T - B)

    out = [
        f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="手持ちミープル数の推移">'
    ]
    for v in range(8):
        y = py(v)
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end" class="tick">{v}</text>')
    for v in (70, 60, 50, 40, 30, 20, 10, 2):
        x = px(v)
        out.append(
            f'<text x="{x:.1f}" y="{H - B + 26}" text-anchor="middle" class="tick">{v}</text>'
        )
    out.append(
        f'<text x="{(L + W - R) / 2}" y="{H - 6}" text-anchor="middle" class="axis">山札の残り枚数（左が序盤）</text>'
    )
    for data, cls in ((greedy, "s-greedy"), (strong, "s-strong")):
        pts = " ".join(
            f"{px(int(k)):.1f},{py(v):.1f}"
            for k, v in sorted(data.items(), key=lambda kv: -int(kv[0]))
        )
        out.append(f'<polyline points="{pts}" class="{cls}" fill="none"/>')
    # 凡例は右上（線は左下に寄るので重ならない。スマホで文字を大きくしても切れない）
    lx = W - R - 250
    for k, (nm, cls, tcls) in enumerate(
        (("強いAI", "s-strong", "lbl-strong"), ("目先の点だけのAI", "s-greedy", "lbl-greedy"))
    ):
        y = T + 14 + k * 32
        out.append(f'<line x1="{lx}" x2="{lx + 34}" y1="{y - 6}" y2="{y - 6}" class="{cls}"/>')
        out.append(f'<text x="{lx + 44}" y="{y}" class="lbl {tcls}">{nm}</text>')
    out.append("</svg>")
    return "".join(out)


def bar_pairs(rows, unit, maxv, aria) -> str:
    """rows: [(ラベル, 強いAIの値, 比較値, 比較名, 強いAIの名前)] を横棒の対で描く。

    棒の名前は上の凡例にまとめ、棒の横には数値だけを書く（スマホで文字を大きくしても収まるように）。
    """
    W, rowh, L, R, top = 640, 64, 100, 96, 40
    H = top + rowh * len(rows) + 4
    aname, bname = rows[0][4], rows[0][3]
    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{aria}">']
    for k, (nm, cls) in enumerate(((aname, "b-strong"), (bname, "b-greedy"))):
        x = L + k * (W - L) / 2
        out.append(f'<rect x="{x:.0f}" y="6" width="22" height="22" rx="3" class="{cls}"/>')
        out.append(f'<text x="{x + 30:.0f}" y="24" class="leg">{nm}</text>')
    for i, (label, a, b, *_names) in enumerate(rows):
        y = top + i * rowh
        out.append(
            f'<text x="{L - 12}" y="{y + 30}" text-anchor="end" class="rowlbl">{label}</text>'
        )
        for j, (v, cls) in enumerate(((a, "b-strong"), (b, "b-greedy"))):
            yy = y + j * 26
            w = v / maxv * (W - L - R)
            out.append(f'<rect x="{L}" y="{yy}" width="{w:.1f}" height="22" rx="2" class="{cls}"/>')
            out.append(f'<text x="{L + w + 8:.1f}" y="{yy + 18}" class="val">{v:.1f}{unit}</text>')
    out.append("</svg>")
    return "".join(out)


def farms_in_phase(s: dict, phase: str) -> float:
    """その局面区分で1人1局あたりに置いた農民の数。"""
    ph = s["by_phase"][phase]
    return ph["kind_rate"]["F"] * ph["moves"] / (s["games"] * 2)


PLAYER = ['<span class="red">赤</span>', '<span class="blue">青</span>']
KIND = {"C": "都市", "R": "道", "M": "修道院", "F": "草原"}


def phase(left: int) -> str:
    return "序盤" if left >= 47 else "中盤" if left >= 24 else "終盤"


def captions(ex: dict) -> dict:
    """図版の説明文（見出し＋本文）を、pick_examples.py が残した局面の記録から作る。"""
    out = {}

    def head(e):
        return f'<span class="k">実戦の例（{phase(e["left"])}・残り{e["left"]}枚）</span>'

    if "skip" in ex:
        e = ex["skip"]
        me = PLAYER[e["mover"]]
        out["cap_skip"] = head(e) + (
            f"{me}はタイルを置きましたが、手元に{e['supply'][0]}個あるミープルは置きませんでした。"
            f"目先の点だけのAIなら同じ置き方で{KIND[e['greedy_kind']]}にミープルを乗せる場面です。"
            "行き先の決まっていない特徴に乗せると、しばらく戻ってきません。"
        )
    if "farm" in ex:
        e = ex["farm"]
        d, o = e["cities_done"], e["cities_open"]
        more = f"未完成の都市も{o}つ接しているので、完成すればさらに3点ずつ増えます。" if o else ""
        out["cap_farm"] = head(e) + (
            f"{PLAYER[e['mover']]}は草原にミープルを置きました（農民）。この草原は完成済みの都市{d}つに"
            f"接していて、置いた時点で{3 * d}点が見込めます。{more}"
        )
    if "merge" in ex:
        e = ex["merge"]
        me, op = PLAYER[e["mover"]], PLAYER[1 - e["mover"]]
        m = e["meeples"]
        if m[0] == m[1]:
            tail = f"赤と青のミープルは{m[0]}個ずつなので、完成すればどちらも満点です。{op}に独り占めさせない一手です。"
        else:
            lead = PLAYER[0 if m[0] > m[1] else 1]
            tail = f"ミープルは赤{m[0]}個・青{m[1]}個なので、完成すれば多い{lead}だけが点をもらいます。"
        out["cap_merge"] = head(e) + (
            f"{me}は自分の都市と{op}の都市をつなぎ、{e['city_tiles']}タイルの都市にしました。{tail}"
        )
    if "block" in ex:
        e = ex["block"]
        me, op = PLAYER[e["mover"]], PLAYER[1 - e["mover"]]
        own = "・".join(KIND[k] for k in e.get("self_blocked", []))
        cost = (
            f"{me}自身の{own}も完成しなくなりますが、相手の都市を止めるほうが得と判断しています。"
            if own
            else ""
        )
        out["cap_block"] = head(e) + (
            f"{me}が置いたタイルで、×のマスは残りの山札のどのタイルでも埋まらなくなりました。"
            f"隣の{op}の都市はもう完成しません。{cost}"
        )
    if "monastery" in ex:
        e = ex["monastery"]
        out["cap_monastery"] = head(e) + (
            f"{PLAYER[e['mover']]}は、自分の修道院の周りの最後の1マスを埋めて完成させ、"
            f"この手で{e['scored'][0]}点を取りました。ミープルは手元に戻り、次の手番でまた使えます。"
        )
    return out


def check_claims(s: dict, g: dict, lead: dict) -> None:
    """テンプレートの言い切りが集計値と合っているか確かめる。合わなければ止める。"""
    farm_early = farms_in_phase(s, "序盤")
    claims = [
        (s["skip_meeple_with_supply"] > g["skip_meeple_with_supply"],
         "#keep: 強いAIは置けるのに置かない手が多い"),
        (s["supply_curve"]["48"] > g["supply_curve"]["48"],
         "#keep: 残り48枚で強いAIの手持ちが多い"),
        (1.0 <= s["supply_curve"]["48"] <= 2.5, "#keep, #recap: 序盤の終わりに1〜2個残る"),
        (s["supply_curve"]["24"] < 1.0, "#keep: 中盤以降は強いAIもほぼ使い切る"),
        (1 - s["road_meeple_new"] >= 0.6, "#road: 道ミープルのほとんどは既存の道に乗せる"),
        (s["meeple_life"]["R"]["turns"] < g["meeple_life"]["R"]["turns"],
         "#road: 道のミープルが早く戻る"),
        (s["city_meeple_new"] >= 0.5, "#city: 都市ミープルの半分以上は新しい都市"),
        (farm_early <= 2.2, "#farm: 農民を序盤に置きすぎない"),
        (s["farm_per_player_game"] < g["farm_per_player_game"],
         "#farm: 強いAIの農民は目先の点だけのAIより少ない"),
        (lead["F"] > 0, "#farm: 勝った側は草原でも多く取る"),
        (s["meeple_life"]["F"]["points"] >= max(s["meeple_life"][k]["points"] for k in "CRM"),
         "#farm: 農民は1個あたりどの置き方より多く稼ぐ"),
        (s["blocks_per_game_player"].get("opp_C", 0)
         > 1.3 * g["blocks_per_game_player"].get("opp_C", 0),
         "#block: 強いAIは相手の都市を止める手をよく指す"),
        (set(sorted(lead, key=lead.get)[-2:]) == {"C", "F"},
         "#citywins, #recap: 勝敗の差が大きい上位2つは都市と草原"),
        (s["touches_opp"] > g["touches_opp"], "#tiles: 強いAIは相手の特徴によく手を出す"),
    ]  # fmt: skip
    bad = [msg for ok, msg in claims if not ok]
    if bad:
        raise SystemExit(
            "集計値が本文の言い切りと合いません。web/ai_tips_template.html の文を直してください:\n  "
            + "\n  ".join(bad)
        )


def _load(name: str) -> dict:
    for d in (ROOT / "runs", ROOT / "docs" / "results"):
        if (d / name).exists():
            return json.loads((d / name).read_text(encoding="utf-8"))
    raise SystemExit(f"{name} が runs/ にも docs/results/ にもありません")


def main() -> None:
    summ = _load("habits_summary.json")
    ex = _load("habits_examples.json")
    s, g = summ["habits_strong"], summ["habits_greedy"]
    kinds = [("C", "都市"), ("R", "道"), ("M", "修道院"), ("F", "草原")]
    charts = {
        "chart_supply": line_chart(s["supply_curve"], g["supply_curve"]),
        "chart_winner": bar_pairs(
            [
                (
                    ja,
                    s["winner_points_by_kind"][k],
                    s["loser_points_by_kind"][k],
                    "負けた側",
                    "勝った側",
                )
                for k, ja in kinds
            ],
            "点",
            50,
            "勝った側と負けた側の、得点源ごとの平均点",
        ),
        "chart_life": bar_pairs(
            [
                (
                    ja,
                    s["meeple_life"][k]["turns"],
                    g["meeple_life"][k]["turns"],
                    "目先の点だけのAI",
                    "強いAI",
                )
                for k, ja in kinds
            ],
            "手",
            32,
            "ミープルが戻るまでの手番数",
        ),
    }
    pct = lambda v: f"{v * 100:.0f}"
    lead = {k: s["winner_points_by_kind"][k] - s["loser_points_by_kind"][k] for k, _ in kinds}
    check_claims(s, g, lead)
    ai = summ.get("ai") or {}
    blk_s = s["blocks_per_game_player"].get("opp_C", 0)
    blk_g = g["blocks_per_game_player"].get("opp_C", 0)
    nums = {
        "games_strong": s["games"],
        "games_greedy": g["games"],
        "avg_score_strong": f"{s['avg_score']:.0f}",
        "avg_score_greedy": f"{g['avg_score']:.0f}",
        "same_as_greedy": pct(s["same_as_greedy"]),
        "differ_from_greedy": pct(1 - s["same_as_greedy"]),
        "skip_strong": pct(s["skip_meeple_with_supply"]),
        "skip_greedy": pct(g["skip_meeple_with_supply"]),
        "supply48_strong": f"{s['supply_curve']['48']:.1f}",
        "supply48_greedy": f"{g['supply_curve']['48']:.1f}",
        "road_life_strong": f"{s['meeple_life']['R']['turns']:.1f}",
        "road_life_greedy": f"{g['meeple_life']['R']['turns']:.1f}",
        "road_join": pct(1 - s["road_meeple_new"]),
        "road_share_strong": pct(s["meeple_kind_share"]["R"]),
        "road_share_greedy": pct(g["meeple_kind_share"]["R"]),
        "city_new_strong": pct(s["city_meeple_new"]),
        "city_new_greedy": pct(g["city_meeple_new"]),
        "city_share_strong": pct(s["meeple_kind_share"]["C"]),
        "city_share_greedy": pct(g["meeple_kind_share"]["C"]),
        "farm_points": f"{s['meeple_life']['F']['points']:.1f}",
        "farm_turns": f"{s['meeple_life']['F']['turns']:.0f}",
        "farm_zero": pct(s["meeple_life"]["F"]["zero_points"]),
        "farm_per_player": f"{s['farm_per_player_game']:.1f}",
        "farm_per_player_greedy": f"{g['farm_per_player_game']:.1f}",
        "farm_early_strong": f"{farms_in_phase(s, '序盤'):.1f}",
        "farm_total": f"{s['points_by_source']['F_end']:.0f}",
        "farm_share": pct(s["points_by_source"]["F_end"] / s["avg_score"]),
        "mon_points": f"{s['meeple_life']['M']['points']:.1f}",
        "mon_stuck": pct(s["meeple_life"]["M"]["stuck_to_end"]),
        "touch_opp_strong": pct(s["touches_opp"]),
        "touch_opp_greedy": pct(g["touches_opp"]),
        "block_strong": f"{s['blocks_per_game_player'].get('opp_C', 0):.2f}",
        "block_greedy": f"{g['blocks_per_game_player'].get('opp_C', 0):.2f}",
        "block_count_strong": round(blk_s * s["games"] * 2),
        "block_ratio": f"{blk_s / blk_g:.1f}" if blk_g else "何",
        "block_every": f"{1 / blk_s:.0f}" if blk_s else "—",
        "supply24_strong": f"{s['supply_curve']['24']:.1f}",
        "ai_name": ai.get("name", "最強設定のAI"),
        "ai_when": f"、{ai['date']} 採用" if ai.get("date") else "",
        "road_new": pct(s["road_meeple_new"]),
        "shared_share": pct(s["shared_points_share"]),
        "lead_C": f"{lead['C']:.0f}",
        "lead_R": f"{lead['R']:.0f}",
        "lead_M": f"{lead['M']:.0f}",
        "lead_F": f"{lead['F']:.0f}",
        **{f"lead_{k}_signed": f"{v:+.0f}".replace("-", "−") for k, v in lead.items()},
        "farm_mid_strong": f"{farms_in_phase(s, '中盤'):.1f}",
        "farm_late_strong": f"{farms_in_phase(s, '終盤'):.1f}",
        "city_points": f"{s['points_by_source']['C_done'] + s['points_by_source']['C_end']:.0f}",
    }
    for k, v in ex.items():
        nums[f"svg_{k}"] = v["svg"]
    nums.update(captions(ex))
    nums.update(charts)
    nums["site_nav"] = nav_html("ai_tips.html")
    nums["site_nav_css"] = NAV_CSS
    tpl = (ROOT / "web" / "ai_tips_template.html").read_text(encoding="utf-8")

    def sub(m):
        key = m.group(1)
        if key not in nums:
            raise SystemExit(f"テンプレートの未定義キー: {key}")
        return str(nums[key])

    html = re.sub(r"\{\{(\w+)\}\}", sub, tpl)
    out = ROOT / "docs" / "ai_tips.html"
    out.write_text(html, encoding="utf-8")
    print(f"{out} を書き出しました（{len(html) // 1024} KB）")


if __name__ == "__main__":
    main()
