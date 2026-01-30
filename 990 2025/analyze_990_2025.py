#!/usr/bin/env python3
"""
IRS Form 990 2025 Batch Analysis Script

Analyzes all 990 XML files to extract:
1. Employers (nonprofit filers with revenue >= $200k)
2. Labor Organizations (501c5 filers, any size)
3. Grant Recipients (>$5k grants)
4. Contractors (>$100k payments)
5. Related Organizations

Output: employers_990_2025.json

Just run: python analyze_990_2025.py
"""

import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
import json
from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

INPUT_DIR = r"C:\Users\jakew\Downloads\labor-data-project\990 2025"
OUTPUT_FILE = r"C:\Users\jakew\Downloads\labor-data-project\990 2025\employers_990_2025.json"

# XML Namespace
IRS_NS = {'irs': 'http://www.irs.gov/efile'}

# Industry classification
EMPLOYER_NTEE_CODES = {
    'E': 'Healthcare', 'F': 'Mental Health', 'G': 'Medical Research', 'H': 'Medical Research',
    'B': 'Education',
    'I': 'Crime/Legal', 'J': 'Employment', 'K': 'Food/Nutrition', 'L': 'Housing/Shelter',
    'M': 'Public Safety', 'N': 'Recreation/Sports', 'O': 'Youth Development', 'P': 'Human Services',
    'A': 'Arts/Culture', 'C': 'Environment', 'D': 'Animal-Related',
}

EMPLOYER_KEYWORDS = [
    'hospital', 'medical center', 'health system', 'healthcare',
    'university', 'college', 'school district', 'academy',
    'nursing home', 'assisted living', 'rehabilitation',
    'social services', 'community center', 'ymca', 'ywca',
    'museum', 'theater', 'theatre', 'orchestra', 'symphony',
    'transit', 'transportation', 'airport', 'housing authority',
]


# ============================================================================
# DATA CLASS
# ============================================================================

@dataclass
class Employer990:
    ein: Optional[str] = None
    name: str = ""
    name_line2: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    source_type: str = ""
    source_ein: Optional[str] = None
    source_name: Optional[str] = None
    total_revenue: Optional[float] = None
    total_expenses: Optional[float] = None
    salaries_benefits: Optional[float] = None
    employee_count: Optional[int] = None
    grant_amount: Optional[float] = None
    contractor_payment: Optional[float] = None
    exempt_status: Optional[str] = None
    industry_category: Optional[str] = None
    tax_year: Optional[int] = None
    source_file: Optional[str] = None
    membership_dues: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


# ============================================================================
# HELPERS
# ============================================================================

def safe_find_text(element, path, ns=None):
    if ns is None:
        ns = {}
    found = element.find(path, ns)
    if found is not None and found.text:
        return found.text.strip()
    if ns:
        found = element.find(path.replace('irs:', ''), {})
        if found is not None and found.text:
            return found.text.strip()
    return None

def safe_find_float(element, path, ns=None):
    text = safe_find_text(element, path, ns)
    if text:
        try:
            return float(text.replace(',', ''))
        except ValueError:
            return None
    return None

def safe_find_int(element, path, ns=None):
    val = safe_find_float(element, path, ns)
    return int(val) if val is not None else None

def classify_industry(name, purpose=None, ntee=None):
    if ntee and len(ntee) > 0:
        first_char = ntee[0].upper()
        if first_char in EMPLOYER_NTEE_CODES:
            return EMPLOYER_NTEE_CODES[first_char]
    
    text = f"{name} {purpose or ''}".lower()
    
    if any(kw in text for kw in ['hospital', 'medical center', 'health system', 'clinic']):
        return 'Healthcare'
    if any(kw in text for kw in ['university', 'college', 'school', 'academy', 'education']):
        return 'Education'
    if any(kw in text for kw in ['nursing home', 'assisted living', 'senior', 'elder']):
        return 'Senior Care'
    if any(kw in text for kw in ['social service', 'community', 'human service']):
        return 'Social Services'
    if any(kw in text for kw in ['theater', 'theatre', 'museum', 'orchestra', 'symphony']):
        return 'Arts/Entertainment'
    if any(kw in text for kw in ['transit', 'transportation', 'airport']):
        return 'Transportation'
    if any(kw in text for kw in ['housing', 'shelter']):
        return 'Housing'
    return None

def is_significant_employer(salaries=None, revenue=None, employees=None, name="", exempt_status=None):
    # 501(c)(5) = labor organizations - always include
    if exempt_status == '501c5':
        return True
    # Minimum $200k revenue for employers
    if not revenue or revenue < 200000:
        return False
    return True


# ============================================================================
# EXTRACTION FUNCTIONS
# ============================================================================

def extract_filer(root, ns, filename):
    ein = safe_find_text(root, './/irs:EIN', ns) or safe_find_text(root, './/EIN', {})
    name = safe_find_text(root, './/irs:BusinessName/irs:BusinessNameLine1Txt', ns) or \
           safe_find_text(root, './/BusinessName/BusinessNameLine1Txt', {})
    
    if not name:
        return None
    
    # Financials
    salaries = safe_find_float(root, './/irs:SalariesOtherCompEmplBnftAmt', ns) or \
               safe_find_float(root, './/irs:CYSalariesCompEmpBnftPaidAmt', ns) or \
               safe_find_float(root, './/SalariesOtherCompEmplBnftAmt', {})
    
    revenue = safe_find_float(root, './/irs:TotalRevenueAmt', ns) or \
              safe_find_float(root, './/irs:CYTotalRevenueAmt', ns) or \
              safe_find_float(root, './/TotalRevenueAmt', {})
    
    expenses = safe_find_float(root, './/irs:TotalExpensesAmt', ns) or \
               safe_find_float(root, './/TotalExpensesAmt', {})
    
    employees = safe_find_int(root, './/irs:TotalEmployeeCnt', ns) or \
                safe_find_int(root, './/TotalEmployeeCnt', {})
    
    membership_dues = safe_find_float(root, './/irs:MembershipDuesAmt', ns) or \
                      safe_find_float(root, './/MembershipDuesAmt', {})
    
    # Exempt status
    exempt_status = None
    if root.find('.//irs:Organization501c3Ind', ns) is not None or \
       root.find('.//Organization501c3Ind', {}) is not None:
        exempt_status = '501c3'
    
    c_type_elem = root.find('.//irs:Organization501cInd', ns)
    if c_type_elem is None:
        c_type_elem = root.find('.//Organization501cInd', {})
    if c_type_elem is not None:
        c_type = c_type_elem.get('organization501cTypeTxt')
        if c_type:
            exempt_status = f'501c{c_type}'
    
    # Filter check
    if not is_significant_employer(salaries, revenue, employees, name, exempt_status):
        return None
    
    emp = Employer990(
        ein=ein,
        name=name,
        name_line2=safe_find_text(root, './/irs:BusinessName/irs:BusinessNameLine2Txt', ns),
        source_type='filer',
        source_file=filename,
        salaries_benefits=salaries,
        total_revenue=revenue,
        total_expenses=expenses,
        employee_count=employees,
        exempt_status=exempt_status,
        membership_dues=membership_dues
    )
    
    # Address
    emp.address_line1 = safe_find_text(root, './/irs:Filer/irs:USAddress/irs:AddressLine1Txt', ns) or \
                        safe_find_text(root, './/Filer/USAddress/AddressLine1Txt', {})
    emp.city = safe_find_text(root, './/irs:Filer/irs:USAddress/irs:CityNm', ns) or \
               safe_find_text(root, './/Filer/USAddress/CityNm', {})
    emp.state = safe_find_text(root, './/irs:Filer/irs:USAddress/irs:StateAbbreviationCd', ns) or \
                safe_find_text(root, './/Filer/USAddress/StateAbbreviationCd', {})
    emp.zip_code = safe_find_text(root, './/irs:Filer/irs:USAddress/irs:ZIPCd', ns) or \
                   safe_find_text(root, './/Filer/USAddress/ZIPCd', {})
    
    # Tax year
    tax_year = safe_find_text(root, './/irs:TaxYr', ns) or safe_find_text(root, './/TaxYr', {})
    emp.tax_year = int(tax_year) if tax_year else None
    
    # Industry
    purpose = safe_find_text(root, './/irs:ActivityOrMissionDesc', ns) or \
              safe_find_text(root, './/irs:PrimaryExemptPurposeTxt', ns) or \
              safe_find_text(root, './/PrimaryExemptPurposeTxt', {})
    emp.industry_category = classify_industry(name, purpose)
    
    if exempt_status == '501c5':
        emp.industry_category = 'Labor Organization'
    
    return emp


def extract_grants(root, ns, source_ein, source_name, filename):
    employers = []
    
    grant_groups = root.findall('.//irs:GrantOrContributionPdDurYrGrp', ns) + \
                   root.findall('.//GrantOrContributionPdDurYrGrp', {}) + \
                   root.findall('.//irs:RecipientTable', ns) + \
                   root.findall('.//RecipientTable', {})
    
    for gg in grant_groups:
        name = safe_find_text(gg, './/irs:RecipientBusinessName/irs:BusinessNameLine1Txt', ns) or \
               safe_find_text(gg, './/RecipientBusinessName/BusinessNameLine1Txt', {}) or \
               safe_find_text(gg, './/irs:RecipientNameBusiness/irs:BusinessNameLine1', ns)
        
        if not name:
            continue
        if len(name.split()) <= 2 and ',' in name:
            continue
        
        amount = safe_find_float(gg, './/irs:Amt', ns) or \
                 safe_find_float(gg, './/Amt', {}) or \
                 safe_find_float(gg, './/irs:CashGrantAmt', ns)
        
        if amount and amount < 5000:
            continue
        
        emp = Employer990(
            name=name,
            source_type='grant_recipient',
            source_ein=source_ein,
            source_name=source_name,
            source_file=filename,
            grant_amount=amount,
            ein=safe_find_text(gg, './/irs:RecipientEIN', ns),
            city=safe_find_text(gg, './/irs:RecipientUSAddress/irs:CityNm', ns) or \
                 safe_find_text(gg, './/RecipientUSAddress/CityNm', {}),
            state=safe_find_text(gg, './/irs:RecipientUSAddress/irs:StateAbbreviationCd', ns) or \
                  safe_find_text(gg, './/RecipientUSAddress/StateAbbreviationCd', {})
        )
        
        purpose = safe_find_text(gg, './/irs:GrantOrContributionPurposeTxt', ns) or \
                  safe_find_text(gg, './/GrantOrContributionPurposeTxt', {})
        emp.industry_category = classify_industry(name, purpose)
        
        employers.append(emp)
    
    return employers


def extract_contractors(root, ns, source_ein, source_name, filename):
    employers = []
    
    contractor_groups = root.findall('.//irs:ContractorCompensationGrp', ns) + \
                        root.findall('.//ContractorCompensationGrp', {}) + \
                        root.findall('.//irs:IndependentContractorsGrp', ns)
    
    for cg in contractor_groups:
        name = safe_find_text(cg, './/irs:ContractorName/irs:BusinessNameLine1Txt', ns) or \
               safe_find_text(cg, './/ContractorName/BusinessNameLine1Txt', {}) or \
               safe_find_text(cg, './/irs:BusinessName/irs:BusinessNameLine1Txt', ns)
        
        if not name:
            continue
        
        amount = safe_find_float(cg, './/irs:CompensationAmt', ns) or \
                 safe_find_float(cg, './/CompensationAmt', {})
        
        if not amount or amount < 100000:
            continue
        
        emp = Employer990(
            name=name,
            source_type='contractor',
            source_ein=source_ein,
            source_name=source_name,
            source_file=filename,
            contractor_payment=amount,
            city=safe_find_text(cg, './/irs:ContractorAddress/irs:USAddress/irs:CityNm', ns),
            state=safe_find_text(cg, './/irs:ContractorAddress/irs:USAddress/irs:StateAbbreviationCd', ns)
        )
        
        services = safe_find_text(cg, './/irs:ServicesDesc', ns)
        emp.industry_category = classify_industry(name, services)
        
        employers.append(emp)
    
    return employers


def extract_related_orgs(root, ns, source_ein, source_name, filename):
    employers = []
    
    related_groups = root.findall('.//irs:IdRelatedTaxExemptOrgGrp', ns) + \
                     root.findall('.//IdRelatedTaxExemptOrgGrp', {}) + \
                     root.findall('.//irs:IdRelatedOrgTxblPartnershipGrp', ns) + \
                     root.findall('.//irs:IdRelatedOrgTxblCorpTrGrp', ns)
    
    for rg in related_groups:
        name = safe_find_text(rg, './/irs:BusinessName/irs:BusinessNameLine1Txt', ns) or \
               safe_find_text(rg, './/BusinessName/BusinessNameLine1Txt', {}) or \
               safe_find_text(rg, './/irs:RelatedOrganizationName/irs:BusinessNameLine1Txt', ns)
        
        if not name:
            continue
        
        emp = Employer990(
            name=name,
            source_type='related_org',
            source_ein=source_ein,
            source_name=source_name,
            source_file=filename,
            ein=safe_find_text(rg, './/irs:EIN', ns) or safe_find_text(rg, './/EIN', {}),
            city=safe_find_text(rg, './/irs:USAddress/irs:CityNm', ns),
            state=safe_find_text(rg, './/irs:USAddress/irs:StateAbbreviationCd', ns)
        )
        
        employers.append(emp)
    
    return employers


def process_file(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = IRS_NS if root.tag.startswith('{') else {}
        filename = os.path.basename(file_path)
        
        source_ein = safe_find_text(root, './/irs:EIN', ns) or safe_find_text(root, './/EIN', {})
        source_name = safe_find_text(root, './/irs:BusinessName/irs:BusinessNameLine1Txt', ns) or \
                      safe_find_text(root, './/BusinessName/BusinessNameLine1Txt', {})
        
        filer = extract_filer(root, ns, filename)
        related = []
        related.extend(extract_grants(root, ns, source_ein, source_name, filename))
        related.extend(extract_contractors(root, ns, source_ein, source_name, filename))
        related.extend(extract_related_orgs(root, ns, source_ein, source_name, filename))
        
        return filer, related
    except Exception as e:
        return None, []


# ============================================================================
# MAIN
# ============================================================================

def main(limit=None, start=0):
    print("=" * 60)
    print("IRS Form 990 2025 Batch Analysis")
    print("=" * 60)
    print(f"Input:  {INPUT_DIR}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Filter: Revenue >= $200k OR 501(c)(5)")
    if limit:
        print(f"Limit:  {limit:,} files (starting from {start:,})")
    print("=" * 60)
    
    results = {
        'summary': {
            'total_files': 0,
            'files_processed': 0,
            'filer_employers': 0,
            'labor_orgs_501c5': 0,
            'grant_recipients': 0,
            'contractors': 0,
            'related_orgs': 0,
            'by_industry': defaultdict(int),
            'by_state': defaultdict(int),
            'by_exempt_status': defaultdict(int),
            'processing_time': None
        },
        'employers': [],
        'labor_organizations': []
    }
    
    start_time = datetime.now()
    
    # Find all XML files recursively
    xml_files = []
    for root_dir, dirs, files in os.walk(INPUT_DIR):
        for f in files:
            if f.endswith('.xml'):
                xml_files.append(os.path.join(root_dir, f))
    
    results['summary']['total_files'] = len(xml_files)
    print(f"\nFound {len(xml_files)} XML files")

    # Apply start/limit
    if start > 0 or limit:
        end = start + limit if limit else len(xml_files)
        xml_files = xml_files[start:end]
        print(f"Processing files {start:,} to {start + len(xml_files):,}")

    print("Processing...\n")

    seen = set()
    
    for i, file_path in enumerate(xml_files):
        if i > 0 and i % 2000 == 0:
            print(f"  {i:,}/{len(xml_files):,} files processed...")
        
        filer, related = process_file(file_path)
        results['summary']['files_processed'] += 1
        
        if filer:
            key = (filer.name.lower(), filer.city, filer.state)
            if key not in seen:
                seen.add(key)
                emp_dict = filer.to_dict()
                
                if filer.exempt_status == '501c5':
                    results['labor_organizations'].append(emp_dict)
                    results['summary']['labor_orgs_501c5'] += 1
                else:
                    results['employers'].append(emp_dict)
                    results['summary']['filer_employers'] += 1
                
                if filer.industry_category:
                    results['summary']['by_industry'][filer.industry_category] += 1
                if filer.state:
                    results['summary']['by_state'][filer.state] += 1
                if filer.exempt_status:
                    results['summary']['by_exempt_status'][filer.exempt_status] += 1
        
        for emp in related:
            key = (emp.name.lower(), emp.city, emp.state)
            if key not in seen:
                seen.add(key)
                results['employers'].append(emp.to_dict())
                
                if emp.source_type == 'grant_recipient':
                    results['summary']['grant_recipients'] += 1
                elif emp.source_type == 'contractor':
                    results['summary']['contractors'] += 1
                elif emp.source_type == 'related_org':
                    results['summary']['related_orgs'] += 1
                
                if emp.industry_category:
                    results['summary']['by_industry'][emp.industry_category] += 1
                if emp.state:
                    results['summary']['by_state'][emp.state] += 1
    
    # Finalize
    results['summary']['processing_time'] = str(datetime.now() - start_time)
    results['summary']['total_employers'] = len(results['employers'])
    results['summary']['total_labor_orgs'] = len(results['labor_organizations'])
    results['summary']['by_industry'] = dict(results['summary']['by_industry'])
    results['summary']['by_state'] = dict(results['summary']['by_state'])
    results['summary']['by_exempt_status'] = dict(results['summary']['by_exempt_status'])
    
    # Write
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Report
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Files processed: {results['summary']['files_processed']:,}")
    print(f"Processing time: {results['summary']['processing_time']}")
    
    print(f"\n--- EMPLOYERS (Revenue >= $200k) ---")
    print(f"Total unique employers: {results['summary']['total_employers']:,}")
    print(f"  Filer employers:   {results['summary']['filer_employers']:,}")
    print(f"  Grant recipients:  {results['summary']['grant_recipients']:,}")
    print(f"  Contractors:       {results['summary']['contractors']:,}")
    print(f"  Related orgs:      {results['summary']['related_orgs']:,}")
    
    print(f"\n--- LABOR ORGANIZATIONS (501c5) ---")
    print(f"Total 501(c)(5) orgs: {results['summary']['labor_orgs_501c5']:,}")
    
    print(f"\n--- TOP INDUSTRIES ---")
    for ind, count in sorted(results['summary']['by_industry'].items(), key=lambda x: -x[1])[:10]:
        print(f"  {ind}: {count:,}")
    
    print(f"\n--- TOP STATES ---")
    for st, count in sorted(results['summary']['by_state'].items(), key=lambda x: -x[1])[:10]:
        print(f"  {st}: {count:,}")
    
    print(f"\n--- EXEMPT STATUS ---")
    for status, count in sorted(results['summary']['by_exempt_status'].items(), key=lambda x: -x[1]):
        print(f"  {status}: {count:,}")
    
    print(f"\n" + "=" * 60)
    print(f"Results saved to: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Limit files to process')
    parser.add_argument('--start', type=int, default=0, help='Start from file index')
    args = parser.parse_args()
    main(limit=args.limit, start=args.start)
