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

county_pattern = re.compile(r"^(City of\s+)?[A-Za-z.\-'\s]+$", re.IGNORECASE)

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

            if any(kw in line_clean.lower() for kw in ignore_headings):
                continue

            if not re.search(r"\d", line_clean) and county_pattern.match(line_clean):
                current_county = line_clean.strip()
                continue

            if "Property Address" in line_clean:
                continue

            parts = line_clean.split()

            # Try to detect ZIP (5-digit number) to split reliably
            zip_idx = None
            for i, token in enumerate(parts):
                if re.fullmatch(r"\d{5}", token):
                    zip_idx = i
                    break

            if zip_idx is None:
                continue  # no ZIP code found, skip

            address = " ".join(parts[:zip_idx-1])  # up to city
            city = parts[zip_idx-1]
            zip_code = parts[zip_idx]
            sale_date = parts[zip_idx+1]
            sale_time = parts[zip_idx+2]
            continued = parts[zip_idx+3]
            opening_bid = parts[zip_idx+4]
            sale_location_city = parts[zip_idx+5]
            civil_case_no = parts[zip_idx+6]
            firm_file = parts[zip_idx+7] if len(parts) > zip_idx+7 else ""

            records.append({
                "county": current_county if current_county else "N/A",
                "property_address": address,
                "property_city": city,
                "property_zip": zip_code,
                "sale_date": sale_date,
                "sale_time": sale_time,
                "continued_date_time": continued,
                "opening_bid": opening_bid,
                "sale_location_city": sale_location_city,
                "civil_case_no": civil_case_no,
                "firm_file": firm_file
            })

# Save to JSON
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} records.")
