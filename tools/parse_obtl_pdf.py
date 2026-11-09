"""
parse_obtl_pdf.py - pulls course code/title and weekly 'Content' topics from EARIST OBTL syllabus PDFs using
pdfplumber table extraction (Week | Content | ILO | ...). Heuristic: review the output; PDFs differ.

    python tools/parse_obtl_pdf.py <syllabus.pdf> ...     # prints JSON {path: {code,title,topics:[{week,topic,detail}]}}
"""
import json, re, sys
import pdfplumber

SKIP = re.compile(r"orientation|vmgo|midterm|final exam|prelim|^examination|^review$|^exam", re.I)
SETTINGS = {"text_x_tolerance": 1.5}


def split_cell(cell):
    """'● / Basic Electronics / ● / Resistor' -> (title, [details]). Cell lines are separated by newlines."""
    text = re.sub(r"\n●", "\n●", cell or "")
    parts, cur = [], None
    for ln in text.split("\n"):
        ln = ln.strip()
        if not ln: continue
        if ln.startswith("●") or ln.startswith("•"):
            cur = [ln.lstrip("●• ").strip()]; parts.append(cur)
        elif cur is not None and not (len(ln) > 0 and ln[0].isupper() and cur[-1].endswith((".", ":", ";"))): cur.append(ln)
        else: cur = [ln]; parts.append(cur)
    items = [re.sub(r"\s+", " ", " ".join(p)).strip(" :;-") for p in parts if " ".join(p).strip(" ●•")]
    return items


def parse(path):
    code = title = ""
    rows = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            flat = pg.extract_text(x_tolerance=1.5) or ""
            m = re.search(r"Course\s*Code\s+([A-Z][A-Z0-9_\-]{2,14})", flat)
            if m and not code: code = m.group(1)
            m = re.search(r"Course\s*Title\s+(.+)", flat)
            if m and not title and not m.group(1).strip().startswith("Contact"): title = re.sub(r"\s+Contact.*", "", m.group(1)).strip()
            for t in pg.extract_tables(SETTINGS):
                for r in t:
                    if len(r) >= 2 and r[0] and re.fullmatch(r"[\d\s\-–/]+", r[0].strip()):
                        cell = next((c for c in r[1:3] if c and re.search(r"[A-Za-z]{4,}", c)), None)   # content is column 1 or 2
                        if cell: rows.append((re.sub(r"\s+", " ", r[0]).strip(), cell))
    out = []
    for week, cell in rows:
        items = split_cell(cell)
        if not items or not re.search(r"[A-Za-z]{4,}", items[0]): continue
        head, details = items[0], items[1:]
        if SKIP.search(head) and not details: continue
        if SKIP.search(head):    # orientation row that also lists content: keep only details
            if not details: continue
            head, details = details[0], details[1:]
        out.append({"week": week, "topic": head, "detail": "; ".join(details)[:300]})
    return {"code": code, "title": title, "topics": out}


if __name__ == "__main__":
    print(json.dumps({p: parse(p) for p in sys.argv[1:]}, indent=1, ensure_ascii=False))
