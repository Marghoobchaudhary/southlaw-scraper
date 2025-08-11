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

county_pattern = re.compile(r"^(City of\s+)?[A-Za-z.\-'\s]+$", re.IGNORECASE)

ignore_headings = [
    "information reported as of",
    "sale date",
    "property address"
]

def clean_line(line):
    return re.sub(r"[^\x20-\x7E]+", "", line).strip()

def is_zip(token):
    return re.fullmatch(r"\d{5}", token) is not None

def is_sale_line(line):
    # Looks for date format M/D/YYYY at start
    return bool(re.match(r"\d{1,2}/\d{1,2}/\d{4}", line))

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        lines = [clean_line(l) for l in text.split("\n") if clean_line(l)]

        i = 0
        while i < len(lines):
            line = lines[i]

            if any(kw in line.lower() for kw in ignore_headings):
                i += 1
                continue

            if not re.search(r"\d", line) and county_pattern.match(line):
                current_county = line.strip()
                i += 1
                continue

            if "Property Address" in line:
                i += 1
                continue

            parts = line.split()

            # If this looks like an address ending in ZIP but no sale date after it
            if len(parts) >= 3 and is_zip(parts[-1]) and (i+1 < len(lines)) and is_sale_line(lines[i+1]):
                # Merge with next line
                line = line + " " + lines[i+1]
                i += 1  # skip next line because we've merged
                parts = line.split()

            # Find ZIP index
            zip_idx = None
            for idx, token in enumerate(parts):
                if is_zip(token):
                    zip_idx = idx
                    break
            if zip_idx is None:
                i += 1
                continue

            # Must have enough tokens after ZIP to get all sale info
            if len(parts) < zip_idx + 8:
                i += 1
                continue

            address = " ".join(parts[:zip_idx-1])
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

            i += 1

with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} records.")
