-- Rule-derived hierarchy edges from scripts/llm_dedup/ rule engine (v1).
--
-- Separate from corporate_hierarchy (DUNS/LEI/CIK-keyed, sourced from
-- GLEIF + Mergent) because this table is keyed on master_id pairs and
-- records relationships derived from name-pattern rules, not regulatory
-- filings.
--
-- Rules populated (all from scripts/llm_dedup/rule_engine.py):
--   H4  -> SIBLING_OF  : names differ only by trailing series/numeric token.
--                         Both masters share a synthetic parent_candidate_name
--                         (the stable prefix) and a sibling_cluster_id.
--   H9  -> CHILD_OF    : shorter-name tokens fully contained in longer-name,
--                         both at same ZIP. Shorter master is parent.
--   H12 -> CHILD_OF    : prefix + activity-descriptor suffix, same ZIP.
--                         Shorter master is parent (activity-division pattern).
--
-- Loaded via scripts/llm_dedup/write_hierarchy.py.

CREATE TABLE IF NOT EXISTS rule_derived_hierarchy (
    id                      BIGSERIAL PRIMARY KEY,
    rule                    TEXT NOT NULL,                 -- H4 | H9 | H12
    relationship            TEXT NOT NULL,                 -- SIBLING_OF | CHILD_OF
    child_master_id         BIGINT,                        -- master_id of subordinate (always set)
    parent_master_id        BIGINT,                        -- master_id of parent (NULL for H4 synthetic parents)
    parent_candidate_name   TEXT,                          -- normalized stable-prefix name (H4) or parent core name
    sibling_cluster_id      BIGINT,                        -- groups H4 siblings that share parent_candidate_name
    confidence              NUMERIC(4, 3) NOT NULL,        -- 0.000 to 1.000 (precision from validation)
    source                  TEXT NOT NULL DEFAULT 'rule_engine_v1',
    built_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (rule IN ('H4', 'H9', 'H12')),
    CHECK (relationship IN ('SIBLING_OF', 'CHILD_OF')),
    -- CHILD_OF edges must have both parent and child
    CHECK (relationship <> 'CHILD_OF' OR parent_master_id IS NOT NULL),
    -- SIBLING_OF edges must have a cluster_id (grouping key)
    CHECK (relationship <> 'SIBLING_OF' OR sibling_cluster_id IS NOT NULL),
    -- child_master_id is always required
    CHECK (child_master_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_rdh_child
    ON rule_derived_hierarchy (child_master_id);
CREATE INDEX IF NOT EXISTS idx_rdh_parent
    ON rule_derived_hierarchy (parent_master_id)
    WHERE parent_master_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rdh_cluster
    ON rule_derived_hierarchy (sibling_cluster_id)
    WHERE sibling_cluster_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rdh_parent_name
    ON rule_derived_hierarchy USING gin (parent_candidate_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_rdh_rule_source
    ON rule_derived_hierarchy (rule, source);

COMMENT ON TABLE rule_derived_hierarchy IS
    'Hierarchy edges derived from the scripts/llm_dedup/ rule engine. '
    'Parent/sibling relationships discovered from name patterns, not filings. '
    'Keyed on master_id; separate from corporate_hierarchy.';
