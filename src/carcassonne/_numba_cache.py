"""Numba のキャッシュ（__pycache__/*.nbi, *.nbc）が古いまま使われるのを防ぐ。

Numba の `cache=True` は、関数を書いたファイル自身が変わったときしか作り直さない。たとえば
`fast_eval.py` の特徴量を変えても、それを呼ぶ `fast_mcts.run_tree` は古い特徴量のまま動いてしまう
（2026-11-11、特徴量を足した評価関数が探索で使われず、対戦が同じ棋譜になった）。
そこで、キャッシュを使うファイルをまとめたハッシュを記録し、どれかが変わったらキャッシュを全部消す。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# cache=True の関数を持つファイル（互いに呼び合うので、どれかが変われば全部作り直す）
SOURCES = (
    "fast.py",
    "fast_eval.py",
    "fast_eval_ext.py",
    "fast_mcts.py",
    "endgame.py",
    "nn_encode.py",
    "rollout_fit.py",
)


def source_hash(pkg: Path) -> str:
    h = hashlib.sha256()
    for name in SOURCES:
        p = pkg / name
        if p.exists():
            h.update(name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def clear_if_stale(pkg: Path | None = None) -> bool:
    """ソースが前回と違えば Numba のキャッシュを消す。消したら True。"""
    pkg = pkg or Path(__file__).resolve().parent
    cache = pkg / "__pycache__"
    stamp = cache / "numba_sources.sha256"
    now = source_hash(pkg)
    try:
        if stamp.read_text(encoding="utf-8") == now:
            return False
    except OSError:
        pass
    removed = False
    try:
        cache.mkdir(exist_ok=True)
        for f in list(cache.glob("*.nbi")) + list(cache.glob("*.nbc")):
            f.unlink(missing_ok=True)
            removed = True
        stamp.write_text(now, encoding="utf-8")
    except OSError:
        pass  # 書けない場所（読み取り専用など）では何もしない
    return removed
