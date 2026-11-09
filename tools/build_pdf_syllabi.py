"""
build_pdf_syllabi.py - runs parse_obtl_pdf.py on the syllabus PDFs that are NOT in Keywords.xlsx and writes
tools/pdf_syllabi.json  ({subject_id: {program, code, title, source_file, topics:[[title, detail]]}}).

    python tools/build_pdf_syllabi.py /path/to/Syllabus
Extraction is heuristic and can miss weeks (INTELSYS and CS GEELECDS are partial). Review the JSON.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_obtl_pdf import parse

# relative path under Syllabus/ -> (subject id, program)
FILES = {
    "CS/1st year/1ST SEM/NTROCOMP/BSCS-OBTL Plan in NTROCOMP_ver6.0.pdf": ("intro-computing", "CS"),
    "CS/2nd year/1ST SEM/DIGDELAB_LEC/BSCS-DIGDELEC_ver.5.0.pdf": ("digital-logic", "CS"),
    "CS/3rd year/1ST SEM/INTELSYS/BSCS INTELSYS_ver5.2.pdf": ("intelligent-systems", "CS"),
    "CS/3rd year/2ND SEM/GEELECDS/BSCS GEELECDS_ver6.0.pdf": ("data-science", "CS"),
    "IT/3rd year/1ST SEM/BSIT_GEELECDS_ver5.0.pdf": ("data-science", "IT"),
    "IT/3rd year/1ST SEM/SYSARCH 1 - Course Syllabus_UPDATED AS OF AUGUST 5- 2026.pdf": ("systems-integration", "IT"),
    "IT/2nd year/1ST SEM/_SYLLABUS_02.1_20-_20BSIT2023_20PTECHLEC.docx": ("platform", "IT"),      # actually a PDF
}

if __name__ == "__main__":
    root = Path(sys.argv[1]); out = {}
    for rel, (sid, prog) in FILES.items():
        r = parse(str(root / rel))
        e = out.setdefault(sid, {"sources": [], "topics": []})
        e["sources"].append({"program": prog, "code": r["code"], "title": r["title"], "file": rel})
        seen = {t[0].lower() for t in e["topics"]}
        for t in r["topics"]:
            if t["topic"].lower() not in seen: seen.add(t["topic"].lower()); e["topics"].append([t["topic"], t["detail"]])
    Path(__file__).with_name("pdf_syllabi.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print({k: len(v["topics"]) for k, v in out.items()})
