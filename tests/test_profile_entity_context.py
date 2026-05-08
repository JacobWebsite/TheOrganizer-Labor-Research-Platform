"""
Integration tests for entity_context in profile / master / unified-detail routes.

Asserts the #44 response shape on known real employers. Depends on the dev DB
being loaded with the standard Apr 2026 snapshot.

Run: py -m pytest tests/test_profile_entity_context.py -v
"""


# ---------- F7 route: /api/profile/employers/{id} ----------

def test_f7_starbucks_has_entity_context(client):
    """Starbucks F7 store: has unit + group (234 members), family null (no crosswalk)."""
    r = client.get("/api/profile/employers/79cf00473da55af3")
    assert r.status_code == 200
    data = r.json()
    ec = data.get("entity_context")
    assert ec is not None

    assert ec["display_mode"] in ("unit_primary", "family_primary")
    assert ec["unit"] is not None
    assert ec["unit"]["count"] == 90
    assert ec["unit"]["city"] == "Anaheim"
    assert ec["unit"]["label"] == "This unit"

    assert ec["group"] is not None
    assert ec["group"]["member_count"] == 234
    assert ec["group"]["canonical_name"] == "Starbucks"


def test_f7_single_site_has_no_group(client):
    """Aventura Hospital: no canonical_group_id -> group is null."""
    r = client.get("/api/profile/employers/0144d5b13f394288")
    assert r.status_code == 200
    ec = r.json()["entity_context"]

    assert ec is not None
    assert ec["display_mode"] == "unit_primary"
    assert ec["unit"] is not None
    assert ec["group"] is None
    assert ec["family"] is None


def test_f7_response_backwards_compatible(client):
    """Legacy employer fields still present on the response (external-caller regression)."""
    r = client.get("/api/profile/employers/79cf00473da55af3")
    data = r.json()
    employer = data["employer"]
    # These keys were always on the response; entity_context is additive.
    for key in ("employer_id", "employer_name", "latest_unit_size"):
        assert key in employer


# ---------- Master route: /api/master/{id} ----------

def test_master_ibm_has_family_from_mergent(client):
    """IBM master (1995673) has Mergent data -> family_primary with ~279K."""
    r = client.get("/api/master/1995673")
    assert r.status_code == 200
    ec = r.json()["entity_context"]

    assert ec is not None
    assert ec["display_mode"] == "family_primary"
    assert ec["family"] is not None
    assert ec["family"]["mergent_count"] is not None
    assert ec["family"]["mergent_count"] > 100_000
    assert ec["family"]["primary_source"] in ("sec_10k", "mergent_company")
    assert ec["family"]["label"] == "Corp. Family"


# ---------- unified-detail route: /api/employers/unified-detail/{canonical_id} ----------

def test_unified_detail_master_matches_master_route(client):
    """MASTER-{id} on unified-detail produces the same family shape as /api/master/{id}."""
    r_master = client.get("/api/master/1995673")
    r_unified = client.get("/api/employers/unified-detail/MASTER-1995673")
    assert r_master.status_code == 200
    assert r_unified.status_code == 200

    ec_master = r_master.json()["entity_context"]
    ec_unified = r_unified.json()["entity_context"]

    assert ec_master is not None and ec_unified is not None
    # Family primary count + source should agree across the two routes.
    fam_m = ec_master["family"]
    fam_u = ec_unified["family"]
    assert fam_m is not None and fam_u is not None
    assert fam_m["primary_count"] == fam_u["primary_count"]
    assert fam_m["primary_source"] == fam_u["primary_source"]


def test_unified_detail_f7_has_entity_context(client):
    """F7 path on unified-detail emits the same entity_context shape as /api/profile/."""
    r = client.get("/api/employers/unified-detail/79cf00473da55af3")
    assert r.status_code == 200
    ec = r.json()["entity_context"]
    assert ec is not None
    assert "unit" in ec and "group" in ec and "family" in ec and "display_mode" in ec


# ---------- Shape contract ----------

def test_entity_context_shape_keys():
    """Smoke-level contract: top-level keys are stable."""
    from api.services.entity_context import build_entity_context_minimal
    out = build_entity_context_minimal({"eligible_voters": 42}, "NLRB")
    assert set(out.keys()) == {"display_mode", "unit", "group", "family"}
    assert out["display_mode"] == "unit_primary"
    assert out["unit"]["count"] == 42
    assert out["group"] is None
    assert out["family"] is None
