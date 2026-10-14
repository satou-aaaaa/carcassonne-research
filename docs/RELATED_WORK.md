# 先行研究・既存実装の調査メモ

調査日: 2026-10-05（Web検索・GitHub検索による。Ameneyro・Jappertは本文を読んだが、
チェコ語の学位論文は未読。引用前に必ず原文で確認すること）。

## 論文・学位論文（本文を精読済み: Ameneyro・Jappert）

### Ameneyro, Galván, Kuri Morales (2020) [arXiv:2009.12974](https://arxiv.org/abs/2009.12974)
- 設定: 基本セット・2人対戦・完全情報（山札の順序のみ確率的）。置けないタイルは山札の底に戻して引き直し
  （全局の約2.3%で発生）。※本プロジェクトは公式ルールどおり捨てて引き直す（`docs/RULES.md` 実装上の決定1）ため、
  この点は先行研究と異なる。先手有利のため、同じ山札列で先後を入れ替えて対戦（本プロジェクトも同方式）。
- 比較: vanilla MCTS / MCTS-RAVE / Star2.5（深さ3、手の順序は 都市→修道院→道→置かない→草原 への
  ミープル配置）。MCTS系が Star2.5 に勝ち、vanilla MCTS は MCTS-RAVE より安定。
- 報酬: **勝敗ではなく「予測得点差（virtual score差）」**。引き分け寄りの局面や逆転狙いの差を見分けられる。
- パラメータ: UCT定数 C=3（報酬が得点差スケールのため）、1ステップあたり100回のシミュレーション。
  デフォルト方策は「配置は一様、ミープルは置ける全選択肢＋置かないを一様」。
- 計算量: 1局36〜71分（ICHEC 336ノード）。計算資源が結果を左右する典型例。
- 示唆: 評価関数による打ち切り（ヒューリスティック評価）は今後の課題として提案されている。

### Jappert (2022) 学士論文（バーゼル大）[PDF](https://ai.dmi.unibas.ch/papers/theses/jappert-bachelor-22.pdf)
- 設定: 2人対戦のMCTS。木の形（単一木／配置→ミープル→チャンスの3段／アンサンブル）、
  木方策（Greedy・ε-Greedy・UCT・UCT-Tuned・Boltzmann）、デフォルト方策（ランダム／ヒューリスティック／
  直接ヒューリスティック評価）を比較。
- 結論: **最良は無知識（ドメイン知識なし）のMCTS**。UCT-Tuned＋探索定数の減衰（c'=512/t）＋
  **ランダムロールアウトでミープル配置確率30%**。アンサンブル4本×各750回が人間平均を上回る。
- 所見: ヒューリスティックロールアウトはロールアウト数を犠牲にするため、同じ時間ならランダムの方が強い。
  複数ロールアウト（1葉あたり複数回）は効果なし。バックプロパゲーションの重み付けは悪化。
  1本の木は約1000反復で性能が頭打ちになり、複数の木の多数決（アンサンブル）で上積みできる。
- 本プロジェクトへの反映: 配置→ミープルの2段木、ミープル確率30%のロールアウト、得点差ベース報酬
  （tanh正規化）を採用。実測では決定化4本×100回より **1本×400回の方が強い**（`docs/EXPERIMENTS.md`）。

### その他
| 文献 | 内容 | 状態 |
|---|---|---|
| Charles University (Praha) 学位論文「Umělá inteligence pro hru Carcassonne」（[handle](https://dspace.cuni.cz/handle/20.500.11956/119448)） | Carcassonne AI（チェコ語） | 未精読 |

確認できた学術的な先行研究はMCTS止まり。AlphaZero型は、GitHubに個人実装
（TommyX12/carcassonne-alpha-zero）があるものの、論文としての評価は見つけられていない
（網羅的な文献調査は未実施）。価値・方策ネット＋MCTSの系統的評価は差別化点になりうる。

## 既存OSS実装（GitHub）

| リポジトリ | 言語/ライセンス | 用途 |
|---|---|---|
| [wingedsheep/carcassonne](https://github.com/wingedsheep/carcassonne) | Python / MIT | ルールエンジン。基本セットのタイル定義（`tile_sets/base_deck.py`）を参照用に利用可。**Python実装のため速度面は要検証** |
| [TommyX12/carcassonne-alpha-zero](https://github.com/TommyX12/carcassonne-alpha-zero) | TF2/Keras / MIT | AlphaZeroのCarcassonne適用例。設計の参考 |
| [zac-garby/carcassonne](https://github.com/zac-garby/carcassonne) | WTFPL | wave function collapse によるシミュレータ |
| [samuelscheit/carcassonne-ai](https://github.com/samuelscheit/carcassonne-ai) | GPL-2.0 | AI実装。**GPLのためコードの取り込みは避け、設計の参考に留める** |
| [farin/JCloisterZone](https://github.com/farin/JCloisterZone) | Java | 拡張込みの網羅的な実装。ルール解釈の突き合わせ（第三者の「正解」）に有用 |

方針: 他実装のコードは**コピーせず**、タイル定義などのデータとルール解釈の検証用（オラクル）として参照する。
自前エンジンを書き、既存実装との**差分テスト**（同一シード・同一手順で得点が一致するか）で正しさを担保する。

## タイル構成の検証

- 基本セットは72枚（開始タイル1＋71枚）。wingedsheep の `base_tile_counts` の合計は72で一致した。
- 同実装は「花（flowers）」付きの絵柄違いを別タイルとして数えている。機能（辺・盾・修道院・接続）が
  同じタイルは同一種として扱う必要があり、**正規化したタイル種別表を自前で作り、印刷版ルールブックと
  突き合わせること**（`docs/RULES.md` の未解決事項）。

## 未確認・今後の調査

- 上記3論文の精読（シミュレーション設定、ルール簡略化、勝率の数値）。
- 2人対戦の評価指標・強さの測り方（Elo、スコア差など）の先行例。
- ニューラルネット表現（グリッド vs グラフ）の先行例。
