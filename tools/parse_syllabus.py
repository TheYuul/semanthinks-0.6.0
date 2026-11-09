"""Parse Keywords.xlsx (Major sheets only) into syllabus.json.
Sheets are laid out as side-by-side course blocks: each block starts with a
'COURSE INFORMATION' cell, then Course Code/Title/Year/Term rows, then a
'Topic / Unit' header and topic rows until the first empty cell."""
import json, sys, openpyxl

def parse_sheet(ws):
    courses = []
    for row in ws.iter_rows():
        for cell in row:
            if cell.value != "COURSE INFORMATION":
                continue
            r, c = cell.row, cell.column
            def val(dr, dc=1):
                return ws.cell(row=r + dr, column=c + dc).value
            course = {"code": val(1), "title": val(2), "year": val(3), "term": val(4), "topics": []}
            rr = r + 6  # 'Topic / Unit' header is at r+6
            assert ws.cell(row=rr, column=c).value == "Topic / Unit", (ws.title, r, c)
            rr += 1
            while ws.cell(row=rr, column=c).value:
                course["topics"].append({"topic": str(ws.cell(row=rr, column=c).value).strip(),
                                         "detail": str(ws.cell(row=rr, column=c + 1).value or "").strip()})
                rr += 1
            courses.append(course)
    return courses

if __name__ == "__main__":
    wb = openpyxl.load_workbook(sys.argv[1])
    out = {}
    for name in ("IT Major", "CS Major"):   # minor (general education) sheets are intentionally ignored
        out[name.split()[0]] = parse_sheet(wb[name])
    json.dump(out, open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
    for k, v in out.items():
        print(k, len(v), "courses", sum(len(c["topics"]) for c in v), "topics")
        for c in v: print("  ", c["code"], "|", c["title"], "|", c["year"], c["term"], "|", len(c["topics"]))
