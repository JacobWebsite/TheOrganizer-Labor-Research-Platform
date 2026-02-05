"""
Unified Employer Matching Module

Provides consistent employer-to-employer matching across all scenarios
with 4-tier matching pipeline and diff reporting.

Usage:
    from scripts.matching import EmployerMatcher, run_scenario

    matcher = EmployerMatcher(conn)
    result = matcher.match("ACME Hospital Inc", state="NY", city="Buffalo")

    # Run predefined scenario with diff
    from scripts.matching import run_scenario
    run_scenario("mergent_to_f7", save=True, diff=True)
"""

from .pipeline import MatchPipeline
from .config import MatchConfig, SCENARIOS
from .differ import DiffReport

__all__ = [
    'MatchPipeline',
    'MatchConfig',
    'SCENARIOS',
    'DiffReport',
]
