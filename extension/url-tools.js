/* URL analysis and link-intent rules. Loaded before content.js (and tested in Node).
 * analyzeLink(href, text, opts) says what a link is for, from its address, its rel attribute and its anchor text:
 *   social        links to a social-media site (Facebook, Instagram, TikTok, X ...); Messenger is not counted
 *   social-share  "share on Facebook / X / WhatsApp" style links
 *   sponsored     rel="sponsored", ad-network and affiliate addresses, paid-campaign tracking, "Sponsored" labels
 *   internal      same site          external   another site
 * These are fixed rules, not a trained model. Links that are none of the first three are judged by the model on their text. */
(function (root) {
  const SOCIAL_BLOCK_DOMAINS = ["facebook.com", "fb.com", "fb.watch", "instagram.com", "tiktok.com", "x.com", "twitter.com", "snapchat.com", "pinterest.com", "reddit.com"];
  // Entertainment, gaming and streaming sites, matched by name so every country domain is covered (animepahe.ru, animepahe.si, ...).
  const ENTERTAINMENT_NAMES = ["roblox", "twitch", "netflix", "steampowered", "epicgames", "poki", "crazygames", "y8", "miniclip", "friv", "9gag", "crunchyroll", "hulu", "disneyplus", "animepahe", "gogoanime", "hianime", "aniwatch", "9anime", "kissanime", "fmovies", "soap2day", "putlocker", "minecraft", "fortnite", "leagueoflegends", "valorant"];
  const SOCIAL_ALLOWED_DOMAINS = ["messenger.com", "m.me"];
  const AD_HOSTS = ["doubleclick.net", "googleadservices.com", "googlesyndication.com", "outbrain.com", "taboola.com", "revcontent.com", "mgid.com", "shareasale.com", "clickbank.net", "awin1.com", "amzn.to", "skimresources.com", "linksynergy.com", "tkqlhce.com", "anrdoezrs.net", "jdoqocy.com", "zemanta.com", "adsterra.com", "popads.net", "propellerads.com", "rapidadexchange.com", "crcdn.org", "exoclick.com", "juicyads.com", "trafficjunky.com", "popcash.net", "hilltopads.net", "clickadu.com", "adcash.com", "a-ads.com", "bidvertiser.com", "admaven.com", "ad-maven.com", "richads.com", "monetag.com", "onclickads.net", "trafficstars.com", "tsyndicate.com", "adnxs.com", "adsrvr.org"];
  const AFFILIATE_PARAMS = /^(aff|affid|aff_id|affiliate|affiliate_id|clickid|gclid|msclkid|ref_id)$/i;
  const PAID_MEDIUMS = /^(cpc|ppc|paid|paidsocial|affiliate|sponsored|banner|display)$/i;
  const SPONSORED_TEXT = /^\s*(sponsored|advertisement|promoted|paid content|ad)\b|\b(sponsored content|paid partnership|affiliate link)\b/i;

  const hostMatches = (host, list) => list.some((d) => host === d || host.endsWith("." + d));
  const cleanHost = (h) => String(h || "").toLowerCase().replace(/^www\./, "");

  function isEntertainmentHost(host) {
    const labels = cleanHost(host).split(".");
    return labels.some((l) => ENTERTAINMENT_NAMES.includes(l));
  }
  // Sites paused while studying: social media, games, streaming.
  function isBlockedSite(host) { return isSocialHost(host) || isEntertainmentHost(host); }
  function isSocialHost(host) {
    const h = cleanHost(host);
    return hostMatches(h, SOCIAL_BLOCK_DOMAINS) && !hostMatches(h, SOCIAL_ALLOWED_DOMAINS);
  }
  function parse(href, base) { try { return new URL(href, base || "https://example.invalid/"); } catch (_) { return null; } }

  function isShareLink(u) {
    const h = u.hostname.toLowerCase(), p = u.pathname;
    if (/^(wa\.me|api\.whatsapp\.com)$/.test(h)) return true;
    if (h === "t.me") return /^\/share/.test(p);
    if (/(^|\.)(facebook|fb)\.com$/.test(h)) return /^\/(sharer|share|dialog\/share)/.test(p);
    if (/(^|\.)(twitter|x)\.com$/.test(h)) return /^\/(intent|share)/.test(p);
    if (/(^|\.)pinterest\.com$/.test(h)) return /^\/pin\/create/.test(p);
    if (/(^|\.)linkedin\.com$/.test(h)) return /^\/(shareArticle|sharing)/.test(p);
    if (/(^|\.)reddit\.com$/.test(h)) return /^\/submit/.test(p);
    return false;
  }

  function analyzeLink(href, text, opts) {
    opts = opts || {};
    const u = parse(href, opts.base);
    const reasons = [];
    if (!u || !/^https?:$/.test(u.protocol)) return { intent: "none", reasons: ["not a web link"], external: false };
    const host = cleanHost(u.hostname), pageHost = cleanHost(opts.pageHost);
    const external = Boolean(pageHost) && host !== pageHost && !host.endsWith("." + pageHost) && !pageHost.endsWith("." + host);
    const rel = String(opts.rel || "").toLowerCase();
    // sponsored first: an advert that points at a social site is still an advert
    if (/\bsponsored\b/.test(rel)) reasons.push('rel="sponsored"');
    if (hostMatches(host, AD_HOSTS)) reasons.push("ad or affiliate network address (" + host + ")");
    const params = [...u.searchParams.entries()];
    if (params.some(([k]) => AFFILIATE_PARAMS.test(k))) reasons.push("affiliate or click-tracking parameter");
    if (params.some(([k, v]) => k.toLowerCase() === "utm_medium" && PAID_MEDIUMS.test(v))) reasons.push("paid-campaign tracking (utm_medium)");
    if (SPONSORED_TEXT.test(String(text || ""))) reasons.push('labelled "sponsored" or "advertisement"');
    if (reasons.length) return { intent: "sponsored", reasons, external };
    if (isShareLink(u)) return { intent: "social-share", reasons: ["share link for " + host], external };
    if (isSocialHost(host)) return { intent: "social", reasons: ["social media site (" + host + ")"], external };
    if (isEntertainmentHost(host)) return { intent: "entertainment", reasons: ["entertainment or gaming site (" + host + ")"], external };
    return { intent: external ? "external" : "internal", reasons: [], external };
  }

  // The text a student searched for, read from the address of a search-results page (arXiv ?query=, Scribd ?query=, Medium ?q= ...).
  // A results page has a generic title ("Search | arXiv e-print repository"), so the searched text is what tells us the topic.
  const QUERY_PARAMS = ["q", "query", "search_query", "search", "searchterm", "search_term", "term", "terms", "keyword", "keywords", "k", "s", "text", "wd", "allfield", "allfields", "searchtext", "text1", "querytext", "query_text", "searchquery", "search_term_string", "st", "queryterm"];
  function searchQueryFromUrl(href) {
    const u = parse(href); if (!u) return "";
    const lower = new Map([...u.searchParams.entries()].map(([k, v]) => [k.toLowerCase(), v]));   // ACM uses ?AllField=
    for (const name of QUERY_PARAMS) {
      const v = (lower.get(name) || "").replace(/\s+/g, " ").trim();
      if (v.length >= 3 && v.length <= 200 && /[a-z\u00c0-\u024f]{2}/i.test(v) && !/^https?:/i.test(v)) return v;
    }
    const m = u.pathname.match(/^\/(?:search|s|find|results)\/([^/]{3,120})\/?$/i);   // /search/<words>
    if (m) { try { return decodeURIComponent(m[1]).replace(/[-+_]+/g, " ").trim(); } catch (_) {} }
    return "";
  }

  root.UrlTools = { isEntertainmentHost, isBlockedSite, AD_HOSTS, ENTERTAINMENT_NAMES, searchQueryFromUrl, SOCIAL_BLOCK_DOMAINS, SOCIAL_ALLOWED_DOMAINS, isSocialHost, analyzeLink, cleanHost };
})(typeof self !== "undefined" ? self : globalThis);
