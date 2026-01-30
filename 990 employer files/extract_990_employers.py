#!/usr/bin/env python3
"""
IRS Form 990 Employer Extraction Script

Primary goal: Extract employer entities from 990 data for labor relations platform

Filtering:
- Employers: Total revenue >= $200,000
- Labor Organizations: 501(c)(5) status (any size)

Employer sources:
1. 990 filers with employees (nonprofits ARE employers)
2. Grant recipients (from Schedule I / 990PF)
3. Contractors paid >$100k (from Schedule J)
4. Related organizations (from Schedule R)

Usage:
    python extract_990_employers.py --input-dir /path/to/990_xml --output employers.json
"""

import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
import json
from datetime import datetime

# XML Namespace
IRS_NS = {'irs': 'http://www.irs.gov/efile'}


# ============================================================================
# NTEE CODES - Industry Classification
# ============================================================================

# NTEE codes that indicate significant employers
EMPLOYER_NTEE_CODES = {
    # Healthcare - major union targets (SEIU, AFSCME, nurses)
    'E': 'Healthcare',
    'F': 'Mental Health',
    'G': 'Disease/Medical Research',
    'H': 'Medical Research',
    
    # Education - AFT, NEA targets
    'B': 'Education',
    
    # Human Services - AFSCME, SEIU targets
    'I': 'Crime/Legal',
    'J': 'Employment',
    'K': 'Food/Nutrition',
    'L': 'Housing/Shelter',
    'M': 'Public Safety',
    'N': 'Recreation/Sports',
    'O': 'Youth Development',
    'P': 'Human Services',
    
    # Arts/Culture - IATSE, stagehands
    'A': 'Arts/Culture',
    
    # Environment - some organizing
    'C': 'Environment',
    'D': 'Animal-Related',
}

# Keywords suggesting significant employer
EMPLOYER_KEYWORDS = [
    'hospital', 'medical center', 'health system', 'healthcare',
    'university', 'college', 'school district', 'academy',
    'nursing home', 'assisted living', 'rehabilitation',
    'social services', 'community center', 'ymca', 'ywca',
    'museum', 'theater', 'theatre', 'orchestra', 'symphony',
    'transit', 'transportation', 'airport',
    'housing authority', 'public housing',
]


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Employer990:
    """Employer entity extracted from 990 data"""
    # Identity
    ein: Optional[str] = None
    name: str = ""
    name_line2: Optional[str] = None
    
    # Location
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    
    # Source info
    source_type: str = ""  # 'filer', 'grant_recipient', 'contractor', 'related_org'
    source_ein: Optional[str] = None
    source_name: Optional[str] = None
    
    # Financial indicators
    total_revenue: Optional[float] = None
    total_expenses: Optional[float] = None
    salaries_benefits: Optional[float] = None  # Key indicator of employer size
    employee_count: Optional[int] = None
    grant_amount: Optional[float] = None  # If from grant recipient
    contractor_payment: Optional[float] = None  # If from contractor
    
    # Classification
    exempt_status: Optional[str] = None
    ntee_code: Optional[str] = None
    industry_category: Optional[str] = None
    
    # Metadata
    tax_year: Optional[int] = None
    source_file: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


# ============================================================================
# PARSING HELPERS
# ============================================================================

def safe_find_text(element: ET.Element, path: str, ns: dict = None) -> Optional[str]:
    """Safely find element text"""
    if ns is None:
        ns = {}
    found = element.find(path, ns)
    if found is not None and found.text:
        return found.text.strip()
    # Try without namespace
    if ns:
        found = element.find(path.replace('irs:', ''), {})
        if found is not None and found.text:
            return found.text.strip()
    return None


def safe_find_float(element: ET.Element, path: str, ns: dict = None) -> Optional[float]:
    """Safely find and convert to float"""
    text = safe_find_text(element, path, ns)
    if text:
        try:
            return float(text.replace(',', ''))
        except ValueError:
            return None
    return None


def safe_find_int(element: ET.Element, path: str, ns: dict = None) -> Optional[int]:
    """Safely find and convert to int"""
    val = safe_find_float(element, path, ns)
    return int(val) if val is not None else None


def classify_industry(name: str, purpose: str = None, ntee: str = None) -> Optional[str]:
    """Classify employer industry from available data"""
    # Check NTEE code first
    if ntee and len(ntee) > 0:
        first_char = ntee[0].upper()
        if first_char in EMPLOYER_NTEE_CODES:
            return EMPLOYER_NTEE_CODES[first_char]
    
    # Fall back to keyword matching
    text_to_check = f"{name} {purpose or ''}".lower()
    
    if any(kw in text_to_check for kw in ['hospital', 'medical center', 'health system', 'clinic']):
        return 'Healthcare'
    if any(kw in text_to_check for kw in ['university', 'college', 'school', 'academy', 'education']):
        return 'Education'
    if any(kw in text_to_check for kw in ['nursing home', 'assisted living', 'senior', 'elder']):
        return 'Senior Care'
    if any(kw in text_to_check for kw in ['social service', 'community', 'human service']):
        return 'Social Services'
    if any(kw in text_to_check for kw in ['theater', 'theatre', 'museum', 'orchestra', 'symphony']):
        return 'Arts/Entertainment'
    if any(kw in text_to_check for kw in ['transit', 'transportation', 'airport']):
        return 'Transportation'
    if any(kw in text_to_check for kw in ['housing', 'shelter']):
        return 'Housing'
    
    return None


def is_significant_employer(salaries: float = None, revenue: float = None, 
                           employees: int = None, name: str = "",
                           exempt_status: str = None) -> bool:
    """
    Determine if organization is a significant employer worth tracking
    
    Rules:
    - Must have >= $200k total revenue to qualify as employer
    - EXCEPTION: 501(c)(5) orgs are labor organizations, always include
    """
    # 501(c)(5) = labor organizations - always include regardless of size
    if exempt_status == '501c5':
        return True
    
    # Minimum revenue threshold for employers
    if not revenue or revenue < 200000:
        return False
    
    # Above $200k revenue - check other indicators
    # Has substantial payroll
    if salaries and salaries > 100000:
        return True
    
    # Has employees reported
    if employees and employees > 10:
        return True
    
    # Revenue alone is enough if above threshold
    if revenue >= 200000:
        return True
    
    # Known employer keywords in name
    name_lower = name.lower()
    if any(kw in name_lower for kw in EMPLOYER_KEYWORDS):
        return True
    
    return False


# ============================================================================
# MAIN EXTRACTION FUNCTIONS
# ============================================================================

def extract_filer_as_employer(root: ET.Element, ns: dict, filename: str) -> Optional[Employer990]:
    """Extract the 990 filer itself as a potential employer"""
    
    # Get basic identity
    ein = safe_find_text(root, './/irs:EIN', ns) or safe_find_text(root, './/EIN', {})
    name = safe_find_text(root, './/irs:BusinessName/irs:BusinessNameLine1Txt', ns) or \
           safe_find_text(root, './/BusinessName/BusinessNameLine1Txt', {})
    
    if not name:
        return None
    
    # Get financials
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
    
    # Determine exempt status BEFORE filtering
    exempt_status = None
    
    # Check for 501(c)(3)
    if root.find('.//irs:Organization501c3Ind', ns) is not None or \
       root.find('.//Organization501c3Ind', {}) is not None:
        exempt_status = '501c3'
    
    # Check for other 501(c) types - this is where 501(c)(5) labor orgs are identified
    c_type_elem = root.find('.//irs:Organization501cInd', ns)
    if c_type_elem is None:
        c_type_elem = root.find('.//Organization501cInd', {})
    if c_type_elem is not None:
        c_type = c_type_elem.get('organization501cTypeTxt')
        if c_type:
            exempt_status = f'501c{c_type}'
    
    # Check if significant employer (passes exempt_status for 501c5 exception)
    if not is_significant_employer(salaries, revenue, employees, name, exempt_status):
        return None
    
    # Build employer record
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
        exempt_status=exempt_status
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
    
    # Industry classification
    purpose = safe_find_text(root, './/irs:ActivityOrMissionDesc', ns) or \
              safe_find_text(root, './/irs:PrimaryExemptPurposeTxt', ns) or \
              safe_find_text(root, './/PrimaryExemptPurposeTxt', {})
    emp.industry_category = classify_industry(name, purpose)
    
    # Mark 501c5 as labor organization
    if exempt_status == '501c5':
        emp.industry_category = 'Labor Organization'
    
    return emp


def extract_grant_recipients(root: ET.Element, ns: dict, source_ein: str, 
                            source_name: str, filename: str) -> List[Employer990]:
    """Extract grant recipients as potential employers"""
    employers = []
    
    # 990PF grant recipients
    grant_groups = root.findall('.//irs:GrantOrContributionPdDurYrGrp', ns) + \
                   root.findall('.//GrantOrContributionPdDurYrGrp', {})
    
    # Full 990 Schedule I recipients
    grant_groups += root.findall('.//irs:RecipientTable', ns) + \
                    root.findall('.//RecipientTable', {})
    
    for gg in grant_groups:
        # Get recipient name
        name = safe_find_text(gg, './/irs:RecipientBusinessName/irs:BusinessNameLine1Txt', ns) or \
               safe_find_text(gg, './/RecipientBusinessName/BusinessNameLine1Txt', {}) or \
               safe_find_text(gg, './/irs:RecipientNameBusiness/irs:BusinessNameLine1', ns) or \
               safe_find_text(gg, './/RecipientNameBusiness/BusinessNameLine1', {})
        
        if not name:
            continue
        
        # Skip if clearly an individual
        if len(name.split()) <= 2 and ',' in name:
            continue
        
        amount = safe_find_float(gg, './/irs:Amt', ns) or \
                 safe_find_float(gg, './/Amt', {}) or \
                 safe_find_float(gg, './/irs:CashGrantAmt', ns) or \
                 safe_find_float(gg, './/CashGrantAmt', {})
        
        # Only track significant grants
        if amount and amount < 5000:
            continue
        
        emp = Employer990(
            name=name,
            source_type='grant_recipient',
            source_ein=source_ein,
            source_name=source_name,
            source_file=filename,
            grant_amount=amount
        )
        
        # Address
        emp.city = safe_find_text(gg, './/irs:RecipientUSAddress/irs:CityNm', ns) or \
                   safe_find_text(gg, './/RecipientUSAddress/CityNm', {}) or \
                   safe_find_text(gg, './/irs:USAddress/irs:CityNm', ns)
        emp.state = safe_find_text(gg, './/irs:RecipientUSAddress/irs:StateAbbreviationCd', ns) or \
                    safe_find_text(gg, './/RecipientUSAddress/StateAbbreviationCd', {}) or \
                    safe_find_text(gg, './/irs:USAddress/irs:StateAbbreviationCd', ns)
        
        # EIN if available
        emp.ein = safe_find_text(gg, './/irs:RecipientEIN', ns) or \
                  safe_find_text(gg, './/RecipientEIN', {})
        
        # Purpose
        purpose = safe_find_text(gg, './/irs:GrantOrContributionPurposeTxt', ns) or \
                  safe_find_text(gg, './/GrantOrContributionPurposeTxt', {}) or \
                  safe_find_text(gg, './/irs:PurposeOfGrantTxt', ns)
        
        emp.industry_category = classify_industry(name, purpose)
        
        employers.append(emp)
    
    return employers


def extract_contractors(root: ET.Element, ns: dict, source_ein: str,
                       source_name: str, filename: str) -> List[Employer990]:
    """Extract independent contractors as potential employers/service providers"""
    employers = []
    
    # Schedule J / Part VII contractors
    contractor_groups = root.findall('.//irs:ContractorCompensationGrp', ns) + \
                        root.findall('.//ContractorCompensationGrp', {}) + \
                        root.findall('.//irs:IndependentContractorsGrp', ns) + \
                        root.findall('.//IndependentContractorsGrp', {})
    
    for cg in contractor_groups:
        name = safe_find_text(cg, './/irs:ContractorName/irs:BusinessNameLine1Txt', ns) or \
               safe_find_text(cg, './/ContractorName/BusinessNameLine1Txt', {}) or \
               safe_find_text(cg, './/irs:BusinessName/irs:BusinessNameLine1Txt', ns)
        
        if not name:
            continue
        
        amount = safe_find_float(cg, './/irs:CompensationAmt', ns) or \
                 safe_find_float(cg, './/CompensationAmt', {})
        
        # Only track significant contractors
        if not amount or amount < 100000:
            continue
        
        emp = Employer990(
            name=name,
            source_type='contractor',
            source_ein=source_ein,
            source_name=source_name,
            source_file=filename,
            contractor_payment=amount
        )
        
        # Address
        emp.city = safe_find_text(cg, './/irs:ContractorAddress/irs:USAddress/irs:CityNm', ns)
        emp.state = safe_find_text(cg, './/irs:ContractorAddress/irs:USAddress/irs:StateAbbreviationCd', ns)
        
        # Services description for classification
        services = safe_find_text(cg, './/irs:ServicesDesc', ns) or \
                   safe_find_text(cg, './/ServicesDesc', {})
        emp.industry_category = classify_industry(name, services)
        
        employers.append(emp)
    
    return employers


def extract_related_organizations(root: ET.Element, ns: dict, source_ein: str,
                                  source_name: str, filename: str) -> List[Employer990]:
    """Extract related organizations (Schedule R) as potential employers"""
    employers = []
    
    # Schedule R - Related Organizations
    related_groups = root.findall('.//irs:IdRelatedTaxExemptOrgGrp', ns) + \
                     root.findall('.//IdRelatedTaxExemptOrgGrp', {}) + \
                     root.findall('.//irs:IdRelatedOrgTxblPartnershipGrp', ns) + \
                     root.findall('.//IdRelatedOrgTxblPartnershipGrp', {}) + \
                     root.findall('.//irs:IdRelatedOrgTxblCorpTrGrp', ns) + \
                     root.findall('.//IdRelatedOrgTxblCorpTrGrp', {})
    
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
            source_file=filename
        )
        
        emp.ein = safe_find_text(rg, './/irs:EIN', ns) or safe_find_text(rg, './/EIN', {})
        emp.city = safe_find_text(rg, './/irs:USAddress/irs:CityNm', ns)
        emp.state = safe_find_text(rg, './/irs:USAddress/irs:StateAbbreviationCd', ns)
        
        employers.append(emp)
    
    return employers


def process_990_file(file_path: str) -> Tuple[Optional[Employer990], List[Employer990]]:
    """
    Process a single 990 file
    Returns: (filer_employer, [related_employers])
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Determine namespace
        ns = IRS_NS if root.tag.startswith('{') else {}
        filename = os.path.basename(file_path)
        
        # Get filer info for source tracking
        source_ein = safe_find_text(root, './/irs:EIN', ns) or safe_find_text(root, './/EIN', {})
        source_name = safe_find_text(root, './/irs:BusinessName/irs:BusinessNameLine1Txt', ns) or \
                      safe_find_text(root, './/BusinessName/BusinessNameLine1Txt', {})
        
        # Extract filer as employer
        filer_employer = extract_filer_as_employer(root, ns, filename)
        
        # Extract related employers
        related_employers = []
        related_employers.extend(extract_grant_recipients(root, ns, source_ein, source_name, filename))
        related_employers.extend(extract_contractors(root, ns, source_ein, source_name, filename))
        related_employers.extend(extract_related_organizations(root, ns, source_ein, source_name, filename))
        
        return filer_employer, related_employers
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None, []


# ============================================================================
# BATCH PROCESSING
# ============================================================================

def process_batch(input_dir: str, output_file: str = 'employers_990.json',
                  limit: int = None) -> Dict:
    """Process all 990 files and extract employers"""
    
    results = {
        'summary': {
            'total_files': 0,
            'files_processed': 0,
            'filer_employers': 0,
            'labor_orgs_501c5': 0,  # Separate count for labor organizations
            'grant_recipients': 0,
            'contractors': 0,
            'related_orgs': 0,
            'filtered_under_200k': 0,  # Track how many filtered out
            'by_industry': defaultdict(int),
            'by_state': defaultdict(int),
            'processing_time': None
        },
        'employers': [],
        'labor_organizations': []  # Separate list for 501c5 orgs
    }
    
    start_time = datetime.now()
    
    # Get XML files
    xml_files = [f for f in os.listdir(input_dir) if f.endswith('.xml')]
    if limit:
        xml_files = xml_files[:limit]
    
    results['summary']['total_files'] = len(xml_files)
    print(f"Processing {len(xml_files)} files for employer extraction...")
    print(f"Filter: Revenue >= $200k OR 501(c)(5) labor organization")
    
    seen_employers = set()  # Dedupe by (name, city, state)
    
    for i, filename in enumerate(xml_files):
        if i > 0 and i % 1000 == 0:
            print(f"  Processed {i}/{len(xml_files)}...")
        
        file_path = os.path.join(input_dir, filename)
        filer_emp, related_emps = process_990_file(file_path)
        
        results['summary']['files_processed'] += 1
        
        # Add filer employer
        if filer_emp:
            key = (filer_emp.name.lower(), filer_emp.city, filer_emp.state)
            if key not in seen_employers:
                seen_employers.add(key)
                emp_dict = filer_emp.to_dict()
                
                # Separate labor orgs from employers
                if filer_emp.exempt_status == '501c5':
                    results['labor_organizations'].append(emp_dict)
                    results['summary']['labor_orgs_501c5'] += 1
                else:
                    results['employers'].append(emp_dict)
                    results['summary']['filer_employers'] += 1
                
                if filer_emp.industry_category:
                    results['summary']['by_industry'][filer_emp.industry_category] += 1
                if filer_emp.state:
                    results['summary']['by_state'][filer_emp.state] += 1
        
        # Add related employers (grant recipients, contractors, related orgs)
        for emp in related_emps:
            key = (emp.name.lower(), emp.city, emp.state)
            if key not in seen_employers:
                seen_employers.add(key)
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
    
    # Write results
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n=== Extraction Complete ===")
    print(f"Files processed: {results['summary']['files_processed']}")
    print(f"\nEMPLOYERS (Revenue >= $200k):")
    print(f"  Total unique employers: {results['summary']['total_employers']}")
    print(f"    - Filer employers: {results['summary']['filer_employers']}")
    print(f"    - Grant recipients: {results['summary']['grant_recipients']}")
    print(f"    - Contractors: {results['summary']['contractors']}")
    print(f"    - Related orgs: {results['summary']['related_orgs']}")
    print(f"\nLABOR ORGANIZATIONS (501c5, any size):")
    print(f"  Total 501(c)(5) orgs: {results['summary']['labor_orgs_501c5']}")
    print(f"\nTop industries:")
    for ind, count in sorted(results['summary']['by_industry'].items(), key=lambda x: -x[1])[:10]:
        print(f"  {ind}: {count}")
    print(f"\nResults saved to: {output_file}")
    
    return results


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract employers from IRS 990 files')
    parser.add_argument('--input-dir', required=True, help='Directory with 990 XML files')
    parser.add_argument('--output', default='employers_990.json', help='Output JSON file')
    parser.add_argument('--limit', type=int, help='Limit files to process')
    
    args = parser.parse_args()
    process_batch(args.input_dir, args.output, args.limit)
