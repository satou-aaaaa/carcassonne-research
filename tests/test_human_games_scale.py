"""棋譜が何千局にたまっても困らないための仕組み（公開ファイルの分割・取り込みの速さ・採点の上限）。

ページの表示（一覧を分けて並べる・番号で開いた局を再生できる）は scripts/ui_check.mjs が
5000局のにせものの一覧で確かめる。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from carcassonne import human_findings as hf
from carcassonne import human_games as hg

from .test_human_games import TS, make_record

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "human_games_script", ROOT / "scripts" / "human_games.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def games():
    return [hg.normalize(make_record(s, s % 2), TS) for s in range(7)]


def test_public_index_is_light(games):
    rows = hg.public_index(games)
    r, rec = rows[1], games[1]
    h = rec["human_seat"]
    assert r == [rec["level"], h, rec["scores"][h], rec["scores"][1 - h], len(rec["moves"]), 0]
    # 1局あたり数十バイト（棋譜の本体は1局 1KB ほど）。5000局でも数百KB に収まる
    per = len(json.dumps(rows, separators=(",", ":"))) / len(rows)
    assert per < 60


def test_public_chunks_keep_numbering(games):
    chunks = hg.public_chunks(games, size=3)
    assert [len(c) for c in chunks] == [3, 3, 1]
    n = 5  # 5局目（1始まり）は (n-1)//3 番目のファイルの (n-1)%3 番目
    assert chunks[(n - 1) // 3][(n - 1) % 3] is games[n - 1]


def test_page_uses_same_chunk_size():
    """対戦ページの再生が読むファイルの決め方が、書く側（CHUNK）と同じ。"""
    js = (ROOT / "web" / "play.html").read_text(encoding="utf-8")
    m = re.search(r"const PUBLIC_CHUNK = (\d+);", js)
    assert m and int(m.group(1)) == hg.CHUNK
    tpl = (ROOT / "web" / "games_template.html").read_text(encoding="utf-8")
    assert '"human_games/index.json"' in tpl
    assert "fetch(SRC" in tpl and '../human_games.json"' not in tpl.split("<script>")[1]


def test_write_public_rewrites_only_changed_files(tmp_path, games):
    mod = load_script()
    out, dl = tmp_path / "pub", tmp_path / "all.json"
    mod.write_public(games[:3], out, dl)
    assert json.loads(dl.read_text()) == games[:3]  # 全局のダウンロード用（1局1行）
    assert len(dl.read_text().splitlines()) == 3
    assert sorted(f.name for f in out.iterdir()) == ["0.json", "index.json"]
    chunk = out / "0.json"
    before = chunk.stat().st_mtime_ns
    mod.write_public(games[:3], out, dl)  # 同じ中身なら書き換えない（git の差分が増えない）
    assert chunk.stat().st_mtime_ns == before
    (out / "7.json").write_text("[]")  # もう要らないファイル（にせもの）は消す
    mod.write_public(games[:3], out, dl)
    assert not (out / "7.json").exists()
    assert json.loads((out / "index.json").read_text()) == hg.public_index(games[:3])


def test_form_skips_known_games_without_rechecking(tmp_path, games, monkeypatch):
    """フォームの表は回答がたまり続ける。受け取り済みの局は検査（再生）し直さず、ファイルも1回だけ読む。"""
    path = tmp_path / "g.jsonl"
    for r in games[:3]:
        hg.add(path, r)
    texts = [json.dumps(r) for r in games]
    calls = {"normalize": 0, "load": 0}
    real_norm, real_load = hg.normalize, hg.load

    def norm(obj, ts=None):
        calls["normalize"] += 1
        return real_norm(obj, ts)

    def load(p):
        calls["load"] += 1
        return real_load(p)

    monkeypatch.setattr(hg, "normalize", norm)
    monkeypatch.setattr(hg, "load", load)
    got = hg.ingest_rows(texts + texts, path, TS)
    assert got == {"added": 4, "duplicate": 10, "invalid": 0}
    assert calls == {"normalize": 4, "load": 1}
    assert len(real_load(path)) == 7


def test_cache_is_one_line_per_game_and_reads_old_format(tmp_path):
    mod = load_script()
    f = tmp_path / "cache.json"
    cache = {"b": {"ai": "g", "moves": []}, "a": {"ai": "g", "moves": [{"ply": 0}]}}
    mod.write_cache(cache, f)
    assert len(f.read_text().splitlines()) == 2
    assert mod.read_cache(f) == cache
    f.write_text(json.dumps(cache))  # 前の形（1行に全部）も読める
    assert mod.read_cache(f) == cache


def test_summarize_keeps_game_numbers_of_scored_subset(games):
    """採点が追いつかず一部の局だけで集計しても、大きく損した手の番号は全体の番号のまま。"""
    moves = [[{"ply": 4, "loss": 6.0, "mine": None, "best": "C", "cat": "no_meeple"}]]
    s = hf.summarize([games[4]], moves, [], numbers=[5])
    assert s["games"] == 1 and s["worst"][0]["game"] == 5


def test_report_scores_at_most_max_per_run(tmp_path, games, monkeypatch):
    """1回の report で新しく採点するのは max_score 局まで。残りは次の回にまわし、採点待ちとして数える。"""
    import carcassonne.webplay as wp

    mod = load_script()
    real = mod.FINDINGS_CACHE.read_bytes() if mod.FINDINGS_CACHE.exists() else None
    monkeypatch.setattr(mod, "FINDINGS_CACHE", tmp_path / "cache.json")
    monkeypatch.setattr(mod, "FINDINGS", tmp_path / "findings.json")
    monkeypatch.setattr(wp, "make_agent", lambda level: None)
    monkeypatch.setattr(wp, "make_coach", lambda agent: None)
    monkeypatch.setattr(hf, "analyze_game", lambda rec, coach: [])
    mod.write_findings(games, [], max_score=3)
    s = json.loads((tmp_path / "findings.json").read_text())
    assert s["games"] == 3 and s["pending"] == 4
    mod.write_findings(games, [], max_score=3)
    mod.write_findings(games, [], max_score=3)
    s = json.loads((tmp_path / "findings.json").read_text())
    assert s["games"] == 7 and s["pending"] == 0
    # 本物の採点（リポジトリの docs/results/）には触らない（既定の引数で置き場所を固定すると書き換えてしまう）
    real_path = ROOT / "docs" / "results" / "human_findings_cache.json"
    assert (real_path.read_bytes() if real_path.exists() else None) == real
