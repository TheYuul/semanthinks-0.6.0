/* Runs inside the web page itself (manifest "world": "MAIN") at document start, in every frame, so it can wrap the page's own functions.
 * It stops pop-up windows and forced redirects that ad scripts start from a click:
 *   - window.open() to another site, or to a blank window (pop-unders)
 *   - a script clicking a hidden <a target="_blank"> to another site
 *   - a real click on a sponsored link that opens a new tab (ad network address, affiliate or paid-campaign tracking)
 * Links the student clicks on purpose to ordinary pages, and sign-in pop-ups of the big account providers, still work.
 * The content script switches it off with <html data-semanthinks-popups="off"> and listens for the "semanthinks-blocked" event. */
(function () {
  if (window.__semanthinksGuard || typeof UrlTools === "undefined") return;
  window.__semanthinksGuard = true;
  const ACCOUNTS = ["accounts.google.com", "appleid.apple.com", "login.microsoftonline.com", "login.live.com", "github.com", "auth0.com", "okta.com", "paypal.com"];
  const isOff = () => document.documentElement && document.documentElement.getAttribute("data-semanthinks-popups") === "off";
  const pageHost = () => UrlTools.cleanHost(location.hostname);
  function otherSite(url) {
    try {
      const u = new URL(url, location.href); if (!/^https?:$/.test(u.protocol)) return false;
      const h = UrlTools.cleanHost(u.hostname), p = pageHost();
      if (h === p || h.endsWith("." + p) || p.endsWith("." + h)) return false;
      return !ACCOUNTS.some((d) => h === d || h.endsWith("." + d));
    } catch (_) { return false; }
  }
  const tell = (what, url) => { try { document.dispatchEvent(new CustomEvent("semanthinks-blocked", { detail: { what, host: (() => { try { return new URL(url, location.href).hostname; } catch (_) { return ""; } })() } })); } catch (_) {} };

  const realOpen = window.open;
  window.open = function (url, ...rest) {
    if (!isOff()) {
      const blank = url == null || url === "" || String(url) === "about:blank";
      if (blank || otherSite(url)) { tell("window", url); return null; }
    }
    return realOpen.call(this, url, ...rest);
  };
  const realClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (!isOff() && (this.target === "_blank" || this.target === "_new") && otherSite(this.href)) { tell("anchor", this.href); return; }
    return realClick.apply(this, arguments);
  };
  document.addEventListener("click", (event) => {
    if (isOff()) return;
    const a = event.target && event.target.closest && event.target.closest("a[href]");
    if (!a || (a.target !== "_blank" && a.target !== "_new")) return;
    const link = UrlTools.analyzeLink(a.href, a.textContent, { pageHost: location.hostname, rel: a.getAttribute("rel") });
    if (link.intent === "sponsored") { event.preventDefault(); event.stopImmediatePropagation(); tell("sponsored link", a.href); }
  }, true);
})();
