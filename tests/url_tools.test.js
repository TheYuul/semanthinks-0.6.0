// Run: node tests/url_tools.test.js
const fs = require("fs"), vm = require("vm"), path = require("path"), assert = require("assert");
const ctx = { URL }; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "extension", "url-tools.js"), "utf8"), ctx, { filename: "url-tools.js" });
vm.runInContext("this.U = UrlTools;", ctx); const U = ctx.U;
let n = 0; const ok = (name, fn) => { fn(); n++; console.log("ok -", name); };
const intent = (href, text = "Some link text here", o = {}) => U.analyzeLink(href, text, { pageHost: "news.example.com", base: "https://news.example.com/a", ...o }).intent;

ok("social sites and subdomains are social; Messenger is not", () => {
  assert.strictEqual(intent("https://www.facebook.com/somepage"), "social"); assert.strictEqual(intent("https://m.facebook.com/x"), "social");
  assert.strictEqual(intent("https://www.instagram.com/p/abc"), "social"); assert.strictEqual(intent("https://x.com/user"), "social");
  assert.notStrictEqual(intent("https://www.messenger.com/t/1"), "social"); assert.notStrictEqual(intent("https://m.me/someone"), "social");
  assert.strictEqual(U.isSocialHost("box.com"), false); assert.strictEqual(U.isSocialHost("www.reddit.com"), true);
});
ok("share links are recognised", () => {
  assert.strictEqual(intent("https://www.facebook.com/sharer/sharer.php?u=x"), "social-share"); assert.strictEqual(intent("https://twitter.com/intent/tweet?text=x"), "social-share");
  assert.strictEqual(intent("https://wa.me/?text=x"), "social-share"); assert.strictEqual(intent("https://www.linkedin.com/shareArticle?url=x"), "social-share");
});
ok("sponsored: rel, ad networks, affiliate and paid-campaign parameters, labels", () => {
  assert.strictEqual(intent("https://shop.example.com/x", "Best laptops", { rel: "nofollow sponsored" }), "sponsored");
  assert.strictEqual(intent("https://ads.doubleclick.net/click?id=1"), "sponsored"); assert.strictEqual(intent("https://www.taboola.com/x"), "sponsored");
  assert.strictEqual(intent("https://shop.example.com/x?aff=123"), "sponsored"); assert.strictEqual(intent("https://shop.example.com/x?utm_source=a&utm_medium=cpc"), "sponsored");
  assert.strictEqual(intent("https://shop.example.com/x", "Sponsored: top laptops for coding"), "sponsored");
  assert.strictEqual(intent("https://www.facebook.com/page", "x", { rel: "sponsored" }), "sponsored", "an advert pointing at a social site is still an advert");
});
ok("ordinary links are not flagged (utm_source alone is only analytics)", () => {
  assert.strictEqual(intent("https://news.example.com/post/2?utm_source=newsletter"), "internal");
  assert.strictEqual(intent("https://other.org/paper.pdf"), "external"); assert.strictEqual(intent("/relative/path"), "internal");
  assert.strictEqual(intent("https://other.org/", "An ad hoc committee meets"), "external", "the word 'ad' inside a sentence is not a label");
});
ok("non-web links are ignored", () => { assert.strictEqual(intent("javascript:void(0)"), "none"); assert.strictEqual(intent("mailto:a@b.com"), "none"); assert.strictEqual(intent("#top"), "internal"); });
ok("the searched text is read from search-results addresses", () => {
  assert.strictEqual(U.searchQueryFromUrl("https://arxiv.org/search/cs?query=introduction+to+computing&searchtype=all&size=50"), "introduction to computing");
  assert.strictEqual(U.searchQueryFromUrl("https://medium.com/search?q=binary%20trees"), "binary trees");
  assert.strictEqual(U.searchQueryFromUrl("https://www.scribd.com/search?query=sql%20joins&content_type=documents"), "sql joins");
  assert.strictEqual(U.searchQueryFromUrl("https://site.example/search/finite-automata"), "finite automata");
  assert.strictEqual(U.searchQueryFromUrl("https://dl.acm.org/action/doSearch?AllField=sorting+algorithms"), "sorting algorithms"); assert.strictEqual(U.searchQueryFromUrl("https://pubmed.ncbi.nlm.nih.gov/?term=database+indexing"), "database indexing");
  assert.strictEqual(U.searchQueryFromUrl("https://site.example/post/123?ref=home"), ""); assert.strictEqual(U.searchQueryFromUrl("https://site.example/?s=1"), "");
  assert.strictEqual(U.searchQueryFromUrl("https://site.example/x?q=https://other.com/page"), "", "a URL in a parameter is not a search");
});
ok("entertainment sites are matched by name across country domains; look-alike names are not", () => {
  for (const h of ["www.roblox.com", "animepahe.ru", "animepahe.si", "www.twitch.tv", "www.netflix.com", "poki.com"]) assert(U.isEntertainmentHost(h) && U.isBlockedSite(h), h);
  for (const h of ["chess.stackexchange.com", "robloxstudio-docs.example.org", "pokiman.example.org", "en.wikipedia.org"]) assert(!U.isEntertainmentHost(h), h);
  assert.strictEqual(intent("https://www.roblox.com/games/1"), "entertainment"); assert.strictEqual(intent("https://rapidadexchange.com/do/c.php?x=1"), "sponsored");
});
console.log(`\n${n} groups passed`);
