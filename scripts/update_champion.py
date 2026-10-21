"""自己対戦ループの最新チャンピオンを、公開ページ（docs/play.html）用に models/ へ複写する。

    py scripts/update_champion.py state/loop   # ループの状態フォルダ（selfplay-state の loop/）

models/eval_champion.npy（重み）と models/eval_champion.json（世代名・採用日）を書き、
変わったときは終了コード 0 で「updated」と出す。同じなら「unchanged」。
JavaScript 版が扱えない形式（線形でない）のときは書かずに「skipped」と出す。
そのあと scripts/build_pages.py で公開ページを作り直す（.github/workflows/selfplay.yml が自動で行う）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.fast_eval import NF

DEST = ROOT / "models" / "eval_champion.npy"
INFO = ROOT / "models" / "eval_champion.json"


def main(loop_root: str) -> str:
    root = Path(loop_root)
    st = json.loads((root / "state.json").read_text(encoding="utf-8"))
    src = root / st["champion"]
    w = np.load(src)
    if w.ndim != 1 or len(w) > NF:
        return "skipped"
    name = src.stem
    promoted = [h for h in st["history"] if h.get("promoted") and h["candidate"] == st["champion"]]
    info = {
        "name": name,
        "attempt": promoted[-1]["attempt"] if promoted else None,
        "date": promoted[-1]["date"] if promoted else None,
    }
    old = json.loads(INFO.read_text(encoding="utf-8")) if INFO.exists() else None
    if old == info and DEST.exists() and np.array_equal(np.load(DEST), w):
        return "unchanged"
    np.save(DEST, w)
    INFO.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return "updated"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(main(sys.argv[1]))
