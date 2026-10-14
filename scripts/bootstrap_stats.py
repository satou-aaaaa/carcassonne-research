"""ローカルに残っている生データ（runs/data_*.npz）から、持ち越し用の統計量 models/ridge_stats.npz を作る（初回のみ）。"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne import ridge_stats
from carcassonne.fast_eval import NF

files = sorted(glob.glob(str(ROOT / "runs" / "data_*.npz")), key=lambda f: Path(f).stat().st_mtime)
stats = None
for f in files:
    d = np.load(f)
    if d["X"].shape[1] != NF:
        continue
    stats = ridge_stats.merge(stats, ridge_stats.stats_of(d["X"], d["y"]), 0.7)
    print("merged", Path(f).name, len(d["y"]))
if stats is None:
    sys.exit(
        f"runs/data_*.npz に特徴量{NF}個のデータがありません（models/ridge_stats.npz は変更しません）"
    )
ridge_stats.save(stats, ROOT / "models" / "ridge_stats.npz")
print("有効件数", stats["n"])
