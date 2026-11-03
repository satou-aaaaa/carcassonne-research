"""scripts/gh_retry.sh（gh の一時的な失敗のやり直し）を、にせものの gh で確かめる。

2026-11-03 の selfplay は、Issue を作る要求が `HTTP 504: 504 Gateway Timeout` で1回返っただけで落ちた。
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "gh_retry.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash が要る")

FAKE_GH = r"""#!/usr/bin/env bash
echo "gh $*" >> "$GH_LOG"
n=$(grep -c . "$GH_LOG")
case "$1 $2" in
  "issue create")
    touch "$GH_LOG.created"   # 504 でも GitHub 側ではできていることがある
    if [ "${FAKE_MODE:-}" = 504 ]; then echo "HTTP 504: 504 Gateway Timeout (https://api.github.com/graphql)" >&2; exit 1; fi
    echo "https://github.com/o/r/issues/7" ;;
  "api repos/o/r/issues?state=open&per_page=100")
    [ -e "$GH_LOG.created" ] && echo "https://github.com/o/r/issues/7"; true ;;
  "issue close")
    if [ "${FAKE_MODE:-}" = 404 ]; then echo "HTTP 404: Not Found" >&2; exit 1; fi
    if [ "$n" -le 1 ]; then echo "HTTP 502: Bad Gateway" >&2; exit 1; fi ;;
esac
"""


def sh(tmp_path, script, **env):
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    (d / "gh").write_text(FAKE_GH)
    (d / "gh").chmod(0o755)
    (tmp_path / "body.md").write_text("本文\n")
    e = dict(os.environ, PATH=f"{d}{os.pathsep}{os.environ['PATH']}", GH_LOG=str(tmp_path / "log"),
             GITHUB_REPOSITORY="o/r", GH_RETRY_WAIT="0", **env)  # fmt: skip
    return subprocess.run(["bash", "-c", f'source "{LIB}"; {script}'], cwd=tmp_path, env=e,
                          capture_output=True, text=True, check=False)  # fmt: skip


def log(tmp_path):
    return (tmp_path / "log").read_text().splitlines()


def test_transient_error_is_retried(tmp_path):
    r = sh(tmp_path, "ghr gh issue close 3")
    assert r.returncode == 0, r.stderr
    assert len(log(tmp_path)) == 2
    assert "やり直します" in r.stderr


def test_client_error_is_not_retried(tmp_path):
    """4xx はやり直しても直らない。すぐ失敗にする（本物の失敗を隠さない）。"""
    r = sh(tmp_path, "ghr gh issue close 3", FAKE_MODE="404")
    assert r.returncode != 0
    assert len(log(tmp_path)) == 1


def test_gives_up_after_the_limit(tmp_path):
    r = sh(
        tmp_path,
        "ghr gh issue create --title t --body-file body.md",
        FAKE_MODE="504",
        GH_RETRY_TRIES="3",
    )
    assert r.returncode != 0
    assert len(log(tmp_path)) == 3


def test_issue_create_once_does_not_duplicate_after_504(tmp_path):
    r = sh(tmp_path, 'gh_issue_create_once "題" body.md', FAKE_MODE="504")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "https://github.com/o/r/issues/7"
    assert sum(c.startswith("gh issue create") for c in log(tmp_path)) == 1, (
        "やり直しで Issue を2件作った"
    )
