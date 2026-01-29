import sqlite3

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\osha_enforcement.db')
cursor = conn.cursor()

# Check inspection table structure
cursor.execute("PRAGMA table_info(inspection)")
columns = cursor.fetchall()
print("inspection table columns:")
for col in columns:
    print(f"  {col[1]} ({col[2]})")

print("\n" + "="*60)

# Check violation table structure
cursor.execute("PRAGMA table_info(violation)")
columns = cursor.fetchall()
print("\nviolation table columns:")
for col in columns:
    print(f"  {col[1]} ({col[2]})")

print("\n" + "="*60)

# Check accident table structure  
cursor.execute("PRAGMA table_info(accident)")
columns = cursor.fetchall()
print("\naccident table columns:")
for col in columns:
    print(f"  {col[1]} ({col[2]})")

conn.close()
