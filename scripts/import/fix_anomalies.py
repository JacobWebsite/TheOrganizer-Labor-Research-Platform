"""
Fix identified anomalies in membership deduplication
"""

import psycopg2
import os

from db_config import get_connection
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

conn = get_connection()
conn.autocommit = True
cursor = conn.cursor()

print("="*70)
print("FIXING ANOMALIES")
print("="*70)

# 1. Add data_quality_flag column
print("\n1. Adding data quality flag...")
cursor.execute("""
    ALTER TABLE union_organization_level 
    ADD COLUMN IF NOT EXISTS data_quality_flag VARCHAR(50)
""")

# 2. Flag suspicious member counts (members/assets ratio > 1000)
print("2. Flagging data quality issues...")

cursor.execute("""
    UPDATE union_organization_level ol
    SET 
        is_leaf_level = FALSE,
        data_quality_flag = 'suspicious_member_count',
        dedup_category = 'data_quality_exclude'
    FROM lm_data l
    WHERE ol.f_num = l.f_num
    AND l.yr_covered = 2024
    AND l.members > 100000
    AND l.ttl_assets > 0
    AND l.members::float / (l.ttl_assets / 1000.0) > 500
""")
print(f"   Flagged {cursor.rowcount} records with suspicious member/asset ratios")

# 3. Fix IATSE - only count actual locals, not the erroneous 513711
print("3. Fixing IATSE classification...")

# First, mark all IATSE as potential aggregates
cursor.execute("""
    UPDATE union_organization_level ol
    SET is_leaf_level = FALSE, dedup_category = 'iatse_exclude'
    FROM lm_data l
    WHERE ol.f_num = l.f_num
    AND l.yr_covered = 2024
    AND l.aff_abbr = 'IATSE'
    AND ol.is_leaf_level = TRUE
    AND l.members > 50000
""")
print(f"   Updated {cursor.rowcount} large IATSE records")

# 4. Fix PPF - SA units are aggregates
print("4. Fixing PPF (UA) classification...")

cursor.execute("""
    UPDATE union_organization_level ol
    SET is_leaf_level = FALSE, dedup_category = 'ppf_sa_aggregate'
    FROM lm_data l
    WHERE ol.f_num = l.f_num
    AND l.yr_covered = 2024
    AND l.aff_abbr = 'PPF'
    AND TRIM(l.desig_name) = 'SA'
""")
print(f"   Updated {cursor.rowcount} PPF SA records")

# 5. Fix IUOE - CONF are aggregates
print("5. Fixing IUOE classification...")

cursor.execute("""
    UPDATE union_organization_level ol
    SET is_leaf_level = FALSE, dedup_category = 'iuoe_conf_aggregate'
    FROM lm_data l
    WHERE ol.f_num = l.f_num
    AND l.yr_covered = 2024
    AND l.aff_abbr = 'IUOE'
    AND TRIM(l.desig_name) = 'CONF'
""")
print(f"   Updated {cursor.rowcount} IUOE CONF records")

# 6. Fix UNITHE - JB (Joint Boards) are aggregates
print("6. Fixing UNITE HERE classification...")

cursor.execute("""
    UPDATE union_organization_level ol
    SET is_leaf_level = FALSE, dedup_category = 'unithe_jb_aggregate'
    FROM lm_data l
    WHERE ol.f_num = l.f_num
    AND l.yr_covered = 2024
    AND l.aff_abbr = 'UNITHE'
    AND TRIM(l.desig_name) = 'JB'
""")
print(f"   Updated {cursor.rowcount} UNITE HERE JB records")

# 7. Verify results
print("\n" + "="*70)
print("VERIFICATION")
print("="*70)

cursor.execute("""
    SELECT 
        SUM(reported_members) as reported,
        SUM(counted_members) as counted
    FROM v_deduplicated_membership
""")
row = cursor.fetchone()
print(f"\nUpdated totals:")
print(f"  Reported: {row[0]:,}")
print(f"  Counted:  {row[1]:,}")
print(f"  BLS:      14,300,000")
print(f"  Diff:     {row[1] - 14300000:+,} ({(row[1]/14300000 - 1)*100:+.1f}%)")

# Check specific unions
print("\nKey union counts:")
cursor.execute("""
    SELECT aff_abbr, SUM(counted_members) as counted
    FROM v_deduplicated_membership
    WHERE aff_abbr IN ('IATSE', 'PPF', 'IUOE', 'UNITHE')
    GROUP BY aff_abbr
    ORDER BY aff_abbr
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]:,}")

# Data quality flags
print("\nData quality flags:")
cursor.execute("""
    SELECT data_quality_flag, COUNT(*), SUM(
        (SELECT COALESCE(members, 0) FROM lm_data WHERE lm_data.f_num = union_organization_level.f_num AND yr_covered = 2024 LIMIT 1)
    )
    FROM union_organization_level
    WHERE data_quality_flag IS NOT NULL
    GROUP BY data_quality_flag
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} records, {row[2] or 0:,} members excluded")

cursor.close()
conn.close()

print("\n" + "="*70)
