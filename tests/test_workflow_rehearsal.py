"""selfplay・AI content の「知らせ」の手順を、ワークフローの run: そのままで、にせものの gh で通しで動かす（GitHub には何もしない）。

selfplay の失敗が1週間で3回続いた（10/28 #92 差の無い PR・11/02 #110 本文が長すぎ・11/03 #118 API の 504）。
3回とも、約5時間の自己対戦のあと・採用が出た回にしか動かない手順で、テストでも普段の実行でも通らず、
本番で初めて落ちた。直すたびに、その1つの症状だけを静的に調べる検査を足していた。

ここでは、その手順を毎回の PR で本番と同じ中身のまま動かす。にせものの gh は本物の決まり
（本文 65536 文字・題 256 文字まで）を守り、書き込みは1回目に 504 を返す。
新しく gh を呼ぶ手順を足したら、REHEARSED に足してここで動かす（test_every_gh_step_is_rehearsed が見る）。
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash が要る")

# 動かして確かめる手順（ワークフロー → 手順の名前）。merge_via_pr.sh を呼ぶ手順は tests/test_merge_via_pr.py が動かす
REHEARSED = {
    "selfplay.yml": [
        "学習ページ（コツ集・クイズ）を最新チャンピオンで作り直す",
        "新しく採用が出たら Issue で知らせる",
    ],
    "ai-content.yml": [
        "答えが変わったクイズを Issue で知らせる",
        "言い切りが合わずコツ集を前の版で残したら Issue で知らせる",
    ],
}

GH_BODY_MAX = 65536  # GitHub の Issue・PR・コメントの本文の上限
GH_TITLE_MAX = 256

FAKE_GH = r"""#!/usr/bin/env bash
# にせものの gh。呼ばれた引数を GH_LOG に書き、本物の上限を守り、書き込みは1回目だけ 504 で失敗する
echo "gh $*" >> "$GH_LOG"
args=("$@")
body_file=""; title=""; body=""
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[i]}" in
    --body-file) body_file=${args[i+1]} ;;
    --title) title=${args[i+1]} ;;
    --body) body=${args[i+1]} ;;
  esac
done
if [ -n "$body_file" ] && [ "$(python3 -c 'import sys;print(len(open(sys.argv[1],encoding="utf-8").read()))' "$body_file")" -gt BODY_MAX ]; then
  echo "GraphQL: Body is too long (maximum is BODY_MAX characters) (createIssue)" >&2; exit 1
fi
[ "${#body}" -le BODY_MAX ] || { echo "Body is too long" >&2; exit 1; }
[ "${#title}" -le TITLE_MAX ] || { echo "Title is too long" >&2; exit 1; }
write_once() {  # 書き込みは種類ごとに1回目だけ 504
  local mark="$GH_LOG.$1"
  if [ ! -e "$mark" ]; then
    touch "$mark"; echo "HTTP 504: 504 Gateway Timeout (https://api.github.com/graphql)" >&2; exit 1
  fi
}
case "$1 $2" in
  # 作る要求は、GitHub 側で作れたのに 504 が返る（いちばん困る形）。やり直しで2件目を作ってはいけない
  "issue create") touch "$GH_LOG.created"; write_once create; echo "https://github.com/o/r/issues/99" ;;
  "issue close") write_once close ;;
  "issue edit") write_once edit ;;
  "issue comment") write_once comment ;;
  "workflow run") write_once dispatch ;;
  "api repos/o/r/issues?state=open&per_page=100")
    # 開いている Issue を探す：前からある知らせは FAKE_OPEN の番号で答える
    jq=""; for ((i = 0; i < ${#args[@]}; i++)); do [ "${args[i]}" = --jq ] && jq=${args[i+1]}; done
    if [[ "$jq" == *"| .html_url" ]]; then
      [ -e "$GH_LOG.created" ] && echo "https://github.com/o/r/issues/99"; true
    elif [ -n "${FAKE_OPEN:-}" ]; then echo "$FAKE_OPEN"; fi ;;
  *) echo "知らない gh の呼び方: $*" >&2; exit 2 ;;
esac
""".replace("BODY_MAX", str(GH_BODY_MAX)).replace("TITLE_MAX", str(GH_TITLE_MAX))


def steps(wf: str) -> dict[str, str]:
    """ワークフローの手順の名前 → run: の中身（インデントを外したもの）。"""
    lines = (WF / wf).read_text(encoding="utf-8").splitlines()
    out, name = {}, None
    for i, line in enumerate(lines):
        m = re.match(r"\s*- name: (.+)$", line)
        if m:
            name = m.group(1).strip()
        m = re.match(r"(\s*)run: \|\s*$", line)
        if m and name:
            ind = len(m.group(1))
            body = []
            for nxt in lines[i + 1 :]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= ind:
                    break
                body.append(nxt)
            pad = min(len(b) - len(b.lstrip()) for b in body if b.strip())
            out[name] = "\n".join(b[pad:] for b in body) + "\n"
            name = None
    return out


def rehearse(tmp_path: Path, wf: str, name: str, **env) -> tuple[subprocess.CompletedProcess, str]:
    """手順を tmp_path を作業場所にして動かす。返り値は（結果, gh の呼ばれ方）。"""
    script = steps(wf)[name].replace("${{ github.repository }}", "o/r")
    assert "${{" not in script, f"{name}: 置き換えていない式がある: {script}"
    (tmp_path / "scripts").mkdir(exist_ok=True)
    for f in ("gh_retry.sh", "cap_body.py"):
        shutil.copy(ROOT / "scripts" / f, tmp_path / "scripts" / f)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "gh").write_text(FAKE_GH)
    (bin_dir / "python").write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n')
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    log = tmp_path / "gh.log"
    full_env = dict(
        os.environ,
        PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        GH_LOG=str(log),
        GH_RETRY_WAIT="0",
        GITHUB_REPOSITORY="o/r",
        **env,
    )
    r = subprocess.run(
        ["bash", "-e", "-c", script],
        check=False,
        cwd=tmp_path,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return r, (log.read_text() if log.exists() else "")


def test_every_gh_step_is_rehearsed() -> None:
    """selfplay・AI content で gh を呼ぶ手順は、ここで動かすか merge_via_pr.sh（別のテストで動かす）に任せる。"""
    missing = []
    for wf, names in REHEARSED.items():
        for name, body in steps(wf).items():
            if not re.search(r"(?<![\w-])gh |gh_issue_create_once", body):
                continue
            if name in names or "scripts/merge_via_pr.sh" in body:
                continue
            missing.append(f"{wf}: {name}")
        for n in names:
            assert n in steps(wf), f"{wf} に手順「{n}」が無い（名前を変えたらここも直す）"
    assert not missing, (
        "gh を呼ぶ手順を足したら tests/test_workflow_rehearsal.py で動かす:\n" + "\n".join(missing)
    )


def _selfplay_state(tmp_path: Path, progress_chars: int) -> None:
    loop = tmp_path / "state" / "loop"
    loop.mkdir(parents=True)
    hist = [{"attempt": a, "promoted": a == 950, "win_rate": 0.55} for a in range(940, 951)]
    (loop / "state.json").write_text(json.dumps({"history": hist}))
    row = "| 950 | gen950 | 0.550 | 採用 |\n"
    (loop / "progress.md").write_text(
        "# 成績表\n" + row * (progress_chars // len(row) + 1), encoding="utf-8"
    )
    (tmp_path / "before.txt").write_text("0\n")


def test_selfplay_notify_survives_long_body_and_504(tmp_path: Path) -> None:
    """採用の知らせ：成績表が上限より長くても・API が 504 を返しても、Issue は1件だけでき、前の知らせが閉じる。"""
    _selfplay_state(tmp_path, progress_chars=GH_BODY_MAX + 20000)
    r, log = rehearse(
        tmp_path, "selfplay.yml", "新しく採用が出たら Issue で知らせる", FAKE_OPEN="5"
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert log.count("gh issue create") == 1, log  # 504 のあとは作れたかを探してから。2件にしない
    assert "gh issue close 5" in log, log


def test_selfplay_notify_does_nothing_without_promotion(tmp_path: Path) -> None:
    _selfplay_state(tmp_path, progress_chars=100)
    (tmp_path / "before.txt").write_text("1\n")
    r, log = rehearse(tmp_path, "selfplay.yml", "新しく採用が出たら Issue で知らせる")
    assert r.returncode == 0, r.stdout + r.stderr
    assert log == "", log


def test_selfplay_dispatches_ai_content_through_504(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "refresh_ai_content.py").write_text("print('stale')\n")
    r, log = rehearse(
        tmp_path, "selfplay.yml", "学習ページ（コツ集・クイズ）を最新チャンピオンで作り直す"
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert log.count("gh workflow run ai-content.yml") == 2, log  # 504 を1回やり直す


def _puzzles(tmp_path: Path, disputed: int) -> None:
    (tmp_path / "data").mkdir(exist_ok=True)
    ps = [
        {"id": f"s{i}t1", "title": "問" * 40, "disputed": "選択肢3の点差が最大 " * 30}
        for i in range(disputed)
    ]
    (tmp_path / "data" / "puzzles.json").write_text(json.dumps(ps, ensure_ascii=False))


@pytest.mark.parametrize("open_num", ["", "7"])
def test_ai_content_quiz_notice(tmp_path: Path, open_num: str) -> None:
    """食い違うクイズの知らせ：多くても本文の上限に収まり、504 でも落ちない。前からある1件は書き直す。"""
    _puzzles(tmp_path, disputed=400)
    r, log = rehearse(
        tmp_path, "ai-content.yml", "答えが変わったクイズを Issue で知らせる", FAKE_OPEN=open_num
    )
    assert r.returncode == 0, r.stdout + r.stderr
    if open_num:
        assert "gh issue edit 7" in log and "gh issue create" not in log, log
    else:
        assert log.count("gh issue create") == 1, log


def test_ai_content_quiz_notice_closes_when_resolved(tmp_path: Path) -> None:
    _puzzles(tmp_path, disputed=0)
    r, log = rehearse(
        tmp_path, "ai-content.yml", "答えが変わったクイズを Issue で知らせる", FAKE_OPEN="7"
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "gh issue close 7" in log, log


@pytest.mark.parametrize("blocked", [True, False])
def test_ai_content_tips_notice(tmp_path: Path, blocked: bool) -> None:
    (tmp_path / "data").mkdir()
    if blocked:
        (tmp_path / "data" / "tips_blocked.json").write_text(
            json.dumps(
                {"ai": {"name": "gen926"}, "failed_claims": ["#farm: 勝った側は草原でも多く取る"]},
                ensure_ascii=False,
            )
        )
    r, log = rehearse(
        tmp_path,
        "ai-content.yml",
        "言い切りが合わずコツ集を前の版で残したら Issue で知らせる",
        FAKE_OPEN="" if blocked else "8",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    if blocked:
        assert log.count("gh issue create") == 1, log
    else:
        assert "gh issue close 8" in log, log
