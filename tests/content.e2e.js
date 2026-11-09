// Run: NODE_PATH=$(npm root -g) node tests/content.e2e.js
const { chromium } = require("playwright"); const fs = require("fs"); const path = require("path"); const assert = require("assert");
const ext = (f) => fs.readFileSync(path.join(__dirname, "..", "extension", f), "utf8");
(async () => {
  const browser = await chromium.launch(); const page = await browser.newPage();
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.route("https://www.youtube.com/**", (r) => r.fulfill({ contentType: "text/html", body: `<html><body>
    <ytd-rich-item-renderer id="a"><a id="video-title" title="Prank gone wrong"></a></ytd-rich-item-renderer>
    <ytd-rich-item-renderer id="b"><a id="video-title" title="Finite Automata explained"></a></ytd-rich-item-renderer>
    <ytd-rich-item-renderer id="c"><a id="video-title" title="Maybe related video"></a></ytd-rich-item-renderer></body></html>` }));
  await page.addInitScript(() => {
    window.__sent = [];
    const sync = { enabled: true, subject: "Both", selectedSubjects: ["cs-automata", "it-programming"], useModel: true, logDecisions: false, hideYouTubeRecommendations: true };
    window.chrome = { runtime: { id: "x", lastError: null, onMessage: { addListener() {} },
        sendMessage(msg, cb) { window.__sent.push(msg); const t = msg.text;
          const res = /Prank/.test(t) ? { block: true, action: "hide", score: 0.1, mode: "text" } : /Maybe/.test(t) ? { block: false, action: "warn", score: 0.5, mode: "text", detected_subjects: [{ id: "networks", p: 0.8 }] } : { block: false, action: "allow", score: 0.9, mode: "text" };
          setTimeout(() => cb && cb({ ok: true, result: res, ms: 5 }), 10); } },
      storage: { sync: { get: async (d) => ({ ...d, ...sync }) }, onChanged: { addListener() {} } } };
  });
  await page.goto("https://www.youtube.com/");
  for (const f of ["subject-catalog.js", "subject-tools.js", "url-tools.js", "content.js"]) await page.addScriptTag({ content: ext(f) });
  await page.addStyleTag({ content: ext("content.css") });
  await page.waitForTimeout(1200);
  const state = await page.evaluate(() => ({ a: document.querySelector("#a").className, b: document.querySelector("#b").className, c: document.querySelector("#c").className, cTitle: document.querySelector("#c").title, sent: window.__sent.filter((m) => m.type === "classify") }));
  assert(/semanthinks-hidden/.test(state.a), "hide band hides the card"); console.log("ok - hide action hides the card");
  assert(!/hidden|warn/.test(state.b), state.b); console.log("ok - allow action leaves the card alone");
  assert(/semanthinks-warn/.test(state.c) && !/hidden/.test(state.c) && state.cTitle.startsWith("Semanthinks:")); console.log("ok - warn action keeps the card visible and marked");
  assert(/looks like Networks/.test(state.cTitle), state.cTitle); console.log("ok - the warning names the detected subject");
  assert(state.sent.every((m) => Array.isArray(m.subjects) && m.subjects.includes("programming") && m.subjects.includes("automata")), JSON.stringify(state.sent[0])); console.log("ok - chosen subject ids are sent to the backend");
  const ctxs = new Set(state.sent.map((m) => m.context)); assert.strictEqual(ctxs.size, 1);
  const ctx = [...ctxs][0]; assert(/^Computer Programming 1 & 2; Automata Theory & Formal Languages:/.test(ctx), ctx);
  console.log("ok - old ids migrated and the subject context is sent to the backend:", ctx.slice(0, 90) + "...");
  assert.deepStrictEqual(errors, [], errors.join("; ")); console.log("ok - no page errors");

  // Keyword focus: the typed term replaces the subject text as context and narrows the subjects sent to the model.
  const page2 = await browser.newPage();
  await page2.route("https://www.youtube.com/**", (r) => r.fulfill({ contentType: "text/html", body: `<html><body><ytd-rich-item-renderer id="a"><a id="video-title" title="C++ pointers explained"></a></ytd-rich-item-renderer></body></html>` }));
  await page2.addInitScript(() => {
    window.__sent = [];
    const sync = { enabled: true, subject: "Both", selectedSubjects: ["database", "networks"], focusTerms: [{ term: "c++", subjects: ["programming"] }], useModel: true, logDecisions: false, hideYouTubeRecommendations: true };
    window.chrome = { runtime: { id: "x", lastError: null, onMessage: { addListener() {} }, sendMessage(msg, cb) { window.__sent.push(msg); setTimeout(() => cb && cb({ ok: true, result: { block: false, action: "allow", score: 0.9, mode: "text" }, ms: 5 }), 10); } },
      storage: { sync: { get: async (d) => ({ ...d, ...sync }) }, onChanged: { addListener() {} } } };
  });
  await page2.goto("https://www.youtube.com/");
  for (const f of ["subject-catalog.js", "subject-tools.js", "url-tools.js", "content.js"]) await page2.addScriptTag({ content: ext(f) });
  await page2.waitForTimeout(800);
  const sent2 = await page2.evaluate(() => window.__sent.filter((m) => m.type === "classify"));
  assert(sent2.length >= 1 && sent2.every((m) => m.context === "focus: c++ | Computer Programming 1 & 2" && JSON.stringify(m.subjects) === '["programming"]'), JSON.stringify(sent2[0]));
  console.log("ok - keyword focus sends 'focus: c++ | Computer Programming 1 & 2' and only the programming subject");

  // Articles and documents: page-level notice, banner, listing cards and pop-up relevance.
  async function articlePage(url, body, answers, extra = {}) {
    const p = await browser.newPage();
    await p.route(url + "**", (r) => r.fulfill({ contentType: "text/html", body }));
    await p.addInitScript(({ answers, extra }) => {
      window.__sent = [];
      const sync = { enabled: true, subject: "Both", selectedSubjects: ["programming"], useModel: true, logDecisions: false, guardPages: true, hideYouTubeRecommendations: true, ...extra };
      window.chrome = { runtime: { id: "x", lastError: null, onMessage: { addListener() {} }, sendMessage(msg, cb) { window.__sent.push(msg);
          const hit = answers.find((a) => new RegExp(a[0], "i").test(msg.text)); const act = hit ? hit[1] : "allow";
          setTimeout(() => cb && cb({ ok: true, result: { block: act === "hide", action: act === "weak" ? "allow" : act, score: act === "hide" ? 0.1 : act === "warn" ? 0.5 : act === "weak" ? 0.6 : 0.9, mode: "text" }, ms: 5 }), 10); } },
        storage: { sync: { get: async (d) => ({ ...d, ...sync }) }, local: { get: async (d) => ({ ...d, ...(window.__local || {}) }), set: async (o) => { window.__local = Object.assign(window.__local || {}, o); } }, onChanged: { addListener() {} } } };
    }, { answers, extra });
    await p.goto(url);
    for (const f of ["subject-catalog.js", "subject-tools.js", "url-tools.js", "content.js"]) await p.addScriptTag({ content: ext(f) });
    await p.addStyleTag({ content: ext("content.css") });
    await p.waitForTimeout(900);
    return p;
  }
  const paras = "<p>" + "Some long paragraph of body text about the topic. ".repeat(6) + "</p>";
  const doc = (title) => `<html><head><title>${title}</title><meta property="og:type" content="article"></head><body><article><h1>${title}</h1>${paras}${paras}${paras}${paras}</article></body></html>`;
  const blocked = await articlePage("https://news.example.com/a", doc("Celebrity gossip of the week"), [["gossip", "hide"]]);
  assert(await blocked.evaluate(() => { const n = document.getElementById("semanthinks-page-notice"); return Boolean(n && n.shadowRoot.textContent.includes("doesn’t look related")); }), "off-topic article gets the full-page notice");
  assert.strictEqual(await blocked.evaluate(() => document.getElementById("semanthinks-page-notice").shadowRoot.getElementById("go")), null); console.log("ok - off-topic article page is paused, with Go back only (no Continue anyway)");
  const warned = await articlePage("https://news.example.com/b", doc("Maybe related reading"), [["Maybe", "warn"]]);
  assert(await warned.evaluate(() => document.getElementById("semanthinks-page-notice").shadowRoot.textContent.includes("may be off-topic"))); console.log("ok - borderline article page gets a dismissible banner");
  const fine = await articlePage("https://news.example.com/c", doc("Binary search explained"), []);
  assert.strictEqual(await fine.evaluate(() => document.getElementById("semanthinks-page-notice")), null); console.log("ok - relevant article page is left alone");
  const docsite = await articlePage("https://www.scribd.com/document/1/x", `<html><head><title>Wedding seating plan</title></head><body><div>doc viewer</div></body></html>`, [["Wedding", "hide"]]);
  assert(await docsite.evaluate(() => Boolean(document.getElementById("semanthinks-page-notice")))); console.log("ok - document repository page (Scribd) is judged even without article markup");
  const search = await articlePage("https://www.google.com/search", doc("Celebrity gossip"), [["gossip", "hide"]]);
  assert.strictEqual(await search.evaluate(() => document.getElementById("semanthinks-page-notice")), null); console.log("ok - search engines are never judged");
  const card = (t) => `<article><h2><a href="#">${t}</a></h2><p>x</p></article>`;
  const listing = await articlePage("https://blog.example.com/", `<html><head><title>Blog</title></head><body>${card("Top celebrity gossip")}${card("Learning SQL joins quickly")}${card("Intro to recursion in Python")}</body></html>`, [["gossip", "hide"]]);
  const cls = await listing.evaluate(() => [...document.querySelectorAll("article")].map((a) => a.className));
  assert(/semanthinks-hidden/.test(cls[0]) && !/hidden/.test(cls[1]) && !/hidden/.test(cls[2]), cls.join("|")); console.log("ok - listing cards are judged one by one");
  const rg = await articlePage("https://papers.example.com/", `<html><head><title>Paper</title></head><body style="overflow:hidden"><main><h1>Visualizing natural language interaction</h1><p>In this paper we investigate how natural language interfaces can be integrated.</p></main><div id="bd" style="position:fixed;inset:0;background:rgba(0,0,0,.5)"></div><div id="join" class="modal" role="dialog" style="position:fixed;top:100px;left:100px;width:400px;height:200px;background:#fff"><h2>Discover the world's research</h2><p>Join ResearchGate to find the people and research you need to help your work.</p><button>Join for free</button></div><div id="login" role="dialog" style="position:fixed;top:400px;left:100px;width:300px;height:100px">Log in to continue <input type="password"></div><div id="ck" role="dialog" style="position:fixed;bottom:0;left:0;width:300px;height:80px">We use cookies. Create an account to save preferences <button>Accept</button></div></body></html>`, []);
  const rgs = await rg.evaluate(() => ({ join: document.querySelector("#join").className, bd: document.querySelector("#bd").className, login: document.querySelector("#login").className, ck: document.querySelector("#ck").className, unlock: document.documentElement.getAttribute("data-semanthinks-unlock"), ov: getComputedStyle(document.body).overflow }));
  assert(/semanthinks-hidden/.test(rgs.join) && /semanthinks-hidden/.test(rgs.bd) && !/hidden/.test(rgs.login) && !/hidden/.test(rgs.ck) && rgs.unlock === "1" && rgs.ov === "auto", JSON.stringify(rgs));
  console.log("ok - a join / sign-up pop-up is hidden with its dimmed backdrop and the scroll lock; a log-in form and a cookie notice are left alone");
  // --- ACM / IEEE-style subscription and upgrade pop-ups; the cookie consent banner stays ---
  const sub = await articlePage("https://dl.acm.org/", `<html><head><title>ACM Digital Library</title></head><body><main><h1>ACM Digital Library</h1><p>Search millions of papers on computing.</p></main>
    <div id="bd" style="position:fixed;inset:0;background:#0009;z-index:100"></div>
    <div id="acm" class="modal__dialog" style="position:fixed;top:300px;left:660px;width:600px;height:300px;background:#fff;z-index:101"><h2>ACM is now Open Access</h2><p>New features for researchers are available in the Premium Edition. You are currently in the Basic Edition. Features requiring a subscription appear in grey.</p><button>Sign In</button><button>Upgrade</button></div>
    <div id="ieee" class="popup" style="position:fixed;top:300px;left:100px;width:600px;height:300px;background:#e5a128;z-index:102"><h2>Access to this document requires a subscription.</h2><p>IEEE offers both personal and institutional subscriptions.</p><button>LEARN MORE</button><a href="#">Close</a></div>
    <div id="ck" role="dialog" style="position:fixed;bottom:0;left:0;right:0;height:120px;background:#fff;z-index:103"><p>This website uses cookies. We share information about your use of our site with our advertising partners.</p><button>Allow all cookies</button></div></body></html>`, []);
  await sub.waitForTimeout(800);
  const subs = await sub.evaluate(() => Object.fromEntries(["acm", "ieee", "ck", "bd"].map((id) => [id, document.getElementById(id).className])));
  assert(/semanthinks-hidden/.test(subs.acm) && /semanthinks-hidden/.test(subs.ieee) && /semanthinks-hidden/.test(subs.bd) && !/hidden/.test(subs.ck), JSON.stringify(subs));
  console.log("ok - subscription / upgrade pop-ups (ACM Open Access notice, IEEE access-requires-subscription) are hidden with their backdrop; the cookie consent banner stays");
  // --- a floating box labelled as an advert, with no dialog markup, is judged by its topic ---
  const fl = await articlePage("https://papers.example.com/x", `<html><head><title>Notes</title></head><body><main><h1>Recursion notes</h1><p>Text.</p></main>
    <div id="on" class="box" style="position:fixed;right:10px;top:10px;width:300px;height:120px;background:#fff"><small>Advertisement</small><p>Shop now: Learn Python programming and data structures. Limited offer, 40% off.</p></div>
    <div id="off" class="box" style="position:fixed;right:10px;top:200px;width:300px;height:120px;background:#fff"><small>Sponsored</small><p>Win big at our online casino. Bonus promo code VEGAS100.</p></div></body></html>`, [["casino", "hide"]]);
  await fl.waitForTimeout(800);
  const fls = await fl.evaluate(() => ({ on: document.getElementById("on").className, off: document.getElementById("off").className }));
  assert(!/hidden/.test(fls.on) && /semanthinks-hidden/.test(fls.off), JSON.stringify(fls));
  console.log("ok - a floating advert box without dialog markup is kept when on-topic and hidden when off-topic");
  const ac = await articlePage("https://www.academia.example/", `<html><head><title>A short history of Information Management</title></head><body><header style="position:fixed;top:0;left:0;right:0;height:60px;background:#fff"><a href="#">Log In</a> <a href="#">Sign Up</a></header><main><h1>A short history of Information Management</h1><p>Abstract text about records and libraries.</p></main><div id="bar" class="x1f9" style="position:fixed;bottom:0;left:0;right:0;height:200px;background:#000;color:#fff"><h3>Sign up for access to the world's latest research</h3><ul><li>Get notified about relevant papers</li></ul><button>Sign up for free</button></div></body></html>`, []);
  const acs = await ac.evaluate(() => [document.querySelector("#bar").className, document.querySelector("header").className]);
  assert(/semanthinks-hidden/.test(acs[0]) && !/hidden/.test(acs[1]), acs.join("|")); console.log("ok - a sticky sign-up banner with no dialog markup is hidden; the header's Log In / Sign Up buttons stay");
  const notice = (pg) => pg.evaluate(() => { const n = document.getElementById("semanthinks-page-notice"); return n ? { kind: n.dataset.kind, hasGo: Boolean(n.shadowRoot.getElementById("go")), hasBack: Boolean(n.shadowRoot.getElementById("back")) } : null; });
  const feed = "<html><head><title>Home</title></head><body><main>feed</main></body></html>";
  const fb = await articlePage("https://www.facebook.com/", feed, []);
  const fbn = await notice(fb); assert(fbn && fbn.kind === "social" && !fbn.hasGo && fbn.hasBack, JSON.stringify(fbn)); console.log("ok - Facebook is blocked and the notice has no way past it");
  for (const u of ["https://www.instagram.com/", "https://www.tiktok.com/", "https://x.com/home", "https://www.reddit.com/"]) { const q = await articlePage(u, feed, []); assert.strictEqual((await notice(q))?.kind, "social", u); await q.close(); }
  console.log("ok - Instagram, TikTok, X and Reddit are blocked too");
  for (const u of ["https://www.messenger.com/t/123", "https://www.facebook.com/messages/t/123", "https://www.box.com/"]) { const q = await articlePage(u, feed, []); assert.strictEqual(await notice(q), null, u); await q.close(); }
  console.log("ok - Messenger (messenger.com and facebook.com/messages) is not blocked, and look-alike domains such as box.com are not matched");
  const off = await articlePage("https://www.facebook.com/", feed, [], { blockSocial: false }); assert.strictEqual(await notice(off), null); console.log("ok - the switch in the popup turns social blocking off");
  await fb.evaluate(() => history.pushState({}, "", "/messages/t/1")); await fb.waitForTimeout(1200); assert.strictEqual(await notice(fb), null);
  await fb.evaluate(() => history.pushState({}, "", "/watch")); await fb.waitForTimeout(1200); assert.strictEqual((await notice(fb))?.kind, "social"); console.log("ok - moving inside Facebook (no reload) between Messages and the feed unblocks and re-blocks");
  const modelBlock = await articlePage("https://blog.example.com/post", `<html><head><title>Celebrity gossip tonight</title></head><body><article><h1>Celebrity gossip tonight</h1></article></body></html>`, [["gossip", "hide"]]);
  const mb = await notice(modelBlock); assert(mb && mb.kind === "block" && !mb.hasGo && mb.hasBack, JSON.stringify(mb)); console.log("ok - the model's block screen has no Continue anyway either");
  const inline = await articlePage("https://news.example.com/story", `<html><head><title>Understanding database indexing</title><meta property="og:type" content="article"></head><body>
    <article id="main"><h1>Understanding database indexing</h1><p>${"Indexes speed up queries in a relational database. ".repeat(12)}</p></article>
    <aside class="related-articles"><h3>Related articles</h3><ul>
      <li id="r1"><a href="/a/1">Top celebrity gossip of the week revealed</a></li>
      <li id="r2"><a href="/a/2">How B-tree indexes work in SQL databases</a></li>
      <li id="r3"><a href="https://shop.example.org/laptops?utm_medium=cpc">Best laptops for coding students</a></li>
      <li id="r4"><a href="https://www.facebook.com/newsfan">Follow our Facebook page for updates</a></li></ul></aside>
    <div class="addthis_toolbox" id="share"><a href="https://twitter.com/intent/tweet?text=x">Tweet this article now</a></div></body></html>`, [["gossip", "hide"]]);
  await inline.waitForTimeout(800);
  const ic = await inline.evaluate(() => Object.fromEntries(["main", "r1", "r2", "r3", "r4", "share"].map((id) => [id, document.getElementById(id).className])));
  assert(/hidden/.test(ic.r1) && !/hidden/.test(ic.r2) && /hidden/.test(ic.r3) && /hidden/.test(ic.r4) && /hidden/.test(ic.share) && !/hidden/.test(ic.main), JSON.stringify(ic));
  const asked = await inline.evaluate(() => window.__sent.filter((m) => m.type === "classify").map((m) => m.text));
  assert(!asked.some((t) => /laptops|Facebook page/.test(t)), "rule-hidden links are not sent to the model: " + asked.join("|")); assert(asked.some((t) => /B-tree/.test(t)));
  console.log("ok - inside a related-articles box: off-topic link hidden by the model, sponsored and social links hidden by URL rules, the on-topic link and the article stay; share bar hidden");
  const adPage = `<html><head><title>x</title></head><body><div class="html5-video-player" id="pl"><video id="v"></video><div class="ytp-ad-module"><button class="ytp-skip-ad-button" id="skip" onclick="window.__skipped=(window.__skipped||0)+1">Skip</button></div></div>
    <div id="player-ads">banner ad</div></body></html>`;
  const yt = await articlePage("https://www.youtube.com/watch?v=abc", adPage, []);
  await yt.evaluate(() => { const v = document.getElementById("v"); let t = 0; Object.defineProperty(v, "duration", { get: () => 30 }); Object.defineProperty(v, "currentTime", { get: () => t, set: (x) => { t = x; } }); v.playbackRate = 1.5; v.muted = false; window.__t = () => t; });
  await yt.waitForTimeout(600);
  await yt.evaluate(() => document.getElementById("pl").classList.add("ad-showing"));   // the ad starts after the student set their own speed
  await yt.waitForTimeout(1200);
  const ad = await yt.evaluate(() => { const v = document.getElementById("v"); return { muted: v.muted, rate: v.playbackRate, t: window.__t(), skipped: window.__skipped || 0, banner: document.getElementById("player-ads").className }; });
  assert(ad.muted && ad.rate === 16 && ad.t > 29 && ad.skipped >= 1 && /hidden/.test(ad.banner), JSON.stringify(ad)); console.log("ok - an in-video ad is skipped (button), muted, fast-forwarded to its end; the ad banner is hidden");
  await yt.evaluate(() => document.getElementById("pl").classList.remove("ad-showing")); await yt.waitForTimeout(900);
  const back = await yt.evaluate(() => { const v = document.getElementById("v"); return { muted: v.muted, rate: v.playbackRate }; });
  assert(back.muted === false && back.rate === 1.5, JSON.stringify(back)); console.log("ok - after the ad the student's own volume and playback speed are restored");
  const ytOff = await articlePage("https://www.youtube.com/watch?v=def", adPage.replace('class="html5-video-player"', 'class="html5-video-player ad-showing"'), [], { blockVideoAds: false });
  await ytOff.waitForTimeout(900); assert.strictEqual(await ytOff.evaluate(() => document.getElementById("v").playbackRate), 1); console.log("ok - the popup switch turns in-video ad skipping off");
  const arx = (query) => `https://arxiv.org/search/cs?query=${encodeURIComponent(query)}&searchtype=all`;
  const generic = `<html><head><title>Search | arXiv e-print repository</title><meta name="description" content="arXiv e-print repository. Press Enter to search. Advanced search"></head><body><main><h1>Showing results</h1></main></body></html>`;
  const answersArx = [["introduction to computing", "allow"], ["celebrity", "hide"], ["arxiv", "hide"]];   // the site's generic text would be judged off-topic
  const sOk = await articlePage(arx("introduction to computing"), generic, answersArx);
  assert.strictEqual(await sOk.evaluate(() => document.getElementById("semanthinks-page-notice")), null);
  assert(await sOk.evaluate(() => window.__sent.some((m) => m.type === "classify" && m.text === "introduction to computing")), "the searched text is what the model judges"); console.log("ok - arXiv results page for an on-topic search is judged by the searched text and is not blocked");
  const sBad = await articlePage(arx("celebrity gossip"), generic, answersArx);
  const sn = await sBad.evaluate(() => { const n = document.getElementById("semanthinks-page-notice"); return n ? n.shadowRoot.textContent : ""; });
  assert(/Your search/.test(sn) && /celebrity gossip/.test(sn), sn); console.log("ok - a search for an off-topic subject is blocked, and the notice names the search");
  const li = (id, title, abs) => `<li class="arxiv-result" id="${id}"><p class="list-title"><a href="/abs/${id}">arXiv:${id}</a></p><p class="title is-5 mathjax">${title}</p><p class="authors">Authors: A. Person</p><p class="abstract mathjax"><span class="abstract-short">${abs}</span></p></li>`;
  const resultsPage = `<html><head><title>Search | arXiv e-print repository</title></head><body><main><h1>Showing 1-4 results</h1><ol>
    ${li("r1", "Teaching introduction to computing with Python", "We describe an introductory computing course covering programming, algorithms and data structures for first year students.")}
    ${li("r2", "Celebrity gossip and fan culture online", "A study of entertainment news, celebrity gossip and social media fandom across many platforms and audiences.")}
    ${li("r3", "A survey of operating system scheduling", "We review process scheduling algorithms used in operating systems and compare their performance on workloads.")}
    ${li("r4", "Sorting algorithms and complexity for beginners", "An overview of sorting algorithms, big-O complexity and how to teach them in an introductory course.")}</ol></main></body></html>`;
  const resPg = await articlePage(arx("introduction to computing"), resultsPage, [["gossip", "hide"]]);
  await resPg.waitForTimeout(800);
  const rc = await resPg.evaluate(() => Object.fromEntries(["r1", "r2", "r3", "r4"].map((id) => [id, document.getElementById(id).className])));
  assert(/hidden/.test(rc.r2) && !/hidden/.test(rc.r1) && !/hidden/.test(rc.r3) && !/hidden/.test(rc.r4), JSON.stringify(rc));
  const sentTexts = await resPg.evaluate(() => window.__sent.filter((m) => m.type === "classify").map((m) => m.text));
  assert(sentTexts.some((t) => /^Teaching introduction to computing with Python\. We describe an introductory/.test(t)), sentTexts.join(" | "));
  console.log("ok - the results of a search page are extracted (title + abstract) and judged one by one: the off-topic result is hidden, the rest stay");
  const hit = (id, t, d) => `<div class="hit" id="${id}"><a href="/doc/${id}"><h3>${t}</h3></a><p>${d}</p></div>`;
  const generic2 = await articlePage("https://docs.example.org/find?q=sql+joins", `<html><head><title>Find documents</title></head><body><div id="list">
    ${hit("g1", "SQL joins explained with examples", "Inner, outer and cross joins in relational databases, with worked queries.")}${hit("g2", "Top celebrity gossip this week", "Entertainment news and rumours about famous people and their lives.")}
    ${hit("g3", "Database normalization basics", "First, second and third normal forms and why they matter for design.")}${hit("g4", "Query optimization in PostgreSQL", "How the planner chooses join orders and indexes for faster queries.")}</div></body></html>`, [["gossip", "hide"]]);
  await generic2.waitForTimeout(800);
  const g = await generic2.evaluate(() => ["g1", "g2", "g3", "g4"].map((id) => document.getElementById(id).className));
  assert(/hidden/.test(g[1]) && !/hidden/.test(g[0]) && !/hidden/.test(g[2]) && !/hidden/.test(g[3]), g.join("|")); console.log("ok - an unknown results layout is still found (a list of similar blocks with title links on a page with a search query)");
  // --- Google Scholar is judged (google.com itself is not) ---
  const gs = (t, d) => `<div class="gs_r gs_or gs_scl"><div class="gs_ri"><h3 class="gs_rt"><a href="/x/${t.length}">${t}</a></h3><div class="gs_rs">${d}</div></div></div>`;
  const scholar = await articlePage("https://scholar.google.com/scholar?q=introduction+to+computing", `<html><head><title>introduction to computing - Google Scholar</title></head><body><div id="gs_res_ccl_mid">
    ${gs("Introduction to computing and programming for beginners", "A first course covering algorithms, data structures and programming in Python for new students.")}${gs("Celebrity gossip and tabloid culture", "Entertainment news, rumours and gossip about famous people shared widely on social media.")}
    ${gs("Computing fundamentals: hardware and software", "An overview of computer hardware, operating systems and software for introductory courses.")}</div></body></html>`, [["gossip", "hide"]]);
  await scholar.waitForTimeout(800);
  const sch = await scholar.evaluate(() => [...document.querySelectorAll(".gs_r")].map((n) => n.className));
  assert(/hidden/.test(sch[1]) && !/hidden/.test(sch[0]) && !/hidden/.test(sch[2]), sch.join("|")); console.log("ok - Google Scholar results are extracted and judged (Scholar is no longer on the never-judged list)");
  // --- entertainment and gaming sites are blocked by name, any country domain ---
  for (const u of ["https://www.roblox.com/home", "https://www.twitch.tv/x", "https://animepahe.ru/", "https://animepahe.si/anime", "https://www.netflix.com/browse"]) { const q = await articlePage(u, feed, []); assert.strictEqual((await notice(q))?.kind, "social", u); await q.close(); }
  const okSite = await articlePage("https://chess.stackexchange.com/q/1", feed, []); assert.strictEqual(await notice(okSite), null); console.log("ok - Roblox, Twitch, Netflix and anime streaming sites are blocked by name; a Stack Exchange site named after a game is not");
  // --- warn items: kind-aware tooltip, no orange outline, a notice when clicked ---
  const cardW = (t) => `<article><h2><a href="#${t.length}">${t}</a></h2><p>x</p></article>`;
  const warnPg = await articlePage("https://blog.example.com/", `<html><head><title>Blog</title></head><body>${cardW("Borderline reading about computers")}${cardW("Learning SQL joins quickly")}${cardW("Intro to recursion in Python")}</body></html>`, [["Borderline", "warn"]]);
  await warnPg.waitForTimeout(600);
  const wv = await warnPg.evaluate(() => { const a = document.querySelector("article"); return { cls: a.className, title: a.title, outline: getComputedStyle(a).outlineStyle }; });
  assert(/semanthinks-warn/.test(wv.cls) && /this result may be off-topic/.test(wv.title) && !/video/.test(wv.title) && wv.outline === "none", JSON.stringify(wv));
  await warnPg.evaluate(() => document.querySelector("article h2 a").addEventListener("click", (e) => e.preventDefault())); await warnPg.click("article h2 a");
  const toast = await warnPg.evaluate(() => document.getElementById("semanthinks-toast")?.shadowRoot.getElementById("t").textContent || "");
  assert(/this result may be off-topic/.test(toast), toast); console.log("ok - a warned document says 'result' (not 'video'), has no orange outline, and shows a notice when clicked");
  // --- an off-topic search makes borderline results hidden; an on-topic one keeps them as warnings ---
  const sr = (q, ans) => articlePage(`https://arxiv.org/search/cs?query=${encodeURIComponent(q)}&searchtype=all`, resultsPage.replace(/Teaching introduction to computing with Python/, "Borderline survey about wellbeing"), ans);
  const strictPg = await sr("mental health", [["mental health", "warn"], ["Borderline", "warn"], ["gossip", "hide"]]); await strictPg.waitForTimeout(900);
  const looseP = await sr("introduction to computing", [["introduction to computing", "allow"], ["Borderline", "warn"], ["gossip", "hide"]]); await looseP.waitForTimeout(900);
  const sCls = await strictPg.evaluate(() => document.getElementById("r1").className), lCls = await looseP.evaluate(() => document.getElementById("r1").className);
  assert(/hidden/.test(sCls) && /semanthinks-warn/.test(lCls) && !/hidden/.test(lCls), sCls + " | " + lCls); console.log("ok - when the search itself is off-topic, borderline results are hidden; when it is on-topic they stay as faded warnings");
  // a weakly matching result (allowed, score 0.60) is hidden on an off-topic search, kept on an on-topic one
  const weakS = await sr("mental health", [["mental health", "warn"], ["Borderline", "weak"]]); await weakS.waitForTimeout(900);
  const weakL = await sr("introduction to computing", [["introduction to computing", "allow"], ["Borderline", "weak"]]); await weakL.waitForTimeout(900);
  const wS = await weakS.evaluate(() => document.getElementById("r1").className), wL = await weakL.evaluate(() => document.getElementById("r1").className);
  assert(/hidden/.test(wS) && !/hidden/.test(wL), wS + " | " + wL); console.log("ok - on an off-topic search a result needs a score of 0.70 to stay (a weak 0.60 match is hidden); on an on-topic search it stays");
  // the home page of a repository is never judged, even when the model dislikes its generic text; a document page there still is
  const ieHome = await articlePage("https://ieeexplore.ieee.org/Xplore/home.jsp", `<html><head><title>IEEE Xplore gossip home</title><meta name="description" content="IEEE Xplore, delivering full text access to the world's highest quality technical literature in engineering and technology gossip."></head><body><main><h1>Advancing Technology for Humanity</h1></main></body></html>`, [["gossip", "hide"]]);
  await ieHome.waitForTimeout(900);
  const ieDoc = await articlePage("https://ieeexplore.ieee.org/document/1234567", `<html><head><title>Celebrity gossip paper</title><meta name="citation_title" content="Celebrity gossip and fan culture"><meta name="citation_abstract" content="A long study of celebrity gossip and entertainment news across many online platforms, audiences and communities worldwide."></head><body><main><h1>Celebrity gossip and fan culture</h1></main></body></html>`, [["gossip", "hide"]]);
  await ieDoc.waitForTimeout(900);
  const hN = await ieHome.evaluate(() => Boolean(document.getElementById("semanthinks-page-notice"))), dN = await ieDoc.evaluate(() => Boolean(document.getElementById("semanthinks-page-notice")));
  assert(!hN && dN, `home notice ${hN}, document notice ${dN}`); console.log("ok - a repository home page (/Xplore/home.jsp) is never blocked; a document page on the same site is still judged");
  // --- banner ads and invisible click-catchers (animepahe style) ---
  const bannerPg = await articlePage("https://stream.example.net/ep5", `<html><head><title>Episode 5</title></head><body><main><p>Player here</p></main>
    <div id="wrap"><a id="ad1" href="https://rapidadexchange.com/do/c.php?x=1" target="_blank" rel="noopener, noreferrer" style="display:block;width:300px;height:250px"><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="300" height="250"></a></div>
    <a id="ad2" href="https://other-shop.example.org/sale" target="_blank" style="display:block;width:728px;height:90px"><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="728" height="90"></a>
    <a id="own" href="/about" style="display:block;width:300px;height:250px"><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="300" height="250"></a>
    <div id="catcher" style="position:fixed;inset:0;z-index:99999;opacity:0"></div></body></html>`, []);
  await bannerPg.waitForTimeout(500);
  const bn = await bannerPg.evaluate(() => ({ wrap: document.getElementById("wrap").className, ad1: document.getElementById("ad1").className, ad2: document.getElementById("ad2").className, own: document.getElementById("own").className, catcher: document.getElementById("catcher").className }));
  assert(/hidden/.test(bn.wrap + bn.ad1) && /hidden/.test(bn.ad2) && !/hidden/.test(bn.own) && /hidden/.test(bn.catcher), JSON.stringify(bn)); console.log("ok - ad-network and standard-size external banners are hidden, a site's own image link stays, an invisible full-screen click-catcher is removed");
  // --- pop-up windows and forced redirects (page-guard.js runs in the page itself) ---
  const pgPage = await articlePage("https://stream.example.net/ep6", `<html><head><title>Episode 6</title></head><body><a id="norm" href="https://en.wikipedia.org/wiki/X" target="_blank">A normal link to another site</a><a id="spons" href="https://rapidadexchange.com/c?x=1" target="_blank">Click</a></body></html>`, []);
  await pgPage.addScriptTag({ content: ext("page-guard.js") });
  const pg = await pgPage.evaluate(() => {
    window.__ev = []; document.addEventListener("semanthinks-blocked", (e) => window.__ev.push(e.detail.what));
    const out = {}; out.openExternal = window.open("https://ads.example.net/x"); out.openBlank = window.open("about:blank");
    const a = document.createElement("a"); a.href = "https://ads.example.net/y"; a.target = "_blank"; document.body.append(a); a.click();
    let prevented = false; const s = document.getElementById("spons"); s.addEventListener("click", (e) => { prevented = e.defaultPrevented; e.preventDefault(); }); s.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    const n = document.getElementById("norm"); let normPrevented = true; n.addEventListener("click", (e) => { normPrevented = e.defaultPrevented; e.preventDefault(); }); n.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    document.documentElement.setAttribute("data-semanthinks-popups", "off"); const a2 = document.createElement("a"); a2.href = "https://ads.example.net/z"; a2.target = "_blank"; a2.addEventListener("click", (e) => { out.offClicked = true; e.preventDefault(); }); a2.click();
    return { ...out, sponsPrevented: prevented === false && window.__ev.includes("sponsored link"), openExternal: out.openExternal === null, openBlank: out.openBlank === null, events: window.__ev, normPrevented, offClicked: out.offClicked === true };
  });
  assert(pg.openExternal && pg.openBlank && pg.events.includes("window") && pg.events.includes("anchor") && pg.events.includes("sponsored link") && pg.sponsPrevented && !pg.normPrevented && pg.offClicked, JSON.stringify(pg));
  console.log("ok - window.open to another site or a blank window, scripted new-tab clicks and sponsored-link clicks are blocked; ordinary links and the off switch still work");
  // --- ads are judged on their topic, not their sales wording ---
  const tp = await resPg.evaluate(() => ["Shop now: Raspberry Pi starter kit for coding and electronics projects. Limited offer.", "Advertisement: Master Java and object-oriented programming. Discount for students.", "Sponsored: Win big at our online casino. Bonus promo code VEGAS100.", "Subscribe now", "Limited offer: 60% discount on designer sneakers. Shop now!"].map((t) => topicOfAd(t)));
  assert.deepStrictEqual(tp, ["Raspberry Pi starter kit for coding and electronics projects", "Master Java and object-oriented programming", "Win big at our online casino. Bonus", "Subscribe now", "on designer sneakers"], JSON.stringify(tp));
  console.log("ok - sales wording (Shop now, Limited offer, discount, promo codes) is removed before the model judges what an ad is about");
  // --- PubMed: results page, and an article page whose abstract is only in the page ---
  const docsum = (t, sn) => `<article class="full-docsum"><div class="docsum-wrap"><div class="docsum-content"><a class="docsum-title" href="/${t.length}/">${t}</a><div class="docsum-citation">Smith J. J Med. 2024.</div><div class="full-view-snippet">${sn}</div></div></div></article>`;
  const pub = await articlePage("https://pubmed.ncbi.nlm.nih.gov/?term=database+indexing", `<html><head><title>database indexing - Search Results - PubMed</title></head><body><main><div class="search-results-list">
    ${docsum("Learned index structures for relational database systems", "We study learned indexes for relational databases and compare query latency against B-trees on large tables.")}${docsum("Celebrity gossip exposure and teenage wellbeing", "A cohort study of celebrity gossip media exposure and its relation to wellbeing among adolescents in schools.")}
    ${docsum("Index selection for query workloads in SQL databases", "An algorithm for choosing database indexes under storage limits for mixed query workloads and updates.")}</div></main></body></html>`, [["gossip", "hide"]]);
  await pub.waitForTimeout(800);
  const pc2 = await pub.evaluate(() => [...document.querySelectorAll("article.full-docsum")].map((n) => n.className));
  assert(/hidden/.test(pc2[1]) && !/hidden/.test(pc2[0]) && !/hidden/.test(pc2[2]), pc2.join("|")); console.log("ok - PubMed search results (article.full-docsum, a.docsum-title, snippet) are extracted and judged");
  const xpl = (t, d) => `<div class="List-results-items"><xpl-results-item class="hide-mobile-print"><div class="d-flex result-item"><div class="col result-item-align"><h3 class="text-md-md-lh"><a class="fw-bold" href="/document/${t.length}">${t}</a></h3><div class="author">A. Author</div><div class="description"><span>${d}</span></div></div></div></xpl-results-item></div>`;
  const ie = await articlePage("https://ieeexplore.ieee.org/search/searchresult.jsp?newsearch=true&queryText=programming", `<html><head><title>IEEE Xplore Search Results</title></head><body><main><div class="Dashboard"><xpl-results-list>
    ${xpl("Applying the block-based programming language ALICE for developing competencies", "We describe a block-based programming course for university students and its outcomes.")}${xpl("Celebrity gossip and fan culture in online communities", "A study of gossip and fandom across entertainment platforms and audiences.")}${xpl("Using goal programming to solve fuzzy multi-objective problems", "An approach to solving linear fractional programming problems with fuzzy goals.")}</xpl-results-list></div></main></body></html>`, [["gossip", "hide"]]);
  await ie.waitForTimeout(800);
  const ies = await ie.evaluate(() => [...document.querySelectorAll("xpl-results-item")].map((n) => n.className));
  assert(/hidden/.test(ies[1]) && !/hidden/.test(ies[0]) && !/hidden/.test(ies[2]), ies.join("|")); console.log("ok - IEEE Xplore search results (xpl-results-item, h3 a, description) are extracted and judged");
  const pubDoc = await articlePage("https://pubmed.ncbi.nlm.nih.gov/12345678/", `<html><head><title>Learned index structures - PubMed</title></head><body><main><h1 class="heading-title">Learned index structures for relational database systems</h1>
    <div id="abstract"><h2 class="title">Abstract</h2><div class="abstract-content selected"><p>We study learned indexes for relational databases and compare query latency against B-trees on large tables, finding speedups on read-heavy workloads.</p></div></div></main></body></html>`, []);
  await pubDoc.waitForTimeout(600);
  const sentDoc = await pubDoc.evaluate(() => window.__sent.filter((m) => m.type === "classify").map((m) => m.text));
  assert(sentDoc.some((t) => /relational databases and compare query latency/.test(t)), sentDoc.join(" | ")); console.log("ok - on an article page the abstract found in the page (not only in metadata) is part of what is judged");
  // --- ACM Digital Library: results page ---
  const acmI = (t, ab) => `<li class="search__item issue-item-container"><div class="issue-item__content"><h5 class="issue-item__title"><a href="/doi/10.1145/${t.length}">${t}</a></h5><div class="issue-item__abstract"><p>${ab}</p></div></div></li>`;
  const acm = await articlePage("https://dl.acm.org/action/doSearch?AllField=sorting+algorithms", `<html><head><title>Search Results | ACM Digital Library</title></head><body><main><ul class="search-result__xsl-body">
    ${acmI("Sorting algorithms for large data sets", "We survey comparison sorting algorithms and analyse their time complexity on large data sets in memory.")}${acmI("Fan culture and celebrity gossip in online communities", "A study of celebrity gossip and fandom practices across online entertainment communities and forums.")}
    ${acmI("Parallel merge sort on modern processors", "We present a parallel merge sort and evaluate its speedup and scalability on multicore processors.")}</ul></main></body></html>`, [["gossip", "hide"]]);
  await acm.waitForTimeout(800);
  const ac2 = await acm.evaluate(() => [...document.querySelectorAll("li.search__item")].map((n) => n.className));
  assert(/hidden/.test(ac2[1]) && !/hidden/.test(ac2[0]) && !/hidden/.test(ac2[2]), ac2.join("|")); console.log("ok - ACM Digital Library search results (?AllField= search, li.search__item) are extracted and judged");
  const home = await articlePage("https://arxiv.org/", generic, [["arxiv", "hide"]]);
  assert.strictEqual(await home.evaluate(() => document.getElementById("semanthinks-page-notice")), null); console.log("ok - the home page of a repository site is not judged");
  const popup = await articlePage("https://shop.example.com/", `<html><head><title>x</title></head><body><div id="p1" role="dialog">Subscribe now and get a discount on our course bundle</div><div id="p2" role="dialog">Sign up now: free python programming bootcamp promo code</div></body></html>`, [["bundle", "hide"], ["bootcamp", "allow"]]);
  const pc = await popup.evaluate(() => [document.querySelector("#p1").className, document.querySelector("#p2").className, document.querySelector("#p2").title]);
  assert(/semanthinks-hidden/.test(pc[0]) && !/hidden/.test(pc[1]) && /kept/.test(pc[2]), pc.join("|")); console.log("ok - a promotional pop-up on the student's topic is kept, an unrelated one is filtered");

  // Text-only mode: no thumbnail URL is sent when "useImages" is off.
  const pageT = await browser.newPage();
  await pageT.route("https://www.youtube.com/**", (r) => r.fulfill({ contentType: "text/html", body: `<html><body><ytd-rich-item-renderer id="a"><img src="https://i.ytimg.com/vi/abc/hq720.jpg"><a id="video-title" title="Finite Automata explained"></a></ytd-rich-item-renderer></body></html>` }));
  async function sentImages(useImages) {
    const pg = await browser.newPage();
    await pg.route("https://www.youtube.com/**", (r) => r.fulfill({ contentType: "text/html", body: `<html><body><ytd-rich-item-renderer id="a"><img src="https://i.ytimg.com/vi/abcdefghijk/hq720.jpg"><a id="video-title" title="Finite Automata explained"></a></ytd-rich-item-renderer></body></html>` }));
    await pg.addInitScript((useImages) => {
      window.__sent = []; const sync = { enabled: true, subject: "Both", selectedSubjects: [], useModel: true, useImages, logDecisions: false, hideYouTubeRecommendations: true };
      window.chrome = { runtime: { id: "x", lastError: null, onMessage: { addListener() {} }, sendMessage(msg, cb) { window.__sent.push(msg); setTimeout(() => cb && cb({ ok: true, result: { block: false, action: "allow", score: 0.9, mode: "text" }, ms: 5 }), 10); } },
        storage: { sync: { get: async (d) => ({ ...d, ...sync }) }, onChanged: { addListener() {} } } };
    }, useImages);
    await pg.goto("https://www.youtube.com/");
    for (const f of ["subject-catalog.js", "subject-tools.js", "url-tools.js", "content.js"]) await pg.addScriptTag({ content: ext(f) });
    await pg.waitForTimeout(700);
    return (await pg.evaluate(() => window.__sent.filter((m) => m.type === "classify"))).map((m) => m.imageUrl);
  }
  const withImg = await sentImages(true), noImg = await sentImages(false);
  assert(withImg.length >= 1 && /ytimg/.test(withImg[0]) && noImg.length >= 1 && noImg.every((u) => u === null), JSON.stringify([withImg, noImg]));
  console.log("ok - text-only mode sends no thumbnail; the normal mode does");

  // No flash before the verdict: cards are blurred until judged, released after the verdict, and always released by the failsafe.
  async function guardPage(mode) {
    const pg = await browser.newPage();
    await pg.route("https://www.youtube.com/**", (r) => r.fulfill({ contentType: "text/html", body: `<html><body><ytd-rich-item-renderer id="a"><div class="inner">x</div><a id="video-title" title="Finite Automata explained"></a></ytd-rich-item-renderer></body></html>` }));
    await pg.addInitScript((mode) => {
      window.__SEMANTHINKS_SLOW_MS = 600; window.__SEMANTHINKS_FINAL_MS = 1600;
      const sync = { enabled: true, subject: "Both", selectedSubjects: [], useModel: true, logDecisions: false, hideYouTubeRecommendations: true };
      window.chrome = { runtime: { id: "x", lastError: null, onMessage: { addListener() {} }, sendMessage(msg, cb) {
          if (mode === "silent") return;                                              // the backend never answers
          setTimeout(() => cb && (mode === "down" ? cb({ ok: false }) : cb({ ok: true, result: { block: false, action: "allow", score: 0.9, mode: "text" }, ms: 5 })), mode === "slow" ? 1000 : 400); } },
        storage: { sync: { get: async (d) => ({ ...d, ...sync }) }, onChanged: { addListener() {} } } };
    }, mode);
    await pg.goto("https://www.youtube.com/");
    for (const f of ["subject-catalog.js", "subject-tools.js", "url-tools.js", "content.js"]) await pg.addScriptTag({ content: ext(f) });
    await pg.addStyleTag({ content: ext("content.css") });
    return pg;
  }
  const probe = (pg) => pg.evaluate(() => ({ guard: document.documentElement.hasAttribute("data-semanthinks-guard"), done: document.querySelector("#a").dataset.semanthinksDone || null, blur: getComputedStyle(document.querySelector("#a .inner")).filter, vis: getComputedStyle(document.querySelector("#a .inner")).visibility }));
  const g1 = await guardPage("ok"); await g1.waitForTimeout(250);
  let st = await probe(g1); assert(st.guard && !st.done && /blur/.test(st.blur), JSON.stringify(st)); console.log("ok - a card is blurred while it waits for its verdict");
  await g1.waitForTimeout(500); st = await probe(g1); assert(st.done && st.blur === "none", JSON.stringify(st)); console.log("ok - the blur is lifted when the verdict arrives");
  const g2 = await guardPage("silent"); await g2.waitForTimeout(350); st = await probe(g2); assert(/blur/.test(st.blur) && st.vis === "visible", JSON.stringify(st));
  await g2.waitForTimeout(500); st = await probe(g2); assert(!st.done && st.vis === "hidden", JSON.stringify(st)); console.log("ok - when the backend is slow, the card's content is hidden (not just blurred)");
  await g2.waitForTimeout(1300); st = await probe(g2); assert(st.done && st.blur === "none" && st.vis === "visible", JSON.stringify(st)); console.log("ok - if the backend never answers, the card is released at the hard limit");
  const g4 = await guardPage("slow"); await g4.waitForTimeout(800); st = await probe(g4); assert(st.vis === "hidden", JSON.stringify(st));
  await g4.waitForTimeout(500); st = await probe(g4); assert(st.done && st.vis === "visible" && st.blur === "none", JSON.stringify(st)); console.log("ok - a slow answer shows the card again when the verdict is allow");
  const g3 = await guardPage("down"); await g3.waitForTimeout(900); st = await probe(g3); assert(st.done && st.blur === "none", JSON.stringify(st)); console.log("ok - if the backend is down, the card is released (keyword rules take over)");
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
