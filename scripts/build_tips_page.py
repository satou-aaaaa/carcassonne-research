"""集計結果と図版から、初心者向けの「強いAIに学ぶコツ」ページ（docs/ai_tips.html）を組み立てる。

例:
    py scripts/build_tips_page.py
入力: runs/habits_summary.json（summarize_habits.py）、runs/habits_examples.json（pick_examples.py）、
      web/ai_tips_template.html。本文の数値はテンプレートの {{key}} を集計値で置き換える。
      runs/ に無ければ、コミット済みの docs/results/ の同名ファイルを使う（再集計せずに文面だけ直せる）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from site_nav import NAV_CSS, nav_html

ROOT = Path(__file__).resolve().parents[1]


def line_chart(strong: dict, greedy: dict) -> str:
    """手持ちミープル数の推移（横軸=残りタイル枚数、左が序盤）。"""
    W, H, L, R, T, B = 640, 300, 44, 16, 16, 44
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
            f'<text x="{x:.1f}" y="{H - B + 18}" text-anchor="middle" class="tick">{v}</text>'
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
    # 直接ラベル
    out.append(
        f'<text x="{px(46) + 8:.1f}" y="{py(strong["46"]) - 8:.1f}" class="lbl lbl-strong">強いAI</text>'
    )
    out.append(
        f'<text x="{px(54) - 8:.1f}" y="{py(greedy["54"]) + 18:.1f}" text-anchor="end" class="lbl lbl-greedy">目先の点だけのAI</text>'
    )
    out.append("</svg>")
    return "".join(out)


def bar_pairs(rows, unit, maxv, aria) -> str:
    """rows: [(ラベル, 強いAIの値, 比較値, 比較名)] を横棒の対で描く。"""
    W, rowh, L, R = 640, 58, 92, 64
    H = rowh * len(rows) + 8
    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{aria}">']
    for i, (label, a, b, bname, aname) in enumerate(rows):
        y = 6 + i * rowh
        out.append(
            f'<text x="{L - 10}" y="{y + 25}" text-anchor="end" class="rowlbl">{label}</text>'
        )
        for j, (v, cls, nm) in enumerate(((a, "b-strong", aname), (b, "b-greedy", bname))):
            yy = y + j * 22
            w = v / maxv * (W - L - R)
            out.append(f'<rect x="{L}" y="{yy}" width="{w:.1f}" height="18" rx="2" class="{cls}"/>')
            out.append(
                f'<text x="{L + w + 6:.1f}" y="{yy + 14}" class="val">{v:.1f}{unit}<tspan class="valname"> {nm}</tspan></text>'
            )
    out.append("</svg>")
    return "".join(out)


def farms_in_phase(s: dict, phase: str) -> float:
    """その局面区分で1人1局あたりに置いた農民の数。"""
    ph = s["by_phase"][phase]
    return ph["kind_rate"]["F"] * ph["moves"] / (s["games"] * 2)


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
        "block_count_strong": round(s["blocks_per_game_player"].get("opp_C", 0) * s["games"] * 2),
        "shared_share": pct(s["shared_points_share"]),
        "lead_C": f"{lead['C']:.0f}",
        "lead_R": f"{lead['R']:.0f}",
        "lead_M": f"{lead['M']:.0f}",
        "lead_F": f"{lead['F']:.0f}",
        "city_points": f"{s['points_by_source']['C_done'] + s['points_by_source']['C_end']:.0f}",
    }
    for k, v in ex.items():
        nums[f"svg_{k}"] = v["svg"]
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
