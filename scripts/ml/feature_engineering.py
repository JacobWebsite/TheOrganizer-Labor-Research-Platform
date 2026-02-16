"""
Phase 5.5: Feature engineering for NLRB election propensity model.

Model A (high-fidelity): Elections matched to OSHA establishments via F7.
Model B (low-fidelity): All elections with state/demographic features only.

Run: imported by train_propensity_model.py
"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


def _log_transform(series):
    """Log(1 + x) transform, handling NaN/negative."""
    return np.log1p(series.clip(lower=0).fillna(0))


def _cyclical_month(month_series):
    """Encode month as sin/cos for cyclical pattern."""
    rad = 2 * np.pi * month_series / 12
    return np.sin(rad), np.cos(rad)


def _one_hot_top_n(df, col, n=15, prefix=None):
    """One-hot encode top-N values of a column, rest as 'other'."""
    prefix = prefix or col
    top_vals = df[col].value_counts().head(n).index.tolist()
    mapped = df[col].where(df[col].isin(top_vals), other='other')
    dummies = pd.get_dummies(mapped, prefix=prefix, dtype=float)
    return dummies


def build_model_a_dataframe(conn=None):
    """Build Model A features: elections matched to OSHA via F7.

    Joins: nlrb_elections -> nlrb_participants -> osha_f7_matches -> osha_establishments
    Returns DataFrame with election outcome + OSHA/employer features.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    sql = """
    SELECT
        e.case_number,
        e.election_date,
        EXTRACT(YEAR FROM e.election_date)::int AS election_year,
        EXTRACT(MONTH FROM e.election_date)::int AS election_month,
        e.election_type,
        e.eligible_voters,
        COALESCE(e.union_won, FALSE)::int AS union_won,
        oe.employee_count,
        LEFT(oe.naics_code, 2) AS naics_2digit,
        oe.naics_code,
        oe.total_violations,
        oe.total_penalties,
        oe.willful_count,
        oe.repeat_count,
        oe.serious_count,
        oe.total_inspections,
        oe.last_inspection_date,
        oe.site_state,
        COALESCE(sd.union_density_pct, 0)::float AS state_density_rate,
        COALESCE(sid.estimated_density, 0)::float AS estimated_density
    FROM nlrb_elections e
    JOIN nlrb_participants p ON p.case_number = e.case_number
        AND p.participant_type = 'Employer'
        AND p.matched_employer_id IS NOT NULL
    JOIN osha_f7_matches ofm ON ofm.f7_employer_id = p.matched_employer_id
    JOIN v_osha_organizing_targets oe ON oe.establishment_id = ofm.establishment_id
    LEFT JOIN bls_state_density sd ON sd.state = oe.site_state AND sd.year = (SELECT MAX(year) FROM bls_state_density)
    LEFT JOIN estimated_state_industry_density sid
        ON sid.state = oe.site_state
        AND LEFT(oe.naics_code, 2) = regexp_replace(COALESCE(sid.industry_code::text, ''), '[^0-9]', '', 'g')
    WHERE e.election_date IS NOT NULL
      AND e.eligible_voters > 0
    """
    df = pd.read_sql(sql, conn)
    if close_conn:
        conn.close()

    if df.empty:
        return df

    # Feature transforms
    df['eligible_voters_log'] = _log_transform(df['eligible_voters'])
    df['employee_count_log'] = _log_transform(df['employee_count'].fillna(0))
    df['total_violations_log'] = _log_transform(df['total_violations'].fillna(0))
    df['total_penalties_log'] = _log_transform(df['total_penalties'].fillna(0))
    df['total_inspections_log'] = _log_transform(df['total_inspections'].fillna(0))

    df['willful_flag'] = (df['willful_count'].fillna(0) > 0).astype(float)
    df['repeat_flag'] = (df['repeat_count'].fillna(0) > 0).astype(float)
    df['serious_ratio'] = df['serious_count'].fillna(0) / df['total_violations'].fillna(0).clip(lower=1)

    # Inspection recency
    df['inspection_recency_years'] = (
        (pd.Timestamp.now() - pd.to_datetime(df['last_inspection_date'], errors='coerce')).dt.days / 365.25
    ).fillna(20.0).clip(upper=30.0)

    # Cyclical month
    df['election_month_sin'], df['election_month_cos'] = _cyclical_month(df['election_month'].fillna(6))

    return df


def build_model_b_dataframe(conn=None):
    """Build Model B features: all elections with basic demographic/state features.

    Uses only election-level data + state density. No OSHA match required.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    sql = """
    SELECT
        e.case_number,
        e.election_date,
        EXTRACT(YEAR FROM e.election_date)::int AS election_year,
        EXTRACT(MONTH FROM e.election_date)::int AS election_month,
        e.election_type,
        e.eligible_voters,
        COALESCE(e.union_won, FALSE)::int AS union_won,
        p.state AS site_state,
        COALESCE(sd.union_density_pct, 0)::float AS state_density_rate
    FROM nlrb_elections e
    JOIN nlrb_participants p ON p.case_number = e.case_number
        AND p.participant_type = 'Employer'
    LEFT JOIN bls_state_density sd ON sd.state = p.state AND sd.year = (SELECT MAX(year) FROM bls_state_density)
    WHERE e.election_date IS NOT NULL
      AND e.eligible_voters > 0
    """
    df = pd.read_sql(sql, conn)
    if close_conn:
        conn.close()

    if df.empty:
        return df

    # Deduplicate (one row per election)
    df = df.drop_duplicates(subset=['case_number'], keep='first')

    # Feature transforms
    df['eligible_voters_log'] = _log_transform(df['eligible_voters'])
    df['election_month_sin'], df['election_month_cos'] = _cyclical_month(df['election_month'].fillna(6))

    return df


def temporal_train_test_split(df, cutoff_year=2023):
    """Split by election year: pre-cutoff = train, cutoff+ = test.

    Prevents temporal leakage: model only learns from past elections.
    """
    train = df[df['election_year'] < cutoff_year].copy()
    test = df[df['election_year'] >= cutoff_year].copy()
    return train, test


def prepare_model_a_features(df):
    """Prepare final feature matrix for Model A (with OSHA data)."""
    feature_cols = [
        'eligible_voters_log', 'election_year',
        'election_month_sin', 'election_month_cos',
        'employee_count_log', 'total_violations_log', 'total_penalties_log',
        'willful_flag', 'repeat_flag', 'serious_ratio',
        'total_inspections_log', 'inspection_recency_years',
        'estimated_density', 'state_density_rate',
    ]

    # One-hot encoding
    naics_dummies = _one_hot_top_n(df, 'naics_2digit', n=15, prefix='naics')
    type_dummies = _one_hot_top_n(df, 'election_type', n=5, prefix='etype')
    state_dummies = _one_hot_top_n(df, 'site_state', n=20, prefix='state')

    X = pd.concat([
        df[feature_cols].fillna(0),
        naics_dummies,
        type_dummies,
        state_dummies,
    ], axis=1)

    y = df['union_won'].values
    return X, y


def prepare_model_b_features(df):
    """Prepare final feature matrix for Model B (no OSHA data)."""
    feature_cols = [
        'eligible_voters_log', 'election_year',
        'election_month_sin', 'election_month_cos',
        'state_density_rate',
    ]

    type_dummies = _one_hot_top_n(df, 'election_type', n=5, prefix='etype')
    state_dummies = _one_hot_top_n(df, 'site_state', n=20, prefix='state')

    X = pd.concat([
        df[feature_cols].fillna(0),
        type_dummies,
        state_dummies,
    ], axis=1)

    y = df['union_won'].values
    return X, y
