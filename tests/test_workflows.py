"""CI（.github/workflows と scripts/*.sh）が main へ直接 push しないことを確かめる。

main は Ruleset で「PR 必須」なので、直接 push は断られ、定期実行がそのたびに失敗する
（2026-10-21〜24 の selfplay、Issue #66）。CI のコミットを main に入れるときは
scripts/merge_via_pr.sh（PR を作ってすぐマージする）を使う。
"""

from __future__ import annotations

import json
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


def test_dispatched_workflows_are_watched_by_the_sweep() -> None:
    """ほかのワークフローが `gh workflow run` で起こすワークフローは、CI失敗の見張りに入れ、見回り（schedule）も持たせる。

    GITHUB_TOKEN で起こした実行は workflow_run を起こさないので、見回りが無いと失敗が Issue にならず、
    成功しても Issue が閉じない（AI content、#83、2026-10-26〜28）。
    """
    import re

    wf_dir = ROOT / ".github" / "workflows"
    names = {f.name: re.search(r"^name:\s*(.+)$", f.read_text(encoding="utf-8"), re.MULTILINE).group(1).strip().strip("\"'")
             for f in wf_dir.glob("*.yml")}  # fmt: skip
    watch = (wf_dir / "ci-failure-issue.yml").read_text(encoding="utf-8")
    m = re.search(r"^\s*workflows:\s*(\[.*\])\s*$", watch, re.MULTILINE)
    assert m, "ci-failure-issue.yml の workflows: は見回りが読めるよう1行で書く"
    watched = set(json.loads(m.group(1)))
    assert re.search(r"^  schedule:", watch, re.MULTILINE), (
        "ci-failure-issue.yml に見回りの schedule が要る"
    )
    for f in FILES:
        for target in re.findall(
            r"gh workflow run\s+([\w.-]+\.ya?ml)", f.read_text(encoding="utf-8")
        ):
            assert names.get(target) in watched, (
                f"{f.name} が起こす {target} を ci-failure-issue.yml の workflows に入れる"
            )


def test_issue_and_pr_bodies_are_capped() -> None:
    """CI が `--body-file` で渡す本文は、先に scripts/cap_body.py で上限（65536 文字）に収める。

    回を重ねると伸びる中身（selfplay の成績表）をそのまま入れると、ある日から上限を超えて
    知らせが作れず失敗する（Issue #110、2026-11-02）。
    """
    import re

    missing = []
    for f in FILES:
        lines = f.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            m = re.search(r"--body-file\s+\"?([\w.$/{}-]+)", line)
            if not m or line.lstrip().startswith("#"):
                continue
            name = m.group(1)
            before = "\n".join(lines[:i])
            if not re.search(r"cap_body\.py\"?\s+\"?" + re.escape(name), before):
                missing.append(f"{f.relative_to(ROOT)}:{i + 1}: {line.strip()}")
    assert not missing, "本文を scripts/cap_body.py に通してから渡す:\n" + "\n".join(missing)


WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def test_gh_calls_in_workflows_retry_transient_errors() -> None:
    """ワークフローの中の gh（GitHub の API）は scripts/gh_retry.sh の ghr を通す。

    GitHub の API の一時的な 504 で、selfplay の「新しく採用が出たら Issue で知らせる」が落ちた（2026-11-03）。
    Issue を作るのは gh_issue_create_once を使う（やり直しで2件にしない）。
    """
    import re

    bad = []
    for f in WORKFLOWS:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split(" #", 1)[0]
            if line.lstrip().startswith("#"):
                continue
            for m in re.finditer(r"(?<![\w-])gh (issue|pr|api|workflow|run) ?(\w*)", code):
                if m.group(1) == "issue" and m.group(2) == "create":
                    bad.append(
                        f"{f.name}:{i}: gh issue create → gh_issue_create_once: {line.strip()}"
                    )
                elif not code[: m.start()].rstrip().endswith("ghr"):
                    bad.append(f"{f.name}:{i}: {line.strip()}")
    assert not bad, (
        "gh は `source scripts/gh_retry.sh` してから `ghr gh ...` で呼ぶ:\n" + "\n".join(bad)
    )


def test_auto_pr_checks_can_be_dispatched() -> None:
    """自動の PR（scripts/merge_via_pr.sh）は、マージ前の検査を workflow_dispatch で起こして待つ。

    GITHUB_TOKEN で作った PR の pull_request の実行は承認待ちになり、すぐマージするとジョブ0件の failure が
    残った（2026-10-25〜11-03、auto/* の test・CodeQL・Secret scan で45回）。検査のワークフローに
    workflow_dispatch が無い・呼ぶ側に actions: write が無いと、マージ前の検査が起こせない。
    """
    import re

    script = (ROOT / "scripts" / "merge_via_pr.sh").read_text(encoding="utf-8")
    m = re.search(r'CHECK_WORKFLOWS=\$\{CHECK_WORKFLOWS:-"([^"]+)"\}', script)
    assert m, "merge_via_pr.sh に CHECK_WORKFLOWS が要る"
    for name in m.group(1).split():
        wf = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert re.search(r"^  workflow_dispatch:", wf, re.MULTILINE), (
            f"{name} に workflow_dispatch が要る"
        )
    assert "[skip ci]" in script, (
        "承認待ちの pull_request の実行を作らせないよう、自動のコミットに [skip ci] を付ける"
    )
    callers = [
        f for f in WORKFLOWS if "bash scripts/merge_via_pr.sh" in f.read_text(encoding="utf-8")
    ]
    assert callers
    for f in callers:
        assert re.search(r"^  actions: write", f.read_text(encoding="utf-8"), re.MULTILINE), (
            f"{f.name} は merge_via_pr.sh で検査を起こすので permissions に actions: write が要る"
        )
