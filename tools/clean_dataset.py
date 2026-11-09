"""
clean_dataset.py - turns the merged export into a training-ready dataset.csv plus review files.

    python tools/clean_dataset.py data/export_merged_labeled.csv --out data/clean

Outputs (in --out): dataset_clean.csv (for extract_features.py), rejects.csv (dropped rows + reason),
conflicts_for_review.csv (same text, different labels), cleaning_report.md.

LABEL DIRECTION: in the export, label 1 = RELEVANT (academic CS/IT) and 0 = not relevant. The pipeline uses
1 = distracting, so the label is flipped here. Check this with the audit (make_audit_sample.py) before training.

CURRICULUM COLUMNS (reference only, NOT ground truth, never fed to the model as labels):
  domain_subjects   subjects of the catalog that the sheet's `domain` code maps to (DOMAIN_TO_SUBJECTS below; my mapping)
  keyword_subjects  subjects whose curriculum keywords appear in the text (automatic keyword match)
  matched_keywords  the keywords that matched
  curriculum_basis  'domain' | 'keyword' | 'both' | 'none'
`context` is label-independent (program level, from the catalog) so cosine similarity cannot leak the label.
"""
import argparse, csv, re, sys, unicodedata
from collections import defaultdict
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_catalog import build_subjects, program_contexts

# Sheet domain code -> catalog subject ids (my mapping from the domain-basis tab; review it).
DOMAIN_TO_SUBJECTS = {
    "prg": ["programming", "oop", "programming-languages"], "ai": ["intelligent-systems", "data-science"],
    "se": ["software-engineering"], "web": ["web", "integrative"], "net": ["networks"],
    "alg": ["data-structures", "complexity", "automata"], "cyb": ["security"], "db": ["database", "info-management"],
    "ds": ["data-science", "business-analytics"], "sys": ["operating-systems", "platform", "systems-admin"],
    "dist": ["distributed"], "mm": ["multimedia", "graphics"], "arch": ["architecture"], "mobile": ["mobile"],
    "hci": ["hci"], "is": ["info-management", "systems-integration"], "other_csit": [], "non_csit": [],
}
VALID_LANG = {"english", "taglish", "tagalog"}
MIN_CHARS = 15
MAX_TEXT = 1200          # characters kept; embedder max_seq_length is 128 tokens anyway


def norm_text(s):
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return re.sub(r"[^a-z0-9ñ]+", " ", s).strip()


def clean_text(s):
    s = "" if pd.isna(s) else str(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"https?://\S+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def keyword_index(subjects):
    idx = []
    for s in subjects:
        for k in s["keywords"]:
            nk = norm_text(k)
            if len(nk) >= 4:
                idx.append((s["id"], k, re.compile(rf"(^| ){re.escape(nk)}(s|es)?( |$)")))
    return idx


def curriculum_columns(df, subjects):
    idx = keyword_index(subjects)
    dom, kws_s, kws_m, basis = [], [], [], []
    for domain, text in zip(df["domain"], df["text"]):
        d = DOMAIN_TO_SUBJECTS.get(str(domain), [])
        nt = norm_text(text)
        hit_s, hit_k = [], []
        for sid, k, rx in idx:
            if rx.search(nt):
                if sid not in hit_s: hit_s.append(sid)
                if k not in hit_k: hit_k.append(k)
        dom.append(";".join(d)); kws_s.append(";".join(hit_s)); kws_m.append(";".join(hit_k[:8]))
        basis.append("both" if d and hit_s else "domain" if d else "keyword" if hit_s else "none")
    df["domain_subjects"], df["keyword_subjects"], df["matched_keywords"], df["curriculum_basis"] = dom, kws_s, kws_m, basis
    return df


def clean(raw, subjects, ctx_text, drop_contradictions=True):
    """Returns (clean_df, rejects_df, conflicts_df, stats)."""
    df = raw.copy()
    rejects = []

    def reject(mask, reason):
        nonlocal df
        if mask.any():
            r = df[mask].copy(); r["reject_reason"] = reason; rejects.append(r)
            df = df[~mask]

    # 1. broken rows (CSV shifted by embedded newlines/commas): label must be 0/1 and language known
    reject(~df["label"].isin(["0", "1"]), "bad label (malformed row)")
    reject(df["language_verified"].isna() | ~df["language_verified"].isin(VALID_LANG | {"exclude"}), "bad language value (malformed row)")
    reject(df["id"].isna() | (df["id"].str.len() > 40), "bad id (malformed row)")
    # 2. annotators marked language 'exclude'
    reject(df["language_verified"] == "exclude", "language_verified = exclude")
    # 2b. the sheet's own domain code says "not CS/IT" but the label says relevant: contradiction, noise (--keep-contradictions to keep)
    if drop_contradictions:
        reject((df["domain"] == "non_csit") & (df["label"] == "1"), "domain code non_csit but label relevant (contradiction)")
    # 3. text
    df["text"] = (df["title_text"].map(clean_text) + ". " + df["description_text"].map(clean_text)).str.strip(" .")
    df["text"] = df["text"].str.slice(0, MAX_TEXT)
    reject(df["text"].str.len() < MIN_CHARS, f"text shorter than {MIN_CHARS} characters")
    # 4. duplicates / conflicts on normalized text
    df["_key"] = df["text"].map(norm_text)
    nl = df.groupby("_key")["label"].nunique()
    conflict_keys = set(nl[nl > 1].index)
    conflicts = df[df["_key"].isin(conflict_keys)].sort_values("_key").drop(columns="_key")
    reject(df["_key"].isin(conflict_keys), "same text with different labels (see conflicts_for_review.csv)")
    reject(df.duplicated("_key", keep="first"), "exact duplicate text (first kept)")
    df = df.drop(columns="_key")

    # 5. pipeline columns
    df["label_pipeline"] = df["label"].map({"1": "relevant", "0": "distracting"})     # export: 1 = relevant
    df["language"] = df["language_verified"]
    df["source"] = df["platform"].fillna("")
    df["group"] = df["group_id"].fillna(df["youtube_video_id"]).fillna(df["id"])
    df["image_path"] = ""
    yt = df["image_url"].fillna("").str.contains(r"^https://i\.ytimg\.com/", regex=True)
    df.loc[yt, "image_path"] = df.loc[yt, "youtube_video_id"].fillna("").map(lambda v: f"{v}.jpg" if v else "")
    # 6. label-independent program-level context (see build_catalog.program_contexts)
    df["context"] = ctx_text
    df = curriculum_columns(df, subjects)

    cols = ["id", "text", "image_path", "label_pipeline", "language", "source", "context", "group",
            "domain", "domain_subjects", "keyword_subjects", "matched_keywords", "curriculum_basis", "source_url", "image_url"]
    out = df[cols].rename(columns={"label_pipeline": "label"})
    rej = pd.concat(rejects) if rejects else pd.DataFrame()
    stats = {"input_rows": len(raw), "kept": len(out), "rejected": len(rej),
             "reject_reasons": rej["reject_reason"].value_counts().to_dict() if len(rej) else {},
             "conflict_texts": len(conflict_keys), "label_counts": out["label"].value_counts().to_dict(),
             "language_counts": out["language"].value_counts().to_dict(), "with_image": int((out["image_path"] != "").sum()),
             "groups": int(out["group"].nunique()), "curriculum_basis": out["curriculum_basis"].value_counts().to_dict()}
    return out, rej, conflicts, stats


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("csv"); ap.add_argument("--out", default="data/clean")
    ap.add_argument("--keywords", default=str(HERE / "Keywords.xlsx")); ap.add_argument("--program", default="Both", choices=["CS", "IT", "Both"])
    ap.add_argument("--keep-contradictions", action="store_true", help="keep rows whose domain is non_csit but label is relevant")
    a = ap.parse_args()
    subjects, _, _ = build_subjects(a.keywords)
    raw = pd.read_csv(a.csv, dtype=str)
    out, rej, conf, st = clean(raw, subjects, program_contexts(subjects)[a.program], not a.keep_contradictions)
    o = Path(a.out); o.mkdir(parents=True, exist_ok=True)
    out.to_csv(o / "dataset_clean.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    rej.to_csv(o / "rejects.csv", index=False); conf.to_csv(o / "conflicts_for_review.csv", index=False)
    lines = ["# Cleaning report", "", f"- Input rows: {st['input_rows']}", f"- Kept: {st['kept']}", f"- Rejected: {st['rejected']}", "", "## Rejected by reason"]
    lines += [f"- {k}: {v}" for k, v in st["reject_reasons"].items()]
    lines += ["", f"Label counts (pipeline: distracting = export label 0): {st['label_counts']}", f"Languages: {st['language_counts']}",
              f"Rows with a thumbnail URL: {st['with_image']}  |  groups: {st['groups']}", f"Curriculum basis: {st['curriculum_basis']}",
              "", "Curriculum columns are automatic reference columns, not ground truth."]
    (o / "cleaning_report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
