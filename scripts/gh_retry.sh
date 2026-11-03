# CI から gh（GitHub の API）を呼ぶときの、一時的な失敗のやり直し。`source scripts/gh_retry.sh` で読み込む。
#
#   ghr gh issue edit 12 --body-file body.md        # 一時的な失敗（5xx・タイムアウト・接続切れ）だけ、間を空けてやり直す
#   url=$(gh_issue_create_once "題" body.md)         # Issue を1件だけ作る（やり直しで2件にしない）
#
# GitHub の API はときどき 502/504 を返す（2026-11-03 の selfplay「新しく採用が出たら Issue で知らせる」が
# `HTTP 504: 504 Gateway Timeout (https://api.github.com/graphql)` で落ちた）。一度の 5xx でジョブを赤にしない。
# 4xx（権限・入力の誤り）はやり直しても直らないので、すぐ失敗にする（本物の失敗は隠さない）。
# 待ち時間は GitHub の「REST API のベストプラクティス」（失敗が続くなら間隔を指数的に延ばし、回数に上限を置く）に従う:
#   https://docs.github.com/en/enterprise-server@3.16/rest/guides/best-practices-for-using-the-rest-api
# 待ち時間は GH_RETRY_WAIT 秒から倍にしていく（テストでは 0 にする）。

GH_RETRY_TRIES=${GH_RETRY_TRIES:-4}
GH_RETRY_WAIT=${GH_RETRY_WAIT:-20}

# 一時的な失敗か（gh のメッセージで見分ける）
gh_transient() {
  grep -qiE 'HTTP 5[0-9][0-9]|Gateway|timed? ?out|timeout|connection reset|unexpected EOF|TLS handshake|temporarily unavailable|Something went wrong|secondary rate limit' <<<"$1"
}

ghr() {
  local i out err wait=$GH_RETRY_WAIT rc
  err=$(mktemp)
  for ((i = 1; i <= GH_RETRY_TRIES; i++)); do
    rc=0
    out=$("$@" 2>"$err") || rc=$?
    if [ "$rc" -eq 0 ]; then
      cat "$err" >&2
      rm -f "$err"
      [ -z "$out" ] || printf '%s\n' "$out"
      return 0
    fi
    cat "$err" >&2
    if ! gh_transient "$(cat "$err")" || [ "$i" -eq "$GH_RETRY_TRIES" ]; then
      rm -f "$err"
      [ -z "$out" ] || printf '%s\n' "$out"
      return "$rc"
    fi
    echo "::warning title=GitHub API の一時的な失敗::${wait} 秒待ってやり直します（${i}/${GH_RETRY_TRIES} 回目）: $*" >&2
    sleep "$wait"
    wait=$((wait * 2))
  done
}

# 題が同じ開いた Issue があればその URL を、無ければ作って URL を出す。
# 作る要求が 5xx で返っても、GitHub 側では作れていることがある。やり直す前に探すので、2件にならない。
gh_issue_create_once() {
  local title=$1 body=$2 i url wait=$GH_RETRY_WAIT err
  python3 "$(dirname "${BASH_SOURCE[0]}")/cap_body.py" "$body" # 本文の上限（65536 文字）に収める（#110）
  err=$(mktemp)
  for ((i = 1; i <= GH_RETRY_TRIES; i++)); do
    url=$(gh api "repos/${GITHUB_REPOSITORY}/issues?state=open&per_page=100" --paginate \
      --jq ".[] | select(.pull_request == null) | select(.title == \"${title//\"/\\\"}\") | .html_url" 2>"$err" | head -n1) || true
    if [ -n "$url" ]; then
      rm -f "$err"
      echo "$url"
      return 0
    fi
    if url=$(gh issue create --title "$title" --body-file "$body" 2>>"$err"); then
      rm -f "$err"
      echo "$url"
      return 0
    fi
    cat "$err" >&2
    if ! gh_transient "$(cat "$err")" || [ "$i" -eq "$GH_RETRY_TRIES" ]; then
      rm -f "$err"
      return 1
    fi
    : >"$err"
    echo "::warning title=GitHub API の一時的な失敗::${wait} 秒待って、Issue ができていないか確かめてからやり直します（${i}/${GH_RETRY_TRIES} 回目）" >&2
    sleep "$wait"
    wait=$((wait * 2))
  done
}
