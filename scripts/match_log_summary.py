"""run_match の JSONL（途中で止まったものも可）を、先後がそろった山札だけで集計する。

    python scripts/match_log_summary.py runs/a/m.jsonl runs/b/m.jsonl --a "fastmcts(...)"

--a を省くと、最初の行の先手を A にする。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.arena import summarize_log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--a", default=None, help="A のエージェント名")
    args = ap.parse_args()
    a = args.a
    if a is None:
        first = next(ln for ln in Path(args.logs[0]).read_text(encoding="utf-8").splitlines() if ln)
        a = json.loads(first)["p0"]
    print(f"A={a}\n{summarize_log(args.logs, a)}")


if __name__ == "__main__":
    main()
