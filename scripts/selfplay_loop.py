"""自己対戦で強くなり続けるループを回す（中身は `src/carcassonne/selfplay_loop.py`）。

    py scripts/selfplay_loop.py run --root /mnt/project-files/carcassonne-runs/loop --minutes 50
    py scripts/selfplay_loop.py status --root /mnt/project-files/carcassonne-runs/loop

初回の `run` で `--root` に状態を作り、初代チャンピオン（`--initial`、既定は `models/best.json` の最強の評価関数）
から始める。設定（`--games` など）は初回だけ効き、以後は `state.json` の値を使う。
指定した分数を過ぎたら、その時点の作業単位（数分）を終えてから止まる。続きは次の `run` で再開する。
進み具合は `--root` の `progress.md`（世代ごとの成績表）と `log.txt` に残る。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.selfplay_loop import Config, Loop


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "status"])
    ap.add_argument("--root", default="runs/loop", help="状態・データ・重みを置くフォルダ")
    ap.add_argument("--minutes", type=float, default=50)
    best = json.loads((ROOT / "models" / "best.json").read_text(encoding="utf-8"))["best"]
    ap.add_argument("--initial", default=str(ROOT / best))
    defaults = Config()
    for k, v in vars(defaults).items():
        ap.add_argument(f"--{k.replace('_', '-')}", type=type(v), default=v)
    args = ap.parse_args()
    root = Path(args.root)
    if args.cmd == "status":
        st = json.loads((root / "state.json").read_text(encoding="utf-8"))
        print(f"試行{st['attempt']} {st['phase']} / チャンピオン {st['champion']}")
        progress = root / "progress.md"
        if progress.exists():
            print(progress.read_text(encoding="utf-8"))
        return
    cfg = Config(**{k: getattr(args, k) for k in vars(defaults)})
    loop = Loop(root, cfg, args.initial)
    log_path = root / "log.txt"

    def log(msg: str) -> None:
        print(msg, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")

    loop.run(args.minutes, log)


if __name__ == "__main__":
    main()
