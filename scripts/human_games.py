"""人がAIと指した棋譜（対戦ページから送ってもらったもの）を受け取る・ためる・まとめる。

    py scripts/human_games.py add 棋譜.json ...          # ファイルで受け取った棋譜を検査して足す
    py scripts/human_games.py ingest-issue --event イベント.json --result 結果.json
                                                        # GitHub の Issue で届いた棋譜（human-games.yml から呼ぶ）
    py scripts/human_games.py ingest-form --result 結果.json
                                                        # Google フォームの回答（公開 CSV）を取り込む（human-games.yml から毎朝）
    py scripts/human_games.py report                    # human_games.md・公開する棋譜 docs/human_games/・研究ノートの集計 human_findings.json を作り直す
    py scripts/human_games.py x-draft --title 題.txt --body 本文.md  # 10局ごとの X 投稿の下書き（human-games.yml が Issue に）

棋譜は data/human_games.jsonl に1局1行でためる（形と検査は src/carcassonne/human_games.py）。
ためた棋譜は自己対戦ループの学習に混ざる（selfplay_loop.Config.human_games）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne import human_games as hg

GAMES = ROOT / "data" / "human_games.jsonl"
REPORT = ROOT / "docs" / "results" / "human_games.md"
# 公開する棋譜。一覧（index.json）と、100局ずつに分けた本体（0.json, 1.json, …）。
# 「みんなの対局」は一覧だけ、対戦ページの再生（play.html#replay=番号）はその局の入ったファイルだけを読む
PUBLIC = ROOT / "docs" / "human_games"
# 全局のダウンロード用（みんなの対局の「全局をダウンロード」。ページを開いただけでは読まない）。
# 1局1行の JSON 配列にして、局が増えたときの差分を増えた行だけにする
DOWNLOAD = ROOT / "docs" / "human_games.json"
FINDINGS = ROOT / "docs" / "human_findings.json"  # 「みんなの対局」ページの研究ノートが読む集計
FINDINGS_CACHE = (
    ROOT / "docs" / "results" / "human_findings_cache.json"
)  # 局ごとの採点（新しい局だけ採点する。1局1行）
FORM = ROOT / "data" / "human_games_form.json"
# 1回の report で新しく採点する局数の上限。採点は1局で数十秒かかるので、一度にたくさん届いても
# ワークフローの時間切れ（90分）にならないよう、残りは次の回にまわす（研究ノートは採点済みの局で作る）
MAX_SCORE = 40


def cmd_add(a) -> int:
    bad = 0
    for f in a.files:
        text = Path(f).read_text(encoding="utf-8")
        try:
            rec = hg.normalize(json.loads(text))
        except (hg.RecordError, json.JSONDecodeError) as e:
            print(f"{f}: 受け取れません: {e}")
            bad += 1
            continue
        print(f"{f}: {'足しました' if hg.add(a.games, rec) else '同じ対局がもうあります'}")
    return 1 if bad else 0


def cmd_ingest_issue(a) -> int:
    event = json.loads(Path(a.event).read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    status, message = hg.ingest_issue(issue.get("body") or "", a.games)
    Path(a.result).write_text(
        json.dumps({"status": status, "message": message}, ensure_ascii=False), encoding="utf-8"
    )
    print(status, message)
    return 0


def cmd_ingest_form(a) -> int:
    import urllib.request

    url = json.loads(FORM.read_text(encoding="utf-8")).get("csv", "")
    if not url:
        out = {"added": 0, "duplicate": 0, "invalid": 0, "note": "フォームの設定が空"}
    else:
        if not url.startswith("https://docs.google.com/spreadsheets/"):
            raise SystemExit(f"{FORM} の csv は Google スプレッドシートの公開 URL にしてください")
        from datetime import datetime, timezone

        with urllib.request.urlopen(url, timeout=60) as r:
            text = r.read().decode("utf-8-sig")
        rows = hg.form_rows(text)
        # 取り込みが止まっていなかったか（送ってから LATE_HOURS 時間より長く待たせた棋譜）を、取り込む前に調べる
        late = hg.late_rows(rows, hg.known_keys(a.games), datetime.now(timezone.utc))
        out = hg.ingest_rows([t for _, t in rows], a.games)
        out["late"] = late
    Path(a.result).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(out)
    return 0


def cmd_report(a) -> int:
    from carcassonne.fast import Fast
    from carcassonne.fast_eval import load_eval
    from carcassonne.webplay import champion_eval_path

    w, mode = load_eval(champion_eval_path())
    if mode != 1:
        raise SystemExit("弱点分析は線形の評価関数だけに対応しています")
    games = hg.load(a.games)
    fast = Fast()
    sw = hg.swings(fast, games, w, top=20)
    text = hg.report_md(fast, games, w, sw)
    write_public(games)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"{a.out} を書きました")
    write_findings(games, sw, a.max_score)
    return 0


def write_public(games: list[dict], out: Path | None = None, download: Path | None = None) -> None:
    """公開する棋譜を、一覧と100局ずつのファイルに分けて書く（中身が同じファイルは書き換えない）。

    全局を1つにまとめたダウンロード用のファイルも書く。
    """
    out = out or PUBLIC
    download = download or DOWNLOAD
    rows = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in games]
    download.write_text("[" + ",\n".join(rows) + "]\n", encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    files = {"index.json": hg.public_index(games)}
    files.update({f"{i}.json": c for i, c in enumerate(hg.public_chunks(games))})
    for name, data in files.items():
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
        f = out / name
        if not f.exists() or f.read_text(encoding="utf-8") != text:
            f.write_text(text, encoding="utf-8")
    for f in out.glob("*.json"):  # 局を消して減ったときの、もう要らない分
        if f.name not in files:
            f.unlink()
    print(f"{out} に {len(games)} 局を書きました（{len(files) - 1} ファイル）")


def read_cache(path: Path | None = None) -> dict:
    path = path or FINDINGS_CACHE
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("{"):  # 前の形（1行に全部）
        return json.loads(text)
    return {k: v for k, v in (json.loads(line) for line in text.splitlines() if line.strip())}


def write_cache(cache: dict, path: Path | None = None) -> None:
    """1局1行（[key, 採点]）。局が増えても差分は増えた行だけになる。"""
    path = path or FINDINGS_CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps([k, cache[k]], sort_keys=True, separators=(",", ":")) + "\n"
            for k in sorted(cache)
        ),
        encoding="utf-8",
    )


def write_findings(games: list[dict], sw: list[dict], max_score: int = MAX_SCORE) -> None:
    """人の手を最強AIで採点し（新しい局だけ、1回に max_score 局まで）、研究ノートの集計 docs/human_findings.json を書く。"""
    import datetime

    from carcassonne import human_findings as hf
    from carcassonne.webplay import champion_info, make_agent, make_coach

    cache = read_cache()
    ai = champion_info().get("name", "")
    coach = None
    scored, moves, numbers, new = [], [], [], 0
    for gi, rec in enumerate(games):
        k = hg.key(rec)
        if k not in cache:
            if new >= max_score:
                continue  # 残りは次の回に採点する
            coach = coach or make_coach(make_agent("strong"))
            cache[k] = {"ai": ai, "moves": hf.analyze_game(rec, coach)}
            new += 1
            print(f"採点しました: {k}")
        scored.append(rec)
        moves.append(cache[k]["moves"])
        numbers.append(gi + 1)
    keys = {hg.key(r) for r in games}
    cache = {k: v for k, v in cache.items() if k in keys}  # 消した局の採点は残さない
    write_cache(cache)
    s = hf.summarize(scored, moves, sw, numbers)
    s["pending"] = len(games) - len(scored)
    s["ai"] = sorted({v["ai"] for v in cache.values()}) or [ai]
    s["updated"] = datetime.date.today().isoformat()
    FINDINGS.write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{FINDINGS} を書きました（採点待ち {s['pending']} 局）")


def cmd_x_draft(a) -> int:
    """区切り（10局ごと）の X 下書き。区切りに届いていなければ何も書かない（題も空）。"""
    from carcassonne import human_findings as hf

    s = json.loads(FINDINGS.read_text(encoding="utf-8")) if FINDINGS.exists() else {"games": 0}
    m = hf.milestone(s["games"])
    Path(a.title).write_text(f"X投稿の下書き: 人との対局 {m}局\n" if m else "", encoding="utf-8")
    if m:
        Path(a.body).write_text(hf.x_issue_body(s), encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--games", default=str(GAMES), help="棋譜をためるファイル")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_add)
    p = sub.add_parser("ingest-issue")
    p.add_argument("--event", required=True, help="GitHub のイベント（$GITHUB_EVENT_PATH）")
    p.add_argument("--result", required=True, help="結果（status・message）を書く JSON")
    p.set_defaults(func=cmd_ingest_issue)
    p = sub.add_parser("ingest-form")
    p.add_argument(
        "--result", required=True, help="結果（added・duplicate・invalid の数）を書く JSON"
    )
    p.set_defaults(func=cmd_ingest_form)
    p = sub.add_parser("x-draft")
    p.add_argument("--title", required=True, help="Issue の題を書くファイル（区切り前なら空）")
    p.add_argument("--body", required=True, help="Issue の本文を書くファイル")
    p.set_defaults(func=cmd_x_draft)
    p = sub.add_parser("report")
    p.add_argument("--out", default=str(REPORT))
    p.add_argument("--max-score", type=int, default=MAX_SCORE, help="1回で新しく採点する局数の上限")
    p.set_defaults(func=cmd_report)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
