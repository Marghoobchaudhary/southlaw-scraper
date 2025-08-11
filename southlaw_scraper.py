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
    # Clean up extra spaces
    cleaned = re.sub(r"\s+", " ", line.strip())
    if not cleaned:
        return False
    # No numbers, $ signs, or slashes in county names
    if re.search(r"[\d/$]", cleaned):
        return False
    # County headings are usually short (under 40 chars)
    if len(cleaned) > 40:
        return False
    # All uppercase with optional dots, hyphens, and spaces
    if re.match(r"^[A-Z .\-]+$", cleaned):
        return True
    return False

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            # Detect county headings
            if is_county_heading(line):
                current_county = re.sub(r"\s+", " ", line.strip())  # preserve original casing from PDF
                print(f"Detected county: {current_county}")
                continue

            # Skip header rows
            if "Property Address" in line:
                continue

            # Split row by spaces
            parts = line.strip().split()
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
            address = " ".join(parts[0:-9])

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

# Save to JSON
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} records.")
