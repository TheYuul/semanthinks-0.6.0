/* Decision log and "report a wrong decision". Everything stays in this browser (chrome.storage.local) until the student
 * exports it. recordDecision() keeps the last 30 hidden or warned items; addReport() stores a report; toCsv() builds the export.
 * user_label uses the dataset convention: "relevant" = it should have been allowed, "distracting" = it should have been blocked. */
(function (root) {
  const KEY_R = "reports", KEY_D = "recentDecisions", MAX_R = 1000, MAX_D = 30;
  let chain = Promise.resolve();
  const queued = (fn) => { chain = chain.then(fn).catch(() => {}); return chain; };
  const trim = (s, n) => String(s || "").replace(/\s+/g, " ").trim().slice(0, n);
  const newId = (p) => p + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  function cleanUrl(u) { try { const x = new URL(u); return x.origin + x.pathname; } catch (_) { return ""; } }   // no query string or fragment

  function recordDecision(d) {
    return queued(async () => {
      const cur = (await chrome.storage.local.get({ [KEY_D]: [] }))[KEY_D];
      const rec = { id: newId("d"), ts: new Date().toISOString(), text: trim(d.text, 300), action: d.action, score: d.score, host: d.host || "", url: cleanUrl(d.url), context: trim(d.context, 200), source: d.source || "model", reported: false };
      if (rec.text.length < 3) return;
      await chrome.storage.local.set({ [KEY_D]: [rec, ...cur.filter((x) => !(x.text === rec.text && x.host === rec.host))].slice(0, MAX_D) });
    });
  }
  function addReport(r) {
    return queued(async () => {
      const store = await chrome.storage.local.get({ [KEY_R]: [], [KEY_D]: [] });
      const rep = { id: newId("r"), ts: new Date().toISOString(), host: r.host || "", url: cleanUrl(r.url), text: trim(r.text, 300), shown_action: r.shown_action || "", score: r.score ?? "", context: trim(r.context, 200),
                    user_label: r.user_label === "distracting" ? "distracting" : "relevant", source: r.source || "", note: trim(r.note, 200) };
      if (!rep.text) return;
      const reports = [rep, ...store[KEY_R].filter((x) => !(x.text === rep.text && x.host === rep.host && x.user_label === rep.user_label))].slice(0, MAX_R);
      const recent = store[KEY_D].map((x) => (r.decisionId && x.id === r.decisionId ? { ...x, reported: true } : x));
      await chrome.storage.local.set({ [KEY_R]: reports, [KEY_D]: recent });
    });
  }
  async function get() { const s = await chrome.storage.local.get({ [KEY_R]: [], [KEY_D]: [] }); return { reports: s[KEY_R], recent: s[KEY_D] }; }
  function clearReports() { return queued(() => chrome.storage.local.set({ [KEY_R]: [] })); }

  const COLS = ["id", "ts", "host", "url", "text", "user_label", "shown_action", "score", "context", "source", "note"];
  function cell(v) {
    let s = String(v ?? "");
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;           // a spreadsheet would run text that starts like a formula
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function toCsv(rows) { return [COLS.join(","), ...rows.map((r) => COLS.map((c) => cell(r[c])).join(","))].join("\r\n") + "\r\n"; }

  root.ReportTools = { recordDecision, addReport, get, clearReports, toCsv, COLS };
})(typeof self !== "undefined" ? self : globalThis);
