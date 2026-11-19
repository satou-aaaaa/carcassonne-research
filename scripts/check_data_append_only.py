"""集めた対局データが消えたり書き換わったりしていないか確かめる（足すだけを許す）。

    py scripts/check_data_append_only.py --base origin/main   # base の版と今の版を比べる

PROTECTED のファイルは「base の中身をそのまま先頭に持ち、後ろに足しただけ」でなければ失敗する。
人が善意で送ってくれた棋譜は取り直せないので、間違った変更・自動処理の不具合で消えるのを PR の時点で止める
（2026-11-12 satou「データが紛失したら困る」。消す仕組みは作らない）。test.yml の data ジョブが動かす。

あわせて、同じ対局（山札・指し手・人の席が同じ）が2行以上ないことも確かめる。受け取る側は
human_games.add で重複を足さないが、手で足す・別の経路を作るなどで入り込むと、局数や勝率が水増しされる
（2026-11-19 satou「同じ対局を何回でも送れてしまうかも」）。key は src/carcassonne/human_games.py の key と同じ
（numba の要らない data ジョブで動かすため、ここに写している。一致はテストで確かめる）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


def game_key(rec: dict) -> str:
    """同じ対局の見出し。src/carcassonne/human_games.py の key と同じ（tests/test_human_games.py で一致を確認）。"""
    s = json.dumps([rec["deck"], rec["moves"], rec["human_seat"]], separators=(",", ":"))
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def duplicates(text: str | None, path: str) -> list[str]:
    """同じ対局が2行以上あれば、その説明を返す（何行目と何行目が同じか）。"""
    first: dict[str, int] = {}
    out = []
    for i, line in enumerate((text or "").splitlines(), 1):
        if not line.strip():
            continue
        k = game_key(json.loads(line))
        if k in first:
            out.append(
                f"{path} の {i} 行目は {first[k]} 行目と同じ対局です（同じ対局は1局として足す）"
            )
        else:
            first[k] = i
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--base", required=True, help="比べる元（例 origin/main、PR の base の SHA）")
    a = ap.parse_args()
    bad = []
    for path in PROTECTED:
        p = ROOT / path
        new = p.read_text(encoding="utf-8") if p.exists() else None
        bad += problems(git_show(a.base, path), new, path)
        bad += duplicates(new, path)
    for m in bad:
        print(f"::error title=集めた対局データの確認で問題::{m}")
    if not bad:
        print(f"{', '.join(PROTECTED)} は {a.base} から足しただけで、同じ対局の重複もありません")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
