from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute('SELECT COUNT(*) FROM occupation_similarity')
print(f'Occupation similarity pairs: {cur.fetchone()[0]:,}')

cur.execute("""
    SELECT occupation_code_1, occupation_code_2, similarity_score
    FROM occupation_similarity
    ORDER BY similarity_score DESC
    LIMIT 5
""")

print('\nTop 5 most similar occupation pairs:')
for r in cur.fetchall():
    print(f'  {r[0]} <-> {r[1]}: {r[2]:.4f}')

conn.close()
