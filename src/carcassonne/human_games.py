"""人がAIと指した棋譜（公開の対戦ページから送ってもらったもの）の読み込み・検査・学習データ化・弱点分析。

対戦ページ（docs/play.html）は終局後に棋譜を JSON で書き出す（web/play_local.js の gameRecord）。
送ってもらう方法は2つ: ファイルに保存して渡す、または GitHub の Issue で送る（本文に JSON を入れた
Issue の画面が開き、本人が見てから送信する）。Issue は .github/workflows/human-games.yml が受け取り、
`ingest_issue` で検査してから data/human_games.jsonl に1局1行で足す。

棋譜（1局）の形:
    {"v": 1, "deck": [71枚の種別index], "moves": [[x, y, 向き, 断片(-1=なし)], ...],
     "human_seat": 0|1, "level": "strong"|"standard"|"greedy", "ai": "gen1144",
     "coach": bool, "hints": int, "undos": int, "scores": [先手, 後手]}
名前などの個人情報は入れない（受け取っても捨てる）。山札は乱数の種ではなく並びそのものを持つ
（ブラウザ版と Python 版では山札の混ぜ方が違うため）。

使い道:
- 学習: `to_data` で自己対戦と同じ (特徴量, 終局得点差, 手番, 対局番号) にし、自己対戦ループの学習に混ぜる
  （selfplay_loop.Config.human_games）。判定の対戦は今までどおりなので、混ぜて弱くなれば採用されない。
- 弱点分析: `swings` で、人の手のあとにAIの見積もりが大きく下がった局面（AIが読めていなかった手）を拾う。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

from .fast import SC_CUR, SC_OVER, SC_PL, SC_S0, SC_S1, Fast
from .fast_eval import NF, features
from .state import Move, State
from .tiles import TileSet, load_tileset

VERSION = 1
MARK = "carcassonne-game-record"  # Issue の本文に入れる目印（ワークフローはこれで棋譜の Issue を見分ける）
LEVELS = ("strong", "standard", "greedy")
KEEP = ("v", "deck", "moves", "human_seat", "level", "ai", "coach", "hints", "undos", "scores")
MAX_BODY = 20000  # Issue 本文の上限（これより長いものは読まない）


class RecordError(ValueError):
    """棋譜として受け取れない（形が違う・ルールに合わない）。"""


def _full_deck(ts: TileSet) -> Counter:
    c = Counter({i: t.count for i, t in enumerate(ts.types)})
    c[ts.start] -= 1
    return c


def normalize(obj, ts: TileSet | None = None) -> dict:
    """受け取った JSON を検査し、決まった項目だけの棋譜にする。ルールどおり再生できなければ RecordError。

    再生して確かめること: 山札が基本セットの71枚であること、各手が合法手であること、
    最後まで指して終局し、記録の得点と一致すること。
    """
    ts = ts or load_tileset()
    if not isinstance(obj, dict):
        raise RecordError("棋譜が JSON のオブジェクトではありません")
    if obj.get("v") != VERSION:
        raise RecordError(f"棋譜の版が違います（v={obj.get('v')!r}）")
    deck, moves = obj.get("deck"), obj.get("moves")
    if not (isinstance(deck, list) and all(isinstance(t, int) for t in deck)):
        raise RecordError("deck が整数の並びではありません")
    if Counter(deck) != _full_deck(ts):
        raise RecordError("山札が基本セットの71枚になっていません")
    if not (isinstance(moves, list) and 0 < len(moves) <= len(deck)):
        raise RecordError("moves の長さがおかしい")
    seat, level = obj.get("human_seat"), obj.get("level")
    if seat not in (0, 1):
        raise RecordError("human_seat は 0 か 1")
    if level not in LEVELS:
        raise RecordError(f"level は {LEVELS} のどれか")
    st = State(list(deck), ts)
    norm_moves = []
    for k, m in enumerate(moves):
        if not (isinstance(m, list) and len(m) == 4 and all(isinstance(v, int) for v in m)):
            raise RecordError(f"{k + 1}手目の形が [x, y, 向き, 断片] ではありません")
        if st.over:
            raise RecordError(f"{k + 1}手目: もう終局しています")
        x, y, v, p = m
        mv = Move(x, y, v, None if p < 0 else p)
        if mv not in st.legal_moves():
            raise RecordError(f"{k + 1}手目がルール上置けない手です")
        st.apply(mv)
        norm_moves.append([x, y, v, -1 if p < 0 else p])
    if not st.over:
        raise RecordError("最後まで指されていません（終局した対局だけ受け取ります）")
    if list(obj.get("scores", [])) != list(st.scores):
        raise RecordError(f"得点が再生結果 {list(st.scores)} と合いません")
    ai = obj.get("ai")
    return {
        "v": VERSION,
        "deck": list(deck),
        "moves": norm_moves,
        "human_seat": seat,
        "level": level,
        "ai": ai[:40] if isinstance(ai, str) else None,
        "coach": bool(obj.get("coach")),
        "hints": max(0, int(obj.get("hints") or 0)),
        "undos": max(0, int(obj.get("undos") or 0)),
        "scores": list(st.scores),
    }


def key(rec: dict) -> str:
    """同じ対局を二重に足さないための見出し（山札と指し手のハッシュ）。"""
    s = json.dumps([rec["deck"], rec["moves"], rec["human_seat"]], separators=(",", ":"))
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _raw_key(obj) -> str | None:
    """検査する前の棋譜の key（形が違えば None）。normalize は山札・指し手・席を変えないので key と同じになる。"""
    try:
        return key({k: obj[k] for k in ("deck", "moves", "human_seat")})
    except (KeyError, TypeError):
        return None


def public_index(games: list[dict]) -> list[list]:
    """「みんなの対局」の一覧に要る分だけの軽い表（1局1行）。棋譜の本体は `public_chunks` に分けて置く。

    1行は [強さ, 人の席, 人の得点, AIの得点, 手数, 初心者モード・ヒント・待ったの有無(0/1)]。
    """
    out = []
    for r in games:
        h = r["human_seat"]
        assisted = r["coach"] or r["hints"] > 0 or r["undos"] > 0
        out.append(
            [r["level"], h, r["scores"][h], r["scores"][1 - h], len(r["moves"]), int(assisted)]
        )
    return out


CHUNK = 100  # 公開する棋譜を何局ずつのファイルに分けるか（再生は1ファイルだけ読む）


def public_chunks(games: list[dict], size: int = CHUNK) -> list[list[dict]]:
    """棋譜を size 局ずつに分ける。n 局目（1始まり）は (n-1)//size 番目のファイルの (n-1)%size 番目。

    局は後ろに足されるだけなので、新しい局が届いても書き換わるのは最後のファイルだけ。
    """
    return [games[i : i + size] for i in range(0, len(games), size)]


def from_issue_body(body: str) -> dict:
    """Issue の本文から棋譜の JSON（```json の枠の中）を取り出す。"""
    if not body or MARK not in body:
        raise RecordError("棋譜の Issue ではありません")
    if len(body) > MAX_BODY:
        raise RecordError("本文が長すぎます")
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
    if not m:
        raise RecordError("本文に棋譜の JSON が見つかりません")
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise RecordError(f"棋譜の JSON が読めません（{e.msg}）") from None


def load(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def known_keys(path: str | Path) -> set[str]:
    """もうある対局の key（二重に足さないため）。"""
    return {key(r) for r in load(path)}


def add(path: str | Path, rec: dict, known: set[str] | None = None) -> bool:
    """棋譜を1行足す。同じ対局がもうあれば足さずに False。

    known（`known_keys` の結果）を渡すと、ファイルを読み直さずにそれで見分け、足した key を加える
    （フォームの表は回答がたまり続けるので、1行ごとに全部を読み直すと局数に比例して遅くなる）。
    """
    p = Path(path)
    if known is None:
        known = known_keys(p)
    k = key(rec)
    if k in known:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
    known.add(k)
    return True


def replay(fast: Fast, rec: dict):
    """棋譜を再生し、各手の直前の局面 S を順に返す（最後に終局局面）。S は使い回すのでその場で読むこと。"""
    S = fast.new_game(rec["deck"])
    for x, y, v, p in rec["moves"]:
        yield S
        fast.apply(S, x, y, int(S[10][SC_CUR]), v, None if p < 0 else p)
    assert S[10][SC_OVER], "棋譜の最後で終局していない"
    yield S


def to_data(fast: Fast, games: list[dict], feat=features, nf: int = NF):
    """棋譜から (X, y, 手番, 対局番号) を作る（`records.records_to_data` と同じ並び）。"""
    xs, ys, ps, gs = [], [], [], []
    f = np.zeros(nf)
    for gi, rec in enumerate(games):
        n = len(rec["moves"])
        players = []
        for k, S in enumerate(replay(fast, rec)):
            if k == n:
                d = int(S[10][SC_S0]) - int(S[10][SC_S1])
                break
            me = int(S[10][SC_PL])
            feat(S, fast.T, fast.P, me, f)
            xs.append(f.copy())
            players.append(me)
        ys.extend(d if me == 0 else -d for me in players)
        ps.extend(players)
        gs.extend([gi] * len(players))
    return (
        np.array(xs).reshape(-1, nf),
        np.array(ys, np.float64),
        np.array(ps, np.int64),
        np.array(gs, np.int64),
    )


def swings(fast: Fast, games: list[dict], w: np.ndarray, top: int = 10) -> list[dict]:
    """人の手で、AIの見積もり（線形評価、AI視点の得点差）が大きく下がった局面を大きい順に返す。

    AIの読みが外れた＝人の手の価値をAIが低く見ていた候補。下がり幅は「人の手の直前」と「直後」の差。
    """
    out = []
    f = np.zeros(NF)
    for gi, rec in enumerate(games):
        ai = 1 - rec["human_seat"]
        vals, movers = [], []
        for S in replay(fast, rec):
            features(S, fast.T, fast.P, ai, f)
            vals.append(float(f @ w[:NF]))
            movers.append(int(S[10][SC_PL]) if not S[10][SC_OVER] else -1)
        for k, (x, y, _v, _p) in enumerate(rec["moves"]):
            if movers[k] != rec["human_seat"]:
                continue
            out.append(
                {"game": gi, "ply": k + 1, "x": x, "y": y, "drop": round(vals[k] - vals[k + 1], 1)}
            )
    out.sort(key=lambda r: -r["drop"])
    return out[:top]


def summary(games: list[dict]) -> dict:
    """強さごとの局数・人の勝ち数・人から見た平均得点差。初心者モード・ヒント・待ったの局は別に数える。"""
    rows: dict[str, dict] = {}
    for rec in games:
        assisted = rec["coach"] or rec["hints"] > 0 or rec["undos"] > 0
        r = rows.setdefault(
            rec["level"], {"games": 0, "human_wins": 0, "draws": 0, "diff": 0, "assisted": 0}
        )
        h = rec["human_seat"]
        d = rec["scores"][h] - rec["scores"][1 - h]
        r["games"] += 1
        r["human_wins"] += d > 0
        r["draws"] += d == 0
        r["diff"] += d
        r["assisted"] += assisted
    for r in rows.values():
        r["mean_diff"] = round(r.pop("diff") / r["games"], 1)
    return rows


PLAY_URL = "https://satou-aaaaa.github.io/carcassonne-research/play.html"


def replay_url(game: int, ply: int | None = None) -> str:
    """対戦ページでその対局（1始まり）を再生する URL。ply を渡すとその手数から。"""
    return f"{PLAY_URL}#replay={game}" + (f"&ply={ply}" if ply is not None else "")


REPORT_LIST = 50  # レポートに並べる対局の数（新しい順。全部は「みんなの対局」ページで見る）
GAMES_URL = "https://satou-aaaaa.github.io/carcassonne-research/games.html"


def report_md(fast: Fast, games: list[dict], w: np.ndarray, sw: list[dict] | None = None) -> str:
    """弱点分析のレポート（Markdown）。sw は `swings` の結果（省くとここで計算する）。"""
    lines = [
        "# 人との対局のまとめ（自動）",
        "",
        (
            "対戦ページから送ってもらった棋譜（data/human_games.jsonl）の集計。"
            "`python scripts/human_games.py report` で作り直す。"
        ),
        "",
        f"受け取った対局: {len(games)}局",
        "",
    ]
    if not games:
        return "\n".join(lines + ["まだ棋譜がありません。"]) + "\n"
    lines += [
        "| AIの強さ | 局数 | 人の勝ち | 引き分け | 人から見た平均得点差 | うちヒント等あり |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for lv, r in sorted(summary(games).items(), key=lambda kv: LEVELS.index(kv[0])):
        lines.append(
            f"| {lv} | {r['games']} | {r['human_wins']} | {r['draws']} | {r['mean_diff']:+.1f} | {r['assisted']} |"
        )
    lines += ["", "## 対局の一覧（押すと一手ずつ再生）", ""]
    if len(games) > REPORT_LIST:
        lines += [f"新しい{REPORT_LIST}局だけ。全部は [みんなの対局]({GAMES_URL}) で見られる。", ""]
    for gi in range(len(games) - 1, max(-1, len(games) - 1 - REPORT_LIST), -1):
        rec = games[gi]
        h = rec["human_seat"]
        sc = rec["scores"]
        seat = "先手" if h == 0 else "後手"
        lines.append(
            f"- [{gi + 1}局目]({replay_url(gi + 1)}): 人（{seat}）{sc[h]} − AI {sc[1 - h]}"
            f"（{rec['level']}、{len(rec['moves'])}手）"
        )
    lines += [
        "",
        "## AIの読みが外れた人の手（AIの見積もりが大きく下がった順）",
        "",
        (
            "AI視点の評価（最新チャンピオンの線形評価、単位は得点差）が、人の手の直前と直後でどれだけ下がったか。"
            "大きいものは、AIがその手の価値を低く見ていた候補（弱点探しの出発点）。"
        ),
        "",
        "対局の番号を押すと、対戦ページでその手の直前から一手ずつ再生できる。",
        "",
        "| 対局 | 手数 | 置いた場所 (x, y) | 下がり幅 |",
        "|---:|---:|---|---:|",
    ]
    for s in (swings(fast, games, w) if sw is None else sw)[:10]:
        url = replay_url(s["game"] + 1, s["ply"] - 1)
        lines.append(
            f"| [{s['game'] + 1}]({url}) | {s['ply']} | ({s['x']}, {s['y']}) | {s['drop']:+.1f} |"
        )
    return "\n".join(lines) + "\n"


def ingest_rows(texts, path: str | Path, ts: TileSet | None = None) -> dict:
    """Google フォームの回答（棋譜の JSON の文字列の並び）を検査して足す。数を返す（added / duplicate / invalid）。"""
    ts = ts or load_tileset()
    out = {"added": 0, "duplicate": 0, "invalid": 0}
    known = known_keys(path)
    for text in texts:
        try:
            if len(text) > MAX_BODY:
                raise RecordError("長すぎます")
            obj = json.loads(text)
            if _raw_key(obj) in known:  # もう受け取った対局（表には残り続ける）は検査を省く
                out["duplicate"] += 1
                continue
            rec = normalize(obj, ts)
        except (RecordError, json.JSONDecodeError, TypeError):
            out["invalid"] += 1
            continue
        out["added" if add(path, rec, known) else "duplicate"] += 1
    return out


def form_texts(csv_text: str) -> list[str]:
    """フォームの回答の表（CSV。1列目はタイムスタンプ、2列目が棋譜）から棋譜の文字列を取り出す。"""
    import csv
    import io

    rows = list(csv.reader(io.StringIO(csv_text)))
    return [r[1] for r in rows[1:] if len(r) > 1 and r[1].strip()]


def ingest_issue(body: str, path: str | Path, ts: TileSet | None = None) -> tuple[str, str]:
    """Issue の本文の棋譜を検査して足す。(結果, 知らせる文) を返す。結果は added / duplicate / invalid。"""
    try:
        rec = normalize(from_issue_body(body), ts)
    except RecordError as e:
        return "invalid", f"棋譜として受け取れませんでした: {e}"
    if not add(path, rec):
        return "duplicate", "同じ対局の棋譜はもう受け取っています。ありがとうございます。"
    h = rec["human_seat"]
    d = rec["scores"][h] - rec["scores"][1 - h]
    return "added", (
        f"棋譜を受け取りました（{len(rec['moves'])}手、あなた {rec['scores'][h]} − AI "
        f"{rec['scores'][1 - h]}、差 {d:+d}）。AIの学習と弱点探しに使わせていただきます。ありがとうございます！"
    )
