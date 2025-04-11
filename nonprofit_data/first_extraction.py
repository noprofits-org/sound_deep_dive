import os
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict

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

def find_element_by_paths(root, paths, namespace=None):
    """Find an element using multiple possible paths."""
    # Try different approaches to find the element
    for path in paths:
        try:
            # Try with namespace
            if namespace and '{' not in path:
                ns_path = path.replace('/', '/{' + namespace + '}')
                if not ns_path.startswith('{'):
                    ns_path = '{' + namespace + '}' + ns_path
                elem = root.find(ns_path)
                if elem is not None and elem.text:
                    return elem.text
            
            # Try without namespace
            elem = root.find(path)
            if elem is not None and elem.text:
                return elem.text
            
            # Try XPath with local-name
            if '/' in path:
                local_name = path.split('/')[-1]
                for e in root.iter():
                    if e.tag.split('}')[-1] == local_name:
                        if e.text:
                            return e.text
        except Exception as e:
            continue
    
    # If the above approaches fail, try regex on the XML string
    try:
        xml_str = ET.tostring(root, encoding='unicode')
        for path in paths:
            local_name = path.split('/')[-1]
            pattern = rf'<{local_name}>([^<]+)</{local_name}>'
            match = re.search(pattern, xml_str)
            if match:
                return match.group(1)
    except Exception:
        pass
    
    return None

def extract_financial_data(xml_content):
    """Extract key financial data from Form 990 XML content."""
    try:
        # Clean up XML content
        xml_content = re.sub(r'&gt;', '>', xml_content)
        xml_content = re.sub(r'&lt;', '<', xml_content)
        
        # Parse XML
        root = ET.fromstring(xml_content)
        
        # Determine namespace
        ns = ''
        if '}' in root.tag:
            ns = root.tag.split('}', 1)[0][1:]
        
        # Initialize data dictionary
        data = {
            'tax_year': None,
            'schema_version': root.get('returnVersion', 'Unknown'),
            'total_revenue': None,
            'total_expenses': None,
            'program_service_expenses': None,
            'fundraising_expenses': None,
            'total_contributions': None
        }
        
        # Extract tax year with various possible paths
        tax_year_paths = [
            './/TaxPeriodEndDt',
            './/TaxYr',
            './/ReturnHeader/TaxPeriodEndDt',
            './/TaxPeriodEndDt'
        ]
        
        tax_year_value = find_element_by_paths(root, tax_year_paths, ns)
        if tax_year_value:
            # Extract year from YYYY-MM-DD format if needed
            if '-' in tax_year_value:
                data['tax_year'] = tax_year_value.split('-')[0]
            else:
                data['tax_year'] = tax_year_value
        
        # Extract financial data using various possible element paths
        
        # Total Revenue
        revenue_paths = [
            './/IRS990/CYTotalRevenueAmt',
            './/IRS990/TotalRevenueAmt',
            './/ReturnData/IRS990/CYTotalRevenueAmt',
            './/ReturnData/IRS990/TotalRevenueAmt',
            './/TotalRevenue',
            './/CYTotalRevenueAmt',
            './/IRS990/TotalRevenue/TotalRevenueColumnAmt'
        ]
        data['total_revenue'] = find_element_by_paths(root, revenue_paths, ns)
        
        # Total Expenses
        expense_paths = [
            './/IRS990/CYTotalExpensesAmt',
            './/IRS990/TotalExpensesAmt',
            './/ReturnData/IRS990/CYTotalExpensesAmt',
            './/ReturnData/IRS990/TotalExpensesAmt',
            './/TotalExpenses',
            './/CYTotalExpensesAmt',
            './/IRS990/TotalFunctionalExpenses/TotalAmt'
        ]
        data['total_expenses'] = find_element_by_paths(root, expense_paths, ns)
        
        # Program Service Expenses
        program_expense_paths = [
            './/IRS990/TotalProgramServiceExpensesAmt',
            './/ReturnData/IRS990/TotalProgramServiceExpensesAmt',
            './/TotalProgramServiceExpensesAmt',
            './/IRS990/TotalFunctionalExpenses/ProgramServicesAmt'
        ]
        data['program_service_expenses'] = find_element_by_paths(root, program_expense_paths, ns)
        
        # Fundraising Expenses
        fundraising_paths = [
            './/IRS990/CYTotalFundraisingExpenseAmt',
            './/IRS990/FundraisingExpensesAmt',
            './/ReturnData/IRS990/CYTotalFundraisingExpenseAmt',
            './/ReturnData/IRS990/FundraisingExpensesAmt',
            './/CYTotalFundraisingExpenseAmt',
            './/IRS990/TotalFunctionalExpenses/FundraisingAmt'
        ]
        data['fundraising_expenses'] = find_element_by_paths(root, fundraising_paths, ns)
        
        # Total Contributions
        contribution_paths = [
            './/IRS990/CYContributionsGrantsAmt',
            './/IRS990/ContributionsGrantsAmt',
            './/ReturnData/IRS990/CYContributionsGrantsAmt',
            './/ReturnData/IRS990/ContributionsGrantsAmt',
            './/CYContributionsGrantsAmt',
            './/IRS990/TotalContributionsAmt'
        ]
        data['total_contributions'] = find_element_by_paths(root, contribution_paths, ns)
        
        # Print what we found for debugging
        print(f"Year: {data['tax_year']}, Schema: {data['schema_version']}")
        print(f"  Revenue: {data['total_revenue']}")
        print(f"  Expenses: {data['total_expenses']}")
        print(f"  Program Expenses: {data['program_service_expenses']}")
        print(f"  Fundraising: {data['fundraising_expenses']}")
        print(f"  Contributions: {data['total_contributions']}")
        
        # Convert numeric values
        for key in ['total_revenue', 'total_expenses', 'program_service_expenses', 
                   'fundraising_expenses', 'total_contributions']:
            if data[key]:
                try:
                    data[key] = float(data[key])
                except ValueError:
                    data[key] = None
        
        return data
    
    except Exception as e:
        print(f"Error extracting financial data: {str(e)}")
        return {
            'tax_year': None,
            'schema_version': 'Error',
            'total_revenue': None,
            'total_expenses': None,
            'program_service_expenses': None,
            'fundraising_expenses': None,
            'total_contributions': None
        }

def calculate_efficiency_metrics(data):
    """Calculate program efficiency and fundraising efficiency metrics."""
    if data['total_expenses'] and data['program_service_expenses'] and data['total_expenses'] > 0:
        data['program_efficiency'] = data['program_service_expenses'] / data['total_expenses']
    else:
        data['program_efficiency'] = None
    
    if data['fundraising_expenses'] and data['total_contributions'] and data['total_contributions'] > 0:
        data['fundraising_efficiency'] = data['fundraising_expenses'] / data['total_contributions']
    else:
        data['fundraising_efficiency'] = None
    
    return data

def analyze_directory(directory_path):
    """Analyze all XML files in the given directory and extract financial data."""
    results = []
    
    for filename in sorted(os.listdir(directory_path)):
        if filename.endswith('.xml'):
            file_path = os.path.join(directory_path, filename)
            print(f"\nProcessing {filename}...")
            
            # Extract the XML content
            xml_content = extract_real_xml_content(file_path)
            
            if xml_content:
                # Extract financial data
                data = extract_financial_data(xml_content)
                data['filename'] = filename
                
                # Calculate efficiency metrics
                data = calculate_efficiency_metrics(data)
                
                results.append(data)
            else:
                print(f"  Could not extract XML content from {filename}")
    
    return results

def generate_financial_report(results):
    """Generate a financial report with efficiency metrics."""
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(results)
    
    # Fill NaN values with 'N/A' for display purposes
    df_display = df.copy()
    
    # Sort by tax year
    if 'tax_year' in df.columns:
        df = df.sort_values(by='tax_year')
        df_display = df_display.sort_values(by='tax_year')
    
    # Create markdown report
    markdown = []
    
    # Table 1: Financial Overview
    markdown.append("**Table 1.** Financial Overview for United Way Worldwide (EIN: 910818971)\n")
    markdown.append("| Tax Year | Schema Version | Total Revenue ($) | Total Expenses ($) | Program Expenses ($) | Fundraising Expenses ($) |")
    markdown.append("|----------|----------------|-----------------|-------------------|---------------------|------------------------|")
    
    for _, row in df_display.iterrows():
        tax_year = row.get('tax_year', 'Unknown')
        if tax_year != 'Unknown' and tax_year is not None:
            markdown.append(
                f"| {tax_year} | {row.get('schema_version', 'Unknown')} | " +
                f"{format_currency(row['total_revenue'])} | " +
                f"{format_currency(row['total_expenses'])} | " +
                f"{format_currency(row['program_service_expenses'])} | " +
                f"{format_currency(row['fundraising_expenses'])} |"
            )
    
    markdown.append("\n")
    
    # Table 2: Efficiency Metrics
    markdown.append("**Table 2.** Efficiency Metrics for United Way Worldwide (EIN: 910818971)\n")
    markdown.append("| Tax Year | Program Efficiency | Fundraising Efficiency |")
    markdown.append("|----------|-------------------|------------------------|")
    
    for _, row in df_display.iterrows():
        tax_year = row.get('tax_year', 'Unknown')
        if tax_year != 'Unknown' and tax_year is not None:
            program_eff = format_percentage(row['program_efficiency']) if 'program_efficiency' in row else 'N/A'
            fundraising_eff = format_percentage(row['fundraising_efficiency']) if 'fundraising_efficiency' in row else 'N/A'
            
            markdown.append(
                f"| {tax_year} | {program_eff} | {fundraising_eff} |"
            )
    
    # Create visualizations
    create_visualizations(df)
    
    return "\n".join(markdown)

def format_currency(value):
    """Format a value as currency."""
    if value is None:
        return "N/A"
    return f"${value:,.2f}"

def format_percentage(value):
    """Format a value as percentage."""
    if value is None:
        return "N/A"
    return f"{value:.2%}"

def create_visualizations(df):
    """Create and save visualizations of the financial data."""
    # Ensure the directory exists
    os.makedirs('visualizations', exist_ok=True)
    
    # Clean up data for plotting - remove rows with missing essential data
    df_plot = df.copy()
    
    # Only include rows with tax year data
    df_plot = df_plot[df_plot['tax_year'].notna()]
    
    if len(df_plot) == 0:
        print("No data available for visualizations")
        return
    
    # Sort by tax year
    df_plot['tax_year'] = df_plot['tax_year'].astype(str)
    df_plot = df_plot.sort_values(by='tax_year')
    
    # Plot 1: Financial Overview
    plt.figure(figsize=(12, 6))
    
    # Create line chart for revenue and expenses
    if df_plot['total_revenue'].notna().any():
        plt.plot(df_plot['tax_year'], df_plot['total_revenue'], marker='o', label='Total Revenue')
    
    if df_plot['total_expenses'].notna().any():
        plt.plot(df_plot['tax_year'], df_plot['total_expenses'], marker='s', label='Total Expenses')
    
    if df_plot['program_service_expenses'].notna().any():
        plt.plot(df_plot['tax_year'], df_plot['program_service_expenses'], marker='^', label='Program Expenses')
    
    plt.title('United Way Worldwide Financial Overview')
    plt.xlabel('Tax Year')
    plt.ylabel('Amount ($)')
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    
    # Save the figure
    plt.savefig('visualizations/financial_overview.png', dpi=300)
    plt.close()
    
    # Plot 2: Efficiency Metrics
    if 'program_efficiency' in df_plot.columns or 'fundraising_efficiency' in df_plot.columns:
        plt.figure(figsize=(12, 6))
        
        # Filter out rows with missing efficiency metrics
        df_eff = df_plot[df_plot['program_efficiency'].notna() | df_plot['fundraising_efficiency'].notna()]
        
        if not df_eff.empty:
            # Create line chart for efficiency metrics
            if 'program_efficiency' in df_eff.columns and df_eff['program_efficiency'].notna().any():
                plt.plot(df_eff['tax_year'], df_eff['program_efficiency'], marker='o', label='Program Efficiency')
            
            if 'fundraising_efficiency' in df_eff.columns and df_eff['fundraising_efficiency'].notna().any():
                plt.plot(df_eff['tax_year'], df_eff['fundraising_efficiency'], marker='s', label='Fundraising Efficiency')
            
            plt.title('United Way Worldwide Efficiency Metrics')
            plt.xlabel('Tax Year')
            plt.ylabel('Efficiency Ratio')
            plt.xticks(rotation=45)
            plt.legend()
            plt.grid(True, linestyle='--', alpha=0.7)
            plt.tight_layout()
            
            # Save the figure
            plt.savefig('visualizations/efficiency_metrics.png', dpi=300)
        plt.close()

# Main execution
if __name__ == "__main__":
    directory_path = "910818971"
    
    # Check for required packages
    try:
        import bs4
    except ImportError:
        print("BeautifulSoup is required. Please install it with: pip install beautifulsoup4")
        exit(1)
    
    try:
        import pandas
    except ImportError:
        print("Pandas is required. Please install it with: pip install pandas")
        exit(1)
    
    try:
        import matplotlib
    except ImportError:
        print("Matplotlib is required. Please install it with: pip install matplotlib")
        exit(1)
    
    results = analyze_directory(directory_path)
    
    if results:
        markdown_report = generate_financial_report(results)
        
        # Save to file
        output_file = "910818971_financial_analysis.md"
        with open(output_file, "w") as f:
            f.write(markdown_report)
        
        print(f"\nAnalysis complete. Results saved to {output_file}")
        print(f"Visualizations saved to the 'visualizations' directory")
    else:
        print("\nNo valid results were obtained. Check for errors above.")