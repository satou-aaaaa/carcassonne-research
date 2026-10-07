"""方策・価値ネットの推論（numpy だけで動く。学習は `nn_torch.py`）。

構造: 3x3畳み込み（盤全体の情報を線形変換してチャンネルごとに足す）→ 残差ブロック×B
→ 方策ヘッド（1x1畳み込みで向きごとのロジット、合法手以外は除外）
→ 価値ヘッド（1x1畳み込み→平坦化→盤全体の情報と連結→全結合2層、終局得点差/30 を予測）。
BatchNorm は学習後に畳み込みへ畳み込み済み。
"""

from __future__ import annotations

import numpy as np

from .nn_encode import NC, R

VALUE_SCALE = 30.0


def conv(x: np.ndarray, w: np.ndarray, b: np.ndarray) -> np.ndarray:
    """x[N,C,R,R] に w[O,C,k,k]（stride 1、same パディング）を掛ける。"""
    n, c, h, wd = x.shape
    _, _, k, _ = w.shape
    if k == 1:
        return np.einsum("nchw,oc->nohw", x, w[:, :, 0, 0], optimize=True) + b[None, :, None, None]
    p = k // 2
    xp = np.pad(x, ((0, 0), (0, 0), (p, p), (p, p)))
    cols = np.empty((n, c, k, k, h, wd), x.dtype)
    for i in range(k):
        for j in range(k):
            cols[:, :, i, j] = xp[:, :, i : i + h, j : j + wd]
    out = np.einsum("ncklhw,ockl->nohw", cols, w, optimize=True)
    return out + b[None, :, None, None]


class PolicyValueNet:
    def __init__(self, path: str) -> None:
        with np.load(path) as d:
            self.p = {k: d[k].astype(np.float32) for k in d.files}
        self.blocks = int(self.p["n_blocks"])

    def forward(self, planes: np.ndarray, glob: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """planes[N,NC,R,R], glob[N,NG] → (方策ロジット[N,4*R*R]（違法手は -inf）, 予測得点差[N])。"""
        p = self.p
        x = planes.astype(np.float32).reshape(-1, NC, R, R)
        g = (glob.astype(np.float32).reshape(len(x), -1) - p["g_mean"]) / p["g_std"]
        h = conv(x, p["stem_w"], p["stem_b"]) + (g @ p["glob_w"].T + p["glob_b"])[:, :, None, None]
        h = np.maximum(h, 0)
        for i in range(self.blocks):
            y = np.maximum(conv(h, p[f"b{i}_w1"], p[f"b{i}_b1"]), 0)
            y = conv(y, p[f"b{i}_w2"], p[f"b{i}_b2"])
            h = np.maximum(h + y, 0)
        logits = conv(h, p["pol_w"], p["pol_b"]).reshape(len(x), -1)
        legal = x[:, 25:29].reshape(len(x), -1) > 0
        logits = np.where(legal, logits, -np.inf)
        v = np.maximum(conv(h, p["val_w"], p["val_b"]), 0).reshape(len(x), -1)
        v = np.maximum(np.concatenate([v, g], axis=1) @ p["fc1_w"].T + p["fc1_b"], 0)
        v = v @ p["fc2_w"].T + p["fc2_b"]
        return logits, v[:, 0] * VALUE_SCALE
