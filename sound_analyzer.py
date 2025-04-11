import os
import re
import json
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Load the element paths lookup
with open("990_element_paths.json", "r") as f:
    ELEMENT_PATHS = json.load(f)

def extract_real_xml_content(file_path):
    """Extract the actual XML content from HTML files that contain embedded XML."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Try to find the standard Return element
        return_pattern = r'<Return xmlns="http://www\.irs\.gov/efile".*?</Return>'
        match = re.search(return_pattern, content, re.DOTALL)
        if match:
            return match.group(0)
        
        # If that fails, try to extract from a div
        soup = BeautifulSoup(content, 'html.parser')
        source_div = soup.find('div', id='webkit-xml-viewer-source-xml')
        if source_div:
            return_matches = re.findall(return_pattern, str(source_div), re.DOTALL)
            if return_matches:
                return return_matches[0]
        
        print(f"Could not extract XML from {file_path}")
        return None
    
    except Exception as e:
        print(f"Error reading {file_path}: {str(e)}")
        return None

def extract_schema_version(root):
    """Extract schema version from the Return element."""
    return root.get('returnVersion', 'Unknown')

def find_element_by_path(root, path, namespace=None):
    """Find an element using a given path, with namespace handling."""
    try:
        # Try with namespace
        if namespace and '{' not in path:
            ns_path = path.replace('/', '/{' + namespace + '}')
            if not ns_path.startswith('{'):
                ns_path = '{' + namespace + '}' + ns_path
            elem = root.find(ns_path)
            if elem is not None and elem.text:
                return elem.text.strip()
        
        # Try without namespace
        elem = root.find(path)
        if elem is not None and elem.text:
            return elem.text.strip()
        
    except Exception as e:
        pass
    
    return None

def extract_executive_compensation(root, schema_version, namespace=None):
    """Extract executive compensation data for a given form."""
    if schema_version not in ELEMENT_PATHS:
        print(f"Schema version {schema_version} not found in lookup")
        return []
    
    exec_comp_data = []
    
    # Find all Form990PartVIISectionAGrp elements
    person_paths = ELEMENT_PATHS[schema_version].get("PersonNm", [])
    title_paths = ELEMENT_PATHS[schema_version].get("TitleTxt", [])
    hours_paths = ELEMENT_PATHS[schema_version].get("AverageHoursPerWeekRt", [])
    comp_paths = ELEMENT_PATHS[schema_version].get("ReportableCompFromOrgAmt", [])
    other_comp_paths = ELEMENT_PATHS[schema_version].get("OtherCompensationAmt", [])
    
    # Find all Form990PartVIISectionAGrp elements
    section_a_pattern = ".//{*}Form990PartVIISectionAGrp"
    if namespace:
        section_a_pattern = f".//{{{namespace}}}Form990PartVIISectionAGrp"
    
    section_a_elements = root.findall(section_a_pattern)
    
    for section in section_a_elements:
        person_name = find_element_by_path(section, "PersonNm", namespace)
        title = find_element_by_path(section, "TitleTxt", namespace)
        hours = find_element_by_path(section, "AverageHoursPerWeekRt", namespace)
        compensation = find_element_by_path(section, "ReportableCompFromOrgAmt", namespace)
        other_comp = find_element_by_path(section, "OtherCompensationAmt", namespace)
        
        if person_name:
            exec_comp_data.append({
                "name": person_name,
                "title": title or "Unknown",
                "hours": float(hours) if hours and hours.replace('.', '').isdigit() else 0,
                "compensation": float(compensation) if compensation and compensation.replace('.', '').isdigit() else 0,
                "other_compensation": float(other_comp) if other_comp and other_comp.replace('.', '').isdigit() else 0,
                "total_compensation": (
                    float(compensation) if compensation and compensation.replace('.', '').isdigit() else 0
                ) + (
                    float(other_comp) if other_comp and other_comp.replace('.', '').isdigit() else 0
                )
            })
    
    return exec_comp_data

def extract_financial_metrics(root, schema_version, namespace=None):
    """Extract key financial metrics from the form."""
    metrics = {
        "total_revenue": None,
        "total_expenses": None,
        "program_service_expenses": None,
        "fundraising_expenses": None,
        "total_assets": None,
        "total_liabilities": None,
        "employee_count": None,
        "volunteer_count": None,
        "program_service_revenue": None
    }
    
    if schema_version not in ELEMENT_PATHS:
        return metrics
    
    # Map metrics to corresponding paths in the lookup
    path_mappings = {
        "total_revenue": ELEMENT_PATHS[schema_version].get("CYTotalRevenueAmt", []),
        "total_expenses": ELEMENT_PATHS[schema_version].get("CYTotalExpensesAmt", []),
        "program_service_expenses": ELEMENT_PATHS[schema_version].get("TotalProgramServiceExpensesAmt", []),
        "fundraising_expenses": ELEMENT_PATHS[schema_version].get("CYTotalFundraisingExpenseAmt", []),
        "total_assets": ELEMENT_PATHS[schema_version].get("TotalAssetsEOYAmt", []),
        "total_liabilities": ELEMENT_PATHS[schema_version].get("TotalLiabilitiesEOYAmt", []),
        "employee_count": ELEMENT_PATHS[schema_version].get("TotalEmployeeCnt", []),
        "volunteer_count": ELEMENT_PATHS[schema_version].get("TotalVolunteersCnt", []),
        "program_service_revenue": ELEMENT_PATHS[schema_version].get("CYProgramServiceRevenueAmt", [])
    }
    
    # Extract each metric using its paths
    for metric, paths in path_mappings.items():
        for path in paths:
            value = find_element_by_path(root, path, namespace)
            if value:
                try:
                    # Try to convert to float for numerical values
                    metrics[metric] = float(value)
                    break
                except ValueError:
                    metrics[metric] = value
                    break
    
    # Calculate additional metrics if possible
    if metrics["program_service_expenses"] and metrics["total_expenses"] and metrics["total_expenses"] > 0:
        metrics["program_efficiency"] = metrics["program_service_expenses"] / metrics["total_expenses"]
    else:
        metrics["program_efficiency"] = None
        
    if metrics["fundraising_expenses"] and metrics["total_revenue"] and metrics["total_revenue"] > 0:
        metrics["fundraising_efficiency"] = metrics["fundraising_expenses"] / metrics["total_revenue"]
    else:
        metrics["fundraising_efficiency"] = None
    
    return metrics

def extract_mission_and_programs(root, schema_version, namespace=None):
    """Extract mission statement and program descriptions."""
    program_data = {
        "mission": None,
        "programs": []
    }
    
    if schema_version not in ELEMENT_PATHS:
        return program_data
    
    # Find mission statement
    mission_paths = ELEMENT_PATHS[schema_version].get("MissionDesc", [])
    for path in mission_paths:
        mission = find_element_by_path(root, path, namespace)
        if mission:
            program_data["mission"] = mission
            break
    
    # Find program descriptions and expenses
    program_desc_pattern = ".//{*}ProgSrvcAccom"
    expense_pattern = ".//{*}ExpenseAmt"
    
    if namespace:
        program_desc_pattern = f".//{{{namespace}}}ProgSrvcAccom"
        expense_pattern = f".//{{{namespace}}}ExpenseAmt"
    
    # Try to find main program description
    main_desc_element = find_element_by_path(root, "//Desc", namespace)
    main_expense_element = find_element_by_path(root, "//ExpenseAmt", namespace)
    
    if main_desc_element and main_expense_element:
        try:
            expense = float(main_expense_element)
        except (ValueError, TypeError):
            expense = None
            
        program_data["programs"].append({
            "description": main_desc_element,
            "expense": expense
        })
    
    # Find program descriptions in various sections
    for program_num in [2, 3]:
        desc_path = f"//ProgSrvcAccomActy{program_num}Grp/Desc"
        expense_path = f"//ProgSrvcAccomActy{program_num}Grp/ExpenseAmt"
        
        desc = find_element_by_path(root, desc_path, namespace)
        expense_elem = find_element_by_path(root, expense_path, namespace)
        
        if desc:
            try:
                expense = float(expense_elem) if expense_elem else None
            except (ValueError, TypeError):
                expense = None
                
            program_data["programs"].append({
                "description": desc,
                "expense": expense
            })
    
    # Find "other" program descriptions
    other_desc_path = "//ProgSrvcAccomActyOtherGrp/Desc"
    other_expense_path = "//ProgSrvcAccomActyOtherGrp/ExpenseAmt"
    
    other_desc = find_element_by_path(root, other_desc_path, namespace)
    other_expense_elem = find_element_by_path(root, other_expense_path, namespace)
    
    if other_desc:
        try:
            other_expense = float(other_expense_elem) if other_expense_elem else None
        except (ValueError, TypeError):
            other_expense = None
            
        program_data["programs"].append({
            "description": other_desc,
            "expense": other_expense
        })
    
    return program_data

def analyze_files(directory_path):
    """Analyze all XML files in the directory and extract comprehensive data."""
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
            
            # Get schema version
            schema_version = extract_schema_version(root)
            print(f"  Schema version: {schema_version}")
            
            # Extract tax year
            tax_year = None
            tax_year_paths = [
                './/TaxPeriodEndDt',
                './/TaxYr',
                './/ReturnHeader/TaxPeriodEndDt',
                './/ReturnHeader/TaxYr'
            ]
            
            for path in tax_year_paths:
                tax_year_value = find_element_by_path(root, path, ns)
                if tax_year_value:
                    # Extract year from YYYY-MM-DD format if needed
                    if '-' in tax_year_value:
                        tax_year = tax_year_value.split('-')[0]
                    else:
                        tax_year = tax_year_value
                    break
            
            print(f"  Tax Year: {tax_year}")
            
            # Extract executive compensation
            exec_comp = extract_executive_compensation(root, schema_version, ns)
            print(f"  Found {len(exec_comp)} executives")
            
            # Extract financial metrics
            metrics = extract_financial_metrics(root, schema_version, ns)
            print(f"  Revenue: ${metrics['total_revenue']:,.2f}" if metrics['total_revenue'] else "  Revenue: N/A")
            
            # Extract mission and programs
            programs = extract_mission_and_programs(root, schema_version, ns)
            
            # Combine all data
            result = {
                "filename": filename,
                "tax_year": tax_year,
                "schema_version": schema_version,
                "executives": exec_comp,
                "financials": metrics,
                "mission_and_programs": programs
            }
            
            results.append(result)
    
    # Sort results by tax year
    results.sort(key=lambda x: x["tax_year"] if x["tax_year"] else "0")
    
    return results

def create_executive_comp_analysis(results):
    """Create executive compensation analysis and visualizations."""
    # Prepare data for executive compensation analysis
    exec_data = []
    
    for result in results:
        tax_year = result["tax_year"]
        if not tax_year:
            continue
            
        for exec_info in result["executives"]:
            if exec_info["total_compensation"] > 0:  # Only include paid positions
                exec_data.append({
                    "year": tax_year,
                    "name": exec_info["name"],
                    "title": exec_info["title"],
                    "compensation": exec_info["compensation"],
                    "other_compensation": exec_info["other_compensation"],
                    "total_compensation": exec_info["total_compensation"],
                    "hours": exec_info["hours"]
                })
    
    if not exec_data:
        print("No executive compensation data found")
        return None
    
    # Convert to DataFrame for analysis
    exec_df = pd.DataFrame(exec_data)
    
    # Find top executives by compensation
    top_execs = exec_df.groupby("name")["total_compensation"].sum().sort_values(ascending=False).head(10).index
    
    # Filter for top executives
    top_exec_df = exec_df[exec_df["name"].isin(top_execs)]
    
    # Create visualization of top executive compensation over time
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
    os.makedirs("visualizations", exist_ok=True)
    plt.savefig("visualizations/executive_compensation_trend.png", dpi=300)
    plt.close()
    
    # Create a stacked bar chart showing compensation components
    plt.figure(figsize=(14, 10))
    
    # Prepare data for stacked bar chart (most recent year for each executive)
    recent_exec_data = top_exec_df.sort_values("year").groupby("name").tail(1)
    recent_exec_data = recent_exec_data.sort_values("total_compensation", ascending=False)
    
    # Create the stacked bar chart
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Plot bars
    bar_width = 0.65
    names = recent_exec_data["name"].tolist()
    
    # Create bars
    ax.bar(names, recent_exec_data["compensation"], width=bar_width, 
           label="Base Compensation", color="steelblue")
    ax.bar(names, recent_exec_data["other_compensation"], width=bar_width, 
           bottom=recent_exec_data["compensation"], label="Other Compensation", color="lightsteelblue")
    
    # Add labels and formatting
    ax.set_title("Executive Compensation Breakdown (Most Recent Year)", fontsize=16)
    ax.set_xlabel("Executive", fontsize=14)
    ax.set_ylabel("Compensation ($)", fontsize=14)
    ax.set_xticklabels(names, rotation=45, ha="right")
    
    # Add total compensation labels on top of bars
    for i, name in enumerate(names):
        row = recent_exec_data[recent_exec_data["name"] == name].iloc[0]
        total = row["total_compensation"]
        ax.text(i, total + 5000, f"${total:,.0f}", 
                ha="center", va="bottom", fontweight="bold")
    
    ax.legend()
    plt.grid(True, linestyle="--", alpha=0.3, axis="y")
    plt.tight_layout()
    
    # Save the plot
    plt.savefig("visualizations/executive_compensation_breakdown.png", dpi=300)
    plt.close()
    
    return exec_df

def create_financial_trend_analysis(results):
    """Create financial trend analysis and visualizations."""
    # Prepare data for financial analysis
    financial_data = []
    
    for result in results:
        tax_year = result["tax_year"]
        if not tax_year:
            continue
            
        metrics = result["financials"]
        financial_data.append({
            "year": tax_year,
            "total_revenue": metrics["total_revenue"],
            "total_expenses": metrics["total_expenses"],
            "program_service_expenses": metrics["program_service_expenses"],
            "fundraising_expenses": metrics["fundraising_expenses"],
            "program_efficiency": metrics["program_efficiency"],
            "fundraising_efficiency": metrics["fundraising_efficiency"],
            "program_service_revenue": metrics["program_service_revenue"],
            "total_assets": metrics["total_assets"],
            "total_liabilities": metrics["total_liabilities"],
            "employee_count": metrics["employee_count"],
            "volunteer_count": metrics["volunteer_count"]
        })
    
    if not financial_data:
        print("No financial data found")
        return None
    
    # Convert to DataFrame for analysis
    fin_df = pd.DataFrame(financial_data)
    
    # Create revenue vs expenses visualization
    plt.figure(figsize=(12, 8))
    
    plt.plot(fin_df["year"], fin_df["total_revenue"], marker="o", linestyle="-", 
             linewidth=2.5, label="Total Revenue", color="green")
    plt.plot(fin_df["year"], fin_df["total_expenses"], marker="s", linestyle="-", 
             linewidth=2.5, label="Total Expenses", color="red")
    plt.plot(fin_df["year"], fin_df["program_service_expenses"], marker="^", linestyle="--", 
             linewidth=2, label="Program Expenses", color="blue")
    
    plt.title("Revenue vs. Expenses Over Time", fontsize=16)
    plt.xlabel("Year", fontsize=14)
    plt.ylabel("Amount ($)", fontsize=14)
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.legend(fontsize=12)
    plt.xticks(rotation=45)
    
    # Annotate key points
    for idx, row in fin_df.iterrows():
        if idx % 2 == 0:  # Add labels to every other point to avoid crowding
            plt.annotate(f"${row['total_revenue']/1000000:.1f}M", 
                         (row["year"], row["total_revenue"]),
                         textcoords="offset points", xytext=(0,10), 
                         ha='center', fontsize=9)
    
    plt.tight_layout()
    
    # Save the plot
    plt.savefig("visualizations/revenue_expense_trend.png", dpi=300)
    plt.close()
    
    # Create program efficiency visualization
    plt.figure(figsize=(12, 6))
    
    # Calculate program efficiency and management/fundraising percentages
    fin_df["program_pct"] = fin_df["program_service_expenses"] / fin_df["total_expenses"] * 100
    fin_df["non_program_pct"] = 100 - fin_df["program_pct"]
    
    # Create stacked bar chart
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Create stacked bars
    years = fin_df["year"].tolist()
    program_pct = fin_df["program_pct"].tolist()
    non_program_pct = fin_df["non_program_pct"].tolist()
    
    ax.bar(years, program_pct, label="Program Services", color="mediumseagreen")
    ax.bar(years, non_program_pct, bottom=program_pct, 
           label="Administration & Fundraising", color="lightcoral")
    
    # Add percentage labels
    for i, year in enumerate(years):
        # Only add text if percentage is large enough
        if program_pct[i] > 5:
            ax.text(i, program_pct[i]/2, f"{program_pct[i]:.1f}%", 
                    ha="center", va="center", color="white", fontweight="bold")
        if non_program_pct[i] > 5:
            ax.text(i, program_pct[i] + non_program_pct[i]/2, f"{non_program_pct[i]:.1f}%", 
                    ha="center", va="center", color="white", fontweight="bold")
    
    ax.set_title("Program Efficiency Over Time", fontsize=16)
    ax.set_xlabel("Year", fontsize=14)
    ax.set_ylabel("Percentage of Total Expenses", fontsize=14)
    ax.set_ylim(0, 100)
    ax.legend(loc="upper right")
    
    plt.tight_layout()
    
    # Save the plot
    plt.savefig("visualizations/program_efficiency.png", dpi=300)
    plt.close()
    
    # Create organization growth visualization
    plt.figure(figsize=(12, 8))
    
    # Create line for assets and liabilities
    fig, ax1 = plt.subplots(figsize=(12, 6))
    
    # Plot assets and liabilities
    ax1.plot(fin_df["year"], fin_df["total_assets"], marker="o", linestyle="-", 
             linewidth=2, label="Total Assets", color="darkblue")
    ax1.plot(fin_df["year"], fin_df["total_liabilities"], marker="s", linestyle="-", 
             linewidth=2, label="Total Liabilities", color="darkred")
    
    ax1.set_xlabel("Year", fontsize=14)
    ax1.set_ylabel("Amount ($)", fontsize=14)
    ax1.tick_params(axis="y")
    
    # Create a second y-axis for employee count
    ax2 = ax1.twinx()
    ax2.plot(fin_df["year"], fin_df["employee_count"], marker="^", linestyle="--", 
             linewidth=2, label="Employees", color="darkgreen")
    ax2.set_ylabel("Number of Employees", fontsize=14)
    ax2.tick_params(axis="y")
    
    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    
    plt.title("Organizational Growth Over Time", fontsize=16)
    plt.grid(True, linestyle="--", alpha=0.3)
    plt.tight_layout()
    
    # Save the plot
    plt.savefig("visualizations/organization_growth.png", dpi=300)
    plt.close()
    
    return fin_df

def generate_report(results, exec_df=None, fin_df=None):
    """Generate a comprehensive report of findings."""
    report = []
    
    # Add a title and introduction
    report.append("# Sound (EIN: 91-0818971) - Nonprofit Financial Analysis\n")
    
    # Extract mission statement from the most recent filing
    latest_filing = results[-1]
    mission = latest_filing["mission_and_programs"]["mission"]
    
    report.append("## Organization Overview\n")
    if mission:
        report.append(f"**Mission Statement:** {mission}\n")
    
    # Add financial overview
    report.append("## Financial Performance Summary\n")
    
    # Create financial summary table
    report.append("### Financial Metrics Over Time\n")
    report.append("| Year | Total Revenue | Total Expenses | Program Expenses | Program Efficiency | Total Assets | Total Liabilities |")
    report.append("|------|--------------|----------------|------------------|-------------------|--------------|-------------------|")
    
    for result in results:
        year = result["tax_year"]
        if not year:
            continue
            
        fin = result["financials"]
        revenue = f"${fin['total_revenue']:,.2f}" if fin['total_revenue'] else "N/A"
        expenses = f"${fin['total_expenses']:,.2f}" if fin['total_expenses'] else "N/A"
        program_exp = f"${fin['program_service_expenses']:,.2f}" if fin['program_service_expenses'] else "N/A"
        program_eff = f"{fin['program_efficiency']*100:.1f}%" if fin['program_efficiency'] else "N/A"
        assets = f"${fin['total_assets']:,.2f}" if fin['total_assets'] else "N/A"
        liabilities = f"${fin['total_liabilities']:,.2f}" if fin['total_liabilities'] else "N/A"
        
        report.append(f"| {year} | {revenue} | {expenses} | {program_exp} | {program_eff} | {assets} | {liabilities} |")
    
    report.append("\n")
    
    # Add executive compensation section
    report.append("## Executive Compensation Analysis\n")
    
    # Create a table of top compensated executives from the most recent year
    report.append("### Top Compensated Executives (Most Recent Year)\n")
    
    if exec_df is not None:
        recent_year = exec_df["year"].max()
        recent_execs = exec_df[exec_df["year"] == recent_year]
        recent_execs_sorted = recent_execs.sort_values("total_compensation", ascending=False)
        
        report.append("| Name | Title | Base Compensation | Other Compensation | Total Compensation |")
        report.append("|------|-------|-------------------|-------------------|-------------------|")
        
        for _, row in recent_execs_sorted.head(10).iterrows():
            name = row["name"]
            title = row["title"]
            comp = f"${row['compensation']:,.2f}" if pd.notnull(row['compensation']) else "$0.00"
            other = f"${row['other_compensation']:,.2f}" if pd.notnull(row['other_compensation']) else "$0.00"
            total = f"${row['total_compensation']:,.2f}" if pd.notnull(row['total_compensation']) else "$0.00"
            
            report.append(f"| {name} | {title} | {comp} | {other} | {total} |")
    else:
        report.append("No executive compensation data available for analysis.")
    
    report.append("\n")
    
    # Add program descriptions
    report.append("## Program Services Description\n")
    
    for result in sorted(results, key=lambda x: x["tax_year"] if x["tax_year"] else "0", reverse=True):
        year = result["tax_year"]
        if not year:
            continue
            
        programs = result["mission_and_programs"]["programs"]
        if programs:
            report.append(f"### {year} Program Services\n")
            
            for i, program in enumerate(programs, 1):
                desc = program["description"]
                expense = program["expense"]
                
                expense_str = f"(${expense:,.2f})" if expense else ""
                report.append(f"**Program {i}** {expense_str}\n")
                report.append(f"{desc}\n\n")
    
    report.append("\n")
    
    # Add link to visualizations
    report.append("## Visualizations\n")
    report.append("The following visualizations have been generated in the 'visualizations' directory:\n\n")
    report.append("1. Executive Compensation Trends\n")
    report.append("2. Revenue and Expenses Over Time\n")
    report.append("3. Program Efficiency Metrics\n")
    report.append("4. Organizational Growth Indicators\n")
    
    return "\n".join(report)

def main():
    # Directory containing XML files
    directory_path = "nonprofit_data/910818971"
    
    # Create output directory for visualizations
    os.makedirs("visualizations", exist_ok=True)
    
    # Process all XML files
    results = analyze_files(directory_path)
    
    if not results:
        print("No valid results found. Check the file paths and formats.")
        return
    
    # Generate executive compensation analysis
    exec_df = create_executive_comp_analysis(results)
    
    # Generate financial trend analysis
    fin_df = create_financial_trend_analysis(results)
    
    # Generate comprehensive report
    report = generate_report(results, exec_df, fin_df)
    
    # Save the report
    with open("sound_nonprofit_analysis.md", "w") as f:
        f.write(report)
    
    print("\nAnalysis complete!")
    print(f"Report saved to sound_nonprofit_analysis.md")
    print(f"Visualizations saved to the 'visualizations' directory")

if __name__ == "__main__":
    main()