"""公開ページ（docs/ の rules・ai_tips・quiz）をまとめて作り直す。

    py scripts/build_pages.py           # 作り直す
    py scripts/build_pages.py --check   # 作り直した結果がコミット済みの docs/ と同じか確かめる（CI用）

docs/index.html は手書きなので対象外。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDERS = ["build_rules_page.py", "build_puzzles.py", "build_tips_page.py"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="作り直して git の差分がなければ成功")
    args = ap.parse_args()
    for b in BUILDERS:
        subprocess.run([sys.executable, str(ROOT / "scripts" / b)], check=True, cwd=ROOT)
    if args.check:
        r = subprocess.run(
            ["git", "status", "--porcelain", "--", "docs/"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )  # fmt: skip
        if r.stdout.strip():
            print(r.stdout)
            raise SystemExit(
                "docs/ が最新ではありません。py scripts/build_pages.py を実行してコミットしてください"
            )
        print("docs/ は最新です")


if __name__ == "__main__":
    main()
