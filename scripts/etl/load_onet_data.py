"""
Load O*NET bulk files into PostgreSQL.

Source: https://www.onetcenter.org/database.html

Expected local files under data/onet/ (CSV or tab-delimited TXT):
- Work Context: one of
  - data/onet/Work Context.csv
  - data/onet/work_context.csv
  - data/onet/Work Context.txt
- Job Zones: one of
  - data/onet/Job Zones.csv
  - data/onet/job_zones.csv
  - data/onet/Job Zones.txt

Creates/loads:
- onet_work_context
- onet_job_zones

Join path used by this platform:
  onet_*.onetsoc_code
    -> bls_industry_occupation_matrix.occ_code
    -> NAICS
    -> f7_employers_deduped.naics_code

Usage:
  py scripts/etl/load_onet_data.py
  py scripts/etl/load_onet_data.py --drop-existing
"""

import argparse
import csv
import os
import sys
from pathlib import Path

from psycopg2.extras import execute_values

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


DATA_DIR = Path('data') / 'onet'
WORK_CONTEXT_CANDIDATES = ['Work Context.csv', 'work_context.csv', 'Work Context.txt']
JOB_ZONES_CANDIDATES = ['Job Zones.csv', 'job_zones.csv', 'Job Zones.txt']
BATCH_SIZE = 5000


def find_input_file(candidates):
    for name in candidates:
        path = DATA_DIR / name
        if path.exists():
            return path
    return None


def normalize_key(key):
    return ''.join(ch.lower() for ch in key if ch.isalnum())


def detect_delimiter(path: Path) -> str:
    return '\t' if path.suffix.lower() == '.txt' else ','


def parse_num(value):
    if value in (None, ''):
        return None
    try:
        return float(str(value).replace(',', ''))
    except ValueError:
        return None


def parse_int(value):
    if value in (None, ''):
        return None
    try:
        return int(float(str(value).replace(',', '')))
    except ValueError:
        return None


def field_lookup(row):
    normalized = {normalize_key(k): v for k, v in row.items()}

    def get(*keys):
        for key in keys:
            if key in normalized:
                val = normalized[key]
                return val.strip() if isinstance(val, str) else val
        return None

    return get


def iter_work_context_rows(path: Path):
    delimiter = detect_delimiter(path)
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            get = field_lookup(row)
            yield (
                get('onetsoccode', 'onet_soc_code'),
                get('elementid'),
                get('elementname'),
                get('scaleid'),
                get('scalename'),
                parse_num(get('datavalue')),
                parse_int(get('n')),
                parse_num(get('standarderror')),
                parse_num(get('lowercibound')),
                parse_num(get('uppercibound')),
                get('recommendsuppress'),
                get('notrelevant'),
                get('date'),
                get('domainsource'),
            )


def iter_job_zone_rows(path: Path):
    delimiter = detect_delimiter(path)
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            get = field_lookup(row)
            yield (
                get('onetsoccode', 'onet_soc_code'),
                get('title'),
                parse_int(get('jobzone')),
                get('education'),
                get('relatedexperience'),
                get('jobtraining'),
                get('svprange'),
            )


def create_tables(cur, drop_existing=False):
    if drop_existing:
        cur.execute('DROP TABLE IF EXISTS onet_work_context')
        cur.execute('DROP TABLE IF EXISTS onet_job_zones')

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS onet_work_context (
            id BIGSERIAL PRIMARY KEY,
            onetsoc_code TEXT,
            element_id TEXT,
            element_name TEXT,
            scale_id TEXT,
            scale_name TEXT,
            data_value DOUBLE PRECISION,
            n INTEGER,
            standard_error DOUBLE PRECISION,
            lower_ci_bound DOUBLE PRECISION,
            upper_ci_bound DOUBLE PRECISION,
            recommend_suppress TEXT,
            not_relevant TEXT,
            date_value TEXT,
            domain_source TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS onet_job_zones (
            id BIGSERIAL PRIMARY KEY,
            onetsoc_code TEXT,
            title TEXT,
            job_zone INTEGER,
            education TEXT,
            related_experience TEXT,
            job_training TEXT,
            svp_range TEXT
        )
        """
    )


def truncate_target_tables(cur):
    cur.execute('TRUNCATE TABLE onet_work_context')
    cur.execute('TRUNCATE TABLE onet_job_zones')


def insert_batches(cur, sql, rows_iter):
    batch = []
    inserted = 0
    for row in rows_iter:
        batch.append(row)
        if len(batch) >= BATCH_SIZE:
            execute_values(cur, sql, batch)
            inserted += len(batch)
            batch = []
    if batch:
        execute_values(cur, sql, batch)
        inserted += len(batch)
    return inserted


def create_indexes(cur):
    cur.execute(
        'CREATE INDEX IF NOT EXISTS idx_onet_work_context_soc ON onet_work_context (onetsoc_code)'
    )
    cur.execute(
        'CREATE INDEX IF NOT EXISTS idx_onet_job_zones_soc ON onet_job_zones (onetsoc_code)'
    )


def print_missing_file_help():
    print('O*NET files not found. No changes made.')
    print('Download O*NET bulk files from: https://www.onetcenter.org/database.html')
    print('Place files in: data/onet/')
    print('Expected one Work Context file and one Job Zones file.')
    print('Accepted names:')
    for name in WORK_CONTEXT_CANDIDATES:
        print(f'  - {DATA_DIR / name}')
    for name in JOB_ZONES_CANDIDATES:
        print(f'  - {DATA_DIR / name}')


def main():
    parser = argparse.ArgumentParser(description='Load O*NET Work Context and Job Zones data')
    parser.add_argument('--drop-existing', action='store_true', help='Drop and recreate target tables before load')
    args = parser.parse_args()

    work_context_file = find_input_file(WORK_CONTEXT_CANDIDATES)
    job_zones_file = find_input_file(JOB_ZONES_CANDIDATES)

    if not work_context_file or not job_zones_file:
        print_missing_file_help()
        return

    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            create_tables(cur, drop_existing=args.drop_existing)
            truncate_target_tables(cur)

            wc_inserted = insert_batches(
                cur,
                """
                INSERT INTO onet_work_context (
                    onetsoc_code, element_id, element_name, scale_id, scale_name,
                    data_value, n, standard_error, lower_ci_bound, upper_ci_bound,
                    recommend_suppress, not_relevant, date_value, domain_source
                ) VALUES %s
                """,
                iter_work_context_rows(work_context_file),
            )

            jz_inserted = insert_batches(
                cur,
                """
                INSERT INTO onet_job_zones (
                    onetsoc_code, title, job_zone, education,
                    related_experience, job_training, svp_range
                ) VALUES %s
                """,
                iter_job_zone_rows(job_zones_file),
            )

            create_indexes(cur)

            cur.execute('SELECT COUNT(*) FROM onet_work_context')
            wc_count = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM onet_job_zones')
            jz_count = cur.fetchone()[0]

        conn.commit()

        print('O*NET load complete.')
        print(f'  Work Context source: {work_context_file}')
        print(f'  Job Zones source:    {job_zones_file}')
        print(f'  Inserted work context rows: {wc_inserted:,}')
        print(f'  Inserted job zones rows:    {jz_inserted:,}')
        print(f'  onet_work_context row count: {wc_count:,}')
        print(f'  onet_job_zones row count:    {jz_count:,}')

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
