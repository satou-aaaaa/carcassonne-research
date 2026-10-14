"""リッジ回帰の十分統計量（増分更新用）。

(X, y) の生データを持ち越さずに、n・ΣX・Σy・Σy²・XᵀX・Xᵀy だけを保存する。古い統計を
`decay` 倍してから新しい統計を足すと、新しい方策のデータを重視した再学習ができる。
クラウドの定期実行のように、毎回まっさらな環境から始まる場合に使う（数KBで済む）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .fast_eval import ridge_solve


def stats_of(X: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "n": np.array(float(len(y))),
        "sx": X.sum(axis=0),
        "sy": np.array(float(y.sum())),
        "syy": np.array(float((y * y).sum())),
        "xtx": X.T @ X,
        "xty": X.T @ y,
    }


def merge(old: dict[str, np.ndarray] | None, new: dict[str, np.ndarray], decay: float):
    """old を decay 倍して new を足す。old が None なら new をそのまま返す。"""
    if old is None:
        return new
    return {k: decay * old[k] + new[k] for k in new}


def solve_ridge(
    stats: dict[str, np.ndarray], lam: float, prior: np.ndarray | None = None
) -> np.ndarray:
    """バイアス項を正則化しないリッジ解（prior は `fast_eval.ridge_solve` を参照）。"""
    return ridge_solve(stats["xtx"], stats["xty"], lam, prior)


def r2(stats: dict[str, np.ndarray], w: np.ndarray) -> float:
    n = float(stats["n"])
    sse = float(stats["syy"]) - 2 * w @ stats["xty"] + w @ stats["xtx"] @ w
    sst = float(stats["syy"]) - float(stats["sy"]) ** 2 / n
    return 1.0 - sse / sst


def save(stats: dict[str, np.ndarray], path: str | Path) -> None:
    np.savez_compressed(path, **stats)


def load(path: str | Path, nf: int | None = None) -> dict[str, np.ndarray] | None:
    """統計を読む。無い場合、または nf を指定して特徴量数が合わない場合は None。"""
    p = Path(path)
    if not p.exists():
        return None
    with np.load(p) as d:
        stats = {k: d[k] for k in d.files}
    if nf is not None and stats["xtx"].shape[0] != nf:
        return None  # 特徴量を変えた後は古い統計を捨てて、新しいデータから学び直す
    return stats
