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

# ZIP to County mapping for overrides
stl_zip_to_county = {
    # St. Louis County
    "63005": "St. Louis",
    "63011": "St. Louis",
    "63017": "St. Louis",
    "63021": "St. Louis",
    "63121": "St. Louis",
    "63122": "St. Louis",
    "63123": "St. Louis",
    "63124": "St. Louis",
    "63125": "St. Louis",
    "63126": "St. Louis",
    "63127": "St. Louis",
    "63128": "St. Louis",
    "63129": "St. Louis",
    "63130": "St. Louis",
    "63131": "St. Louis",
    "63132": "St. Louis",
    "63133": "St. Louis",
    "63134": "St. Louis",
    "63135": "St. Louis",
    "63136": "St. Louis",
    "63137": "St. Louis",
    "63138": "St. Louis",
    "63140": "St. Louis",
    "63141": "St. Louis",
    "63143": "St. Louis",
    "63144": "St. Louis",
    "63146": "St. Louis",

    # City of St. Louis
    "63101": "City of St. Louis",
    "63102": "City of St. Louis",
    "63103": "City of St. Louis",
    "63104": "City of St. Louis",
    "63106": "City of St. Louis",
    "63107": "City of St. Louis",
    "63108": "City of St. Louis",
    "63109": "City of St. Louis",
    "63110": "City of St. Louis",
    "63111": "City of St. Louis",
    "63112": "City of St. Louis",
    "63113": "City of St. Louis",
    "63115": "City of St. Louis",
    "63116": "City of St. Louis",
    "63118": "City of St. Louis",
    "63120": "City of St. Louis",
    "63139": "City of St. Louis",
    "63147": "City of St. Louis",
}

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            # Detect county headings (allow periods)
            if re.match(r"^[A-Z\s.]+$", line.strip()) and len(line.strip()) > 3:
                current_county = line.strip().title()
                continue

            # Skip header rows
            if "Property Address" in line:
                continue

            # Split row by spaces
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

            # If ZIP matches St. Louis or City of St. Louis, override county
            county = stl_zip_to_county.get(zip_code, current_county)

            records.append({
                "county": county,
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
