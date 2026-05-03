-- CBA pgvector migration (2026-04-16)
--
-- Adds pgvector support to cba_embeddings so semantic search can use
-- SQL operators (<=>, <->) with HNSW index instead of loading all
-- embeddings into Python memory.
--
-- Also extends the table to hold embeddings for BOTH articles
-- (cba_sections) and individual provisions (cba_provisions) — one
-- table, one index, unified semantic search across both object types.
--
-- Run with:
--   psql -h localhost -U postgres -d olms_multiyear -f sql/schema/cba_pgvector_migration.sql
-- Or via db_config.get_connection().cursor().execute() of each statement.

BEGIN;

-- 1) Enable extension (idempotent)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2) Add provision_id column for provision-level embeddings
ALTER TABLE cba_embeddings
    ADD COLUMN IF NOT EXISTS provision_id integer
        REFERENCES cba_provisions(provision_id) ON DELETE CASCADE;

-- 3) Add object_type discriminator (article | provision)
ALTER TABLE cba_embeddings
    ADD COLUMN IF NOT EXISTS object_type varchar(16);

-- Backfill object_type for existing rows (all 38 current rows are articles)
UPDATE cba_embeddings
    SET object_type = 'article'
    WHERE object_type IS NULL AND section_id IS NOT NULL;

ALTER TABLE cba_embeddings
    ALTER COLUMN object_type SET NOT NULL;

-- 4) Make section_id nullable so provision-only rows are allowed
ALTER TABLE cba_embeddings
    ALTER COLUMN section_id DROP NOT NULL;

-- 5) Check constraint: exactly one of (section_id, provision_id) is non-null,
--    matching object_type
ALTER TABLE cba_embeddings
    DROP CONSTRAINT IF EXISTS cba_embeddings_object_check;

ALTER TABLE cba_embeddings
    ADD CONSTRAINT cba_embeddings_object_check
        CHECK (
            (object_type = 'article'   AND section_id   IS NOT NULL AND provision_id IS NULL)
         OR (object_type = 'provision' AND provision_id IS NOT NULL AND section_id   IS NULL)
        );

-- 6) Add halfvec column (3072 dims, matches Gemini gemini-embedding-001)
--    halfvec supports HNSW up to 4000 dims (regular vector caps at 2000)
ALTER TABLE cba_embeddings
    ADD COLUMN IF NOT EXISTS embedding_halfvec halfvec(3072);

-- 7) Backfill halfvec from existing jsonb embeddings (38 rows, takes <1s)
UPDATE cba_embeddings
    SET embedding_halfvec = (
        SELECT array_agg(value::float)::halfvec(3072)
        FROM jsonb_array_elements_text(embedding) AS t(value)
    )
    WHERE embedding_halfvec IS NULL
      AND embedding IS NOT NULL;

-- 8) Drop old unique constraint (section_id, model_name) and add new one
--    that covers both object types via a partial unique index approach
ALTER TABLE cba_embeddings
    DROP CONSTRAINT IF EXISTS cba_embeddings_section_id_model_name_key;
ALTER TABLE cba_embeddings
    DROP CONSTRAINT IF EXISTS cba_embeddings_object_model_unique;

-- Two partial unique indexes — one for each object_type
CREATE UNIQUE INDEX IF NOT EXISTS cba_embeddings_article_unique
    ON cba_embeddings (section_id, model_name)
    WHERE object_type = 'article';

CREATE UNIQUE INDEX IF NOT EXISTS cba_embeddings_provision_unique
    ON cba_embeddings (provision_id, model_name)
    WHERE object_type = 'provision';

-- 9) HNSW index on the halfvec column using cosine distance
--    (Gemini embeddings are already L2-normalized, so cosine works well)
--    m=16, ef_construction=64 are sane defaults for <100K vectors
CREATE INDEX IF NOT EXISTS cba_embeddings_halfvec_hnsw
    ON cba_embeddings
    USING hnsw (embedding_halfvec halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 10) Index to speed up object-type filtering in queries
CREATE INDEX IF NOT EXISTS cba_embeddings_object_type_idx
    ON cba_embeddings (object_type);

COMMIT;

-- Post-migration summary query (run separately to verify)
--
-- SELECT object_type,
--        COUNT(*) AS row_count,
--        COUNT(embedding_halfvec) AS with_halfvec,
--        COUNT(embedding) AS with_jsonb
-- FROM cba_embeddings
-- GROUP BY object_type
-- ORDER BY object_type;
