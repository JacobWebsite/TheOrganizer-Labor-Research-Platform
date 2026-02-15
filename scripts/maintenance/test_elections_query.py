"""Test elections endpoint specifically"""
import psycopg2
from psycopg2.extras import RealDictCursor
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

conn = get_connection(cursor_factory=RealDictCursor)
cur = conn.cursor()

f_num = '137'
limit = 50
offset = 0

print("Testing elections query...")
try:
    cur.execute("""
from db_config import get_connection
        SELECT 
            e.election_id,
            e.case_number,
            e.election_date,
            e.election_type,
            er.total_ballots_counted,
            er.void_ballots,
            (SELECT SUM(t.votes) FROM nlrb_tallies t 
             WHERE t.election_id = e.election_id 
             AND (LOWER(t.option) LIKE '%%yes%%' OR t.option NOT LIKE '%%No%%')) as votes_for_union,
            (SELECT SUM(t.votes) FROM nlrb_tallies t 
             WHERE t.election_id = e.election_id 
             AND LOWER(t.option) LIKE '%%no%%') as votes_against,
            er.certified_union,
            emp.participant_name as employer_name,
            emp.city as employer_city,
            emp.state as employer_state
        FROM nlrb_union_xref x
        JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
        JOIN nlrb_cases c ON p.case_number = c.case_number
        JOIN nlrb_elections e ON c.case_number = e.case_number
        LEFT JOIN nlrb_election_results er ON e.election_id = er.election_id
        LEFT JOIN nlrb_participants emp ON c.case_number = emp.case_number AND emp.subtype = 'Employer'
        WHERE x.olms_f_num = %s::int
        ORDER BY e.election_date DESC
        LIMIT %s OFFSET %s
    """, [f_num, limit, offset])
    
    rows = cur.fetchall()
    print(f"Got {len(rows)} elections")
    for row in rows[:3]:
        print(f"  {row['election_date']}: {row['employer_name']} - for:{row['votes_for_union']} against:{row['votes_against']}")
        
except Exception as e:
    print(f"ERROR: {e}")

conn.close()
