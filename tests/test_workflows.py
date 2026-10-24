"""CI（.github/workflows と scripts/*.sh）が main へ直接 push しないことを確かめる。

main は Ruleset で「PR 必須」なので、直接 push は断られ、定期実行がそのたびに失敗する
（2026-10-21〜24 の selfplay、Issue #66）。CI のコミットを main に入れるときは
scripts/merge_via_pr.sh（PR を作ってすぐマージする）を使う。
"""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + sorted(
    (ROOT / "scripts").glob("*.sh")
)


def _words(line: str) -> list[str]:
    """シェルの1行を語に分ける。引用符の中の # はコメントにしない。`;`・`&&`・`|` も1語にする。"""
    lex = shlex.shlex(line, posix=True, punctuation_chars=";&|")
    lex.whitespace_split = True
    lex.commenters = "#"
    try:
        return list(lex)
    except ValueError:  # 引用符が行をまたぐ（YAML の複数行）ときは素朴に分ける
        return line.split("#", 1)[0].split()


def pushes_to_main(line: str) -> bool:
    """1行の中の `git push` のどれかが main へ入れるものなら True。

    `HEAD:main`・`HEAD:refs/heads/main`・`origin main` のように main を指すもの、
    `origin HEAD` や行き先を書かない `git push` / `git push origin`（今のブランチ＝CI では main へ入る）を見つける。
    """
    words = _words(line)
    for i in range(len(words) - 1):
        if words[i] != "git" or words[i + 1] != "push":
            continue
        args = []
        for w in words[i + 2 :]:
            if set(w) <= set(";&|"):
                break
            if not w.startswith("-"):
                args.append(w)
        if len(args) <= 1:  # 行き先が無い: 今のブランチ（main）へ入る
            return True
        for ref in args[1:]:
            dst = ref.split(":", 1)[-1].lstrip("+")
            if dst in ("main", "refs/heads/main", "HEAD"):
                return True
    return False


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "git pull -q --rebase origin main && git push -q origin HEAD:main && pushed=1 && break",
            True,
        ),
        ("git push origin main", True),
        ("git push -q origin HEAD:refs/heads/main", True),
        ("git push", True),
        ("git push origin HEAD", True),
        ('echo "# start"; git push origin HEAD:main', True),
        ("git push origin HEAD:selfplay-state && git push origin HEAD:main", True),
        ("git push -f origin tmp:selfplay-state", False),
        ('git push -q origin "HEAD:refs/heads/${branch}"', False),
        ('git push -q origin --delete "$branch" || true', False),
        ("# git push origin main はしない", False),
    ],
)
def test_pushes_to_main_detects(line: str, expected: bool) -> None:
    assert pushes_to_main(line) is expected


def test_no_direct_push_to_main() -> None:
    found = [
        f"{p.relative_to(ROOT)}:{i}: {line.strip()}"
        for p in FILES
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if pushes_to_main(line)
    ]
    assert not found, (
        "main は PR 必須なので直接 push は断られます。scripts/merge_via_pr.sh を使ってください:\n"
        + "\n".join(found)
    )
