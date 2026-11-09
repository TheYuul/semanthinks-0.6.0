"""
build_catalog.py - generates extension/subject-catalog.js

    python build_catalog.py Keywords.xlsx ../extension/subject-catalog.js

Inputs
  Keywords.xlsx        syllabus topics, one block per course (see parse_syllabus.py). Only the
                       "CS Major" and "IT Major" sheets are read. Minor / GE sheets are ignored.
  legacy_catalog.json  the keyword lists of the 0.2.x catalog, reused for filtering keywords.
  SUBJECTS (below)     which subjects exist, which program(s) they belong to, and which syllabus
                       course codes feed each one.

To add syllabus data for a subject that has none yet, add its course block to Keywords.xlsx, put the
course code in that subject's "codes" list below, and run this script again.
"""
import json, sys
from pathlib import Path
import openpyxl
sys.path.insert(0, str(Path(__file__).parent))
from parse_syllabus import parse_sheet

HERE = Path(__file__).parent

# id, CS label, IT label, Both-mode label (None = use CS label), legacy ids, extra keywords, syllabus codes
# A label of None means the subject does not belong to that program.
# MAJOR = any core / non-General-Education subject (team decision). GE-coded courses are excluded, except GEELECDS
# Practical Data Science, which both programs' syllabi list as a technical elective (team decision: both CS and IT).
SUBJECTS = [
    ("intro-computing", "Introduction to Computing", "Introduction to Computing", None, [],
     ["introduction to computing", "computing fundamentals", "computer basics", "history of computing"], []),
    ("programming", "Computer Programming 1 & 2", "Computer Programming 1 & 2", None, ["cs-programming", "it-programming"], [],
     ["FPROGLAB", "FPROGLEC", "IPROGLAB", "IPROGLEC"]),
    ("discrete", "Discrete Structures 1 & 2", "Discrete Mathematics", "Discrete Structures / Mathematics", ["cs-discrete", "it-discrete"], [], []),
    ("database", "Database Management Systems", "Database Management Systems", None, ["cs-database", "it-database"], ["indexing", "database indexing", "query optimization"], []),
    ("info-management", "Information Management", "Information Management", None, ["cs-information-management", "it-information-management"], [],
     ["INFOMGMTLEC", "INFOMGMTLAB", "INFMGTLC"]),
    ("data-structures", "Data Structures & Algorithms", "Data Structures & Algorithms", None, ["cs-data-structures", "it-data-structures"], [], ["DSALGLEC"]),
    ("calculus", "Differential & Integral Calculus", None, None, ["cs-calculus"], [], []),
    ("digital-logic", "Digital Logic Design", None, None, ["cs-digital-logic"], [], []),
    ("graphics", "Graphics & Visual Computing", None, None, ["cs-graphics"], [], []),
    ("security", "Information Assurance & Security", "Information Assurance & Security", None, ["cs-security", "it-security"], [], ["INFOASEC", "IAASLEC2"]),
    ("robotics", "Microprocessor & Introduction to Robotics", None, None, ["cs-robotics"], [], []),
    ("networks", "Networks & Communications", "Networking", "Networks & Communications / Networking", ["cs-networks", "it-networking"], [], []),
    ("oop", "Object-Oriented Programming", "Object-Oriented Programming", None, ["cs-oop", "it-oop"], [], ["OOPGRLEC"]),
    ("physics", "Physics for Computer Scientists", None, None, [],
     ["physics", "mechanics", "electricity", "magnetism", "optics", "thermodynamics", "waves"], []),
    ("data-science", "Practical Data Science", "Practical Data Science", None, ["cs-data-science"], [], []),
    ("programming-languages", "Programming Languages", None, None, ["cs-programming-languages"], [], ["PROGLLEC", "PROGLLAB"]),
    ("complexity", "Algorithm & Complexity", None, None, ["cs-complexity"], [], ["ALGCMPLX"]),
    ("emerging-tech", "Application Development & Emerging Technology", "Application Development & Emerging Technology", None, ["cs-emerging-tech", "it-emerging-tech"], [],
     ["APDEVLEC", "APDEVLAB"]),
    ("architecture", "Architecture & Organization", None, None, ["cs-architecture"], [], ["ARCHIORG"]),
    ("hci", "Human & Computer Interaction", "Human Computer Interaction", None, ["cs-hci", "it-hci"], [], ["HUCOMINT"]),
    ("intelligent-systems", "Intelligent Systems", None, None, ["cs-intelligent-systems"], [], []),
    ("mobile", "Mobile Application Development (iOS & Android)", "Mobile Application Development (iOS & Android)", None, ["cs-mobile", "it-mobile"], [], []),
    ("modeling", "Modeling & Simulation", "Quantitative Methods (incl. Modeling & Simulation)", "Modeling & Simulation / Quantitative Methods", ["cs-modeling", "it-quantitative"], [], []),
    ("operating-systems", "Operating Systems", None, None, ["cs-operating-systems"], [], ["OPERSYST"]),
    ("distributed", "Parallel & Distributed Computing", None, None, ["cs-distributed"], [], []),
    ("software-engineering", "Software Engineering 1 & 2", None, None, ["cs-software-engineering"], [], ["SOFTENG2"]),
    ("thesis", "Thesis 1 & 2", "Capstone Project & Research 1 & 2", "Thesis / Capstone & Research", ["cs-thesis", "it-capstone"], [], ["CSTHESI1", "ITTHESL2"]),
    ("automata", "Automata Theory & Formal Languages", None, None, ["cs-automata"], [], ["AUTOMATA"]),
    ("spi", "Social & Professional Issues", "Social & Professional Issues", None, [],
     ["social and professional issues", "computer ethics", "professional ethics", "intellectual property", "software licensing"], ["SSUPPRAC", "SPISSUES"]),
    # IT-only major subjects
    ("business-analytics", None, "Business Analytics", None, ["it-business-analytics"], [], []),
    ("platform", None, "Platform Technologies", None, ["it-platform"], [], []),
    ("web", None, "Web Development 1-3", None, ["it-web"], [], []),
    ("integrative", None, "Integrative Programming & Technologies", None, ["it-integrative"], [], []),
    ("multimedia", None, "Multimedia", None, ["it-multimedia"], [], []),
    ("systems-integration", None, "Systems Integration & Architecture 1 & 2", None, ["it-systems-integration"], [], []),
    ("systems-admin", None, "Systems Administration & Maintenance", None, ["it-systems-admin"], [], []),
    ("internship", None, "Practicum / Internship", None, ["it-internship"], [], []),
]

PROGRAM_NAMES = {"CS": "Computer Science", "IT": "Information Technology", "Both": "Computer Science and Information Technology"}


def program_contexts(subjects):
    """Session-context text used when a program is chosen but no subject is selected: program name plus the two
    leading curriculum keywords of every subject, capped at 400 characters. The extension (subject-tools.js) and
    the dataset builder (clean_dataset.py) both use exactly this text."""
    out = {}
    for key, name in PROGRAM_NAMES.items():
        kws = []
        for s in subjects:
            if key == "Both" or key in s["programs"]:
                kws += s["keywords"][:2]
        out[key] = f"{name}: {', '.join(dict.fromkeys(kws))}"[:400]
    return out


def build_subjects(xlsx):
    """Returns (subjects, legacy_map, courses). `courses` maps subject id -> the official syllabus courses behind it
    (program, code, title, year, term, topic count). Shared with build_reference.py and clean_dataset.py."""
    wb = openpyxl.load_workbook(xlsx)
    syllabus = {"CS": {c["code"]: c for c in parse_sheet(wb["CS Major"])},
                "IT": {c["code"]: c for c in parse_sheet(wb["IT Major"])}}
    legacy = json.loads((HERE / "legacy_catalog.json").read_text())
    drafts = json.loads((HERE / "draft_syllabus.json").read_text())   # see make_draft_syllabus.py
    pdf_path = HERE / "pdf_syllabi.json"      # see build_pdf_syllabi.py
    pdf_syl = json.loads(pdf_path.read_text()) if pdf_path.exists() else {}
    public_syl = json.loads((HERE / "public_syllabi.json").read_text()) if (HERE / "public_syllabi.json").exists() else {}
    legacy_kw = {}
    for program in legacy.values():
        for old_id, entry in program.items():
            legacy_kw[old_id] = entry["keywords"]

    subjects, legacy_map, used_codes, courses = [], {}, set(), {}
    for sid, cs_label, it_label, both_label, old_ids, extra_kw, codes in SUBJECTS:
        programs = [p for p, label in (("CS", cs_label), ("IT", it_label)) if label]
        keywords = []
        for old in old_ids:
            legacy_map[old] = sid
            keywords += legacy_kw.get(old, [])
        keywords = list(dict.fromkeys(keywords + extra_kw))
        topics, seen = [], set()
        for program in programs:
            for code in codes:
                course = syllabus[program].get(code)
                if not course: continue
                used_codes.add((program, code))
                courses.setdefault(sid, []).append({"program": program, "code": code, "title": course["title"], "year": course["year"],
                                                    "term": course["term"], "n_topics": len(course["topics"])})
                for t in course["topics"]:
                    if t["topic"].lower() in seen: continue
                    seen.add(t["topic"].lower())
                    topics.append([t["topic"], t["detail"]])
        # Official topics from syllabus PDFs (tools/pdf_syllabi.json); only for subjects the spreadsheet does not cover.
        for title, detail in pdf_syl.get(sid, {}).get("topics", []):
            if title.lower() not in seen:
                seen.add(title.lower()); topics.append([title, detail])
        for src in pdf_syl.get(sid, {}).get("sources", []):
            if src["program"] in programs:
                courses.setdefault(sid, []).append({"program": src["program"], "code": src["code"], "title": src["title"], "year": "", "term": "", "n_topics": len(pdf_syl[sid]["topics"])})
        # Topics from a PUBLIC syllabus of another Philippine university (tools/public_syllabi.json), cited by URL.
        pub = public_syl.get(sid)
        if pub:
            for title, detail in pub["topics"]:
                if title.lower() not in seen:
                    seen.add(title.lower()); topics.append([title, detail])
            for p in programs:
                courses.setdefault(sid, []).append({"program": p, "code": "PUBLIC", "title": pub["source"] + " " + pub["url"], "year": "", "term": "", "n_topics": len(pub["topics"])})
        # Draft topics (third item = 1) are only added when the title is not already in the official syllabus.
        for title, detail in drafts.get(sid, []):
            if title.lower() not in seen:
                seen.add(title.lower()); topics.append([title, detail, 1])
        subjects.append({"id": sid,
                         "labels": {"CS": cs_label, "IT": it_label, "Both": both_label or cs_label or it_label},
                         "programs": programs, "keywords": keywords, "topics": topics})

    unused = [(p, c) for p in syllabus for c in syllabus[p] if (p, c) not in used_codes]
    if unused:
        print("WARNING: syllabus courses not attached to any subject:", unused)
    return subjects, legacy_map, courses


def main(xlsx, out_js):
    subjects, legacy_map, _ = build_subjects(xlsx)

    header = "/* GENERATED by tools/build_catalog.py from Keywords.xlsx. Do not edit by hand. */\n"
    body = ("const PROGRAM_OPTIONS = [[\"Computer Science\", \"CS\"], [\"Information Technology\", \"IT\"], [\"Both\", \"Both\"]];\n"
            "const SUBJECTS = " + json.dumps(subjects, ensure_ascii=False, indent=1) + ";\n"
            "const LEGACY_SUBJECT_IDS = " + json.dumps(legacy_map, indent=1) + ";\n"
            "const PROGRAM_CONTEXTS = " + json.dumps(program_contexts(subjects), ensure_ascii=False, indent=1) + ";\n")
    Path(out_js).write_text(header + body, encoding="utf-8")

    for p in ("CS", "IT"):
        mine = [s for s in subjects if p in s["programs"]]
        print(f"{p}: {len(mine)} subjects, {sum(1 for s in mine if s['topics'])} with syllabus topics")
    print(f"Both: {len(subjects)} subjects")
    official = [s["id"] for s in subjects if any(len(t) == 2 for t in s["topics"])]
    print(f"Official syllabus topics: {len(official)} subjects. Draft-only: {', '.join(s['id'] for s in subjects if s['topics'] and s['id'] not in official)}")
    print("No topics at all:", ", ".join(s["id"] for s in subjects if not s["topics"]) or "none")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
