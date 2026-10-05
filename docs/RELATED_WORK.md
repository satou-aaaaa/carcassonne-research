# 先行研究・既存実装の調査メモ

調査日: 2026-10-05（Web検索・GitHub検索による。論文本文の精読は未了のため、要点は
概要・抄録ベース。引用前に必ず原文で確認すること）。

## 論文・学位論文

| 文献 | 内容（確認できた範囲） | 状態 |
|---|---|---|
| Ameneyro, Galván, Kuri Morales, "Playing Carcassonne with Monte Carlo Tree Search" (2020) [arXiv:2009.12974](https://arxiv.org/abs/2009.12974) | 2人対戦。vanilla MCTS と MCTS-RAVE を、ドメイン固有ヒューリスティック付き Star2.5 と比較。MCTS系が Star2.5 を上回り、vanilla MCTS の方が MCTS-RAVE より安定。Carcassonneは確率的で「得点が欺瞞的（deceptive）」と指摘 | 抄録確認。本文のルール簡略化・シミュレーション数・勝率は**要精読** |
| Jappert, Bachelor thesis, Univ. Basel（[PDF](https://ai.dmi.unibas.ch/papers/theses/jappert-bachelor-22.pdf)） | Carcassonne関連の学士論文。内容は未確認（PDFをテキスト抽出できなかった） | **要精読** |
| Charles University (Praha) 学位論文「Umělá inteligence pro hru Carcassonne」（[handle](https://dspace.cuni.cz/handle/20.500.11956/119448)） | Carcassonne AI。内容は未確認 | **要精読** |

先行研究が少ない（Ameneyroらも "limited prior research" と述べている）ため、
本プロジェクトは「基本ルール・2人対戦」に絞ってAlphaZero型まで踏み込む余地がある。

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
