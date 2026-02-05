"""
Diff Report Generation

Compares matching runs to identify new, lost, and changed matches.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class DiffEntry:
    """Single diff entry."""
    source_id: str
    source_name: str
    old_target_id: Optional[str]
    old_target_name: Optional[str]
    new_target_id: Optional[str]
    new_target_name: Optional[str]
    old_method: Optional[str]
    new_method: Optional[str]
    old_score: Optional[float]
    new_score: Optional[float]
    change_type: str  # "NEW", "LOST", "CHANGED", "IMPROVED", "DEGRADED"


@dataclass
class DiffReport:
    """
    Generates diff reports between matching runs.
    """
    conn: Any
    scenario: Optional[str] = None
    run_a_id: Optional[str] = None
    run_b_id: Optional[str] = None

    # Results
    new_matches: List[DiffEntry] = field(default_factory=list)
    lost_matches: List[DiffEntry] = field(default_factory=list)
    changed_matches: List[DiffEntry] = field(default_factory=list)

    # Stats
    run_a_stats: Dict[str, Any] = field(default_factory=dict)
    run_b_stats: Dict[str, Any] = field(default_factory=dict)

    def generate(self, scenario: str = None,
                 run_a: str = None,
                 run_b: str = None) -> 'DiffReport':
        """
        Generate diff between two runs.

        Args:
            scenario: Scenario name (will use latest 2 runs if run_a/b not specified)
            run_a: Older run ID (optional)
            run_b: Newer run ID (optional)

        Returns:
            Self with populated diff data
        """
        self.scenario = scenario or self.scenario

        if not self.scenario and not (run_a and run_b):
            raise ValueError("Must provide scenario or both run IDs")

        cursor = self.conn.cursor()

        # Get run IDs if not provided
        if not run_a or not run_b:
            cursor.execute("""
                SELECT run_id, started_at, total_source, total_matched, match_rate
                FROM match_runs
                WHERE scenario = %s
                ORDER BY started_at DESC
                LIMIT 2
            """, (self.scenario,))

            runs = cursor.fetchall()
            if len(runs) < 2:
                logger.warning(f"Need at least 2 runs to compare. Found {len(runs)}.")
                return self

            self.run_b_id = runs[0][0]  # Newer
            self.run_a_id = runs[1][0]  # Older

            self.run_b_stats = {
                "run_id": runs[0][0],
                "started_at": runs[0][1],
                "total_source": runs[0][2],
                "total_matched": runs[0][3],
                "match_rate": float(runs[0][4]),
            }
            self.run_a_stats = {
                "run_id": runs[1][0],
                "started_at": runs[1][1],
                "total_source": runs[1][2],
                "total_matched": runs[1][3],
                "match_rate": float(runs[1][4]),
            }
        else:
            self.run_a_id = run_a
            self.run_b_id = run_b

            # Load stats
            for run_id, stats_dict in [(run_a, 'run_a_stats'), (run_b, 'run_b_stats')]:
                cursor.execute("""
                    SELECT run_id, started_at, total_source, total_matched, match_rate
                    FROM match_runs
                    WHERE run_id = %s
                """, (run_id,))
                row = cursor.fetchone()
                if row:
                    setattr(self, stats_dict, {
                        "run_id": row[0],
                        "started_at": row[1],
                        "total_source": row[2],
                        "total_matched": row[3],
                        "match_rate": float(row[4]),
                    })

        # Find differences
        self._find_new_matches(cursor)
        self._find_lost_matches(cursor)
        self._find_changed_matches(cursor)

        return self

    def _find_new_matches(self, cursor):
        """Find matches in run_b that weren't in run_a."""
        cursor.execute("""
            SELECT b.source_id, b.target_id, b.method, b.confidence
            FROM match_run_results b
            LEFT JOIN match_run_results a
                ON a.run_id = %s AND a.source_id = b.source_id
            WHERE b.run_id = %s
                AND a.source_id IS NULL
                AND b.target_id IS NOT NULL
        """, (self.run_a_id, self.run_b_id))

        for row in cursor.fetchall():
            self.new_matches.append(DiffEntry(
                source_id=row[0],
                source_name="",  # Would need join to get
                old_target_id=None,
                old_target_name=None,
                new_target_id=row[1],
                new_target_name="",
                old_method=None,
                new_method=row[2],
                old_score=None,
                new_score=float(row[3]) if row[3] else None,
                change_type="NEW",
            ))

    def _find_lost_matches(self, cursor):
        """Find matches in run_a that aren't in run_b."""
        cursor.execute("""
            SELECT a.source_id, a.target_id, a.method, a.confidence
            FROM match_run_results a
            LEFT JOIN match_run_results b
                ON b.run_id = %s AND b.source_id = a.source_id
            WHERE a.run_id = %s
                AND (b.source_id IS NULL OR b.target_id IS NULL)
                AND a.target_id IS NOT NULL
        """, (self.run_b_id, self.run_a_id))

        for row in cursor.fetchall():
            self.lost_matches.append(DiffEntry(
                source_id=row[0],
                source_name="",
                old_target_id=row[1],
                old_target_name="",
                new_target_id=None,
                new_target_name=None,
                old_method=row[2],
                new_method=None,
                old_score=float(row[3]) if row[3] else None,
                new_score=None,
                change_type="LOST",
            ))

    def _find_changed_matches(self, cursor):
        """Find matches where target changed between runs."""
        cursor.execute("""
            SELECT
                a.source_id,
                a.target_id as old_target,
                a.method as old_method,
                a.confidence as old_conf,
                b.target_id as new_target,
                b.method as new_method,
                b.confidence as new_conf
            FROM match_run_results a
            JOIN match_run_results b
                ON b.run_id = %s AND b.source_id = a.source_id
            WHERE a.run_id = %s
                AND a.target_id IS NOT NULL
                AND b.target_id IS NOT NULL
                AND a.target_id != b.target_id
        """, (self.run_b_id, self.run_a_id))

        for row in cursor.fetchall():
            old_conf = float(row[3]) if row[3] else 0
            new_conf = float(row[6]) if row[6] else 0

            if new_conf > old_conf:
                change_type = "IMPROVED"
            elif new_conf < old_conf:
                change_type = "DEGRADED"
            else:
                change_type = "CHANGED"

            self.changed_matches.append(DiffEntry(
                source_id=row[0],
                source_name="",
                old_target_id=row[1],
                old_target_name="",
                new_target_id=row[4],
                new_target_name="",
                old_method=row[2],
                new_method=row[5],
                old_score=old_conf,
                new_score=new_conf,
                change_type=change_type,
            ))

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = []

        lines.append(f"# Match Diff: {self.scenario}")
        lines.append(f"Run A: {self.run_a_id} ({self.run_a_stats.get('started_at', 'N/A')})")
        lines.append(f"Run B: {self.run_b_id} ({self.run_b_stats.get('started_at', 'N/A')})")
        lines.append("")

        # Stats comparison
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Run A | Run B | Change |")
        lines.append("|--------|-------|-------|--------|")

        matched_a = self.run_a_stats.get('total_matched', 0)
        matched_b = self.run_b_stats.get('total_matched', 0)
        delta = matched_b - matched_a
        delta_pct = (delta / matched_a * 100) if matched_a else 0
        lines.append(f"| Matched | {matched_a:,} | {matched_b:,} | {delta:+,} ({delta_pct:+.1f}%) |")

        rate_a = self.run_a_stats.get('match_rate', 0)
        rate_b = self.run_b_stats.get('match_rate', 0)
        rate_delta = rate_b - rate_a
        lines.append(f"| Match Rate | {rate_a:.1f}% | {rate_b:.1f}% | {rate_delta:+.1f}pp |")

        lines.append("")

        # New matches
        if self.new_matches:
            lines.append(f"## New Matches ({len(self.new_matches)})")
            lines.append("")
            lines.append("| Source ID | Target ID | Method | Score |")
            lines.append("|-----------|-----------|--------|-------|")
            for entry in self.new_matches[:20]:  # Limit display
                lines.append(f"| {entry.source_id} | {entry.new_target_id} | {entry.new_method} | {entry.new_score:.3f if entry.new_score else 'N/A'} |")
            if len(self.new_matches) > 20:
                lines.append(f"| ... | {len(self.new_matches) - 20} more | ... | ... |")
            lines.append("")

        # Lost matches
        if self.lost_matches:
            lines.append(f"## Lost Matches ({len(self.lost_matches)})")
            lines.append("")
            lines.append("| Source ID | Old Target | Old Method | Old Score |")
            lines.append("|-----------|------------|------------|-----------|")
            for entry in self.lost_matches[:20]:
                lines.append(f"| {entry.source_id} | {entry.old_target_id} | {entry.old_method} | {entry.old_score:.3f if entry.old_score else 'N/A'} |")
            if len(self.lost_matches) > 20:
                lines.append(f"| ... | {len(self.lost_matches) - 20} more | ... | ... |")
            lines.append("")

        # Changed matches
        if self.changed_matches:
            lines.append(f"## Changed Matches ({len(self.changed_matches)})")
            lines.append("")
            lines.append("| Source ID | Change | Old Target | New Target | Old Score | New Score |")
            lines.append("|-----------|--------|------------|------------|-----------|-----------|")
            for entry in self.changed_matches[:20]:
                lines.append(
                    f"| {entry.source_id} | {entry.change_type} | "
                    f"{entry.old_target_id} | {entry.new_target_id} | "
                    f"{entry.old_score:.3f if entry.old_score else 'N/A'} | "
                    f"{entry.new_score:.3f if entry.new_score else 'N/A'} |"
                )
            if len(self.changed_matches) > 20:
                lines.append(f"| ... | {len(self.changed_matches) - 20} more | ... | ... | ... | ... |")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scenario": self.scenario,
            "run_a": self.run_a_stats,
            "run_b": self.run_b_stats,
            "summary": {
                "new_matches": len(self.new_matches),
                "lost_matches": len(self.lost_matches),
                "changed_matches": len(self.changed_matches),
            },
            "new_matches": [
                {
                    "source_id": e.source_id,
                    "target_id": e.new_target_id,
                    "method": e.new_method,
                    "score": e.new_score,
                }
                for e in self.new_matches
            ],
            "lost_matches": [
                {
                    "source_id": e.source_id,
                    "target_id": e.old_target_id,
                    "method": e.old_method,
                    "score": e.old_score,
                }
                for e in self.lost_matches
            ],
            "changed_matches": [
                {
                    "source_id": e.source_id,
                    "old_target_id": e.old_target_id,
                    "new_target_id": e.new_target_id,
                    "old_method": e.old_method,
                    "new_method": e.new_method,
                    "old_score": e.old_score,
                    "new_score": e.new_score,
                    "change_type": e.change_type,
                }
                for e in self.changed_matches
            ],
        }

    def print_summary(self):
        """Print summary to console."""
        print(f"\n{'='*60}")
        print(f"DIFF REPORT: {self.scenario}")
        print(f"{'='*60}")
        print(f"Run A: {self.run_a_id} ({self.run_a_stats.get('started_at', 'N/A')})")
        print(f"Run B: {self.run_b_id} ({self.run_b_stats.get('started_at', 'N/A')})")
        print()

        matched_a = self.run_a_stats.get('total_matched', 0)
        matched_b = self.run_b_stats.get('total_matched', 0)
        delta = matched_b - matched_a

        print(f"Matches: {matched_a:,} → {matched_b:,} ({delta:+,})")
        print(f"Match Rate: {self.run_a_stats.get('match_rate', 0):.1f}% → {self.run_b_stats.get('match_rate', 0):.1f}%")
        print()
        print(f"New matches:     {len(self.new_matches):,}")
        print(f"Lost matches:    {len(self.lost_matches):,}")
        print(f"Changed matches: {len(self.changed_matches):,}")
        print(f"{'='*60}\n")
