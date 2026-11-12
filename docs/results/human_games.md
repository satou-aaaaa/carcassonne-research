# 人との対局のまとめ（自動）

対戦ページから送ってもらった棋譜（data/human_games.jsonl）の集計。`python scripts/human_games.py report` で作り直す。

受け取った対局: 1局

| AIの強さ | 局数 | 人の勝ち | 引き分け | 人から見た平均得点差 | うちヒント等あり |
|---|---:|---:|---:|---:|---:|
| strong | 1 | 0 | 0 | -41.0 | 1 |

## 対局の一覧（押すと一手ずつ再生）

- [1局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1): 人（先手）87 − AI 128（strong、70手）

## AIの読みが外れた人の手（AIの見積もりが大きく下がった順）

AI視点の評価（最新チャンピオンの線形評価、単位は得点差）が、人の手の直前と直後でどれだけ下がったか。大きいものは、AIがその手の価値を低く見ていた候補（弱点探しの出発点）。

対局の番号を押すと、対戦ページでその手の直前から一手ずつ再生できる。

| 対局 | 手数 | 置いた場所 (x, y) | 下がり幅 |
|---:|---:|---|---:|
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=44) | 45 | (3, -1) | +9.8 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=22) | 23 | (2, 1) | +6.3 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=30) | 31 | (7, -1) | +6.3 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=38) | 39 | (5, -4) | +6.0 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=58) | 59 | (11, -1) | +5.1 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=54) | 55 | (11, -2) | +4.7 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=40) | 41 | (10, -2) | +4.1 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=36) | 37 | (7, -3) | +4.0 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=8) | 9 | (-2, 2) | +3.9 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=18) | 19 | (1, -1) | +3.9 |
