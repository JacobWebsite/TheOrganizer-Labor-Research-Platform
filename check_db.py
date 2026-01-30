import psycopg2
import sys

try:
    conn = psycopg2.connect(
        dbname="olms_multiyear",
        user="postgres",
        password="Juniordog33!",
        host="localhost"
    )
    cur = conn.cursor()
    
    # Check current public sector status
    cur.execute("""
        SELECT state, COUNT(*) as records, SUM(num_employees) as workers 
        FROM manual_employers 
        WHERE sector = 'PUBLIC' 
        GROUP BY state 
        ORDER BY SUM(num_employees) DESC;
    """)
    
    results = cur.fetchall()
    print("Current PUBLIC sector records:")
    print("State | Records | Workers")
    print("-" * 30)
    for row in results:
        print(f"{row[0]} | {row[1]} | {row[2]}")
    
    # Get total
    cur.execute("""
        SELECT COUNT(*), SUM(num_employees) 
        FROM manual_employers 
        WHERE sector = 'PUBLIC';
    """)
    total = cur.fetchone()
    print("-" * 30)
    print(f"TOTAL: {total[0]} records, {total[1]} workers")
    
    cur.close()
    conn.close()

except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
