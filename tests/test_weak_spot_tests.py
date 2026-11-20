"""人が外した局面のテスト問題（data/weak_spot_tests.json）の形を確かめる。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_weak_spot_tests_are_well_formed():
    d = json.loads((ROOT / "data" / "weak_spot_tests.json").read_text(encoding="utf-8"))
    tests = d["tests"]
    assert len(tests) >= 50
    for t in tests:
        vals = {tuple(v[:4]): v[4] for v in t["vals"]}
        assert max(vals.values()) == t["best"]
        # 正解は最善から good_within 点以内、人の手は正解に入らない
        assert all(
            t["best"] - vals[tuple(m)] <= d["good_within"] + 1e-9
            for m in t["good"]
            if tuple(m) in vals
        )
        assert t["human"] not in t["good"] and t["human_loss"] >= d["clear"]
