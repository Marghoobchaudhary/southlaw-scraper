import requests
import pdfplumber
import json
from io import BytesIO
import re

# ---------- Helper: county list + normalization ----------
MO_COUNTIES = [
    "Adair","Andrew","Atchison","Audrain","Barry","Barton","Bates","Benton",
    "Bollinger","Boone","Buchanan","Butler","Caldwell","Callaway","Camden",
    "Cape Girardeau","Carroll","Carter","Cass","Cedar","Chariton","Christian",
    "Clark","Clay","Clinton","Cole","Cooper","Crawford","Dade","Dallas",
    "Daviess","DeKalb","Dent","Douglas","Dunklin","Franklin","Gasconade",
    "Gentry","Greene","Grundy","Harrison","Henry","Hickory","Holt","Howard",
    "Howell","Iron","Jackson","Jasper","Jefferson","Johnson","Knox","Laclede",
    "Lafayette","Lawrence","Lewis","Lincoln","Linn","Livingston","Macon",
    "Madison","Maries","Marion","Miller","Mississippi","Moniteau","Monroe",
    "Montgomery","Morgan","New Madrid","Newton","Nodaway","Oregon","Osage",
    "Ozark","Pemiscot","Perry","Pettis","Phelps","Pike","Platte","Polk",
    "Pulaski","Putnam","Ralls","Randolph","Ray","Reynolds","Ripley","Saline",
    "Schuyler","Scotland","Scott","Shannon","Shelby","St. Charles","St. Clair",
    "St. Francois","St. Louis","Ste. Genevieve","Stoddard","Stone","Sullivan",
    "Taney","Texas","Vernon","Warren","Washington","Wayne","Webster","Worth",
    "Wright"
]

# Add the independent city explicitly
MO_COUNTIES.append("City of St. Louis")

# normalization helper
def norm_text(s):
    s = (s or "").strip()
    # lower, remove punctuation except periods (we'll remove them too)
    s = s.lower()
    s = re.sub(r'[^a-z0-9\s]', ' ', s)   # remove punctuation (dots, commas, etc.)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

# Build a normalized map: normalized -> canonical
county_map = {}
for c in MO_COUNTIES:
    k = norm_text(c)
    county_map[k] = c
    # also add a "with county" variant so "st louis county" matches
    county_map[norm_text(c + " county")] = c

# ---------- PDF fetch & parse ----------
url = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
resp = requests.get(url, timeout=60)
resp.raise_for_status()
pdf_file = BytesIO(resp.content)

records = []
current_county = None

# ignore lines that look like table headers or page footers
IGNORE_KEYWORDS = {"information reported as of", "property address", "sale date", "firm file", "continued"}

with pdfplumber.open(pdf_file) as pdf:
    for page_no, page in enumerate(pdf.pages, start=1):
        text = page.extract_text()
        if not text:
            continue

        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            low = line.lower()
            if any(kw in low for kw in IGNORE_KEYWORDS):
                # skip header/footer lines
                continue

            # Normalize the line and try to match a county name
            nline = norm_text(line)

            matched = False
            # direct exact match
            if nline in county_map:
                current_county = county_map[nline]
                print(f"[page {page_no}] Detected county (exact): {current_county}")
                continue

            # try to match if the normalized county name appears at start of line
            for nk, canonical in county_map.items():
                if nline == nk or nline.startswith(nk + " ") or nk in nline:
                    current_county = canonical
                    print(f"[page {page_no}] Detected county (partial): {current_county}  <-- from line: {line}")
                    matched = True
                    break
            if matched:
                continue

            # If we reach here, the line is not a county heading. Try to parse as a property row.

            # Basic protection: skip obviously short lines that aren't data rows
            parts = line.split()
            if len(parts) < 10:
                continue

            # Extract columns by position (same as your previous logic)
            # caution: this assumes table columns are consistently aligned in the text extraction
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
                "firm_file": firm_file,
                "raw_line": line   # keep raw_line for debugging
            })

# Save output
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=2, ensure_ascii=False)

print(f"Extracted {len(records)} records. Sample counties found: {sorted(set(r['county'] for r in records) )[:10]}")
