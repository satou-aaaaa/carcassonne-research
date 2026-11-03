"""scripts/merge_via_pr.sh を、にせものの gh で試しに動かして確かめる（GitHub には何もしない）。

本物の CI で初めて動いて落ちる、をなくすためのもの。流れ（検査を起こす→待つ→PR→マージ）と、
失敗したときに main へ入れないこと・一時的な失敗（504）でやり直すことを見る。
"""

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
    (seed / "docs").mkdir()
    (seed / "docs/champion.txt").write_text("gen622\n")
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


FAKE_GH = r"""#!/usr/bin/env bash
# にせものの gh。呼ばれた引数を GH_LOG に書き、FAKE_* の設定どおりに答える
echo "gh $*" >> "$GH_LOG"
once() {  # FAKE_FAIL_ONCE に書いたコマンドは、1回目だけ 504 で失敗する
  local key=$1 mark="$GH_LOG.$1"
  if [[ " ${FAKE_FAIL_ONCE:-} " == *" $key "* ]] && [ ! -e "$mark" ]; then
    touch "$mark"; echo "HTTP 504: 504 Gateway Timeout (https://api.github.com/graphql)" >&2; exit 1
  fi
}
case "$1 $2" in
  "workflow run") once dispatch; echo "https://github.com/o/r/actions/runs/$((RANDOM + 100))" ;;
  "run view") echo "completed ${FAKE_CONCLUSION:-success} $(git rev-parse HEAD)" ;;
  "pr list") [ -e "$GH_LOG.pr" ] && echo "https://github.com/o/r/pull/1"; true ;;
  "pr create") touch "$GH_LOG.pr"; once pr_create; echo "https://github.com/o/r/pull/1" ;;
  "pr merge") once pr_merge; true ;;
  "pr view") echo MERGED ;;
  "api -X") echo queued ;;
  *) echo "知らない gh の呼び方: $*" >&2; exit 2 ;;
esac
"""


def run(work, tmp_path, **fake):
    fake_dir = tmp_path / "bin"
    fake_dir.mkdir(exist_ok=True)
    gh = fake_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    env = dict(
        os.environ,
        PATH=f"{fake_dir}{os.pathsep}{os.environ['PATH']}",
        GH_LOG=str(tmp_path / "gh.log"),
        GITHUB_REPOSITORY="o/r",
        GH_RETRY_WAIT="0",
        CHECK_POLL="0",
        **fake,
    )
    return subprocess.run(
        ["bash", str(SCRIPT), "champion", "t"],
        check=False,
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )


def calls(tmp_path):
    return (tmp_path / "gh.log").read_text().splitlines()


def new_change(tmp_path, path="docs/champion.txt"):
    origin, _seed, work = setup(tmp_path)
    (work / path).parent.mkdir(parents=True, exist_ok=True)
    (work / path).write_text("gen640\n")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "gen640")
    return origin, work


def test_same_change_already_in_main_is_success(tmp_path):
    origin, seed, work = setup(tmp_path)
    # 先の回が同じチャンピオンを main に入れた
    (seed / "docs/champion.txt").write_text("gen633\n")
    git(seed, "commit", "-q", "-am", "gen633 (先の回)")
    git(seed, "push", "-q", "origin", "HEAD:main")
    # 待たされた回も、古い main の上で同じ差し替えをする
    (work / "docs/champion.txt").write_text("gen633\n")
    git(work, "commit", "-q", "-am", "gen633 (待たされた回)")

    r = run(work, tmp_path)

    assert r.returncode == 0, r.stdout + r.stderr
    assert "もう main に入っていました" in r.stdout
    assert not (tmp_path / "gh.log").exists(), "差が無いのに PR を作ろうとした"
    assert git(origin, "for-each-ref", "refs/heads/auto/") == "", "差が無いのにブランチを残した"


def test_checks_run_before_the_pr_and_then_it_merges(tmp_path):
    """GITHUB_TOKEN の PR では pull_request の実行が承認待ちになり、すぐマージするとジョブ0件の failure が残った
    （2026-10-25〜11-03、auto/* で45回）。[skip ci] でそれを作らせず、検査は workflow_dispatch で回してから入れる。"""
    origin, work = new_change(tmp_path)

    r = run(work, tmp_path)

    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(tmp_path)
    order = [c.split()[1] + " " + c.split()[2] for c in log]
    assert order.index("workflow run") < order.index("pr create") < order.index("pr merge")
    assert any(c.startswith("gh workflow run test.yml --ref auto/champion-") for c in log)
    assert any(c.startswith("gh workflow run secret-scan.yml --ref auto/champion-") for c in log)
    pushed = git(origin, "for-each-ref", "--format=%(refname)", "refs/heads/auto/").split()
    assert len(pushed) == 1
    assert "[skip ci]" in git(origin, "log", "-1", "--format=%B", pushed[0])


def test_failed_check_keeps_it_out_of_main(tmp_path):
    origin, work = new_change(tmp_path)

    r = run(work, tmp_path, FAKE_CONCLUSION="failure")

    assert r.returncode == 1
    assert "検査が通らなかった" in r.stdout
    assert not any(c.startswith("gh pr create") for c in calls(tmp_path))
    assert git(origin, "for-each-ref", "refs/heads/auto/") == "", "通らなかったブランチを残した"


def test_only_generated_files_go_in(tmp_path):
    """自動の PR は生成物だけ（CodeQL を回さないのは、調べる対象のコードが入らないから）。"""
    _origin, work = new_change(tmp_path, path="src/carcassonne/x.py")

    r = run(work, tmp_path)

    assert r.returncode == 1
    assert "生成物でないファイル" in r.stdout
    assert not (tmp_path / "gh.log").exists()


def test_transient_504_is_retried_without_a_second_pr(tmp_path):
    """GitHub の API の 504（2026-11-03）で落とさない。作る要求は、やり直す前に既にできていないか探す。"""
    _origin, work = new_change(tmp_path)

    r = run(work, tmp_path, FAKE_FAIL_ONCE="dispatch pr_create pr_merge")

    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(tmp_path)
    assert sum(c.startswith("gh pr create") for c in log) == 1, "PR を2回作ろうとした"
    assert "マージしました" in r.stdout
