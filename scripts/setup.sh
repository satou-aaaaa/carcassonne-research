#!/usr/bin/env bash
# 開発の準備を1コマンドで行う。人も、どの AI も同じ手順で動かせるようにするためのもの。何度実行してもよい。
#   使い方: bash scripts/setup.sh   （Windows は Git Bash で）
# .venv を作って requirements.txt を入れる。以後は .venv の Python で動かす（README「環境構築」）。
# Claude Code のクラウドセッションでは .claude/settings.json の SessionStart フックが自動で呼び、.venv を PATH の先頭に置く。
# CI の Setup check（共通部品 satou-aaaaa/shared-workflows）が、まっさらな環境でこれが通るかを確かめる。
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "✗ $*" >&2; exit 1; }
# 環境変数をクラウドセッションの以後のコマンドに渡す（ほかの環境では何もしない）
session_env() { if [ -n "${CLAUDE_ENV_FILE:-}" ]; then echo "export $1" >> "$CLAUDE_ENV_FILE"; fi; }

# Python（版は .python-version。pyenv・uv・mise などはこのファイルを読む。pyproject.toml は 3.11 以上）
py=""
for c in python3 python py; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then py=$c; break; fi
done
[ -n "$py" ] || fail "Python $(cat .python-version)（3.11 以上）が要る（https://www.python.org/ ）"

[ -d .venv ] || "$py" -m venv .venv
if [ -x .venv/bin/python ]; then vpy=.venv/bin/python; else vpy=.venv/Scripts/python.exe; fi   # Windows は Scripts
"$vpy" -m pip install -q --disable-pip-version-check -r requirements.txt
session_env "PATH=\"$PWD/.venv/bin:\$PATH\""

echo "✓ 準備できた。次は: $vpy scripts/check.py --quick"
