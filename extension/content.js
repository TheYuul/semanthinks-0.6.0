/* Semanthinks rule-based prototype. All detection remains on the current page. */
const ACADEMIC_TERMS = [
  "algorithm", "computer", "computer science", "computing", "programming", "software", "hardware", "database", "network", "security", "artificial intelligence", "machine learning", "data structure", "thesis", "research", "journal", "citation", "lecture", "university", "mathematics", "science", "physics", "chemistry", "biology", "engineering", "code", "javascript", "python", "web development",
  "pag-aaral", "pananaliksik", "kompyuter", "programa", "datos", "seguridad", "sistema", "kaalaman", "leksyon", "paaralan", "unibersidad", "pagsusuri", "teknolohiya"
];
// Pop-ups that ask the student to join, sign up, subscribe, install an app or turn on notifications. They are never study content,
// so they are hidden whatever the topic of the page is (the model is not asked: "relevant" does not make a sign-up wall useful).
const ENGAGEMENT_TERMS = ["join free", "requires a subscription", "subscription required", "subscribe to read", "institutional subscription", "personal subscription", "premium edition", "basic edition", "upgrade now", "upgrade to", "upgrade your", "sign in or register", "become a member", "members only", "join for free", "join now", "join researchgate", "sign up for free", "sign up free", "sign up to continue", "sign in to continue", "log in to continue", "create a free account", "create your free account", "create an account", "register now", "register for free", "subscribe to our newsletter", "join our newsletter", "get our newsletter", "get the app", "download our app", "download the app", "install our app", "turn on notifications", "enable notifications", "allow notifications", "free trial", "upgrade to premium", "go premium", "get premium", "unlock full access", "continue reading with", "mag-sign up", "sumali nang libre", "take a short survey", "take our survey", "take the survey", "complete a short survey", "share your feedback", "give us your feedback", "we would love your feedback", "rate your experience", "become a member", "join acm", "join the community", "get access to", "stay up to date with", "sign up for alerts", "email alerts"];
const PROMOTIONAL_TERMS = ["sponsored", "advertisement", "advertorial", "buy now", "shop now", "limited offer", "discount", "subscribe now", "sign up now", "affiliate", "promo code", "paid partnership", "patalastas", "i-click", "bumili na", "mga alok", "diskwento", "mag-subscribe", "sponsor"];
const DISTRACTING_TERMS = ["celebrity", "gossip", "viral", "prank", "reaction", "gameplay", "mukbang", "giveaway", "shorts", "trending", "chismis", "sikat", "nakakatawa", "challenge", "vlog", "music video", "movie trailer", "drama", "stream highlights"];
const DEFAULT_REPOSITORY_DOMAINS = ["arxiv.org", "ieee.org", "acm.org", "pubmed.ncbi.nlm.nih.gov", "researchgate.net"];
const SELECTORS = {
  // The watch-page sidebar (#secondary) is no longer hidden as a whole.
  // Its video cards are judged one by one in filterYoutubeCards().
  youtubeChrome: ["ytd-player-legacy-desktop-watch-ads-renderer", "#player-ads", "ytd-companion-slot-renderer", "ytd-action-companion-ad-renderer", "ytd-display-ad-renderer", "ytd-banner-promo-renderer", "ytd-statement-banner-renderer", "ytd-in-feed-ad-layout-renderer", ".ytp-ad-overlay-container", ".ytp-ad-overlay-slot", "ytd-merch-shelf-renderer", "ytd-promoted-sparkles-web-renderer", "ytd-ad-slot-renderer", "ytd-reel-shelf-renderer", "ytd-reel-item-renderer", "ytd-reel-video-renderer", "ytd-rich-shelf-renderer[is-shorts]", "ytd-rich-section-renderer:has(ytd-reel-shelf-renderer)", "grid-shelf-view-model:has(a[href^='/shorts/'])"],
  // yt-lockup-view-model is YouTube's newer card element. Check it against your
  // own YouTube layout with DevTools, because YouTube changes these tags often.
  youtubeCards: ["ytd-rich-item-renderer", "ytd-video-renderer", "ytd-compact-video-renderer", "ytd-grid-video-renderer", "yt-lockup-view-model"],
  generalAds: ["[id*='advert']", "[class*='advert']", "[id*='ad-container']", "[class*='ad-container']", "[class*='sponsor']", "[class*='promotion']", "[data-ad]", "[data-ad-slot]", "[id='google_vignette']", "[class*='google-vignette']", "[id^='google_ads_iframe']", "iframe[aria-label='Advertisement']", "iframe[title*='ad content' i]", "[data-google-av-adk]", ".GoogleActiveViewElement", "[data-asoch-targets^='ad']", "a[href*='googleads.g.doubleclick.net']", ".avp-floating-container.avp-fixed", "[id^='aniplayer_'][id$='Wrapper']", "video[src*='play.aniview.com']", "ins.adsbygoogle", "iframe[src*='doubleclick']", "iframe[src*='googlesyndication']", "iframe[src*='googleadservices']", "a[href*='rapidadexchange.com']", "a[href*='exoclick.com']", "a[href*='juicyads.com']", "a[href*='trafficjunky.com']", "a[href*='adsterra']", "img[src*='/extban/']", "iframe[src*='exoclick']", "iframe[src*='adsterra']"],
  articleChrome: ["article .related-posts", "article .recommended", "article .newsletter", "article .social-share", "main .related-posts", "main .newsletter", "aside.floatrecirc", "aside[class*='recirc']", "[data-testid*='recirc']", "[data-testid*='newsletter']"],
  repositoryChrome: [".related-content", ".related-articles", ".recommended-content", ".recommendations", ".publication-recommendations", ".ad-container", ".advertisement", ".subscription-prompt"]
};
const CARD_SELECTOR = SELECTORS.youtubeCards.join(",");
const OLD_CARD_SELECTOR = "ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, ytd-grid-video-renderer";

let settings = {};
let queued = false;
let sessionBypass = false;
let silentRun = false; // true while re-hiding after a settings change, so stats are not counted twice
let processed = new WeakSet();

// ---------- AI model client ----------
// The content script never talks to the backend directly. It asks the background worker, which calls
// http://localhost:8000. Results are cached by title and thumbnail, at most MODEL_CONCURRENCY requests
// are in flight, and after a failure the backend is left alone for BACKEND_RETRY_MS while the keyword
// rules take over.
const MODEL_CONCURRENCY = 4;
const BACKEND_RETRY_MS = 15000;
const MODEL_CACHE_LIMIT = 2000;
const modelCache = new Map();
const modelQueue = [];
let modelInFlight = 0;
let backendDownUntil = 0;

function requestFromBackground(message) {
  return new Promise((resolve) => {
    try {
      if (!chrome.runtime?.id) return resolve(null);
      chrome.runtime.sendMessage(message, (reply) => {
        void chrome.runtime.lastError; // read it so Chrome does not log an unchecked error
        resolve(reply || null);
      });
    } catch (_) {
      resolve(null);
    }
  });
}
// ---------- no flash before the verdict ----------
// While the model is on, YouTube cards that have no verdict yet are blurred by content.css (html[data-semanthinks-guard]).
// A card is released (data-semanthinks-done) as soon as it has a verdict. If the backend is slow (GUARD_SLOW_MS) the card's content is
// hidden, not just blurred, and comes back when the verdict says it is fine. If there is still no answer after GUARD_FINAL_MS the
// card is released, so a dead backend can never leave the page hidden (the keyword rules take over at that point).
const GUARD_SLOW_MS = window.__SEMANTHINKS_SLOW_MS || 6000;
const GUARD_FINAL_MS = window.__SEMANTHINKS_FINAL_MS || 20000;
function markDone(card) {
  card.dataset.semanthinksDone = "1";
  delete card.dataset.semanthinksSlow;
  card.classList.remove("semanthinks-pending");
  card.querySelectorAll(CARD_SELECTOR).forEach((n) => { n.dataset.semanthinksDone = "1"; });   // a card nested inside it is the same video
}
function armFailsafe(card) {
  if (card.dataset.semanthinksFirst) return;
  card.dataset.semanthinksFirst = "1";
  setTimeout(() => { if (card.isConnected && !card.dataset.semanthinksDone) card.dataset.semanthinksSlow = "1"; }, GUARD_SLOW_MS);
  setTimeout(() => { if (card.isConnected && !card.dataset.semanthinksDone) markDone(card); }, GUARD_FINAL_MS);
}
function updateGuard() {
  const on = Boolean(settings.enabled) && !sessionBypass && settings.useModel !== false && settings.hideYouTubeRecommendations !== false
    && location.hostname.includes("youtube.com") && Date.now() >= backendDownUntil;
  document.documentElement.toggleAttribute("data-semanthinks-guard", on);
}
function modelAvailable() { return settings.useModel !== false && Date.now() >= backendDownUntil; }
function askModel(text, imageUrl, context, subjects, card) {
  return new Promise((resolve) => { modelQueue.push({ text, imageUrl, context, subjects, card, resolve }); pumpModelQueue(); });
}
// Cards nearest the visible part of the page are judged first, so what the student sees is ready before what is far below.
function distanceFromViewport(card) {
  if (!card || !card.isConnected) return 1e9;
  const r = card.getBoundingClientRect();
  return r.bottom < 0 ? -r.bottom : r.top > innerHeight ? r.top - innerHeight : 0;
}
function pumpModelQueue() {
  while (modelInFlight < MODEL_CONCURRENCY && modelQueue.length) {
    if (modelQueue.length > 1) {
      let best = 0, bestD = Infinity;
      modelQueue.forEach((j, i) => { const d = distanceFromViewport(j.card); if (d < bestD) { bestD = d; best = i; } });
      modelQueue.unshift(...modelQueue.splice(best, 1));
    }
    const job = modelQueue.shift();
    if (Date.now() < backendDownUntil) { job.resolve(null); continue; }
    modelInFlight += 1;
    requestFromBackground({ type: "classify", text: job.text, imageUrl: job.imageUrl, context: job.context, subjects: job.subjects }).then((reply) => {
      modelInFlight -= 1;
      if (reply?.ok) job.resolve({ ...reply.result, ms: reply.ms });
      else { backendDownUntil = Date.now() + BACKEND_RETRY_MS; job.resolve(null); }
      pumpModelQueue();
    });
  }
}
// Only YouTube video thumbnails are sent. Channel avatars and other images are ignored.
function cardImageUrl(card) {
  if (settings.useImages === false) return null;      // text-only mode: no thumbnail is downloaded or scored
  const img = card.querySelector("img[src*='ytimg.com/vi']");
  const url = img ? (img.currentSrc || img.src) : "";
  return /^https?:/.test(url) ? url : null;
}

function normalized(value) { return (value || "").toLowerCase().replace(/\s+/g, " ").trim(); }

// Whole-word matching. A plain text.includes(term) lets short keywords match
// inside other words ("ai" in "explained", "ios" in "curiosity"). A trailing
// "s" or "es" is allowed so "tree" still matches "trees" and "class" matches "classes".
function escapeRegex(value) { return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
const termRegexCache = new Map();
function hasTerm(text, term) {
  let pattern = termRegexCache.get(term);
  if (!pattern) {
    pattern = new RegExp(`(^|[^a-z0-9])${escapeRegex(term)}(s|es)?($|[^a-z0-9])`, "i");
    termRegexCache.set(term, pattern);
  }
  return pattern.test(text);
}
function includesAny(text, terms) { return terms.some((term) => hasTerm(text, term)); }

// Content scripts can remain in an already-open tab for a moment after the
// extension is reloaded. In that situation Chrome removes the old runtime
// context, so extension messages must be treated as optional.
function sendRuntimeMessage(message) {
  try {
    if (!chrome.runtime?.id) return;
    const result = chrome.runtime.sendMessage(message);
    if (result?.catch) result.catch(() => {});
  } catch (_) {
    // The page will receive the current content script on its next refresh.
  }
}
// "Repository mode" means a research-repository site where paragraph filtering
// is off and a lighter set of page-chrome selectors is used. It is not an exemption list.
function isRepository() {
  const host = location.hostname.toLowerCase();
  return (settings.repositoryDomains || DEFAULT_REPOSITORY_DOMAINS).some((domain) => host === domain || host.endsWith(`.${domain}`));
}
// Subject ids are shared by CS and IT, so the selection works for "Both" too. Old 0.2.x ids are migrated.
// A keyword focus (e.g. "c++") narrows filtering to the typed terms; without one the whole subject checklist is used.
function selectedSubjectKeywords() {
  const focus = SubjectTools.focusKeywords(settings.focusTerms || []);
  return focus.length ? focus : SubjectTools.selectedKeywords(settings.selectedSubjects || []);
}
function sessionContext() { return SubjectTools.contextString(settings.selectedSubjects || [], settings.subject, settings.focusTerms || []); }
function sessionSubjects() { return SubjectTools.effectiveSubjects(settings.selectedSubjects || [], settings.focusTerms || []); }
function detectedSubjectName(result) {
  const top = result.detected_subjects && result.detected_subjects[0];
  const subject = top && top.p >= 0.4 && SubjectTools.subjectById(top.id);   // a low-confidence guess is not shown as a fact
  return subject ? SubjectTools.subjectLabel(subject, settings.subject) : "";
}
// This is a keyword score, not cosine similarity. The trained EmbeddingGemma
// pipeline will replace it in the final system.
function keywordRelevance(text) {
  const value = normalized(text);
  const academicHits = [...new Set([...ACADEMIC_TERMS, ...selectedSubjectKeywords()])].filter((term) => hasTerm(value, term)).length;
  const distractingHits = DISTRACTING_TERMS.filter((term) => hasTerm(value, term)).length;
  return Math.max(0, Math.min(1, 0.5 + academicHits * 0.14 - distractingHits * 0.18));
}
function saveOriginalStyle(element) {
  if (element.dataset.semanthinksHadInlineStyle !== undefined) return;
  element.dataset.semanthinksHadInlineStyle = element.hasAttribute("style") ? "true" : "false";
  element.dataset.semanthinksOriginalStyle = element.getAttribute("style") || "";
}
function currentState(element) {
  if (element.classList.contains("semanthinks-hidden") || element.classList.contains("semanthinks-paragraph-hidden")) return "hidden";
  return "visible";
}
function restore(element) {
  element.classList.remove("semanthinks-hidden", "semanthinks-paragraph-hidden", "semanthinks-warn");
  if (element.dataset.semanthinksHadInlineStyle === "true") element.setAttribute("style", element.dataset.semanthinksOriginalStyle || "");
  else element.removeAttribute("style");
  delete element.dataset.semanthinksHadInlineStyle;
  delete element.dataset.semanthinksOriginalStyle;
  delete element.dataset.semanthinksBy;
  delete element.dataset.semanthinksDone;
  delete element.dataset.semanthinksFirst;
  if ((element.title || "").startsWith("Semanthinks:")) element.removeAttribute("title");
}
function restoreAll() {
  document.documentElement.removeAttribute("data-semanthinks-unlock");
  document.querySelectorAll(".semanthinks-hidden, .semanthinks-paragraph-hidden").forEach(restore);
}
function applyTreatment(element, treatment, category, count = false) {
  if (!element) return false;
  if (location.hostname.includes("youtube.com") && element.closest("#masthead-container, ytd-masthead, ytd-guide-signin-promo-renderer")) return false;
  if (treatment === "show") { restore(element); return true; }
  if (currentState(element) === "hidden") return false;
  if (currentState(element) !== "visible") restore(element);
  saveOriginalStyle(element);
  element.classList.remove("semanthinks-hidden", "semanthinks-paragraph-hidden");
  element.classList.add(category === "Promotional paragraph" ? "semanthinks-paragraph-hidden" : "semanthinks-hidden");
  element.style.setProperty("display", "none", "important");
  element.style.setProperty("visibility", "hidden", "important");
  element.style.setProperty("pointer-events", "none", "important");
  // Nested advertising frames may re-render repeatedly. Count only actions
  // taken by the top-page script so the session statistic remains meaningful.
  if (count && !silentRun && window.top === window) sendRuntimeMessage({ type: "incrementStats", hidden: 1, paragraphs: category === "Promotional paragraph" ? 1 : 0 });
  return true;
}
function treatCandidate(element, category) {
  if (sessionBypass) return false;
  return applyTreatment(element, "hide", category, true);
}
function adContainer(element) {
  const container = element.closest("[id*='ad-container'], [class*='ad-container'], [id^='google_ads'], [id*='advert'], [class*='advert'], [class*='sponsor'], [class*='promotion']");
  if (container && container !== element) return container;
  const googleAd = element.closest("[data-google-av-adk], .GoogleActiveViewElement, [id='google_vignette'], [class*='google-vignette']");
  if (googleAd) return googleAd.closest("[id*='full-slot'], [class*='full-slot'], [class*='autoplay-in-motion']") || googleAd;
  const floatingVideoAd = element.closest(".avp-floating-container.avp-fixed, [id^='aniplayer_'][id$='Wrapper']");
  if (floatingVideoAd) return floatingVideoAd;
  const parent = element.parentElement;
  if (element.matches("iframe") && parent && parent.children.length <= 2 && !normalized(parent.textContent)) return parent;
  return element;
}
// Never hide a wrapper that contains the page's main content. A broad class rule
// such as [class*='promotion'] can otherwise match a container around the whole page.
function wrapsMainContent(element) {
  return element === document.body || element === document.documentElement || element.matches("main, article, [role='main']") || Boolean(element.querySelector("main, article, [role='main']"));
}
function cardTitleText(card) {
  const titleNode = card.querySelector("#video-title, a#video-title, h3 a, h3");
  return normalized(titleNode?.getAttribute("title") || titleNode?.textContent || "");
}
// The keyword rules from the earlier prototype. They are used when the AI model is switched off
// or the backend is not reachable.
function judgeCardByRules(card, title, focusKeywords) {
  if (focusKeywords.length && !includesAny(title, focusKeywords)) {
    treatCandidate(card, "Outside selected subjects");
    return;
  }
  if (!includesAny(title, ACADEMIC_TERMS) && includesAny(title, DISTRACTING_TERMS) && keywordRelevance(title) < 0.47) treatCandidate(card, "Distracting video");
}
const STRICT_ALLOW = 0.70;
function itemKind() { return location.hostname.includes("youtube.com") ? "video" : "result"; }
function applyModelResult(card, result) {
  // The thesis model returns action "allow", "warn" or "hide". Warned cards stay visible but are faded and marked.
  // On a search-results page whose own search was not judged on-topic, a borderline result is hidden instead (data-semanthinks-strict).
  // The bar is raised as well: a result must score at least STRICT_ALLOW (the engine's bar for a narrowed keyword focus) to stay.
  const strict = card.dataset.semanthinksStrict === "1";
  const action = strict && (result.action === "warn" || (result.action === "allow" && Number(result.score) < STRICT_ALLOW)) ? "hide" : result.action;
  const block = Boolean(result.block) || action === "hide";
  card.classList.toggle("semanthinks-warn", action === "warn");
  const looksLike = detectedSubjectName(result);
  if (card.classList.contains("semanthinks-warn")) {
    const note = `this ${itemKind()} may be off-topic for your focus${looksLike ? ` (looks like ${looksLike})` : ""}`;
    card.dataset.semanthinksWarn = note; card.title = "Semanthinks: " + note;
  } else { delete card.dataset.semanthinksWarn; }
  if (block) {
    if (treatCandidate(card, "Model: unrelated")) card.dataset.semanthinksBy = "model";
  } else if (card.dataset.semanthinksBy === "model" && currentState(card) === "hidden") {
    restore(card); // an earlier text-only verdict was replaced by a better one
  }
}
// Clicking a borderline (warned) item shows a short notice, since a tooltip needs a hover.
let warnToastTimer = 0;
function showWarnToast(text) {
  let host = document.getElementById("semanthinks-toast");
  if (!host) {
    host = document.createElement("div"); host.id = "semanthinks-toast"; host.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:2147483647;pointer-events:none;";
    host.attachShadow({ mode: "open" }).innerHTML = `<style>div{background:#1d2b4f;color:#fff;font:600 14px/1.4 Arial,sans-serif;padding:10px 16px;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.35);max-width:min(520px,90vw)}</style><div id="t"></div>`;
    (document.body || document.documentElement).append(host);
  }
  host.shadowRoot.getElementById("t").textContent = "Semanthinks: " + text; host.style.display = "block";
  clearTimeout(warnToastTimer); warnToastTimer = setTimeout(() => { host.style.display = "none"; }, 4500);
}
document.addEventListener("click", (event) => {
  const warned = event.target instanceof Element && event.target.closest(".semanthinks-warn");
  if (warned && warned.dataset.semanthinksWarn) showWarnToast(warned.dataset.semanthinksWarn);
}, true);
function judgeCardWithModel(card, displayTitle, signature) {
  const imageUrl = cardImageUrl(card);
  const context = sessionContext();
  const key = `${signature}|${imageUrl || ""}|${context}|${sessionSubjects().join(",")}`;
  armFailsafe(card);
  const cached = modelCache.get(key);
  if (cached) { applyModelResult(card, cached); markDone(card); return; }
  if (card.dataset.semanthinksPending === key) return; // already asked about this exact card
  card.dataset.semanthinksPending = key;
  card.classList.add("semanthinks-pending");
  askModel(displayTitle.slice(0, 300), imageUrl, context, sessionSubjects(), card).then((result) => {
    if (card.dataset.semanthinksPending === key) {
      delete card.dataset.semanthinksPending;
      card.classList.remove("semanthinks-pending");
    }
    if (!settings.enabled || settings.useModel === false) { markDone(card); return; }
    if (card.dataset.semanthinksSig !== signature) return; // YouTube reused this card for another video meanwhile
    if (!result) { judgeCardByRules(card, normalized(displayTitle), selectedSubjectKeywords()); markDone(card); updateGuard(); return; }
    if (modelCache.size >= MODEL_CACHE_LIMIT) modelCache.clear();
    modelCache.set(key, result);
    if (settings.logDecisions) console.info(`[Semanthinks] ${result.block ? "HIDE" : "keep"} | ${result.mode} | C=${result.score ?? result.p_related} | ${result.action || ""} | ${detectedSubjectName(result) || "-"} | ${result.ms} ms | ${displayTitle.slice(0, 80)}`);
    applyModelResult(card, result);
    markDone(card);
  });
}
// The model gets the title exactly as shown (same capital letters). Only the keyword rules use lowercase text.
function rawCardTitle(card) {
  const node = card.querySelector("#video-title, a#video-title, h3 a, h2 a, h3, h2");
  const text = node?.getAttribute("title") || node?.textContent || card.textContent || "";
  return text.replace(/\s+/g, " ").trim();
}
function filterYoutubeCards() {
  const focusKeywords = selectedSubjectKeywords();
  document.querySelectorAll(CARD_SELECTOR).forEach((card) => {
    if (card.closest("ytd-rich-shelf-renderer[is-shorts], ytd-reel-shelf-renderer")) { markDone(card); return; }
    // A lockup nested inside another card type is the same video. Judge it once, at the outer card.
    if (card.matches("yt-lockup-view-model") && card.parentElement?.closest(OLD_CARD_SELECTOR)) return;
    const titleOnly = cardTitleText(card);
    const title = titleOnly || normalized(card.textContent);
    if (!title) { armFailsafe(card); return; }
    // YouTube reuses the same element for different videos as you scroll or navigate.
    // If the title changed since the last decision, undo the old decision and judge again.
    const signature = titleOnly || title;
    if (card.dataset.semanthinksSig !== undefined && card.dataset.semanthinksSig !== signature) restore(card);
    card.dataset.semanthinksSig = signature;
    // When the model answers, it decides alone and the subject checklist is not used.
    if (modelAvailable()) judgeCardWithModel(card, rawCardTitle(card) || title, signature);
    else { judgeCardByRules(card, title, focusKeywords); markDone(card); }
  });
}
function hideShorts() {
  document.querySelectorAll("a[href^='/shorts/'], a[href*='youtube.com/shorts/']").forEach((link) => {
    const shelf = link.closest("grid-shelf-view-model, ytd-reel-shelf-renderer, ytd-rich-shelf-renderer, ytd-rich-section-renderer");
    const card = link.closest("ytd-rich-item-renderer, ytd-video-renderer, ytd-grid-video-renderer, ytd-reel-item-renderer");
    treatCandidate(shelf || card || link, "YouTube Short");
  });
  document.querySelectorAll("ytd-reel-shelf-renderer, ytd-rich-shelf-renderer[is-shorts]").forEach((shelf) => treatCandidate(shelf, "YouTube Short"));
  document.querySelectorAll("ytd-rich-section-renderer").forEach((section) => {
    const heading = [...section.querySelectorAll("span, yt-formatted-string")].some((node) => normalized(node.textContent) === "shorts");
    if (heading) treatCandidate(section, "YouTube Short");
  });
}
// Real dialogs and fixed-position overlay boxes are checked. Page-sized wrappers, cookie notices and password forms are skipped.
const POPUP_SELECTOR = "[role='dialog'], [aria-modal='true'], [class*='modal' i], [class*='popup' i], [class*='overlay' i], [class*='dialog' i], [id*='modal' i], [id*='popup' i]";
function isFloatingBox(el) {
  const cs = getComputedStyle(el);
  if (cs.position !== "fixed" && cs.position !== "absolute" && cs.position !== "sticky") return false;
  const r = el.getBoundingClientRect();
  return r.width > 120 && r.height > 60 && !wrapsMainContent(el);
}
// After a pop-up is hidden, the dimmed backdrop and the page's scroll lock would still be there. Remove both.
function releaseModalLock(popup) {
  const vw = window.innerWidth, vh = window.innerHeight;
  [...document.querySelectorAll("body div, body section, body aside")].slice(0, 2500).forEach((el) => {
    if (el === popup || popup.contains(el) || el.contains(popup) || currentState(el) === "hidden") return;
    const cs = getComputedStyle(el);
    if (cs.position !== "fixed" && cs.position !== "absolute") return;
    const r = el.getBoundingClientRect();
    if (r.width < vw * 0.9 || r.height < vh * 0.9 || normalized(el.textContent).length > 30 || wrapsMainContent(el)) return;
    applyTreatment(el, "hide", "Pop-up backdrop", false);
  });
  document.documentElement.setAttribute("data-semanthinks-unlock", "1");
}
// Sticky sign-up banners (for example a bar fixed to the bottom of the page) have no dialog markup or telling class name, so they are
// found by what they say and by being fixed on screen. Fixed top headers (log in / sign up buttons) are not touched. Runs at most every 1.5 s.
let lastBannerScan = 0;
// A pop-up that is a real advert (promotional wording) is judged by the model against the student's topic instead, so a course ad
// that fits the subject is kept. Sign-up walls without advert wording are always hidden.
function isAdForModel(text) { return modelAvailable() && includesAny(text, PROMOTIONAL_TERMS); }
function filterEngagementBanners() {
  if (sessionBypass || Date.now() - lastBannerScan < 1500) return;
  lastBannerScan = Date.now();
  const vh = window.innerHeight;
  [...document.querySelectorAll("body div, body section, body aside, body footer")].slice(0, 3000).forEach((el) => {
    if (el.closest(".semanthinks-hidden")) return;
    const rough = el.textContent.length;
    if (rough < 15 || rough > 900) return;
    const cs = getComputedStyle(el);
    if (cs.position !== "fixed" && cs.position !== "sticky") return;
    // innerText keeps the line breaks between blocks, so "papers" + "Sign up" is not read as one word.
    const text = normalized(el.innerText || el.textContent);
    if (text.length < 15 || text.length > 700 || text.includes("cookie")) return;
    const r0 = el.getBoundingClientRect();
    // a floating box labelled as an advert, with no dialog markup: the model decides by its topic
    if (includesAny(text, PROMOTIONAL_TERMS) && !includesAny(text, ENGAGEMENT_TERMS) && r0.width >= 120 && r0.height >= 40 && !wrapsMainContent(el) && !el.querySelector("input, textarea, select") && !el.querySelector(POPUP_SELECTOR)) {
      if (!modelAvailable()) treatCandidate(el, "Promotional popup"); else judgeAdBox(el, text);
      return;
    }
    if (!includesAny(text, ENGAGEMENT_TERMS) || isAdForModel(text)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 120 || r.height < 40 || wrapsMainContent(el)) return;
    if (!(r.bottom >= vh - 8 || r.top > 80)) return;
    if (el.querySelector("input[type='password']")) return;
    if (el.querySelector("input:not([type='hidden']):not([type='submit']):not([type='button']), textarea, select") && !/newsletter|subscribe/.test(text)) return;
    if (treatCandidate(el, "Engagement popup")) releaseModalLock(el);
  });
}
// A pop-up advert is judged on what it is ABOUT. Sales wording ("Shop now", "Limited offer", "discount", promo codes) is removed first,
// so a course ad that fits the student's subject is not hidden only because it sounds like an advert.
const escapeForRegex = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const PROMO_PATTERNS = ["promo code [a-z0-9]+", "use code [a-z0-9]+", "up to \\d+% off", "\\d+% ?(?:off|discount)"];   // written as regular expressions
const PROMO_PHRASES = ["limited offer", "limited time", "this week only", "today only", "free trial", "for students", "hurry", "enroll today", "enroll now", "book now", "buy now", "free gift", "special offer", "act now", "don't miss"];
const PROMO_WORDING = new RegExp("(" + [...PROMO_PATTERNS, ...[...PROMO_PHRASES, ...PROMOTIONAL_TERMS].map(escapeForRegex)].join("|") + ")", "gi");
function topicOfAd(text) {
  const t = text.replace(PROMO_WORDING, " ").replace(/\s+/g, " ").replace(/^[\s:;,.!\-]+|[\s:;,.!\-]+$/g, "").trim();
  return t.length >= 12 ? t : text;   // nothing left to judge: use the original wording
}
function filterPromotionalPopups() {
  filterEngagementBanners();
  document.querySelectorAll(POPUP_SELECTOR).forEach((popup) => {
    if (currentState(popup) === "hidden") return;
    const text = normalized(popup.innerText || popup.textContent);
    if (text.length <= 5 || text.length > 1200) return;
    const isDialog = popup.matches("[role='dialog'], [aria-modal='true']");
    if (!isDialog && !isFloatingBox(popup)) return;
    if (!sessionBypass && !text.includes("cookie") && includesAny(text, ENGAGEMENT_TERMS) && !isAdForModel(text)) {
      const hasPassword = popup.querySelector("input[type='password']");
      const hasFields = popup.querySelector("input:not([type='hidden']):not([type='submit']):not([type='button']), textarea, select");
      // A sign-up or newsletter box is hidden; a log-in form is left alone so the student can still sign in.
      if (!hasPassword && (!hasFields || /newsletter|subscribe/.test(text))) {
        if (treatCandidate(popup, "Engagement popup")) releaseModalLock(popup);
        return;
      }
    }
    if (!isDialog) return;
    if (popup.querySelector("input, textarea, select")) return;
    if (!includesAny(text, PROMOTIONAL_TERMS)) return;
    if (!modelAvailable() || sessionBypass) { treatCandidate(popup, "Promotional popup"); return; }
    // With the model running, a promotional pop-up is kept when it is about the student's topic and filtered when it is not.
    judgeAdBox(popup, text);
  });
}
// An advert box is kept when it is about the student's topic and filtered when it is not (the model sees the topic, not the sales wording).
function judgeAdBox(box, text) {
  if (box.dataset.semanthinksPopupSig === text) return;
  box.dataset.semanthinksPopupSig = text;
  askModel(topicOfAd(text).slice(0, 300), null, sessionContext(), sessionSubjects(), box).then((result) => {
    if (box.dataset.semanthinksPopupSig !== text || sessionBypass) return;
    if (!result || result.action !== "allow") treatCandidate(box, "Promotional popup");
    else box.title = "Semanthinks: kept, this pop-up matches your topic";
  });
}
// ---- Distractions that sit flat inside the page: "related / recommended / trending" boxes, sidebars, share bars, embedded social widgets ----
// Each link in such a box is looked at on its own (link intent by URL rules first, then the model on its text); the rest of the box stays.
const WIDGET_SELECTOR = "aside, [role='complementary'], [class*='related' i], [class*='recommend' i], [class*='trending' i], [class*='popular' i], [class*='sidebar' i], [class*='widget' i], [class*='also-read' i], [class*='read-next' i], [class*='more-stories' i], [class*='outbrain' i], [class*='taboola' i], [id*='related' i], [id*='recommend' i], [id*='trending' i], [id*='sidebar' i]";
const WIDGET_HEADING = /\b(related|recommended|you (may|might) also like|more from|trending|popular|sponsored|from around the web|also read|read next|more stories|top stories|don't miss)\b/i;
const SOCIAL_WIDGETS = ["iframe[src*='facebook.com/plugins']", "iframe[src*='platform.twitter.com']", "iframe[src*='instagram.com/embed']", ".fb-like", ".fb-page", ".fb-share-button", ".twitter-timeline", ".twitter-share-button", ".addthis_toolbox", ".a2a_kit", ".sharethis-inline-share-buttons", "[class*='social-share' i]", "[class*='share-buttons' i]", "[class*='sharing-buttons' i]"];
let widgetLinksJudged = 0;
function widgetContainers() {
  const found = new Set(document.querySelectorAll(WIDGET_SELECTOR));
  document.querySelectorAll("h2, h3, h4, [role='heading']").forEach((h) => {
    if (h.textContent.length < 60 && WIDGET_HEADING.test(h.textContent) && h.parentElement) found.add(h.parentElement);
  });
  return [...found].filter((c) => !c.closest("nav, header, footer") && !wrapsMainContent(c) && c.textContent.length <= 4000 && !c.closest(".semanthinks-hidden")).slice(0, 40);
}
function linkUnit(anchor, container) {
  const hrefs = (el) => new Set([...el.querySelectorAll("a[href]")].map((a) => a.href));
  let unit = anchor;
  while (unit.parentElement && unit.parentElement !== container && hrefs(unit.parentElement).size <= 1) unit = unit.parentElement;
  return unit;
}
function filterInlineWidgets() {
  if (window.top !== window || location.hostname.includes("youtube.com") || !/^https?:$/.test(location.protocol)) return;
  if (neverJudged() || /\.(edu|ac)(\.[a-z]{2})?$/.test(location.hostname)) return;
  SOCIAL_WIDGETS.forEach((selector) => document.querySelectorAll(selector).forEach((el) => { if (!wrapsMainContent(el)) treatCandidate(el, "Social widget"); }));
  const useModel = settings.guardPages !== false && modelAvailable();
  widgetContainers().forEach((container) => {
    const anchors = [...container.querySelectorAll("a[href]")];
    if (anchors.length < 2 || anchors.length > 40) return;
    anchors.forEach((a) => {
      const label = (a.getAttribute("aria-label") || a.textContent || a.title || "").replace(/\s+/g, " ").trim();   // keep the original case for the model
      if (label.length < 12 || label.length > 220) return;
      const unit = linkUnit(a, container);
      if (processed.has(unit) || wrapsMainContent(unit) || unit === container) return;
      processed.add(unit);
      const link = UrlTools.analyzeLink(a.href, label, { pageHost: location.hostname, rel: a.getAttribute("rel"), base: location.href });
      if (link.intent === "sponsored" || link.intent === "social" || link.intent === "social-share" || link.intent === "entertainment") { unit.title = "Semanthinks: hidden, " + link.reasons[0]; treatCandidate(unit, "Link: " + link.intent); return; }
      if (!useModel || widgetLinksJudged >= 150) return;
      widgetLinksJudged += 1;
      askModel(label.slice(0, 200), null, sessionContext(), sessionSubjects(), unit).then((result) => {
        if (sessionBypass || !settings.enabled || !result || result.action !== "hide") return;
        unit.title = "Semanthinks: hidden, this link is not about your studies"; treatCandidate(unit, "Link: off-topic");
      });
    });
  });
}
function filterParagraphs() {
  if (!settings.hidePromotionalParagraphs || isRepository()) return;
  document.querySelectorAll("article p, main p, [role='main'] p").forEach((paragraph) => {
    if (processed.has(paragraph)) return;
    processed.add(paragraph);
    const text = normalized(paragraph.textContent);
    if (text.length >= 60 && includesAny(text, PROMOTIONAL_TERMS) && keywordRelevance(text) < 0.47) treatCandidate(paragraph, "Promotional paragraph");
  });
}
// ---------- articles and documents ----------
// The same model that judges YouTube cards judges the page itself (title, description, first lines, URL words) on article
// and document sites, and the listing cards on news-style pages. "hide" puts a full-page notice with only a Go back button;
// "warn" shows a slim banner. Search engines, mail, school sites and code hosts are never judged.
const DOCUMENT_DOMAINS = ["scribd.com", "studocu.com", "coursehero.com", "slideshare.net", "academia.edu", "pdfcoffee.com", "docsity.com", "issuu.com", "yumpu.com", "dokumen.pub", "vdocuments.mx", "pdfdrive.com", "researchgate.net", "semanticscholar.org", "core.ac.uk", "jstor.org", "sciencedirect.com", "springer.com"];
const NEVER_JUDGE_DOMAINS = ["google.com", "bing.com", "duckduckgo.com", "yahoo.com", "mail.google.com", "outlook.com", "live.com", "office.com", "github.com", "gitlab.com", "stackoverflow.com", "stackexchange.com", "wikipedia.org", "claude.ai", "chatgpt.com", "localhost", "127.0.0.1"];
const hostIn = (list) => list.some((d) => location.hostname === d || location.hostname.endsWith("." + d));
// Google itself is never judged, but Google Scholar is a document-search site: its results are judged like any other.
const neverJudged = () => hostIn(NEVER_JUDGE_DOMAINS) && !/^scholar\.google\./.test(location.hostname);
function isDocumentSite() { return hostIn(DOCUMENT_DOMAINS) || hostIn(DEFAULT_REPOSITORY_DOMAINS); }
// Social media is blocked while studying (the popup has a switch, on by default). Messenger stays reachable so students can still
// talk to classmates and teachers; Facebook's feed, groups, watch and reels are blocked. This is a domain rule, not a model decision.
const SOCIAL_BLOCK_DOMAINS = UrlTools.SOCIAL_BLOCK_DOMAINS;   // one list, in url-tools.js, shared with the link rules
const SOCIAL_ALLOWED_DOMAINS = UrlTools.SOCIAL_ALLOWED_DOMAINS;
function isBlockedSocial() {
  if (hostIn(SOCIAL_ALLOWED_DOMAINS)) return false;
  if (/(^|\.)(facebook|fb)\.com$/.test(location.hostname) && /^\/(messages|messenger)(\/|$)/.test(location.pathname)) return false;   // Messenger inside facebook.com
  return UrlTools.isBlockedSite(location.hostname);   // social media, and entertainment / gaming / streaming sites matched by name
}
function guardSocial() {
  if (window.top !== window) return false;
  const existing = document.getElementById("semanthinks-page-notice");
  const blocked = Boolean(settings.enabled) && settings.blockSocial !== false && isBlockedSocial();
  if (!blocked) { if (existing && existing.dataset.kind === "social") removePageNotice(); return false; }
  if (!existing || existing.dataset.kind !== "social") showPageNotice("social", null);
  return true;
}
function pageIsJudgeable() {
  if (window.top !== window || !/^https?:$/.test(location.protocol) || location.hostname.includes("youtube.com")) return false;
  if (neverJudged() || /\.(edu|ac)(\.[a-z]{2})?$/.test(location.hostname)) return false;
  if (isDocumentSite()) return true;
  const og = document.querySelector("meta[property='og:type']")?.content || "";
  const paragraphs = [...document.querySelectorAll("p")];
  return /article/i.test(og) || Boolean(document.querySelector("article")) || (paragraphs.length >= 4 && paragraphs.reduce((n, p) => n + p.textContent.length, 0) >= 800);
}
function metaText(...names) {
  for (const n of names) { const c = document.querySelector(`meta[name='${n}' i], meta[property='${n}' i]`)?.content; if (c && c.trim()) return c.replace(/\s+/g, " ").trim(); }
  return "";
}
function pageProfile() {
  // Scholarly sites publish the title and abstract as metadata (citation_title, DC.title); some only show them in the page (PubMed, ACM).
  let title = metaText("citation_title", "dc.title", "og:title") || (document.title || "").replace(/\s+/g, " ").trim();
  if (title.length < 8) title = clean(document.querySelector("h1.heading-title, h1.citation__title, h1")?.textContent) || title;
  let desc = metaText("citation_abstract", "dc.description", "description", "og:description");
  if (desc.length < 80) {
    const abs = document.querySelector("#abstract .abstract-content, #eng-abstract, #abstract, .abstractSection, .abstractInFull, section.abstract, [class*='abstract' i]:not(a):not(button), [id*='abstract' i]");
    const t = clean(abs?.textContent).replace(/^abstract:?\s*/i, "");
    if (t.length >= 80) desc = t;
  }
  const lead = desc || [...document.querySelectorAll("article p, main p, p")].slice(0, 3).map((p) => p.textContent).join(" ").replace(/\s+/g, " ").trim();
  const slug = decodeURIComponent(location.pathname).replace(/\.[a-z0-9]{2,4}$/i, "").replace(/[-_/+]+/g, " ").replace(/\b\d{4,}\b/g, "").replace(/\s+/g, " ").trim();
  return { title, text: [title, lead.slice(0, 260), title.length < 25 ? slug.slice(0, 80) : ""].filter(Boolean).join(". ").slice(0, 440) };
}
let pageKey = "", pageToken = 0;
const queryVerdicts = new Map();   // searched text + context -> Promise of the model's verdict (shared by the page check and the result filter)
function queryVerdict(query) {
  const key = `${query}|${sessionContext()}|${sessionSubjects().join(",")}`;
  if (!queryVerdicts.has(key)) { if (queryVerdicts.size > 50) queryVerdicts.clear(); queryVerdicts.set(key, askModel(query, null, sessionContext(), sessionSubjects(), null)); }
  return queryVerdicts.get(key);
}
function removePageNotice() { document.getElementById("semanthinks-page-notice")?.remove(); document.documentElement.style.removeProperty("overflow"); }
function showPageNotice(kind, result, query) {
  removePageNotice();
  const host = document.createElement("div"); host.id = "semanthinks-page-notice"; host.dataset.kind = kind;
  host.style.cssText = kind !== "banner" ? "position:fixed;inset:0;z-index:2147483647;" : "position:fixed;top:0;left:0;right:0;z-index:2147483647;";
  const root = host.attachShadow({ mode: "open" });
  const looks = result ? detectedSubjectName(result) : "";
  const reason = result ? `${looks ? `It looks like “${looks}”. ` : ""}Relevance score ${Number(result.score).toFixed(2)}.` : "";
  root.innerHTML = kind === "social"
    ? `<style>.w{position:fixed;inset:0;background:rgba(18,24,38,.97);color:#fff;font:16px/1.5 Arial,sans-serif;display:flex;align-items:center;justify-content:center;text-align:center}.c{max-width:460px;padding:28px}h1{font-size:22px;margin:0 0 10px}p{margin:0 0 18px;color:#d5dbe8}button{font:600 15px Arial;padding:10px 18px;margin:4px;border-radius:8px;border:0;cursor:pointer;background:#fff;color:#1d2b4f}</style><div class="w"><div class="c"><h1>This site is paused while you study</h1><p>Social media, games and streaming sites are blocked during study time. Messenger is still available for talking to your classmates and teachers.</p><button id="back">Go back</button></div></div>`
    : kind === "block"
    ? `<style>.w{position:fixed;inset:0;background:rgba(18,24,38,.94);color:#fff;font:16px/1.5 Arial,sans-serif;display:flex;align-items:center;justify-content:center;text-align:center}.c{max-width:460px;padding:28px}h1{font-size:22px;margin:0 0 10px}p{margin:0 0 18px;color:#d5dbe8}button{font:600 15px Arial;padding:10px 18px;margin:4px;border-radius:8px;border:0;cursor:pointer}.p{background:#fff;color:#1d2b4f}.s{background:transparent;color:#fff;border:1px solid #8fa0c4}</style><div class="w"><div class="c"><h1>${query ? "Your search doesn’t look related to your studies" : "This page doesn’t look related to your studies"}</h1><p>${query ? `Searched for “${query.replace(/[<>&]/g, "")}”. ` : ""}${reason} Semanthinks paused it while your course focus is on.</p><button class="p" id="back">Go back</button></div></div>`
    : `<style>.b{background:#fff4d6;color:#4a3500;border-bottom:2px dashed #c98a00;font:14px/1.4 Arial,sans-serif;padding:8px 14px;display:flex;gap:12px;align-items:center}button{margin-left:auto;font:13px Arial;border:1px solid #c98a00;background:#fff;border-radius:6px;padding:3px 10px;cursor:pointer}</style><div class="b"><span><b>Semanthinks:</b> this page may be off-topic for your focus. ${reason}</span><button id="go">Dismiss</button></div>`;
  (document.body || document.documentElement).append(host);
  if (kind !== "banner") document.documentElement.style.setProperty("overflow", "hidden", "important");
  const go = root.getElementById("go");   // only the warning banner has a Dismiss button; a block has no way past it
  if (go) go.addEventListener("click", () => { try { sessionStorage.setItem("semanthinks-ok:" + location.hostname, "1"); } catch (_) {} removePageNotice(); });
  const back = root.getElementById("back");
  if (back) back.addEventListener("click", () => { if (history.length > 1) history.back(); else location.href = "about:blank"; });
}
function looksLikeDocumentPage() {
  if (metaText("citation_title", "dc.title", "citation_abstract")) return true;
  return /\/(document|doc|abs|abstract|article|paper|papers|pdf|doi|view|details?|fulltext|publication|record)s?\/|\/\d{4,}|\bdoi\b|\/[a-z]{2,6}[-_]?\d{4,}/i.test(location.pathname);
}
function guardPage() {
  if (settings.guardPages === false || !modelAvailable() || !pageIsJudgeable()) return;
  try { if (sessionStorage.getItem("semanthinks-ok:" + location.hostname)) return; } catch (_) {}
  const profile = pageProfile(); const title = profile.title;
  if (title.length < 4) return;
  // A search-results page is judged by what was searched for. Its title and description are the site's generic ones.
  const query = UrlTools.searchQueryFromUrl(location.href);
  // The home page of a document or repository site says nothing about a topic either; it is left alone.
  // Home, browse and landing pages (/, /Xplore/home.jsp, /browse) are left alone too: only a page that is a document is judged without a search.
  if (!query && isDocumentSite() && !looksLikeDocumentPage()) return;
  const text = query || profile.text;
  const context = sessionContext();
  const key = `${location.href}|${title}|${context}|${sessionSubjects().join(",")}`;
  if (key === pageKey) return;
  pageKey = key;
  const token = ++pageToken;
  (query ? queryVerdict(query) : askModel(text, null, context, sessionSubjects(), null)).then((result) => {
    if (token !== pageToken || !result || !settings.enabled || sessionBypass) return;
    if (settings.logDecisions) console.info(`[Semanthinks] page ${result.action} | C=${result.score} | ${result.ms} ms | ${query ? "search: " + query : title.slice(0, 80)}`);
    if (result.action === "hide") showPageNotice("block", result, query);
    else if (result.action === "warn") showPageNotice("banner", result);
    else removePageNotice();
  });
}
// Search-results pages (arXiv, Google Scholar, Scribd, Medium...): every result is extracted (title + the abstract or snippet under it) and judged
// like a video card, so an off-topic result is hidden while the relevant ones stay. Known result layouts first, then any list of 4+ similar
// blocks that each have a title link (only tried when the address has a search query).
const RESULT_SELECTORS = ["li.arxiv-result", "xpl-results-item", "div.result-item", "div.List-results-items > div", "article.full-docsum", "article.docsum", "li.search__item", ".issue-item-container", "div.issue-item", ".gs_r.gs_or", ".search-result", "[class*='search-result' i]", "[class*='searchresult' i]", "[class*='result-item' i]", "[data-testid*='search-result' i]", "li[class*='result' i]"];
const RESULT_TITLES = ["h3 a.fw-bold", ".result-item-title a", "a.docsum-title", ".issue-item__title a", ".issue-item__title", ".hlFld-Title a", "p.title", ".gs_rt", "h2 a", "h3 a", "h4 a", "h2", "h3", "h4", "[class*='title' i]"];   // most specific first (arXiv also has a "list-title" line with just the id)
const RESULT_SNIPPET = ".description, .full-view-snippet, .docsum-snippet, .issue-item__abstract, .issue-item__content, .abstract-short, .abstract, .gs_rs, [class*='snippet' i], [class*='abstract' i], [class*='description' i], [class*='summary' i], p";
const clean = (t) => (t || "").replace(/\s+/g, " ").trim();
function resultText(item) {
  let titleNode = null, title = "";
  for (const selector of RESULT_TITLES) {
    const node = item.querySelector(selector); const t = clean(node?.getAttribute("title") || node?.textContent);
    if (t.length >= 8 && t.length <= 250) { titleNode = node; title = t; break; }
  }
  if (!titleNode) return "";
  let snippet = "";
  for (const node of item.querySelectorAll(RESULT_SNIPPET)) {
    if (titleNode && (node === titleNode || node.contains(titleNode) || titleNode.contains(node))) continue;
    const t = clean(node.textContent).replace(/^abstract:\s*/i, "");
    if (t.length >= 40) { snippet = t.slice(0, 200); break; }
  }
  return snippet ? `${title}. ${snippet}` : title;
}
function isResultCandidate(el) {
  // a result may itself be an <article> (PubMed); it only must not wrap the page's main content
  const isPage = el === document.body || el === document.documentElement || el.matches("main, [role='main']") || Boolean(el.querySelector("main, article, [role='main']"));
  return !isPage && el.textContent.length < 2500 && el.querySelector("a[href]");
}
function searchResultItems() {
  let items = [...document.querySelectorAll(RESULT_SELECTORS.join(", "))].filter(isResultCandidate);
  items = items.filter((el) => !items.some((other) => other !== el && el.contains(other)));    // keep the innermost blocks, not their wrappers
  if (items.length < 3 && UrlTools.searchQueryFromUrl(location.href)) {
    items = [];
    for (const parent of [...document.querySelectorAll("ul, ol, div, section, main")].slice(0, 800)) {
      const kids = [...parent.children]; if (kids.length < 4 || kids.length > 100) continue;
      const groups = new Map();
      kids.forEach((k) => { const key = k.tagName + "|" + [...k.classList].sort().join("."); (groups.get(key) || groups.set(key, []).get(key)).push(k); });
      groups.forEach((g) => { if (g.length >= 4 && g.filter((k) => isResultCandidate(k) && resultText(k)).length >= g.length * 0.75) items.push(...g.filter(isResultCandidate)); });
      if (items.length) break;
    }
  }
  items = [...new Set(items.map((el) => el.closest("xpl-results-item, li.arxiv-result, article.full-docsum, article.docsum") || el))];   // hide the whole result, not only its inner column
  return items.map((el) => ({ el, text: resultText(el) })).filter((r) => r.text);
}
// Listing pages: <article> cards with a heading link (news, blogs), or the results of a search page.
function filterArticleCards() {
  if (settings.guardPages === false || !modelAvailable() || window.top !== window || location.hostname.includes("youtube.com") || neverJudged()) return;
  const results = searchResultItems();
  const articles = [...document.querySelectorAll("article")].filter((a) => !a.querySelector("article, main") && a.textContent.length < 1500 && a.querySelector("h2 a, h3 a, a h2, a h3")).map((el) => ({ el, text: rawCardTitle(el) }));
  const items = results.length >= 3 ? results : articles;
  if (items.length < 3) return;
  const query = results.length >= 3 ? UrlTools.searchQueryFromUrl(location.href) : "";
  const runItems = (strict) => items.forEach(({ el: card, text: title }) => {
    if (title.length < 8) return;
    if (strict) card.dataset.semanthinksStrict = "1"; else delete card.dataset.semanthinksStrict;
    const signature = normalized(title);
    if (card.dataset.semanthinksSig !== undefined && card.dataset.semanthinksSig !== signature) restore(card);
    card.dataset.semanthinksSig = signature;
    judgeCardWithModel(card, title, signature);
  });
  if (!query) { runItems(false); return; }
  queryVerdict(query).then((verdict) => runItems(Boolean(verdict) && verdict.action !== "allow"));   // an off-topic search: borderline results are hidden too
}

// ---- Ads inside the YouTube player (pre-roll, mid-roll). While the player says an ad is showing: press Skip when it is offered,
// otherwise mute, speed up and jump to the end of the ad, then restore the student's own volume and speed. Checked every 400 ms.
// This relies on YouTube's player markup (.ad-showing, the skip-button classes), which YouTube changes from time to time.
const AD_SKIP_BUTTONS = [".ytp-skip-ad-button", ".ytp-ad-skip-button", ".ytp-ad-skip-button-modern", ".ytp-ad-skip-button-container button", ".ytp-ad-skip-button-slot button"];
let adState = null;
function handleVideoAd() {
  if (!location.hostname.includes("youtube.com") || window.top !== window) return;
  const player = document.querySelector(".html5-video-player");
  const video = player && player.querySelector("video");
  if (!player || !video) return;
  const active = settings.enabled !== false && settings.blockVideoAds !== false && !sessionBypass && (player.classList.contains("ad-showing") || player.classList.contains("ad-interrupting"));
  if (!active) {
    if (adState) { video.muted = adState.muted; video.playbackRate = adState.rate; adState = null; }
    return;
  }
  if (!adState) adState = { muted: video.muted, rate: video.playbackRate || 1 };
  for (const selector of AD_SKIP_BUTTONS) { const button = player.querySelector(selector); if (button && button.offsetParent !== null) { button.click(); break; } }
  video.muted = true;
  video.playbackRate = 16;
  const end = video.duration;
  if (Number.isFinite(end) && end > 0.5 && video.currentTime < end - 0.2) { try { video.currentTime = end - 0.05; } catch (_) {} }
}
// ---- Banner ads and invisible click-catchers (the part of a pop-up that a script cannot stop, because it is just markup) ----
const BANNER_SIZES = [[300, 250], [728, 90], [160, 600], [320, 50], [970, 250], [300, 600], [468, 60], [336, 280], [320, 100], [970, 90], [300, 50], [120, 600], [250, 250], [200, 200]];
const near = (a, b) => Math.abs(a - b) <= 3;
function filterBannerAds() {
  if (window.top === window && (neverJudged() || /\.(edu|ac)(\.[a-z]{2})?$/.test(location.hostname))) return;
  document.querySelectorAll("a[href]:has(img)").forEach((a) => {
    if (processed.has(a) || a.closest(".semanthinks-hidden") || wrapsMainContent(a)) return;
    processed.add(a);
    const link = UrlTools.analyzeLink(a.href, a.textContent, { pageHost: location.hostname, rel: a.getAttribute("rel"), base: location.href });
    const img = a.querySelector("img"); const r = (img || a).getBoundingClientRect();
    const sized = BANNER_SIZES.some(([w, h]) => (near(r.width, w) && near(r.height, h)) || (near(Number(img.getAttribute("width")), w) && near(Number(img.getAttribute("height")), h)));
    const textless = clean(a.textContent).length < 20;
    const newTab = a.target === "_blank";
    // sponsored address: hide whatever its size; a standard banner size pointing to another site and opening a new tab: hide too
    if (link.intent === "sponsored" || (sized && textless && newTab && link.external)) {
      const parent = a.parentElement;
      const box = parent && parent !== document.body && parent.children.length === 1 && !clean(parent.textContent) && !wrapsMainContent(parent) ? parent : a;
      a.title = "Semanthinks: hidden, " + (link.reasons[0] || "banner ad"); treatCandidate(box, "Banner ad");
    }
  });
}
// A transparent element that covers the whole screen only exists to catch a click and open an advert.
function filterClickOverlays() {
  const vw = innerWidth, vh = innerHeight;
  document.querySelectorAll("body > div, body > a, body > span, body > iframe, html > div").forEach((el) => {
    if (processed.has(el) || el.closest(".semanthinks-hidden") || wrapsMainContent(el) || el.id === "semanthinks-page-notice" || el.id === "semanthinks-toast") return;
    const cs = getComputedStyle(el);
    if (cs.position !== "fixed" && cs.position !== "absolute") return;
    const r = el.getBoundingClientRect();
    if (r.width < vw * 0.85 || r.height < vh * 0.85) return;
    const invisible = Number(cs.opacity) < 0.05 || cs.visibility === "hidden" || (/rgba\(0, 0, 0, 0\)|transparent/.test(cs.backgroundColor) && !clean(el.textContent) && !el.querySelector("img, video, canvas, svg"));
    if (invisible && !clean(el.textContent) && cs.pointerEvents !== "none") { processed.add(el); treatCandidate(el, "Click overlay"); }
  });
}
function runFilter() {
  updateGuard();
  if (guardSocial()) return;
  if (!settings.enabled || sessionBypass || document.hidden) return;
  if (location.hostname.includes("youtube.com") && settings.hideYouTubeRecommendations) {
    SELECTORS.youtubeChrome.forEach((selector) => document.querySelectorAll(selector).forEach((element) => treatCandidate(element, "YouTube distraction")));
    hideShorts();
    filterYoutubeCards();
  }
  SELECTORS.generalAds.forEach((selector) => document.querySelectorAll(selector).forEach((element) => {
    const target = adContainer(element);
    if (wrapsMainContent(target)) return;
    treatCandidate(target, "Advertisement");
  }));
  filterPromotionalPopups();
  const chromeSelectors = isRepository() ? SELECTORS.repositoryChrome : SELECTORS.articleChrome;
  chromeSelectors.forEach((selector) => document.querySelectorAll(selector).forEach((element) => treatCandidate(element, isRepository() ? "Repository distraction" : "Page recommendation")));
  filterParagraphs();
  filterBannerAds();
  filterClickOverlays();
  filterInlineWidgets();
  filterArticleCards();
  guardPage();
}
function scheduleFilter() {
  if (queued) return;
  queued = true;
  setTimeout(() => { queued = false; runFilter(); silentRun = false; }, 250);
}
// Tells page-guard.js (running in the page itself) whether it should act.
function syncPopupGuard() { document.documentElement.setAttribute("data-semanthinks-popups", settings.enabled === false || settings.blockPopups === false ? "off" : "on"); }
async function start() {
  settings = await chrome.storage.sync.get({ blockPopups: true, enabled: true, subject: "Computer Science", selectedSubjects: [], focusTerms: [], hideYouTubeRecommendations: true, hidePromotionalParagraphs: true, guardPages: true, blockSocial: true, blockVideoAds: true, useImages: true, useModel: true, logDecisions: true, repositoryDomains: DEFAULT_REPOSITORY_DOMAINS });
  syncPopupGuard();
  document.addEventListener("semanthinks-blocked", (e) => {
    if (window.top === window) showWarnToast("blocked a pop-up (" + ((e.detail && e.detail.what) || "window") + (e.detail && e.detail.host ? " to " + e.detail.host : "") + ")");
    sendRuntimeMessage({ type: "incrementStats", hidden: 1, paragraphs: 0 });
  });
  runFilter();
  new MutationObserver(scheduleFilter).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["style", "src"] });
  if (location.hostname.includes("youtube.com")) setInterval(handleVideoAd, 400);
  let lastHref = location.href;
  setInterval(() => { if (location.href !== lastHref) { lastHref = location.href; scheduleFilter(); } }, 700);   // Facebook changes address without reloading
  setInterval(() => { if (!document.hidden && pageKey && !pageKey.startsWith(location.href + "|")) scheduleFilter(); }, 1500);   // single-page sites change URL without reloading
  // A tab opened in the background skips filtering. Catch up when it becomes visible.
  document.addEventListener("visibilitychange", () => { if (!document.hidden) scheduleFilter(); });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "sync") return;
    Object.entries(changes).forEach(([key, change]) => { settings[key] = change.newValue; });
    syncPopupGuard();
    sessionBypass = false;
    // Undo everything hidden under the old settings, then judge again under the new ones.
    // If filtering was switched off, runFilter() does nothing and the page stays restored.
    restoreAll(); removePageNotice(); pageKey = ""; updateGuard();
    processed = new WeakSet();
    silentRun = true;
    scheduleFilter();
  });
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === "restorePage") { sessionBypass = true; restoreAll(); removePageNotice(); guardSocial(); updateGuard(); sendResponse({ ok: true }); }
    if (message.type === "applyFilter") { sessionBypass = false; pageKey = ""; processed = new WeakSet(); silentRun = true; runFilter(); silentRun = false; sendResponse({ ok: true }); }
    if (message.type === "getPageState") sendResponse({ hidden: !sessionBypass });
  });
}
start();
