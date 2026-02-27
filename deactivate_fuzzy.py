from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# Count active fuzzy matches below 0.85
query_count = """
SELECT COUNT(*) 
FROM unified_match_log 
WHERE status = 'active' 
  AND (evidence::json->>'name_similarity') IS NOT NULL
  AND (evidence::json->>'name_similarity')::float < 0.85
"""

cur.execute(query_count)
count = cur.fetchone()[0]
print(f"Found {count} active fuzzy matches with similarity < 0.85.")

if count > 0:
    print("Deactivating matches...")
    update_query = """
    UPDATE unified_match_log 
    SET status = 'inactive', 
        updated_at = NOW(),
        notes = COALESCE(notes, '') || ' | Deactivated by 2_26 roadmap cleanup: similarity < 0.85'
    WHERE status = 'active' 
      AND (evidence::json->>'name_similarity') IS NOT NULL
      AND (evidence::json->>'name_similarity')::float < 0.85
    """
    cur.execute(update_query)
    updated = cur.rowcount
    print(f"Successfully deactivated {updated} matches.")
    conn.commit()
else:
    print("No matches to deactivate.")

conn.close()
