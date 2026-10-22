"""価値ネット（盤面＋盤全体の情報 → 終局得点差）の学習。8通りの回転・反転でランダムに水増しする。"""

import argparse
import glob
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from enc import CHANS, IDX, NCV, NGV, unpack

from carcassonne.fast_eval import eval_value, load_eval

SCALE = 30.0


class Block(nn.Module):
    def __init__(s, c):
        super().__init__()
        s.c1 = nn.Conv2d(c, c, 3, padding=1)
        s.n1 = nn.BatchNorm2d(c)
        s.c2 = nn.Conv2d(c, c, 3, padding=1)
        s.n2 = nn.BatchNorm2d(c)

    def forward(s, h):
        return torch.relu(h + s.n2(s.c2(torch.relu(s.n1(s.c1(h))))))


class VNet(nn.Module):
    def __init__(s, c, b, hid=64):
        super().__init__()
        s.stem = nn.Conv2d(NCV, c, 3, padding=1)
        s.sn = nn.BatchNorm2d(c)
        s.gl = nn.Linear(NGV, c)
        s.blocks = nn.ModuleList(Block(c) for _ in range(b))
        s.fc1 = nn.Linear(2 * c + NGV, hid)
        s.fc2 = nn.Linear(hid, 1)
        s.lin = nn.Linear(NGV, 1)

    def forward(s, x, g):
        h = torch.relu(s.sn(s.stem(x)) + s.gl(g)[:, :, None, None])
        for bl in s.blocks:
            h = bl(h)
        z = torch.cat([h.mean((2, 3)), h.amax((2, 3)), g], 1)
        return (s.fc2(torch.relu(s.fc1(z))) + s.lin(g))[:, 0]


def load(pattern):
    ps = [dict(np.load(f)) for f in sorted(glob.glob(pattern))]
    off = 0
    for p in ps:
        p["game"] = p["game"] + off
        off = int(p["game"].max()) + 1
    return {k: np.concatenate([p[k] for p in ps]) for k in ps[0]}


def r2(y, p):
    return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="runs/az/rec/e_*.npz")
    ap.add_argument("--c", type=int, default=48)
    ap.add_argument("--b", type=int, default=4)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--wd", type=float, default=1e-4)
    ap.add_argument("--out", default="runs/az/vnet.pt")
    ap.add_argument("--max-steps", type=int, default=0)
    a = ap.parse_args()
    torch.manual_seed(0)
    d = load(a.data)
    n = len(d["y"])
    games = d["game"]
    cut = np.quantile(np.unique(games), 0.9)
    tr, va = np.flatnonzero(games < cut), np.flatnonzero(games >= cut)
    print(f"局面 {n}（学習 {len(tr)}・検証 {len(va)}）", flush=True)
    G = d["glob"]
    gm = G[tr].mean(0)
    gs = G[tr].std(0) + 1e-3
    Gn = torch.from_numpy(((G - gm) / gs).astype(np.float32))
    Y = d["y"].astype(np.float32) / SCALE
    Xp = d["planes"]
    yv = Y[va]
    w, mode = load_eval("runs/az/gen386.npy")
    lin = np.array([eval_value(w, mode, G[i, :36].astype(np.float64)) for i in va]) / SCALE
    print(f"参考: gen386 の式の検証R2 {r2(yv, lin):.4f}", flush=True)
    # 参考: 盤全体の情報だけのリッジ回帰
    A = np.c_[G[tr], np.ones(len(tr))]
    coef = np.linalg.solve(A.T @ A + 1e-2 * np.eye(A.shape[1]), A.T @ Y[tr])
    print(
        f"参考: 盤全体の情報84個の線形 検証R2 {r2(yv, np.c_[G[va], np.ones(len(va))] @ coef):.4f}",
        flush=True,
    )
    net = VNet(a.c, a.b)
    print(sum(p.numel() for p in net.parameters()), "params", flush=True)
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
    nb = len(tr) // a.batch
    steps = a.epochs * nb if not a.max_steps else a.max_steps
    sch = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=steps)
    rng = np.random.default_rng(0)
    t0 = time.time()
    step = 0

    def batch(ix, t):
        x = unpack(Xp[ix]).astype(np.float32)
        ox, oy = IDX[t]
        x = x[:, CHANS[t]][:, :, ox, oy]
        return torch.from_numpy(np.ascontiguousarray(x)), Gn[ix]

    def evaluate():
        net.eval()
        ps = []
        with torch.no_grad():
            for i in range(0, len(va), 1024):
                ix = va[i : i + 1024]
                x, g = batch(ix, 0)
                ps.append(net(x, g).numpy())
        net.train()
        return r2(yv, np.concatenate(ps))

    for ep in range(a.epochs):
        perm = rng.permutation(tr)
        tl = 0
        for i in range(nb):
            ix = np.sort(perm[i * a.batch : (i + 1) * a.batch])
            x, g = batch(ix, int(rng.integers(8)))
            loss = nn.functional.mse_loss(net(x, g), torch.from_numpy(Y[ix]))
            opt.zero_grad()
            loss.backward()
            opt.step()
            sch.step()
            tl += loss.item()
            step += 1
            if step % 200 == 0:
                print(
                    f"  step {step}/{steps} loss {tl / (i + 1):.4f} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
            if step >= steps:
                break
        print(
            f"ep{ep + 1}: 学習 {tl / (i + 1):.4f} 検証R2 {evaluate():.4f} ({time.time() - t0:.0f}s)",
            flush=True,
        )
        torch.save({"state": net.state_dict(), "gm": gm, "gs": gs, "c": a.c, "b": a.b}, a.out)
        if step >= steps:
            break


if __name__ == "__main__":
    main()
