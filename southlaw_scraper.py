import requests
import pdfplumber
import json
from io import BytesIO
import re

url = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
response = requests.get(url)
pdf_file = BytesIO(response.content)

records = []
current_county = None

def is_county_heading(line):
    line = line.strip()
    if not line:
        return False
    # Remove any special characters like green line artifacts
    cleaned = re.sub(r"[^A-Za-z.\-\s]", "", line).strip()
    # Must not contain numbers or $
    if re.search(r"[\d$]", cleaned):
        return False
    # Should be mostly uppercase
    upper_ratio = sum(1 for c in cleaned if c.isupper()) / max(len(cleaned), 1)
    if upper_ratio < 0.6:  # at least 60% uppercase
        return False
    # Usually short
    if len(cleaned) > 40:
        return False
    return True

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        for raw_line in text.split("\n"):
            line = raw_line.strip()

            # Detect county headings
            if is_county_heading(line):
                current_county = re.sub(r"\s+", " ", line).strip()
                print(f"Detected county: {current_county}")
                continue

            # Skip headers
            if "Property Address" in line:
                continue

            # Parse property rows
            parts = line.split()
            if len(parts) < 10:
                continue

            firm_file = parts[-1]
            civil_case = parts[-2]
            sale_city = parts[-3]
            bid = parts[-4]
            continued = parts[-5]
            sale_time = parts[-6]
            sale_date = parts[-7]
            zip_code = parts[-8]
            city = parts[-9]
            address = " ".join(parts[:-9])

            records.append({
                "county": current_county if current_county else "Unknown",
                "property_address": address,
                "property_city": city,
                "property_zip": zip_code,
                "sale_date": sale_date,
                "sale_time": sale_time,
                "continued_date_time": continued,
                "opening_bid": bid,
                "sale_location_city": sale_city,
                "civil_case_no": civil_case,
                "firm_file": firm_file
            })

# Save JSON
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} records.")
