import os
import psycopg2

from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

print("=" * 60)
print("NLRB PARTICIPANT MATCHING STATUS")
print("=" * 60)

# Check participant types
cur.execute("""
    SELECT participant_type, COUNT(*) as cnt
    FROM nlrb_participants
    GROUP BY participant_type
    ORDER BY cnt DESC
    LIMIT 10
""")
print("\nParticipant types:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]:,}")

# Check employer matching rate
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_employer_id) as matched_to_f7,
        COUNT(matched_olms_fnum) as matched_to_olms
    FROM nlrb_participants
    WHERE participant_type = 'Employer'
""")
row = cur.fetchone()
print(f"\n--- EMPLOYERS ---")
print(f"Total NLRB employers: {row[0]:,}")
print(f"Matched to F7: {row[1]:,} ({100*row[1]/row[0]:.1f}%)" if row[0] > 0 else "No employers")
print(f"Matched to OLMS: {row[2]:,} ({100*row[2]/row[0]:.1f}%)" if row[0] > 0 else "")

# Check union matching rate
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as matched
    FROM nlrb_participants
    WHERE participant_type IN ('Labor Organization', 'Union', 'Petitioner - Labor Organization')
""")
row = cur.fetchone()
print(f"\n--- UNIONS ---")
print(f"Total NLRB unions: {row[0]:,}")
print(f"Matched to OLMS: {row[1]:,} ({100*row[1]/row[0]:.1f}%)" if row[0] > 0 else "No unions")

# Sample unmatched employers for fuzzy matching analysis
print("\n" + "=" * 60)
print("SAMPLE UNMATCHED NLRB EMPLOYERS (for fuzzy matching)")
print("=" * 60)
cur.execute("""
    SELECT DISTINCT participant_name, city, state
    FROM nlrb_participants
    WHERE participant_type = 'Employer'
    AND matched_employer_id IS NULL
    LIMIT 20
""")
for row in cur.fetchall():
    print(f"  {row[0]} | {row[1]}, {row[2]}")

conn.close()
