"""
Tests for new source data loaders (ABS, CBP, PPP, Form 5500, LODES, USAspending).

Validates:
- Loader scripts are importable (no syntax errors)
- ABS filename metadata parser extracts correct fields
- Common helpers work correctly
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "etl"))


class TestABSLoader:
    """Tests for newsrc_load_abs.py."""

    def test_importable(self):
        import newsrc_load_abs  # noqa: F401

    def test_filename_parser(self):
        from newsrc_load_abs import parse_filename_meta

        meta = parse_filename_meta("ABS_2023_abscs_state.csv")
        assert meta["abs_vintage"] == "2023"
        assert meta["abs_dataset"] == "abscs"
        assert meta["abs_geo_level"] == "state"

    def test_filename_parser_county(self):
        from newsrc_load_abs import parse_filename_meta

        meta = parse_filename_meta("ABS_2023_abscbo_county.csv")
        assert meta["abs_vintage"] == "2023"
        assert meta["abs_dataset"] == "abscbo"
        assert meta["abs_geo_level"] == "county"

    def test_filename_parser_msa(self):
        from newsrc_load_abs import parse_filename_meta

        meta = parse_filename_meta("ABS_2023_abscb_msa_micro.csv")
        assert meta["abs_vintage"] == "2023"
        assert meta["abs_dataset"] == "abscb"
        assert meta["abs_geo_level"] == "msa_micro"

    def test_filename_parser_no_match(self):
        from newsrc_load_abs import parse_filename_meta

        meta = parse_filename_meta("random_file.csv")
        assert meta["abs_vintage"] is None
        assert meta["abs_dataset"] is None
        assert meta["abs_geo_level"] is None


class TestCommonHelpers:
    """Tests for newsrc_common.py shared utilities."""

    def test_sanitize_columns(self):
        from newsrc_common import sanitize_column_names

        cols = sanitize_column_names(["#FOO", "Bar Baz", "123abc", "", "FOO"])
        assert cols[0] == "foo"
        assert cols[1] == "bar_baz"
        assert cols[2] == "c_123abc"
        assert cols[3] == "col_4"
        assert cols[4] == "foo_2"  # deduped

    def test_sanitize_preserves_order(self):
        from newsrc_common import sanitize_column_names

        result = sanitize_column_names(["A", "B", "C"])
        assert result == ["a", "b", "c"]

    def test_quote_ident(self):
        from newsrc_common import quote_ident

        assert quote_ident("my_table") == '"my_table"'
        assert quote_ident('tab"le') == '"tab""le"'

    def test_header_inject_stream(self):
        import io
        from newsrc_common import HeaderInjectStream

        body = io.StringIO("row1\nrow2\n")
        stream = HeaderInjectStream("header\n", body)
        content = stream.read()
        assert content == "header\nrow1\nrow2\n"


class TestRunAllOrchestrator:
    """Tests for newsrc_run_all.py."""

    def test_importable(self):
        import newsrc_run_all  # noqa: F401

    def test_has_abs_skip_flag(self):
        from newsrc_run_all import parse_args

        # Just verify the parse_args function accepts --skip-abs
        import sys
        old_argv = sys.argv
        sys.argv = ["test", "--skip-abs"]
        try:
            args = parse_args()
            assert args.skip_abs is True
        finally:
            sys.argv = old_argv


class TestCurateOrchestrator:
    """Tests for newsrc_curate_all.py."""

    def test_importable(self):
        import newsrc_curate_all  # noqa: F401

    def test_builder_registry(self):
        from newsrc_curate_all import BUILDERS

        expected = {"form5500", "ppp", "usaspending", "cbp", "lodes", "abs", "acs"}
        assert set(BUILDERS.keys()) == expected

    def test_all_builders_callable(self):
        from newsrc_curate_all import BUILDERS

        for name, func in BUILDERS.items():
            assert callable(func), f"Builder {name} is not callable"
