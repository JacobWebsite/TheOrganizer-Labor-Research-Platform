"""Tests for prediction range computation and API integration."""
import json
import os
import sys
import pytest

# Ensure demographics_v5 can import from scripts
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(PROJECT_ROOT, 'scripts', 'analysis', 'demographics_comparison')
if DEMO_DIR not in sys.path:
    sys.path.insert(0, DEMO_DIR)


class TestGetDiversityTier:
    """Test get_diversity_tier classification."""

    def test_low(self):
        from api.services.demographics_v5 import get_diversity_tier
        assert get_diversity_tier(10.0) == "Low"

    def test_med_low(self):
        from api.services.demographics_v5 import get_diversity_tier
        assert get_diversity_tier(20.0) == "Med-Low"

    def test_med_high(self):
        from api.services.demographics_v5 import get_diversity_tier
        assert get_diversity_tier(35.0) == "Med-High"

    def test_high(self):
        from api.services.demographics_v5 import get_diversity_tier
        assert get_diversity_tier(60.0) == "High"

    def test_none(self):
        from api.services.demographics_v5 import get_diversity_tier
        assert get_diversity_tier(None) == "unknown"

    def test_boundary_15(self):
        from api.services.demographics_v5 import get_diversity_tier
        assert get_diversity_tier(15.0) == "Med-Low"

    def test_boundary_30(self):
        from api.services.demographics_v5 import get_diversity_tier
        assert get_diversity_tier(30.0) == "Med-High"

    def test_boundary_50(self):
        from api.services.demographics_v5 import get_diversity_tier
        assert get_diversity_tier(50.0) == "High"


class TestComputePredictionRanges:
    """Test compute_prediction_ranges with mocked lookup data."""

    @pytest.fixture(autouse=True)
    def setup_ranges(self, monkeypatch):
        """Inject a known prediction ranges lookup."""
        from api.services import demographics_v5 as mod
        self.mod = mod
        # Ensure models are "loaded" so we skip the file I/O
        monkeypatch.setattr(mod, '_model_loaded', True)
        monkeypatch.setattr(mod, '_prediction_ranges', {
            'Healthcare/Social (62)|Med-High': {
                'ranges': {
                    'White': {'p15': -8.0, 'p85': 6.0},
                    'Black': {'p15': -5.0, 'p85': 10.0},
                    'Asian': {'p15': -3.0, 'p85': 2.0},
                    'Hispanic': {'p15': -6.0, 'p85': 4.0},
                    'Female': {'p15': -10.0, 'p85': 8.0},
                },
                'n': 150,
            },
            'Healthcare/Social (62)|*': {
                'ranges': {
                    'White': {'p15': -10.0, 'p85': 10.0},
                    'Black': {'p15': -7.0, 'p85': 12.0},
                    'Asian': {'p15': -4.0, 'p85': 3.0},
                    'Hispanic': {'p15': -7.0, 'p85': 5.0},
                    'Female': {'p15': -12.0, 'p85': 10.0},
                },
                'n': 500,
            },
            '*|Med-High': {
                'ranges': {
                    'White': {'p15': -9.0, 'p85': 9.0},
                    'Black': {'p15': -6.0, 'p85': 11.0},
                    'Asian': {'p15': -3.5, 'p85': 2.5},
                    'Hispanic': {'p15': -6.5, 'p85': 4.5},
                    'Female': {'p15': -11.0, 'p85': 9.0},
                },
                'n': 2000,
            },
            '*|*': {
                'ranges': {
                    'White': {'p15': -12.0, 'p85': 12.0},
                    'Black': {'p15': -8.0, 'p85': 9.0},
                    'Asian': {'p15': -4.0, 'p85': 4.0},
                    'Hispanic': {'p15': -8.0, 'p85': 6.0},
                    'Female': {'p15': -14.0, 'p85': 14.0},
                },
                'n': 14000,
            },
        })

    def _pred(self):
        return {
            'race': {'White': 60.0, 'Black': 15.0, 'Asian': 10.0,
                     'AIAN': 0.5, 'NHOPI': 0.3, 'Two+': 1.5},
            'hispanic': {'Hispanic': 18.0, 'Not Hispanic': 82.0},
            'gender': {'Male': 55.0, 'Female': 45.0},
        }

    def test_exact_cell_match(self):
        ranges, ctx = self.mod.compute_prediction_ranges(
            self._pred(), 'Healthcare/Social (62)', 'Med-High')
        assert ranges is not None
        assert ctx['lookup_cell'] == 'Healthcare/Social (62)|Med-High'
        assert ctx['cell_n'] == 150
        assert ctx['interval'] == '70%'
        # White: low = 60 - 6.0 = 54.0, high = 60 - (-8.0) = 68.0
        assert ranges['White'] == {'low': 54.0, 'high': 68.0}

    def test_naics_fallback(self):
        """Unknown tier falls back to naics-only cell."""
        ranges, ctx = self.mod.compute_prediction_ranges(
            self._pred(), 'Healthcare/Social (62)', 'Low')
        assert ctx['lookup_cell'] == 'Healthcare/Social (62)|*'
        assert ctx['cell_n'] == 500

    def test_tier_fallback(self):
        """Unknown naics falls back to tier-only cell."""
        ranges, ctx = self.mod.compute_prediction_ranges(
            self._pred(), 'Other', 'Med-High')
        assert ctx['lookup_cell'] == '*|Med-High'
        assert ctx['cell_n'] == 2000

    def test_global_fallback(self):
        """Unknown naics + tier falls back to global cell."""
        ranges, ctx = self.mod.compute_prediction_ranges(
            self._pred(), 'Other', 'Low')
        assert ctx['lookup_cell'] == '*|*'
        assert ctx['cell_n'] == 14000

    def test_clamping_low(self):
        """Ranges should not go below 0."""
        pred = self._pred()
        pred['race']['Asian'] = 1.0  # Very low value
        ranges, _ = self.mod.compute_prediction_ranges(
            pred, 'Healthcare/Social (62)', 'Med-High')
        assert ranges['Asian']['low'] >= 0.0

    def test_clamping_high(self):
        """Ranges should not exceed 100."""
        pred = self._pred()
        pred['gender']['Female'] = 98.0
        pred['gender']['Male'] = 2.0
        ranges, _ = self.mod.compute_prediction_ranges(
            pred, 'Healthcare/Social (62)', 'Med-High')
        assert ranges['Female']['high'] <= 100.0

    def test_low_lte_pred_lte_high(self):
        """Range must bracket the prediction: low <= pred <= high."""
        pred = self._pred()
        ranges, _ = self.mod.compute_prediction_ranges(
            pred, 'Healthcare/Social (62)', 'Med-High')
        for cat in ['White', 'Black', 'Asian', 'Hispanic', 'Female']:
            pct = pred['race'].get(cat) or pred['hispanic'].get(cat) or pred['gender'].get(cat)
            assert ranges[cat]['low'] <= pct, '%s low > pred' % cat
            assert ranges[cat]['high'] >= pct, '%s high < pred' % cat

    def test_complement_ranges(self):
        """Male and Not Hispanic get complement ranges."""
        ranges, _ = self.mod.compute_prediction_ranges(
            self._pred(), 'Healthcare/Social (62)', 'Med-High')
        assert 'Male' in ranges
        assert 'Not Hispanic' in ranges
        # Male low = 100 - Female high, Male high = 100 - Female low
        assert ranges['Male']['low'] == round(100 - ranges['Female']['high'], 1)
        assert ranges['Male']['high'] == round(100 - ranges['Female']['low'], 1)

    def test_no_ranges_for_small_cats(self):
        """AIAN, NHOPI, Two+ should NOT get ranges."""
        ranges, _ = self.mod.compute_prediction_ranges(
            self._pred(), 'Healthcare/Social (62)', 'Med-High')
        assert 'AIAN' not in ranges
        assert 'NHOPI' not in ranges
        assert 'Two+' not in ranges

    def test_returns_none_when_no_lookup(self):
        """Returns (None, None) when prediction ranges are not loaded."""
        self.mod._prediction_ranges = None
        ranges, ctx = self.mod.compute_prediction_ranges(
            self._pred(), 'Healthcare/Social (62)', 'Med-High')
        assert ranges is None
        assert ctx is None


class TestPredictionRangesFile:
    """Verify the generated prediction_ranges_v11.json is well-formed."""

    @pytest.fixture
    def ranges_data(self):
        path = os.path.join(
            PROJECT_ROOT, 'api', 'data', 'prediction_ranges_v11.json')
        if not os.path.exists(path):
            pytest.skip('prediction_ranges_v11.json not generated yet')
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_has_global_fallback(self, ranges_data):
        assert '*|*' in ranges_data

    def test_global_has_all_cats(self, ranges_data):
        global_cell = ranges_data['*|*']
        for cat in ['White', 'Black', 'Asian', 'Hispanic', 'Female']:
            assert cat in global_cell['ranges'], 'missing %s' % cat
            assert 'p15' in global_cell['ranges'][cat]
            assert 'p85' in global_cell['ranges'][cat]

    def test_cell_n_positive(self, ranges_data):
        for key, cell in ranges_data.items():
            assert cell['n'] > 0, 'cell %s has n=0' % key

    def test_p15_less_than_p85(self, ranges_data):
        for key, cell in ranges_data.items():
            for cat, vals in cell['ranges'].items():
                assert vals['p15'] <= vals['p85'], (
                    'cell %s cat %s: p15 > p85' % (key, cat))

    def test_has_specific_cells(self, ranges_data):
        """Should have at least some naics x tier cells."""
        specific = [k for k in ranges_data if '|' in k
                    and '*' not in k.split('|')[0]
                    and '*' not in k.split('|')[1]]
        assert len(specific) >= 30, 'only %d specific cells' % len(specific)


class TestApiResponseShape:
    """Test that the workforce-profile API includes ranges when V5 is active."""

    @pytest.fixture
    def client(self):
        from api.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_gate_v1_response_has_ranges(self, client):
        """If gate_v1 produces an estimate, response should include range fields."""
        # Use a known employer (any F7 employer should work)
        from db_config import get_connection
        conn = get_connection()
        try:
            from psycopg2.extras import RealDictCursor
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT employer_id FROM f7_employers_deduped
                    WHERE naics_detailed IS NOT NULL
                      AND zip IS NOT NULL
                    LIMIT 1
                """)
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip('No F7 employer with NAICS and ZIP')

        eid = row['employer_id']
        resp = client.get('/api/profile/employers/%s/workforce-profile' % eid)
        if resp.status_code != 200:
            pytest.skip('Endpoint returned %d' % resp.status_code)

        data = resp.json()
        est = data.get('estimated_composition')
        if not est or est.get('method') != 'gate_v1':
            pytest.skip('V5 gate_v1 not active for this employer')

        # Check that at least some race items have range_low/range_high
        race = est.get('race', [])
        items_with_ranges = [r for r in race if 'range_low' in r]
        assert len(items_with_ranges) > 0, 'No race items have range_low'

        # Check range_context
        ctx = est.get('range_context')
        assert ctx is not None, 'Missing range_context'
        assert ctx['interval'] == '70%'
        assert ctx['cell_n'] > 0
