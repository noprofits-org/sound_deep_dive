import os
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import json
from collections import defaultdict
import pandas as pd
from pathlib import Path

def extract_real_xml_content(file_path):
    """Extract the actual XML content from HTML files that contain embedded XML."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Look for the XML content within the HTML
        # First, try to find the standard Return element
        return_pattern = r'<Return xmlns="http://www\.irs\.gov/efile".*?</Return>'
        match = re.search(return_pattern, content, re.DOTALL)
        if match:
            return match.group(0)
        
        # If that fails, try to extract from the webkit-xml-viewer-source-xml div
        soup = BeautifulSoup(content, 'html.parser')
        source_div = soup.find('div', id='webkit-xml-viewer-source-xml')
        if source_div:
            # Get the first Return element from the div's contents
            return_matches = re.findall(return_pattern, str(source_div), re.DOTALL)
            if return_matches:
                return return_matches[0]
        
        print(f"Could not extract XML from {file_path}")
        return None
    
    except Exception as e:
        print(f"Error reading {file_path}: {str(e)}")
        return None

def extract_schema_info(xml_content):
    """Extract schema version and tax year information from XML content."""
    try:
        # Clean up XML content if needed
        xml_content = re.sub(r'&gt;', '>', xml_content)
        xml_content = re.sub(r'&lt;', '<', xml_content)
        
        # Parse XML
        root = ET.fromstring(xml_content)
        
        # Get schema version from returnVersion attribute
        schema_version = root.get('returnVersion', 'Unknown')
        
        # Determine namespace
        ns = ''
        if '}' in root.tag:
            ns = root.tag.split('}', 1)[0][1:]
        
        # Try to find tax year with various possible paths
        tax_year = None
        tax_year_paths = [
            './/TaxPeriodEndDt',
            './/TaxYr',
            './/ReturnHeader/TaxPeriodEndDt',
            './/ReturnHeader/TaxYr'
        ]
        
        for path in tax_year_paths:
            # Try with namespace
            if ns:
                ns_path = path.replace('/', '/{' + ns + '}')
                if not ns_path.startswith('{'):
                    ns_path = '{' + ns + '}' + ns_path
                elem = root.find(ns_path)
                if elem is not None and elem.text:
                    tax_year_val = elem.text
                    # If it's a date, extract just the year
                    if '-' in tax_year_val:
                        tax_year = tax_year_val.split('-')[0]
                    else:
                        tax_year = tax_year_val
                    break
            
            # Try without namespace
            elem = root.find(path)
            if elem is not None and elem.text:
                tax_year_val = elem.text
                # If it's a date, extract just the year
                if '-' in tax_year_val:
                    tax_year = tax_year_val.split('-')[0]
                else:
                    tax_year = tax_year_val
                break
        
        return {
            'schema_version': schema_version,
            'tax_year': tax_year,
            'namespace': ns
        }
    
    except Exception as e:
        print(f"Error extracting schema info: {str(e)}")
        return {
            'schema_version': 'Error',
            'tax_year': None,
            'namespace': None
        }

def get_element_paths(element, current_path='', path_map=None, namespace=None):
    """Recursively map all element paths in the XML."""
    if path_map is None:
        path_map = defaultdict(list)
    
    # Get the local name without namespace
    if '}' in element.tag:
        local_name = element.tag.split('}', 1)[1]
    else:
        local_name = element.tag
    
    # Update the current path
    new_path = f"{current_path}/{local_name}" if current_path else local_name
    
    # Add to path map if the element has text content
    if element.text and element.text.strip():
        path_map[local_name].append({
            'path': new_path,
            'value': element.text.strip(),
            'has_attributes': len(element.attrib) > 0
        })
    elif len(element.attrib) > 0:
        # Add to path map if the element has attributes even without text
        path_map[local_name].append({
            'path': new_path,
            'value': '',
            'has_attributes': True
        })
    
    # Process child elements
    for child in element:
        get_element_paths(child, new_path, path_map, namespace)
    
    return path_map

def map_schema_elements(xml_content, max_depth=10):
    """Map the elements in a schema to understand its structure."""
    try:
        # Clean up XML content if needed
        xml_content = re.sub(r'&gt;', '>', xml_content)
        xml_content = re.sub(r'&lt;', '<', xml_content)
        
        # Parse XML
        root = ET.fromstring(xml_content)
        
        # Map elements
        element_paths = get_element_paths(root)
        
        # Get all unique parent paths up to max_depth
        parent_paths = set()
        for paths in element_paths.values():
            for path_info in paths:
                path = path_info['path']
                parts = path.split('/')
                for i in range(1, min(len(parts), max_depth) + 1):
                    parent_paths.add('/'.join(parts[:i]))
        
        # Count elements at each path level
        path_counts = defaultdict(int)
        for paths in element_paths.values():
            for path_info in paths:
                path = path_info['path']
                path_counts[path] += 1
        
        return {
            'element_paths': element_paths,
            'parent_paths': sorted(list(parent_paths)),
            'path_counts': dict(path_counts)
        }
    
    except Exception as e:
        print(f"Error mapping schema elements: {str(e)}")
        return {
            'element_paths': {},
            'parent_paths': [],
            'path_counts': {}
        }

def find_elements_of_interest(schema_map, interest_list):
    """Find paths for elements of interest."""
    findings = {}
    
    for interest_item in interest_list:
        findings[interest_item] = []
        
        # Look for exact matches in element_paths
        if interest_item in schema_map['element_paths']:
            findings[interest_item].extend(schema_map['element_paths'][interest_item])
        
        # Look for partial matches
        for element_name, paths in schema_map['element_paths'].items():
            if interest_item.lower() in element_name.lower() and element_name != interest_item:
                for path_info in paths:
                    # Add with a note that it's a partial match
                    path_info_copy = path_info.copy()
                    path_info_copy['partial_match'] = True
                    path_info_copy['matched_element'] = element_name
                    findings[interest_item].append(path_info_copy)
    
    return findings

def analyze_directory(directory_path, elements_of_interest):
    """Analyze all XML files in the given directory and map schemas."""
    schema_results = defaultdict(list)
    schema_element_maps = {}
    file_info = []
    
    for filename in sorted(os.listdir(directory_path)):
        if filename.endswith('.xml'):
            file_path = os.path.join(directory_path, filename)
            print(f"\nProcessing {filename}...")
            
            # Extract the XML content
            xml_content = extract_real_xml_content(file_path)
            
            if xml_content:
                # Extract schema information
                schema_info = extract_schema_info(xml_content)
                schema_info['filename'] = filename
                
                # Add to file_info list
                file_info.append(schema_info)
                
                # Check if we've already mapped this schema version
                schema_version = schema_info['schema_version']
                if schema_version not in schema_element_maps:
                    print(f"  Mapping elements for schema version {schema_version}...")
                    schema_map = map_schema_elements(xml_content)
                    schema_element_maps[schema_version] = schema_map
                    
                    # Find paths for elements of interest
                    interest_findings = find_elements_of_interest(schema_map, elements_of_interest)
                    schema_results[schema_version].append({
                        'schema_info': schema_info,
                        'interest_findings': interest_findings
                    })
                else:
                    print(f"  Schema version {schema_version} already mapped.")
            else:
                print(f"  Could not extract XML content from {filename}")
    
    return {
        'file_info': file_info,
        'schema_results': dict(schema_results),
        'schema_element_maps': schema_element_maps
    }

def generate_schema_report(results):
    """Generate a markdown report of schema findings."""
    markdown = []
    
    # Summary of files analyzed
    markdown.append("# Form 990 Schema Analysis Report\n")
    
    # Table of files
    markdown.append("## Files Analyzed\n")
    markdown.append("| Filename | Schema Version | Tax Year |")
    markdown.append("|----------|----------------|----------|")
    
    for file_info in results['file_info']:
        markdown.append(
            f"| {file_info['filename']} | {file_info['schema_version']} | {file_info['tax_year'] or 'Unknown'} |"
        )
    
    markdown.append("\n")
    
    # Unique schema versions
    unique_schemas = set(file_info['schema_version'] for file_info in results['file_info'])
    markdown.append("## Schema Versions Found\n")
    for schema in sorted(unique_schemas):
        markdown.append(f"- {schema}")
    
    markdown.append("\n")
    
    # For each unique schema, show paths for elements of interest
    markdown.append("## Element Paths by Schema Version\n")
    
    for schema_version, findings in results['schema_results'].items():
        markdown.append(f"### Schema Version: {schema_version}\n")
        
        for finding in findings:
            interest_findings = finding['interest_findings']
            
            for element, paths in interest_findings.items():
                markdown.append(f"#### {element}\n")
                
                if not paths:
                    markdown.append("*No matches found.*\n")
                else:
                    markdown.append("| Path | Example Value | Has Attributes | Notes |")
                    markdown.append("|------|---------------|----------------|-------|")
                    
                    for path_info in paths:
                        notes = f"Partial match to {path_info['matched_element']}" if path_info.get('partial_match') else ""
                        has_attrs = "Yes" if path_info['has_attributes'] else "No"
                        value = path_info['value']
                        # Truncate very long values
                        if len(value) > 40:
                            value = value[:37] + "..."
                        
                        markdown.append(
                            f"| {path_info['path']} | {value} | {has_attrs} | {notes} |"
                        )
                
                markdown.append("\n")
    
    return "\n".join(markdown)

def build_element_path_lookup(results):
    """Build a lookup dictionary for element paths across schema versions."""
    lookup = {}
    
    for element_of_interest in results['schema_results'].values():
        for finding in element_of_interest:
            schema_version = finding['schema_info']['schema_version']
            
            if schema_version not in lookup:
                lookup[schema_version] = {}
            
            for element, paths in finding['interest_findings'].items():
                if element not in lookup[schema_version]:
                    lookup[schema_version][element] = []
                
                for path_info in paths:
                    # Only add exact matches to the lookup
                    if not path_info.get('partial_match'):
                        lookup[schema_version][element].append(path_info['path'])
    
    return lookup

# Main execution
if __name__ == "__main__":
    # Directory containing XML files
    data_dir = "nonprofit_data/910818971"
    
    # Elements of interest for nonprofit analysis
    elements_of_interest = [
        # Basic organization info
        "BusinessNameLine1Txt", "EIN", "WebsiteAddressTxt", "MissionDesc",
        
        # Financial data
        "TotalRevenueAmt", "TotalExpensesAmt", "TotalAssetsEOYAmt", "TotalLiabilitiesEOYAmt",
        "CYTotalRevenueAmt", "CYTotalExpensesAmt", "CYContributionsGrantsAmt",
        "ProgramServiceRevenueAmt", "CYProgramServiceRevenueAmt",
        "TotalProgramServiceExpensesAmt", "CYTotalFundraisingExpenseAmt",
        "FundraisingAmt", "ManagementAndGeneralAmt",
        
        # Executive compensation
        "PersonNm", "TitleTxt", "AverageHoursPerWeekRt", "ReportableCompFromOrgAmt", 
        "OtherCompensationAmt", "CompCurrentOfcrDirectorsGrp",
        
        # Program services and accomplishments
        "ProgSrvcAccomActy", "ProgramServicesAmt", "ExpenseAmt", "Desc",
        
        # Employees and volunteers
        "TotalEmployeeCnt", "TotalVolunteersCnt",
        
        # Functional expenses
        "OtherSalariesAndWagesGrp", "PayrollTaxesGrp", "OccupancyGrp",
        "TotalFunctionalExpensesGrp", "OtherExpensesGrp"
    ]
    
    # Run the analysis
    results = analyze_directory(data_dir, elements_of_interest)
    
    # Generate report
    report = generate_schema_report(results)
    output_file = "990_schema_analysis.md"
    with open(output_file, "w") as f:
        f.write(report)
    
    # Build and save element path lookup
    path_lookup = build_element_path_lookup(results)
    with open("990_element_paths.json", "w") as f:
        json.dump(path_lookup, f, indent=2)
    
    print(f"\nAnalysis complete. Schema report saved to {output_file}")
    print(f"Element path lookup saved to 990_element_paths.json")