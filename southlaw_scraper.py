import requests, pdfplumber, json, re, sys
from io import BytesIO
from datetime import datetime

PDF_URL = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
OUTPUT_JSON = "sales_report.json"

# --- Regexes / helpers ---
zip_re   = re.compile(r"^\d{5}(?:-\d{4})?$")
date_re  = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$", re.ASCII)
time_re  = re.compile(r"^\d{1,2}:\d{2}(?:AM|PM)$", re.IGNORECASE)
money_re = re.compile(r"^\$?[\d,]+(?:\.\d{2})?$")
placeholder_set = {"—", "-", "None", "TBD", "N/A"}

# Header lines to ignore
ignore_headings = {
    "foreclosure sales report: missouri",
    "property address property city property zip sale date sale time continued date/time opening bid sale location(city) civil case no. firm file#",
    "information reported as of",
}

def starts_with_number(text: str) -> bool:
    return bool(re.match(r"^\d+\b", text))

def fetch_pdf_bytes(url: str) -> bytes:
    resp = requests.get(url, timeout=45)
    resp.raise_for_status()
    return resp.content

def parse_pdf(content: bytes):
    records = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            raw = page.extract_text() or ""
            lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]

            # 1) Remove obvious headers
            cleaned = []
            for ln in lines:
                if any(h in ln.lower() for h in ignore_headings):
                    continue
                cleaned.append(ln)

            # 2) Merge soft-wrapped fragments that belong to a property row
            # Heuristic: a fragment with NO digits that follows an address-like line,
            # and the NEXT line begins with a ZIP -> it's part of the same row (e.g., "Neighbor", "Village").
            merged = []
            i = 0
            while i < len(cleaned):
                cur = cleaned[i]
                nxt = cleaned[i+1] if i+1 < len(cleaned) else ""
                prv = merged[-1] if merged else ""

                def next_starts_with_zip(text):
                    first = (text.split() or [""])[0]
                    return bool(zip_re.match(first))

                if (
                    not re.search(r"\d", cur)              # no digits in fragment
                    and merged and starts_with_number(prv) # previous looks like address row
                    and next_starts_with_zip(nxt)          # next begins with ZIP
                ):
                    merged[-1] = prv + " " + cur
                    i += 1
                    continue

                merged.append(cur)
                i += 1

            # 3) Parse each merged line into columns
            for line_clean in merged:
                parts = line_clean.split()
                if len(parts) < 8:
                    continue

                # Find Sale Time (right-anchored)
                time_idxs = [idx for idx, tok in enumerate(parts) if time_re.match(tok)]
                if not time_idxs:
                    continue
                ti = time_idxs[-1]        # last time token
                di = ti - 1               # date immediately before
                if di < 0 or not date_re.match(parts[di]):
                    continue

                # Rightmost ZIP before Sale Date
                zi_candidates = [idx for idx, tok in enumerate(parts[:di]) if zip_re.match(tok)]
                if not zi_candidates:
                    continue
                zi = zi_candidates[-1]

                # From far-right: Firm File#, Civil Case No., Opening Bid, Sale Location(City), (optional) Continued Date/Time
                idx = len(parts) - 1
                firm_file = parts[idx]; idx -= 1
                civil_case = parts[idx]; idx -= 1

                # Find Opening Bid token (money or placeholder), everything between that and the two IDs is Sale Location(City)
                j = idx
                while j >= 0 and not (money_re.match(parts[j]) or parts[j] in placeholder_set):
                    j -= 1
                if j < 0:
                    # couldn't find opening bid; skip
                    continue
                opening_bid = parts[j]
                sale_location_city = " ".join(parts[j+1:idx+1]) if j+1 <= idx else ""
                idx = j - 1  # move left of opening bid

                # Continued Date/Time can be:
                #  - DATE TIME (two tokens)
                #  - one placeholder or a lone DATE
                #  - absent
                continued = ""
                if idx >= 1 and date_re.match(parts[idx-1]) and time_re.match(parts[idx]):
                    continued = parts[idx-1] + " " + parts[idx]
                    idx -= 2
                elif idx >= 0 and (parts[idx] in placeholder_set or date_re.match(parts[idx])):
                    continued = parts[idx]
                    idx -= 1
                # else: leave empty

                # Property City: tokens between ZIP and Sale Date (exclusive)
                property_city = " ".join(parts[zi-1:di-1]) if zi-1 >= 0 else ""
                # Property Address: everything before the city tokens
                property_address = " ".join(parts[:zi-1]) if zi-1 > 0 else ""

                # Basic sanity: address should start with a number
                if not starts_with_number(property_address):
                    continue

                record = {
                    "Property Address": property_address,
                    "Property City": property_city,
                    "Property Zip": parts[zi],
                    "Sale Date": parts[di],
                    "Sale Time": parts[ti],
                    "Continued Date/Time": continued,
                    "Opening Bid": opening_bid,
                    "Sale Location(City)": sale_location_city,
                    "Civil Case No.": civil_case,
                    "Firm File#": firm_file,
                    # Optional: keep when row was scraped (helpful for GitHub runs)
                    "scraped_at": datetime.utcnow().isoformat() + "Z",
                }
                records.append(record)

    return records

def main():
    try:
        pdf_bytes = fetch_pdf_bytes(PDF_URL)
    except Exception as e:
        print(f"Failed to download PDF: {e}", file=sys.stderr)
        sys.exit(1)

    rows = parse_pdf(pdf_bytes)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=4)

    print(f"Extracted {len(rows)} records -> {OUTPUT_JSON}")
    # Optional: print a few lines to verify "Continued Date/Time" is captured
    for r in rows[:10]:
        print(
            f"{r['Property Address']} | {r['Property City']} {r['Property Zip']} | "
            f"Sale: {r['Sale Date']} {r['Sale Time']} | Continued: {r['Continued Date/Time'] or '—'} | "
            f"Bid: {r['Opening Bid']} | Loc: {r['Sale Location(City)']} | "
            f"Civil: {r['Civil Case No.']} | File: {r['Firm File#']}"
        )

if __name__ == "__main__":
    main()
