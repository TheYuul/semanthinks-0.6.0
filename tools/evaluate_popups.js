// evaluate_popups.js - measures what the extension does with pop-ups and ads, using the REAL content script in a browser.
//
//   node tools/evaluate_popups.js                       # uses the real backend at http://localhost:8000 (start it first)
//   node tools/evaluate_popups.js --fake                # keyword stub instead of the model (for a quick self-check only)
//   node tools/evaluate_popups.js --subjects programming,database   # the student's chosen subjects (default)
//   NODE_PATH=$(npm root -g) node tools/evaluate_popups.js          # if Playwright is installed globally
//
// Each row of tools/popup_eval_set.csv is shown as a pop-up (role=dialog, fixed position) on a study page. The result "filter"
// means the extension hid it, "keep" means it stayed. expected = what a student on that subject should get.
// Positive class = filter. Writes results/popup_eval.md and results/popup_eval.json.
const { chromium } = require("playwright"); const fs = require("fs"); const path = require("path");
const args = process.argv.slice(2); const flag = (n, d) => { const i = args.indexOf(n); return i < 0 ? d : (args[i + 1] && !args[i + 1].startsWith("--") ? args[i + 1] : true); };
const FAKE = args.includes("--fake"); const BACKEND = flag("--backend", "http://localhost:8000"); const SUBJECTS = String(flag("--subjects", "programming,database")).split(",");
const root = path.join(__dirname, ".."); const ext = (f) => fs.readFileSync(path.join(root, "extension", f), "utf8");

function parseCsv(text) {
  const rows = []; let row = [], cur = "", q = false;
  for (let i = 0; i < text.length; i++) { const c = text[i];
    if (q) { if (c === '"' && text[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; }
    else if (c === '"') q = true; else if (c === ",") { row.push(cur); cur = ""; } else if (c === "\n") { row.push(cur); rows.push(row); row = []; cur = ""; } else if (c !== "\r") cur += c; }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  const [h, ...b] = rows; return b.filter((r) => r.length === h.length).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i]])));
}
const fakeModel = (t) => /casino|sneakers|gossip|weight loss|boracay|watches|fantasy battle|skincare|betting|fashion|pet food|cryptocurrency|concert|cook/i.test(t) ? "hide" : "allow";
async function realModel(msg) {
  const r = await fetch(`${BACKEND}/api/classify`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: msg.text, image_url: null, context: msg.context || null, subjects: msg.subjects || null }) });
  if (!r.ok) throw new Error("backend " + r.status); return r.json();
}

(async () => {
  const set = parseCsv(fs.readFileSync(path.join(__dirname, "popup_eval_set.csv"), "utf8"));
  if (!FAKE) { try { await realModel({ text: "test", context: "x", subjects: [] }); } catch (e) { console.error(`Cannot reach the backend at ${BACKEND} (${e.message}). Start it, or use --fake.`); process.exit(2); } }
  const browser = await chromium.launch(); const out = [];
  for (const row of set) {
    const page = await browser.newPage(); const url = "https://study.example.com/";
    await page.route(url + "**", (r) => r.fulfill({ contentType: "text/html", body: `<html><head><title>Study page</title></head><body><main><h1>Lecture notes</h1><p>Some course content here.</p></main>
      <div id="pop" role="dialog" style="position:fixed;top:120px;left:120px;width:460px;height:220px;background:#fff">${row.text.replace(/</g, "&lt;")}${row.has_password === "1" ? '<input type="password">' : ""}</div></body></html>` }));
    await page.exposeFunction("__classify", async (msg) => {
      try { if (FAKE) { const a = fakeModel(msg.text); return { ok: true, result: { block: a === "hide", action: a, score: a === "hide" ? 0.1 : 0.9, mode: "text" }, ms: 1 }; }
            const t0 = Date.now(); const result = await realModel(msg); return { ok: true, result, ms: Date.now() - t0 }; } catch (e) { return { ok: false }; }
    });
    await page.addInitScript((subjects) => {
      window.__pending = 0; window.__asked = 0;
      const sync = { enabled: true, subject: "Both", selectedSubjects: subjects, useModel: true, logDecisions: false, guardPages: false, hideYouTubeRecommendations: true };
      window.chrome = { runtime: { id: "x", lastError: null, onMessage: { addListener() {} }, sendMessage(msg, cb) {
          if (msg.type !== "classify") { cb && cb({ ok: true }); return; }
          window.__asked++; window.__pending++; window.__classify(msg).then((r) => { window.__pending--; cb && cb(r); }); } },
        storage: { sync: { get: async (d) => ({ ...d, ...sync }) }, onChanged: { addListener() {} } } };
    }, SUBJECTS);
    await page.goto(url);
    for (const f of ["subject-catalog.js", "subject-tools.js", "url-tools.js", "content.js"]) await page.addScriptTag({ content: ext(f) });
    await page.addStyleTag({ content: ext("content.css") });
    await page.waitForTimeout(500);
    for (let i = 0; i < 40 && await page.evaluate(() => window.__pending > 0); i++) await page.waitForTimeout(250);
    await page.waitForTimeout(250);
    const s = await page.evaluate(() => ({ hidden: /semanthinks-hidden/.test(document.querySelector("#pop").className), asked: window.__asked }));
    out.push({ ...row, result: s.hidden ? "filter" : "keep", askedModel: s.asked > 0 }); await page.close();
  }
  await browser.close();
  const m = (rows) => { const tp = rows.filter((r) => r.expected === "filter" && r.result === "filter").length, fn = rows.filter((r) => r.expected === "filter" && r.result === "keep").length,
      fp = rows.filter((r) => r.expected === "keep" && r.result === "filter").length, tn = rows.filter((r) => r.expected === "keep" && r.result === "keep").length;
    const f = (a, b) => (b ? a / b : NaN); const pr = f(tp, tp + fp), rc = f(tp, tp + fn);
    return { n: rows.length, correct: tp + tn, accuracy: f(tp + tn, rows.length), precision: pr, recall: rc, f1: f(2 * pr * rc, pr + rc), fpr: f(fp, fp + tn), tp, fp, fn, tn }; };
  const fmt = (x) => (Number.isNaN(x) ? "n/a" : x.toFixed(3));
  const kinds = [...new Set(out.map((r) => r.kind))]; const all = m(out);
  const lines = [`# Pop-up and ad evaluation (${FAKE ? "FAKE keyword stub, not the model" : "real backend"})`, "",
    `Study subjects: ${SUBJECTS.join(", ")}. ${out.length} labeled pop-ups from \`tools/popup_eval_set.csv\`. Positive class = filter (hide).`, "",
    "| Overall | n | accuracy | precision | recall | F1 | FPR |", "|---|---|---|---|---|---|---|", `| all | ${all.n} | ${fmt(all.accuracy)} | ${fmt(all.precision)} | ${fmt(all.recall)} | ${fmt(all.f1)} | ${fmt(all.fpr)} |`, "",
    "| Kind | n | expected | correct | wrongly hidden | wrongly kept | sent to model |", "|---|---|---|---|---|---|---|"];
  for (const k of kinds) { const r = out.filter((x) => x.kind === k); const c = m(r);
    lines.push(`| ${k} | ${r.length} | ${r[0].expected} | ${c.correct}/${c.n} | ${c.fp} | ${c.fn} | ${r.filter((x) => x.askedModel).length} |`); }
  const wrong = out.filter((r) => r.expected !== r.result);
  lines.push("", `## Mistakes (${wrong.length})`, ...wrong.map((r) => `- [${r.kind}] expected ${r.expected}, got ${r.result}${r.askedModel ? "" : " (model not asked)"}: ${r.text.slice(0, 110)}`));
  lines.push("", "Notes: the pop-up set was written by the project team/assistant, not scraped from real sites, so treat the numbers as a functional check of the decision logic. Sign-up/newsletter/app prompts are handled by rules (hidden regardless of topic); pop-ups with promotional wording are judged by the model against the student's subjects; pop-ups with neither kind of wording are left alone.");
  fs.mkdirSync(path.join(root, "results"), { recursive: true });
  fs.writeFileSync(path.join(root, "results", FAKE ? "popup_eval_fake.md" : "popup_eval.md"), lines.join("\n") + "\n");
  fs.writeFileSync(path.join(root, "results", FAKE ? "popup_eval_fake.json" : "popup_eval.json"), JSON.stringify({ overall: all, rows: out }, null, 1));
  console.log(lines.join("\n"));
})();
