"""人間 vs AI の対戦セッション（ブラウザUI用）。

`HumanGame` が `State` を保持し、人間の着手を検証して適用し、続けてAIの手番を進める。
ブラウザへ渡す表示用データ（盤面・ミープル位置・合法手・得点）を `view()` で作る。
終局時に対局記録を JSONL（1局1行）で追記する。集計は scripts/summarize_human.py。

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
        self.saved = False
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
        self.last_ai = None
        self._play(move)
        self._advance_ai()

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
        text = f"{who}: ({move.x},{move.y})に配置、{put}"
        if gain or opp:
            text += f" ／ 得点 {who}+{gain}" + (f" 相手+{opp}" if opp else "")
        self.events.append({"player": player, "text": text})

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
            "last_ai": self.last_ai,
            "events": self.events[-40:],
            "placements": placements,
            "discarded": len(st.discarded),
        }
