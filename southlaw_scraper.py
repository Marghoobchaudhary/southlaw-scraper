import requests
import pdfplumber
import json
from io import BytesIO
import re

url = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
response = requests.get(url)
pdf_file = BytesIO(response.content)

data = []
current_county = None

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue
        for line in text.split("\n"):
            # County name line (all caps, no numbers)
            if re.match(r"^[A-Z\s]+$" , line.strip()) and len(line.strip()) > 3:
                current_county = line.strip().title()
                continue

            # Skip header lines
            if "Property Address" in line or "Opening Bid" in line:
                continue

            # Data line — just store raw for now
            if re.search(r"\d", line):  # must contain a number
                data.append({
                    "county": current_county,
                    "raw_text": line.strip()
                })

# Save as JSON
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)

print(f"Scraping complete. {len(data)} records found.")
