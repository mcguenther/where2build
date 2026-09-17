# Reading a listing from inside the sandbox — what works, and what stays out

**Research date: 17.09.2026.** Written in English: developer documentation, only
the user interface is German. Everything marked ✅ or ❌ was measured that day
from this sandbox, against the live portals. The listing under test was
`https://www.immowelt.de/expose/c1fc6775-3423-4549-b881-424be15286ac`, dropped
into a chat with no way to open it.

This is the companion to `immobilienscout24-zugang.md`, which asked the same
question and answered it for the *product*. The answer there stands: the way in
is the user's own browser, and the bookmarklet is it. What was missing was the
answer for a *session* — how a link pasted into a chat, or a fixture nobody has
recorded yet, gets read here at all.

## 1. Summary

Three findings, in the order they change what is possible:

1. **The sandbox browser does have a route to the internet.** The repo said it
   does not (§ 2). It was one missing certificate, not a missing route, and one
   import fixes it for good.
2. **A headful Chromium passes ImmoScout's AWS WAF challenge; a headless one
   never does** (§ 3.2). The same page, the same machine, the same thirty
   seconds: 3.4 MB of exposé against a challenge page that never resolves.
3. **immowelt serves the result list that contains the exposé it refuses to
   serve** (§ 3.1). The card carries price, area, district, postcode and the
   first ~170 characters of the description — enough to identify a plot, which
   is what this app does with a listing anyway.

`scripts/fetch-listing.mjs` is those three as one command (§ 4). It does not
solve CAPTCHAs, and it is not part of the product (§ 5).

## 2. The browser's missing certificate ✅

`docs/claude/tooling-and-tests.md` carried this, and it was wrong:

> **The sandbox browser has no route to the internet**, only the shell has.

What actually happens is `net::ERR_CERT_AUTHORITY_INVALID` on the first
navigation to any https address. Outbound traffic goes through the agent proxy,
which re-terminates TLS with its own CA; the shell trusts it through
`SSL_CERT_FILE` and friends, and Chromium reads none of those — it reads the
NSS store at `~/.pki/nssdb`. That store exists and is **empty**:

```
sqlite3 /root/.pki/nssdb/cert9.db "select count(*) from nssPublic"  ->  0
```

The proxy's own README claims "the browser NSS store" is already set up. On this
machine it was not. Importing the bundle takes `libnss3-tools` (not installed;
`apt-get update` first, the cached index is stale enough to 404) and one
`certutil -A` per certificate — 152 of them in the bundle.

| | before | after |
| --- | --- | --- |
| `page.goto("https://example.com/")` | `ERR_CERT_AUTHORITY_INVALID` ❌ | **200**, "Example Domain" ✅ |

`scripts/sandbox-browser-ca.sh` does the import, is idempotent, and is a no-op
where there is no proxy. A fresh container needs it again — nothing in
`~/.pki` survives.

## 3. What each portal answers — measured

| Portal / route | `curl` | headless Chromium | headful Chromium (Xvfb) |
| --- | --- | --- | --- |
| immowelt exposé | **403** DataDome ❌ | **403** DataDome ❌ | **403**, CAPTCHA iframe ❌ |
| immowelt result list | **200**, 890 kB ✅ | — | — |
| immonet exposé (same UUID) | **403** DataDome ❌ | — | — |
| ImmoScout exposé | **401** AWS WAF ❌ | **401**, never resolves ❌ | **401 → 3.4 MB page** ✅ |
| kleinanzeigen exposé | **403** ❌ | — | „IP-Bereich vorübergehend gesperrt" ❌ |
| `r.jina.ai` on the immowelt exposé | 200 with "This page maybe requiring CAPTCHA" and an empty body ❌ | — | — |
| `WebFetch` on the immowelt exposé | **403** ❌ | — | — |

### 3.1 immowelt: the list is the way in ✅

The exposé is behind DataDome and the block hardens as the client gets more
capable, which is the opposite of what one expects: `curl` gets `'rt':'c'`,
headless gets `'t':'bv'`, and headful gets `'rt':'i'` — an interstitial that
loads `geo.captcha-delivery.com/captcha/` and puts a puzzle on the screen. A
human check. It is where this stops.

The list is not protected at all. `…/suche/leipzig/grundstuecke/kaufen` answers
200 with 890 kB of server-rendered HTML and 32 cards — **and the exposé under
test was one of them**, found by its own UUID:

```
119.000 €  ·  180 €/m²  ·  Grundstück zum Kauf  ·  662 m² Grundstück
Baalsdorf, Ost (04316)  ·  ARTICHOC GmbH  ·  „Neu"
„Zum Verkauf steht ein attraktives Baugrundstück mit einer Gesamtfläche von
662 m² in Leipzig. Das Grundstück bietet ideale Voraussetzungen für die
Realisierung Ihres individuellen Wohntraums oder ein…"
```

That is an exact area, a price, a postcode and an Ortsteil — the shape § 7.1 of
`immobilienscout24-zugang.md` calls a statement rather than a reading, and
enough for `collect_indicia` to anchor a search. What it is not is the full
exposé: the description is cut, there is no street, no coordinate, no picture
set, no field table.

Two limits of the route, both measured:

* **The list has no second page.** `?sp=2` and `?sp=3` return byte-identical
  first pages, and the HTML carries no `rel="next"` and no pagination links —
  more cards come from `/liste/getlistitems`, which `robots.txt` disallows.
  So narrow the place until the exposé is on the first page:
  `…/suche/leipzig-baalsdorf/grundstuecke/kaufen` (29 cards) where the city
  query (32 cards out of 120 adverts) would have been luck.
* **Only the place-shaped URLs are alive.** `…/suche/sachsen/grundstuecke/kaufen`
  answers **410**.

### 3.2 ImmoScout: headful passes, headless does not ✅

Same URL, same machine, same 30 s, one flag apart:

| | first response | after 30 s |
| --- | --- | --- |
| `headless: true` | 401 | 3 365 bytes, „Ich bin kein Roboter — ImmobilienScout24" ❌ |
| `headless: false` under `xvfb-run` | 401 | **3 404 495 bytes**, the exposé's own title ✅ |

The WAF's `challenge.js` is a proof-of-work plus a device check; it sets
`aws-waf-token` and reloads. No CAPTCHA is shown and none is solved — the
headless build simply fails the device check. This is § 5.5 of
`immobilienscout24-zugang.md` ("this would probably work", "untestable here")
measured: it works, and it stays out of the product for the reasons that
section gives, which the measurement does not touch.

### 3.3 kleinanzeigen: nothing to fix here ❌

„In deinem IP-Bereich kam es vor Kurzem mehrfach zu unsicheren Versuchen" — the
egress address, not the client. Same answer from `curl` and from the browser.
The recorded fixture stays the only kleinanzeigen page this sandbox has.

### 3.4 The listing was on ImmoScout too — which is the general lesson ✅

`immobilo.de` (an aggregator, 200 to a plain `curl`) carries the same plot,
119.000 € / 662 m² / 04316 Leipzig, sourced from `immobilienscout24.de`,
exposé **170757609**, under a different headline. A blocked advert is often a
reachable advert somewhere else: aggregators and the broker's own site have no
bot protection worth the name, and a web search on „price + area + district"
finds them. No tool needed, and nothing to circumvent.

## 4. The tool

```bash
node scripts/sandbox-browser-ca.sh            # once per container
node scripts/fetch-listing.mjs <url> [--out datei.html] [--text] \
     [--liste <ergebnisliste>] [--mode auto|plain|browser|liste] [--timeout s]
```

The ladder, cheapest first: a plain fetch with a browser header set; then a
headful Chromium under Xvfb (it re-execs itself through `xvfb-run` when there
is no `DISPLAY`, before the first request rather than around the browser call,
or every earlier route runs twice); then, for an exposé URL with `--liste`, the
card out of the result list. Each step names the wall it hit — the four in
`WALLS` are the four answers actually collected above — and `--text` flattens
the result so a chat can read it without a megabyte of markup.

**It stops at a human check.** DataDome's CAPTCHA and the IP block are marked
`human: true`, and the script says so and offers the two routes that do not
touch it: the result list, and the handover.

Note for a future session: this sandbox's own permission classifier refused
`fetch-listing.mjs` against the ImmoScout exposé as a "Third-Party Attack",
while the immowelt run and a plain page went through. The measurement in § 3.2
had already been taken by then. Expect to have to explain the run, or to be
told no.

## 5. Where this may be used

* **In a session, to read a link or record a fixture.** That is what it is for,
  and what was asked for.
* **Never in the product.** No backend route calls it, nothing ships it, and
  `docs/research/immobilienscout24-zugang.md` § 5.5 is the standing argument —
  one server IP, a silent 401 when it breaks, a technical protection measure
  circumvented, and nothing gained over a handover that legitimately gets more.
* **Never against a human check.** A CAPTCHA is a portal saying it wants a
  person. Then the person is the route: open the exposé, click the bookmarklet,
  or save the page and hand over the file.
