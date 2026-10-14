"""TD(λ) の学習目標。

終局得点差だけを答えにすると、その後の山札の引きの運がそのまま答えのノイズになる。
TD(λ) では、次の局面の評価値と、さらに先の目標を λ で混ぜた値を答えにする
（λ=1 で終局得点差、λ=0 で次の局面の評価値そのもの）。

各局面の値は手番側視点なので、次の局面の手番が相手なら符号を反転して足す。
"""

from __future__ import annotations

import numpy as np


def td_lambda_targets(
    values: np.ndarray,
    finals: np.ndarray,
    players: np.ndarray,
    game_ids: np.ndarray,
    lam: float,
) -> np.ndarray:
    """局面列から TD(λ) の目標を作る。

    values[t]: 局面 t の評価値（手番側視点）。finals[t]: その対局の終局得点差（局面 t の手番側視点）。
    players[t]: 局面 t の手番。game_ids[t]: 対局番号（同じ対局の局面は連続して時系列順に並ぶこと）。
    G_t = (1−λ)·V(s_{t+1}) + λ·G_{t+1}（各項を局面 t の手番側視点に直す）、対局の最後の局面は G = 終局得点差。
    """
    n = len(values)
    out = np.empty(n)
    for t in range(n - 1, -1, -1):
        if t == n - 1 or game_ids[t + 1] != game_ids[t]:
            out[t] = finals[t]
            continue
        s = 1.0 if players[t + 1] == players[t] else -1.0
        out[t] = s * ((1.0 - lam) * values[t + 1] + lam * out[t + 1])
    return out
