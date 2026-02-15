-- SQL Schema for IRS Exempt Organization Business Master File (BMF) Staging and Lookup Tables

-- Purpose:
-- This script defines the schema for loading and managing IRS BMF data.
-- It includes a staging table for raw data import and lookup tables for coded fields
-- to ensure data integrity and facilitate analysis.

-- Staging Table: bmf_staging
-- This table is designed to hold the raw BMF data directly from the CSV files.
-- It serves as an initial landing zone before cleaning and normalization.
CREATE TABLE bmf_staging (
    ein TEXT PRIMARY KEY,               -- Employer Identification Number (Unique Identifier)
    name TEXT,                          -- Organization Name
    sort_name TEXT,                     -- Secondary Name, often DBA or chapter name
    in_care_of TEXT,                    -- "In Care Of" Name
    street TEXT,                        -- Street Address
    city TEXT,                          -- City
    state TEXT,                         -- State (or Country for international records)
    zip_code TEXT,                      -- Zip Code
    country TEXT,                       -- Country (derived or from international records)
    group_exemption_number TEXT,        -- Group Exemption Number
    subsection VARCHAR(2),              -- IRS Subsection Code (e.g., '03' for 501(c)(3))
    affiliation VARCHAR(1),             -- Affiliation Code (e.g., '3' for sub-affiliate)
    classification_codes TEXT,          -- Classification Codes
    ruling_date TEXT,                   -- Date of Ruling
    deductibility_code VARCHAR(2),      -- Deductibility Code
    foundation_code VARCHAR(2),         -- Foundation Code
    activity_codes TEXT,                -- Activity Codes
    organization_code VARCHAR(1),       -- Organization Code
    exempt_organization_status TEXT,    -- Exempt Organization Status
    tax_period TEXT,                    -- Tax Period
    asset_code TEXT,                    -- Asset Code
    income_code TEXT,                   -- Income Code
    filing_requirement_code TEXT,       -- Filing Requirement Code
    accounting_period TEXT,             -- Accounting Period
    asset_amount TEXT,                  -- Asset Amount
    income_amount TEXT,                  -- Income Amount
    revenue_amount TEXT,                -- Revenue Amount
    ntee_code VARCHAR(3),               -- National Taxonomy of Exempt Entities (NTEE) Code
    latest_postmark_date TEXT,          -- Latest Postmark Date
    public_charity_status TEXT,         -- Public Charity Status
    digit_check TEXT,                   -- Digit Check
    form_990_return_type TEXT           -- Form 990 Return Type
    -- Additional fields from BMF CSV can be added as needed.
);

-- Lookup Table: bmf_subsection_lookup
-- Stores descriptions for IRS Subsection Codes (e.g., 501(c)(3), 501(c)(5)).
CREATE TABLE bmf_subsection_lookup (
    subsection_code VARCHAR(2) PRIMARY KEY,
    description TEXT
);

-- Lookup Table: bmf_affiliation_lookup
-- Stores descriptions for Affiliation Codes, detailing organizational hierarchy.
CREATE TABLE bmf_affiliation_lookup (
    affiliation_code VARCHAR(1) PRIMARY KEY,
    description TEXT
);

-- Lookup Table: bmf_ntee_lookup
-- Stores descriptions for NTEE Codes, which classify the organization's primary activity.
CREATE TABLE bmf_ntee_lookup (
    ntee_code VARCHAR(3) PRIMARY KEY,
    description TEXT
);

-- Note: The 'STATE' field in the BMF data can sometimes contain country names for international
-- records (e.g., 'CA' for Canada, 'MX' for Mexico). This will require a separate cleaning
-- or mapping step during data import to standardize state/province fields if necessary.
-- The 'zip_code' and 'country' fields may also need similar handling for consistency.

-- Data Loading Strategy:
-- 1. Load raw data from eo_*.csv files into the 'bmf_staging' table.
-- 2. Populate the lookup tables (bmf_subsection_lookup, bmf_affiliation_lookup, bmf_ntee_lookup)
--    using the 'eo-info.pdf' data dictionary or by extracting distinct values from the staging table.
-- 3. Clean and transform data from 'bmf_staging' into final normalized tables, resolving
--    geographic inconsistencies and linking to lookup tables via foreign keys.