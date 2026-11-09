/* Helpers for the subject catalog (subject-catalog.js). Loaded by the popup and the content script.
 * Tests load both files into one Node vm context, the same way the browser does. */
(function (root) {
  // subject-catalog.js declares these with const, so they are visible by name (not as window properties).
  const SUBJECTS_ = () => SUBJECTS;
  const LEGACY_ = () => LEGACY_SUBJECT_IDS;
  const PROGRAM_CONTEXTS_ = () => PROGRAM_CONTEXTS;

  // The program <select> stores "Computer Science", "Information Technology" or "Both".
  function programKey(value) {
    if (value === "Information Technology" || value === "IT") return "IT";
    if (value === "Both") return "Both";
    return "CS";
  }
  function inProgram(subject, program) {
    const key = programKey(program);
    return key === "Both" || subject.programs.includes(key);
  }
  function subjectsForProgram(program) { return SUBJECTS_().filter((s) => inProgram(s, program)); }
  function subjectLabel(subject, program) {
    const key = programKey(program);
    return subject.labels[key] || subject.labels.Both;
  }
  function subjectById(id) { return SUBJECTS_().find((s) => s.id === id) || null; }

  // Old (0.2.x) ids such as "cs-programming" are mapped to the new ids. Unknown ids are dropped.
  function normalizeSelection(ids) {
    const known = new Set(SUBJECTS_().map((s) => s.id));
    const legacy = LEGACY_();
    return [...new Set((ids || []).map((id) => legacy[id] || id).filter((id) => known.has(id)))];
  }
  // Keep only the selected ids that exist in the chosen program.
  function selectionForProgram(ids, program) {
    const valid = new Set(subjectsForProgram(program).map((s) => s.id));
    return normalizeSelection(ids).filter((id) => valid.has(id));
  }
  function selectedKeywords(ids) {
    const chosen = new Set(normalizeSelection(ids));
    return SUBJECTS_().filter((s) => chosen.has(s.id)).flatMap((s) => s.keywords);
  }
  // ---------- keyword focus ----------
  // A focus is a list of {term, subjects:[ids]}. It narrows the chosen subjects down to what the student typed (e.g. "c++").
  const MAX_FOCUS = 5;
  function normalizeFocus(list) {
    const known = new Set(SUBJECTS_().map((s) => s.id));
    const seen = new Set(), out = [];
    for (const f of Array.isArray(list) ? list : []) {
      const term = String((f && f.term) || "").replace(/\s+/g, " ").trim().slice(0, 60);
      if (term.length < 2 || seen.has(term.toLowerCase())) continue;
      seen.add(term.toLowerCase());
      out.push({ term, subjects: [...new Set(normalizeSelection((f && f.subjects) || []))].filter((id) => known.has(id)).slice(0, 3) });
      if (out.length >= MAX_FOCUS) break;
    }
    return out;
  }
  function addFocus(list, term, subjects) { return normalizeFocus([...normalizeFocus(list), { term, subjects }]); }
  function removeFocus(list, term) { return normalizeFocus(list).filter((f) => f.term.toLowerCase() !== String(term).toLowerCase()); }
  function focusKeywords(list) { return normalizeFocus(list).map((f) => f.term); }
  // Subjects a typed focus term belongs to: the best matching subjects of the program (score >= 35), at most 3.
  function focusSubjectsForQuery(query, program) {
    return searchSubjects(query, program, 8).filter((r) => r.inProgram && r.score >= 35).slice(0, 3).map((r) => r.id);
  }
  // The subjects the model scores against: the focus term's subjects when a focus is set, otherwise the checklist.
  function effectiveSubjects(ids, focus) {
    const f = normalizeFocus(focus);
    const fromFocus = [...new Set(f.flatMap((x) => x.subjects))];
    return f.length && fromFocus.length ? fromFocus : normalizeSelection(ids);
  }

  // Short text describing the student's declared subjects (or keyword focus). The backend embeds it as the
  // "session context vector". tools/subject_context.py builds the identical text for the training data.
  function contextString(ids, program, focus) {
    const f = normalizeFocus(focus);
    const chosen = new Set(effectiveSubjects(ids, f));
    const subjects = SUBJECTS_().filter((s) => chosen.has(s.id));
    const labels = subjects.map((s) => subjectLabel(s, program)).join("; ");
    if (f.length) return (`focus: ${f.map((x) => x.term).join(", ")}` + (labels ? ` | ${labels}` : "")).slice(0, 400);
    // No subject selected: describe the whole program, the same text the training data uses.
    if (!subjects.length) return PROGRAM_CONTEXTS_()[programKey(program)] || "";
    const keywords = [...new Set(subjects.flatMap((s) => s.keywords))].slice(0, 40).join(", ");
    return `${labels}: ${keywords}`.slice(0, 400);
  }

  // ---------- recommendations ----------
  // Syllabus topics of the selected subjects. `round` rotates which topics are shown so that
  // "More ideas" in the popup reveals the next ones.
  function recommendTopics(ids, program, { perSubject = 5, round = 0 } = {}) {
    const chosen = new Set(normalizeSelection(ids));
    return SUBJECTS_().filter((s) => chosen.has(s.id) && inProgram(s, program)).map((s) => {
      const titles = s.topics.map(([title]) => title);
      const draftTitles = new Set(s.topics.filter((t) => t[2]).map((t) => t[0]));
      const n = titles.length;
      const picked = [];
      for (let i = 0; i < Math.min(perSubject, n); i++) picked.push(titles[(round * perSubject + i) % n]);
      const unique = [...new Set(picked)];
      return { id: s.id, label: subjectLabel(s, program), topics: unique, total: n, draft: unique.some((t) => draftTitles.has(t)) };
    });
  }
  function youtubeSearchUrl(topic, label) {
    const short = String(label || "").replace(/\s*\(.*?\)\s*/g, " ").replace(/\s+\d+\s*&\s*\d+\s*$/, "").trim();
    return "https://www.youtube.com/results?search_query=" + encodeURIComponent(`${topic} ${short}`.trim());
  }

  // Where a suggested-topic chip searches: the site the student is on, YouTube, Google, Google Scholar or arXiv.
  // Sites whose own search address is well known use it; every other site is searched through Google with "site:host".
  const SITE_SEARCH = {
    "youtube.com": null,
    "arxiv.org": (q) => "https://arxiv.org/search/?searchtype=all&query=" + q,
    "wikipedia.org": (q, h) => `https://${h}/w/index.php?search=${q}`,
    "github.com": (q) => "https://github.com/search?q=" + q,
    "stackoverflow.com": (q) => "https://stackoverflow.com/search?q=" + q,
    "medium.com": (q) => "https://medium.com/search?q=" + q,
    "dev.to": (q) => "https://dev.to/search?q=" + q,
    "semanticscholar.org": (q) => "https://www.semanticscholar.org/search?q=" + q,
  };
  function searchUrl(where, host, topic, label) {
    const q = encodeURIComponent(String(topic || "").trim());
    const h = String(host || "").toLowerCase().replace(/^www\./, "");
    if (where === "google") return "https://www.google.com/search?q=" + q;
    if (where === "scholar") return "https://scholar.google.com/scholar?q=" + q;
    if (where === "arxiv") return SITE_SEARCH["arxiv.org"](q);
    if (where === "site" && h && /^[a-z0-9.-]+\.[a-z]{2,}$/.test(h) && h !== "localhost" && !/^google\./.test(h)) {
      if (/(^|\.)youtube\.com$/.test(h)) return youtubeSearchUrl(topic, label);
      if (/^scholar\.google\./.test(h)) return "https://scholar.google.com/scholar?q=" + q;
      const key = Object.keys(SITE_SEARCH).find((k) => SITE_SEARCH[k] && (h === k || h.endsWith("." + k)));
      if (key) return SITE_SEARCH[key](q, h);
      return "https://www.google.com/search?q=" + encodeURIComponent(`${String(topic).trim()} site:${h}`);
    }
    return youtubeSearchUrl(topic, label);
  }
  function searchSiteName(where, host) {
    const h = String(host || "").toLowerCase().replace(/^www\./, "");
    if (where === "google") return "Google"; if (where === "scholar") return "Google Scholar"; if (where === "arxiv") return "arXiv";
    if (where === "site" && h && h !== "localhost" && /^[a-z0-9.-]+\.[a-z]{2,}$/.test(h)) return h;
    return "YouTube";
  }

  // ---------- search ----------
  function norm(value) {
    return String(value || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9+#]+/g, " ").trim();
  }
  const esc = (v) => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  function phraseRegex(q) { return new RegExp(`(^| )${esc(q)}(s|es)?( |$)`); }

  function searchSubjects(query, program, limit = 8) {
    const q = norm(query);
    if (q.length < 2) return [];
    const words = q.split(" ");
    const phrase = phraseRegex(q);
    const results = [];
    for (const s of SUBJECTS_()) {
      let score = 0;
      const matches = [];
      const labels = [...new Set(Object.values(s.labels).filter(Boolean))];
      const bag = new Set();
      labels.forEach((l) => norm(l).split(" ").forEach((w) => bag.add(w)));
      for (const l of labels) {
        const nl = norm(l);
        if (phrase.test(nl)) score = Math.max(score, 100);
        else if (q.length >= 3 && nl.includes(q)) score = Math.max(score, 55);
      }
      for (const k of s.keywords) {
        const nk = norm(k);
        nk.split(" ").forEach((w) => bag.add(w));
        if (nk === q) { score = Math.max(score, 95); matches.push({ kind: "keyword", text: k }); }
        else if (phrase.test(nk)) { score = Math.max(score, 70); matches.push({ kind: "keyword", text: k }); }
        else if (q.length >= 3 && nk.includes(q)) { score = Math.max(score, 35); matches.push({ kind: "keyword", text: k }); }
      }
      const topicHits = [];
      for (const [title, detail] of s.topics) {
        const nt = norm(title), nd = norm(detail);
        nt.split(" ").concat(nd.split(" ")).forEach((w) => bag.add(w));
        let t = 0;
        if (phrase.test(nt)) t = 90;
        else if (phrase.test(nd)) t = 60;
        else if (q.length >= 3 && nt.includes(q)) t = 45;
        else if (q.length >= 3 && nd.includes(q)) t = 30;
        else if (words.length > 1 && words.every((w) => nt.includes(w) || nd.includes(w))) t = 40;
        if (t) { topicHits.push({ kind: "topic", text: title, t }); score = Math.max(score, t); }
      }
      topicHits.sort((a, b) => b.t - a.t).slice(0, 3).forEach((h) => matches.push(h));
      // Several words that are each found somewhere in the subject (not necessarily together).
      if (!score && words.length > 1) {
        const found = words.filter((w) => bag.has(w) || (w.length >= 3 && [...bag].some((b) => b.startsWith(w)))).length;
        if (found === words.length) score = 25;
      }
      if (score) results.push({ id: s.id, label: subjectLabel(s, program), score, inProgram: inProgram(s, program), programs: s.programs, matches: matches.slice(0, 3) });
    }
    return results.sort((a, b) => (b.inProgram - a.inProgram) || (b.score - a.score) || a.label.localeCompare(b.label)).slice(0, limit);
  }

  const api = { programKey, inProgram, subjectsForProgram, subjectLabel, subjectById, normalizeSelection, selectionForProgram,
                selectedKeywords, contextString, recommendTopics, youtubeSearchUrl, searchUrl, searchSiteName, searchSubjects,
                normalizeFocus, addFocus, removeFocus, focusKeywords, focusSubjectsForQuery, effectiveSubjects, MAX_FOCUS };
  root.SubjectTools = api;
})(typeof self !== "undefined" ? self : globalThis);
