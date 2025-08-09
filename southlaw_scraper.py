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

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            # Detect county headers (all caps, no digits, longer than 3 chars)
            if re.match(r"^[A-Z\s]+$", line.strip()) and len(line.strip()) > 3:
                current_county = line.strip().title()
                continue

            # Skip column header lines
            if "Property Address" in line:
                continue

            # Try to match data line
            # Regex Explanation:
            #   ^(?P<address>.*?)  -> Property Address (non-greedy)
            #   \s+(?P<city>[A-Za-z.\s]+) -> Property City
            #   \s+(?P<zip>\d{5}) -> Zip Code
            #   \s+(?P<sale_date>\d{1,2}/\d{1,2}/\d{4})
            #   \s+(?P<sale_time>\d{1,2}:\d{2}[APM]+)
            #   \s+(?P<continued>.*?) -> Continued Date/Time (can be N/A)
            #   \s+(?P<bid>.*?) -> Opening Bid (can be N/A)
            #   \s+(?P<sale_city>[A-Za-z.\s]+) -> Sale Location City
            #   \s+(?P<civil_case>\d+) -> Civil Case No
            #   \s+(?P<firm_file>\d+)$ -> Firm File#
            pattern = re.compile(
                r"^(?P<address>.+?)\s+(?P<city>[A-Za-z.\s]+)\s+(?P<zip>\d{5})\s+"
                r"(?P<sale_date>\d{1,2}/\d{1,2}/\d{4})\s+(?P<sale_time>\d{1,2}:\d{2}[APM]+)\s+"
                r"(?P<continued>(?:\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}[APM]+|N/A))\s+"
                r"(?P<bid>.+?)\s+(?P<sale_city>[A-Za-z.\s]+)\s+"
                r"(?P<civil_case>\d+)\s+(?P<firm_file>\d+)$"
            )

            match = pattern.match(line.strip())
            if match:
                record = match.groupdict()
                record["county"] = current_county
                records.append(record)

# Save results
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} records.")
