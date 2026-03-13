-- ============================================================================
-- CBA Sections Migration
-- Progressive decomposition: TOC-based section splitting with page images
-- Idempotent: safe to re-run.
-- Created: 2026-03-12
-- ============================================================================

-- ============================================================================
-- 1. cba_sections table (Pass 2: TOC-based decomposition)
-- ============================================================================

CREATE TABLE IF NOT EXISTS cba_sections (
    section_id      SERIAL PRIMARY KEY,
    cba_id          INTEGER NOT NULL REFERENCES cba_documents(cba_id) ON DELETE CASCADE,
    section_num     VARCHAR(20) NOT NULL,           -- "I", "XIX.3", "Side Letters"
    section_title   VARCHAR(500) NOT NULL,
    section_level   INTEGER NOT NULL DEFAULT 1,     -- 1=article, 2=sub-section
    parent_section_id INTEGER REFERENCES cba_sections(section_id),
    sort_order      INTEGER NOT NULL,
    section_text    TEXT NOT NULL,
    char_start      INTEGER NOT NULL,
    char_end        INTEGER NOT NULL,
    page_start      INTEGER,
    page_end        INTEGER,
    detection_method VARCHAR(30) NOT NULL,           -- 'toc_parsed', 'heading_heuristic', 'manual'
    attributes      JSONB DEFAULT '{}'::jsonb,       -- Pass 3+ sub-fields
    has_page_images BOOLEAN DEFAULT FALSE,
    page_image_paths JSONB DEFAULT '[]'::jsonb,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cba_sections_cba_id ON cba_sections(cba_id);
CREATE INDEX IF NOT EXISTS idx_cba_sections_parent ON cba_sections(parent_section_id);
CREATE INDEX IF NOT EXISTS idx_cba_sections_title_gin ON cba_sections USING gin(to_tsvector('english', section_title));
CREATE INDEX IF NOT EXISTS idx_cba_sections_attrs_gin ON cba_sections USING gin(attributes);

-- ============================================================================
-- 2. cba_page_images table (page-level image extraction)
-- ============================================================================

CREATE TABLE IF NOT EXISTS cba_page_images (
    image_id     SERIAL PRIMARY KEY,
    cba_id       INTEGER NOT NULL REFERENCES cba_documents(cba_id) ON DELETE CASCADE,
    section_id   INTEGER REFERENCES cba_sections(section_id),
    page_number  INTEGER NOT NULL,
    file_path    TEXT NOT NULL,
    image_format VARCHAR(10) DEFAULT 'png',
    width_px     INTEGER,
    height_px    INTEGER,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cba_id, page_number)
);

-- ============================================================================
-- 3. New columns on cba_documents for decomposition tracking
-- ============================================================================

ALTER TABLE cba_documents ADD COLUMN IF NOT EXISTS toc_json JSONB;
ALTER TABLE cba_documents ADD COLUMN IF NOT EXISTS decomposition_status VARCHAR(20) DEFAULT 'pending';
