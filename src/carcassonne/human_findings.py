"""人との対局（送ってもらった棋譜）から分かったことの集計。「みんなの対局」ページの研究ノートの元。

人の手を1手ずつ最強AIで採点し（対戦ページの「ヒント」と同じ `webplay.make_coach`）、
損した手（悪手）がどんな種類・どの時期に多いかを数える。AIの側は、人が勝った局と、
人の手でAIの見積もりが大きく外れた局面（`human_games.swings`）を数える。

採点は1局で数十秒かかるので、局ごとの結果を docs/results/human_findings_cache.json に覚えておき（1局1行）、
新しく届いた局だけ採点する（採点したAIの名前も残す）。ページの言い切りは `claims` の条件で決め、
局数が少ないうちは「傾向」と言わない（ONE_GAME_NOTE 未満は例として見せるだけ）。
"""

from __future__ import annotations

from collections import Counter

from .state import Move, State
from .tiles import TileSet, load_tileset

BAD = 3.0  # これ以上損した手を「悪手」と数える（AIの見積もりで、最終得点差の点数）
TREND_GAMES = 10  # この局数に届くまでは「傾向」とは言わない
PHASES = (
    ("early", 0, 24),
    ("middle", 24, 48),
    ("late", 48, 999),
)  # 盤面全体の手数（71手）で3つに分ける
# 人の手とAIの最善手の違い方
CATS = ("no_meeple", "extra_meeple", "other_feature", "placement", "unexplored")


def phase(ply: int) -> str:
    """ply は0始まりの手数（両者合わせて）。"""
    return next(name for name, lo, hi in PHASES if lo <= ply < hi)


def piece_kind(st: State, move: Move) -> str | None:
    """手で置くミープルの種類（C 都市・R 道・F 草原・M 修道院）。置かないなら None。"""
    if move.piece is None:
        return None
    return st.ts.types[st.current].variants[move.variant].pieces[move.piece].kind


def category(loss: float | None, mine: str | None, best: str | None) -> str:
    """人の手（ミープルの種類 mine）がAIの最善手（best）とどう違ったか。"""
    if loss is None:
        return "unexplored"  # AIがほとんど考えなかった手（探索で一度も選ばれなかった）
    if best is not None and mine is None:
        return "no_meeple"
    if best is None and mine is not None:
        return "extra_meeple"
    if best != mine:
        return "other_feature"
    return "placement"


def analyze_game(rec: dict, coach, ts: TileSet | None = None) -> list[dict]:
    """1局の人の手を全部採点する。coach は `webplay.make_coach` が返す関数。"""
    ts = ts or load_tileset()
    st = State(rec["deck"], ts)
    out = []
    for ply, (x, y, v, p) in enumerate(rec["moves"]):
        m = Move(x, y, v, None if p < 0 else p)
        if st.player == rec["human_seat"]:
            c = coach(st, m, ply)
            b = c["best"]
            best_kind = piece_kind(st, Move(b["x"], b["y"], b["v"], b["piece"]))
            mine = piece_kind(st, m)
            out.append(
                {
                    "ply": ply,
                    "loss": c["loss"],
                    "mine": mine,
                    "best": best_kind,
                    "cat": category(c["loss"], mine, best_kind),
                }
            )
        st.apply(m)
    return out


def summarize(
    games: list[dict],
    moves: list[list[dict]],
    swings: list[dict],
    numbers: list[int] | None = None,
) -> dict:
    """games と、局ごとの採点（同じ並び）から、ページに出す集計を作る。

    numbers は各局の番号（1始まり。採点済みの局だけを渡すとき用）。省くと 1, 2, 3, …。
    swings（`human_games.swings`）の game は全局の中の位置（0始まり）。
    """
    n_games = len(games)
    numbers = numbers or list(range(1, n_games + 1))
    all_moves = [dict(m, game=gi) for gi, ms in enumerate(moves) for m in ms]
    scored = [m for m in all_moves if m["loss"] is not None]
    bad = [m for m in all_moves if m["loss"] is None or m["loss"] >= BAD]
    wins = sum(r["scores"][r["human_seat"]] > r["scores"][1 - r["human_seat"]] for r in games)
    by_cat = Counter(m["cat"] for m in bad)
    by_phase = Counter(phase(m["ply"]) for m in bad)
    moves_by_phase = Counter(phase(m["ply"]) for m in all_moves)

    def per_game(x: float) -> float | None:
        return round(x / n_games, 1) if n_games else None

    worst = sorted(
        (m for m in scored if m["loss"] >= BAD), key=lambda m: (-m["loss"], m["game"], m["ply"])
    )[:5]
    return {
        "games": n_games,
        "human_moves": len(all_moves),
        "human_wins": int(wins),
        "mean_loss": round(sum(m["loss"] for m in scored) / len(scored), 1) if scored else None,
        # 損の合計を「悪手の分」と「小さな損（悪手未満）の積み重ね」に分ける（1局あたり）
        "loss_bad_per_game": per_game(sum(m["loss"] for m in scored if m["loss"] >= BAD)),
        "loss_small_per_game": per_game(sum(m["loss"] for m in scored if m["loss"] < BAD)),
        "bad_moves": len(bad),
        "bad_per_game": round(len(bad) / n_games, 1) if n_games else None,
        "by_cat": {c: by_cat.get(c, 0) for c in CATS},
        "by_phase": {
            name: {"bad": by_phase.get(name, 0), "moves": moves_by_phase.get(name, 0)}
            for name, _, _ in PHASES
        },
        "worst": [
            {
                "game": numbers[m["game"]],
                "ply": m["ply"] + 1,
                "loss": m["loss"],
                "cat": m["cat"],
                "mine": m["mine"],
                "best": m["best"],
            }
            for m in worst
        ],
        "ai_misreads": [
            {"game": s["game"] + 1, "ply": s["ply"], "drop": s["drop"]}
            for s in swings
            if s["drop"] >= BAD
        ][:3],
        "trend": n_games >= TREND_GAMES,
    }


def top_cat(s: dict) -> str | None:
    """悪手の種類で一番多いもの（同数なら CATS の順で先のもの）。悪手がなければ None。"""
    if not s["bad_moves"]:
        return None
    return max(CATS, key=lambda c: (s["by_cat"][c], -CATS.index(c)))


def top_phase(s: dict) -> str | None:
    """悪手が出やすい時期（その時期の人の手のうち悪手の割合が一番高いもの）。"""
    rows = [(k, v["bad"] / v["moves"]) for k, v in s["by_phase"].items() if v["moves"]]
    if not s["bad_moves"] or not rows:
        return None
    return max(rows, key=lambda kv: kv[1])[0]
