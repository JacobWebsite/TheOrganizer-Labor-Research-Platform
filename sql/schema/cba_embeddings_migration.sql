-- CBA Embeddings table for article classification via Gemini gemini-embedding-001
-- Stores 3072-dimensional embeddings as JSONB arrays
-- Used by scripts/cba/12_embed_classify.py

CREATE TABLE IF NOT EXISTS cba_embeddings (
    embedding_id   SERIAL PRIMARY KEY,
    section_id     INTEGER NOT NULL REFERENCES cba_sections(section_id) ON DELETE CASCADE,
    model_name     VARCHAR(50) NOT NULL DEFAULT 'text-embedding-004',
    dimensions     INTEGER NOT NULL DEFAULT 768,
    embedding      JSONB NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(section_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_cba_embeddings_section ON cba_embeddings(section_id);
