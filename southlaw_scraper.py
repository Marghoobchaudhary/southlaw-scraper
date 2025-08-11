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

# Loosened county detection
county_pattern = re.compile(r"^(City of\s+)?[A-Za-z.\-'\s]+$")

# Words to skip
ignore_headings = [
    "information reported as of",
    "sale date",
    "property address"
]

sale_date_pattern = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        prev_line = None  # to hold address if split over two lines

        for line in text.split("\n"):
            line_clean = line.strip()

            # Skip obvious junk lines
            if any(kw in line_clean.lower() for kw in ignore_headings):
                continue

            # Detect county name
            if county_pattern.match(line_clean) and not re.search(r"\d", line_clean):
                current_county = line_clean.strip()
                prev_line = None
                continue

            if "Property Address" in line_clean:
                continue

            parts = line_clean.split()

            # If this line contains a sale date but too few parts, merge with previous line
            if sale_date_pattern.search(line_clean) and len(parts) < 10 and prev_line:
                line_clean = prev_line + " " + line_clean
                parts = line_clean.split()

            if len(parts) < 10:
                prev_line = line_clean  # store for possible merge with next line
                continue

            prev_line = None  # reset after successful parse

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
