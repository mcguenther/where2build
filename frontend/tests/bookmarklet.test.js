/**
 * The bookmarklet, run rather than read.
 *
 * The source is a single line built from a template, because a `javascript:`
 * URL is a URL and a newline in it ends the bookmark. Asserting on that string
 * would prove nothing about whether collapsing it left a working program — so
 * these tests evaluate it, with `window.open` stubbed, and check the handover
 * protocol it is one half of. The other half is `WizardView.startHandover`,
 * tested in `wizard.test.js`.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  HANDOVER_QUERY,
  HANDOVER_READY,
  HANDOVER_PAGE,
  HANDOVER_TIMEOUT_MS,
  BOOKMARK_ICON,
  BOOKMARK_TITLE,
  bookmarkletCode,
  bookmarkletFile,
  bookmarkletFileBlob,
  bookmarkletHref
} from "../src/lib/bookmarklet.js";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ORIGIN = "https://where2build.example";

/** The window `window.open` hands back: it only has to remember what it was
 *  posted, and whether it is still open. */
const fakeTab = () => ({ postMessage: vi.fn(), closed: false });

/** A message as it arrives from the tab that was opened. `source` is a getter
 *  on the prototype, so it has to be shadowed with an own property — which is
 *  exactly the check the bookmarklet leans on. */
const messageFrom = (source, data) => {
  const event = new MessageEvent("message", { data });
  Object.defineProperty(event, "source", { value: source });
  return event;
};

let opened;
let openSpy;

beforeEach(() => {
  vi.useFakeTimers();
  opened = fakeTab();
  openSpy = vi.spyOn(window, "open").mockImplementation(() => opened);
  vi.spyOn(window, "alert").mockImplementation(() => {});
  document.documentElement.innerHTML =
    '<head><meta property="og:latitude" content="51.189265"></head>' +
    "<body><h1>Baugrundstück 502 m²</h1></body>";
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** Run the bookmarklet the way a click on the bookmark would. */
const click = () => {
  // eslint-disable-next-line no-eval
  eval(bookmarkletCode(ORIGIN));
};

describe("the bookmarklet's source", () => {
  it("is one line, so the bookmark survives being saved", () => {
    expect(bookmarkletCode(ORIGIN)).not.toContain("\n");
  });

  it("carries the app's own origin, since it runs on the portal's page", () => {
    expect(bookmarkletCode(ORIGIN)).toContain(JSON.stringify(ORIGIN));
  });

  it("encodes what a URL cannot carry, and leaves the program readable", () => {
    const href = bookmarkletHref(ORIGIN);
    expect(href.startsWith("javascript:")).toBe(true);
    expect(href).not.toMatch(/[ \n]/);
    // The umlauts of the two German sentences would be mangled by a bookmark
    // file; the punctuation the program is made of must not be.
    expect(href).toContain("%C3%BC");
    expect(decodeURI(href.slice("javascript:".length))).toBe(bookmarkletCode(ORIGIN));
  });
});

describe("the handover", () => {
  it("opens the wizard with a nonce and waits to be asked", () => {
    click();
    expect(openSpy).toHaveBeenCalledTimes(1);
    const [url, name] = openSpy.mock.calls[0];
    expect(url).toMatch(
      new RegExp(`^${ORIGIN}/aufnahme/quelle\\?${HANDOVER_QUERY}=\\d+$`)
    );
    expect(name).toBe("where2build");
    // Nothing is sent before the other tab says it is listening.
    expect(opened.postMessage).not.toHaveBeenCalled();
  });

  it("sends the whole document once the tab announces itself", () => {
    click();
    const nonce = new URL(openSpy.mock.calls[0][0]).searchParams.get(HANDOVER_QUERY);
    window.dispatchEvent(
      messageFrom(opened, { w2b: HANDOVER_READY, [HANDOVER_QUERY]: nonce })
    );

    expect(opened.postMessage).toHaveBeenCalledTimes(1);
    const [payload, target] = opened.postMessage.mock.calls[0];
    expect(target).toBe(ORIGIN);
    expect(payload.w2b).toBe(HANDOVER_PAGE);
    expect(payload[HANDOVER_QUERY]).toBe(nonce);
    // The point of the whole exercise: `<head>` travels, which is what a
    // Ctrl+A selection leaves behind.
    expect(payload.html).toContain('property="og:latitude"');
    expect(payload.html).toContain("Baugrundstück 502 m²");
    expect(payload.html.startsWith("<html")).toBe(true);
  });

  it("ignores a message with the wrong nonce", () => {
    click();
    window.dispatchEvent(
      messageFrom(opened, { w2b: HANDOVER_READY, [HANDOVER_QUERY]: "nicht-die-nonce" })
    );
    expect(opened.postMessage).not.toHaveBeenCalled();
  });

  it("ignores a message from any window but the one it opened", () => {
    click();
    const nonce = new URL(openSpy.mock.calls[0][0]).searchParams.get(HANDOVER_QUERY);
    window.dispatchEvent(
      messageFrom(fakeTab(), { w2b: HANDOVER_READY, [HANDOVER_QUERY]: nonce })
    );
    expect(opened.postMessage).not.toHaveBeenCalled();
  });

  it("sends the document once, however often the tab asks", () => {
    click();
    const nonce = new URL(openSpy.mock.calls[0][0]).searchParams.get(HANDOVER_QUERY);
    const ready = () =>
      window.dispatchEvent(
        messageFrom(opened, { w2b: HANDOVER_READY, [HANDOVER_QUERY]: nonce })
      );
    ready();
    ready();
    expect(opened.postMessage).toHaveBeenCalledTimes(1);
  });

  it("says so when the popup was blocked, and opens nothing", () => {
    openSpy.mockImplementation(() => null);
    click();
    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("Pop-ups"));
  });

  it("says so when the app never answers", () => {
    click();
    vi.advanceTimersByTime(HANDOVER_TIMEOUT_MS);
    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining(ORIGIN));
  });

  it("stays quiet when the app answered, or when the tab is gone", () => {
    click();
    const nonce = new URL(openSpy.mock.calls[0][0]).searchParams.get(HANDOVER_QUERY);
    window.dispatchEvent(
      messageFrom(opened, { w2b: HANDOVER_READY, [HANDOVER_QUERY]: nonce })
    );
    vi.advanceTimersByTime(HANDOVER_TIMEOUT_MS);
    expect(window.alert).not.toHaveBeenCalled();

    opened.closed = true;
    click();
    vi.advanceTimersByTime(HANDOVER_TIMEOUT_MS);
    expect(window.alert).not.toHaveBeenCalled();
  });
});

/* The icon the app actually serves, not a stand-in: the file is only worth
 * anything if the picture in it is the one the tab shows. */
const iconBytes = readFileSync(resolve(__dirname, "../public", BOOKMARK_ICON.slice(1)));
const iconDataUrl = `data:image/png;base64,${iconBytes.toString("base64")}`;

describe("the bookmarks file", () => {
  it("holds the bookmarklet unchanged, with the icon, on one line", () => {
    // Chromium's importer reads the format line by line: an entry broken over
    // two lines is no entry. Measured on 25.09.2026 in Chromium 141 — imported
    // from this file, the bar shows the app's icon; the same entry without
    // `ICON` shows the grey globe, which is what a dragged bookmarklet gets.
    const line = bookmarkletFile(ORIGIN, iconDataUrl)
      .split("\n")
      .find(entry => entry.includes("<A "));

    expect(line).toContain(`HREF="${bookmarkletHref(ORIGIN)}"`);
    expect(line).toContain(`ICON="${iconDataUrl}"`);
    expect(line).toContain(`>${BOOKMARK_TITLE}</A>`);
  });

  it("needs no escaping, because the href has nothing to escape", () => {
    // The href goes into the attribute as it is. That is only right while
    // `encodeURI` leaves no quote, ampersand or angle bracket in it.
    expect(bookmarkletHref(ORIGIN)).not.toMatch(/["'&<>]/);
  });

  it("puts the bookmark into the bookmarks bar", () => {
    expect(bookmarkletFile(ORIGIN, iconDataUrl)).toContain('PERSONAL_TOOLBAR_FOLDER="true"');
  });

  it("reads the icon the app serves and embeds it", async () => {
    const fetcher = vi.fn(async () => new Response(iconBytes, { status: 200 }));

    const blob = await bookmarkletFileBlob(ORIGIN, fetcher);

    expect(fetcher).toHaveBeenCalledWith(BOOKMARK_ICON);
    expect(blob.type).toBe("text/html;charset=utf-8");
    expect(await blob.text()).toBe(bookmarkletFile(ORIGIN, iconDataUrl));
  });

  it("says so when the icon is not there, rather than saving a file without it", async () => {
    const fetcher = async () => new Response("", { status: 404 });

    await expect(bookmarkletFileBlob(ORIGIN, fetcher)).rejects.toThrow("HTTP 404");
  });
});
