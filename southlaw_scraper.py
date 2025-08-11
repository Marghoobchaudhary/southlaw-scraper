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

# Looser county detection:
# - Optional "City of "
# - Allows letters, spaces, periods, apostrophes, and hyphens
# - No digits allowed
county_pattern = re.compile(r"^(City of\s+)?[A-Za-z.\-'\s]+$", re.IGNORECASE)

# Words to skip when scanning headings
ignore_headings = [
    "information reported as of",
    "sale date",
    "property address"
]

def clean_line(line):
    """Remove non-printable characters and normalize spaces."""
    return re.sub(r"[^\x20-\x7E]+", "", line).strip()

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            line_clean = clean_line(line)

            # Skip obvious junk lines
            if any(kw in line_clean.lower() for kw in ignore_headings):
                continue

            # Detect county heading (must not contain digits)
            if not re.search(r"\d", line_clean) and county_pattern.match(line_clean):
                current_county = line_clean.strip()
                print(f"Detected county: {current_county}")
                continue

            # Skip header rows in property table
            if "Property Address" in line_clean:
                continue

            # Split row into parts
            parts = line_clean.split()
            if len(parts) < 10:
                continue

            # Extract columns based on position
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
