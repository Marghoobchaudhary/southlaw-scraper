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

# County heading regex
county_pattern = re.compile(r"^(City of\s+)?[A-Za-z.\-'\s]+$")

def is_possible_county(line):
    """Check if a line could be a county heading."""
    return (
        county_pattern.match(line)
        and not re.search(r"\d", line)  # no numbers
        and len(line.split()) <= 5      # short enough to be a heading
    )

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line_clean = lines[i].strip()

            # Merge broken county names
            if (
                i + 1 < len(lines)
                and len(line_clean.split()) <= 2
                and len(lines[i+1].strip().split()) <= 2
                and is_possible_county(line_clean)
                and is_possible_county(lines[i+1].strip())
            ):
                merged_line = f"{line_clean} {lines[i+1].strip()}"
                if is_possible_county(merged_line):
                    line_clean = merged_line
                    i += 1  # skip the next line since it's merged

            # Detect county heading
            if is_possible_county(line_clean):
                current_county = line_clean
                print(f"Detected county: {current_county}")
                i += 1
                continue

            # Skip headers
            if "Property Address" in line_clean:
                i += 1
                continue

            # Parse property row
            parts = line_clean.split()
            if len(parts) >= 10:
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

            i += 1

# Save to JSON
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} records.")
