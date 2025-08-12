import requests, pdfplumber, json, re, sys
from io import BytesIO
from datetime import datetime

PDF_URL = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
OUTPUT_JSON = "sales_report.json"

# --- Missouri counties (plus independent city) ---
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
COUNTY_SET_NORM.update({"city of st louis"})  # common variant in headings

def is_county_heading_text(s: str) -> bool:
    """True if line is a county heading (letters only, 1–3 words, in MO whitelist)."""
    s_stripped = s.strip()
    if not s_stripped or re.search(r"\d", s_stripped):
        return False
    if not re.fullmatch(r"[A-Za-z.\-'\s]+", s_stripped):
        return False
    words = s_stripped.split()
    if not (1 <= len(words) <= 3 or s_stripped.lower().startswith("city of ")):
        return False
    return _norm(s_stripped) in COUNTY_SET_NORM

# --- Regexes / helpers (your working logic) ---
zip_re   = re.compile(r"^\d{5}(?:-\d{4})?$")
date_re  = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$", re.ASCII)  # 2- or 4-digit year
time_re  = re.compile(r"^\d{1,2}:\d{2}\s?(?:[APap]\.?M\.?)$", re.ASCII)  # "10:30 AM", "10:30AM", etc.
money_re = re.compile(r"^\$?[\d,]+(?:\.\d{2})?$")
placeholder_set = {"—", "-", "none", "tbd", "n/a"}

# Header lines to ignore (lowercased compare)
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

def find_opening_from_right(parts):
    """
    From the right: firm_file, civil_case, then find opening_bid token (money or placeholder).
    Return (opening_bid_index, sale_location_city_string, left_index_before_opening, civil_case, firm_file, opening_bid).
    """
    idx = len(parts) - 1
    firm_file = parts[idx]; idx -= 1
    civil_case = parts[idx]; idx -= 1

    j = idx
    while j >= 0 and not (money_re.match(parts[j]) or parts[j].lower() in placeholder_set):
        j -= 1
    if j < 0:
        return None
    opening_bid = parts[j]
    sale_location_city = " ".join(parts[j+1:idx+1]) if j+1 <= idx else ""
    left_idx = j - 1
    return j, sale_location_city, left_idx, civil_case, firm_file, opening_bid

def parse_pdf(content: bytes):
    records = []
    current_county = None  # <-- will be set from county headings

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

            # 2) Merge soft-wrapped fragments (e.g., "Neighbor", "Village") into prior address line
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
                    and not is_county_heading_text(cur)    # don't merge county headings
                    and merged and starts_with_number(prv) # previous looks like address row
                    and next_starts_with_zip(nxt)          # next begins with ZIP
                ):
                    merged[-1] = prv + " " + cur
                    i += 1
                    continue

                merged.append(cur)
                i += 1

            # 3) Parse rows using ZIP→Sale pair, Continued between Sale and Opening Bid, plus county headings
            for line_clean in merged:
                # County heading: update current county and continue
                if is_county_heading_text(line_clean):
                    current_county = line_clean.strip()
                    continue

                parts = line_clean.split()
                if len(parts) < 8:
                    continue

                # Locate rightmost ZIP
                zi_candidates = [idx for idx, tok in enumerate(parts) if zip_re.match(tok)]
                if not zi_candidates:
                    continue
                zi = zi_candidates[-1]

                # From ZIP forward, find the FIRST date/time pair -> Sale Date/Time
                di = ti = None
                k = zi + 1
                while k < len(parts):
                    if date_re.match(parts[k]):
                        # time can be immediately next or next-next (rare spacing)
                        if k + 1 < len(parts) and time_re.match(parts[k+1]):
                            di, ti = k, k+1
                            break
                        elif k + 2 < len(parts) and time_re.match(parts[k+2]):
                            di, ti = k, k+2
                            break
                    k += 1
                if di is None or ti is None:
                    continue  # couldn't find the sale date/time pair

                # From far right, get Opening Bid / Sale Location(City) / Civil / File
                res = find_opening_from_right(parts)
                if not res:
                    continue
                ob_idx, sale_location_city, left_of_ob, civil_case, firm_file, opening_bid = res

                # Search for Continued Date/Time BETWEEN sale time and opening bid
                cont = None
                p = ti + 1
                while p <= left_of_ob:
                    tok = parts[p]
                    low = tok.lower().rstrip(".")
                    if low in {"continued", "cont"}:
                        p += 1
                        continue
                    if date_re.match(tok):
                        if p + 1 <= left_of_ob and time_re.match(parts[p+1]):
                            cont = tok + " " + parts[p+1]
                            p += 2
                            break
                        else:
                            cont = tok
                            p += 1
                            break
                    if low in placeholder_set:
                        cont = tok
                        p += 1
                        break
                    p += 1
                if cont is None:
                    cont = "—"

                # Property City is tokens between ZIP and Sale Date (exclusive)
                property_city = " ".join(parts[zi-1:di-1]) if zi-1 >= 0 else ""
                # Property Address is everything before that
                property_address = " ".join(parts[:zi-1]) if zi-1 > 0 else ""

                # Sanity: address should start with a number
                if not starts_with_number(property_address):
                    continue

                record = {
                    "County": current_county or "N/A",      # <-- add county
                    "Property Address": property_address,
                    "Property City": property_city,
                    "Property Zip": parts[zi],
                    "Sale Date": parts[di],
                    "Sale Time": parts[ti],
                    "Continued Date/Time": cont,
                    "Opening Bid": opening_bid,
                    "Sale Location(City)": sale_location_city,
                    "Civil Case No.": civil_case,
                    "Firm File#": firm_file,
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
    # Quick preview
    for r in rows[:10]:
        print(
            f"[{r['County']}] {r['Property Address']} | {r['Property City']} {r['Property Zip']} | "
            f"Sale: {r['Sale Date']} {r['Sale Time']} | Continued: {r['Continued Date/Time']} | "
            f"Bid: {r['Opening Bid']} | Loc: {r['Sale Location(City)']} | "
            f"Civil: {r['Civil Case No.']} | File: {r['Firm File#']}"
        )

if __name__ == "__main__":
    main()
