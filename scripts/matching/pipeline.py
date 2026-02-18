"""
Unified Matching Pipeline

Orchestrates the 4-tier matching process:
1. EIN exact match
2. Normalized name + city + state
3. Aggressive normalization + city
4. Trigram fuzzy + state
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Generator
import logging

from .config import MatchConfig, SCENARIOS, get_scenario, TIER_NAMES, CONFIDENCE_LEVELS
from .matchers.base import MatchResult, MatchRunStats
from .matchers.exact import EINMatcher, NormalizedMatcher, AggressiveMatcher
from .matchers.address import AddressMatcher
from .matchers.fuzzy import TrigramMatcher

logger = logging.getLogger(__name__)


class MatchPipeline:
    """
    Unified 5-tier matching pipeline (best-match-wins).

    Evaluates all tiers and returns the most specific (highest-confidence) match:
    1. EIN (if available)
    2. Normalized name + state
    3. Address-enhanced
    4. Aggressive name + city
    5. Fuzzy trigram + state

    All tiers are evaluated; the match with the lowest tier number wins.
    Within the same tier, the highest score wins.
    """

    def __init__(self, conn, config: MatchConfig = None, scenario: str = None,
                 skip_fuzzy: bool = False):
        """
        Initialize pipeline.

        Args:
            conn: Database connection
            config: MatchConfig instance (optional if scenario provided)
            scenario: Predefined scenario name (optional if config provided)
            skip_fuzzy: If True, skip Tier 4 fuzzy matching (faster but fewer matches)
        """
        self.conn = conn
        self.skip_fuzzy = skip_fuzzy

        if config:
            self.config = config
        elif scenario:
            self.config = get_scenario(scenario)
        else:
            raise ValueError("Must provide either config or scenario name")

        # Initialize matchers (conditionally include fuzzy)
        self.matchers = [
            EINMatcher(conn, self.config),
            NormalizedMatcher(conn, self.config),
            AddressMatcher(conn, self.config),
            AggressiveMatcher(conn, self.config),
        ]
        if not skip_fuzzy:
            self.matchers.append(TrigramMatcher(conn, self.config))

        # Run statistics
        self.stats: Optional[MatchRunStats] = None

    def match(self, source_name: str,
              state: Optional[str] = None,
              city: Optional[str] = None,
              ein: Optional[str] = None,
              address: Optional[str] = None,
              source_id: Any = None) -> MatchResult:
        """
        Match a single employer through the 5-tier pipeline.

        Args:
            source_name: Employer name to match
            state: Optional state for filtering
            city: Optional city for filtering
            ein: Optional EIN for tier 1 matching
            address: Optional street address for tier 3 matching
            source_id: Optional source record ID

        Returns:
            MatchResult with match details (matched=False if no match found)
        """
        source_id = source_id or source_name

        # Best-match-wins: evaluate ALL tiers and return the most specific match.
        # Lower tier number = higher specificity = preferred.
        # Within the same tier, higher score wins.
        best = None

        for matcher in self.matchers:
            try:
                result = matcher.match(
                    source_id=source_id,
                    source_name=source_name,
                    state=state,
                    city=city,
                    ein=ein,
                    address=address,
                )
                if result and result.matched:
                    if (best is None
                            or result.tier < best.tier
                            or (result.tier == best.tier
                                and result.score > best.score)):
                        best = result
            except Exception as e:
                logger.warning(f"Matcher {matcher.method} failed: {e}")
                # Rollback to clear aborted transaction state
                try:
                    self.conn.rollback()
                except:
                    pass
                continue

        if best:
            return best

        # No match found
        return MatchResult(
            source_id=source_id,
            source_name=source_name,
            matched=False,
        )

    def run_scenario(self, batch_size: int = 1000,
                     limit: Optional[int] = None,
                     progress_callback=None) -> MatchRunStats:
        """
        Run matching for a predefined scenario.

        Loads source records from database and matches against target table.

        Args:
            batch_size: Number of records to process at a time
            limit: Optional limit on total records to process
            progress_callback: Optional callback(processed, total, matched)

        Returns:
            MatchRunStats with run statistics
        """
        run_id = str(uuid.uuid4())[:8]
        self.stats = MatchRunStats(
            scenario=self.config.name,
            run_id=run_id,
            started_at=datetime.now(),
        )

        logger.info(f"Starting scenario {self.config.name} (run {run_id})")

        cursor = self.conn.cursor()
        cfg = self.config

        # Count source records
        count_query = f"SELECT COUNT(*) FROM {cfg.source_table}"
        if cfg.source_filter:
            count_query += f" WHERE {cfg.source_filter}"
        cursor.execute(count_query)
        total = cursor.fetchone()[0]

        if limit:
            total = min(total, limit)

        self.stats.total_source = total
        logger.info(f"Source records to process: {total:,}")

        # Build select query
        select_cols = [cfg.source_id_col, cfg.source_name_col]
        if cfg.source_state_col:
            select_cols.append(cfg.source_state_col)
        if cfg.source_city_col:
            select_cols.append(cfg.source_city_col)
        if cfg.source_ein_col:
            select_cols.append(cfg.source_ein_col)
        if cfg.source_address_col:
            select_cols.append(cfg.source_address_col)

        query = f"""
            SELECT {', '.join(select_cols)}
            FROM {cfg.source_table}
        """
        if cfg.source_filter:
            query += f" WHERE {cfg.source_filter}"
        if limit:
            query += f" LIMIT {limit}"

        # Process in batches
        processed = 0
        matched = 0

        cursor.execute(query)
        col_names = [desc[0] for desc in cursor.description]

        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break

            for row in rows:
                record = dict(zip(col_names, row))

                result = self.match(
                    source_name=record.get(cfg.source_name_col),
                    state=record.get(cfg.source_state_col),
                    city=record.get(cfg.source_city_col),
                    ein=record.get(cfg.source_ein_col) if cfg.source_ein_col else None,
                    address=record.get(cfg.source_address_col) if cfg.source_address_col else None,
                    source_id=record.get(cfg.source_id_col),
                )

                if result.matched:
                    matched += 1
                    self.stats.results.append(result)

                    # Update tier stats
                    tier = result.tier
                    self.stats.by_tier[tier] = self.stats.by_tier.get(tier, 0) + 1
                    self.stats.by_method[result.method] = self.stats.by_method.get(result.method, 0) + 1

                processed += 1

            if progress_callback:
                progress_callback(processed, total, matched)

            if processed % 10000 == 0:
                logger.info(f"Processed: {processed:,} / {total:,} ({matched:,} matched)")

        self.stats.total_matched = matched
        self.stats.completed_at = datetime.now()
        self.stats.finalize()

        logger.info(f"Completed: {matched:,} / {total:,} matched ({self.stats.match_rate:.1f}%)")

        return self.stats

    def get_results(self) -> Generator[MatchResult, None, None]:
        """
        Generator that yields match results as they're processed.

        Use this for streaming large result sets without loading all into memory.
        """
        cfg = self.config
        cursor = self.conn.cursor()

        # Build select query
        select_cols = [cfg.source_id_col, cfg.source_name_col]
        if cfg.source_state_col:
            select_cols.append(cfg.source_state_col)
        if cfg.source_city_col:
            select_cols.append(cfg.source_city_col)
        if cfg.source_ein_col:
            select_cols.append(cfg.source_ein_col)

        query = f"""
            SELECT {', '.join(select_cols)}
            FROM {cfg.source_table}
        """
        if cfg.source_filter:
            query += f" WHERE {cfg.source_filter}"

        cursor.execute(query)
        col_names = [desc[0] for desc in cursor.description]

        for row in cursor:
            record = dict(zip(col_names, row))

            result = self.match(
                source_name=record.get(cfg.source_name_col),
                state=record.get(cfg.source_state_col),
                city=record.get(cfg.source_city_col),
                ein=record.get(cfg.source_ein_col) if cfg.source_ein_col else None,
                source_id=record.get(cfg.source_id_col),
            )

            yield result


def run_scenario(scenario_name: str, conn,
                 save: bool = False,
                 diff: bool = False,
                 batch_size: int = 1000,
                 limit: Optional[int] = None) -> MatchRunStats:
    """
    Convenience function to run a predefined scenario.

    Args:
        scenario_name: Name of predefined scenario
        conn: Database connection
        save: Whether to save results to database
        diff: Whether to generate diff against previous run
        batch_size: Batch size for processing
        limit: Optional limit on records

    Returns:
        MatchRunStats with run statistics
    """
    pipeline = MatchPipeline(conn, scenario=scenario_name)
    stats = pipeline.run_scenario(batch_size=batch_size, limit=limit)

    if save:
        _save_run(conn, stats, pipeline)

    if diff:
        from .differ import DiffReport
        report = DiffReport(conn)
        report.generate(scenario_name)

    return stats


def _save_run(conn, stats: MatchRunStats, pipeline: MatchPipeline):
    """Save run results to database."""
    cursor = conn.cursor()

    # Ensure tables exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_runs (
            run_id VARCHAR(36) PRIMARY KEY,
            scenario VARCHAR(50) NOT NULL,
            started_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP,
            total_source INT,
            total_matched INT,
            match_rate NUMERIC(5,2)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_run_results (
            run_id VARCHAR(36) REFERENCES match_runs(run_id),
            source_id VARCHAR(100) NOT NULL,
            target_id VARCHAR(100),
            confidence NUMERIC(4,3),
            method VARCHAR(50),
            PRIMARY KEY (run_id, source_id)
        )
    """)

    # Insert run record
    cursor.execute("""
        INSERT INTO match_runs (run_id, scenario, started_at, completed_at,
                                total_source, total_matched, match_rate)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        stats.run_id,
        stats.scenario,
        stats.started_at,
        stats.completed_at,
        stats.total_source,
        stats.total_matched,
        stats.match_rate,
    ))

    # Insert individual match results in batches
    if stats.results:
        batch_size = 1000
        for i in range(0, len(stats.results), batch_size):
            batch = stats.results[i:i + batch_size]
            values = []
            for r in batch:
                values.append((
                    stats.run_id,
                    str(r.source_id),
                    str(r.target_id) if r.target_id else None,
                    r.score,
                    r.method,
                ))
            cursor.executemany("""
                INSERT INTO match_run_results (run_id, source_id, target_id, confidence, method)
                VALUES (%s, %s, %s, %s, %s)
            """, values)

    conn.commit()
    logger.info(f"Saved run {stats.run_id} to database")
