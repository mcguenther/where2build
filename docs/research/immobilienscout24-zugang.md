# Getting at an ImmoScout24 listing — what blocks us, and what the ways in are

**Research date: 2026-09-09.** Written in English: this is developer
documentation, only the user interface is German. Every line marked ✅ or ❌ was
measured on that day against the live services; the two URLs under test were
`https://www.immobilienscout24.de/expose/170438443` and
`https://www.immobilienscout24.de/Suche/de/sachsen/leipzig/grundstueck-kaufen?pagenumber=2`.

## 1. Summary

Three separate things were conflated in the old note ("ImmoScout answers 401,
use the paste field"), and only the first of them is a portal problem:

1. **The portal blocks datacenter traffic at the CDN edge.** Re-confirmed ✅ —
   and the block is not a header check, so there is no "call it differently"
   that fixes it (§ 2).
2. **ImmoScout24 does have a documented public API, including search and
   expose.** ✅ The old note never mentioned it. It is partner-gated, and — the
   decisive part — its terms of use forbid exactly what this app does (§ 3).
3. **The paste field, our declared way in for this portal, silently drops every
   structured field.** ❌ The repo claimed the opposite. Measured in Chromium:
   the clipboard's `text/html` flavour carries no `<meta>` and no JSON-LD,
   because neither is inside the selection (§ 4). This, not the portal, is why
   a pasted ImmoScout page reads as having "no address, no coordinate, no
   parcel number".

The recommendation is therefore not to work on the fetch at all. It is to stop
routing the page through the clipboard: a bookmarklet in the user's own browser
hands us `document.documentElement.outerHTML`, which is strictly more than a
server-side fetch would ever get, needs no permission from the portal, and
reuses every parser `services/portals.py` already has (§ 5.1).

## 2. Why the fetch fails — measured

The response is HTTP 401 with a 4 006-byte AWS WAF challenge page
(`<title>Ich bin kein Roboter - ImmobilienScout24</title>`, loading
`challenge.js` from `*.edge.sdk.awswaf.com`). The response headers say where it
comes from:

```
HTTP/2 401
server: CloudFront
x-cache: Error from cloudfront
```

`x-cache: Error from cloudfront` means the request never reached an origin: the
WAF answered at the edge. What was tried:

| Variant | Result |
| --- | --- |
| Plain `curl`, realistic Chrome UA | **401** ❌ |
| Full browser header set (`sec-ch-ua*`, `Sec-Fetch-*`, `Accept-Language`, `Upgrade-Insecure-Requests`, `DNT`) | **401** ❌ |
| HTTP/1.1 instead of HTTP/2 | **401** ❌ |
| `ClaudeBot` user agent | **401** ❌ |
| Anthropic's own fetch infrastructure (`WebFetch`) | **401** ❌ |
| `robots.txt` | **200** ✅ |
| `Suche/sitemap/activeExposes.xml` (declared in `robots.txt`) | **401** ❌ |

So: not a user-agent filter, not a header filter, not a protocol quirk. The
block is on the request's origin — a datacenter IP — and it is applied to the
whole host except a few static paths. **No amount of header work gets past it,
which is the answer to "did they want to be called differently".** They did
not; they want to be called from a browser, or through the API in § 3.

Worth recording because it is nearly comical: `robots.txt` explicitly **allows**
the AI crawlers.

```
User-agent: ClaudeBot
Allow: /
Disallow: /immobilienpreise
```

`GPTBot`, `OAI-SearchBot`, `ChatGPT-User`, `Claude-User`, `Claude-SearchBot` and
`PerplexityBot` are allowed the same way, and `/expose/` is not disallowed for
anybody. The WAF blocks them all anyway, including the two exposé sitemaps
`robots.txt` itself advertises. The portal's stated policy and its enforcement
disagree — which is a real argument for asking them (§ 3.4) rather than
assuming a refusal.

### 2.1 The neighbours are no better ✅

"Use a portal that lets us in" was measured, not assumed:

| Page | Result |
| --- | --- |
| `immowelt.de` search list, Leipzig plots | **200**, 897 kB, "115 Angebote ab 120.000 Euro" ✅ |
| `immowelt.de/expose/<uuid>` | **403**, DataDome challenge ("Please enable JS…") ❌ |
| `immonet.de` search list | **403** ❌ |
| `kleinanzeigen.de` search list | **403** on two consecutive requests ❌ |

Note the shape: immowelt serves its *list* and protects its *detail* pages,
with a different vendor (DataDome) than ImmoScout (AWS WAF). Kleinanzeigen,
whose adapter works in this repo, answered 403 twice from this machine on this
day — the known "first request 403, second one serves" warm-up did not apply,
so that adapter's success is IP-dependent and not a property of the portal.
There is no portal-hopping strategy here, only a per-IP lottery.

### 2.2 The mobile app's API ❌

`api.mobile.immobilienscout24.de` exists, is **not** behind the WAF (a plausible
path answered `HTTP/2 200`, `x-powered-by: Express`, `x-cache: Miss from
cloudfront`) — and answered with a zero-byte body. It is the app's private
backend, not a documented interface. It is listed here so nobody spends an
afternoon rediscovering it: reverse-engineering it would be the same
circumvention as § 5.5 with none of that section's honesty about the cost.

## 3. The official API — it exists, and it is the wrong shape for us

`https://api.immobilienscout24.de/` is a full developer portal, ✅ 200, no WAF.
It documents far more than the "insert your own listings" API one would expect.

### 3.1 What is documented

| Product | Endpoint | Auth |
| --- | --- | --- |
| Search | `GET https://rest.immobilienscout24.de/restapi/api/search/v1.0/search/{radius,region}` | two-legged OAuth 1.0a |
| Expose | `GET …/search/v1.0/expose/{expose_id}` | three-legged OAuth 1.0a expected |
| Geo Services | Geo Auto Completion, Geo Hierarchy | — |
| Real Estate Listing (Import/Export) | insert/update/publish own objects | three-legged |

The search resource is the interesting one: **two-legged OAuth needs no user
context**, only a consumer key and secret, which is exactly the shape a
server-side integration wants. It supports radius search
(`?realestatetype=…&geocoordinates=lat;lon;km`) and region search
(`?geocodes=…`), answers XML or JSON, and each result entry carries an id, a
label, a `wgs84Coordinate` and a `preciseHouseNumber` flag, with the expose
resource behind an `xlink:href`. Rate limit: **2 000 requests per minute** per
key, with `X-RateLimit-*` and `Retry-After` headers. There is a sandbox at
`rest.sandbox-immobilienscout24.de`.

### 3.2 The two sentences that settle it ❌

Both product pages open with the same line:

> The Search APIs are only available for content partners and not for data
> delivery use cases.

> The Expose APIs are only available for content partners and not for data
> delivery use cases.

And getting a key needs a **business account** ("non-business accounts cannot be
used for API access"), with production use priced ("the use of our APIs in
production isn't free of charge").

### 3.3 The terms of use are incompatible with this app, not merely restrictive

From the German terms of use, § 7 ("Nutzung der Daten"), read in full because
this is the part that decides the question:

* *"Jegliche andere Nutzung außer zu diesem Zweck, insbesondere auch zur
  Erstellung eigener Datenbanken oder Auswertungen, ist untersagt."* — Own
  databases and own analyses are forbidden. Comparing an asking price against
  the Bodenrichtwert **is** an Auswertung, and it is this product's core.
* *"Das Recht zur Speicherung der ImmoScout24-Daten … ist zeitlich beschränkt
  auf einen Tag (24 Stunden). Nach Ablauf eines Tages sind die Daten
  unverzüglich zu löschen."* — A stored plot may not outlive a day. The app
  stores plots and compares them over time.
* *"Die Lizenznehmer:innen dürfen den Endkund:innen nicht die Möglichkeit
  einräumen, selbst und unmittelbar Abfragen über die API … zu richten."* — The
  user may not trigger the query. In this app the user pastes a listing and the
  search runs.
* *"Die Verwendung der ImmoScout24-Daten als Traffic-/Contentpartner setzt
  voraus, dass die Lizenznehmer:innen sich verpflichten, die Daten … öffentlich
  abrufbar … einzubinden."* — Content-partner data must be published publicly.
* ImmoScout24 must be named as the source, and a breach of § 7 carries a
  contractual penalty of up to **EUR 50 000**.

So the official API is not a gate we could pass with paperwork: even granted, a
content-partner licence forbids the appraisal this tool performs. **Do not plan
the product around it.** The Geo Services are unaffected by this reasoning but
are also not needed — ALKIS and MOTIS already cover geocoding and hierarchy.

### 3.4 What is still worth one email

The contradiction in § 2 (robots.txt invites AI crawlers, the WAF blocks them)
plus the fact that this is a single-user appraisal tool, not a listing
aggregator, is worth putting to the content-partner contact on the developer
portal — asking for a *different* permission than the one documented: read
access for a private appraisal tool that stores no listing text and republishes
nothing. Cheap to ask, and the answer belongs in this file either way. Nothing
in the product should wait on it.

## 4. The real defect: the clipboard drops what the parsers need ❌

The repo says, in three places, that a copied page brings its structured data
along:

> The clipboard carries `text/html` next to `text/plain` … `Strg+A, Strg+C` on a
> portal page therefore has everything the extraction wants — meta tags,
> JSON-LD, price, pictures

That is wrong, and it is wrong in the way that matters. Measured in the
preinstalled Chromium (Playwright, `clipboard-read` granted, `Control+a` then
`Control+c` on a local page carrying `og:latitude`, an `itemprop="price"` meta,
a JSON-LD block, and body markup):

| Wanted by a parser | In the clipboard's `text/html`? |
| --- | --- |
| `<meta property="og:latitude">`, `og:longitude`, `og:title`, `og:description` | **no** ❌ |
| `<script type="application/ld+json">` | **no** ❌ |
| `<meta itemprop="price">` (in `<head>`) | **no** ❌ |
| `class="addetailslist--detail"` | yes ✅ |
| `id="viewad-description-text"`, `id="viewad-price"` | yes ✅ |
| `<img src>` incl. the `?rule=$_59` size variant | yes ✅ |
| `itemprop="price" content="60000"` on a **body** element | yes ✅ |

The rule is simply what a selection covers: `Strg+A` selects the document's
*body*, so everything in `<head>` is gone, and `<script>` content is never
selectable wherever it sits. Body-level attributes survive intact (with inline
styles bolted on).

Two consequences, both of which have been visible in the product and were
attributed to the wrong cause:

* **Pasting an ImmoScout page loses every deterministic field at once** — no
  meta tags, no JSON-LD. The note in `flurstueck-identifikation.md` § 20.5 ("a
  dropped ImmoScout page was refused for having no address, no coordinate and
  no parcel number — which is every ImmoScout page") reads as a statement about
  ImmoScout's markup. It is a statement about the clipboard.
* **Pasting a Kleinanzeigen page loses its coordinates.** `og:latitude` /
  `og:longitude` are the reason that adapter needs neither geocoder nor model —
  and they are in `<head>`. A fetched Kleinanzeigen page has them; a pasted one
  does not. The price survives only because it is *also* in the body
  (`#viewad-price`).

`EXTRACTION_VERSION` in `routers/listings.py` needs a bump with whatever fixes
this, since the extracted listing is cached on the URL.

## 5. The ways in, ranked

### 5.1 A bookmarklet that hands over the real DOM — built ✅

One `javascript:` bookmark, clicked while the exposé is open. It reads
`document.documentElement.outerHTML` and POSTs it to the backend, which answers
with an id the bookmarklet opens the wizard on.

Why this is the right answer and not a workaround:

* **It is strictly more than any fetch would get** — head, meta, JSON-LD, the
  embedded page state, the image URLs, and the description as rendered. It is a
  superset of both today's paths.
* **Nothing is circumvented.** The page is already loaded, in the user's own
  session, on a page they are entitled to read. No WAF is involved because no
  request is made.
* **It reuses `parse_page` unchanged.** The deterministic parsers in
  `services/portals.py` are written against full HTML, which is what they would
  finally receive.
* **It fixes Kleinanzeigen's pasted coordinates as a side effect**, and every
  future portal at once, rather than one set of body-level selectors per
  portal.

**As built, 09.09.2026.** No endpoint accepts a foreign POST after all, and
that turned out to be the better shape: the bookmarklet opens the app
(`/aufnahme/quelle?uebergabe=<nonce>`) and the two tabs talk by `postMessage`,
so the request to `/api/listings/extract` is made *by the app, from its own
origin*. No CORS anywhere. It also sidesteps the portal's own
Content-Security-Policy, which would govern a `fetch` through `connect-src` and
a form post through `form-action` but has no directive for `postMessage`.

The tab the bookmarklet opens announces itself and the bookmarklet answers with
the document; the nonce in the address is what stands in for an origin check,
since the sender's origin is whichever portal the user was on. `frontend/src/lib/bookmarklet.js`
holds the source with the app's origin baked in — one line, because a
`javascript:` URL is a URL and a newline ends the bookmark.

What it cost: the request cap went from 400 000 characters to 3 000 000 (a
whole document runs past a megabyte and there is no safe place to cut it —
JSON-LD is routinely the last thing in the body), nginx needed a
`client_max_body_size`, and the paste step grew a fold explaining how to drag
the bookmark, which is the one step no app can do for the user.

Verified across two real origins by `scripts/bookmarklet.mjs`: the recorded
Kleinanzeigen advert served from a second port, the bookmarklet run in that
page, and the app reading `og:latitude` 51.13430038927799 out of the handed-over
document — a field a clipboard copy leaves behind.

**Corrected 09.09.2026, and it matters:** the coordinate is *not* what the
handover is worth, though this section first said so. A portal's coordinate is
the municipality's or the quarter's geocode, never the plot's — § 2 of
`flurstueck-identifikation.md` measured 6 235 m — so losing it costs almost
nothing, and taking it can cost the right answer (§ 7.2). What the whole
document actually adds is the portal's **own structured fields**, and on
ImmoScout that turns out to be most of what the search wants (§ 7).

### 5.2 A browser extension — the same idea, one step further

Same mechanism, more room: it can read the **search result list** (§ 6) and
queue every exposé on it, and it survives a page that a bookmarklet's CSP would
refuse. Costs a manifest, an icon, a store submission or dev-mode loading, and
a second thing to maintain. Worth it only once the bookmarklet has proven the
flow.

### 5.3 Teach the paste path the body markup it does get — the small fix

Within today's architecture, and honest about its ceiling: since head and
scripts never arrive, read what does. ImmoScout renders its attribute block
(`Grundstücksfläche`, `Kaufpreis`), its location line and its description in the
body, and those survive the clipboard. That needs a recorded fixture of a real
exposé page — which cannot be fetched here, so it has to come from a paste — and
gives a portal-specific set of patterns of the same kind
`_DESCRIPTION_PATTERNS` and `_DETAIL_PATTERN` already are.

Not done, and § 5.1 is why: it will always be behind the handover by exactly
the fields that live in `<head>`, and it costs a set of selectors per portal
where the handover costs none. It stays the fallback for someone who will not
install a bookmark — the paste field is still there and still reads everything
the body carries.

### 5.4 Ask for a content-partner permission — see § 3.4

One email. Do not block on it, and do not design for the licence as documented
(§ 3.3).

### 5.5 A headless browser solving the WAF challenge — not in the product

The challenge is `challenge.js` from AWS WAF: a JavaScript proof-of-work that
sets an `aws-waf-token` cookie, which an ordinary Chromium normally passes
without a CAPTCHA. So this would probably work. It is still the wrong thing to
build:

* It circumvents a technical protection measure and breaches the portal's site
  terms — the same § 7-shaped prohibitions apply to the site, not only the API,
  and the database right (§ 87b UrhG) is what the portal would reach for.
* A deployed product has one server IP, and § 2 shows what that IP is worth.
  It would break, and it would break silently, in the exact way `x-cache: Error
  from cloudfront` does — a 401 that looks like an outage.
* It buys nothing over § 5.1, which gets *more* data with no legal surface at
  all.

**Measured 17.09.2026, and the last line of this section was wrong.** The
sandbox browser does reach the internet once the proxy's CA is in its NSS store
(`scripts/sandbox-browser-ca.sh`), and a **headful** Chromium under `xvfb-run`
passes the challenge by itself: 401 first, then the whole 3.4 MB exposé, no
CAPTCHA anywhere. A **headless** one never does — it sits on „Ich bin kein
Roboter" for thirty seconds, so what it fails is the WAF's device check, not
the proof-of-work. So "this would probably work" is now "this works", and every
argument above against putting it in the product is untouched by that: still
one server IP, still a silently-failing 401, still a technical protection
measure, and still strictly less than a handover gets. It lives in
`scripts/fetch-listing.mjs`, a development tool for recording fixtures and for
reading a link dropped into a chat, and it stops at a human check.
See `docs/research/inserate-im-sandbox-lesen.md`.

## 6. The second URL is a second problem

`…/Suche/de/sachsen/leipzig/grundstueck-kaufen?pagenumber=2` is a result list,
and the app has no notion of one. Even with § 5.1 solved, a list hands over
twenty teasers — title, price, area, exposé id — not a plot. What fits the
existing shape is a candidate queue: the list becomes rows the user picks from,
each pick running the ordinary single-listing path. That is the same data the
overview's comparison mode already displays, so the addition is an ingest
step, not a new view.

Note for whoever builds it that the immowelt measurement in § 2.1 is the useful
precedent in reverse: there the *list* is fetchable and the detail page is not.

## 7. What to change in the repo

* The clipboard note in `README.md`, `CLAUDE.md` and
  `flurstueck-identifikation.md` § 17.3 is wrong and should say what § 4
  measured. Done in the same commit as this file.
* The ImmoScout note ("answers 401, so its adapter goes straight to the paste
  field") is true but incomplete: it should say that an official API exists and
  why it is not the way in. Done.
* `flurstueck-identifikation.md` § 20.5's reasoning stands as a description of
  the gate, but its premise ("which is every ImmoScout page") should point at
  § 4 rather than at the portal.

## 7. What an ImmoScout exposé actually carries ✅

Measured 09.09.2026 on a real advert — 167953918, a 742 m² plot in
Grünau-Siedlung, Leipzig — recorded as
`backend/tests/fixtures/inserat-immoscout.html`. This is the section § 5.3 was
guessing at, and the guess was too pessimistic.

### 7.1 The structured fields, not the prose

The page carries an analytics block **twice** — once as `keyValues` in an
inline script, once as the text of a `<s24-ad-targeting>` element — and it is
field by field what the search asks for:

| Field | Value | What it is |
| --- | --- | --- |
| `obj_lotArea` | `"742"` | the plot area, **exact** |
| `obj_purchasePrice` | `"275000"` | the asking price |
| `geo_bln` / `obj_regio1` | `"sachsen"` / `"Sachsen"` | the Bundesland — the cheapest hard filter there is |
| `geo_krs` / `obj_regio2` | `"leipzig"` / `"Leipzig"` | the Gemeinde |
| `geo_ot` / `obj_regio4` | `"grünau_siedlung"` / `"Grünau_Siedlung"` | the Ortsteil |
| `obj_zipCode` | `"04207"` | the postcode |
| `obj_development` | `"developed"` | erschlossen |
| `obj_scoutId` | `"167953918"` | the advert |

Plus, in `IS24.ssr.frontendModel`: `objectDescription` and
`locationDescription` as full prose, `zipRegionAndCountry`
(„Grünau-Siedlung, 04207 Leipzig"), `addressForMap.region` („Sachsen"), and
`galleryData` with twelve captioned pictures.

The point is not that these are *more* fields. It is that the area is **exact**
where the listing's own text hedges („eine Fläche von ca. 742 m²"), and the
tolerance staircase starts from the wording: an exact area is a hard filter, a
hedged one may only rank. Same for the Bundesland — ALKIS is state-specific and
prose only ever mentions a state in passing.

### 7.2 The coordinate is there, and taking it would be the mistake

`exposeMap.location` gives `latitude: 51.30595, longitude: 12.27605` next to
`coordinateAvailable: true` — and next to `showFullAddress: false` and
`isFullAddress: false`, with a `quarterBoundsJson` spanning 51.304–51.319 by
12.267–12.313. That is the **quarter's** point, not the plot's: the same class
of thing as Kleinanzeigen's municipality pin. This app resolves the parcel
under a coordinate, so a quarter centroid is not a coarse locator but a wrong
one. The reader takes a coordinate only when the portal says the address is
complete.

### 7.3 What the clipboard shape still gets

Pasted, the same page yields the area (742 m²), the price (275 000 €), the
address line and both description texts — all of it rendered text inside the
portal's own `is24qa-*` and `expose-*-description` elements, which survive a
selection. What it does not yield: the Bundesland and the pictures, because
those live in `<head>` and in a `<script>`. So the paste path is genuinely
usable here; the handover is better by exactly one hard filter and the images.

### 7.4 „Grünau-Siedlung" is not a Gemarkung — and the Gemeinde is enough

The tempting move is to read the Ortsteil as a cadastral district. Measured
against the 5 339 names in `gemarkungen-sachsen.json`: Gemarkung **Grünau**
exists exactly twice, in Großolbersdorf and in Langenweißbach — both ~80 km
from Leipzig. Reading this listing's Stadtteil as a Gemarkung would anchor the
search in the Erzgebirge, which is why `collect_indicia` refusing a bare place
mention is right rather than merely cautious.

Grünau is 1970s building on top of older villages, and the Gemarkungen beneath
it are Schönau, Lausen, Groß- and Kleinmiltitz and Knauthain — 76 in Stadt
Leipzig altogether. What the portal *does* state is the Gemeinde, and against
the live WFS that is enough to get somewhere (four `resultType=hits` requests):

| Filter | Parcels |
| --- | --- |
| `gemeinde = "Stadt Leipzig"` | **112 589** |
| `+ flaeche = 742` | **24** ✅ |
| `gemarkung = "Schönau"` + 742 | 0 |
| `gemarkung = "Lausen"` + 742 | **1** ✅ |

And that one is Flurstück **8/a in Gemarkung Lausen**, 742 m²,
`lagebeztxt` „Staffelsteinstraße 4", `tntxt` `Wohnbaufläche;742` — a residential
plot on a street in Grünau-Siedlung, which is where the advert says the plot is.

Two things followed, and both are built now (§ 8):

* **The Gemeinde plus an exact area is a working anchor for a city listing.**
  24 candidates is a scoreable set, exactly as the „anchor's size is not a
  reason to give up" note predicted for Leipzig at 502 m².
* **A Stadtteil is worth resolving to the Gemarkungen under it.** The directory
  cannot do it — it maps Gemarkung → Gemeinde, and „Grünau-Siedlung" is in
  neither column. The district outlines the search already fetches
  (`ave:KatasterBezirk`) can, against a box around any point in the quarter.
  One `fes:BBOX` request, no model, no guessing.

## 8. Built, and made portal-independent ✅

The two sections above are about one portal. What went in is not.

### 8.1 Reading by the word, not by the markup

A third portal was fetched to keep this honest — **ohne-makler.net**, which has
no adapter and never will (advert 476452, a 5 366 m² plot in Riesa, recorded as
`fixtures/inserat-ohne-makler.html`). Its shape is the awkward one on every
count:

| | ImmoScout | Kleinanzeigen | ohne-makler |
| --- | --- | --- | --- |
| area markup | `<dt>Grundstücksfläche ca.</dt><dd>742 m²</dd>` | `<li>Grundstücksfläche 1.025 m²</li>` | `<span>5.366 m²</span><span>Grundstücksfläche</span>` |
| order | label, value | one element | **value, label** |
| price meta tag | no | yes | no |
| coordinate | quarter's | municipality's | none |
| JSON-LD | the listing | the listing | **the portal company** |

So structure is the wrong thing to key on. `services/portal_fields.py` flattens
the document to one line with `|` where the tags were, finds the German label,
and takes the nearest value of the right *shape* within 60 characters on either
side. Measured distances: ImmoScout 5 characters, Kleinanzeigen 1,
ohne-makler 3 with the value first.

Against the three recordings, with no portal knowledge at all:

| Portal | area | price | location line |
| --- | --- | --- | --- |
| ImmoScout | 742 m² | 275 000 € | 04207 Leipzig, Sachsen |
| Kleinanzeigen | 1 025 m² | — (meta tag instead) | 04575 Neukieritzsch, Sachsen |
| ohne-makler | 5 366 m² | 115 000 € | Maschinenhausstraße, 01587 Riesa, Sachsen |

Four guards, each from a measurement rather than a worry: „370,62 €/m²" sits one
element from ImmoScout's price and is a rate; bare „Fläche" must not match
„Wohnfläche"; „Die großzügige Grundstücksfläche bietet ideale Voraussetzungen"
carries no value and must count for nothing; and the *first* postcode on an
ImmoScout page is in the analytics block, so the first one followed by a name
wins. And the ohne-makler JSON-LD is the reminder that a schema.org address may
only be read from a listing node — its `Organization` puts an address in
Reinbek, 400 km north of the plot.

This is the floor, not the ceiling. Where a portal names its own fields (§ 7.1)
that block still wins, because a structured field is a statement and this is a
reading.

### 8.2 The Stadtteil, resolved

`AlkisService.districts_around(lat, lon, radius_m)` — one BBOX request on
`ave:KatasterBezirk`, `art` filtered client-side because a WFS GET cannot carry
a BBOX and a filter at once. The seed is the platform's own pin, which the
`Anchor` docstring had ruled out entirely; it is still never *the* container,
but it may say which containers get asked.

That distinction is what makes it safe, and the safety is one-directional: a box
too small to hold the plot's district makes every anchor count zero and the run
reports that it found nothing. A bad pin can produce **no** parcel, never a
wrong one — which is why the radius can be chosen without a corpus of solved
listings, the same argument that lets the scoring weights ship uncalibrated.

`PIN_RADIUS_M = 1500`, measured against the pin sitting 6 235 m from the
Lobstädt parcel: ±1500 m returns 8 districts with Lobstädt among them, ±3000 m
returns 23, ±7000 m returns 69.

The whole chain, run against the live cadastre on the recorded ImmoScout page —
a listing that names no Gemarkung anywhere:

```
[raum]    Die Anzeige nennt keine Gemarkung. Um den Kartenpunkt der Anzeige
          liegen 7 Gemarkungen: Mark Flickert, Lausen, Schönau, Göhrenz,
          Großmiltitz, Großzschocher und 1 weitere. …
[raum]    2 892 Flurstücke hat die größte der 7 Gemarkungen
[treppe]  Stufe exakt (genau 742 m²): 3 Treffer
ERGEBNIS  status=mehrdeutig, 3 Kandidaten
            Lausen         8/a    742 m²  Staffelsteinstraße 4
            Kleinzschocher 861/4  742 m²  ohne Lage
            Kleinzschocher 861/5  742 m²  Miltenberger Straße 5
```

Three candidates on the map for the user to pick from, the right one first, and
the verdict `mehrdeutig` rather than `bestätigt` — correctly, because the anchor
came from a geocode and not from an official statement about this plot.

**That run is no longer reproducible on this recording, and the reason is a
guard in this same document.** § 7.2 measured that ImmoScout's `exposeMap`
coordinate for this advert sits next to `showFullAddress: false` — it is the
*quarter's* point — and the reader was made to refuse a coordinate the portal
does not call complete. So there is no pin to seed the box with, and the run
now reports „die Lage ließ sich nicht eingrenzen" (verified against the live
cadastre, 09.09.2026, before and after § 9's changes: identical).

That is the honest answer for this listing and it is not fixable from the name:
Grünau-Siedlung sits on Gemarkung Lausen, and nothing in
`gemarkungen-sachsen.json` says so — the directory maps Gemarkung → Gemeinde and
the quarter is in neither column. The pin path still earns its place wherever a
portal states a complete address. What § 9 adds is the channel that does not
need a coordinate at all.

## 9. The Ortsteil is in the location field ✅

A second ImmoScout exposé, pasted into the app by the user on 09.09.2026:
**advert 170438443**, „Preisreduziert! Baugrund in Rückmarsdorf sucht
Hausbauer", Burghausen-Rückmarsdorf, 04178 Leipzig, 866 m², 199 000 €. It came
back with **31 candidates**. Reproduced exactly, and it is two things.

### 9.1 The location field was read as one string

`collect_indicia` turned the whole field into a single opaque `ort` Indiz. The
municipality was pulled out of it by a pattern anchored at the end of the line
(`(?:^|[-–—])\s*NAME\s*$`), which fits „Sachsen – Grimma" and matches nothing
at all in „Burghausen-Rückmarsdorf, 04178 Leipzig, Sachsen". So neither level
was read, and with no district anchor the run widened to the Gemeinde:

```
[raum]     8 529 Flurstücke hat diese Gemarkung        (Gemarkung Leipzig)
[treppe]   Stufe exakt (genau 866 m²): 0 Treffer
[gemeinde] In der ganzen Gemeinde Stadt Leipzig: 31
ERGEBNIS   status=mehrdeutig, 31 Kandidaten
```

The five digits are the only fixed point in a German location line, and the
three recorded portals put everything else in three orders around them:

| Portal | field | in front | behind |
| --- | --- | --- | --- |
| ImmoScout | `Burghausen-Rückmarsdorf, 04178 Leipzig, Sachsen` | **Ortsteil** | Gemeinde, then state |
| Kleinanzeigen | `04668 Sachsen – Grimma` | — | state, then Gemeinde |
| ohne-makler | `Maschinenhausstraße, 01587 Riesa, Sachsen` | street | Gemeinde, then state |

So the field is read around its postcode now: behind it the Gemeinde, unless
that slot holds the Bundesland and then it is behind the dash; in front of it
the district, which is ImmoScout's own `obj_regio4`. A street stands there on
one portal in three, so the head only counts when the Gemarkungsverzeichnis
knows it — and the postcode-less shape the recorded adverts carry
(„Sachsen - Machern") keeps the old tail rule as a fallback.

### 9.2 „Burghausen-Rückmarsdorf" is two Gemarkungen

The compound is no Gemarkung. Burghausen 145507 and Rückmarsdorf 145614 both
are, both in Stadt Leipzig, and the advert does not say which half the plot is
in — so the answer is **two** candidates and the verdict is `mehrdeutig`:

```
[raum]    2 091 Flurstücke hat die größte der 2 Gemarkungen, die in Frage kommen
[treppe]  Stufe exakt (genau 866 m²): 2 Treffer
ERGEBNIS  status=mehrdeutig, 2 Kandidaten
            Burghausen    286/a   866 m²  Neuburghausener Weg   Punkte 1.00
            Rückmarsdorf  250/38  866 m²  ohne Lage             Punkte 0.68
```

And the ranking is the point of the exercise. Burghausen 286/a carries the
official Lagebezeichnung **„Neuburghausener Weg"**, which the advert's Lage text
names outright („Insgesamt ist der Neuburghausener Weg ein angenehmer Ort zum
Wohnen"), and `tntxt` „Sport-, Freizeit- und Erholungsfläche", which is the
„bisher als Wochenend- bzw. Gartengrundstück genutzt" of the description.
Rückmarsdorf 250/38 is „ohne Lage" and a Weg.

**Before this, the plain-text paste answered `bestätigt` for Rückmarsdorf
250/38** — the title's „Baugrund in Rückmarsdorf" was the only anchor, an exact
866 m² left one parcel standing in it, and the other half of the Ortsteil was
never asked. That is the one failure mode this search exists to refuse: a
confidently wrong parcel, official-looking, in the right city. Reading half a
compound name as the whole location is the same mistake as reading „Grünau" for
„Grünau-Siedlung", pointed the other way.

### 9.3 What keeps the split safe

A part of a compound is a *derived* reading, not a stated one, so it only stands
when its own Gemeinde is the one the listing names. That is what „Grünau-
Siedlung" needs: Gemarkung Grünau exists exactly twice, in Großolbersdorf and
in Langenweißbach, both 80 km from Leipzig, and without the guard the split
would anchor the search there.

Measured against **all 63 Leipzig Ortsteile** and the 5 339 names in
`gemarkungen-sachsen.json`:

| Ortsteil | split into | dropped |
| --- | --- | --- |
| Burghausen-Rückmarsdorf | Burghausen, Rückmarsdorf | — |
| Knautkleeberg-Knauthain | both | — |
| Plaußig-Portitz | both | — |
| Lausen-Grünau | **Lausen** | Grünau/Großolbersdorf, Grünau/Langenweißbach |
| Hartmannsdorf-Knautnaundorf | both | 5 Hartmannsdorf elsewhere |
| Grünau-Ost, -Mitte, -Nord, -Siedlung | **nothing** | all three Grünau |
| Zentrum-Ost, Alt-West, Mockau-Süd | nothing / Mockau | — |

Every compound resolves to its own Gemarkungen, every namesake elsewhere is
dropped, and the five „Grünau-…" names contribute nothing rather than anchoring
wrong. It costs no request: the directory is a committed 490 kB file.

One more rule came out of the same run. „in Leipzig – Stadtteil Burghausen-
Rückmarsdorf" names both levels in one sentence, and Gemarkung Leipzig holds
parcels of every size — so a Gemeinde's own name is demoted from an anchor to a
mention, but *only while another district is on the table*. „Sachsen - Bad
Lausick" names one place that is a Gemarkung and a Gemeinde at once, and
demoting it there leaves the run with no anchor at all — which is the advert
whose stated area has no match in Gemarkung Bad Lausick and exactly one in the
municipality.

### 9.4 And two halves are not a contradiction

With both Gemarkungen on the table the run put them up as a `Konflikt`:
„Welche Gemarkung ist gemeint? Die Angaben widersprechen sich." Nothing in the
listing contradicts — it names one Ortsteil, and that Ortsteil has two
Gemarkungen under it. The rule already existed one field over: „790/11 sowie
238/3" from *one* source is a plot made of two parcels, not two readings of
one, and only numbers from *different* sources are rival. `Indiz.teil_von`
carries the compound a district came out of, and `halves_of_one_ortsteil`
suppresses the question. The choice that was worth offering is the one in the
candidate table: „Wählen", per parcel.

### 9.5 And the paste was answering nothing at all

`/api/listings/extract` ran the deterministic reader only when the pasted text
contained a `<`. That was true of the parsers when the gate was written — they
read markup — and stopped being true when § 8.1 shipped: `portal_fields` goes
by the German word and the value's unit, so it reads a rendered page as well as
a marked-up one. Somebody who selected an exposé and pasted it therefore got
every field back empty, with „Grundstücksfläche ca. 866 m²" and „199.000 €"
standing in the text they had just handed over, and „Gelesene Werte" showing
nothing. The gate is gone; the same paste now reads 866 m², 199 000 € and
„04178 Leipzig".
