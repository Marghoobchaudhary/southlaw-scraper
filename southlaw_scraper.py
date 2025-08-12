import requests, pdfplumber, json, re, sys
from io import BytesIO
from datetime import datetime

URL = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
OUT = "sales_report.json"

# ---------------- Missouri counties (plus independent city) ----------------
COUNTY_CANON = [
    "Adair","Andrew","Atchison","Audrain","Barry","Barton","Bates","Benton","Bollinger","Boone",
    "Buchanan","Butler","Caldwell","Callaway","Camden","Cape Girardeau","Carroll","Carter","Cass",
    "Cedar","Chariton","Christian","Clark","Clay","Clinton","Cole","Cooper","Crawford","Dade",
    "Dallas","Daviess","DeKalb","Dent","Douglas","Dunklin","Franklin","Gasconade","Gentry","Greene",
    "Grundy","Harrison","Henry","Hickory","Holt","Howard","Howell","Iron","Jackson","Jasper",
    "Jefferson","Johnson","Knox","Laclede","Lafayette","Lawrence","Lewis","Lincoln","Linn",
    "Livingston","Macon","Madison","Maries","Marion","McDonald","Mercer","Miller","Mississippi",
    "Moniteau","Monroe","Montgomery","Morgan","New Madrid","Newton","Nodaway","Oregon","Osage",
    "Ozark","Pemiscot","Perry","Pettis","Phelps","Pike","Platte","Polk","Pulaski","Putnam",
    "Ralls","Randolph","Ray","Reynolds","Ripley","St. Charles","St. Clair","Ste. Genevieve",
    "St. Francois","St. Louis","Saline","Schuyler","Scotland","Scott","Shannon","Shelby",
    "Stoddard","Stone","Sullivan","Taney","Texas","Vernon","Warren","Washington","Wayne",
    "Webster","Worth","Wright","St. Louis City",
]
def _norm(s: str) -> str:
    s = s.strip().lower()
    s = s.replace(".", "")
    s = re.sub(r"\s+", " ", s)
    s = s.replace("saint ", "st ")
    return s
COUNTY_SET_NORM = {_norm(c) for c in COUNTY_CANON}
COUNTY_SET_NORM.update({"city of st louis"})  # common variant

# ---------------- Regex / heuristics ----------------
zip_re   = re.compile(r"^\d{5}(?:-\d{4})?$")
date_re  = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$", re.ASCII)
time_re  = re.compile(r"^\d{1,2}:\d{2}(?:AM|PM)$", re.IGNORECASE)
money_re = re.compile(r"^\$?[\d,]+(?:\.\d{2})?$")
placeholder_set = {"—", "-", "None", "TBD", "N/A"}

ignore_headings = {
    "foreclosure sales report: missouri",
    "property address property city property zip sale date sale time continued date/time opening bid sale location(city) civil case no. firm file#",
    "information reported as of",
}

def is_county_heading_text(s: str) -> bool:
    s_stripped = s.strip()
    if not s_stripped or re.search(r"\d", s_stripped):
        return False
    if not re.fullmatch(r"[A-Za-z.\-'\s]+", s_stripped):
        return False
    words = s_stripped.split()
    if not (1 <= len(words) <= 3 or s_stripped.lower().startswith("city of ")):
        return False
    return _norm(s_stripped) in COUNTY_SET_NORM

def starts_with_number(text: str) -> bool:
    return bool(re.match(r"^\d+\b", text))

def fetch_pdf_bytes(url: str) -> bytes:
    resp = requests.get(url, timeout=45)
    resp.raise_for_status()
    return resp.content

def parse_pdf(content: bytes):
    records = []
    current_county = None

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

            # 2) Merge soft-wrapped fragments (e.g., "Neighbor", "Village")
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
                    and not is_county_heading_text(cur)    # not a real county
                    and merged and starts_with_number(prv) # previous looks like address row
                    and next_starts_with_zip(nxt)          # next begins with ZIP
                ):
                    merged[-1] = prv + " " + cur
                    i += 1
                    continue

                merged.append(cur)
                i += 1

            # 3) Parse rows with robust right-anchored logic
            for line_clean in merged:
                # County header (whitelist only)
                if is_county_heading_text(line_clean):
                    current_county = line_clean.strip()
                    continue

                parts = line_clean.split()
                if len(parts) < 8:
                    continue

                # Must have a sale time token
                time_idxs = [idx for idx, tok in enumerate(parts) if time_re.match(tok)]
                if not time_idxs:
                    continue
                ti = time_idxs[-1]        # last time token
                di = ti - 1               # date immediately before
                if di < 0 or not date_re.match(parts[di]):
                    continue

                # Rightmost ZIP before sale_date
                zi_candidates = [idx for idx, tok in enumerate(parts[:di]) if zip_re.match(tok)]
                if not zi_candidates:
                    continue
                zi = zi_candidates[-1]

                # --- Parse from the far right ---
                idx = len(parts) - 1
                firm_file = parts[idx]; idx -= 1
                civil_case = parts[idx]; idx -= 1

                # sale_location_city: multi-word; gather tokens until we hit opening_bid token
                # opening_bid looks like money or placeholder (TBD, —, etc.)
                j = idx
                while j >= 0 and not (money_re.match(parts[j]) or parts[j] in placeholder_set):
                    j -= 1
                if j < 0:
                    # couldn't find opening bid; skip this line
                    continue
                opening_bid = parts[j]
                # city is tokens from j+1 to idx (inclusive)
                sale_location_city = " ".join(parts[j+1:idx+1]) if j+1 <= idx else ""
                idx = j - 1  # move left of opening bid

                # continued date/time:
                continued = ""
                if idx >= 1 and date_re.match(parts[idx-1]) and time_re.match(parts[idx]):
                    # pattern: DATE TIME
                    continued = parts[idx-1] + " " + parts[idx]
                    idx -= 2
                elif idx >= 0 and (parts[idx] in placeholder_set or date_re.match(parts[idx])):
                    # single placeholder or a single date without time
                    continued = parts[idx]
                    idx -= 1
                # else: no continued value present

                # City (property) is tokens between ZIP and sale_date (exclusive of date/time)
                city = " ".join(parts[zi-1:di-1]) if zi-1 >= 0 else ""
                # Address is everything before that
                address = " ".join(parts[:zi-1]) if zi-1 > 0 else ""

                # Sanity: address should start with number
                if not starts_with_number(address):
                    continue

                record = {
                    "county": current_county or "N/A",
                    "property_address": address,
                    "property_city": city,
                    "property_zip": parts[zi],
                    "sale_date": parts[di],
                    "sale_time": parts[ti],
                    "continued_date_time": continued,          # <-- now robust
                    "opening_bid": opening_bid,
                    "sale_location_city": sale_location_city,  # multi-word handled
                    "civil_case_no": civil_case,
                    "firm_file": firm_file,
                    "scraped_at": datetime.utcnow().isoformat() + "Z",
                }
                records.append(record)

    return records

def main():
    try:
        pdf_bytes = fetch_pdf_bytes(URL)
    except Exception as e:
        print(f"Failed to download PDF: {e}", file=sys.stderr)
        sys.exit(1)

    records = parse_pdf(pdf_bytes)

    # Save to JSON (overwrite)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4)

    # Print a quick preview so you can see continued date/time values
    print(f"\nExtracted {len(records)} records → {OUT}\n")
    for r in records[:10]:
        print(
            f"[{r['county']}] {r['property_address']}, {r['property_city']} {r['property_zip']} | "
            f"Sale: {r['sale_date']} {r['sale_time']} | Continued: {r['continued_date_time'] or '—'} | "
            f"Bid: {r['opening_bid']} | Location: {r['sale_location_city']} | "
            f"Civil: {r['civil_case_no']} | File: {r['firm_file']}"
        )

if __name__ == "__main__":
    main()
