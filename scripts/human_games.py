"""人がAIと指した棋譜（対戦ページから送ってもらったもの）を受け取る・ためる・まとめる。

    py scripts/human_games.py add 棋譜.json ...          # ファイルで受け取った棋譜を検査して足す
    py scripts/human_games.py ingest-issue --event イベント.json --result 結果.json
                                                        # GitHub の Issue で届いた棋譜（human-games.yml から呼ぶ）
    py scripts/human_games.py ingest-form --result 結果.json
                                                        # Google フォームの回答（公開 CSV）を取り込む（human-games.yml から毎日）
    py scripts/human_games.py report                    # docs/results/human_games.md と docs/human_games.json を作り直す
    py scripts/human_games.py remove 3                  # 送った人の依頼で3局目を消す（もう取り込まない）

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
REPLAY = ROOT / "docs" / "human_games.json"  # 対戦ページの再生（play.html#replay=番号）が読む
FORM = ROOT / "data" / "human_games_form.json"


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
        with urllib.request.urlopen(url, timeout=60) as r:
            text = r.read().decode("utf-8-sig")
        out = hg.ingest_rows(hg.form_texts(text), a.games)
        out["delete"] = hg.deletion_requests(text)
    Path(a.result).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(out)
    return 0


def cmd_remove(a) -> int:
    rec = hg.remove(a.games, a.game)
    h = rec["human_seat"]
    print(f"{a.game}局目（人 {rec['scores'][h]} − AI {rec['scores'][1 - h]}）を消しました。report で作り直してください")
    return 0


def cmd_deletion_body(a) -> int:
    print(hg.deletion_body(hg.load(a.games), a.game), end="")
    return 0


def cmd_report(a) -> int:
    from carcassonne.fast import Fast
    from carcassonne.fast_eval import load_eval
    from carcassonne.webplay import champion_eval_path

    w, mode = load_eval(champion_eval_path())
    if mode != 1:
        raise SystemExit("弱点分析は線形の評価関数だけに対応しています")
    games = hg.load(a.games)
    text = hg.report_md(Fast(), games, w)
    REPLAY.write_text(json.dumps(games, separators=(",", ":")) + "\n", encoding="utf-8")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"{a.out} を書きました")
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
    p = sub.add_parser("remove")
    p.add_argument("game", type=int, help="消す対局の番号（1始まり。みんなの対局ページの #番号）")
    p.set_defaults(func=cmd_remove)
    p = sub.add_parser("deletion-body")
    p.add_argument("--game", type=int, required=True)
    p.set_defaults(func=cmd_deletion_body)
    p = sub.add_parser("report")
    p.add_argument("--out", default=str(REPORT))
    p.set_defaults(func=cmd_report)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
