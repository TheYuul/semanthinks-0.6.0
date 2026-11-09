// The backend address. It must match the host_permissions entry in manifest.json.
const BACKEND = "http://localhost:8000";

const DEFAULT_SETTINGS = {
  enabled: true,
  subject: "Computer Science",
  selectedSubjects: [],
  focusTerms: [],
  hideYouTubeRecommendations: true,
  hidePromotionalParagraphs: true,
  guardPages: true,
  useImages: true,
  useModel: true,
  logDecisions: true,
  // Repository mode: sites where paragraph filtering is off and a lighter set of rules is used.
  repositoryDomains: ["arxiv.org", "ieee.org", "acm.org", "pubmed.ncbi.nlm.nih.gov", "researchgate.net"]
};
const COUNTERS = { hiddenCount: 0, paragraphCount: 0 };
const MODEL_STATS = { modelChecked: 0, modelBlocked: 0, modelFailed: 0, modelMs: 0 };

chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.sync.get(DEFAULT_SETTINGS);
  await chrome.storage.sync.set(existing);
  const stats = await chrome.storage.local.get({ ...COUNTERS, ...MODEL_STATS });
  await chrome.storage.local.set(stats);
});

// Stat updates are queued one after another. Two messages that arrive together
// would otherwise both read the same old count and one of them would be lost.
let statsQueue = Promise.resolve();
function queueStats(update) {
  statsQueue = statsQueue.then(update).catch(() => {});
  return statsQueue;
}
function addToStats(defaults, delta) {
  return queueStats(async () => {
    const current = await chrome.storage.local.get(defaults);
    const next = {};
    for (const key of Object.keys(delta)) next[key] = current[key] + delta[key];
    await chrome.storage.local.set(next);
  });
}

// Calls the local backend. The content script asks this worker to do it, because a service
// worker uses the extension's host permission and is not limited by the web page's CORS rules.
async function callBackend(path, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${BACKEND}${path}`, { ...options, signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "incrementStats") {
    addToStats(COUNTERS, { hiddenCount: message.hidden || 0, paragraphCount: message.paragraphs || 0 }).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message.type === "resetStats") {
    queueStats(() => chrome.storage.local.set({ ...COUNTERS, ...MODEL_STATS })).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message.type === "classify") {
    const started = Date.now();
    callBackend("/api/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: message.text, image_url: message.imageUrl || null, context: message.context || null, subjects: message.subjects || null })
    }, 15000).then((result) => {
      const ms = Date.now() - started;
      addToStats(MODEL_STATS, { modelChecked: 1, modelBlocked: result.block ? 1 : 0, modelMs: ms });
      sendResponse({ ok: true, result, ms });
    }).catch(() => {
      addToStats(MODEL_STATS, { modelFailed: 1 });
      sendResponse({ ok: false });
    });
    return true;
  }
  if (message.type === "subjectsFor") {
    callBackend("/api/subjects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: message.text }) }, 4000)
      .then((r) => sendResponse({ ok: true, subjects: r.subjects || [] }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
  if (message.type === "modelHealth") {
    callBackend("/health", {}, 2000)
      .then((health) => sendResponse({ ok: true, loaded: Boolean(health.loaded) }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
});
