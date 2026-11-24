"""公開ページ（docs/ のトップ・講座 learn/・研究 research/・対戦 play.html ほか）をまとめて作り直す。

    py scripts/build_pages.py           # 作り直す
    py scripts/build_pages.py --check   # 作り直した結果がコミット済みの docs/ と同じか確かめる（CI用）

ページの置き場所は scripts/i18n.py の LOC（組み立てスクリプトは "rules.html" などの論理名で書く）。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDERS = [
    "build_rules_page.py",
    "build_strategy_page.py",
    "build_puzzles.py",
    "build_tips_page.py",
    "build_play_page.py",
    "build_stats_page.py",
    "build_games_page.py",
    "build_terms_page.py",
    "build_hubs.py",  # トップ・講座の目次（learn/）・研究の目次（research/）
    "build_redirects.py",  # 古い置き場所（docs/rules.html など）の転送ページ
]


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
