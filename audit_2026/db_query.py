"""
Database Query Helper for Audit
Usage: python audit_2026/db_query.py "SELECT count(*) FROM unions_master"
       python audit_2026/db_query.py --file audit_2026/queries.sql
"""
import sys
import psycopg2
import psycopg2.extras

def run_query(sql):
    conn = psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='Juniordog33!'
    )
    conn.set_session(readonly=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql)
        if cur.description:
            rows = cur.fetchall()
            if rows:
                # Print header
                cols = [d[0] for d in cur.description]
                print('\t'.join(cols))
                print('-' * 80)
                for row in rows:
                    print('\t'.join(str(row[c]) if row[c] is not None else 'NULL' for c in cols))
                print(f'\n({len(rows)} rows)')
            else:
                print('(0 rows)')
        else:
            print(f'Query executed. Rows affected: {cur.rowcount}')
    except Exception as e:
        print(f'ERROR: {e}')
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python audit_2026/db_query.py "SQL QUERY HERE"')
        print('       python audit_2026/db_query.py --file path/to/queries.sql')
        sys.exit(1)

    if sys.argv[1] == '--file':
        with open(sys.argv[2], 'r') as f:
            sql = f.read()
    else:
        sql = ' '.join(sys.argv[1:])

    run_query(sql)
