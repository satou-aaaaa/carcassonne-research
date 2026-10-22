"""探索（gen386 の MCTS）の根の候補を、価値ネットの1手先の期待値で採点し直すエージェント。

候補（配置×ミープル）ごとに、着手後に相手が引くタイル種別 t（未公開の枚数で重み付け）を列挙し、
相手視点の価値ネットの予測 V を求めて、自分の値 = −Σ p_t V とする。探索の平均報酬を得点差に戻した値と
alpha で混ぜ、最大の候補を指す。alpha=0 なら元の探索と同じ手（同点の乱択を除く）。
"""

import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from enc import encode_state
from train import SCALE, VNet

from carcassonne.fast import (
    NT,
    SC_CUR,
    SC_DRAW,
    SC_OVER,
    SC_PL,
    SC_S0,
    SC_S1,
    apply_move,
    copy_state,
)
from carcassonne.fast_mcts import FastMCTSAgent, search_stats

_NETS = {}


def load_net(path):
    if path not in _NETS:
        torch.set_num_threads(1)
        ck = torch.load(path, weights_only=False)
        net = VNet(ck["c"], ck["b"])
        net.load_state_dict(ck["state"])
        net.eval()
        _NETS[path] = (net, ck["gm"].astype(np.float32), ck["gs"].astype(np.float32))
    return _NETS[path]


class NetAgent(FastMCTSAgent):
    def __init__(self, vnet="runs/az/vnet.pt", alpha=0.5, topk=8, minfrac=0.0, **kw):
        super().__init__(**kw)
        self.vnet, self.alpha, self.topk, self.minfrac = vnet, alpha, topk, minfrac
        self.name = f"net({self.name},a={alpha},k={topk},mf={minfrac},{Path(vnet).name})"

    def choose(self, S):
        f = self.fast
        T, P, sc = f.T, f.P, f.scratch
        cells, gs, _a1, _w1, a2, w2 = search_stats(
            S,
            T,
            P,
            self.n_sims,
            self.n_det,
            self.c,
            self.reward_scale,
            self.meeple_prob,
            self.rollout_depth,
            sc.stamp,
            sc.stamp_box,
            sc.out_cell,
            sc.out_g,
            sc.free,
            sc.rec,
            self.eval_w,
            self.eval_mode,
            self.fbuf,
            self.late,
            self.fpu,
            self.prior_visits,
            np.zeros(0, np.int64),
            0,
            bool(self.rollout_farm),
            0,
        )
        cand = [
            (int(a2[k, q]), k, q - 1)
            for k in range(len(cells))
            for q in range(P + 1)
            if a2[k, q] > 0
        ]
        cand.sort(reverse=True)
        top = cand[0][0]
        cand = [c for c in cand[: self.topk] if c[0] >= self.minfrac * top]
        if self.alpha <= 0 or len(cand) == 1:
            _, k, p = cand[0]
            return int(cells[k]), int(gs[k]), p
        me = int(S[10][SC_PL])
        lo = int(S[10][SC_DRAW])
        unseen = S[11][lo : NT - 1]
        types, counts = np.unique(unseen, return_counts=True)
        planes, globs, owner, wts, fixed = [], [], [], [], {}
        for ci, (_, k, p) in enumerate(cand):
            if len(unseen) == 0:
                X = copy_state(S)
                apply_move(
                    X, T, P, cells[k], gs[k], p, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g
                )
                d = float(X[10][SC_S0] - X[10][SC_S1])
                fixed[ci] = d if me == 0 else -d
                continue
            for t, n in zip(types, counts):
                X = copy_state(S)
                dk = X[11]
                j = lo + int(np.flatnonzero(dk[lo : NT - 1] == t)[0])
                dk[lo], dk[j] = dk[j], dk[lo]
                apply_move(
                    X, T, P, cells[k], gs[k], p, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g
                )
                if X[10][SC_OVER] or X[10][SC_CUR] != t or X[10][SC_DRAW] != lo + 1:
                    continue  # 置けないタイル（捨てられる）は近似として省く
                v, g = encode_state(X, f)
                planes.append(v)
                globs.append(g)
                owner.append(ci)
                wts.append(n)
        val = np.zeros(len(cand))
        wsum = np.zeros(len(cand))
        if planes and self.vnet == "lin":
            from carcassonne.fast_eval import eval_value

            out = np.array(
                [eval_value(self.eval_w, self.eval_mode, g[:36].astype(np.float64)) for g in globs]
            )
            for o, w, vv in zip(owner, wts, out):
                val[o] += -w * vv
                wsum[o] += w
        elif planes:
            net, gm, gsd = load_net(self.vnet)
            with torch.no_grad():
                x = torch.from_numpy(np.stack(planes).astype(np.float32))
                g = torch.from_numpy((np.stack(globs) - gm) / gsd)
                out = net(x, g).numpy() * SCALE
            for o, w, vv in zip(owner, wts, out):
                val[o] += -w * vv
                wsum[o] += w
        best, bs = 0, -1e30
        for ci, (vis, k, p) in enumerate(cand):
            q = w2[k, p + 1] / vis
            dm = self.reward_scale * np.arctanh(np.clip(2 * q - 1, -0.999, 0.999))
            dn = fixed[ci] if ci in fixed else (val[ci] / wsum[ci] if wsum[ci] > 0 else dm)
            s = (1 - self.alpha) * dm + self.alpha * dn
            if s > bs:
                best, bs = ci, s
        _, k, p = cand[best]
        return int(cells[k]), int(gs[k]), p
