"""Final SAM.gov assessment - usability for labor project."""
import zipfile
import re
from collections import Counter

SAM_ZIP = r"C:\Users\jakew\Downloads\SAM_PUBLIC_UTF-8_MONTHLY_V2_20260201.zip"

print("=== SAM.gov Public V2 Assessment ===")
print()

with zipfile.ZipFile(SAM_ZIP, 'r') as zf:
    fname = zf.infolist()[0].filename
    with zf.open(fname) as f:
        f.readline()  # skip BOF

        total = 0
        active = 0
        has_naics = 0
        has_name = 0
        has_address = 0
        has_cage = 0
        usa_only = 0
        states = Counter()
        naics_2 = Counter()
        entity_types = Counter()
        multi_naics = 0

        for raw_line in f:
            line = raw_line.decode('utf-8', errors='replace').strip()
            if line.startswith('EOF') or line.startswith('!end'):
                continue
            fields = line.split('|')
            if len(fields) < 35:
                continue

            total += 1

            # Status
            status = fields[5].strip() if len(fields) > 5 else ''
            if status == 'A':
                active += 1

            # Country filter
            country = fields[21].strip() if len(fields) > 21 else ''
            if country == 'USA':
                usa_only += 1

            # State
            state = fields[18].strip() if len(fields) > 18 else ''
            if state and country == 'USA':
                states[state] += 1

            # Name
            name = fields[11].strip() if len(fields) > 11 else ''
            if name:
                has_name += 1

            # Address
            addr = fields[15].strip() if len(fields) > 15 else ''
            city = fields[17].strip() if len(fields) > 17 else ''
            if addr and city:
                has_address += 1

            # CAGE
            cage = fields[3].strip() if len(fields) > 3 else ''
            if cage:
                has_cage += 1

            # NAICS
            primary_naics = fields[32].strip() if len(fields) > 32 else ''
            if primary_naics:
                has_naics += 1
                if len(primary_naics) >= 2:
                    naics_2[primary_naics[:2]] += 1

            # Multiple NAICS
            all_naics = fields[34].strip() if len(fields) > 34 else ''
            if '~' in all_naics:
                multi_naics += 1

            # Entity type
            etype = fields[27].strip() if len(fields) > 27 else ''
            if etype:
                entity_types[etype] += 1

            if total % 100000 == 0:
                print(f"  Processed {total:,}...")

        print()
        print(f"=== TOTALS ===")
        print(f"Total records:      {total:,}")
        print(f"Active (status=A):  {active:,} ({active/total*100:.1f}%)")
        print(f"USA entities:       {usa_only:,} ({usa_only/total*100:.1f}%)")
        print(f"Has business name:  {has_name:,} ({has_name/total*100:.1f}%)")
        print(f"Has address+city:   {has_address:,} ({has_address/total*100:.1f}%)")
        print(f"Has CAGE code:      {has_cage:,} ({has_cage/total*100:.1f}%)")
        print(f"Has primary NAICS:  {has_naics:,} ({has_naics/total*100:.1f}%)")
        print(f"Has multiple NAICS: {multi_naics:,} ({multi_naics/total*100:.1f}%)")
        print()

        # Active USA with name + address
        print(f"=== MATCHABLE RECORDS (Active + USA + Name + Address) ===")
        # Re-scan would be needed, estimate from ratios
        est_matchable = int(active * (usa_only/total) * (has_address/total))
        print(f"Estimated matchable: ~{est_matchable:,}")
        print()

        print(f"=== TOP 15 STATES ===")
        for state, count in states.most_common(15):
            print(f"  {state}: {count:,}")
        print()

        print(f"=== TOP 15 NAICS (2-digit) ===")
        naics_labels = {
            '11':'Agriculture', '21':'Mining', '22':'Utilities', '23':'Construction',
            '31':'Manufacturing', '32':'Manufacturing', '33':'Manufacturing',
            '42':'Wholesale', '44':'Retail', '45':'Retail',
            '48':'Transport', '49':'Warehousing', '51':'Information',
            '52':'Finance', '53':'Real Estate', '54':'Professional/Tech',
            '55':'Management', '56':'Admin/Support', '61':'Education',
            '62':'Healthcare', '71':'Arts/Entertainment', '72':'Hospitality',
            '81':'Other Services', '92':'Government',
            '23':'Construction', '33':'Manufacturing'
        }
        for code, count in naics_2.most_common(15):
            label = naics_labels.get(code, '?')
            print(f"  {code} ({label}): {count:,}")
        print()

        print(f"=== ENTITY STRUCTURE CODES ===")
        # SAM codes: 2L=LLC, 2K=Partnership, 2J=S-Corp, 2A=Government, 8H=Nonprofit, etc.
        struct_labels = {
            '2L':'Corporate/LLC', '2K':'Partnership/LLP', '2J':'S-Corporation',
            '2A':'Government', '8H':'Nonprofit/501c', 'ZZ':'Other',
            '2X':'C-Corporation', 'CY':'Sole Proprietorship',
        }
        for code, count in entity_types.most_common(20):
            label = struct_labels.get(code, '?')
            print(f"  {code} ({label}): {count:,}")
        print()

        print("=== VERDICT ===")
        print("NO EIN in public SAM extract (tax-sensitive data)")
        print("YES: UEI, CAGE, Legal Name, DBA, Address, NAICS (6-digit!), Entity Type")
        print("MATCH STRATEGY: Name+State+NAICS or Name+Address")
        print(f"MATCHING UNIVERSE: ~{usa_only:,} USA entities")
