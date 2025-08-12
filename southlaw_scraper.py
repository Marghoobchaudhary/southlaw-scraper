import requests, pdfplumber, json, re, time, logging
from io import BytesIO
from datetime import datetime
import schedule  # pip install schedule

# ------------------ Config ------------------
PDF_URL = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
OUTPUT_JSON = "sales_report.json"

# ------------------ Logging -----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ------------------ Regex/Heuristics --------
# Sale-time and date detectors
zip_re = re.compile(r"^\d{5}(?:-\d{4})?$")
date_re = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$", re.ASCII)
time_re = re.compile(r"^\d{1,2}:\d{2}(?:AM|PM)$", re.IGNORECASE)

ignore_headings = {
    "foreclosure sales report: missouri",
    "property address property city property zip sale date sale time continued date/time opening bid sale location(city) civil case no. firm file#",
    "information reported as of",
}

def is_county_heading(s: str) -> bool:
    # Known special-case
    if s.strip().startswith("City of "):
        return True
    # Must be letters/space/.'- only, title-ish, and short (1–3 words)
    if re.search(r"\d", s):
        return False
    if not re.fullmatch(r"[A-Za-z.\-'\s]+", s):
        return False
    words = s.strip().split()
    return 1 <= len(words) <= 3  # catches "Boone", "St. Louis", "St. Francois", etc.

# ------------------ Scrape + Parse ---------
def extract_once():
    logging.info("Fetching PDF...")
    try:
        resp = requests.get(PDF_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logging.error(f"Failed to download PDF: {e}")
        return

    pdf_file = BytesIO(resp.content)
    records = []
    current_county = None

    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                raw = page.extract_text() or ""
                lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
                # 1) Normalize/skip obvious headers
                cleaned = []
                for ln in lines:
                    low = ln.lower()
                    if any(h in low for h in ignore_headings):
                        continue
                    cleaned.append(ln)

                # 2) Pre-merge soft-wrapped fragments that belong to the SAME row.
                # Heuristic: a line with NO digits that is NOT a county heading and:
                #   (a) previous line looks like an address line (starts with a number), and
                #   (b) the NEXT line begins with a ZIP code
                merged = []
                i = 0
                while i < len(cleaned):
                    cur = cleaned[i]
                    nxt = cleaned[i+1] if i+1 < len(cleaned) else ""
                    prv = merged[-1] if merged else ""

                    def starts_with_number(text): return bool(re.match(r"^\d+\b", text))
                    def next_starts_with_zip(text):
                        first = (text.split() or [""])[0]
                        return bool(zip_re.match(first))

                    if (
                        not re.search(r"\d", cur)              # no digits in current fragment
                        and not is_county_heading(cur)         # not a county
                        and merged and starts_with_number(prv) # previous looks like an address row
                        and next_starts_with_zip(nxt)          # next begins with ZIP
                    ):
                        # merge this fragment into previous line (e.g., "Neighbor", "Village")
                        merged[-1] = prv + " " + cur
                        i += 1
                        continue

                    merged.append(cur)
                    i += 1

                # 3) Detect counties + parse rows
                for line_clean in merged:
                    # County headings
                    if is_county_heading(line_clean):
                        current_county = line_clean.strip()
                        continue

                    # Likely a data row if it has at least a ZIP and a date+time pair
                    parts = line_clean.split()
                    if len(parts) < 10:
                        continue

                    try:
                        # locate sale_date/time by scanning from right
                        ti = max(i for i, tok in enumerate(parts) if time_re.match(tok))
                        di = ti - 1
                        if di < 0 or not date_re.match(parts[di]):
                            continue

                        # ZIP should be somewhere before date; find the rightmost ZIP before di
                        zi_candidates = [i for i, tok in enumerate(parts[:di]) if zip_re.match(tok)]
                        if not zi_candidates:
                            continue
                        zi = zi_candidates[-1]

                        firm_file = parts[-1]
                        civil_case = parts[-2]
                        sale_city = parts[-3]
                        bid = parts[-4]
                        continued = parts[-5]
                        sale_time = parts[ti]
                        sale_date = parts[di]
                        zip_code = parts[zi]
                        city = " ".join(parts[zi-1:di-1]) if zi-1 >= 0 else ""
                        address = " ".join(parts[:zi-1]) if zi-1 > 0 else ""

                        # basic sanity: address should start with a number
                        if not re.match(r"^\d+\b", address):
                            continue

                        records.append({
                            "county": current_county or "N/A",
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
                            "scraped_at": datetime.utcnow().isoformat() + "Z"
                        })
                    except ValueError:
                        # e.g., no time in line
                        continue
    except Exception as e:
        logging.error(f"Failed to parse PDF: {e}")
        return

    # Save (overwrite) JSON
    try:
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4)
        logging.info(f"Extracted {len(records)} records. Saved to {OUTPUT_JSON}")
    except Exception as e:
        logging.error(f"Failed to write JSON: {e}")

# ------------------ Scheduler --------------
def main():
    # run once immediately
    extract_once()

    # then every 5 minutes
    schedule.every(5).minutes.do(extract_once)
    logging.info("Scheduler started: running every 5 minutes.")

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
