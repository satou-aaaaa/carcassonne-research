"""docs/BACKLOG.md（研究の「次にやること」一覧）の書き方を確かめる。

毎日の研究の回（satou-aaaaa/shared-workflows の routines/research-loop.md と
scripts/research-next.mjs）がこの一覧を読んで今日の1件を選ぶので、読めない書き方を main に入れない。
"""

import re
from pathlib import Path

BACKLOG = Path(__file__).resolve().parents[1] / "docs" / "BACKLOG.md"
STATES = {"次", "作業中", "済み", "保留", "やめた"}


def _items():
    items = []
    cur = None
    for line in BACKLOG.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(R-\d{3,})\s+(.+?)\s*$", line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2), "fields": {}}
            items.append(cur)
            continue
        if line.startswith("## "):
            cur = None
            continue
        f = cur is not None and re.match(r"^-\s*([^:：]+)[:：]\s*(.*)$", line)
        if f and f.group(1).strip() not in cur["fields"]:
            cur["fields"][f.group(1).strip()] = f.group(2).strip()
    return items


def test_backlog_is_readable():
    items = _items()
    assert items, "docs/BACKLOG.md に「## R-001 題」の項目が無い"
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)), f"番号が重なっている: {ids}"
    for it in items:
        f = it["fields"]
        assert f.get("状態") in STATES, (
            f"{it['id']} の状態「{f.get('状態')}」は {sorted(STATES)} のどれでもない"
        )
        assert f.get("完了条件"), f"{it['id']} に「完了条件」が無い"
        if f["状態"] == "済み":
            assert f.get("結果"), f"{it['id']} は済みなのに「結果」が無い"
        if f["状態"] == "保留":
            assert f.get("保留の理由"), f"{it['id']} は保留なのに「保留の理由」が無い"
        for w in re.findall(r"R-\d{3,}", f.get("待ち", "")):
            assert w in ids, f"{it['id']} の待ち {w} が一覧に無い"
    working = [i["id"] for i in items if i["fields"]["状態"] == "作業中"]
    assert len(working) <= 1, f"作業中は1件まで: {working}"
