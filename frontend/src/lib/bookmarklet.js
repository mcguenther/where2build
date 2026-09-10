/**
 * The bookmarklet: how a page no server may fetch gets here anyway.
 *
 * immobilienscout24.de answers every server-side request with an AWS WAF
 * challenge at the CloudFront edge — measured 09.09.2026 against a full
 * browser header set, HTTP/1.1, a `ClaudeBot` user agent and Anthropic's own
 * fetch alike, all 401, while `robots.txt` (200) explicitly allows those
 * crawlers. There is no header to fix and nothing to call differently. Its own
 * search and expose API exists but is content-partner only, and its terms
 * forbid own analyses and cap storage at 24 hours, which is this product's
 * core. See `docs/research/immobilienscout24-zugang.md`.
 *
 * So the page comes out of the browser that is already looking at it. The
 * paste field did that first and loses too much on the way: `Strg+A` selects
 * the document's *body*, so every `<meta>` and every JSON-LD block stays
 * behind — which is why a pasted ImmoScout page read as having no address, no
 * coordinate and no parcel number, a fact about the clipboard rather than
 * about the portal.
 *
 * `document.documentElement.outerHTML` has all of it, and more than a fetch
 * would ever get: the head, the scripts, the state the page rendered itself
 * from. Nothing is circumvented — the page is loaded, in the user's own
 * session, on a page they may read. And it needs no CORS, because the
 * bookmarklet never talks to the API: it opens the app and hands the document
 * over with `postMessage`, so the request to `/api/listings/extract` is made
 * by the app, from its own origin.
 *
 * `postMessage` is also what makes this survive the portal's own
 * Content-Security-Policy. A `fetch` from the bookmarklet's context would be
 * governed by the page's `connect-src` and a form post by its `form-action`;
 * neither directive applies here.
 */

/** The query parameter that says a handover is in flight, and its nonce. */
export const HANDOVER_QUERY = "uebergabe";

/** The app is mounted and listening. Sent to `window.opener`. */
export const HANDOVER_READY = "w2b-bereit";

/** The document itself. Sent back to the app. */
export const HANDOVER_PAGE = "w2b-seite";

/** How long the bookmarklet waits for the app to say it is there. */
export const HANDOVER_TIMEOUT_MS = 20000;

/* The two sentences the bookmarklet may have to say. They are interface — a
 * user reads them in an alert box — so they are German, like every other
 * string on screen. */
const BLOCKED =
  "Der Browser hat das Fenster blockiert. Bitte Pop-ups für diese Seite erlauben " +
  "und noch einmal klicken.";
const SILENT = "where2build hat sich nicht gemeldet. Läuft die App unter ";

/**
 * The bookmarklet's source, with the app's own origin baked in.
 *
 * Written across several lines and collapsed to one, because a `javascript:`
 * URL is a URL: a newline in it is not whitespace but the end of the bookmark.
 * For the same reason there is not a single `//` comment inside — the rest of
 * the program would be commented out.
 */
export const bookmarkletCode = origin => `
(function(){
  var o=${JSON.stringify(origin)},
      n=String(Date.now())+String(Math.random()).slice(2,8),
      h=document.documentElement.outerHTML,
      u=location.href,
      w=window.open(o+"/aufnahme/quelle?${HANDOVER_QUERY}="+n,"where2build");
  if(!w){alert(${JSON.stringify(BLOCKED)});return;}
  var done=false;
  function m(e){
    if(done||e.source!==w||!e.data||e.data.w2b!==${JSON.stringify(HANDOVER_READY)}||e.data.${HANDOVER_QUERY}!==n)return;
    done=true;
    window.removeEventListener("message",m);
    w.postMessage({w2b:${JSON.stringify(HANDOVER_PAGE)},${HANDOVER_QUERY}:n,url:u,html:h},o);
  }
  window.addEventListener("message",m);
  setTimeout(function(){
    if(done)return;
    window.removeEventListener("message",m);
    if(!w.closed)alert(${JSON.stringify(SILENT)}+o+"?");
  },${HANDOVER_TIMEOUT_MS});
})()`.replace(/\s*\n\s*/g, "");

/**
 * The value of the bookmark's `href`.
 *
 * `encodeURI` and not `encodeURIComponent`: the browser decodes the URL once
 * before running it, and the component form would escape the punctuation the
 * program is made of. What has to be encoded is what a URL cannot carry — the
 * spaces that survived the collapse, and the umlauts in the two German
 * sentences, which a bookmark file would otherwise mangle.
 */
export const bookmarkletHref = origin => `javascript:${encodeURI(bookmarkletCode(origin))}`;
