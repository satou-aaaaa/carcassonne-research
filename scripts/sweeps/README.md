# 対局実験のスクリプト

`docs/EXPERIMENTS.md` の各表を再現するためのシェルスクリプトです。番号は実験の順番で、
どの表に対応するかは `docs/EXPERIMENTS.md` の「再現:」の行に書いてあります。

- どこから実行してもリポジトリ直下に移動してから動きます（例: `bash scripts/sweeps/sweep18.sh`）。
- 多くは `PY`（Python の実行ファイル）と `WORKERS`（並列数）を環境変数で上書きできます。
- ログは `runs/` に出ます（`runs/` は git に入れません）。
- `sweep1.sh`〜`sweep8.sh` は初期のもので、Python は `PY`（既定は `python`）で切り替えられますが、並列数は固定です。
