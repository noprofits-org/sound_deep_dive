from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
from pathlib import Path
import json
import tempfile
from pyvirtualdisplay import Display

# Target EINs
TARGET_EINS = {
    "91-0818971": "Sound"
}

# Create directories for data
DATA_DIR = Path("nonprofit_data")
DATA_DIR.mkdir(exist_ok=True)

def setup_driver():
    """Set up the Selenium WebDriver with virtual display."""
    # Create a virtual display
    display = Display(visible=0, size=(1920, 1080))
    display.start()
    
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-notifications")
    
    # Create a unique user data directory
    temp_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={temp_dir}")
    
    # Add these options for headless environment
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")  # Run in headless mode
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver, display

def get_propublica_org_url(ein):
    """Convert EIN to ProPublica Nonprofit Explorer URL."""
    # ProPublica formats EINs with a hyphen after the first 2 digits
    if '-' not in ein:
        ein = ein[:2] + '-' + ein[2:]
    return f"https://projects.propublica.org/nonprofits/organizations/{ein}"

def download_xml_files(driver, ein, org_name):
    """Download XML files for an organization using Selenium."""
    org_url = get_propublica_org_url(ein)
    
    print(f"\nProcessing {org_name} (EIN: {ein})...")
    print(f"Navigating to: {org_url}")
    
    # Create a directory for this organization
    clean_ein = ein.replace('-', '')
    org_dir = DATA_DIR / clean_ein
    org_dir.mkdir(exist_ok=True)
    
    # Navigate to the organization page
    driver.get(org_url)
    time.sleep(3)  # Wait for page to load
    
    # Look for XML links
    xml_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'xml') or contains(text(), 'XML')]")
    
    org_results = {}
    
    if xml_links:
        print(f"Found {len(xml_links)} potential XML links")
        
        # Open each XML link in a new tab
        for i, link in enumerate(xml_links):
            try:
                # Try to extract year from link text or surrounding elements
                link_text = link.text
                year = None
                
                # Look for a year in the link text
                if any(year_str in link_text for year_str in ["2020", "2021", "2022", "2023", "2024"]):
                    for year_str in ["2020", "2021", "2022", "2023", "2024"]:
                        if year_str in link_text:
                            year = year_str
                            break
                
                # If no year in link text, try to find it in parent or sibling elements
                if not year:
                    parent_text = link.find_element(By.XPATH, "./..").text
                    for year_str in ["2020", "2021", "2022", "2023", "2024"]:
                        if year_str in parent_text:
                            year = year_str
                            break
                
                if not year:
                    # If we still can't find the year, use the index as a fallback
                    year = f"unknown_{i+1}"
                
                print(f"Processing link for year {year}: {link_text}")
                
                # Open link in a new tab
                driver.execute_script("window.open(arguments[0]);", link.get_attribute('href'))
                
                # Switch to the new tab
                driver.switch_to.window(driver.window_handles[-1])
                
                # Wait for the page to load
                time.sleep(5)
                
                # Check if this is an XML page or a page with an iframe
                if "xml" in driver.current_url.lower():
                    # Direct XML page
                    xml_content = driver.page_source
                    xml_file_path = org_dir / f"{year}_filing.xml"
                    
                    with open(xml_file_path, 'w', encoding='utf-8') as f:
                        f.write(xml_content)
                    
                    org_results[year] = {
                        "status": "downloaded",
                        "file_path": str(xml_file_path)
                    }
                    print(f"Downloaded XML for {year} to {xml_file_path}")
                else:
                    # Look for iframe or download link
                    iframe = driver.find_elements(By.TAG_NAME, "iframe")
                    if iframe:
                        iframe_src = iframe[0].get_attribute("src")
                        driver.get(iframe_src)
                        time.sleep(3)
                        
                        xml_content = driver.page_source
                        xml_file_path = org_dir / f"{year}_filing.xml"
                        
                        with open(xml_file_path, 'w', encoding='utf-8') as f:
                            f.write(xml_content)
                        
                        org_results[year] = {
                            "status": "downloaded",
                            "file_path": str(xml_file_path)
                        }
                        print(f"Downloaded XML from iframe for {year} to {xml_file_path}")
                    else:
                        # Look for download link
                        download_links = driver.find_elements(By.XPATH, "//a[contains(@href, 's3') or contains(@href, 'xml')]")
                        if download_links:
                            driver.get(download_links[0].get_attribute("href"))
                            time.sleep(3)
                            
                            xml_content = driver.page_source
                            xml_file_path = org_dir / f"{year}_filing.xml"
                            
                            with open(xml_file_path, 'w', encoding='utf-8') as f:
                                f.write(xml_content)
                            
                            org_results[year] = {
                                "status": "downloaded",
                                "file_path": str(xml_file_path)
                            }
                            print(f"Downloaded XML from download link for {year} to {xml_file_path}")
                        else:
                            org_results[year] = {
                                "status": "failed",
                                "reason": "Could not find XML content"
                            }
                            print(f"Failed to find XML content for {year}")
                
                # Close the tab and switch back to the main tab
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                
                # Be nice to the server
                time.sleep(2)
                
            except Exception as e:
                print(f"Error processing link: {e}")
                # Make sure we're back on the main tab
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[0])
    else:
        print("No XML links found for this organization")
    
    return org_results

def main():
    driver, display = setup_driver()
    summary_data = {}
    
    try:
        for ein, org_name in TARGET_EINS.items():
            org_results = download_xml_files(driver, ein, org_name)
            
            summary_data[ein] = {
                "name": org_name,
                "results": org_results
            }
            
            # Be nice to the server between organizations
            time.sleep(3)
        
    finally:
        # Save the summary
        summary_path = DATA_DIR / "download_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary_data, f, indent=2)
        
        print(f"\nDownload summary saved to {summary_path}")
        
        # Close the browser and display
        driver.quit()
        display.stop()

if __name__ == "__main__":
    main()