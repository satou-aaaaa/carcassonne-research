"""人間 vs AI の対戦セッション（ブラウザUI用）。

`HumanGame` が `State` を保持し、人間の着手を検証して適用し、続けてAIの手番を進める。
ブラウザへ渡す表示用データ（盤面・ミープル位置・合法手・得点）を `view()` で作る。
終局時に対局記録を JSONL（1局1行）で追記する。集計は scripts/summarize_human.py。

初心者向けの「ヒント」を有効にすると、人間の着手のたびにAIがその局面を解析し、最善手と比べて
何点損したか（AIの見積もり）を返す（`make_coach`）。ヒントありの対局は記録に `coach: true` が付く。

AIは `FastMCTSAgent`。山札の未公開部分は探索の度にシャッフルされるため、AIは山札の順序を
覗かない（公平性）。ミープルの盤上位置は `State` が持たないので、ここで追跡する。
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict
from pathlib import Path

from .state import Move, State
from .tiles import load_tileset

ROOT = Path(__file__).resolve().parents[2]
KIND_JA = {"C": "都市", "R": "道", "F": "草原", "M": "修道院"}
LEVELS = {
    "strong": "最強（MCTS 12000回＋短いロールアウト10手＋評価関数）",
    "standard": "標準（MCTS 2000回＋評価関数）",
    "greedy": "貪欲法（練習用）",
}


def best_eval_path() -> str:
    best = json.loads((ROOT / "models" / "best.json").read_text(encoding="utf-8"))["best"]
    return str(ROOT / best)


def make_agent(level: str):
    """強さ指定からAIを作る。重いimport（numba）は必要になるまで遅らせる。"""
    if level == "greedy":
        from .agents import GreedyAgent

        return GreedyAgent()
    from .fast_mcts import FastMCTSAgent

    sims = {"strong": 12000, "standard": 2000}[level]
    # 最強は評価前に10手のロールアウトを挟む（docs/EXPERIMENTS.md「探索の構造」。標準は従来どおり）
    depth = 10 if level == "strong" else None
    return FastMCTSAgent(n_sims=sims, rollout_depth=depth, eval_path=best_eval_path())


def _best_dict(st: State, best) -> dict:
    """解析結果の手を、画面用の dict（マス・向き・断片・断片の種類）にする。"""
    v = st.ts.types[st.current].variants[best.move.variant]
    kind = KIND_JA[v.pieces[best.move.piece].kind] if best.move.piece is not None else None
    return {
        "x": best.move.x,
        "y": best.move.y,
        "v": best.move.variant,
        "piece": best.move.piece,
        "kind": kind,
    }


def make_coach(agent):
    """人間の着手を採点する関数を返す。agent は FastMCTSAgent（puzzles.analyze で根を解析する）。

    戻り値の関数は (着手前の局面, 人間の手, 乱数シード) を受け取り、表示用の dict を返す。
    損失は「AIの最善手の予想最終点差 − 人間の手の予想最終点差」。人間の手が探索でほとんど
    調べられなかった（訪問0）場合は損失を出さず、その旨だけ返す。
    """
    from .puzzles import analyze

    def coach(st: State, move: Move, seed: int) -> dict:
        opts = analyze(agent, st, seed)
        best = opts[0]  # 訪問数最大の手（AIが実際に指す手）
        out = {"best": _best_dict(st, best), "loss": None}
        mine = next((o for o in opts if o.move == move), None)
        if mine is not None:
            out["loss"] = round(max(0.0, best.diff - mine.diff), 1)
        return out

    return coach


def make_advisor(agent):
    """置く前のヒント: (局面, 乱数シード) を受け取り、AIの最善手を画面用の dict で返す関数。"""
    from .puzzles import analyze

    def advise(st: State, seed: int) -> dict:
        return _best_dict(st, analyze(agent, st, seed)[0])

    return advise


def coach_text(c: dict) -> str:
    """ヒントの1行説明。"""
    b = c["best"]
    ai = f"AIなら紫の点線のマスに置き、{b['kind'] + 'にミープル' if b['kind'] else 'ミープルは置かない'}"
    if c["loss"] is None:
        return f"ヒント: AIがほとんど考えなかった手です。{ai}。"
    if c["loss"] < 1:
        return "ヒント: AIの最善手とほぼ同じ、いい手です。"
    return f"ヒント: AIの見積もりでは最善より約{c['loss']:.0f}点の損。{ai}。"


def tile_library() -> list[dict]:
    """ブラウザ描画用のタイル定義（種別ごとの全向き）。"""
    ts = load_tileset()
    return [
        {
            "id": t.id,
            "count": t.count,
            "variants": [
                {"edges": list(v.edges), "pieces": [asdict(p) for p in v.pieces]}
                for v in t.variants
            ],
        }
        for t in ts.types
    ]


class HumanGame:
    def __init__(
        self,
        seed: int,
        human_seat: int,
        level: str,
        agent,
        name: str = "",
        log_path: str | Path | None = None,
        coach=None,
        advisor=None,
    ) -> None:
        self.seed = seed
        self.human_seat = human_seat
        self.level = level
        self.name = name
        self.agent = agent
        self.log_path = Path(log_path) if log_path else ROOT / "runs" / "human" / "games.jsonl"
        self.st = State.new_game(seed)
        self.rng = random.Random(seed * 2 + 1 - human_seat)  # AI用（再現性のため）
        self.meeples: list[dict] = []
        self.events: list[dict] = []
        self.moves: list[list] = []  # [player, x, y, 種別index, 向き, 断片]
        self.last_ai: dict | None = None
        self.coach = coach
        self.last_coach: dict | None = None
        self.saved = False
        self.end_meeples: list[dict] = []  # 終局直前に盤上にいたミープル（終局の得点内訳用）
        self.advisor = advisor  # 置く前のヒント（make_advisor）
        self.hint: dict | None = None
        self.hints = 0  # ヒントを見た回数（記録用）
        self.undos = 0  # 待ったの回数（記録用）
        self._snaps: list[tuple] = []  # 人間の各手の直前の状態（待った用）
        self._mid = 0
        self._advance_ai()

    # ---- 着手 ------------------------------------------------------------

    def human_move(self, x: int, y: int, variant: int, piece: int | None) -> None:
        st = self.st
        if st.over or st.player != self.human_seat:
            raise ValueError("あなたの手番ではありません")
        move = Move(x, y, variant, piece)
        if move not in st.legal_moves():
            raise ValueError("不正な手です")
        self._snaps.append(
            (
                self.st.copy(),
                list(self.meeples),
                list(self.events),
                list(self.moves),
                self.last_ai,
                self.last_coach,
                self._mid,
            )
        )
        self.last_ai = None
        self.last_coach = None
        self.hint = None
        if self.coach is not None:
            self.last_coach = self.coach(st, move, self.seed * 1000 + len(st.history))
        self._play(move)
        if self.last_coach is not None:
            b = self.last_coach["best"]
            self.events.append(
                {
                    "player": self.human_seat,
                    "text": coach_text(self.last_coach),
                    "x": b["x"],
                    "y": b["y"],
                }
            )
        self._advance_ai()

    def undo(self) -> None:
        """待った: 直前の自分の手（とそれに続くAIの手）を取り消し、その手の前に戻す。"""
        if self.st.over:
            raise ValueError("終局後は戻せません")
        if not self._snaps:
            raise ValueError("戻せる手がありません")
        st, meeples, events, moves, last_ai, last_coach, mid = self._snaps.pop()
        self.st, self.meeples, self.events, self.moves = st, meeples, events, moves
        self.last_ai, self.last_coach, self._mid = last_ai, last_coach, mid
        self.hint = None
        self.undos += 1
        self.events.append({"player": self.human_seat, "text": "待った: 1手戻しました"})

    def request_hint(self) -> None:
        """置く前のヒント: 今の局面でのAIの最善手を self.hint に入れる。"""
        st = self.st
        if st.over or st.player != self.human_seat:
            raise ValueError("あなたの手番ではありません")
        if self.advisor is None:
            raise ValueError("ヒントは使えません")
        self.hint = self.advisor(st, self.seed * 1000 + 500 + len(st.history))
        self.hints += 1

    def _advance_ai(self) -> None:
        while not self.st.over and self.st.player != self.human_seat:
            move = self.agent.act(self.st, self.rng)
            self._play(move)
            self.last_ai = {"x": move.x, "y": move.y}
        if self.st.over:
            self._save()

    def _play(self, move: Move) -> None:
        st = self.st
        player, tile = st.player, st.current
        before = list(st.scores)
        st.apply(move)
        self.moves.append([player, move.x, move.y, tile, move.variant, move.piece])
        if move.piece is not None:
            self._mid += 1
            self.meeples.append(
                {"id": self._mid, "x": move.x, "y": move.y, "piece": move.piece, "player": player}
            )
        if st.over:
            self.end_meeples = list(self.meeples)
        # 回収されたミープル（特徴が完成/終局処理された）を除く
        self.meeples = [
            m
            for m in self.meeples
            if st.meeples[st._find(st.tile_nodes[(m["x"], m["y"])][m["piece"]])][m["player"]] > 0
        ]
        gain = st.scores[player] - before[player]
        opp = st.scores[1 - player] - before[1 - player]
        who = "あなた" if player == self.human_seat else "AI"
        v = st.ts.types[tile].variants[move.variant]
        put = (
            f"{KIND_JA[v.pieces[move.piece].kind]}にミープル"
            if move.piece is not None
            else "ミープルなし"
        )
        text = f"{who}: タイルを置き、{put}"
        if gain or opp:
            text += f" ／ 得点 {who}+{gain}" + (f" 相手+{opp}" if opp else "")
        self.events.append({"player": player, "text": text, "x": move.x, "y": move.y})

    # ---- 記録 ------------------------------------------------------------

    def _save(self) -> None:
        if self.saved:
            return
        self.saved = True
        s = self.st.scores
        h = self.human_seat
        rec = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "name": self.name,
            "seed": self.seed,
            "human_seat": h,
            "level": self.level,
            "coach": self.coach is not None,
            "hints": self.hints,
            "undos": self.undos,
            "ai": getattr(self.agent, "name", str(self.agent)),
            "scores": list(s),
            "human_score": s[h],
            "ai_score": s[1 - h],
            "diff_human": s[h] - s[1 - h],
            "discarded": len(self.st.discarded),
            "moves": self.moves,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- 表示用 ----------------------------------------------------------

    def view(self) -> dict:
        st = self.st
        placements: list[dict] = []
        if not st.over and st.player == self.human_seat:
            grouped: dict[tuple[int, int, int], list[int]] = {}
            for m in st.legal_moves():
                ps = grouped.setdefault((m.x, m.y, m.variant), [])
                if m.piece is not None:
                    ps.append(m.piece)
            placements = [
                {"x": x, "y": y, "v": v, "pieces": ps} for (x, y, v), ps in grouped.items()
            ]
        return {
            "seed": self.seed,
            "human_seat": self.human_seat,
            "level": self.level,
            "name": self.name,
            "player": st.player,
            "over": st.over,
            "scores": list(st.scores),
            "projected": st.projected_scores(),
            "supply": list(st.supply),
            "deck_left": len(st.deck) - st.draw_pos,
            "current": st.current,
            "remaining": st.remaining_counts(),
            "board": [{"x": x, "y": y, "t": t, "v": v} for (x, y), (t, v) in st.board.items()],
            "meeples": self.meeples,
            "end_meeples": self.end_meeples if st.over else [],
            "last_ai": self.last_ai,
            "coach": self.coach is not None,
            "last_coach": self.last_coach,
            "hint": self.hint,
            "can_undo": bool(self._snaps) and not st.over,
            "events": self.events[-40:],
            "placements": placements,
            "discarded": len(st.discarded),
        }
