# where2build — working notes for Claude

Plot-appraisal tool for Saxony: resolve a listing to its official cadastral
parcels, measure them, compare the asking price against the official land value,
place a prefabricated house inside the setback envelope, and route to everyday
destinations.

## Language rules — these are strict

- **Source code is English.** Comments, docstrings, identifiers, commit
  messages, `README.md`, this file.
- **The user interface is German.** Every string a user reads: labels, buttons,
  headings, error messages, chart captions, `DESIGN.md`.

A German identifier in the code or an English label in the UI is a bug. This is
strict: variables, parameters, functions, methods, computed properties, props,
constants and comments are English, always, including local variables nobody
else will read.

Two things are **data**, not identifiers, and stay German:

- **The field names of the API and of the stored document** — `gemarkung`,
  `flaeche_amtlich_m2`, `bodenrichtwert`, `flurstuecksnummer`. They mirror the
  German authorities' own schemas and are the wire format. Read them with an
  English variable name: `const officialArea = props.flaeche_amtlich_m2;`.
- **CSS class names** — `lageplan`, `tafel`, `nicht-drucken`, `weg-karte`. An
  established vocabulary shared with the stylesheets; renaming buys nothing.

Keep comments sparse and about *why*, not *what*.

## Layout

```
backend/     FastAPI. Proxy and disk cache in front of ALKIS, BORIS, GeoSN
             WMS, RAPIS Sachsen (`/api/planning`), MOTIS and the LLM. No
             database — PostGIS is in the plan, not in the code.
             `app/search/` is the exception: it asks the cadastre a series of
             narrow questions and answers NDJSON, so the map can grow while it
             runs — and it *measures* what comes back. See below.
frontend/    Vite + Vue 3, Options API. Owns all geometry the user touches.
docs/        Spec, service research, screenshots. `strategie/` holds the four
             interactive strategy pages for parcel identification, and
             `claude/` the working notes this file points at.
mockup/      The approved UI mock. Historical reference, not built.
```

## Decisions that are settled — do not relitigate

These come from the pre-project note (`docs/vorprojekt-anforderungen.html`) and
from the user directly. Reopen only if the user asks.

- **Vue 3 with the Options API.** No `<script setup>`, no Composition API
  rewrite, no Nuxt.
- **Geometry the user touches runs in the browser**, not in Shapely. Buffering,
  rotation and collision run while the user drags, without a round trip. The
  binding numbers come from ALKIS anyway.
- **Geometry the *search* uses runs in the backend**, and has since the
  envelope was built. The two are not the same job: the browser draws what
  somebody is moving, and the search measures what the cadastre just answered —
  in order to rank a candidate list that is streamed as NDJSON and cannot wait
  for a browser. `search/envelope.py` unions outlines, `engine.py` fits a
  `minimum_rotated_rectangle` against the dimensions a listing states, and the
  soft features in `scoring.py` measure a front width and a neighbouring use.
  The rule that used to stand here („no geometry maths in `app/search/`") had
  already stopped being true when it was read again on 19.09.2026, which is the
  worst state a rule can be in.
- **Use the official area** (`flaeche` attribute from ALKIS) for anything
  price-related. The area computed from the polygon differs by a few square
  metres and is for shape analysis only. Both are shown side by side.
- **A plot is a *set* of parcels.** Not the exception — the normal case.
  Union the polygons, sum the official areas. The search follows the same rule:
  several parcel numbers from *one* source („790/11 sowie 238/3“) are that set
  and are never put to the user as a question, while numbers from *different*
  sources — an image against the body text — are rival readings and are.
- **No contact details are stored.** The extraction schema does not carry
  agent names or phone numbers, so no personal data reaches the database. A
  *Beleg* is free text out of an advert, though, so the divergence log scrubs
  telephone numbers and mail addresses out of every one it keeps.
- **The extraction provider is the deployment's choice.** OpenRouter, OpenAI,
  Anthropic, a local Ollama or any other OpenAI-compatible host: `LLM_ANBIETER`
  names it, `LLM_BASE_URL` overrides where it lives, and „auto" reads it off
  the endpoint. Anthropic speaks a different API and has an adapter of its own
  — never a translation layer. See `docs/claude/services.md`.
- **Fonts come from npm (Fontsource)**, never from a CDN.
- **No separate print view.** `print.css` restyles the live page.
- **There is no "6 m between buildings" rule in Saxony.** § 6 Abs. 5 SächsBO
  gives 0,4 H with a 3 m floor, Abs. 2 puts that area on one's own plot, Abs. 3
  forbids setback areas overlapping — so 6 m is the arithmetic of two minimal
  cases, not a norm, and a neighbour standing too close does **not** enlarge our
  setback. **The dashed § 6 envelope never moves.** What the „Nachbarschaft"
  tab draws is per building, decided with the user on 30.09.2026
  (`lib/neighbourhood.js`, mock-up `docs/strategie/ui-nachbarschaft.html`):
  each outline is classified (Bestand, Nebengebäude that counts for nothing
  under § 6 Abs. 8, Grenzbebauung under 0,5 m, Überdeckung under 3 m, ohne
  Befund) and assigned to the one boundary it faces; a neighbour's own 3 m
  onto us is a grey hatch; the part of our envelope within 6 m of it is the
  amber cross-hatched „6-m-Zone", worded as a question for the Bauaufsicht and
  never as an obligation, and a house reaching into it turns the house check
  amber, not red. A Grenzbebauung has two readings — „Abstand nötig" (the
  cautious default, which never shows more buildable land than there could be)
  and „An die Grenze darf gebaut werden" (our strip along that stretch is
  maybe buildable) — chosen per building and stored with the plot. OSM has the
  outlines but almost no wall heights (11 of 59 around Mölkau 204 carry
  `building:levels`, none carries `height`), and ALKIS none, so only the 3 m
  floor is computable and no drawing states a height.
  See `docs/research/abstandsflaechen-nachbargebaeude.md`.
- Region is Saxony only; ALKIS and BORIS are state-specific.
- **A contradiction is shown, never resolved quietly.** Two Gemarkungen in one
  listing, or a number on an image that the location field disagrees with, are
  a `Konflikt`: the search follows the most trustworthy reading, says which and
  why, carries the *Beleg* for each option, and lets the user pick another —
  which re-runs the search. A contradiction nobody can look up is one nobody
  can resolve.
- **The sentence under a check is composed, not written.** Every finding comes
  from a template in `frontend/src/lib/findings.js`: structured input from one
  service, fixed German text out. No model writes UI copy. That keeps the
  wording reviewable, keeps the same plot reading the same way twice, and makes
  it impossible for a missing input to turn into a sentence that sounds
  confident. The templates take the data's shape seriously — noise is a band so
  the text says a range, a designation is a yes or no so the text is a yes or a
  no.
- **The search field reads what was typed before it looks anything up**
  (`frontend/src/lib/queryInput.js`). Three signals settle almost everything: a
  German address never begins with a digit, so a leading digit rules the address
  index out; a coordinate is two numbers that land inside Germany; a parcel
  denominator (`85/1`) cannot occur in an address. Where two readings stay
  plausible — "Lessingweg 44" and "Mölkau 204" are the same shape — the answer
  says so and both local indexes are asked, rather than one being guessed.
  How it was read is shown in the field itself, at its right edge, for every
  kind of input — a marker whose menu overrules the reading; there is no chip
  row. Long input becomes a pill, and only on an unmistakable signal (a paste,
  a chosen suggestion, Enter, a space after a leading number). The suggestion
  list and the menu open over the page, never in its flow: nothing may move
  while someone types (the user, 26.09.2026). See `docs/claude/frontend.md`.
- **The search decides with hard filters and orders with weights.**
  „Bestätigt“ means an *official* statement left exactly one parcel standing —
  a parcel number resolved against ALKIS, the Gemarkung, `ave:flaeche` when the
  listing's figure is exact — and nothing contradicted it. A single survivor
  reached only through a chosen tolerance is `mehrdeutig`. Everything
  inferential (a rounded area, a street, land use, a broker's distance) may
  only order the list, which is why the weights can ship uncalibrated: they
  can produce an unhelpful ordering, never a wrong answer. One exception,
  asked for by the user on 24.09.2026: a parcel an *area* search finds whose
  dominant `tntxt` use is traffic (Straßenverkehr, Weg, Platz, Bahn-, Flug-,
  Schiffsverkehr) is taken out, in a line of its own that names it. A parcel
  the listing names by number is never taken out — a driveway recorded as Weg
  is often part of the set. See `backend/app/search/`.
- **The administration area is configuration first, database second.**
  `ADMIN_ACCOUNTS` names account keys and is the bootstrap; everybody else is
  promoted in the interface, where the flag lives on `users`. Configuration
  rather than „the first one to sign up", because an instance on the open
  internet would hand the area to whoever got there first — and configuration
  is what survives the empty `users` table the red button leaves behind. What
  the area counts are **aggregates**: one row per hour, area and outcome with
  nobody in them, and one per hour and account for the question „who". Never a
  row per request — that would record when each single call happened, which
  nobody needs and everybody would then have to protect.
- **A price is a file, not a constant, and a missing price is a dash.**
  `ops/llm-preise.json` carries the model prices and the ECB rate with their
  dates, written by `backend/scripts/update_llm_prices.py` from the provider's
  own endpoint and committed, so a change is a diff. A model the file does not
  list costs „—" and never 0,00 €.
- **The administration area asks for a job, it does not run one.** The
  scheduler owns the schedule, the lock and the writable data mount; „Jetzt
  starten" writes a request into the state directory they share. Without a
  scheduler the page says so rather than offering a button with no effect.
- **Never show example data.** There is no sample state and no fallback: when a
  service fails, the German `detail` from the backend is shown instead. Tests
  run on recorded real responses in `frontend/tests/fixtures/`, not on invented
  numbers. A derived figure with a missing input stays `—`; it is never
  computed from `null` (that is where "0,00 €" and "−100 %" came from).

## Working rules

- **Keep the pull request description current.** After every push, the PR body
  must describe what is actually on the branch. A description that still talks
  about the previous step is worse than none.
- **Verify, do not relay.** Statements about an external service belong in the
  repo only after a request has been made and its answer read. `HEAD` is not a
  substitute for `GET` — several of these services answer 404 to a HEAD they
  serve happily on GET.

## Traps that already cost time — read the one you need

Everything below was measured, and most of it failed *silently* the first time:
a blank map with nothing in the console, a test that passed for the wrong
reason, a preview nobody could see. The notes are split by subject so a task
can read the one file it needs instead of all of them.

**Read the file that matches what you are about to touch**, before you touch
it. If a change spans two, read two. They are short.

| File | Read it when |
|---|---|
| [`docs/claude/services.md`](docs/claude/services.md) | Talking to ALKIS, BORIS, the GeoSN map layers, the LUIS environmental server, the UBA, MOTIS/Transitous, Overpass, a listing portal or the model — how each one actually answers, and where it answers wrongly-but-successfully |
| [`docs/claude/parcel-search.md`](docs/claude/parcel-search.md) | Anything in `backend/app/search/`: which questions the cadastre is asked, how German prose is read for a place, what OCR of a listing's images can and cannot deliver, and what may decide versus only rank |
| [`docs/claude/maps-and-drawing.md`](docs/claude/maps-and-drawing.md) | `SitePlan`, MapLibre, the camera, tiles as a ground, the setback envelope and the rest of the browser-side geometry |
| [`docs/claude/frontend.md`](docs/claude/frontend.md) | Vue components, scoped styles, print, forms, the narrow layout, number and date formats |
| [`docs/claude/accounts-and-sharing.md`](docs/claude/accounts-and-sharing.md) | Sign-in, the Postgres store, the request budget, sharing a plot by link and the preview card |
| [`docs/claude/tooling-and-tests.md`](docs/claude/tooling-and-tests.md) | Running the suites, the screenshot run, a browser walk, Docker and Postgres in this sandbox — and the ways a test has lied here |

A finding belongs in one of those files, not here: this file is the part that
is true of the whole project. Add to the file the work touched, in the same
shape as its neighbours — what was measured, what it cost, and what to do
instead.

## Commands

```bash
# backend
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e "backend[dev]"
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend

# the administration area: /verwaltung for whoever is named here. The value is
# an *account key* -- the 32 characters /api/auth/me reports and the account
# page shows -- never a mail address.
export ADMIN_ACCOUNTS=88bcdb2925220580d02b1c458283db8e

# the whole thing in containers: nginx with the build, the backend, Postgres
# and authentik. The app is one origin, so no CORS; authentik is on 9000 of
# its own because it serves from the root of an origin, /api/ included.
# No demo account -- „Anmelden" leads to a page whose „Konto anlegen" works,
# in a window of its own so this page keeps whatever is half-entered on it.
# authentik needs about a minute on the first start.
# --remove-orphans every time: a renamed service leaves its container behind.
# Behind a TLS-reterminating proxy (the cloud sandbox, a corporate network),
# run this once first: it copies that CA into the two build contexts, which is
# what the proxy's own documentation says to do. It does nothing where there is
# no such CA, so it is safe to run always.
scripts/setup-build-ca.sh
docker compose up --build --remove-orphans     # http://localhost:8080
docker compose down --remove-orphans           # volumes stay; -v throws them away

# the stack routes on its own MOTIS: the first start downloads ~640 MB and
# imports for ~7 min at 5.6 GiB peak, after that it is seconds. Where that
# memory is not there, route against Transitous instead:
docker compose -f docker-compose.yml -f docker-compose.transitous.yml up --build

# reading a listing's attached cadastral extract -- optional, and the search
# says so in /api/health when it is missing
apt-get install -y tesseract-ocr tesseract-ocr-deu
backend/.venv/bin/pip install -e "backend[ocr]"

# frontend — needs Node >= 22.19: jsdom 30 pulls in undici 8, and on Node 20
# vitest dies before loading a test with `markAsUncloneable is not a function`.
cd frontend && npm install
npm run dev            # proxies /api to 127.0.0.1:8000
npm run test           # vitest
npm run build

# screenshots of every view, light and dark
node scripts/screenshots.mjs

# the bookmarklet's handover, across two real origins (needs the build and :8000)
node scripts/bookmarklet.mjs
```

## Before calling a change done

1. `npm run test` and `pytest` both green — state the counts.
2. `node scripts/screenshots.mjs`, then **look at the images**. Tests do not
   catch a collapsed layout or an unreadable colour.
3. **Put the pictures of what changed in the chat**, not only the counts. A
   test count says a thing did not throw; it says nothing about whether the
   screen reads. Whoever asked for the change is the one who can see that, and
   they cannot if the images stay in `docs/screenshots/`. Send the views the
   change actually touched — a handful, not all thirty-seven.
4. Check both themes and a 390 px viewport. No horizontal overflow anywhere.
5. Print preview still sane if you touched layout.

Chromium is preinstalled at `/opt/pw-browsers`; never run `playwright install`.

## Test and screenshot counts at last check

- `pytest`: 814 passed, 72 skipped where Tesseract is missing, as measured on
  30.09.2026 (826 and 60 with it). With `TEST_DATABASE_URL` pointed at a
  real Postgres the account store and the administration area run too; they are
  skipped rather than mocked because what they check is the database's own
  behaviour. Of the rest, one needs pyosmium, which only the index builder
  wants, and twelve need Tesseract — this sandbox has it, and for that reason
  never run two suites at once here. Three Tesseract tests failed on a run
  sharing the machine with another pytest, and they failed exactly as a
  photograph of a lawn does: an empty reading, past the 30 s timeout.
- `vitest`: 870 passed (30.09.2026) — plus the integration file, excluded by `npm run test`
  and 8 passed / 2 skipped when a backend is up on :8000
- `scripts/bookmarklet.mjs`: the handover across two origins, against the built
  app and a backend on :8000. It asserts the coordinate, which is the field
  that separates a handed-over document from a pasted one, and it writes
  `assistent-uebergabe.png`.
- `scripts/screenshots.mjs`: 108 images plus one print PDF — 87 and the PDF
  without a session, as measured on 30.09.2026. Eleven of them are the
  „Nachbarschaft" tab (`grundstueck-nachbarschaft-*`), taken on Mölkau 204 in
  a context of its own, typed as „145592 204", with the ELK All in One 159
  placed in the amber state by computation (the run prints house, ratio and
  angle). The location record prints as
  part of the plot sheet now, so there is no second PDF. Twenty-one of them
  need a session (`konto-*` and the administration area) and they are taken only
  with `W2B_ADMIN_COOKIE` set — see `docs/claude/tooling-and-tests.md` for how
  that cookie is made and why the run says so rather than photographing the
  refusal page. The narrow pass
  runs in the **light** theme like the wide one, so the phone-width pictures
  are named `*-hell-schmal.png`. It fails on console errors, on horizontal
  overflow, and if not a single vector tile arrived. It
  also drives the live geocoder, which is slow often enough to blow the 60 s
  wait on the destinations step — two runs failed there and the third passed
  with nothing changed. Re-run once before going looking for the bug.
  The `suche-*` images run a **real** search against ALKIS, so they need a
  backend on :8000 like every other picture here; without one the step reports
  "die Suche kam zu keinem Ergebnis" rather than passing quietly. The
  `assistent-werte-*` images paste a saved advert
  (`backend/tests/fixtures/inserat-kleinanzeigen.html`) through
  `/api/listings/extract`, which needs the same backend and no LLM key, and
  then open the „Gelesene Werte" fold inside the search step — that list is no
  longer a step of its own. The `assistent-einfuegen-*` images are the same
  step with the bookmarklet's fold open. The `grundstueck-bebauung-*` images are taken after a pointer click on the
  footprint, which is what opens the „Bebauung" tab — the run reports it if the
  click did not. The `grundstueck-preis-*` images show the
  price field open and empty: the run's plot is a typed parcel number with no
  listing, and typing a price in would put an invented figure into the docs. The `suche-band-*` images run the
  reference advert a second time with its area rounded to „ca. 1.100 m²", which
  is what keeps the run ambiguous — an exact area settles it in five requests
  and no distance band is ever resolved.
