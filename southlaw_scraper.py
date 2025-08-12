import requests, pdfplumber, json, re
from io import BytesIO

url = "https://www.southlaw.com/report/Sales_Report_MO.pdf"
pdf_file = BytesIO(requests.get(url).content)

records = []
current_county = None

# ---------------- County whitelist (MO) ----------------
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
    "Webster","Worth","Wright",
    "St. Louis City",  # independent city
]

# Build a normalized set (strip periods, unify saint/ste)
def _norm(s: str) -> str:
    s = s.strip().lower()
    s = s.replace(".", "")
    s = re.sub(r"\s+", " ", s)
    # unify saint -> st; ste -> ste (keep as-is but without dot)
    s = s.replace("saint ", "st ")
    s = s.replace("ste ", "ste ")
    return s

COUNTY_SET_NORM = {_norm(c) for c in COUNTY_CANON}
COUNTY_SET_NORM.update({"city of st louis"})  # common variant in docs

# ---------------- Regex / heuristics ----------------
zip_re = re.compile(r"^\d{5}(?:-\d{4})?$")
date_re = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$", re.ASCII)
time_re = re.compile(r"^\d{1,2}:\d{2}(?:AM|PM)$", re.IGNORECASE)

ignore_headings = {
    "foreclosure sales report: missouri",
    "property address property city property zip sale date sale time continued date/time opening bid sale location(city) civil case no. firm file#",
    "information reported as of",
}

def is_county_heading_text(s: str) -> bool:
    """Text shape + whitelist check."""
    s_stripped = s.strip()
    if not s_stripped or re.search(r"\d", s_stripped):
        return False
    if not re.fullmatch(r"[A-Za-z.\-'\s]+", s_stripped):
        return False
    words = s_stripped.split()
    if not (1 <= len(words) <= 3 or s_stripped.lower().startswith("city of ")):
        return False
    # whitelist
    return _norm(s_stripped) in COUNTY_SET_NORM

def starts_with_number(text: str) -> bool:
    return bool(re.match(r"^\d+\b", text))

with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        raw = page.extract_text() or ""
        lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]

        # 1) Remove obvious headers
        cleaned = []
        for ln in lines:
            low = ln.lower()
            if any(h in low for h in ignore_headings):
                continue
            cleaned.append(ln)

        # 2) Merge soft-wrapped fragments within a row
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
                and not is_county_heading_text(cur)    # not a county (per whitelist)
                and merged and starts_with_number(prv) # previous looks like address row
                and next_starts_with_zip(nxt)          # next begins with ZIP
            ):
                merged[-1] = prv + " " + cur           # stitch "Neighbor", "Village", etc.
                i += 1
                continue

            merged.append(cur)
            i += 1

        # 3) Parse rows; set county only when heading passes whitelist
        for idx, line_clean in enumerate(merged):
            if is_county_heading_text(line_clean):
                current_county = line_clean.strip()
                continue

            parts = line_clean.split()
            if len(parts) < 10:
                continue

            try:
                ti = max(i for i, tok in enumerate(parts) if time_re.match(tok))
                di = ti - 1
                if di < 0 or not date_re.match(parts[di]):
                    continue

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
                    "firm_file": firm_file
                })
            except ValueError:
                continue

# Save
with open("sales_report.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4)

print(f"Extracted {len(records)} records.")
