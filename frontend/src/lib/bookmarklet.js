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

/** What the bookmark is called: the button's text, and the file's entry. */
export const BOOKMARK_TITLE = "Grundstück prüfen";

/** The icon the file carries, and what it is called when it is saved. */
export const BOOKMARK_ICON = "/favicon-96x96.png";
export const BOOKMARK_FILE = "where2build-lesezeichen.html";

/**
 * The bookmarklet as a bookmarks file, which is the one way it gets an icon.
 *
 * A bookmark's icon is not a property of the bookmark. The browser keeps one
 * per *page*, recorded when that page loads, and a `javascript:` bookmark
 * never loads one — so a dragged bookmarklet shows the browser's blank icon,
 * and nothing on the dragged link can change that. The Netscape bookmarks file
 * every browser imports carries an `ICON` data URL per entry, though, and
 * Chromium's importer stores that picture against the entry's own URL.
 *
 * Chromium reads this format line by line, so the entry has to stay on one
 * line; and the href is put into the attribute as it is, which is safe only
 * because `encodeURI` leaves no quote, `&`, `<` or `>` in it — a test holds
 * that. The folder is the bookmarks bar, which is where the bookmark belongs.
 */
export const bookmarkletFile = (origin, iconDataUrl) =>
  [
    "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
    '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
    "<TITLE>Bookmarks</TITLE>",
    "<H1>Bookmarks</H1>",
    "<DL><p>",
    '    <DT><H3 PERSONAL_TOOLBAR_FOLDER="true">where2build</H3>',
    "    <DL><p>",
    `        <DT><A HREF="${bookmarkletHref(origin)}" ICON="${iconDataUrl}">${BOOKMARK_TITLE}</A>`,
    "    </DL><p>",
    "</DL><p>",
    ""
  ].join("\n");

const ICON_MISSING = "Das Symbol für das Lesezeichen ließ sich nicht laden";

/**
 * The bookmarks file, ready to save. The icon is read from the app's own
 * `public/` at the moment of saving rather than copied into the bundle, so the
 * bookmark carries the picture the tab carries.
 */
export async function bookmarkletFileBlob(origin, fetcher = fetch) {
  const response = await fetcher(BOOKMARK_ICON);
  if (!response.ok) throw new Error(`${ICON_MISSING} (HTTP ${response.status}).`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const icon = `data:image/png;base64,${btoa(binary)}`;
  return new Blob([bookmarkletFile(origin, icon)], { type: "text/html;charset=utf-8" });
}
