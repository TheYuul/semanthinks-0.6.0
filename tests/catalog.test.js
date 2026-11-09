// Run: node tests/catalog.test.js
const fs = require("fs"), vm = require("vm"), path = require("path"), assert = require("assert");
const ext = path.join(__dirname, "..", "extension");
const ctx = {}; vm.createContext(ctx);
for (const f of ["subject-catalog.js", "subject-tools.js"]) vm.runInContext(fs.readFileSync(path.join(ext, f), "utf8"), ctx, { filename: f });
vm.runInContext("this.T = SubjectTools; this.S = SUBJECTS;", ctx);
const T = ctx.T, S = ctx.S;
const J = JSON.stringify; // arrays from the vm context have another prototype, so compare as JSON
let n = 0; const ok = (name, fn) => { fn(); n++; console.log("ok -", name); };

ok("program lists: CS, IT and Both", () => {
  const cs = T.subjectsForProgram("Computer Science"), it = T.subjectsForProgram("Information Technology"), both = T.subjectsForProgram("Both");
  assert.strictEqual(cs.length, 29); assert.strictEqual(it.length, 24); assert.strictEqual(both.length, S.length);
  const union = new Set([...cs, ...it].map((s) => s.id));
  assert.strictEqual(union.size, both.length, "Both must be exactly CS union IT, with shared subjects listed once");
  assert.strictEqual(new Set(both.map((s) => s.id)).size, both.length, "no duplicate ids");
});
ok("IT checklist has no minor/GE subjects", () => {
  const labels = T.subjectsForProgram("Information Technology").map((s) => s.labels.IT.toLowerCase());
  for (const bad of ["ethics", "rizal", "physical", "national service", "art appreciation", "environmental", "contemporary world", "science, technology"])
    assert(!labels.some((l) => l.includes(bad)), "found minor subject: " + bad);
});
ok("labels differ per program, Both uses the combined label", () => {
  const d = T.subjectById("discrete");
  assert.strictEqual(T.subjectLabel(d, "Computer Science"), "Discrete Structures 1 & 2");
  assert.strictEqual(T.subjectLabel(d, "Information Technology"), "Discrete Mathematics");
  assert.strictEqual(T.subjectLabel(d, "Both"), "Discrete Structures / Mathematics");
});
ok("legacy ids are migrated, unknown ids dropped, duplicates merged", () => {
  assert.strictEqual(J(T.normalizeSelection(["cs-programming", "it-programming", "cs-automata", "nope"])), J(["programming", "automata"]));
});
ok("switching program keeps only valid selections", () => {
  assert.strictEqual(J(T.selectionForProgram(["automata", "programming", "web"], "Information Technology")), J(["programming", "web"]));
  assert.strictEqual(J(T.selectionForProgram(["automata", "programming", "web"], "Computer Science")), J(["automata", "programming"]));
});
ok("search: 'regular expression' finds Automata first", () => {
  const r = T.searchSubjects("Regular Expression", "Computer Science");
  assert.strictEqual(r[0].id, "automata"); assert(r[0].inProgram);
});
ok("search from IT still finds Automata, flagged as outside the program", () => {
  const r = T.searchSubjects("regular expression", "Information Technology");
  const a = r.find((x) => x.id === "automata"); assert(a && !a.inProgram);
});
ok("search: partial words, plurals, case, Tagalog keyword", () => {
  assert.strictEqual(T.searchSubjects("autom", "Both")[0].id, "automata");
  assert(T.searchSubjects("linked lists", "Both").some((x) => x.id === "data-structures"));
  assert(T.searchSubjects("SQL", "Both").some((x) => x.id === "database"));
  assert(T.searchSubjects("seguridad", "Both").some((x) => x.id === "security"));
});
ok("search: syllabus topic text is searchable and reported", () => {
  const r = T.searchSubjects("pushdown", "Both");
  assert.strictEqual(r[0].id, "automata"); assert(r[0].matches.some((m) => m.kind === "topic"));
  const c = T.searchSubjects("cache memory", "Both"); assert.strictEqual(c[0].id, "architecture");
});
ok("search: nonsense and one-letter queries return nothing", () => {
  assert.strictEqual(T.searchSubjects("zzzqqqxx", "Both").length, 0);
  assert.strictEqual(T.searchSubjects("a", "Both").length, 0);
});
ok("recommendations come from the syllabus and rotate", () => {
  const r0 = T.recommendTopics(["automata", "web"], "Both", { perSubject: 3, round: 0 });
  assert.strictEqual(r0.length, 2);
  const au = r0.find((x) => x.id === "automata"); assert.strictEqual(au.topics.length, 3); assert.strictEqual(au.total, 5);
  assert.strictEqual(au.draft, false, "official syllabus topics are not flagged as drafts");
  const web = r0.find((x) => x.id === "web"); assert.strictEqual(web.topics.length, 3); assert.strictEqual(web.draft, true, "drafted subjects are flagged");
  const r1 = T.recommendTopics(["automata"], "Both", { perSubject: 3, round: 1 });
  assert.notStrictEqual(J(r1[0].topics), J(au.topics));
  const all = new Set(S.find((s) => s.id === "automata").topics.map((t) => t[0]));
  r1[0].topics.forEach((t) => assert(all.has(t)));
});
ok("context string: labels + keywords, capped", () => {
  const c = T.contextString(["database", "automata"], "Computer Science");
  assert(c.startsWith("Database Management Systems; Automata Theory & Formal Languages:")); assert(c.length <= 400);
  assert(T.contextString([], "Information Technology").startsWith("Information Technology: ") && T.contextString([], "Both").length <= 400);
  assert.notStrictEqual(T.contextString([], "Computer Science"), T.contextString([], "Information Technology"));
});
ok("youtube search url", () => {
  const u = T.youtubeSearchUrl("Cache Memory", "Architecture & Organization");
  assert(u.startsWith("https://www.youtube.com/results?search_query=Cache%20Memory%20Architecture"));
});
ok("search url: current site, known site search, unknown site through Google site:, fallbacks", () => {
  const dec = (u) => decodeURIComponent(u);
  assert(T.searchUrl("site", "arxiv.org", "Finite Automata", "x").startsWith("https://arxiv.org/search/?searchtype=all&query=Finite%20Automata"));
  assert(T.searchUrl("site", "en.wikipedia.org", "Cache Memory", "x").startsWith("https://en.wikipedia.org/w/index.php?search=Cache%20Memory"));
  assert.strictEqual(dec(T.searchUrl("site", "www.scribd.com", "SQL joins", "x")), "https://www.google.com/search?q=SQL joins site:scribd.com");
  assert(T.searchUrl("site", "www.youtube.com", "Cache Memory", "Architecture").startsWith("https://www.youtube.com/results?search_query="));
  assert(T.searchUrl("site", "", "Cache", "x").startsWith("https://www.youtube.com/results"), "no site -> YouTube");
  assert(T.searchUrl("site", "localhost", "Cache", "x").startsWith("https://www.youtube.com/results"));
  assert(T.searchUrl("scholar", "arxiv.org", "Cache", "x").startsWith("https://scholar.google.com/scholar?q=Cache"));
  assert(T.searchUrl("google", "", "C++ pointers", "x").endsWith("q=C%2B%2B%20pointers"));
  assert.strictEqual(T.searchSiteName("site", "www.scribd.com"), "scribd.com"); assert.strictEqual(T.searchSiteName("site", ""), "YouTube");
});
ok("every subject has topics; official ones are kept and come first", () => {
  assert(S.every((s) => s.topics.length >= 5), "a subject has fewer than 5 topics");
  const official = S.reduce((n, s) => n + s.topics.filter((t) => t.length === 2).length, 0);
  assert(official >= 200, "official topics were lost: " + official);
  const a = S.find((s) => s.id === "software-engineering").topics; assert.strictEqual(a[0].length, 2); assert.strictEqual(a[a.length - 1].length, 3);
});
ok("search finds drafted subjects (the adviser's database indexing example)", () => {
  assert.strictEqual(T.searchSubjects("database indexing", "Both")[0].id, "database");
  assert(T.searchSubjects("subnetting", "Both").some((x) => x.id === "networks"));
  assert(T.searchSubjects("kotlin", "Information Technology").some((x) => x.id === "mobile"));
});
ok("keyword focus: normalization, effective subjects, context text and fallback keywords", () => {
  const f = T.addFocus([], "  c++  ", ["programming", "nonsense"]);
  assert.strictEqual(f.length, 1); assert.strictEqual(f[0].term, "c++"); assert.deepStrictEqual(JSON.parse(JSON.stringify(f[0].subjects)), ["programming"]);
  assert.strictEqual(T.addFocus(f, "C++", []).length, 1, "duplicate terms (case-insensitive) are ignored");
  assert.strictEqual(T.normalizeFocus(Array.from({ length: 9 }, (_, i) => ({ term: "term" + i }))).length, T.MAX_FOCUS);
  assert.strictEqual(T.removeFocus(f, "C++").length, 0);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(T.effectiveSubjects(["database"], f))), ["programming"], "focus narrows the subjects");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(T.effectiveSubjects(["database"], []))), ["database"]);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(T.effectiveSubjects(["database"], [{ term: "x", subjects: [] }]))), ["database"], "a focus without subjects keeps the checklist");
  assert.strictEqual(T.contextString(["database"], "Both", f), "focus: c++ | Computer Programming 1 & 2");
  assert.strictEqual(T.contextString(["database"], "Information Technology", [{ term: "sql", subjects: [] }]), "focus: sql | Database Management Systems");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(T.focusKeywords(f))), ["c++"]);
  assert(T.focusSubjectsForQuery("c++ programming", "Both").includes("programming"));
  assert(T.focusSubjectsForQuery("regular expression", "Computer Science").includes("automata"));
});
console.log(`\n${n} tests passed`);
