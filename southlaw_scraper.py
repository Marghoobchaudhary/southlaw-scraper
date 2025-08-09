import requests
import pdfplumber
import json
from io import BytesIO

url = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
response = requests.get(url)
pdf_file = BytesIO(response.content)

data = []
with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        table = page.extract_table()
        if not table:
            continue
        headers = table[0]
        for row in table[1:]:
            if not any(row):
                continue
            data.append(dict(zip(headers, row)))

with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)

print("Scraping complete. Data saved to sales_report.json")
