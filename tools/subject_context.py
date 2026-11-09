"""
subject_context.py - Python mirror of the context strings built in extension/subject-tools.js (contextString and
focusContext). The training data and the extension MUST produce identical text for the same choice, because the
cosine feature compares the item with this text. tests/test_labeling_tools.py checks parity against the JS.
"""
from build_catalog import PROGRAM_NAMES, program_contexts


class Contexts:
    def __init__(self, subjects, program="Both"):
        self.subjects = subjects
        self.by_id = {s["id"]: s for s in subjects}
        self.program = program
        self.program_text = program_contexts(subjects)[program]

    def label(self, sid):
        s = self.by_id[sid]
        return s["labels"].get(self.program) or s["labels"]["Both"]

    def subject_context(self, ids):
        chosen = [s for s in self.subjects if s["id"] in set(ids)]
        if not chosen:
            return self.program_text
        labels = "; ".join(self.label(s["id"]) for s in chosen)
        kws = ", ".join(list(dict.fromkeys(k for s in chosen for k in s["keywords"]))[:40])
        return f"{labels}: {kws}"[:400]

    def focus_context(self, terms, ids=()):
        terms = [t.strip() for t in terms if t and t.strip()]
        if not terms:
            return self.subject_context(ids)
        chosen = [s for s in self.subjects if s["id"] in set(ids)]
        labels = "; ".join(self.label(s["id"]) for s in chosen)
        return (f"focus: {', '.join(terms)}" + (f" | {labels}" if labels else ""))[:400]
