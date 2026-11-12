"""集めた対局データが消えたり書き換わったりしていないか確かめる（足すだけを許す）。

    py scripts/check_data_append_only.py --base origin/main   # base の版と今の版を比べる

PROTECTED のファイルは「base の中身をそのまま先頭に持ち、後ろに足しただけ」でなければ失敗する。
人が善意で送ってくれた棋譜は取り直せないので、間違った変更・自動処理の不具合で消えるのを PR の時点で止める
（2026-11-12 satou「データが紛失したら困る」。消す仕組みは作らない）。test.yml の data ジョブが動かす。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = ["data/human_games.jsonl"]


def git_show(ref: str, path: str) -> str | None:
    r = subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return r.stdout if r.returncode == 0 else None


def problems(old: str | None, new: str | None, path: str) -> list[str]:
    """old（base）から new（今）への変更が足すだけでなければ、その説明を返す。"""
    if not old or not old.strip():
        return []
    if new is None:
        return [f"{path} が消えています"]
    a, b = old.splitlines(), new.splitlines()
    if len(b) < len(a):
        return [f"{path} の行が減っています（{len(a)} → {len(b)} 行）"]
    for i, (x, y) in enumerate(zip(a, b, strict=False), 1):
        if x != y:
            return [f"{path} の {i} 行目が書き換わっています（足すのは末尾だけにしてください）"]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--base", required=True, help="比べる元（例 origin/main、PR の base の SHA）")
    a = ap.parse_args()
    bad = []
    for path in PROTECTED:
        p = ROOT / path
        bad += problems(
            git_show(a.base, path), p.read_text(encoding="utf-8") if p.exists() else None, path
        )
    for m in bad:
        print(f"::error title=集めた対局データが減っています::{m}")
    if not bad:
        print(f"{', '.join(PROTECTED)} は {a.base} から足しただけです")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
