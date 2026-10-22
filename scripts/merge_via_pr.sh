#!/usr/bin/env bash
# CI（GitHub Actions）が作ったコミットを、PR を通して main に入れる。
#
#   bash scripts/merge_via_pr.sh <ブランチ名の頭> <PRのタイトル> [本文ファイル]
#
# main は Ruleset で「PR 必須」なので、直接 push すると断られる（2026-10-21〜22 の selfplay の失敗、Issue #66）。
# 今の HEAD のコミットを auto/<頭>-<日時> に push し、PR を作ってすぐ squash マージし、ブランチを消す。
# 入れられなかったら終了コード 1（ci-failure-issue.yml が Issue で知らせる）。
# GITHUB_TOKEN で入れたコミットでは GitHub Pages の公開が自動で走らないので、マージ後に公開を起こす（要 pages: write）。
# この PR では CI（test.yml）が走らない（GITHUB_TOKEN の仕様）。前の直接 push と同じで、中身は生成物（重み・docs）だけ。
set -euo pipefail

prefix=${1:?ブランチ名の頭}
title=${2:?PRのタイトル}
body_file=${3:-}

git pull -q --rebase origin main
branch="auto/${prefix}-$(date -u +%Y%m%d-%H%M%S)"
git push -q origin "HEAD:refs/heads/${branch}"

if [ -z "$body_file" ]; then
  body_file=$(mktemp)
  echo "CI が自動で作った変更です（${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}）。" > "$body_file"
fi

if ! url=$(gh pr create --base main --head "$branch" --title "$title" --body-file "$body_file"); then
  echo "::error title=PRを作れませんでした::Settings → Actions → General の「Allow GitHub Actions to create and approve pull requests」が切れていると作れません"
  git push -q origin --delete "$branch" || true
  exit 1
fi
for i in 1 2 3; do
  if gh pr merge "$url" --squash --delete-branch; then
    echo "マージしました: $url"
    gh api -X POST "repos/${GITHUB_REPOSITORY}/pages/builds" --jq .status ||
      echo "::warning::公開（GitHub Pages）を起こせませんでした。次に main へ入る変更で公開されます"
    exit 0
  fi
  sleep 10
done
echo "::error title=PRをマージできませんでした::$url"
exit 1
