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

### 5.1 A bookmarklet that hands over the real DOM — recommended

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

What it costs: an endpoint that accepts a POST from a foreign origin (the
portal's page), so CORS for that one route plus a size cap — an ImmoScout exposé
is on the order of 1–2 MB, against the paste field's current 400 000-character
cap. A handover id rather than a URL fragment, because the payload does not fit
in a URL. And a short German page explaining how to install the bookmark, since
that is the one step a user cannot be walked through inside the app.

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

Do this if the bookmarklet is not wanted. It is smaller, it helps today, and it
will always be behind § 5.1 by exactly the fields that live in `<head>`.

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

Untestable here in any case: the sandbox browser has no route to the internet,
only the shell has.

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
