# カルカソンヌ背景資料（ゲーム概要・歴史・競技シーン・著名プレイヤー）

調査日: 2026-10-06（Web検索・Webページ取得による二次情報。一次資料（公式サイト・原典）での裏取りは未実施の項目が多い。
引用前に必ず出典で確認すること。確度に注意が要る点は各節の「注意」と末尾の「未確認・矛盾点」に集約した）。

このプロジェクト（強いカルカソンヌAIの研究）の文脈資料として、ゲームそのもの・歴史・競技コミュニティを整理する。
AI側の先行研究は [RELATED_WORK.md](RELATED_WORK.md)、ルール実装は [RULES.md](RULES.md) を参照。

---

## 1. ゲームの概要

| 項目 | 内容 |
|---|---|
| 名称 | カルカソンヌ（Carcassonne） |
| デザイナー | Klaus-Jürgen Wrede（クラウス＝ユルゲン・ヴレーデ） |
| 発売 | 2000年（エッセン・シュピール2000で発表） |
| 出版 | Hans im Glück（独）／Rio Grande Games（英語版、〜2012）→ Z-Man Games（英語版、2012〜） |
| 人数・時間 | 2〜5人（拡張で6人以上）、基本セットで約35分 |
| 種類 | タイル配置（タイルレイング）＋ワーカープレイスメント的な「ミープル」配置のユーロゲーム |
| 受賞 | 2001年 Spiel des Jahres（年間ゲーム大賞）、2001年 Deutscher Spiele Preis |

### 基本ルール（基本セット）
- タイルは72枚（スタートタイル含む）。毎手番「タイルを引く → 既存の地形に辺を合わせて置く → 任意でミープルを1個置く → 完成した地形を得点化」。
- 地形は都市・道・修道院・草原。ミープルは1人7個を手番で使い回し（完成した地形から戻る）。
- 得点（完成時）: 都市=タイル数×2＋紋章×2、道=タイル数×1、修道院=1＋周囲8マス（最大9点）。
- 得点（終局時）: 未完成の都市はタイル＋紋章が各1点、未完成の道・修道院は現在の枚数分。
  草原（農夫）は、その草原に接する**完成した都市1つにつき3点**。
- 農夫の得点規則は第3版（2002年）などで改定された経緯があり、英語版（Rio Grande）は2008年まで旧ルールのままだった
  （版による差異に注意。本プロジェクトの実装規則は [RULES.md](RULES.md)）。
- 「勝敗が運だけで決まらない」「脱落がない」「ルールが短い」ことから、ゲートウェイ（入門）ゲームの代表格とされる。

### ゲーム性の特徴（AI研究上の意味）
- 山札の順序が確率的（チャンスノード）、盤面は完全公開。2人戦なら**確率的な完全情報ゲーム**。
- 手番ごとの分岐は「配置位置×向き×ミープル配置先」で数十〜百超になりうる。
- 得点が終局まで確定しない（草原など）ため、中盤の評価が難しい。→ MCTS系・得点差ベースの報酬が使われる理由（RELATED_WORK参照）。
- 世界選手権は基本セット・2人対戦で行われる（後述）。本プロジェクトの2人・基本セット設定は競技の実態に一致する。

---

## 2. 歴史

### 2.1 舞台となった都市カルカソンヌ（中世城塞都市）
- 南フランス・オクシタニー地方（ラングドック）の城塞都市。約2,500年の歴史があり、ローマ人・西ゴート人・十字軍などの支配を受けた。
- 11〜12世紀にトランカヴェル家が統治し、コンタル城を築いて繁栄した。
- アルビジョア十字軍（カタリ派討伐）の拠点の一つ。**1209年8月**に教皇特使アルノー・アモーリ率いる十字軍が包囲し、
  当主レモン＝ロジェ・ド・トランカヴェルは交渉中に捕らえられ、数か月後に不審な状況で死去した。
- 二重の城壁は約3km、塔52基。19世紀に建築家ヴィオレ＝ル＝デュクが修復（当時から「気候や地域の伝統に合わない」と批判された）。
- **1997年にユネスコ世界遺産**登録。
- ゲームは都市そのものを再現したものではなく、この周辺の「城・道・修道院・農地が広がる風景」をタイルで組み上げる発想。

### 2.2 ゲームの誕生（1990年代末〜2000年）
- **1990年代後半**: ヴレーデが、カタリ派十字軍を題材にした小説の取材で南仏を旅行。城や城壁都市が広がる風景に魅了され、
  小説よりもボードゲームの着想を得た。
- 初期の試作タイルは**水彩で手描き**。試作段階では修道院がなく（草原タイルのみ）、各プレイヤーのミープルが3個多く、
  終局まで回収されず、他人が占有中の地形にも置ける、といった現在と異なる仕様だった。
- **2000年初頭**: 試作が完成。無名の作者だったヴレーデはルールと写真を Hans im Glück に送り、編集者 **Dirk Geilenkeuser** の目に留まった。
  同社はドイツと米国でテストプレイを行った。
- **2000年5月**: Hans im Glück が出版を決定。
- **2000年10月**: エッセン・シュピールの締切に合わせて発売。ミープルの駒は同社創業者 **Bernd Brunnhofer** と駒制作者らが
  急ぎで設計した（独語ルールでは「Gefolgsleute（従者）」）。
- 「**ミープル（meeple）**」という語は、米国のゲーマー Alison Hansel が2000年11月に「my people」から造語したとされる。
  公式ルールが採用するまでには年数がかかった。
- ヴレーデは音楽・宗教科の教師（1963年メシェデ生まれ、ケルン近郊在住）で、専業デザイナーではなかった。
  他作品に『ポンペイの滅亡』(2004)、『メソポタミア』(2005)、『ラパ・ヌイ』(2011)。

### 2.3 年表

| 年 | 出来事 |
|---|---|
| 2000 | 発売（エッセン） |
| 2001 | Spiel des Jahres・Deutscher Spiele Preis 受賞。農夫の得点規則が改定される |
| 2002 | 第3版（農夫を「草原ごと」に採点、農夫を寝かせて置くなど）。ミニ拡張「川（The River）」。拡張「宿屋と大聖堂」。初のスピンオフ『狩人と採集者』。初のPC版（Koch Media） |
| 2003 | 拡張「商人と建築家」、スピンオフ『城』（ライナー・クニツィア作）。初の国際トーナメント |
| 2005 | 拡張「王女とドラゴン」（竜・妖精・火山などを追加。賛否が分かれた） |
| 2006 | 拡張「塔」。**第1回世界選手権**（エッセン・シュピール、優勝 Ralph Querfurth） |
| 2007 | 拡張「修道院と市長」。Xbox 360版。携帯版『Travel Carcassonne』 |
| 2008 | 拡張「伯爵・王・盗賊」「カタパルト」（後者は評価が割れた）。英語版の農夫ルールがようやく更新 |
| 2009 | 子供向け『My First Carcassonne』、カード版『Cardcassonne』、ニンテンドーDS版 |
| 2010 | 拡張「橋・城・市場」。iOS版（TheCodingMonkeys、高評価） |
| 2011 | 10周年記念版（ミープル型の箱） |
| 2012 | 英語版の出版が Rio Grande → Z-Man Games へ |
| 2013 | 動画番組 *TableTop*（Wil Wheaton）で紹介（約150万視聴と報じられる） |
| 2014 | 大幅リニューアル（イラストを Anne Pätzke に刷新、ピンクが公式6人目の色に）。拡張「丘と羊」 |
| 2016 | GothCon（スウェーデン）で10,007枚・48卓の世界記録プレイ。「迷宮」発売 |
| 2017 | 拡張「サーカス」、Nintendo Switch版 |
| 2020 | 公式ソロ版、*The Book of Carcassonne* 刊行。BGGの「評価数」ランキングで一時首位 |
| 2021 | 20周年記念版（ミニ拡張15枚・川タイル追加） |
| 2026 | 各国で25周年の販促（例: 伊 Giochi Uniti が3月を記念月に）。※20周年の記事と混在しやすいので出典で確認 |

> 注意: 年表は Meeple Mountain、Wikipedia、Carcassonne Central などの要約に基づく。年が資料により1年ずれる項目
> （例: 拡張「川」の初出、各拡張の独語版/英語版の差）がありうる。

### 2.4 拡張・派生
- 大型拡張（Wikipedia記載）: 宿屋と大聖堂(2002)／商人と建築家(2003)／王女とドラゴン(2005)／塔(2006)／修道院と市長(2007)／
  伯爵・王・盗賊(2008)／カタパルト(2008)／橋・城・市場(2010)／丘と羊(2014)／サーカス(2017)。
- ミニ拡張は2001年以降に30種以上（川、王と斥候、教団、トンネル、ミステリーサークルなど）。コンサバな数え方で公式拡張は約59種との集計もある。
- スピンオフは約16〜20作（『新世界』『サウスシー』『ゴールドラッシュ』『アマゾナス』『サファリ』『スター・ウォーズ版』ほか）。
- 「拡張疲れ」が語られるが、**世界選手権は基本セットのみ**で行われるため、競技・AI研究の標準は基本セットになっている。

### 2.5 デジタル化
Facebook、iOS（TheCodingMonkeys）、Windows Phone/Xbox Live、Xbox 360（2007）、ニンテンドーDS（2009）、Android、Steam（Tiles & Tactics）、
Nintendo Switch（2017）、BrettspielWelt、Board Game Arena など。オンライン対戦の普及が、2020年以降のオンライン選手権や
プレイヤー層の国際化につながった。

### 2.6 売上・位置づけ
- 累計1,200万部超（Meeple Mountain）、22言語に公式翻訳。一方でイタリア報道や古い資料は「1,000万部超」とも。
  数字は資料により異なる（集計時点の差）。
- BoardGameGeek 上では一時 #2 まで上昇（現在は100位台）。2025年5月時点で評価数は Catan に次ぐ多さとされる。
- 近代ボードゲーム（ユーロゲーム）を代表するゲートウェイ作品の一つ。「ミープル」は卓上ゲーム文化全体の象徴的な駒の形になった。

---

## 3. 競技シーン

### 3.1 カルカソンヌ世界選手権（Carcassonne World Championships）
- 主催: Hans im Glück ほか（Spielezentrum Herne など）。2006年にエッセン・シュピールで開始。
- 形式: **基本セット（72枚）・2人対戦**。各国予選（国内選手権）を勝ち抜いた代表が決勝へ。
  近年は予選ラウンドの後、準々決勝・準決勝・決勝（2025年は6ラウンド予選＋決勝トーナメント）。
- 規模の拡大: 2024年は46人・40か国（当時の最多）、2025年は52人・45か国（最多更新）。2026年は50以上の国・地域が参加予定、
  決勝は2026年11月22日予定。
- 2023年以降、Mind Sports Olympiad（MSO）とオンラインの世界チーム選手権の上位者にワイルドカードが与えられる。
- 近年の会場は Spielezentrum Herne（2025年10月25日開催の第19回）。優勝式がエッセンで別途行われる年もある。

### 3.2 歴代世界王者

| 年 | 優勝者 | 国 |
|---|---|---|
| 2006 | Ralph Querfurth | ドイツ |
| 2007 | Sebastian Trunz | ドイツ |
| 2008 | Ralph Querfurth | ドイツ |
| 2009 | Ralph Querfurth | ドイツ |
| 2010 | Ralph Querfurth | ドイツ |
| 2011 | Els Bulten | オランダ |
| 2012 | Martin Mojzis | チェコ |
| 2013 | Pantelis Litsardopoulos | ギリシャ |
| 2014 | Takafumi Mochizuki（望月 孝文） | 日本 |
| 2015 | Pantelis Litsardopoulos | ギリシャ |
| 2016 | Vladimir Kovalev | ロシア |
| 2017 | Tomasz Preuss | ポーランド |
| 2018 | Genro Fujimoto（藤本 玄朗） | 日本 |
| 2019 | Marian Curcan（※下記の注意参照） | ルーマニア |
| 2020 | 開催なし（COVID-19で決勝中止。各国の代表枠を2人に増やして翌年へ繰り延べ） | — |
| 2021 | Maciej Polak | ポーランド |
| 2022 | Arpad Gere | ルーマニア |
| 2023 | Matt Tucker | 英国 |
| 2024 | Dani (Daniel) Angelats | カタルーニャ（スペイン） |
| 2025 | Xiangyu Qin | 中国 |

出典: 公式サイトの歴代結果（2006〜2023）、MSO（2024）、公式2025決勝ページ。日本人王者の漢字表記は筆者の推定で、要確認。

#### 決勝の詳細（公式の結果PDF〜2016年、各年の決勝ページ）
決勝は2人対戦で、スコアは**得点（点数）**。2006〜2016年は6回戦のスイス式予選（勝数→ブッフホルツ）の上位4人が準決勝・決勝へ進んだ。
注: 2006年は準決勝がなく、予選上位4人で決勝（1位×2位）と3位決定戦のみ。

| 年 | 決勝（勝者 vs 敗者、得点） | 3位 | 参加者 |
|---|---|---|---|
| 2006 | Ralph Querfurth 89 – 78 Michael Wischounig（墺。予選は Wischounig が1位） | David Korejtko（チェコ） | 16 |
| 2007 | Sebastian Trunz 99 – 88 Wei-Chi Chen（台湾） | Janne Jaula（フィンランド） | 未確認 |
| 2008 | Ralph Querfurth 109 – 71 Martin Mojzis（チェコ） | Sebastian Trunz | 未確認 |
| 2009 | Ralph Querfurth 95 – 63 Daniel Geromboux（豪） | Matej Tabak（スロバキア） | 未確認 |
| 2010 | Ralph Querfurth 81 – 55 Martin Mojzis | Matej Tabak | 22 |
| 2011 | Els Bulten 75 – 59 Shinnosuke Komukai（日本） | Robert Mützner（独） | 24 |
| 2012 | Martin Mojzis 79 – 76 Stefan Leopoldseder（墺） | Matej Tabak | 26 |
| 2013 | Pantelis Litsardopoulos 107 – 60 Martin Mojzis | Aleksejs Pegusevs（ラトビア） | 36 |
| 2014 | Takafumi Mochiduki（日）が Litsardopoulos に勝利（スコアは未取得） | Matej Tabak | 未確認 |
| 2015 | Pantelis Litsardopoulos 101 – 97 Takafumi Mochizuki | Els Bulten | 32 |
| 2016 | Vladimir Kovalev 114 – 79 Pantelis Litsardopoulos | Wannes Vansina（ベルギー） | 未確認 |
| 2017・2018 | 決勝ページ未取得 | — | — |
| 2019 | Marian Curcan 102 点（同点で予選順位により1位）／2位 Ying Chien（台湾）102 点 | Timofei Gretsenko（エストニア） | 36 |
| 2021 | Maciej Polak（ポ）／2位 Melvin Gavinho Quaresma（ブラジル） | Tomasz Preuss（ポ） | 42 |
| 2022 | Arpad Gere 103 点／2位 Min-Wei Chen（台湾） | Martin Mojzis（※スコア上は3位が100点で2位の98点を上回る。タイブレーク計算のソフト不具合を主催者が認めた旨の記載あり） | 34 |
| 2023 | Matt Tucker（準優勝者は未取得） | — | — |
| 2024 | Dani Angelats 勝利 vs Josef Tihon（ハンガリー） | — | 46（40か国） |
| 2025 | Xiangyu Qin／2位 Horacio Mastandrea（ウルグアイ） | Raf Mesotten（ベルギー） | 52（45か国） |

2025年の上位8位: 1 Qin（中）、2 Mastandrea（ウルグアイ）、3 Raf Mesotten（ベルギー）、4 Aleksejs Pegusevs（ラトビア）、
5 Borislav Aymaliev（ブルガリア）、6 Kyrylo Manakhov（ウクライナ）、7 George Kyriazides（ギリシャ）、8 Vladimir Kovalev（元王者）。
2025年の優勝者は準決勝・決勝を含め全勝（予選の記載は「4.0」）。決勝の得点は結果ページに記載があるが、取得した要約からは読み取れない。

読み取れる傾向:
- 決勝の得点は概ね**60〜140点台**、勝敗差は数点〜40点と幅がある。接戦の決勝（2012年3点差、2015年4点差）も多い。
- **Martin Mojzis**（チェコ）は決勝に4回進出（2008、2010、2012、2013）して優勝1回、2022年も3位。Pantelis Litsardopoulos は2013〜2016年に3連続で決勝進出（優勝2回）。
- Matej Tabak（スロバキア）は2009〜2014年に何度も3位以内（準決勝・3位決定戦の常連）。
- 初期（2006〜2010年）はドイツ勢、その後アジア・東欧・南米と優勝国が拡散している。

### 3.3 著名プレイヤー

| 人物 | 概要 |
|---|---|
| **Ralph Querfurth**（独、1979〜） | 世界王者4回（2006, 2008–2010）で最多。初代王者。ドイツ王者2回（2006, 2023）、ドイツTichu王者(2008)、欧州チーム選手権（オンライン, 2020）優勝。本業は Kosmos の編集者で『EXIT』シリーズの発案者（累計1,800万部超とされる）。 |
| **Pantelis Litsardopoulos**（希） | 2013・2015年王者。決勝に5年連続進出と記録される（2013〜）。 |
| **Els Bulten**（蘭） | 2011年王者。**唯一の女性王者**。 |
| **Takafumi Mochizuki**（日） | 2014年に19歳で優勝。日本勢はその後 Genro Fujimoto が2018年に優勝し、2人の王者を輩出。 |
| **Matt Tucker**（英） | 2023年王者。MSOでも上位。 |
| **Dani Angelats**（カタルーニャ） | 2024年王者。MSO第30回大会でも銅メダル。2024決勝は Josef Tihon（ハンガリー）を破った。 |
| **Bogdan Curcan**（羅） | MSO第30回（2人対戦）金メダル。2019年王者の「Marian Curcan」と同一人物の可能性があるが未確認。 |
| **Xiangyu Qin**（中） | 2025年王者。準優勝は Horacio Mastandrea（ウルグアイ）。 |
| **Ilja Mett**（独）、Ankush Khandelwal | MSOカルカソンヌの金メダリストとして名前が挙がる（年は未確認）。 |

その他の舞台: Mind Sports Olympiad（UK Games Expo併催の年もあり）、UK選手権・イタリア選手権などの国内選手権、
オンライン（Board Game Arena のグループ主催大会、BrettspielWelt）。

### 3.4 戦略面の通説（コミュニティで広く言われるもの。AI研究のヒューリスティック検討の参考）
- 草原（農夫）の使い方が勝敗を分ける。完成都市との接続が将来の3点×都市数を生む。
- ミープル（7個）の管理が鍵。置きすぎるとタイル引きで動けず、置かなさすぎると機会損失。
- 他人の地形への「割り込み」（共有・乗っ取り）と、相手を邪魔するタイル置き（ブロック）の見極め。
- 山札の枚数から残りタイル（都市・道・修道院の残数）を数える。
  → ただしこれらは未検証の通説であり、実際の強さはこのプロジェクトのAIで検証する対象。

---

## 4. 本プロジェクトとの接点

1. **評価対象の妥当性**: 世界選手権は基本セット・2人戦。本プロジェクトの設定（基本セット・2人・先後入替）は競技の実態と合致する。
2. **人間との比較**: 世界王者クラス（例: Ralph Querfurth）はオンライン大会（BrettspielWelt、BGA）にも参加している。
   ただし**公開棋譜は見つからなかった**（§5参照）。BGAは「APIなし・スクレイピングはサイト規約違反」とモデレーターが明言しており、
   BGAの棋譜を機械学習に使うのは避ける。[HUMAN_EVAL.md](HUMAN_EVAL.md) の人間対局は、自前のブラウザUIで集めた記録を使うのが現実的。
   なお世界選手権の決勝得点は概ね60〜140点台（§3.2）。AIの平均得点や得点差をこの水準と見比べれば、強さの粗い目安になる。
3. **ルールの版差**: 農夫の得点規則は版（2001年版／2002年第3版以降／英語版の2008年更新）で異なる。
   実装は現行版に揃えているが、古い棋譜・資料と比較する際は注意。
4. **歴史的背景の活用先**: 公式の棋譜が公開されている大会があれば、教師あり事前学習やベンチマークに使える可能性がある（未調査）。

---

## 5. 未確認・矛盾点（要裏取り）

- **売上**: 1,000万部超（伊報道・古い資料）と1,200万部超（Meeple Mountain）が併存。
- **Querfurth の優勝回数**: 公式歴代表と Wikipedia は4回。取得時の要約に「5回」と書かれたものがあったが、年は4つしか挙がっておらず4回が妥当。
- **2019年王者の表記**: 歴代表は「Marian Curcan」、MSO側は「Bogdan Curcan」。別人か表記ゆれか不明。
- **2021年王者**: 検索の要約には「Martin Mojzis 優勝」とあったが、公式の2021決勝ページは Maciej Polak 優勝・Quaresma 準優勝・Preuss 3位。公式を採用（Mojzisは別の年の記述を取り違えた可能性）。
- **2020年**: 公式ページで「決勝中止」を確認済み。オンライン開催の記載はなし。
- **日本人王者の漢字表記**は未確認。準優勝・参加人数は2006〜2016年（一部）、2019・2021・2022・2025年を反映済み。
  2017・2018・2023・2024年の公式決勝ページはURLが見つからず（404）、準優勝・3位・参加人数は未取得。2014年の決勝スコアも未取得。
- **2019・2022年の順位**: 点数ではなく別のタイブレークで決まっている（2022年は3位の点が2位より高い）。形式が2016年以前と異なる可能性があるが、詳細は未確認。
- **2007〜2009年の参加人数、2014・2016年の参加人数**: PDFの表が崩れて読み取れず未確認。
- **年表のうち**: 「川」の初出年、2026年（25周年）関連の詳細、各拡張の英語版発売年は二次資料のみ。
- MSO 2023〜2025の詳細は未調査。
- **公開棋譜（調査結果）**: 世界選手権の棋譜・Elo相当の公開データは見つからなかった。BGA の「Carcassonne Reviewer」という
  GitHub プロジェクト（個人のレビュー補助）の存在は確認したが、データセットではない。BGA公式は棋譜取得（スクレイピング）を禁止。
  BrettspielWelt の棋譜公開方針は未確認。→ 人間の強さの基準は自前の人間対AI対局（HUMAN_EVAL）で作るのが妥当。
- ヴレーデ本人のインタビュー（Z-Man Games 2021年4月）は取得に失敗（URL不達）。一次資料として別途確認したい。

## 6. 出典

- [Carcassonne (board game) — Wikipedia](https://en.wikipedia.org/wiki/Carcassonne_(board_game))
- [Klaus-Jürgen Wrede — Wikipedia](https://en.wikipedia.org/wiki/Klaus-J%C3%BCrgen_Wrede)
- [Ralph Querfurth — Wikipedia](https://en.wikipedia.org/wiki/Ralph_Querfurth)
- [Carcassonne 20th Anniversary: A History and Celebration — Meeple Mountain](https://www.meeplemountain.com/articles/carcassonne-20th-anniversary-a-history-and-celebration-of-carcassonne/)
- [History of Carcassonne? — Carcassonne Central フォーラム](https://www.carcassonnecentral.com/community/index.php?topic=2035)
- [Carcassonne at 20 — Tabletop Gaming](https://tabletopgaming.co.uk/Features/carcassonne-at-20-behind-the-walls-of-the-tile-laying-juggernaut)
- [公式選手権サイト: 歴代結果](https://carcassonne-meisterschaft.de/en/former-results.htm)（[結果PDF（〜2016）](https://carcassonne-meisterschaft.de/media/uploads/2019/05/CC-WMErgebnissebis2016engl.pdf)）
- [公式選手権サイト: 2025決勝](https://carcassonne-meisterschaft.de/en/final-2025.htm)
- [公式選手権サイト: 参加国](https://carcassonne-meisterschaft.de/en/countries.htm)
- [Dani Angelats is the 2024 Carcassonne World Champion — Mind Sports Olympiad](https://mindsportsolympiad.com/dani-angelats-is-the-2024-carcassonne-world-champion/)（検索結果の要約のみ参照。ページ本体は取得できず）
- [Cité de Carcassonne — Wikipedia](https://en.wikipedia.org/wiki/Cit%C3%A9_de_Carcassonne)
- [Carcassonne 20周年 — AGI（2026-03-12）](https://www.agi.it/cronaca/news/2026-03-12/carcassonne-gioco-tavolo-36071148/)
- [WikiCarpedia: Tournaments and World Championships](https://wikicarpedia.com/car/Tournaments_and_World_Championships)（取得不可。検索結果の存在のみ確認）
- [公式選手権: 2019決勝](https://carcassonne-meisterschaft.de/en/final-2019.htm)・[2021決勝](https://carcassonne-meisterschaft.de/en/final-2019-kopie.htm)・[2022決勝](https://carcassonne-meisterschaft.de/en/final-2022.htm)・[2025結果](https://carcassonne-meisterschaft.de/en/final-results-2025.htm)・[2020中止告知](https://carcassonne-meisterschaft.de/en/final-2020.htm)
- [BGA フォーラム: Accessing Database Carcasonne for Machine Learning](https://forum.boardgamearena.com/viewtopic.php?p=177197)（棋譜取得不可の根拠）
