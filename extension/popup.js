const DEFAULTS = { searchWhere: "site", enabled: true, subject: "Computer Science", selectedSubjects: [], focusTerms: [], hideYouTubeRecommendations: true, hidePromotionalParagraphs: true, guardPages: true, blockSocial: true, blockPopups: true, blockVideoAds: true, useImages: true, useModel: true, logDecisions: true };
const fields = { enabled: document.querySelector("#enabled"), subject: document.querySelector("#subject"), hideYouTubeRecommendations: document.querySelector("#youtube"), hidePromotionalParagraphs: document.querySelector("#paragraphs"), guardPages: document.querySelector("#guardPages"), blockSocial: document.querySelector("#blockSocial"), blockPopups: document.querySelector("#blockPopups"), blockVideoAds: document.querySelector("#blockVideoAds"), useImages: document.querySelector("#useImages"), useModel: document.querySelector("#useModel"), logDecisions: document.querySelector("#logDecisions") };
const pageHidden = document.querySelector("#pageHidden");
const subjectList = document.querySelector("#subjectList");
const searchInput = document.querySelector("#subjectSearch");
const searchResults = document.querySelector("#searchResults");
const recommendations = document.querySelector("#recommendations");
const recHint = document.querySelector("#recHint");
const T = SubjectTools;
let settings = { ...DEFAULTS };
let recRound = 0;
let activeHost = "";   // the site in the current tab (needs the activeTab permission); empty on browser pages

async function activeTab() { const [tab] = await chrome.tabs.query({ active: true, currentWindow: true }); return tab; }
async function sendToPage(message) { const tab = await activeTab(); return tab?.id ? chrome.tabs.sendMessage(tab.id, message, { frameId: 0 }).catch(() => null) : null; }

async function saveSelection(ids) {
  settings.selectedSubjects = ids;
  await chrome.storage.sync.set({ selectedSubjects: ids });
}
// ---------- keyword focus (narrows the chosen subjects to a typed keyword such as "c++") ----------
async function saveFocus(list) {
  settings.focusTerms = T.normalizeFocus(list);
  await chrome.storage.sync.set({ focusTerms: settings.focusTerms });
  renderFocus(); renderSearch();
}
function renderFocus() {
  const chips = document.querySelector("#focusChips"); chips.replaceChildren();
  const list = T.normalizeFocus(settings.focusTerms);
  document.querySelector("#focusHint").hidden = list.length > 0;
  document.querySelector("#clearFocus").hidden = list.length === 0;
  list.forEach((f) => {
    const chip = document.createElement("button"); chip.type = "button"; chip.className = "chip focus-chip";
    const names = f.subjects.map((id) => { const s = T.subjectById(id); return s ? T.subjectLabel(s, settings.subject) : id; }).join("; ");
    chip.textContent = f.term + " ×"; chip.title = (names ? "Subject: " + names + ". " : "") + "Click to remove this focus";
    chip.addEventListener("click", () => saveFocus(T.removeFocus(settings.focusTerms, f.term)));
    chips.append(chip);
  });
}
async function toggleSubject(id, on) {
  const next = new Set(settings.selectedSubjects);
  on ? next.add(id) : next.delete(id);
  await saveSelection([...next]);
  renderSubjects(); renderRecommendations(); renderSearch();
}

function renderSubjects() {
  subjectList.replaceChildren();
  T.subjectsForProgram(settings.subject).forEach((subject) => {
    const row = document.createElement("label"); row.className = "subject-option";
    const input = document.createElement("input"); input.type = "checkbox"; input.value = subject.id; input.checked = settings.selectedSubjects.includes(subject.id);
    input.addEventListener("change", async () => {
      await saveSelection([...subjectList.querySelectorAll("input:checked")].map((checkbox) => checkbox.value));
      renderRecommendations(); renderSearch();
    });
    const text = document.createElement("span"); text.textContent = T.subjectLabel(subject, settings.subject);
    row.append(input, text); subjectList.append(row);
  });
}

// ---------- suggested topics (from the syllabus of the selected subjects) ----------
function renderRecommendations() {
  recommendations.replaceChildren();
  document.querySelector("#searchWhere").value = settings.searchWhere;
  document.querySelector("#searchWhereNote").textContent = "Opens a new tab: " + T.searchSiteName(settings.searchWhere, activeHost) + ".";
  const groups = T.recommendTopics(settings.selectedSubjects, settings.subject, { perSubject: 5, round: recRound });
  recHint.hidden = groups.length > 0;
  document.querySelector("#moreIdeas").hidden = !groups.some((g) => g.total > 5);
  groups.forEach((group) => {
    const box = document.createElement("div"); box.className = "rec-group";
    const heading = document.createElement("h3"); heading.textContent = group.label; box.append(heading);
    if (!group.topics.length) {
      const empty = document.createElement("div"); empty.className = "rec-empty"; empty.textContent = "Syllabus topics for this subject are not loaded yet."; box.append(empty);
    } else {
      const chips = document.createElement("div"); chips.className = "rec-chips";
      group.topics.forEach((topic) => {
        const chip = document.createElement("button"); chip.type = "button"; chip.className = "chip"; chip.textContent = topic; chip.title = "Search " + T.searchSiteName(settings.searchWhere, activeHost) + " for this topic";
        chip.addEventListener("click", () => chrome.tabs.create({ url: T.searchUrl(settings.searchWhere, activeHost, topic, group.label) }));
        chips.append(chip);
      });
      box.append(chips);
      if (group.draft) {
        const note = document.createElement("div"); note.className = "rec-empty"; note.textContent = "Some topics are drafts, not yet checked against the official syllabus.";
        box.append(note);
      }
    }
    recommendations.append(box);
  });
}

// ---------- search bar ----------
const meaningCache = new Map();   // query -> subjects the trained model relates it to
function askMeaning(query) {
  return new Promise((resolve) => {
    try { chrome.runtime.sendMessage({ type: "subjectsFor", text: query }, (r) => { void chrome.runtime.lastError; resolve(r && r.ok ? r.subjects : []); }); }
    catch (_) { resolve([]); }
  });
}
// When the word matching finds little, ask the model which subjects the phrase is about by meaning.
async function addMeaningResults(query, lexical) {
  if (lexical.length && lexical[0].score >= 55) return;
  if (!meaningCache.has(query)) meaningCache.set(query, await askMeaning(query));
  if (searchInput.value.trim() !== query) return;                    // the student kept typing
  const seen = new Set(lexical.map((r) => r.id));
  const extra = meaningCache.get(query).filter((m) => m.p >= 0.15 && !seen.has(m.id) && T.subjectById(m.id));
  if (!extra.length) return;
  searchResults.querySelectorAll(".meaning-block").forEach((n) => n.remove());
  const block = document.createElement("div"); block.className = "meaning-block";
  const note = document.createElement("p"); note.className = "search-note"; note.textContent = "Related by meaning (model suggestion):"; block.append(note);
  extra.slice(0, 3).forEach((m) => {
    const subject = T.subjectById(m.id);
    const selected = settings.selectedSubjects.includes(m.id);
    const row = document.createElement("div"); row.className = "result meaning";
    const main = document.createElement("div"); main.className = "result-main";
    const title = document.createElement("div"); title.className = "result-title"; title.textContent = T.subjectLabel(subject, settings.subject);
    const why = document.createElement("div"); why.className = "result-match"; why.textContent = `Model confidence ${Math.round(m.p * 100)}%`;
    main.append(title, why);
    const button = document.createElement("button"); button.type = "button"; button.textContent = selected ? "Added" : "Add"; if (selected) button.className = "added";
    button.addEventListener("click", async () => { await toggleSubject(m.id, !selected); });
    row.append(main, button); block.append(row);
  });
  searchResults.querySelectorAll(".meaning-block").forEach((n) => n.remove());
  searchResults.append(block);
}
function renderSearch() {
  searchResults.replaceChildren();
  const query = searchInput.value.trim();
  if (query.length < 2) return;
  const results = T.searchSubjects(query, settings.subject);
  addMeaningResults(query, results);
  if (!results.length) { const note = document.createElement("p"); note.className = "search-note"; note.textContent = "No subject or syllabus topic matches that search."; searchResults.append(note); }
  // Narrow to the typed keyword itself, whether or not it matches a subject.
  if (query.length <= 60 && !T.normalizeFocus(settings.focusTerms).some((f) => f.term.toLowerCase() === query.toLowerCase())) {
    const focusButton = document.createElement("button"); focusButton.type = "button"; focusButton.className = "focus-btn"; focusButton.id = "focusOnQuery";
    focusButton.textContent = `Focus only on “${query}”`;
    focusButton.addEventListener("click", async () => {
      const subjects = T.focusSubjectsForQuery(query, settings.subject);
      await saveFocus(T.addFocus(settings.focusTerms, query, subjects));
      searchInput.value = ""; renderSearch();
    });
    searchResults.append(focusButton);
  }
  results.forEach((result) => {
    const selected = settings.selectedSubjects.includes(result.id);
    const row = document.createElement("div"); row.className = "result" + (result.inProgram ? "" : " outside");
    const main = document.createElement("div"); main.className = "result-main";
    const title = document.createElement("div"); title.className = "result-title"; title.textContent = result.label;
    result.programs.forEach((program) => { const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = program; title.append(badge); });
    main.append(title);
    const shown = result.matches.map((m) => m.text).join(" · ");
    if (shown || !result.inProgram) {
      const match = document.createElement("div"); match.className = "result-match";
      match.textContent = (shown ? "Matches: " + shown : "") + (!result.inProgram ? (shown ? " — " : "") + "not in your selected program" : "");
      main.append(match);
    }
    const button = document.createElement("button"); button.type = "button";
    button.textContent = selected ? "Added" : result.inProgram ? "Add" : "Use Both + add";
    if (selected) button.className = "added";
    button.addEventListener("click", async () => {
      if (!result.inProgram) {
        settings.subject = "Both"; fields.subject.value = "Both";
        await chrome.storage.sync.set({ subject: "Both" });
      }
      await toggleSubject(result.id, !selected);
    });
    row.append(main, button); searchResults.append(row);
  });
}
let searchTimer;
searchInput.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(renderSearch, 120); });

const MODEL_STAT_KEYS = ["modelChecked", "modelBlocked", "modelFailed", "modelMs"];
async function renderModelStats() {
  const s = await chrome.storage.local.get({ modelChecked: 0, modelBlocked: 0, modelFailed: 0, modelMs: 0 });
  const el = document.querySelector("#modelStats");
  if (!s.modelChecked && !s.modelFailed) { el.textContent = "No model checks yet."; return; }
  const average = s.modelChecked ? Math.round(s.modelMs / s.modelChecked) : 0;
  el.textContent = `${s.modelChecked} checked, ${s.modelBlocked} hidden, average ${average} ms per check` + (s.modelFailed ? `, ${s.modelFailed} failed` : "") + ".";
}
async function renderModelStatus() {
  const el = document.querySelector("#modelStatus");
  const reply = await chrome.runtime.sendMessage({ type: "modelHealth" }).catch(() => null);
  if (reply?.ok && reply.loaded) { el.textContent = "Backend connected"; el.className = "status online"; }
  else if (reply?.ok) { el.textContent = "Backend loading"; el.className = "status"; }
  else { el.textContent = "Backend offline, using keyword rules"; el.className = "status offline"; }
}
async function render() {
  settings = { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
  // Older versions stored ids like "cs-programming" and cleared the list when the program changed.
  const cleaned = T.selectionForProgram(settings.selectedSubjects, settings.subject);
  if (cleaned.length !== settings.selectedSubjects.length || cleaned.some((id, i) => id !== settings.selectedSubjects[i])) await saveSelection(cleaned);
  settings.selectedSubjects = cleaned;
  Object.entries(fields).forEach(([key, field]) => { field.type === "checkbox" ? field.checked = settings[key] : field.value = settings[key]; });
  settings.focusTerms = T.normalizeFocus(settings.focusTerms);
  try { const tab = await activeTab(); activeHost = tab?.url ? new URL(tab.url).hostname : ""; if (!/^https?:/.test(tab?.url || "")) activeHost = ""; } catch (_) { activeHost = ""; }
  renderSubjects(); renderRecommendations(); renderSearch(); renderFocus();
  const stats = await chrome.storage.local.get({ hiddenCount: 0 }); document.querySelector("#hiddenCount").textContent = stats.hiddenCount;
  renderModelStats();
  renderModelStatus();
  const pageState = await sendToPage({ type: "getPageState" }); if (pageState) pageHidden.checked = pageState.hidden;
}
Object.entries(fields).forEach(([key, field]) => field.addEventListener("change", async () => {
  await chrome.storage.sync.set({ [key]: field.type === "checkbox" ? field.checked : field.value });
  if (key === "subject") {
    // Keep the subjects that also exist in the new program (for example Programming, Database) instead of clearing them.
    settings.subject = field.value;
    await saveSelection(T.selectionForProgram(settings.selectedSubjects, settings.subject));
    recRound = 0; renderSubjects(); renderRecommendations(); renderSearch();
  }
}));
pageHidden.addEventListener("change", () => sendToPage({ type: pageHidden.checked ? "applyFilter" : "restorePage" }));
document.querySelector("#clearFocus").addEventListener("click", () => saveFocus([]));
document.querySelector("#clearSubjects").addEventListener("click", async () => { await saveSelection([]); renderSubjects(); renderRecommendations(); renderSearch(); });
document.querySelector("#searchWhere").addEventListener("change", async (e) => { settings.searchWhere = e.target.value; await chrome.storage.sync.set({ searchWhere: settings.searchWhere }); renderRecommendations(); });
document.querySelector("#moreIdeas").addEventListener("click", () => { recRound += 1; renderRecommendations(); });
document.querySelector("#reset").addEventListener("click", async () => { await chrome.runtime.sendMessage({ type: "resetStats" }); render(); });
// Update only the counter. Rebuilding the whole popup on every count would reset the subject list scroll position.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.hiddenCount) document.querySelector("#hiddenCount").textContent = changes.hiddenCount.newValue ?? 0;
  if (MODEL_STAT_KEYS.some((key) => changes[key])) renderModelStats();
});
render();
