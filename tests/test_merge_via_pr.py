"""scripts/merge_via_pr.sh の、PR を作る手前までの動きを確かめる（gh はにせものに替える）。"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "merge_via_pr.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None, reason="bash と git が要る"
)


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def setup(tmp_path):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(origin), str(seed))
    git(seed, "config", "user.name", "t")
    git(seed, "config", "user.email", "t@example.com")
    (seed / "champion.txt").write_text("gen622\n")
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "gen622")
    git(seed, "push", "-q", "origin", "HEAD:main")
    # CI の作業場所：この時点の main を取り出す（待たされた selfplay の回と同じ）
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "config", "user.name", "t")
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "pull.rebase", "true")
    return origin, seed, work


def run(work, tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    gh = fake / "gh"
    gh.write_text('#!/usr/bin/env bash\necho "gh $*" >> "$GH_LOG"\nexit 1\n')
    gh.chmod(0o755)
    env = dict(
        os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}", GH_LOG=str(tmp_path / "gh.log")
    )
    return subprocess.run(
        ["bash", str(SCRIPT), "champion", "t"],
        check=False,
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )


def test_same_change_already_in_main_is_success(tmp_path):
    origin, seed, work = setup(tmp_path)
    # 先の回が同じチャンピオンを main に入れた
    (seed / "champion.txt").write_text("gen633\n")
    git(seed, "commit", "-q", "-am", "gen633 (先の回)")
    git(seed, "push", "-q", "origin", "HEAD:main")
    # 待たされた回も、古い main の上で同じ差し替えをする
    (work / "champion.txt").write_text("gen633\n")
    git(work, "commit", "-q", "-am", "gen633 (待たされた回)")

    r = run(work, tmp_path)

    assert r.returncode == 0, r.stdout + r.stderr
    assert "もう main に入っていました" in r.stdout
    assert not (tmp_path / "gh.log").exists(), "差が無いのに PR を作ろうとした"
    assert git(origin, "for-each-ref", "refs/heads/auto/") == "", "差が無いのにブランチを残した"


def test_new_change_goes_to_pr(tmp_path):
    origin, _seed, work = setup(tmp_path)
    (work / "champion.txt").write_text("gen640\n")
    git(work, "commit", "-q", "-am", "gen640")

    r = run(work, tmp_path)

    # にせものの gh は失敗するので終了コード 1。PR を作ろうとしたこと・ブランチを片付けたことを見る
    assert r.returncode == 1
    assert "gh pr create" in (tmp_path / "gh.log").read_text()
    assert git(origin, "for-each-ref", "refs/heads/auto/") == ""
