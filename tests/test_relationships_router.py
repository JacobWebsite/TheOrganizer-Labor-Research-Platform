"""
Tests for the SEC 10-K relationship endpoints (24Q-16 / 24Q-17 / 24Q-19):
  GET /api/employers/master/{master_id}/suppliers
  GET /api/employers/master/{master_id}/customers
  GET /api/employers/master/{master_id}/distribution-partners

The backing tables (sec_10k_relationship_links, sec_10k_extracted_entities)
are populated by a parallel agent. These tests cover both the
"tables-don't-exist-yet" defensive path and (when the tables exist) the
populated path. We seed our own deterministic test rows in a temporary
sandbox so the tests don't depend on the loader having run.

Coverage:
  1. 200 + empty items[] for valid master_id with no links
  2. 200 + empty items[] when backing tables don't exist (defensive)
  3. 404 for nonexistent master_id
  4. populated items[] respects the limit param
  5. confidence DESC NULLS LAST ordering
  6. stale=True when latest filing > 18 months
  7. stale=False when latest filing <= 18 months
  8. relationship_type filter is enforced (supplier vs customer)
  9. all three endpoint paths reachable (suppliers/customers/distribution-partners)
 10. limit param validation (422)
"""
from __future__ import annotations

import datetime as _dt

import pytest

from db_config import get_connection


# ---------- helpers ----------

def _backing_tables_exist() -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('sec_10k_relationship_links') AS l, "
                "to_regclass('sec_10k_extracted_entities') AS e"
            )
            row = cur.fetchone()
            return bool(row and row[0] and row[1])
    finally:
        conn.close()


def _get_any_master() -> int:
    """Return any valid master_id. Used for the unmatched-master path."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT master_id FROM master_employers
                ORDER BY master_id LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


@pytest.fixture(scope="function")
def seeded_relationships():
    """Seed `sec_10k_relationship_links` (+ extracted_entities) with a
    handful of deterministic rows for two distinct masters and clean up
    after the test.

    Yields a dict:
      {
        "parent_master_id": int,           # has 4 supplier links + 2 customer
        "fresh_filing_master_id": int,     # has 1 supplier link with recent filing
        "stale_filing_master_id": int,     # has 1 supplier link with 2-year-old filing
      }

    Skips the test if the backing tables don't exist.
    """
    if not _backing_tables_exist():
        pytest.skip("sec_10k_relationship_links / sec_10k_extracted_entities not loaded")

    conn = get_connection()
    inserted_link_ids: list[int] = []
    inserted_entity_ids: list[int] = []
    try:
        with conn.cursor() as cur:
            # Pick three distinct existing master_ids -- we won't insert
            # any new masters, just link existing ones to fake child_text.
            cur.execute(
                """
                SELECT master_id FROM master_employers
                ORDER BY master_id LIMIT 3
                """
            )
            rows = cur.fetchall() or []
            if len(rows) < 3:
                pytest.skip("Need at least 3 existing masters to seed relationships")
            parent_id = int(rows[0][0])
            fresh_id = int(rows[1][0])
            stale_id = int(rows[2][0])

            # Confidence-ordering test: insert four supplier links for
            # the same parent with confidences 0.95 / 0.80 / 0.60 / NULL
            # plus one entity row each so the JOIN yields context.
            today = _dt.date.today()

            def _insert_entity(cik: str, accession: str, context: str) -> int:
                # entity_text + section_type are NOT NULL on the upstream
                # extractor's DDL (Agent 1). Use placeholders -- the fixture
                # only exercises the JOIN onto cik/accession/context.
                cur.execute(
                    """
                    INSERT INTO sec_10k_extracted_entities
                      (cik, accession_number, section_type, entity_text, context)
                    VALUES (%s, %s, 'suppliers', '_FIXTURE_ENTITY_', %s)
                    RETURNING id
                    """,
                    [cik, accession, context],
                )
                row = cur.fetchone()
                rid = int(row[0])
                inserted_entity_ids.append(rid)
                return rid

            def _insert_link(
                parent: int,
                rtype: str,
                child_text: str,
                conf,
                method: str,
                filing_date,
                source_entity_id,
                child_master_id=None,
            ) -> int:
                cur.execute(
                    """
                    INSERT INTO sec_10k_relationship_links
                      (parent_master_id, child_master_id, child_text,
                       relationship_type, source_entity_id, confidence,
                       match_method, source_filing_date)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    [parent, child_master_id, child_text, rtype,
                     source_entity_id, conf, method, filing_date],
                )
                row = cur.fetchone()
                rid = int(row[0])
                inserted_link_ids.append(rid)
                return rid

            # parent_id: 4 supplier rows w/ varied confidence + 2 customer rows
            e1 = _insert_entity("0000001", "0000001-25-001", "We rely on Acme Corp for X.")
            e2 = _insert_entity("0000001", "0000001-25-001", "Beta Industries supplies Y.")
            e3 = _insert_entity("0000001", "0000001-25-001", "Gamma LLC delivers Z.")
            e4 = _insert_entity("0000001", "0000001-25-001", "Delta Co provides W.")

            _insert_link(parent_id, "supplier", "Acme Corp", 0.95,
                         "exact", today, e1)
            _insert_link(parent_id, "supplier", "Beta Industries", 0.80,
                         "trigram", today, e2)
            _insert_link(parent_id, "supplier", "Gamma LLC", 0.60,
                         "alias", today, e3)
            # NULL confidence (unmatched) -- must sort LAST
            _insert_link(parent_id, "supplier", "Delta Co", None,
                         "unmatched", today, e4)

            ce1 = _insert_entity("0000001", "0000001-25-001", "Customer Foo bought.")
            ce2 = _insert_entity("0000001", "0000001-25-001", "Customer Bar bought.")
            _insert_link(parent_id, "customer", "Foo Inc", 0.90,
                         "exact", today, ce1)
            _insert_link(parent_id, "customer", "Bar Co", 0.75,
                         "trigram", today, ce2)

            # parent_id: also a distribution row
            de1 = _insert_entity("0000001", "0000001-25-001", "Distributed via Zeta.")
            _insert_link(parent_id, "distribution", "Zeta Distributors", 0.85,
                         "exact", today, de1)

            # fresh_id: one fresh supplier (today)
            fe1 = _insert_entity("0000002", "0000002-25-001", "Fresh.")
            _insert_link(fresh_id, "supplier", "FreshCo", 0.95,
                         "exact", today, fe1)

            # stale_id: one supplier from 2 years ago
            two_years_ago = today - _dt.timedelta(days=730)
            se1 = _insert_entity("0000003", "0000003-23-001", "Old.")
            _insert_link(stale_id, "supplier", "StaleCo", 0.95,
                         "exact", two_years_ago, se1)

            conn.commit()

        yield {
            "parent_master_id": parent_id,
            "fresh_filing_master_id": fresh_id,
            "stale_filing_master_id": stale_id,
        }
    finally:
        # Teardown: delete only the rows we inserted.
        try:
            with conn.cursor() as cur:
                if inserted_link_ids:
                    cur.execute(
                        "DELETE FROM sec_10k_relationship_links WHERE id = ANY(%s)",
                        [inserted_link_ids],
                    )
                if inserted_entity_ids:
                    cur.execute(
                        "DELETE FROM sec_10k_extracted_entities WHERE id = ANY(%s)",
                        [inserted_entity_ids],
                    )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()


# ---------- tests ----------

# --- shape / 404 / defensive (no fixture) ---

def test_404_on_unknown_master_suppliers(client):
    r = client.get("/api/employers/master/999999999/suppliers")
    assert r.status_code == 404


def test_404_on_unknown_master_customers(client):
    r = client.get("/api/employers/master/999999999/customers")
    assert r.status_code == 404


def test_404_on_unknown_master_distribution(client):
    r = client.get("/api/employers/master/999999999/distribution-partners")
    assert r.status_code == 404


def test_empty_shape_for_known_master_no_links(client):
    """Master with no links -> 200 + items: [], NOT 404.

    Works whether or not the backing tables exist:
      - tables missing  -> defensive empty shape
      - tables present  -> aggregate yields zero, empty shape returned
    Either way the contract is identical.
    """
    master_id = _get_any_master()
    if master_id == 0:
        pytest.skip("No masters in DB")

    for path in ("suppliers", "customers", "distribution-partners"):
        r = client.get(f"/api/employers/master/{master_id}/{path}")
        assert r.status_code == 200, f"{path}: {r.status_code} -- {r.text}"
        data = r.json()
        # Required keys per contract
        for k in ("master_id", "relationship_type", "source", "as_of",
                  "items", "total_extracted", "total_matched", "stale"):
            assert k in data, f"{path}: missing key {k}"
        assert data["master_id"] == master_id
        assert data["source"] == "10-K text mining"
        # Empty-shape invariants (true whether backing tables exist or not)
        # Note: if rows were seeded by another test/fixture this could be
        # nonzero, but we picked the lowest master_id which is unlikely to
        # have 10-K relationship links seeded.
        if data["total_extracted"] == 0:
            assert data["items"] == []
            assert data["total_matched"] == 0
            assert data["stale"] is False


def test_relationship_type_field_matches_path(client):
    master_id = _get_any_master()
    if master_id == 0:
        pytest.skip("No masters in DB")
    r1 = client.get(f"/api/employers/master/{master_id}/suppliers")
    assert r1.json()["relationship_type"] == "supplier"
    r2 = client.get(f"/api/employers/master/{master_id}/customers")
    assert r2.json()["relationship_type"] == "customer"
    r3 = client.get(f"/api/employers/master/{master_id}/distribution-partners")
    assert r3.json()["relationship_type"] == "distribution"


def test_limit_param_validation(client):
    master_id = _get_any_master()
    if master_id == 0:
        pytest.skip("No masters in DB")
    r = client.get(f"/api/employers/master/{master_id}/suppliers?limit=0")
    assert r.status_code == 422
    r = client.get(f"/api/employers/master/{master_id}/suppliers?limit=500")
    assert r.status_code == 422


# --- populated path (require seeded fixture) ---

def test_populated_suppliers_with_seeded_data(client, seeded_relationships):
    master_id = seeded_relationships["parent_master_id"]
    r = client.get(f"/api/employers/master/{master_id}/suppliers")
    assert r.status_code == 200
    data = r.json()
    assert data["master_id"] == master_id
    assert data["relationship_type"] == "supplier"
    # 4 supplier rows seeded for parent_master_id
    assert data["total_extracted"] == 4
    # 0 of them have child_master_id -- all are unmatched-by-text in our
    # seed (we used fake child_text and didn't set child_master_id).
    assert data["total_matched"] == 0
    assert len(data["items"]) == 4
    # stale should be False -- all seeded with today's date
    assert data["stale"] is False
    # Item shape sanity
    item = data["items"][0]
    for k in ("child_master_id", "name", "confidence", "match_method",
              "source_filing", "context"):
        assert k in item, f"missing key: {k}"
    sf = item["source_filing"]
    for k in ("cik", "accession_number", "filing_date"):
        assert k in sf, f"missing source_filing key: {k}"


def test_supplier_relationship_type_excludes_customer_rows(
    client, seeded_relationships
):
    """Filter must not bleed customer or distribution rows into the
    suppliers response. The seed fixture inserts 4 supplier + 2 customer
    + 1 distribution rows for parent_master_id."""
    master_id = seeded_relationships["parent_master_id"]
    r_sup = client.get(f"/api/employers/master/{master_id}/suppliers")
    r_cust = client.get(f"/api/employers/master/{master_id}/customers")
    r_dist = client.get(
        f"/api/employers/master/{master_id}/distribution-partners"
    )
    assert r_sup.json()["total_extracted"] == 4
    assert r_cust.json()["total_extracted"] == 2
    assert r_dist.json()["total_extracted"] == 1


def test_confidence_ordering_with_nulls_last(client, seeded_relationships):
    """Items must come back ordered by confidence DESC NULLS LAST.
    Seeded confidences: 0.95, 0.80, 0.60, NULL -> expect that order."""
    master_id = seeded_relationships["parent_master_id"]
    r = client.get(f"/api/employers/master/{master_id}/suppliers")
    items = r.json()["items"]
    assert len(items) == 4
    confs = [i["confidence"] for i in items]
    # Nones must be at the end
    assert confs[-1] is None
    # Non-null prefix must be DESC
    non_null = [c for c in confs if c is not None]
    assert non_null == sorted(non_null, reverse=True)


def test_limit_truncates_items_only(client, seeded_relationships):
    master_id = seeded_relationships["parent_master_id"]
    r = client.get(f"/api/employers/master/{master_id}/suppliers?limit=2")
    data = r.json()
    assert len(data["items"]) == 2
    # Aggregates should reflect the FULL set, not the truncated one
    assert data["total_extracted"] == 4
    # Top-2 should still be the highest-confidence rows
    assert data["items"][0]["confidence"] == 0.95
    assert data["items"][1]["confidence"] == 0.80


def test_stale_false_when_filing_recent(client, seeded_relationships):
    master_id = seeded_relationships["fresh_filing_master_id"]
    r = client.get(f"/api/employers/master/{master_id}/suppliers")
    data = r.json()
    assert data["total_extracted"] == 1
    assert data["stale"] is False


def test_stale_true_when_filing_too_old(client, seeded_relationships):
    """Latest filing > 18 months -> stale=True."""
    master_id = seeded_relationships["stale_filing_master_id"]
    r = client.get(f"/api/employers/master/{master_id}/suppliers")
    data = r.json()
    assert data["total_extracted"] == 1
    assert data["stale"] is True
