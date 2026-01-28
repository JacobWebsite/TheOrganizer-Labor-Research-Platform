import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

# Check what affiliations exist
print("Distinct affiliations in OLMS:")
cur.execute("""
    SELECT DISTINCT aff_abbr, COUNT(*) as cnt
    FROM lm_data
    WHERE yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    GROUP BY aff_abbr
    ORDER BY cnt DESC
    LIMIT 30
""")
for r in cur.fetchall():
    print(f"  {r[0]:<20} {r[1]:>6} filings")

# Check Teamsters specifically
print("\n\nTeamsters search:")
cur.execute("""
    SELECT aff_abbr, union_name, members, ttl_receipts
    FROM lm_data
    WHERE (union_name ILIKE '%teamster%' OR union_name ILIKE '%brotherhood%chauffeur%')
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY members DESC NULLS LAST
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]:<12} {r[1][:50]:<52} {r[2] or 0:>10,}")

# Check UAW
print("\n\nUAW search:")
cur.execute("""
    SELECT aff_abbr, union_name, members, ttl_receipts
    FROM lm_data
    WHERE (union_name ILIKE '%auto%worker%' OR union_name ILIKE '%UAW%')
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY members DESC NULLS LAST
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]:<12} {r[1][:50]:<52} {r[2] or 0:>10,}")

# Check USW
print("\n\nUSW search:")
cur.execute("""
    SELECT aff_abbr, union_name, members, ttl_receipts
    FROM lm_data
    WHERE (union_name ILIKE '%steelworker%' OR union_name ILIKE '%USW%' OR union_name ILIKE '%steel%')
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY members DESC NULLS LAST
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]:<12} {r[1][:50]:<52} {r[2] or 0:>10,}")

# Check UFCW
print("\n\nUFCW search:")
cur.execute("""
    SELECT aff_abbr, union_name, members, ttl_receipts
    FROM lm_data
    WHERE (union_name ILIKE '%food%commercial%' OR union_name ILIKE '%UFCW%')
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY members DESC NULLS LAST
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]:<12} {r[1][:50]:<52} {r[2] or 0:>10,}")

conn.close()
