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

# Common phrases to ignore even if they look like headings
ignore_headings = {
    "trustee’s sale", "trustees sale", "information reported as of",
    "continued", "property address", "sale date", "firm file"
}

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            line_clean = line.strip()

            # Detect county headings (Title Case, not too short, not in ignore list)
            if (
                len(line_clean) > 2
                and re.match(r"^[A-Z][a-z]+(?:\s[A-Z][a-z]+)*$", line_clean)
                and line_clean.lower() not in ignore_headings
            ):
                current_county = line_clean
                print(f"Detected county: {current_county}")
                continue

            # Skip header rows
            if "Property Address" in line_clean:
                continue

            # Split row into columns
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
            address = " ".join(parts[0:-9])

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
