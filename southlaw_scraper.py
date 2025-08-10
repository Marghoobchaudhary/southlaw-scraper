import requests
import pdfplumber
import json
from io import BytesIO
import re

# Validation regex
date_re = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
zip_re = re.compile(r"^\d{5}$")
price_re = re.compile(r"^\$?\d[\d,]*\.?\d*$")
case_no_re = re.compile(r"^\d+$")
file_no_re = re.compile(r"^\d+$")

url = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
response = requests.get(url)
pdf_file = BytesIO(response.content)

records = []
current_county = None

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            # Detect county headings
            if re.match(r"^[A-Z\s.]+$", line.strip()) and len(line.strip()) > 3:
                current_county = line.strip().title()
                continue

            if "Property Address" in line:
                continue

            parts = line.strip().split()
            if len(parts) < 10:
                continue

            # Parse from right with validation
            idx = len(parts) - 1
            firm_file = parts[idx] if file_no_re.match(parts[idx]) else None
            idx -= 1
            civil_case = parts[idx] if case_no_re.match(parts[idx]) else None
            idx -= 1
            sale_city = parts[idx]  # May not validate, cities can be words
            idx -= 1
            opening_bid = parts[idx] if price_re.match(parts[idx]) or parts[idx] == "N/A" else None
            idx -= 1
            continued_date_time = parts[idx] if date_re.match(parts[idx]) or parts[idx] == "N/A" else None
            idx -= 1
            sale_time = parts[idx] if re.match(r"^\d{1,2}:\d{2}[AP]M$", parts[idx]) else None
            idx -= 1
            sale_date = parts[idx] if date_re.match(parts[idx]) else None
            idx -= 1
            property_zip = parts[idx] if zip_re.match(parts[idx]) else None
            idx -= 1
            property_city = parts[idx]
            address = " ".join(parts[0:idx])

            # Ensure all critical fields are valid before saving
            if not (current_county and sale_date and property_zip and property_city and firm_file):
                continue

            records.append({
                "county": current_county,
                "property_address": address,
                "property_city": property_city,
                "property_zip": property_zip,
                "sale_date": sale_date,
                "sale_time": sale_time,
                "continued_date_time": continued_date_time,
                "opening_bid": opening_bid,
                "sale_location_city": sale_city,
                "civil_case_no": civil_case,
                "firm_file": firm_file
            })

with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} validated records.")

