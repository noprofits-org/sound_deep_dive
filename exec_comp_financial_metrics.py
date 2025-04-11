import os
import re
import json
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
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

def extract_text_from_path(root, path, namespace=None):
    """Extract text from a specific path with namespace handling."""
    if namespace:
        ns_path = path.replace('/', '/{' + namespace + '}')
        if not ns_path.startswith('{'):
            ns_path = '{' + namespace + '}' + ns_path
        
        # Try to find element with namespace
        parts = ns_path.split('/')
        current = root
        
        for part in parts:
            if not part:  # Skip empty parts
                continue
                
            found = False
            for child in current:
                if child.tag == part:
                    current = child
                    found = True
                    break
            
            if not found:
                return None
        
        return current.text.strip() if current.text else None
    
    # Try a different approach for finding elements
    parts = path.split('/')
    if parts[0] == '':  # Remove empty first part if path starts with /
        parts = parts[1:]
    
    # Try to find the element by navigating through parts
    current = root
    for part in parts:
        found = False
        for child in current:
            tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if tag_name == part:
                current = child
                found = True
                break
        
        if not found:
            return None
    
    return current.text.strip() if current.text else None

def extract_elements_by_tag(root, tag_name, namespace=None):
    """Find all elements with a specific tag name."""
    results = []
    
    # If namespace is provided, create the full tag
    if namespace:
        ns_tag = f"{{{namespace}}}{tag_name}"
    else:
        ns_tag = tag_name
    
    # Recursive function to search all elements
    def _find_elements(element):
        # Check if this element's tag matches
        if '}' in element.tag:
            current_tag = element.tag.split('}')[-1]
        else:
            current_tag = element.tag
            
        if current_tag == tag_name:
            results.append(element)
        
        # Check all children
        for child in element:
            _find_elements(child)
    
    _find_elements(root)
    return results

def extract_tax_year(root, namespace=None):
    """Extract tax year using multiple methods."""
    # Method 1: Try TaxPeriodEndDt
    tax_period_elements = extract_elements_by_tag(root, "TaxPeriodEndDt", namespace)
    if tax_period_elements:
        date_str = tax_period_elements[0].text.strip()
        if date_str and "-" in date_str:
            return date_str.split("-")[0]  # Extract year from YYYY-MM-DD
        return date_str
    
    # Method 2: Try TaxYr
    tax_yr_elements = extract_elements_by_tag(root, "TaxYr", namespace)
    if tax_yr_elements:
        return tax_yr_elements[0].text.strip()
    
    # Method 3: Try to find year-like text in ReturnHeader
    header_elements = extract_elements_by_tag(root, "ReturnHeader", namespace)
    if header_elements:
        header_text = ET.tostring(header_elements[0], encoding='unicode')
        year_match = re.search(r'20\d{2}', header_text)
        if year_match:
            return year_match.group(0)
    
    return None

def extract_executive_compensation(root, namespace=None):
    """Extract executive compensation information."""
    executives = []
    
    # Find Form990PartVIISectionAGrp elements
    section_elements = extract_elements_by_tag(root, "Form990PartVIISectionAGrp", namespace)
    
    for section in section_elements:
        exec_data = {}
        
        # Find PersonNm
        person_elements = extract_elements_by_tag(section, "PersonNm", namespace)
        if person_elements and person_elements[0].text:
            exec_data["name"] = person_elements[0].text.strip()
        else:
            continue  # Skip if no name found
        
        # Find TitleTxt
        title_elements = extract_elements_by_tag(section, "TitleTxt", namespace)
        exec_data["title"] = title_elements[0].text.strip() if title_elements and title_elements[0].text else "Unknown"
        
        # Find compensation
        comp_elements = extract_elements_by_tag(section, "ReportableCompFromOrgAmt", namespace)
        if comp_elements and comp_elements[0].text:
            try:
                exec_data["compensation"] = float(comp_elements[0].text.strip())
            except (ValueError, TypeError):
                exec_data["compensation"] = 0
        else:
            exec_data["compensation"] = 0
        
        # Find other compensation
        other_comp_elements = extract_elements_by_tag(section, "OtherCompensationAmt", namespace)
        if other_comp_elements and other_comp_elements[0].text:
            try:
                exec_data["other_compensation"] = float(other_comp_elements[0].text.strip())
            except (ValueError, TypeError):
                exec_data["other_compensation"] = 0
        else:
            exec_data["other_compensation"] = 0
        
        # Calculate total
        exec_data["total_compensation"] = exec_data["compensation"] + exec_data["other_compensation"]
        
        executives.append(exec_data)
    
    return executives

def extract_financial_metrics(root, namespace=None):
    """Extract key financial metrics."""
    metrics = {
        "total_revenue": None,
        "total_expenses": None,
        "program_service_expenses": None,
        "fundraising_expenses": None,
        "total_assets": None,
        "total_liabilities": None
    }
    
    # Try to find CYTotalRevenueAmt
    revenue_elements = extract_elements_by_tag(root, "CYTotalRevenueAmt", namespace)
    if revenue_elements and revenue_elements[0].text:
        try:
            metrics["total_revenue"] = float(revenue_elements[0].text.strip())
        except (ValueError, TypeError):
            pass
    
    # Try to find CYTotalExpensesAmt
    expense_elements = extract_elements_by_tag(root, "CYTotalExpensesAmt", namespace)
    if expense_elements and expense_elements[0].text:
        try:
            metrics["total_expenses"] = float(expense_elements[0].text.strip())
        except (ValueError, TypeError):
            pass
    
    # Try to find TotalProgramServiceExpensesAmt
    program_elements = extract_elements_by_tag(root, "TotalProgramServiceExpensesAmt", namespace)
    if program_elements and program_elements[0].text:
        try:
            metrics["program_service_expenses"] = float(program_elements[0].text.strip())
        except (ValueError, TypeError):
            pass
    
    # Try to find CYTotalFundraisingExpenseAmt or FundraisingAmt
    fundraising_elements = extract_elements_by_tag(root, "CYTotalFundraisingExpenseAmt", namespace)
    if not fundraising_elements:
        fundraising_elements = extract_elements_by_tag(root, "FundraisingAmt", namespace)
    
    if fundraising_elements and fundraising_elements[0].text:
        try:
            metrics["fundraising_expenses"] = float(fundraising_elements[0].text.strip())
        except (ValueError, TypeError):
            pass
    
    # Try to find TotalAssetsEOYAmt
    assets_elements = extract_elements_by_tag(root, "TotalAssetsEOYAmt", namespace)
    if assets_elements and assets_elements[0].text:
        try:
            metrics["total_assets"] = float(assets_elements[0].text.strip())
        except (ValueError, TypeError):
            pass
    
    # Try to find TotalLiabilitiesEOYAmt
    liabilities_elements = extract_elements_by_tag(root, "TotalLiabilitiesEOYAmt", namespace)
    if liabilities_elements and liabilities_elements[0].text:
        try:
            metrics["total_liabilities"] = float(liabilities_elements[0].text.strip())
        except (ValueError, TypeError):
            pass
    
    # Calculate program efficiency if possible
    if metrics["program_service_expenses"] and metrics["total_expenses"] and metrics["total_expenses"] > 0:
        metrics["program_efficiency"] = metrics["program_service_expenses"] / metrics["total_expenses"]
    else:
        metrics["program_efficiency"] = None
    
    return metrics

def analyze_files(directory_path):
    """Analyze all XML files in the directory."""
    results = []
    
    for filename in sorted(os.listdir(directory_path)):
        if filename.endswith('.xml'):
            file_path = os.path.join(directory_path, filename)
            print(f"Processing {filename}...")
            
            # Extract XML content
            xml_content = extract_real_xml_content(file_path)
            if not xml_content:
                continue
            
            # Parse XML
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError as e:
                print(f"XML parse error in {filename}: {e}")
                continue
            
            # Determine namespace
            ns = ''
            if '}' in root.tag:
                ns = root.tag.split('}', 1)[0][1:]
            
            # Extract tax year
            tax_year = extract_tax_year(root, ns)
            print(f"  Tax Year: {tax_year}")
            
            # If no tax year found in XML, try to find it in the filename
            if not tax_year:
                year_match = re.search(r'20[0-9]{2}', filename)
                if year_match:
                    tax_year = year_match.group(0)
                    print(f"  Tax Year (from filename): {tax_year}")
            
            # Extract schema version
            schema_version = root.get('returnVersion', 'Unknown')
            print(f"  Schema version: {schema_version}")
            
            # Extract executive compensation
            exec_comp = extract_executive_compensation(root, ns)
            print(f"  Found {len(exec_comp)} executives with compensation data")
            
            # If we found executives, print the highest paid to verify data
            if exec_comp:
                top_exec = sorted(exec_comp, key=lambda x: x["total_compensation"], reverse=True)[0]
                print(f"  Top executive: {top_exec['name']} - ${top_exec['total_compensation']:,.2f}")
            
            # Extract financial metrics
            metrics = extract_financial_metrics(root, ns)
            if metrics["total_revenue"]:
                print(f"  Revenue: ${metrics['total_revenue']:,.2f}")
            
            # Add all to results
            results.append({
                "filename": filename,
                "tax_year": tax_year,
                "schema_version": schema_version,
                "executives": exec_comp,
                "financials": metrics
            })
    
    # Sort results by tax year
    results.sort(key=lambda x: x["tax_year"] if x["tax_year"] else "0")
    
    return results

def create_executive_comp_visualization(results):
    """Create executive compensation visualization."""
    # Only run if we have results with tax years
    valid_results = [r for r in results if r["tax_year"]]
    if not valid_results:
        print("No results with tax years found, skipping visualizations")
        return
    
    # Prepare data for visualization
    exec_data = []
    
    for result in valid_results:
        year = result["tax_year"]
        for exec_info in result["executives"]:
            if exec_info["total_compensation"] > 0:  # Only include paid positions
                exec_data.append({
                    "year": year,
                    "name": exec_info["name"],
                    "title": exec_info["title"],
                    "compensation": exec_info["compensation"],
                    "other_compensation": exec_info.get("other_compensation", 0),
                    "total_compensation": exec_info["total_compensation"]
                })
    
    if not exec_data:
        print("No executive compensation data found, skipping visualizations")
        return
    
    # Convert to DataFrame
    exec_df = pd.DataFrame(exec_data)
    
    # Find top executives by compensation
    top_execs = exec_df.groupby("name")["total_compensation"].sum().nlargest(10).index
    
    # Filter to top executives
    top_exec_df = exec_df[exec_df["name"].isin(top_execs)]
    
    # Create visualization directory
    os.makedirs("visualizations", exist_ok=True)
    
    # Create line plot
    plt.figure(figsize=(12, 8))
    
    # Use different colors for each executive
    palette = sns.color_palette("husl", len(top_execs))
    
    # Create line plot
    sns.lineplot(
        data=top_exec_df,
        x="year",
        y="total_compensation", 
        hue="name",
        marker="o",
        palette=palette
    )
    
    plt.title("Top Executive Compensation Over Time", fontsize=16)
    plt.xlabel("Year", fontsize=14)
    plt.ylabel("Total Compensation ($)", fontsize=14)
    plt.xticks(rotation=45)
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.tight_layout()
    
    # Save the plot
    plt.savefig("visualizations/executive_compensation_trend.png", dpi=300)
    plt.close()
    
    return exec_df

def create_financial_visualization(results):
    """Create financial metrics visualization."""
    # Only run if we have results with tax years
    valid_results = [r for r in results if r["tax_year"]]
    if not valid_results:
        print("No results with tax years found, skipping visualizations")
        return
    
    # Prepare data for visualization
    financial_data = []
    
    for result in valid_results:
        year = result["tax_year"]
        metrics = result["financials"]
        financial_data.append({
            "year": year,
            "total_revenue": metrics["total_revenue"],
            "total_expenses": metrics["total_expenses"],
            "program_service_expenses": metrics["program_service_expenses"],
            "fundraising_expenses": metrics["fundraising_expenses"],
            "program_efficiency": metrics.get("program_efficiency"),
            "total_assets": metrics["total_assets"],
            "total_liabilities": metrics["total_liabilities"]
        })
    
    # Convert to DataFrame
    fin_df = pd.DataFrame(financial_data)
    
    # Skip if no financial data
    if fin_df["total_revenue"].isna().all() or fin_df["total_expenses"].isna().all():
        print("No financial metrics data found, skipping visualizations")
        return
    
    # Create visualization directory
    os.makedirs("visualizations", exist_ok=True)
    
    # Create revenue vs expenses visualization
    plt.figure(figsize=(12, 8))
    
    # Only plot if we have data
    if not fin_df["total_revenue"].isna().all():
        plt.plot(fin_df["year"], fin_df["total_revenue"], marker="o", linestyle="-", 
                linewidth=2.5, label="Total Revenue", color="green")
    
    if not fin_df["total_expenses"].isna().all():
        plt.plot(fin_df["year"], fin_df["total_expenses"], marker="s", linestyle="-", 
                linewidth=2.5, label="Total Expenses", color="red")
    
    if not fin_df["program_service_expenses"].isna().all():
        plt.plot(fin_df["year"], fin_df["program_service_expenses"], marker="^", linestyle="--", 
                linewidth=2, label="Program Expenses", color="blue")
    
    plt.title("Revenue vs. Expenses Over Time", fontsize=16)
    plt.xlabel("Year", fontsize=14)
    plt.ylabel("Amount ($)", fontsize=14)
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.legend(fontsize=12)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save the plot
    plt.savefig("visualizations/revenue_expense_trend.png", dpi=300)
    plt.close()
    
    # Create program efficiency visualization if we have data
    if not fin_df["program_efficiency"].isna().all():
        plt.figure(figsize=(10, 6))
        plt.plot(fin_df["year"], fin_df["program_efficiency"] * 100, marker="o", 
                linestyle="-", linewidth=2.5, color="blue")
        
        plt.title("Program Efficiency Over Time", fontsize=16)
        plt.xlabel("Year", fontsize=14)
        plt.ylabel("Program Efficiency (%)", fontsize=14)
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save the plot
        plt.savefig("visualizations/program_efficiency_trend.png", dpi=300)
        plt.close()
    
    return fin_df

def generate_summary_report(results, exec_df=None, fin_df=None):
    """Generate a summary report of the analysis."""
    # Filter to results with tax years
    valid_results = [r for r in results if r["tax_year"]]
    
    if not valid_results:
        print("No results with tax years found, skipping report")
        return
    
    # Sort by tax year
    valid_results.sort(key=lambda x: x["tax_year"])
    
    # Start the report
    report = []
    report.append("# Sound (EIN: 91-0818971) Financial Analysis Report\n")
    
    # Financial overview
    report.append("## Financial Overview\n")
    report.append("| Year | Total Revenue | Total Expenses | Program Expenses | Program Efficiency | Assets | Liabilities |")
    report.append("|------|--------------|----------------|------------------|-------------------|--------|-------------|")
    
    for result in valid_results:
        year = result["tax_year"]
        fin = result["financials"]
        
        revenue = f"${fin['total_revenue']:,.2f}" if fin['total_revenue'] else "N/A"
        expenses = f"${fin['total_expenses']:,.2f}" if fin['total_expenses'] else "N/A"
        program = f"${fin['program_service_expenses']:,.2f}" if fin['program_service_expenses'] else "N/A"
        efficiency = f"{fin.get('program_efficiency', 0)*100:.1f}%" if fin.get('program_efficiency') else "N/A"
        assets = f"${fin['total_assets']:,.2f}" if fin['total_assets'] else "N/A"
        liabilities = f"${fin['total_liabilities']:,.2f}" if fin['total_liabilities'] else "N/A"
        
        report.append(f"| {year} | {revenue} | {expenses} | {program} | {efficiency} | {assets} | {liabilities} |")
    
    report.append("\n")
    
    # Executive compensation
    report.append("## Executive Compensation\n")
    
    # Get most recent year
    latest_result = valid_results[-1]
    latest_year = latest_result["tax_year"]
    latest_execs = latest_result["executives"]
    
    if latest_execs:
        # Sort by total compensation
        latest_execs.sort(key=lambda x: x["total_compensation"], reverse=True)
        
        report.append(f"### Top Compensated Executives ({latest_year})\n")
        report.append("| Name | Title | Compensation | Other Comp | Total Comp |")
        report.append("|------|-------|--------------|------------|------------|")
        
        for exec_info in latest_execs[:10]:  # Top 10
            name = exec_info["name"]
            title = exec_info["title"]
            comp = f"${exec_info['compensation']:,.2f}" if exec_info['compensation'] else "$0.00"
            other = f"${exec_info.get('other_compensation', 0):,.2f}" if exec_info.get('other_compensation') else "$0.00"
            total = f"${exec_info['total_compensation']:,.2f}" if exec_info['total_compensation'] else "$0.00"
            
            report.append(f"| {name} | {title} | {comp} | {other} | {total} |")
    else:
        report.append("No executive compensation data available.")
    
    report.append("\n")
    
    # Save the report
    report_text = "\n".join(report)
    with open("sound_analysis_report.md", "w") as f:
        f.write(report_text)
    
    print(f"Report saved to sound_analysis_report.md")

def main():
    # Directory containing XML files
    directory_path = "nonprofit_data/910818971"
    
    # Process all XML files
    results = analyze_files(directory_path)
    
    if not results:
        print("No valid results found. Check the file paths and formats.")
        return
    
    # Create executive compensation visualization
    exec_df = create_executive_comp_visualization(results)
    
    # Create financial visualization
    fin_df = create_financial_visualization(results)
    
    # Generate summary report
    generate_summary_report(results, exec_df, fin_df)
    
    # Save consolidated data for further analysis
    with open("sound_analysis_data.json", "w") as f:
        # Convert data to serializable format
        serializable_results = []
        for result in results:
            serializable_result = {
                "filename": result["filename"],
                "tax_year": result["tax_year"],
                "schema_version": result["schema_version"],
                "executives": result["executives"],
                "financials": {k: float(v) if isinstance(v, (int, float)) and v is not None else v 
                              for k, v in result["financials"].items()}
            }
            serializable_results.append(serializable_result)
        
        json.dump(serializable_results, f, indent=2)
    
    print("Analysis complete!")
    print("Data saved to sound_analysis_data.json")

if __name__ == "__main__":
    main()