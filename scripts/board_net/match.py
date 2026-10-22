"""NetAgent と gen386（同じ探索）を、先後入れ替えの組で対戦させる。"""

import argparse
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from netagent import NetAgent

from carcassonne.arena import run_match
from carcassonne.fast_mcts import FastMCTSAgent

ap = argparse.ArgumentParser()
ap.add_argument("--sims", type=int, default=2000)
ap.add_argument("--bsims", type=int, default=0)
ap.add_argument("--alpha", type=float, default=0.5)
ap.add_argument("--topk", type=int, default=8)
ap.add_argument("--minfrac", type=float, default=0.0)
ap.add_argument("--vnet", default="runs/az/vnet.pt")
ap.add_argument("--seeds", type=int, default=100)
ap.add_argument("--start", type=int, default=7000)
ap.add_argument("--workers", type=int, default=4)
ap.add_argument("--log", default=None)
a = ap.parse_args()
kw = {"rollout_depth": 10, "eval_path": "runs/az/gen386.npy"}
A = partial(
    NetAgent, vnet=a.vnet, alpha=a.alpha, topk=a.topk, minfrac=a.minfrac, n_sims=a.sims, **kw
)
B = partial(FastMCTSAgent, n_sims=a.bsims or a.sims, **kw)
s = run_match(A, B, range(a.start, a.start + a.seeds), a.log, a.workers)
print(
    f"A=net(sims={a.sims},alpha={a.alpha},topk={a.topk},mf={a.minfrac},{a.vnet}) B=gen386(sims={a.bsims or a.sims})\n{s}",
    flush=True,
)
