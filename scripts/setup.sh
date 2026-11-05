#!/usr/bin/env bash
# 開発の準備を1コマンドで行う。人も、どの AI も同じ手順で動かせるようにするためのもの。何度実行してもよい。
#   使い方: bash scripts/setup.sh   （Windows は Git Bash で）
# .venv を作って requirements.txt を入れる。以後は .venv の Python で動かす（README「環境構築」）。
# Claude Code のクラウドセッションでは .claude/settings.json の SessionStart フックが自動で呼び、.venv を PATH の先頭に置く。
# CI の Setup check（共通部品 satou-aaaaa/shared-workflows）が、まっさらな環境でこれが通るかを確かめる。
# ひな形の版: 4（上げたら写しの版も上げる。shared-workflows の scripts/drift-check.mjs が古い写しを週次まとめに出す）
#   2: 依存は毎回 npm ci・ブラウザが無ければ止める・このシェルで要る操作（nvm use・export）を最後に出す（shared-workflows incidents/2026-11-03-setup-false-ready.md）
#   3: nvm.sh を --no-use で読む（.nvmrc の版が入っていないと、読んだだけで何も言わずに止まっていた。shared-workflows incidents/2026-11-04-setup-nvm-silent-stop.md）
#   4: ブラウザの場所はファイルかも見る（-x だけだとフォルダでも通った。2026-11-05 CodeRabbit が bunshi-tsukuri #1 で指摘）
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "✗ $*" >&2; exit 1; }
runnable() { [ -f "$1" ] && [ -x "$1" ]; }   # 動かせるファイルか（フォルダも -x では通るので -f も見る）
# 準備のあと、このシェルで打つ必要がある操作。1つでもあれば最後に「✓」を出さない
todo=()
# 環境変数を以後のコマンドに渡す。クラウドセッションは CLAUDE_ENV_FILE に書く。
# それ以外は子のプロセスから親のシェルを変えられないので、打つ操作として最後に出す
session_env() {
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then echo "export $1" >> "$CLAUDE_ENV_FILE"; else todo+=("export $1"); fi
}

# Python（版は .python-version。pyenv・uv・mise などはこのファイルを読む。pyproject.toml は 3.11 以上）
py=""
for c in python3 python py; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then py=$c; break; fi
done
[ -n "$py" ] || fail "Python $(cat .python-version)（3.11 以上）が要る（https://www.python.org/ ）"

[ -d .venv ] || "$py" -m venv .venv
if [ -x .venv/bin/python ]; then vpy=.venv/bin/python; else vpy=.venv/Scripts/python.exe; fi   # Windows は Scripts
"$vpy" -m pip install -q --disable-pip-version-check -r requirements.txt
vbin=$(dirname "$vpy")
# .venv の Python を以後のコマンドで使う。クラウドは PATH の先頭に置き、それ以外は打つ操作として出す
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then session_env "PATH=\"$PWD/$vbin:\$PATH\""; else todo+=(". $vbin/activate"); fi

next="$vpy scripts/check.py --quick"
if [ ${#todo[@]} -gt 0 ]; then
  echo "△ 準備はできた。ただし、このシェルで先に次を打つ（打たないと古い Node や別のブラウザで動く）:"
  printf '    %s\n' "${todo[@]}"
  echo "  そのあと: $next"
else
  echo "✓ 準備できた。次は: $next"
fi
