"""方策・価値ネットの学習（PyTorch）。構造は `nn_model.py` と同じで、学習後に numpy 形式で書き出す。"""

from __future__ import annotations

import time

import numpy as np
import torch
from torch import nn

from .nn_encode import NC, NG, R
from .nn_model import VALUE_SCALE


class Block(nn.Module):
    def __init__(self, c: int) -> None:
        super().__init__()
        self.c1 = nn.Conv2d(c, c, 3, padding=1)
        self.n1 = nn.BatchNorm2d(c)
        self.c2 = nn.Conv2d(c, c, 3, padding=1)
        self.n2 = nn.BatchNorm2d(c)

    def forward(self, h):
        y = torch.relu(self.n1(self.c1(h)))
        return torch.relu(h + self.n2(self.c2(y)))


class Net(nn.Module):
    def __init__(self, c: int, blocks: int) -> None:
        super().__init__()
        self.stem = nn.Conv2d(NC, c, 3, padding=1)
        self.stem_n = nn.BatchNorm2d(c)
        self.glob = nn.Linear(NG, c)
        self.blocks = nn.ModuleList(Block(c) for _ in range(blocks))
        self.pol = nn.Conv2d(c, 4, 1)
        self.val = nn.Conv2d(c, 1, 1)
        self.val_n = nn.BatchNorm2d(1)
        self.fc1 = nn.Linear(R * R + NG, 64)
        self.fc2 = nn.Linear(64, 1)

    def forward(self, x, g):
        h = torch.relu(self.stem_n(self.stem(x)) + self.glob(g)[:, :, None, None])
        for b in self.blocks:
            h = b(h)
        logits = self.pol(h).flatten(1)
        logits = logits.masked_fill(x[:, 25:29].flatten(1) <= 0, -1e9)
        v = torch.relu(self.val_n(self.val(h))).flatten(1)
        v = self.fc2(torch.relu(self.fc1(torch.cat([v, g], 1))))
        return logits, v[:, 0]


def _fold(conv: nn.Conv2d, bn: nn.BatchNorm2d):
    s = (bn.weight / torch.sqrt(bn.running_var + bn.eps)).detach()
    w = conv.weight.detach() * s[:, None, None, None]
    b = (conv.bias.detach() - bn.running_mean) * s + bn.bias.detach()
    return w.numpy(), b.numpy()


def export(net: Net, g_mean, g_std, path: str) -> None:
    net.eval()
    out = {"n_blocks": np.array(len(net.blocks)), "g_mean": g_mean, "g_std": g_std}
    out["stem_w"], out["stem_b"] = _fold(net.stem, net.stem_n)
    out["glob_w"] = net.glob.weight.detach().numpy()
    out["glob_b"] = net.glob.bias.detach().numpy()
    for i, b in enumerate(net.blocks):
        out[f"b{i}_w1"], out[f"b{i}_b1"] = _fold(b.c1, b.n1)
        out[f"b{i}_w2"], out[f"b{i}_b2"] = _fold(b.c2, b.n2)
    out["pol_w"] = net.pol.weight.detach().numpy()
    out["pol_b"] = net.pol.bias.detach().numpy()
    out["val_w"], out["val_b"] = _fold(net.val, net.val_n)
    for k in ("fc1", "fc2"):
        out[f"{k}_w"] = getattr(net, k).weight.detach().numpy()
        out[f"{k}_b"] = getattr(net, k).bias.detach().numpy()
    np.savez_compressed(path, **{k: np.asarray(v, np.float32) for k, v in out.items()})


def train(d: dict, args) -> None:
    torch.manual_seed(0)
    games = d["game"]
    cut = np.quantile(np.unique(games), 0.9)
    tr, va = np.flatnonzero(games < cut), np.flatnonzero(games >= cut)
    g_mean = d["glob"][tr].mean(0)
    g_std = d["glob"][tr].std(0) + 1e-3
    X = torch.from_numpy(d["planes"].astype(np.float32))
    Gl = torch.from_numpy(((d["glob"] - g_mean) / g_std).astype(np.float32))
    Pt = torch.from_numpy(d["pol"].astype(np.float32))
    Y = torch.from_numpy((d["y"] / VALUE_SCALE).astype(np.float32))
    net = Net(args.channels, args.blocks)
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=1e-4)
    steps = args.epochs * (len(tr) // args.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, args.lr, total_steps=steps)
    t0 = time.time()
    for ep in range(args.epochs):
        net.train()
        perm = np.random.default_rng(ep).permutation(tr)
        tl = tv = 0.0
        nb = len(perm) // args.batch
        for i in range(nb):
            ix = torch.from_numpy(perm[i * args.batch : (i + 1) * args.batch])
            logits, v = net(X[ix], Gl[ix])
            lp = -(Pt[ix] * torch.log_softmax(logits, 1)).sum(1).mean()
            lv = nn.functional.mse_loss(v, Y[ix])
            loss = lp + args.value_weight * lv
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tl += lp.item()
            tv += lv.item()
        m = evaluate(net, X, Gl, Pt, Y, va)
        print(
            f"ep{ep + 1}: 学習 方策{tl / nb:.3f} 価値{tv / nb:.3f} | 検証 方策{m['pol']:.3f} "
            f"一致率{m['top1']:.3f} 上位3{m['top3']:.3f} 価値R2 {m['r2']:.3f} "
            f"({time.time() - t0:.0f}s)",
            flush=True,
        )
    export(net, g_mean, g_std, args.out)
    print(f"-> {args.out}", flush=True)


@torch.no_grad()
def evaluate(net, X, Gl, Pt, Y, idx) -> dict:
    net.eval()
    lp = top1 = top3 = 0.0
    vs = []
    for i in range(0, len(idx), 1024):
        ix = torch.from_numpy(idx[i : i + 1024])
        logits, v = net(X[ix], Gl[ix])
        lp += -(Pt[ix] * torch.log_softmax(logits, 1)).sum(1).sum().item()
        best = Pt[ix].argmax(1)
        top = logits.topk(3, 1).indices
        top1 += (top[:, 0] == best).sum().item()
        top3 += (top == best[:, None]).any(1).sum().item()
        vs.append(v.numpy())
    v = np.concatenate(vs)
    y = Y[torch.from_numpy(idx)].numpy()
    r2 = 1 - ((y - v) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    n = len(idx)
    return {"pol": lp / n, "top1": top1 / n, "top3": top3 / n, "r2": float(r2)}
