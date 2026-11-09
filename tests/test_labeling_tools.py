"""Labeling workflow tests on synthetic data: label sheet, merge, focus pairs, training CSV, JS/Python context parity.
Run: python tests/test_labeling_tools.py"""
import sys, pathlib, tempfile, subprocess, json, shutil
import pandas as pd, numpy as np
root = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(root / "tools")); sys.path.insert(0, str(root / "training"))
import make_label_sheet as ls, merge_labels as ml, make_focus_pairs as fp, build_training_csv as bt, clean_dataset as cd
from build_catalog import build_subjects
from subject_context import Contexts

KW = str(root / "tools" / "Keywords.xlsx")
subjects, _, _ = build_subjects(KW); order = {s["id"]: i for i, s in enumerate(subjects)}; valid = set(order)
tmp = pathlib.Path(tempfile.mkdtemp())

# synthetic cleaned dataset
rows = []
texts = {"database": "Database indexing and SQL query optimization tutorial", "networks": "Subnetting and TCP/IP explained for beginners",
         "programming": "C++ pointers and loops programming tutorial", "automata": "Regular expression to finite automata conversion"}
for i, (sid, t) in enumerate([(k, v) for k, v in texts.items() for _ in range(6)]):
    rows.append({"id": f"r{i}", "text": t + f" part {i}", "image_path": "", "label": "relevant", "language": "english", "source": "youtube", "context": "x", "group": f"g{i}",
                 "domain": "db", "domain_subjects": sid, "keyword_subjects": sid, "matched_keywords": "", "curriculum_basis": "both", "source_url": "", "image_url": ""})
for i in range(10):
    rows.append({"id": f"d{i}", "text": f"Funny cat compilation number {i} with silly pranks", "image_path": "", "label": "distracting", "language": "english", "source": "youtube",
                 "context": "x", "group": f"gd{i}", "domain": "non_csit", "domain_subjects": "", "keyword_subjects": "", "matched_keywords": "", "curriculum_basis": "none", "source_url": "", "image_url": ""})
clean = pd.DataFrame(rows); clean_path = tmp / "clean.csv"; clean.to_csv(clean_path, index=False)

# 1) label sheet: relevant rows only, dropdown ids, blind overlap
r = subprocess.run([sys.executable, str(root / "tools" / "make_label_sheet.py"), str(clean_path), "--n", "20", "--overlap", "6", "--prefill", "--out", str(tmp / "lab")], capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-600:]
import openpyxl
A = pd.read_excel(tmp / "lab" / "subject_sheet_A.xlsx", sheet_name="label", dtype=str).fillna(""); B = pd.read_excel(tmp / "lab" / "subject_sheet_B.xlsx", sheet_name="label", dtype=str).fillna("")
assert len(A) == 20 and A["id"].str.startswith("r").all() and len(B) == 6 and set(B["id"]) <= set(A["id"])
assert (B["subject_1"] == "").all() and (A[A["id"].isin(B["id"])]["subject_1"] == "").all(), "overlap rows must be blind (no prefill)"
assert (A[~A["id"].isin(B["id"])]["subject_1"] != "").all(), "other rows are prefilled when --prefill is set"
wb = openpyxl.load_workbook(tmp / "lab" / "subject_sheet_A.xlsx"); assert wb["label"].data_validations.dataValidation and wb["subjects"].max_row == len(subjects) + 1
print("ok - label sheet: relevant rows only, dropdown list of catalog ids, blind overlap sheet")

# 2) merge two annotators: agreement, conflict, not_csit, invalid id
def sheet(pairs, name):
    df = pd.DataFrame([{"id": i, "text": "", "language": "", "suggested": "", "subject_1": s1, "subject_2": s2, "subject_3": "", "not_csit": n, "note": ""} for i, s1, s2, n in pairs]); p = tmp / f"{name}.csv"; df.to_csv(p, index=False); return p
pa = sheet([("r0", "database", "", ""), ("r1", "networks", "", ""), ("r2", "programming", "oop", ""), ("r3", "automata", "", "Y"), ("r4", "bogus", "", ""), ("r5", "database", "", "")], "annA")
pb = sheet([("r0", "database", "", ""), ("r1", "database", "", ""), ("r2", "programming", "oop", "")], "annB")
problems = []
parsed = {"annA": ml.parse(ml.read_sheet(pa), valid, "annA", problems), "annB": ml.parse(ml.read_sheet(pb), valid, "annB", problems)}
rows_, conflicts, flags = ml.merge(parsed, valid)
st = {r_["id"]: r_ for r_ in rows_}
assert st["r0"]["status"] == "agreed" and st["r0"]["subjects"] == "database" and st["r2"]["subjects"] == "programming;oop"
assert st["r1"]["status"] == "conflict" and st["r3"]["status"] == "not_csit" and st["r5"]["status"] == "ok" and "r4" not in st
assert len(problems) == 1 and "bogus" in problems[0][2] and [c["id"] for c in conflicts] == ["r1"] and flags[0]["id"] == "r3"
ag = ml.agreement(parsed); assert ag["n"] == 3 and 0 < ag["mean_jaccard"] <= 1
r = subprocess.run([sys.executable, str(root / "tools" / "merge_labels.py"), str(pa), str(pb), "--out", str(tmp / "mer"), "--target", "1"], capture_output=True, text=True)
assert r.returncode == 0 and (tmp / "mer" / "subject_label_report.md").exists() and "conflict" in (tmp / "mer" / "subject_labels.csv").read_text()
print("ok - merge: agreed / ok / conflict / not_csit statuses, invalid ids reported, agreement computed")

# 3) a fully labeled set -> focus pairs -> training csv
lab = pd.DataFrame([{"id": f"r{i}", "subjects": s, "status": "ok", "annotators": "a"} for i, s in enumerate([k for k in texts for _ in range(6)])])
lab.to_csv(tmp / "labels.csv", index=False)
r = subprocess.run([sys.executable, str(root / "tools" / "make_focus_pairs.py"), str(clean_path), str(tmp / "labels.csv"), "--out", str(tmp / "pairs"), "--sheet-n", "30"], capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-600:]
key = pd.read_csv(tmp / "pairs" / "focus_pairs_key.csv", dtype=str); sheet_ = pd.read_csv(tmp / "pairs" / "focus_pairs_sheet.csv", dtype=str)
assert set(key["kind"]) <= {"pos", "neg_same", "neg_other"} and "pos" in set(key["kind"]) and "neg_other" in set(key["kind"])
assert "suggested" not in sheet_.columns and "kind" not in sheet_.columns, "annotator sheet must not leak the suggestion"
text_of = dict(zip(clean["id"], clean["text"]))
for _, p in key.iterrows():                                            # suggestions are consistent with the text
    appears = fp.appears(p["focus"], cd.norm_text(text_of[p["id"]]))
    assert (p["kind"] == "pos") == appears, (p["kind"], p["focus"], text_of[p["id"]])
assert fp.is_heldout("c++", 0.2) == fp.is_heldout("C++", 0.2) and 0 < key["heldout"].astype(int).sum() < len(key)
print(f"ok - focus pairs: {key['kind'].value_counts().to_dict()}, annotator sheet hides suggestions, held-out terms fixed by hash")

answers = sheet_.copy(); answers["answer"] = ["yes" if i % 3 == 0 else "no" if i % 3 == 1 else "partly" for i in range(len(answers))]
out, stats = bt.build(clean, lab, subjects, key, answers, aug_per_item=1, aug_distracting=1.0, seed=1)
assert set(out["kind"]) == {"base", "subject_ctx", "focus"} and stats["focus"] > 0 and stats["subject_ctx"] > 0
base = out[out["kind"] == "base"].set_index("id")
assert (base.loc[[f"d{i}" for i in range(10)], "subjects"] == "none").all() and base.loc["r0", "subjects"] == "database"
pos = out[out["id"] == "r0#p0"].iloc[0]; neg = out[out["id"] == "r0#n0"].iloc[0]
assert pos["label"] == "relevant" and pos["ctx_subjects"] == "database" and pos["context"].startswith("Database Management Systems:")
assert neg["label"] == "distracting" and neg["ctx_subjects"] != "database" and neg["group"] == pos["group"] == "g0"
assert (out[out["kind"] == "focus"]["context"].str.startswith("focus: ")).all() and set(out[out["kind"] == "focus"]["label"]) <= {"relevant", "distracting"}
assert out[out["kind"] == "focus"]["id"].str.contains("~weak").sum() == 0
weak, st2 = bt.build(clean, lab, subjects, key, None, use_suggested=True, seed=1)
assert st2["focus"] == len(key[key["suggested"].isin(["yes", "no"])]) and weak[weak["kind"] == "focus"]["id"].str.endswith("~weak").all()
flagged = lab.copy(); flagged.loc[0, "status"] = "not_csit"; fo, fs = bt.build(clean, flagged, subjects, None, None); assert "r0" not in set(fo["id"]) and fs["dropped_flagged"] == 1
assert out["group"].notna().all() and out.groupby("group")["id"].count().max() >= 2
cat_out, cst = bt.build(clean, lab, subjects, key, answers, add_catalog=True, seed=1)
cat = cat_out[cat_out["kind"] == "catalog"]
assert cst["catalog"] == len(cat) > 100 and set(cat["source"]) == {"catalog"} and cat["group"].is_unique is False or cat["id"].is_unique
assert set(cat["label"]) == {"relevant", "distracting"} and (cat["image_path"] == "").all() and cat["id"].is_unique
rel = cat[(cat["label"] == "relevant") & (cat["ctx_subjects"] == "")]; assert (rel["subjects"] != "").all() and (rel["context"].str.startswith("Computer Science and Information Technology")).all()
assert (cat[cat["id"].str.endswith("#f")]["context"].str.startswith("focus: ")).all()
no_drafts, _ = bt.build(clean, lab, subjects, None, None, add_catalog=True, catalog_drafts=False, seed=1)
assert len(no_drafts[no_drafts["kind"] == "catalog"]) < len(cat), "--no-catalog-drafts removes draft topics"
assert len(bt.build(clean, lab, subjects, None, None, seed=1)[0][lambda d: d["kind"] == "catalog"]) == 0, "catalog rows are opt-in"
print(f"ok - training csv: {stats}, flagged rows dropped, weak labels only with --use-suggested")

# 4) the context strings must be identical in Python (training) and JS (extension)
js = """
const fs=require('fs'),vm=require('vm');const ctx=vm.createContext({console});
for (const f of ['subject-catalog.js','subject-tools.js']) vm.runInContext(fs.readFileSync('%s/extension/'+f,'utf8'),ctx);
const T=ctx.SubjectTools;
console.log(JSON.stringify([T.contextString(['database'],'Both',[]), T.contextString(['programming','oop'],'Both',[]), T.contextString([],'Both',[]),
  T.contextString([],'Both',[{term:'c++',subjects:['programming']}]), T.contextString([],'Both',[{term:'regular expression',subjects:['automata']}])]));
""" % root
out_js = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
c = Contexts(subjects, "Both")
py = [c.subject_context(["database"]), c.subject_context(["programming", "oop"]), c.subject_context([]), c.focus_context(["c++"], ["programming"]), c.focus_context(["regular expression"], ["automata"])]
assert out_js == py, (out_js, py)
print("ok - Python and JavaScript build identical context text (training and extension cannot drift apart)")
shutil.rmtree(tmp)
print("labeling tool tests passed")
