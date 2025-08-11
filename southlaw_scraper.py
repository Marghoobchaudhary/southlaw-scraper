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

# Helper: is this line a county heading?
def is_county_heading(line):
    # Trim spaces
    txt = line.strip()
    # Ignore empty lines
    if not txt:
        return False
    # Must be mostly uppercase or capitalized
    if not re.match(r"^[A-Z\s\.\-]+$", txt):
        return False
    # Short enough to be a heading
    if len(txt.split()) > 5:
        return False
    # No dates
    if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", txt):
        return False
    # No zip codes
    if re.search(r"\b\d{5}\b", txt):
        return False
    # No dollar signs
    if "$" in txt:
        return False
    return True

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            # Detect county headings
            if is_county_heading(line):
                current_county = line.strip().title()
                print(f"Detected county: {current_county}")
                continue

            # Skip the table header
            if "Property Address" in line:
                continue

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
