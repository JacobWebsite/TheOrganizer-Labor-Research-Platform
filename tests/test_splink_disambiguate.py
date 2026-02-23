import sys
import types

from scripts.matching.deterministic_matcher import DeterministicMatcher


def test_splink_disambiguate_rejects_below_name_floor(monkeypatch):
    matcher = DeterministicMatcher(
        conn=None,
        run_id="test_run",
        source_system="osha",
        dry_run=True,
        skip_fuzzy=False,
    )
    matcher.min_name_similarity = 0.80

    monkeypatch.setattr(matcher, "_splink_available", lambda: True)
    monkeypatch.setattr(matcher, "_get_splink_model_path", lambda: "fake_model.json")

    class _FakePredResult:
        def as_pandas_dataframe(self):
            import pandas as pd
            return pd.DataFrame(
                [
                    {
                        "id_l": "SRC1",
                        "id_r": "T1",
                        "match_probability": 0.99,
                        "name_normalized_l": "alpha health clinic",
                        "name_normalized_r": "zeus drilling company",
                    }
                ]
            )

    class _FakeInference:
        def predict(self, threshold_match_probability=0.01):
            return _FakePredResult()

    class _FakeLinker:
        def __init__(self, *_args, **_kwargs):
            self.inference = _FakeInference()

    fake_splink = types.SimpleNamespace(DuckDBAPI=object, Linker=_FakeLinker)
    monkeypatch.setitem(sys.modules, "splink", fake_splink)

    source_rec = {
        "id": "SRC1",
        "name": "Alpha Health Clinic",
        "state": "NY",
        "city": "Albany",
        "zip": "12207",
        "naics": "",
        "address": "1 Main St",
    }
    candidates = [
        ("T1", "Zeus Drilling Company", "ALBANY"),
        ("T2", "Alpha Family Practice", "ALBANY"),
    ]

    result = matcher._splink_disambiguate(
        source_rec=source_rec,
        candidates=candidates,
        source_id="SRC1",
        source_name="Alpha Health Clinic",
        state="NY",
        method="NAME_STATE_EXACT",
    )

    assert result is None

