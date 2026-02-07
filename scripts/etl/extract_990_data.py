r"""
IRS 990 XML Data Extractor
Extracts key fields from 990, 990PF, and 990EZ forms for employer matching.

Usage: python extract_990_data.py <input_folder> <output_csv>
Example: python extract_990_data.py "C:\Users\jakew\Downloads\labor-data-project\990 2025" ny_990_extract.csv

For 700K files, recommend running with state filter:
python extract_990_data.py "C:\990 2025" ny_990_extract.csv --state NY
"""

import xml.etree.ElementTree as ET
import csv
import os
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
from datetime import datetime

# IRS 990 namespace
NS = {'irs': 'http://www.irs.gov/efile'}

def safe_find(root, paths, ns=NS):
    """Try multiple XPath expressions, return first match or empty string."""
    if isinstance(paths, str):
        paths = [paths]
    for path in paths:
        try:
            # Try with namespace
            elem = root.find(path, ns)
            if elem is not None and elem.text:
                return elem.text.strip()
            # Try without namespace (some older files)
            elem = root.find(path.replace('irs:', ''))
            if elem is not None and elem.text:
                return elem.text.strip()
        except:
            pass
    return ''

def extract_990_data(xml_path):
    """Extract key fields from a 990 XML file."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Determine form type
        form_type = safe_find(root, [
            './/irs:ReturnTypeCd',
            './/ReturnTypeCd'
        ])
        
        # Basic identifiers - in ReturnHeader/Filer
        ein = safe_find(root, [
            './/irs:Filer/irs:EIN',
            './/Filer/EIN',
            './/irs:EIN',
            './/EIN'
        ])
        
        # Organization name
        org_name = safe_find(root, [
            './/irs:Filer/irs:BusinessName/irs:BusinessNameLine1Txt',
            './/Filer/BusinessName/BusinessNameLine1Txt',
            './/irs:BusinessName/irs:BusinessNameLine1Txt',
            './/BusinessName/BusinessNameLine1Txt',
            './/irs:Filer/irs:Name/irs:BusinessNameLine1',
            './/Filer/Name/BusinessNameLine1'
        ])
        
        org_name_2 = safe_find(root, [
            './/irs:Filer/irs:BusinessName/irs:BusinessNameLine2Txt',
            './/Filer/BusinessName/BusinessNameLine2Txt'
        ])
        if org_name_2:
            org_name = f"{org_name} {org_name_2}"
        
        # Address
        city = safe_find(root, [
            './/irs:Filer/irs:USAddress/irs:CityNm',
            './/Filer/USAddress/CityNm',
            './/irs:USAddress/irs:CityNm',
            './/USAddress/CityNm',
            './/irs:Filer/irs:USAddress/irs:City',
            './/Filer/USAddress/City'
        ])
        
        state = safe_find(root, [
            './/irs:Filer/irs:USAddress/irs:StateAbbreviationCd',
            './/Filer/USAddress/StateAbbreviationCd',
            './/irs:USAddress/irs:StateAbbreviationCd',
            './/USAddress/StateAbbreviationCd',
            './/irs:Filer/irs:USAddress/irs:State',
            './/Filer/USAddress/State'
        ])
        
        zip_code = safe_find(root, [
            './/irs:Filer/irs:USAddress/irs:ZIPCd',
            './/Filer/USAddress/ZIPCd',
            './/irs:USAddress/irs:ZIPCd',
            './/USAddress/ZIPCd'
        ])
        
        street = safe_find(root, [
            './/irs:Filer/irs:USAddress/irs:AddressLine1Txt',
            './/Filer/USAddress/AddressLine1Txt',
            './/irs:USAddress/irs:AddressLine1Txt'
        ])
        
        # Tax year
        tax_year = safe_find(root, [
            './/irs:TaxYr',
            './/TaxYr',
            './/irs:ReturnHeader/irs:TaxYr'
        ])
        
        # Tax period
        tax_period_end = safe_find(root, [
            './/irs:TaxPeriodEndDt',
            './/TaxPeriodEndDt'
        ])
        
        # Phone
        phone = safe_find(root, [
            './/irs:Filer/irs:PhoneNum',
            './/Filer/PhoneNum',
            './/irs:PhoneNum'
        ])
        
        # Website (990 only)
        website = safe_find(root, [
            './/irs:WebsiteAddressTxt',
            './/WebsiteAddressTxt',
            './/irs:IRS990/irs:WebsiteAddressTxt'
        ])
        
        # Revenue - varies by form type
        total_revenue = ''
        total_expenses = ''
        total_assets = ''
        num_employees = ''
        
        if form_type == '990':
            # Regular 990
            total_revenue = safe_find(root, [
                './/irs:IRS990/irs:CYTotalRevenueAmt',
                './/irs:TotalRevenueGrp/irs:TotalRevenueColumnAmt',
                './/irs:TotalRevenueAmt',
                './/IRS990/CYTotalRevenueAmt',
                './/CYTotalRevenueAmt'
            ])
            total_expenses = safe_find(root, [
                './/irs:IRS990/irs:CYTotalExpensesAmt',
                './/irs:TotalFunctionalExpensesGrp/irs:TotalAmt',
                './/CYTotalExpensesAmt'
            ])
            total_assets = safe_find(root, [
                './/irs:IRS990/irs:TotalAssetsEOYAmt',
                './/irs:TotalAssetsEOYAmt',
                './/TotalAssetsEOYAmt'
            ])
            num_employees = safe_find(root, [
                './/irs:IRS990/irs:TotalEmployeeCnt',
                './/irs:TotalEmployeeCnt',
                './/TotalEmployeeCnt'
            ])
            
        elif form_type == '990PF':
            # Private Foundation 990PF
            total_revenue = safe_find(root, [
                './/irs:IRS990PF/irs:AnalysisOfRevenueAndExpenses/irs:TotalRevAndExpnssAmt',
                './/irs:TotalRevAndExpnssAmt',
                './/TotalRevAndExpnssAmt'
            ])
            total_expenses = safe_find(root, [
                './/irs:IRS990PF/irs:AnalysisOfRevenueAndExpenses/irs:TotalExpensesRevAndExpnssAmt',
                './/irs:TotalExpensesRevAndExpnssAmt',
                './/TotalExpensesRevAndExpnssAmt'
            ])
            total_assets = safe_find(root, [
                './/irs:IRS990PF/irs:Form990PFBalanceSheetsGrp/irs:TotalAssetsEOYAmt',
                './/irs:TotalAssetsEOYAmt',
                './/TotalAssetsEOYAmt',
                './/irs:FMVAssetsEOYAmt',
                './/FMVAssetsEOYAmt'
            ])
            
        elif form_type == '990EZ':
            # 990-EZ (small organizations)
            total_revenue = safe_find(root, [
                './/irs:IRS990EZ/irs:TotalRevenueAmt',
                './/irs:TotalRevenueAmt',
                './/TotalRevenueAmt'
            ])
            total_expenses = safe_find(root, [
                './/irs:IRS990EZ/irs:TotalExpensesAmt',
                './/irs:TotalExpensesAmt',
                './/TotalExpensesAmt'
            ])
            total_assets = safe_find(root, [
                './/irs:IRS990EZ/irs:Form990TotalAssetsGrp/irs:EOYAmt',
                './/irs:TotalAssetsEOYAmt'
            ])
        
        # Activity/Mission description (990 only - useful for classification)
        activity_desc = safe_find(root, [
            './/irs:IRS990/irs:ActivityOrMissionDesc',
            './/irs:ActivityOrMissionDesc',
            './/ActivityOrMissionDesc',
            './/irs:IRS990/irs:Desc',
            './/irs:PrimaryExemptPurposeTxt'
        ])[:500]  # Truncate long descriptions
        
        # NTEE code (nonprofit classification - if present)
        ntee_code = safe_find(root, [
            './/irs:NTEECd',
            './/NTEECd'
        ])
        
        # 501c type
        org_type_501c = safe_find(root, [
            './/irs:Organization501c3Ind',
            './/irs:Organization501cInd',
            './/Organization501c3Ind'
        ])
        if not org_type_501c:
            # Check for 501c3 indicator
            c3_ind = root.find('.//{http://www.irs.gov/efile}Organization501c3ExemptPFInd')
            if c3_ind is not None:
                org_type_501c = '501c3'
        
        return {
            'filename': os.path.basename(xml_path),
            'ein': ein,
            'org_name': org_name,
            'street': street,
            'city': city,
            'state': state,
            'zip': zip_code,
            'phone': phone,
            'website': website,
            'form_type': form_type,
            'tax_year': tax_year,
            'tax_period_end': tax_period_end,
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'total_assets': total_assets,
            'num_employees': num_employees,
            'ntee_code': ntee_code,
            'org_type_501c': org_type_501c,
            'activity_desc': activity_desc
        }
        
    except ET.ParseError as e:
        return {'filename': os.path.basename(xml_path), 'error': f'XML Parse Error: {e}'}
    except Exception as e:
        return {'filename': os.path.basename(xml_path), 'error': f'Error: {e}'}

def process_files(input_folder, output_csv, state_filter=None, limit=None):
    """Process all XML files in folder and write to CSV."""
    
    # Get list of XML files
    xml_files = list(Path(input_folder).glob('*.xml'))
    total_files = len(xml_files)
    print(f"Found {total_files:,} XML files in {input_folder}")
    
    if limit:
        xml_files = xml_files[:limit]
        print(f"Processing first {limit:,} files (limit applied)")
    
    # CSV columns
    fieldnames = [
        'filename', 'ein', 'org_name', 'street', 'city', 'state', 'zip',
        'phone', 'website', 'form_type', 'tax_year', 'tax_period_end',
        'total_revenue', 'total_expenses', 'total_assets', 'num_employees',
        'ntee_code', 'org_type_501c', 'activity_desc', 'error'
    ]
    
    processed = 0
    matched = 0
    errors = 0
    start_time = datetime.now()
    
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        # Process in batches for memory efficiency
        batch_size = 1000
        
        for i, xml_path in enumerate(xml_files):
            result = extract_990_data(str(xml_path))
            
            # Apply state filter if specified
            if state_filter and result.get('state', '').upper() != state_filter.upper():
                processed += 1
                continue
            
            if 'error' in result:
                errors += 1
            else:
                matched += 1
            
            writer.writerow(result)
            processed += 1
            
            # Progress update every 10000 files
            if processed % 10000 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = (total_files - processed) / rate if rate > 0 else 0
                print(f"Processed {processed:,}/{total_files:,} ({processed/total_files*100:.1f}%) - "
                      f"{matched:,} matched, {errors:,} errors - "
                      f"Rate: {rate:.0f}/sec - ETA: {remaining/60:.1f} min")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"COMPLETE: Processed {processed:,} files in {elapsed:.1f} seconds")
    print(f"  - Matched (written): {matched:,}")
    print(f"  - Errors: {errors:,}")
    print(f"  - Output: {output_csv}")
    print(f"  - Rate: {processed/elapsed:.0f} files/second")

def main():
    parser = argparse.ArgumentParser(description='Extract data from IRS 990 XML files')
    parser.add_argument('input_folder', help='Folder containing 990 XML files')
    parser.add_argument('output_csv', help='Output CSV file path')
    parser.add_argument('--state', help='Filter by state (e.g., NY)')
    parser.add_argument('--limit', type=int, help='Limit number of files to process')
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.input_folder):
        print(f"Error: Input folder not found: {args.input_folder}")
        sys.exit(1)
    
    process_files(args.input_folder, args.output_csv, args.state, args.limit)

if __name__ == '__main__':
    main()
