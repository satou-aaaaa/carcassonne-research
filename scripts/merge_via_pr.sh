#!/usr/bin/env bash
# CI（GitHub Actions）が作ったコミットを、検査を通してから PR で main に入れる。
#
#   bash scripts/merge_via_pr.sh <ブランチ名の頭> <PRのタイトル> [本文ファイル]
#
# main は Ruleset で「PR 必須」なので、直接 push すると断られる（2026-10-21〜22 の selfplay の失敗、Issue #66）。
# 流れ:
#   1. 今の HEAD のコミットを auto/<頭>-<日時> に push する。中身は生成物（AUTO_PATHS）だけに限る。
#   2. そのブランチで検査（CHECK_WORKFLOWS: test.yml・secret-scan.yml）を workflow_dispatch で起こし、終わるまで待つ。
#      どれかが成功でなければ、PR を作らずにブランチを消して終了コード 1（ci-failure-issue.yml が Issue で知らせる）。
#   3. PR を作ってすぐ squash マージし、ブランチを消す。GitHub Pages の公開を起こす（要 pages: write）。
#
# なぜ自分で検査を起こすか: GITHUB_TOKEN で作った PR の pull_request の実行は「承認待ち」になり、動かない
# （GitHub Docs「Triggering a workflow」）。すぐマージしてブランチを消すと、承認待ちの実行がジョブ0件の
# failure として残る（2026-10-25〜11-03 に auto/* の test・CodeQL・Secret scan で計45回）。そこで、
# コミットに [skip ci] を付けてその承認待ちの実行を作らせず（GitHub Docs「Skipping workflow runs」）、
# 代わりに GITHUB_TOKEN でも動く workflow_dispatch で同じ検査を回し、その結果でマージを決める。
# CodeQL（python・actions を調べる）は、生成物だけのこの変更には調べる対象が無いので回さない（AUTO_PATHS で保証）。
#
# 呼ぶワークフローには actions: write（検査を起こす）・contents: write・pull-requests: write・pages: write が要る。
set -euo pipefail

prefix=${1:?ブランチ名の頭}
title=${2:?PRのタイトル}
body_file=${3:-}

# 自動で入れてよいのは生成物だけ（重み・公開ページ・クイズ・コツ集の保留メモ・人から受け取った棋譜）
AUTO_PATHS=${AUTO_PATHS:-'^(docs/|models/eval_champion\.(npy|json)$|data/puzzles\.json$|data/tips_blocked\.json$|data/human_games\.jsonl$)'}
CHECK_WORKFLOWS=${CHECK_WORKFLOWS:-"test.yml secret-scan.yml"}
CHECK_TIMEOUT=${CHECK_TIMEOUT:-2400} # 検査を待つ上限（秒）
CHECK_POLL=${CHECK_POLL:-20}
# shellcheck source=scripts/gh_retry.sh
source "$(dirname "$0")/gh_retry.sh"

git pull -q --rebase origin main
# 待っているあいだに、同じ中身が先に main へ入っていることがある（selfplay は同時に1本しか回らず、
# 待たされた回は古い main を取り出したまま走る）。rebase で空になったら入れる物は無いので、成功で終える。
# ここで止めないと、差の無い PR を作ろうとして失敗する（Issue #92、2026-10-28）。
if git diff --quiet FETCH_HEAD HEAD; then
  echo "同じ中身がもう main に入っていました。PR は作りません"
  exit 0
fi
other=$(git diff --name-only FETCH_HEAD HEAD | grep -vE "$AUTO_PATHS" || true)
if [ -n "$other" ]; then
  echo "::error title=生成物でないファイルが入っています::自動の PR に入れてよいのは生成物だけです（AUTO_PATHS）: $(echo "$other" | tr '\n' ' ')"
  exit 1
fi

# PR の pull_request で承認待ちの実行を作らせない（検査は下で workflow_dispatch で回す）
git commit -q --amend -m "$(git log -1 --format=%B)" -m "[skip ci] 検査は scripts/merge_via_pr.sh が workflow_dispatch で回す"
branch="auto/${prefix}-$(date -u +%Y%m%d-%H%M%S)"
git push -q origin "HEAD:refs/heads/${branch}"
sha=$(git rev-parse HEAD)
cleanup() { git push -q origin --delete "$branch" || true; }

# 検査を起こす。gh は起こした実行の URL を出す。出なければ一覧から探す
dispatch() {
  local wf=$1 out id="" i=0
  out=$(ghr gh workflow run "$wf" --ref "$branch" 2>&1) || { echo "$out" >&2; return 1; }
  id=$(grep -oE '/actions/runs/[0-9]+' <<<"$out" | head -n1 | grep -oE '[0-9]+$' || true)
  while [ -z "$id" ] && [ "$i" -lt 15 ]; do
    i=$((i + 1))
    sleep "$CHECK_POLL"
    id=$(ghr gh run list --workflow "$wf" --branch "$branch" --event workflow_dispatch --limit 1 \
      --json databaseId --jq '.[0].databaseId // empty' || true)
  done
  [ -n "$id" ] || { echo "$wf の実行が見つかりません" >&2; return 1; }
  echo "$id"
}

declare -A runs=()
for wf in $CHECK_WORKFLOWS; do
  if ! runs[$wf]=$(dispatch "$wf"); then
    echo "::error title=検査を起こせませんでした::$wf（ワークフローに workflow_dispatch と、呼ぶ側に actions: write が要る）"
    cleanup
    exit 1
  fi
  echo "検査 $wf: ${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${runs[$wf]}"
done

deadline=$(($(date +%s) + CHECK_TIMEOUT))
failed=""
for wf in $CHECK_WORKFLOWS; do
  id=${runs[$wf]}
  while :; do
    state=$(ghr gh run view "$id" --json status,conclusion,headSha --jq '"\(.status) \(.conclusion) \(.headSha)"' || echo "unknown")
    read -r status conclusion head <<<"$state"
    if [ "$status" = completed ]; then
      if [ "$conclusion" != success ]; then failed="$failed $wf($conclusion)"; fi
      if [ "$head" != "$sha" ]; then failed="$failed $wf(別のコミット $head)"; fi
      break
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      failed="$failed $wf(時間切れ)"
      break
    fi
    sleep "$CHECK_POLL"
  done
done
if [ -n "$failed" ]; then
  echo "::error title=検査が通らなかったので main に入れません::${failed# }（実行の URL は上に出しています。ブランチは消します）"
  cleanup
  exit 1
fi
echo "検査はすべて成功しました: $CHECK_WORKFLOWS"

if [ -z "$body_file" ]; then
  body_file=$(mktemp)
  echo "CI が自動で作った変更です（${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}）。" > "$body_file"
fi
{ echo; echo "検査（workflow_dispatch で実行し、すべて成功）:"; for wf in $CHECK_WORKFLOWS; do echo "- $wf: ${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${runs[$wf]}"; done; } >> "$body_file"

python3 "$(dirname "$0")/cap_body.py" "$body_file"  # 本文の上限（65536 文字）に収める（#110）
# 作る要求が一時的な失敗で返っても作れていることがあるので、やり直す前にそのブランチの PR を探す
url=""
errf=$(mktemp)
for ((i = 1; i <= GH_RETRY_TRIES; i++)); do
  url=$(gh pr list --head "$branch" --state open --json url --jq '.[0].url // empty' 2>/dev/null || true)
  [ -n "$url" ] && break
  if url=$(gh pr create --base main --head "$branch" --title "$title" --body-file "$body_file" 2>"$errf"); then break; fi
  url=""
  cat "$errf" >&2
  gh_transient "$(cat "$errf")" || break
  sleep "$GH_RETRY_WAIT"
done
rm -f "$errf"
if [ -z "$url" ]; then
  echo "::error title=PRを作れませんでした::上の gh のメッセージを見る。よくある原因は Settings → Actions → General の「Allow GitHub Actions to create and approve pull requests」が切れていると作れません"
  cleanup
  exit 1
fi
merged() { [ "$(ghr gh pr view "$url" --json state --jq .state || true)" = MERGED ]; }
for i in 1 2 3; do
  # 一時的な失敗で返っても、マージは済んでいることがある
  if ghr gh pr merge "$url" --squash --delete-branch --body "CI が自動で作り、検査（$CHECK_WORKFLOWS）を通した変更です。" || merged; then
    echo "マージしました: $url"
    # 公開を起こせなければ、ページが古いままなのでジョブを失敗にして知らせる
    for j in 1 2 3; do
      ghr gh api -X POST "repos/${GITHUB_REPOSITORY}/pages/builds" --jq .status && exit 0
      sleep 10
    done
    echo "::error title=公開（GitHub Pages）を起こせませんでした::マージは済み（$url）。Actions の pages build を手で回すか、次に main へ入る変更で公開されます"
    exit 1
  fi
  sleep 10
done
echo "::error title=PRをマージできませんでした::$url"
exit 1
