import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# Batch 1: Largest non-retiree profiles with 0 employers
profile_ids = [14, 61, 46, 199, 267, 220, 134, 166, 234, 243, 183, 4, 8, 50, 11, 114, 155, 215, 294, 65, 48, 12, 13, 47, 111, 99, 232, 246, 289, 43, 82, 80]

for pid in profile_ids:
    cur.execute("""
        SELECT id, union_name, state, local_number,
               LEFT(raw_text, 5000), LEFT(raw_text_about, 5000)
        FROM web_union_profiles WHERE id = %s
    """, (pid,))
    row = cur.fetchone()
    if not row:
        continue

    pid_val, name, state, local_num, homepage, about = row
    print(f'\n{"="*60}')
    print(f'[{pid_val}] {name} ({state}) Local {local_num}')
    print(f'{"="*60}')

    if about and len(about.strip()) > 300:
        print(f'--- ABOUT PAGE ---')
        # Replace problematic characters
        clean_about = about[:4000].replace('\ue61e', '').replace('\ue61d', '')
        print(clean_about)

    if homepage and len(homepage.strip()) > 300:
        print(f'\n--- HOMEPAGE (first 3000) ---')
        clean_home = homepage[:3000].replace('\ue61e', '').replace('\ue61d', '')
        print(clean_home)

    print(f'\n--- END [{pid_val}] ---')

conn.close()
