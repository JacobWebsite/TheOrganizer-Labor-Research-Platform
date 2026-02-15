import os
from db_config import get_connection
"""
OSHA Phase 6.4: Create Normalized Names
Adds normalized employer names to osha_establishments for better matching
"""

import psycopg2
import re
from datetime import datetime

PG_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', '')
}
BATCH_SIZE = 50000

def normalize_name(name):
    """Normalize employer name for matching"""
    if not name:
        return None
    
    # Lowercase
    name = name.lower().strip()
    
    # Remove common suffixes
    suffixes = [
        r'\b(inc|incorporated|corp|corporation|llc|llp|lp|ltd|limited|co|company|companies)\b\.?',
        r'\b(pllc|pc|pa|plc|sa|gmbh|ag|nv|bv)\b\.?',
        r'\b(the|a|an)\b',
        r'\bd/?b/?a\b',  # DBA
    ]
    for suffix in suffixes:
        name = re.sub(suffix, '', name, flags=re.IGNORECASE)
    
    # Remove punctuation except spaces
    name = re.sub(r'[^\w\s]', ' ', name)
    
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name if name else None

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.4: Create Normalized OSHA Names")
    print("=" * 60)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get total count
    cursor.execute("SELECT COUNT(*) FROM osha_establishments WHERE estab_name_normalized IS NULL")
    total = cursor.fetchone()[0]
    print(f"Establishments to normalize: {total:,}")
    
    # Process in batches
    processed = 0
    
    while processed < total:
        # Fetch batch
        cursor.execute("""
            SELECT establishment_id, estab_name 
            FROM osha_establishments 
            WHERE estab_name_normalized IS NULL
            LIMIT %s
        """, (BATCH_SIZE,))
        
        rows = cursor.fetchall()
        if not rows:
            break
        
        # Build update values
        updates = []
        for est_id, name in rows:
            normalized = normalize_name(name)
            updates.append((normalized, est_id))
        
        # Batch update
        cursor.executemany("""
            UPDATE osha_establishments 
            SET estab_name_normalized = %s 
            WHERE establishment_id = %s
        """, updates)
        conn.commit()
        
        processed += len(rows)
        pct = (processed / total) * 100
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Processed: {processed:>10,} / {total:,} ({pct:5.1f}%)")
    
    # Create index for normalized names
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Creating trigram index on normalized names...")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_osha_est_name_norm_trgm 
        ON osha_establishments USING gin (estab_name_normalized gin_trgm_ops)
    """)
    conn.commit()
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM osha_establishments WHERE estab_name_normalized IS NOT NULL")
    normalized_count = cursor.fetchone()[0]
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Phase 6.4 COMPLETE")
    print(f"Establishments with normalized names: {normalized_count:,}")
    
    # Sample
    cursor.execute("""
        SELECT estab_name, estab_name_normalized 
        FROM osha_establishments 
        WHERE estab_name_normalized IS NOT NULL
        LIMIT 5
    """)
    print("\nSample normalizations:")
    for row in cursor.fetchall():
        print(f"  {row[0][:50]:50} -> {row[1]}")
    
    conn.close()

if __name__ == '__main__':
    main()
