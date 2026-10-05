"""対戦ランナーと集計。

同じ山札シードで先手・後手を入れ替えた2局を1組（ペア）として扱い、山札の運の差を打ち消す。
結果は JSONL で保存でき、勝率（Wilson区間）・平均得点差（標準誤差）で比較する。
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from .agents import Agent
from .state import State


@dataclass
class GameResult:
    seed: int
    p0: str
    p1: str
    scores: list[int]
    plies: int
    discarded: int

    @property
    def diff(self) -> int:
        return self.scores[0] - self.scores[1]


def play_game(seed: int, a0: Agent, a1: Agent, move_seed: int | None = None) -> GameResult:
    """seed の山札で a0（先手）と a1（後手）が対戦する。"""
    st = State.new_game(seed)
    rngs = [random.Random((move_seed if move_seed is not None else seed) * 2 + i) for i in (0, 1)]
    agents = (a0, a1)
    plies = 0
    while not st.over:
        p = st.player
        st.apply(agents[p].act(st, rngs[p]))
        plies += 1
    return GameResult(seed, a0.name, a1.name, list(st.scores), plies, len(st.discarded))


@dataclass
class MatchSummary:
    games: int
    wins_a: float  # 引き分けは0.5勝
    mean_diff_a: float  # Aの平均得点差（A−B）
    se_diff: float
    win_rate: float
    ci_low: float
    ci_high: float

    def __str__(self) -> str:
        return (
            f"{self.games}局 Aの勝率 {self.win_rate:.3f} "
            f"[{self.ci_low:.3f}, {self.ci_high:.3f}] 平均得点差 {self.mean_diff_a:+.2f}±{self.se_diff:.2f}"
        )


def wilson(wins: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def summarize(results_a_first: list[GameResult], results_b_first: list[GameResult]) -> MatchSummary:
    """A先手の結果と B先手の結果（同一シード）から、Aの視点で集計する。"""
    diffs = [r.diff for r in results_a_first] + [-r.diff for r in results_b_first]
    wins = sum(1.0 if d > 0 else 0.5 if d == 0 else 0.0 for d in diffs)
    n = len(diffs)
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / max(n - 1, 1)
    lo, hi = wilson(wins, n)
    return MatchSummary(n, wins, mean, math.sqrt(var / n), wins / n, lo, hi)


def _play_job(job: tuple) -> GameResult:
    seed, make0, make1 = job
    return play_game(seed, make0(), make1())


def run_match(
    make_a: Callable[[], Agent],
    make_b: Callable[[], Agent],
    seeds: range | list[int],
    log_path: str | Path | None = None,
    workers: int = 1,
) -> MatchSummary:
    """各シードで先後を入れ替えて対戦し、Aの視点で集計する。

    workers > 1 のときはプロセス並列。make_a / make_b はpickle可能（モジュール直下の関数や
    functools.partial）である必要がある。
    """
    seeds = list(seeds)
    jobs = [(s, make_a, make_b) for s in seeds] + [(s, make_b, make_a) for s in seeds]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_play_job, jobs, chunksize=1))
    else:
        results = [_play_job(j) for j in jobs]
    a_first, b_first = results[: len(seeds)], results[len(seeds) :]
    if log_path is not None:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for r in a_first + b_first:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    return summarize(a_first, b_first)
