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

county_pattern = re.compile(r"^(City of\s+)?[A-Za-z.\-'\s]+$")  # County names only
ignore_headings = [
    "information reported as of",
    "sale date",
    "property address"
]

def looks_like_property(line):
    """Check if a line contains a ZIP and a date → likely a property row"""
    has_zip = bool(re.search(r"\b\d{5}\b", line))
    has_date = bool(re.search(r"\d{1,2}/\d{1,2}/\d{4}", line))
    return has_zip and has_date

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        merged_lines = []
        buffer = ""

        # Merge multi-line property rows
        for line in lines:
            if looks_like_property(line):
                if buffer:
                    merged_lines.append(buffer + " " + line)
                    buffer = ""
                else:
                    merged_lines.append(line)
            else:
                # Might be part of an address
                if buffer:
                    buffer += " " + line
                else:
                    buffer = line
        if buffer:
            merged_lines.append(buffer)

        for line_clean in merged_lines:
            # Skip obvious junk lines
            if any(kw in line_clean.lower() for kw in ignore_headings):
                continue

            # Detect county heading (only if not a property row)
            if county_pattern.match(line_clean) and not re.search(r"\d", line_clean):
                if not looks_like_property(line_clean):
                    current_county = line_clean.strip()
                    print(f"Detected county: {current_county}")
                    continue

            parts = line_clean.split()

            # Find ZIP position
            zip_idx = None
            for i, token in enumerate(parts):
                if re.fullmatch(r"\d{5}", token):
                    zip_idx = i
                    break

            if zip_idx is None or zip_idx + 7 >= len(parts):
                continue

            address = " ".join(parts[:zip_idx - 1])
            city = " ".join(parts[zip_idx - 1:zip_idx])
            zip_code = parts[zip_idx]
            sale_date = parts[zip_idx + 1]
            sale_time = parts[zip_idx + 2]
            continued = parts[zip_idx + 3]
            bid = parts[zip_idx + 4]
            sale_city = parts[zip_idx + 5]
            civil_case = parts[zip_idx + 6]
            firm_file = parts[zip_idx + 7]

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

# Save to JSON
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} records.")
