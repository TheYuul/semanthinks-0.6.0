// Run: node tests/popup.e2e.js   (needs the preinstalled Playwright + Chromium)
const { chromium } = require("playwright"); const path = require("path"); const assert = require("assert");
const url = "file://" + path.join(__dirname, "..", "extension", "popup.html");
const stub = () => {
  const store = { sync: {}, local: {} }; window.__created = []; window.__store = store;
  const get = (area) => async (defaults) => ({ ...(typeof defaults === "object" ? defaults : {}), ...store[area] });
  window.chrome = {
    storage: { sync: { get: get("sync"), set: async (o) => Object.assign(store.sync, o) }, local: { get: get("local"), set: async (o) => Object.assign(store.local, o) }, onChanged: { addListener() {} } },
    tabs: { query: async () => [], sendMessage: async () => null, create: (o) => window.__created.push(o.url) },
    runtime: { sendMessage: async () => ({ ok: false }) },
  };
};
(async () => {
  const browser = await chromium.launch(); const page = await browser.newPage({ viewport: { width: 390, height: 900 }, deviceScaleFactor: 2 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message)); page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.addInitScript(stub); await page.goto(url);
  const count = () => page.locator("#subjectList input").count();
  let n = 0; const ok = (m) => console.log("ok -", m, ++n && "");
  assert.strictEqual(await count(), 29); ok("CS lists 29 subjects");
  await page.selectOption("#subject", "Information Technology"); assert.strictEqual(await count(), 24); ok("IT lists 24 subjects");
  const itText = await page.locator("#subjectList").innerText(); assert(!/Ethics|Rizal/.test(itText)); ok("IT list has no minor subjects");
  await page.selectOption("#subject", "Both"); assert.strictEqual(await count(), 37); ok("Both lists the combined 37");
  await page.selectOption("#subject", "Information Technology");
  await page.fill("#subjectSearch", "regular expression"); await page.waitForSelector(".result");
  const first = await page.locator(".result").first().innerText(); assert(/Automata Theory/.test(first) && /not in your selected program/.test(first)); ok("IT search finds Automata, flagged as CS-only");
  await page.locator(".result button").first().click();
  await page.waitForFunction(() => document.querySelector("#subject").value === "Both"); ok("button switched the program to Both");
  assert(await page.locator("#subjectList input[value=automata]").isChecked()); ok("Automata is now checked");
  const rec = await page.locator("#recommendations").innerText(); assert(/Automata Theory & Formal Languages/.test(rec) && /Finite Automata|Turing/.test(rec)); ok("recommendations show syllabus topics");
  await page.locator(".chip", { hasText: "Finite Automata" }).first().click();
  const created = await page.evaluate(() => window.__created); assert(created[0].includes("youtube.com/results?search_query=Finite%20Automata")); ok("topic chip opens a YouTube search");
  await page.locator("#subjectList input[value=database]").check();
  assert(/Database Management Systems/.test(await page.locator("#recommendations").innerText()));
  const recText = await page.locator("#recommendations").innerText();
  assert(/Database Indexing|Normalization|Entity-Relationship/.test(recText) && /drafts/.test(recText)); ok("drafted subject shows topics with a draft notice");
  await page.selectOption("#subject", "Computer Science");
  const saved = await page.evaluate(() => window.__store.sync.selectedSubjects); assert(saved.includes("automata") && saved.includes("database")); ok("switching program keeps valid selections");
  await page.fill("#subjectSearch", "zzzqq"); await page.waitForSelector(".search-note"); ok("no-match message");
  await page.fill("#subjectSearch", "c++ programming"); await page.waitForFunction(() => /c\+\+ programming/.test(document.querySelector("#focusOnQuery")?.textContent || ""));
  assert(/Focus only on/.test(await page.locator("#focusOnQuery").innerText())); ok("search offers 'Focus only on ...'");
  await page.click("#focusOnQuery"); await page.waitForSelector(".focus-chip");
  const fs_ = await page.evaluate(() => window.__store.sync.focusTerms);
  assert.strictEqual(fs_.length, 1); assert.strictEqual(fs_[0].term, "c++ programming"); assert(fs_[0].subjects.includes("programming")); ok("focus chip saved with its subject");
  assert(/c\+\+ programming/.test(await page.locator("#focusChips").innerText())); assert.strictEqual(await page.locator("#searchResults #focusOnQuery").count(), 0); ok("focus shown as a chip, search cleared");
  await page.click(".focus-chip"); assert.strictEqual((await page.evaluate(() => window.__store.sync.focusTerms)).length, 0); ok("chip click removes the focus");
  await page.fill("#subjectSearch", "database"); await page.waitForSelector(".result");
  await page.screenshot({ path: process.argv[2] || require("path").join(require("os").tmpdir(), "semanthinks-popup.png"), fullPage: true });
  // Topic chips search the site the student is on (second popup with an arXiv tab and a Scribd tab).
  for (const [tabUrl, expect] of [["https://arxiv.org/abs/2101.00001", "arxiv.org/search"], ["https://www.scribd.com/document/1/x", "site%3Ascribd.com"], ["chrome://extensions", "youtube.com/results"]]) {
    const p2 = await browser.newPage({ viewport: { width: 390, height: 900 } });
    await p2.addInitScript(stub); await p2.addInitScript((u) => { window.chrome.tabs.query = async () => [{ id: 1, url: u }]; }, tabUrl);
    await p2.goto(url); await p2.selectOption("#subject", "Computer Science"); await p2.locator("#subjectList input[value=automata]").check();
    await p2.locator(".chip").first().click(); const made = (await p2.evaluate(() => window.__created))[0];
    assert(made.includes(expect), `${tabUrl} -> ${made}`); ok(`topic chip on ${tabUrl.slice(0, 30)} opens ${expect}`);
    if (tabUrl.includes("arxiv")) { await p2.selectOption("#searchWhere", "youtube"); await p2.locator(".chip").first().click(); assert((await p2.evaluate(() => window.__created))[1].includes("youtube.com/results")); assert.strictEqual(await p2.evaluate(() => window.__store.sync.searchWhere), "youtube"); ok("choosing YouTube overrides the current site and is saved"); }
    await p2.close();
  }
  assert.deepStrictEqual(errors, [], "console errors: " + errors.join("; ")); ok("no console errors");
  await browser.close(); console.log(`\n${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
