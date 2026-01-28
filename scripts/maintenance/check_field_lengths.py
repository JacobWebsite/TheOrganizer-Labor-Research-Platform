import sqlite3

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\labor-data-project\data\nlrb\nlrb.db')
cursor = conn.cursor()

print("=== PARTICIPANT TABLE FIELD LENGTHS ===")
fields = ['case_number', 'participant', 'type', 'subtype', 'address', 'address_1', 'city', 'state', 'zip', 'phone_number']
for field in fields:
    cursor.execute(f"SELECT MAX(LENGTH({field})) FROM participant")
    max_len = cursor.fetchone()[0]
    print(f"{field:20}: max_len = {max_len}")

print("\n=== ALLEGATION TABLE ===")
cursor.execute("SELECT MAX(LENGTH(allegation)) FROM allegation")
print(f"allegation: max_len = {cursor.fetchone()[0]}")

print("\n=== ELECTION TABLES ===")
cursor.execute("SELECT MAX(LENGTH(option)) FROM tally")
print(f"tally.option: max_len = {cursor.fetchone()[0]}")

cursor.execute("SELECT MAX(LENGTH(union_to_certify)) FROM election_result")
print(f"election_result.union_to_certify: max_len = {cursor.fetchone()[0]}")

conn.close()
