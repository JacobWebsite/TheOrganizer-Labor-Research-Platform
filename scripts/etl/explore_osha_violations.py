import sqlite3

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\osha_enforcement.db')
cursor = conn.cursor()

# Get violation table schema
cursor.execute("PRAGMA table_info(violation)")
columns = cursor.fetchall()
print('=== violation table schema ===')
for col in columns:
    print(f'  {col[1]:30} {col[2]:15}')

print('\n=== inspection table schema ===')
cursor.execute("PRAGMA table_info(inspection)")
columns = cursor.fetchall()
for col in columns:
    print(f'  {col[1]:30} {col[2]:15}')

# Count violations from 2012+
print('\nCounting violations from 2012+...')
cursor.execute('''
    SELECT COUNT(*) 
    FROM violation v
    JOIN inspection i ON v.activity_nr = i.activity_nr
    WHERE i.open_date >= '2012-01-01'
''')
count = cursor.fetchone()[0]
print(f'Violations from 2012+: {count:,}')

# Sample a few records
cursor.execute('''
    SELECT v.activity_nr, v.citation_id, v.viol_type, v.issuance_date, 
           v.current_penalty, v.initial_penalty, v.standard
    FROM violation v
    JOIN inspection i ON v.activity_nr = i.activity_nr
    WHERE i.open_date >= '2012-01-01'
    LIMIT 5
''')
print('\nSample violations:')
for row in cursor.fetchall():
    print(f'  {row}')

conn.close()
