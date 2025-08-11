import requests
import pdfplumber
import json
from io import BytesIO
import re

# PDF URL
url = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
response = requests.get(url)
pdf_file = BytesIO(response.content)

records = []
current_county = None

# Loosened county detection:
county_pattern = re.compile(r"^(City of\s+)?[A-Za-z.\-'\s]+$")

ignore_headings = [
    "information reported as of",
    "sale date",
    "property address"
]

def is_county_line(line):
    """Return True if line looks like a county heading, not a property row."""
    if not county_pattern.match(line):
        return False
    if re.search(r"\d", line):  # county names shouldn't have digits
        return False
    if re.search(r"\b\d{5}\b", line):  # ZIP code present → not a county
        return False
    if re.search(r"\d{1,2}/\d{1,2}/\d{4}", line):  # date present → not a county
        return False
    if "$" in line:  # bid amount present → not a county
        return False
    # Optional: prevent very short names like "St Louis" from being mistaken unless preceded by "County"
    if len(line.split()) <= 3 and "county" not in line.lower() and not line.lower().startswith("city of"):
        return False
    return True

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            line_clean = line.strip()

            if any(kw in line_clean.lower() for kw in ignore_headings):
                continue

            # Detect county heading using stricter function
            if is_county_line(line_clean):
                current_county = line_clean.strip()
                print(f"Detected county: {current_county}")
                continue

            if "Property Address" in line_clean:
                continue

            parts = line_clean.split()
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
                "county": current_county if current_county else "N/A",
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

# Save extracted records to JSON
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} records.")
