"""Issue・PR の本文ファイルを GitHub の上限に収まるよう短くする（その場で書き換える）。

    python scripts/cap_body.py body.md [--limit 60000] [--note "全文: <URL>"]

GitHub の Issue・PR の本文は 65536 文字まで（超えると gh が
「Body is too long (maximum is 65536 characters)」で失敗する）。CI が作る本文は、成績表など
回を重ねるほど伸びるものを入れると、ある日から上限を超えて止まる（selfplay の採用の知らせ、Issue #110、
2026-11-02。progress.md が 890 試行で 68700 文字になった）。

上限を超えるときは、頭（見出し・表の頭）と末尾（新しい行）を残し、途中を省いた印を入れる。
CI で `--body-file` に渡す前に必ず通す（tests/test_workflows.py が確かめる）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

GITHUB_LIMIT = 65536
DEFAULT_LIMIT = 60000  # 上限より少し余裕を持たせる（gh が足す分・数え方の違い）


def cap(text: str, limit: int = DEFAULT_LIMIT, note: str = "") -> str:
    """text が limit 文字を超えるなら、行の切れ目で頭と末尾を残して途中を省く。"""
    if len(text) <= limit:
        return text
    mark = (
        f"\n\n…（長いので途中を省きました。{note}）…\n\n"
        if note
        else "\n\n…（長いので途中を省きました）…\n\n"
    )
    room = limit - len(mark)
    head_room, tail_room = room // 3, room - room // 3  # 新しい行（末尾）を多めに残す
    lines = text.split("\n")
    head: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > head_room:
            break
        head.append(line)
        used += len(line) + 1
    tail: list[str] = []
    used = 0
    for line in reversed(lines[len(head) :]):
        if used + len(line) + 1 > tail_room:
            break
        tail.append(line)
        used += len(line) + 1
    out = "\n".join(head) + mark + "\n".join(reversed(tail))
    return out[:limit]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    p = Path(args.file)
    text = p.read_text(encoding="utf-8")
    out = cap(text, args.limit, args.note)
    if out != text:
        p.write_text(out, encoding="utf-8")
        print(f"{p}: {len(text)} 文字 → {len(out)} 文字に短くしました")


if __name__ == "__main__":
    main()
