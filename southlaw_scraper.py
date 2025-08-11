#!/usr/bin/env python3
"""
southlaw_scraper_with_counties.py

Reads a PDF (local path or URL), detects county headings (green text / big font),
groups property lines under the county heading, parses common fields and writes JSON.

Heuristics are conservative; if PDF layout differs, tweak the regexes / thresholds.
"""
import fitz                     # PyMuPDF
import re
import json
import argparse
import requests
import io
from statistics import median

# -------------------------
# Helpers
# -------------------------
PRICE_RE = re.compile(r'\$?\s*\d{1,3}(?:[,\d]{0,})(?:\.\d{1,2})?')
ZIP_RE = re.compile(r'\b(\d{5})(?:-\d{4})?\b')
DATE_RE = re.compile(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b')
INTEGER_RE = re.compile(r'\b\d{4,8}\b')  # firm file or case number candidates


def rgb_from_srgb_int(srgb_int):
    """Convert PyMuPDF sRGB integer (0xRRGGBB) to (r,g,b) ints 0..255.
       fitz provides sRGB_to_rgb helper, but fallback here for safety."""
    try:
        return fitz.sRGB_to_rgb(srgb_int)
    except Exception:
        # fallback decode manually
        if not srgb_int:
            return (0, 0, 0)
        r = (srgb_int >> 16) & 0xFF
        g = (srgb_int >> 8) & 0xFF
        b = srgb_int & 0xFF
        return (r, g, b)


def looks_like_county_text(line_text, spans, page_median_size):
    """
    Decide whether this line is a county heading:
      - short line, no digits, few words
      - text color strongly green in at least one span OR font size noticeably larger than page median
    """
    t = line_text.strip()
    if not t or len(t) > 40:
        return False
    # exclude anything that contains digits or many punctuation
    if re.search(r'\d', t):
        return False
    if len(t.split()) > 4:   # county headings usually 1-3 words (Jasper, Jefferson, Lewis)
        return False

    # check spans for green-ish color
    for sp in spans:
        c = sp.get('color')
        if c is None:
            continue
        r, g, b = rgb_from_srgb_int(int(c))
        # greenish heuristic: green significantly higher than red/blue and above threshold
        if g >= 100 and g > (r * 1.2) and g > (b * 1.2):
            return True

    # fallback: very large font (e.g., heading)
    sizes = [sp.get('size', 0) for sp in spans if sp.get('size')]
    if sizes:
        avg_size = sum(sizes) / len(sizes)
        if page_median_size and avg_size >= page_median_size * 1.25:
            return True

    return False


def extract_lines_from_page(page):
    """Return sorted lines: list of dicts with keys (x0,y0, text, spans, avg_size)"""
    d = page.get_text("dict")              # detailed text extraction
    lines = []
    for block in d.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            # compute leftmost x and top y from the line bbox
            bbox = line.get("bbox", None)
            y0 = bbox[1] if bbox else spans[0].get("bbox", [0, 0, 0, 0])[1]
            x0 = bbox[0] if bbox else spans[0].get("bbox", [0, 0, 0, 0])[0]
            text = "".join([s.get("text", "") for s in spans]).strip()
            sizes = [s.get("size", 0) for s in spans if s.get("size")]
            avg_size = (sum(sizes) / len(sizes)) if sizes else 0
            lines.append({"y": y0, "x": x0, "text": text, "spans": spans, "avg_size": avg_size})
    # sort top->bottom then left->right
    lines.sort(key=lambda r: (round(r["y"], 1), round(r["x"], 1)))
    return lines


def parse_property_block(block_text, current_county):
    """
    Heuristic parsing of a single property block string.
    Returns a dict with keys that match your JSON schema.
    """
    text = " ".join(block_text.split())  # normalize whitespace

    # find opening bid (first price-looking token)
    opening_match = PRICE_RE.search(text)
    opening_bid = opening_match.group(0).strip() if opening_match else "N/A"
    # normalize to $X,XXX.XX format
    if opening_bid != "N/A":
        # remove stray spaces, ensure leading $
        num = re.sub(r'[^\d.]', '', opening_bid)
        if num == "":
            opening_bid = "N/A"
        else:
            # format to 2 decimals
            try:
                opening_bid = "$" + f"{float(num):,.2f}"
            except Exception:
                opening_bid = "$" + num

    # find all dates
    dates = DATE_RE.findall(text)
    sale_date = dates[0] if dates else "N/A"
    continued_date = dates[1] if len(dates) > 1 else "N/A"

    # find zip
    zip_m = ZIP_RE.search(text)
    prop_zip = zip_m.group(1) if zip_m else "N/A"

    # find firm file (first 4-8 digit integer that looks plausible)
    firm_m = INTEGER_RE.search(text)
    firm_file = firm_m.group(0) if firm_m else "N/A"

    # civil/case: look for 'Case' or 'Civil' keywords and take nearby token
    civil = "N/A"
    cm = re.search(r'(?:Case|Civil|Cause)\s*(?:No\.?|#|:)?\s*([A-Za-z0-9\-\/]+)', text, flags=re.I)
    if cm:
        civil = cm.group(1)

    # Try to guess address and city using comma splitting or patterns
    property_address = "N/A"
    property_city = "N/A"
    # First try comma-separated pattern: addr, city, [state] zip or addr, city zip
    parts = [p.strip() for p in re.split(r'\s{2,}|,|\s-\s', text) if p.strip()]
    # prefer first few parts
    if len(parts) >= 3:
        property_address = parts[0]
        property_city = parts[1]
        # if city is actually a county or a stray token, we leave it — user can tweak
    else:
        # fallback regex: number + street ... city + zip
        m = re.search(r'(\d+\s+[\w\.\-/#\s]+?)\s+([A-Za-z .\-]{2,50})\s+(\d{5})', text)
        if m:
            property_address = m.group(1).strip()
            property_city = m.group(2).strip()

    # sale_time: some PDFs put time near date or as '10:30AM' etc
    time_m = re.search(r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b', text)
    sale_time = time_m.group(0) if time_m else "N/A"

    # sale_location_city: keep a copy if there's a stray $ price not mapped to opening_bid (rare)
    sale_location_city = "N/A"
    # try to capture second price if present
    all_prices = PRICE_RE.findall(text)
    if len(all_prices) > 1:
        sale_location_city = all_prices[1].strip()

    # build result
    result = {
        "county": current_county or "N/A",
        "property_address": property_address,
        "property_city": property_city,
        "property_zip": prop_zip,
        "sale_date": sale_date,
        "sale_time": sale_time,
        "continued_date_time": continued_date,
        "opening_bid": opening_bid,
        "sale_location_city": sale_location_city,
        "civil_case_no": civil,
        "firm_file": firm_file,
        "raw_text": text  # keep raw_text for debugging / future parsing improvements
    }
    return result


def pdf_to_json(pdf_stream, out_json_path):
    doc = fitz.open(stream=pdf_stream, filetype="pdf")
    all_items = []

    for page_no in range(len(doc)):
        page = doc[page_no]
        lines = extract_lines_from_page(page)
        # compute median size on the page (for heading fallback)
        sizes = [l["avg_size"] for l in lines if l["avg_size"] > 0]
        page_median_size = median(sizes) if sizes else None

        current_county = None
        buffer_lines = []

        def flush_buffer():
            nonlocal buffer_lines, current_county, all_items
            if not buffer_lines:
                return
            block_text = " ".join(buffer_lines).strip()
            # only parse if block contains something useful (price or date or address)
            if PRICE_RE.search(block_text) or DATE_RE.search(block_text) or ZIP_RE.search(block_text):
                parsed = parse_property_block(block_text, current_county)
                all_items.append(parsed)
            buffer_lines = []

        for L in lines:
            text = L["text"].strip()
            if not text:
                # blank line — maybe property end
                flush_buffer()
                continue

            # is this line a county heading?
            if looks_like_county_text(text, L["spans"], page_median_size):
                # flush pending property before switching county
                flush_buffer()
                # set county (clean it)
                county_name = re.sub(r'[^A-Za-z \-\.]', '', text).strip()
                current_county = county_name
                continue

            # Heuristic: if line contains clear property terminator (price, date, firm file) treat it as end
            terminator = False
            if PRICE_RE.search(text) or DATE_RE.search(text) or INTEGER_RE.search(text):
                # append and flush
                buffer_lines.append(text)
                flush_buffer()
                continue

            # default: accumulate
            buffer_lines.append(text)

        # end page: flush
        flush_buffer()

    # save JSON
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)

    print(f"Written {len(all_items)} records to {out_json_path}")


# -------------------------
# CLI
# -------------------------
def main():
    parser = argparse.ArgumentParser(description="Southlaw scraper with county detection (PyMuPDF).")
    parser.add_argument("--pdf", help="Local PDF path", default=None)
    parser.add_argument("--pdf-url", help="Remote PDF URL", default=None)
    parser.add_argument("--out", help="Output JSON path", default="sales_report.json")
    args = parser.parse_args()

    if not args.pdf and not args.pdf_url:
        parser.error("You must provide either --pdf (local path) or --pdf-url (remote PDF).")

    if args.pdf_url:
        r = requests.get(args.pdf_url, timeout=60)
        r.raise_for_status()
        pdf_stream = io.BytesIO(r.content)
    else:
        pdf_stream = open(args.pdf, "rb").read()

    pdf_to_json(pdf_stream, args.out)


if __name__ == "__main__":
    main()
