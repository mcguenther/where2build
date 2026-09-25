# Accounts, server storage, and sharing a plot

Optional and off until configured: without `OIDC_ISSUER` there is no sign-in
and without `DATABASE_URL` no server storage, and both are complete
deployments. On top of them sits sharing a plot by link -- a snapshot with an
end date, switched on field by field, with a preview card drawn on the
server.

---

- **The plot ceiling is serialised by the account upsert, not by a lock
  anybody wrote.** `save_plot` calls `_account_id(create=True)` first, and its
  `on conflict do update` takes a row lock on `users` that is incompatible
  with itself, so two writes for one account queue there and the second counts
  what the first stored. Measured 09.09.2026: a second upsert on a held row
  runs into `lock_timeout`, while two plain inserts into `plots` do not wait on
  each other at all, because a foreign key only takes `for key share` and that
  is compatible with itself. Turning the upsert into "select, and insert if
  missing" is the obvious tidy-up once the row usually exists, and it would
  quietly turn the ceiling into a suggestion.
  Two attempts to *prove* the race first measured something else entirely: an
  `asyncio.gather` of two `save_plot` calls proves nothing, because both take
  the same pooled connection, and a write blocked behind an outside `for
  update` on the account row proves only that the foreign key touches that
  row. `test_der_upsert_auf_das_konto_serialisiert` measures the two
  statements themselves and fails when the upsert stops writing.

- **A request budget read off `X-Forwarded-For` fails silently in both
  directions.** Read from the *left*, the header is whatever the caller typed,
  so a fresh value per request is a fresh budget and the ceiling is decoration.
  Left unconfigured behind a proxy, every signed-out caller counts against the
  proxy's own container address, so they all share one budget and the first
  busy tab locks out everybody else. Neither shows up as an error. So the
  header is read only when `APP_PROXY_HOPS` says how many proxies of ours stand
  in front, and then from the right — nginx appends the peer it saw
  (`$proxy_add_x_forwarded_for`), so the last entry is the one it vouched for.
  `docker-compose.yml` sets `APP_PROXY_HOPS=1` itself, because it is the file
  that puts the nginx there.

- **The private half of a plot is not only the note.** A share cuts `note`,
  which is obvious, and `routes`, which is easy to miss: it is keyed by
  destination id and holds the travel times to them, and the destinations are
  somebody's work address, their children's school, their parents' home. A
  reader who cannot see the names can still count the destinations and read off
  the distances. Both are cut in `Storage.for_sharing`, on the way *in*: a
  promise the frontend keeps is one a bug in the frontend can break, and cut at
  the door the row simply never holds it.

- **The pool's jsonb codec already encodes, so a second `json.dumps` stores a
  JSON string.** It reads back as a `str` where every other document is a
  `dict`, and pydantic is what finally said so. Worse, the test that was meant
  to prove the note was gone passed anyway: `"note" not in some_string` is a
  substring test, and it was true for the wrong reason. Assert the row is a
  dict before asserting anything about its keys.

- **A snapshot cannot look anything up.** A shared plot is one document, and
  the house type lives in the settings document — so a share made of the plot
  alone shows no building at all. The footprint and the type's name are
  resolved into the snapshot when the link is made. Anything else a plot page
  reads from elsewhere has to travel the same way or be left out on purpose.

- **`("note")` is the string, not a one-element tuple, and a privacy switch
  built on it withholds nothing.** `SHARE_OPTIONS` maps a switch to the fields
  it governs, and the set of withheld names is built by iterating those tuples —
  so a missing trailing comma iterates the *letters* and the withheld set holds
  `n`, `o`, `t`, `e` while nothing named `note` is ever cut. Every shared link
  would have carried the personal note. Nothing about the code reads wrong; it
  was caught by running the function, and it is pinned now by a table-driven
  test that walks each switch against exactly its own fields.

- **What is not shared must not go on the wire either.** Sending the whole plot
  and trusting the backend to cut it works — and puts somebody's destinations
  and their note through a request made for a link that does not carry them.
  `SharePanel.snapshot()` therefore only resolves the house type and the
  destination names when their switch is on, and the backend cuts again on the
  way in. Two places, on purpose: the browser decides, the server enforces.

- **The share panel's most-seen state is the signed-out one.** Sharing needs a
  server to hold the copy, so it needs an account — and a disabled button with
  no reason reads as broken, while hiding it means nobody learns the feature
  exists. Three states, all in words: the invitation with a sign-in link, and
  where no provider is configured at all a sentence saying so and pointing at
  the print sheet and the JSON export. `teilen-*.png` in the screenshot run is
  the signed-out one, because the run has no identity provider.

- **A preview bot runs no JavaScript, so the built app hands it the same title
  for every plot ever shared.** A chat client, a messenger or a search engine
  reads the `og:` tags out of the HTML it is given and stops; the app is a Vue
  route, so what it gets is the build's own `<title>where2build</title>`.
  The answer is **one server-side include**, not a guess at who is asking:
  `frontend/index.html` carries `<!--#include virtual="/api/shares/$token/
  vorschau-kopf" -->`, and `nginx.conf` switches SSI on for `/geteilt/…` only,
  capturing the token in the location itself. Every caller — bot or browser —
  then gets the plot's own tags, and every other page ships the line as an
  inert HTML comment and costs no request (measured: 0 backend calls for
  `/`, `/grundstuecke`, `/haustypen`).
  The first version sniffed the user agent against a list of known crawlers and
  routed those to a page the backend rendered. It worked, and it was wrong in a
  way that could not be noticed from inside: a messenger nobody had put on the
  list got no preview, and there was nothing to see anywhere. The list is gone,
  and so is the backend's HTML page — one mechanism, no dead route.
- **`try_files` re-enters location matching, which switches SSI back off.**
  `location ~ ^/geteilt/… { ssi on; try_files $uri /index.html; }` looks right
  and does nothing: the internal redirect lands in `location /`, where SSI is
  off, so the include ships to the client as a literal comment. That reads
  exactly like a feature that was never wired up. `rewrite ^ /index.html break;`
  stays in the location. Verified against nginx 1.24 with the shipped config and
  against the `nginx:1.27-alpine` image the frontend actually ships.
- **The fragment is a fragment.** It lands inside a head that already has a
  charset, a viewport and a title, so it carries no `<html>`, no `<head>` and
  **no second `<title>`** — a browser takes the first title it sees, so a
  duplicate would not throw anywhere while every shared plot showed the wrong
  name in the tab. An unknown or withdrawn token answers **200 with an empty
  body**: nginx substitutes nothing for a failed include either way, so the page
  is identical, and 200 keeps a link that is simply old out of the error log.
  The reader then gets the app's own „Dieser Link führt nirgendwohin".
- **Starlette adds no HEAD for a GET route, and a link expander asks HEAD
  first.** Slack's does, to see the type and the size before fetching the
  picture; the 405 that answered made the preview be skipped, and nothing in a
  browser shows that. `/api/shares/{token}/vorschau.jpg` answers HEAD, as a
  **route of its own** rather than a second method on the same decorator:
  `methods=["GET", "HEAD"]` gives both operations the same `operationId` and the
  OpenAPI document then quietly drops one. A test asserts the ids stay unique.
- **nginx's `$host` drops the port, `$http_host` keeps it.** One route writes
  absolute URLs back out — the `og:url` and `og:image` of a shared plot — and
  with `proxy_set_header Host $host` both named port 80 on the compose default
  (`localhost:8080`): a preview pointing at a server nobody is running.
  Measured against a real nginx before and after, and again in the containers.
- **A card with a photograph on it must not be a PNG.** The same 1200 × 630
  card is 574 kB as PNG and ~100 kB as JPEG at quality 86, and several clients
  — WhatsApp among them — show no preview at all above a few hundred kilobytes,
  with nothing anywhere to say why. And the switch is the **third** time in this
  repo a cache key failed to name what produced the answer: the stored PNG kept
  being served under `Content-Type: image/jpeg`, which every client renders, so
  the picture looked right and stayed five times too big. `CARD_VERSION` is in
  the key and covers the format, not just the drawing.

- **Fontsource ships `.woff` next to `.woff2`, and FreeType reads the first
  without brotli.** A server-drawn card needs a file Pillow can open, so the
  three faces the browser loads are vendored into `backend/app/assets/fonts/`
  as woff (about 18 kB each) and travel as package data. The card is then the
  app's own typeface rather than DejaVu.

- **A zoom step is a factor of two, so fitting to one frames a plot anywhere
  between a third and the whole card.** The preview frame is rendered
  *oversized* at the zoom that fits and scaled back — the same move `tiles.py`
  makes to get under a WMS scale limit — so every plot sits at 78 % of the card
  whatever its size. The drawing goes on *after* the scaling back, or the
  outline's stroke and its halo shrink with the ground.

- **The card's ground is the orthophoto, and it is best effort.** At the size a
  chat shows it, the photograph is what makes a plot look like a place; the
  outline carries the site plan's halo for exactly that reason. A slow or broken
  WMS leaves paper behind the drawing rather than an error, because the one part
  of the card that can fail must not cost the outline.

- **A link nobody can see is a link nobody can take back.** Sharing shipped
  without any way to list or withdraw what had been handed out, and a link is
  public for ninety days — so a slip could only be waited out. `SharedLinks`
  sits at the foot of the plot's own page (that is where somebody who has just
  shared something looks, not in the account) and is **absent** while there is
  nothing: a panel that is always there and usually empty is furniture.

- **Present is not filled, and the list said so wrongly.** What a link carries
  is derived from the stored row rather than remembered from the switches —
  keeping the switches would let the two drift apart. But `field in dokument`
  is the wrong test: a plot with no price still has an `askingPrice` key, so
  switching the price on writes `null` into the row and the row then announced
  a „Kaufpreis" nobody could read off the link. `share_scope` requires a value
  that is not `None` and not an empty container. Found in a browser walk, not
  in a test.

- **An issuer is one string doing two jobs, and inside a compose network the
  two addresses differ.** The provider is `http://localhost:9000` for the
  browser and `http://authentik:9000` for the backend, and OIDC has no field
  for that: everything comes back naming the public address, which the backend
  cannot resolve. It fails as a connection error during the callback, i.e. as
  „Anmeldung fehlgeschlagen" with nothing in the browser to say why.
  `OIDC_INTERNAL_BASE_URL` reroutes **only the calls this backend makes
  itself** (`OidcService._reachable`); the authorization URL the browser is
  sent to and the `iss` that is checked against the token stay public, because
  rewriting either would send the user to a hostname their machine does not
  have, or make the check pass for a token issued by somebody else. Keycloak
  calls the same setting a „frontend URL", from the other end.

- **The rerouted request has to keep saying which host it is for.** The first
  version only swapped the address, and the browser was then redirected to
  `http://authentik:9000/application/o/authorize/` — a name only the compose
  network knows, so the page did not load at all. A provider builds every
  absolute URL it hands out, the discovery document's endpoints and an ID
  token's `iss` among them, **from the host header it was asked as**. So the
  connection goes inside while the request still carries the public `Host`,
  which is what any reverse proxy in front of such a provider does. Nothing
  about this is visible in a unit test with a fixed discovery document — it
  took a real authentik and a browser.

- **The endpoints are not under the issuer, so the swap is by origin.**
  authentik's issuer is `/application/o/where2build/` and its token endpoint
  is `/application/o/token/`, one path up. Matching the issuer as a prefix
  therefore rewrote the discovery URL and left the token endpoint alone —
  which is the one call the sign-in cannot do without.

- **`userinfo_endpoint` is optional**, and the rewrite called `.startswith` on
  whatever the document held. A provider that omits it (authentik does not,
  several do) would have died inside discovery with an attribute error, with
  the internal address set and nothing else wrong.

- **The discovery document is cached on disk, and the cache key cannot know
  the code changed.** After the Host header was added, the backend kept
  redirecting to the internal address: the key names the issuer and the
  internal base URL, both unchanged, so the stale document — the one fetched
  before, with the wrong endpoints in it — kept being served. It reads as
  „the fix did nothing". Clear `/cache` after changing how a provider is
  reached.

- **A blueprint writes the whole object, so a field left out is a field
  cleared.** Switching registration on means one field on an existing stage
  (`default-authentication-identification.enrollment_flow`), and a blueprint
  entry with just that field made authentik refuse the whole file: „When no
  user fields are selected, at least one source must be selected" — because
  `user_fields` was now empty. Every field that must survive has to be
  repeated in the entry.

- **authentik masks the error it is reporting.** The message that came out was
  `KeyOf: failed to find entry with id of 'enrollment'`, which points at a
  reference that is perfectly fine: the real error was raised while
  *serialising* the failed entry for the log, because `repr()` of an
  unresolved `!KeyOf` tag re-raises. The way to the actual message is to run
  `ak shell` with `authentik.events.utils.sanitize_item` wrapped in a
  try/except and call `Importer.validate()` by hand.

- **The provider's own pages are only half translatable.** The brand carries
  `attributes.settings.locale: de`, and that does translate the buttons — but
  authentik 2025.2's German flow bundle holds about 35 strings, so „Email or
  Username" and „Need an account? Sign up." stay English however the brand is
  configured. What *is* ours: the flow titles, every label in the enrollment
  form, the brand title and the logo (`branding_logo`, pointed at the app's
  own `favicon.svg`, mounted into authentik's media directory).

- **A successful registration ended on a refusal.** Somebody who signs in at
  authentik itself rather than by clicking „Anmelden" has to end up
  *somewhere*, and authentik's own answer is its user interface — which
  refuses exactly the accounts this stack creates. They are `external` (people
  who use where2build, not authentik), and an external user gets „Die
  Oberfläche kann nur von internen Nutzern geöffnet werden", immediately after
  the account was created successfully. authentik has the remedy built in and
  the field even says so: `Brand.default_application` — „external users will
  be redirected to this application after authenticating". It is pointed at
  the application's `meta_launch_url`, and that is **`/api/auth/login`**, not
  the start page: arriving at the start page would leave somebody signed in at
  authentik and signed out of where2build, i.e. looking at „Anmelden" in the
  corner seconds after registering. The sign-in endpoint bounces through the
  provider once more, silently, because the session is already there.

- **Signing in ran in the page and cost everything the page held.** The
  exchange is five redirects across three origins, so the app unloaded and
  came back: a pasted advert, a dragged building and a half-filled search were
  reloaded from storage on the way back, or gone where they were never stored
  — at exactly the moment somebody wanted an account *so that* their work
  would be kept. It runs in a window of its own now (`lib/signIn.js`), which
  lands on `/anmeldung-fertig`, posts to its opener and closes; the page never
  unloads. Three things that make it hold up: `window.open` has to be reached
  synchronously from the click or every browser refuses it; a refused window
  falls back to the old full navigation, because a button that does nothing is
  worse than a page change; and whether it worked is asked of `/api/auth/me`
  afterwards rather than read off the message, because a window closed by hand
  posts nothing and a window that posts and then closes is a race. A sign-in
  that breaks off still lands on the start page with „Die Anmeldung kam nicht
  zustande" — in the small window, which is where it happened.


## `create table if not exists` ist keine Migration

Gemessen 19.09.2026 in einem laufenden Stapel. Die Anmeldung klappte, und der
erste Speicherversuch antwortete 500:

```
null value in column "kennung" of relation "users" violates not-null constraint
```

`kennung` kommt in `schema.sql` nicht vor — auch in keiner Fassung der
Historie. Die Tabelle stammte aus einer anderen Version, und das ist kein
Zufall: `schema.sql` wird bei jedem Start mit `create table if not exists`
angewandt, und das **ändert eine vorhandene Tabelle nie**. Das Volume
`db-data` überlebt `docker compose down`, also bleibt ein einmal angelegtes
Schema für immer bestehen. Der Kommentar über `SCHEMA_PATH` hatte das
vorhergesagt („what has to replace it before the first change to a column"),
und die Grenze ist jetzt überschritten.

Bis es Migrationen gibt, sagt der Start es wenigstens laut. `_check_columns`
liest nach dem Anwenden des Schemas aus `information_schema`, welche Spalten
die Datenbank **verlangt** (`not null`, kein Default), und vergleicht sie mit
denen, die `schema.sql` deklariert. Eine Spalte, die die Datenbank fordert und
das Schema nicht kennt, bricht jeden `insert` — also bricht sie jetzt den
Start, mit dem Namen der Spalte und dem Weg heraus.

Was zu tun ist, wenn es auftritt: entweder die Spalte von Hand entfernen
(`alter table users drop column kennung`) oder, wenn nichts darin gespeichert
ist, `docker compose down -v` — das wirft die Volumes weg, **mitsamt aller
gespeicherten Grundstücke**.

## Ein Cache darf keinen Request töten

Im selben Stapel antwortete jeder `/api/listings/extract` mit 500:

```
PermissionError: [Errno 13] Permission denied: '.cache'
```

Der Prozess läuft unprivilegiert, `APP_CACHE_DIR=/cache` zeigt auf das
gemountete Volume — und der Pfad im Fehler ist der relative Standardwert,
also griff die Einstellung in dem laufenden Image nicht (ein Start ohne
`--build` reicht dafür). Das ist die eine Hälfte.

**Korrektur vom 25.09.2026:** Es war nicht das alte Image. `backend/.env` ist
eine Kopie von `.env.example`, und die setzt `APP_CACHE_DIR=.cache`. Compose
liest die Datei per `env_file`, und das schlägt das `ENV` aus dem Dockerfile —
mit jedem Image, auch frisch gebaut. Gemessen beim Nutzer: `/cache` 4 KB groß
und leer, das Log mit genau diesem `Permission denied: '.cache'`, und dieselbe
Kachel zweimal hintereinander zweimal `MISS`. Der Cache hat im Stapel also nie
etwas gehalten. `docker-compose.yml` setzt `APP_CACHE_DIR=/cache` jetzt unter
`environment`, das Vorrang vor `env_file` hat, für Backend und Scheduler;
`docker compose config` mit einer kopierten Vorlage zeigt vorher `.cache`,
nachher `/cache`. Allgemein: was das Dockerfile per `ENV` setzt und in
`.env.example` steht, gewinnt im Stapel die Vorlage.

Die andere ist schlimmer und unabhängig davon: `DiskCache.get_bytes` hat einen
`OSError` immer geschluckt, `set_bytes` hat ihn durchgelassen. Das ist die
falsche Richtung — ein Cache, der nicht lesen kann, ist langsam, und einer,
der nicht schreiben kann, ist genauso langsam. Stattdessen starb der Request
**nachdem** das Modell geantwortet hatte: die Arbeit war getan und bezahlt und
wurde weggeworfen, weil das Ablegen scheiterte. `set_bytes` protokolliert
jetzt einmal je Verzeichnis und gibt auf.
---

## The administration area

- **A counter that only counts hours cannot stop anything.** The request budget
  in `app/ratelimit.py` is a sliding hour, and the statistics are hourly rows;
  both are the right shape for reading and useless for defending. An account
  that starts scanning is visible at the end of the hour, by which time the
  hour has happened. So `app/telemetry.py` keeps a *second*, short window per
  account — 300 calls in 5 minutes by default — and an account that crosses it
  is blocked in the process that saw it, before the answer is sent. The
  database is the durable and shared copy: the flush writes local blocks out
  and reads every block back, so a second worker follows within one flush
  interval rather than instantly. That is the accepted seam, and it is in the
  harmless direction: a worker is late to block, never late to unblock.

- **Lifting a block does nothing while the window that caused it is still
  full.** Measured here: a screenshot run spent 347 calls in an hour, the guard
  fired, the block was lifted through the API — and the very next request
  crossed the same line again and was blocked, with nothing on screen saying
  why. `Recorder.clear_block` drops the account's short window as well now.
  Lifting a block means the counting starts over; anything else is a button
  that appears not to work.

- **Map tiles must not be in the burst window.** One screen of a map is dozens
  of them and a pan is dozens more — a window sized for calls to the cadastre
  fires on somebody looking at a map. They are counted for the account (they do
  go outward) and kept out of the window; what bounds them is their own, far
  wider ceiling in `app/ratelimit.py`. The distinction is one flag at the
  counting site in `main.py`, and getting it wrong would block ordinary use
  while looking like a working defence.

- **A blocked administrator must still reach the area that lifts blocks.**
  `current_account` refuses a blocked account, and `/api/verwaltung/…` takes
  `signed_in` instead — deliberately, and the only route in the application
  that does. The first version had `current_admin` depend on `current_account`
  and the guard could lock the operator out of its own off switch. The pictures
  in `docs/screenshots/verwaltung-konten-*.png` were taken in exactly that
  state: the administration area open, the plot list refused with 403.

- **`users` is keyed by issuer and subject, and nothing else in the app speaks
  that.** Session cookie, API and request budget all carry the *account key* —
  `sha256(issuer + "\n" + subject)`, first 32 hex characters — so no statement
  could be joined to a row. The migration adds `kennung` and backfills it in
  SQL; Postgres would not take it as a generated column, because `convert_to`
  is stable rather than immutable, so `not null` is the guard instead: an
  insert that forgets the column fails rather than leaving a row nobody can
  find.

- **A block cannot hang off `users`.** That row appears on first *write*, and
  an account worth blocking is exactly one that is spending the upstream budget
  without necessarily having stored anything. `sperren` is therefore keyed by
  the account key and references nothing. The same fact shapes the account
  list: it is a **full outer join** of `users` against `nutzung_konto`, because
  neither set contains the other, and the row an operator is looking for is
  usually the one that stored nothing.

- **Promotion needs a row, blocking does not.** So promoting an account that
  has never stored anything answers 404 with a sentence saying why, rather than
  reporting success and writing nothing. And demoting the last administrator is
  refused unless `ADMIN_ACCOUNTS` names one — otherwise the area becomes
  reachable by nobody, from inside the area itself.

- **The red button that empties the audit trail is not an audit trail.** The
  wipe takes a scope („konten", „statistik", „sperren") and `pruefprotokoll` is
  in none of them. The entry is also written *before* the `truncate`, so a wipe
  that fails half-way still leaves the record that somebody pressed it.

- **Two confirmations that only the browser knows about are one confirmation.**
  `/datenbank/vorbereiten` hands out a single-use key with a two-minute life
  tied to the administrator who asked, and `/datenbank/leeren` needs that key
  *and* the sentence typed back, both checked on the server. Worth knowing
  behind several workers: the second request has to reach the worker that
  handed out the key, and otherwise gets a fresh dialog — a wipe that has to be
  started twice is the harmless direction.

- **503 is not an error, and an error log full of it is one nobody reads.** In
  this API 503 means „this deployment has no server storage", which is a
  complete state. The first version logged every failure from 400 up and the
  list filled with the deployment's own configuration; it records from 500 up
  now, minus that one. The counterpart: the error list falls back to this
  process's own ring when there is no database at all, because a page that goes
  blank exactly when something is wrong is worse than one that says where its
  numbers come from.

- **A flush that fails must not cost the minute.** `Recorder.put_back` returns
  the snapshot the database refused, and it is not theoretical: the 502 rows in
  `docs/screenshots/verwaltung-fehler-hell.png` were recorded while Postgres
  was stopped and written when it came back.

- **The chart needs the buckets the server has no rows for.** The API answers
  only hours that were counted; drawn straight, a quiet night closes up and
  yesterday's bar stands next to this morning's, showing a busy stretch that
  never happened. `lib/period.js:fillSeries` pads the period out, and an hour
  with no row is a bar of height zero — which for a counter is what "no
  request" looks like. A period with nothing in it at all still says so in
  words rather than drawing a flat line.

- **A price is not a measurement, and the two must not share a code path.**
  Tokens are counted here; what they cost is a claim about somebody else's
  price list. So the prices are a committed file with a date on it
  (`ops/llm-preise.json`) and `app/prices.py` answers `None` for everything it
  cannot say — a model the file does not list, a file that will not parse, a
  missing exchange rate. The one thing it must never return is 0,00 €, which is
  the same mistake as computing a figure from `null`. Written by
  `scripts/update_llm_prices.py` from OpenRouter's own `/api/v1/models` and the
  ECB's daily rate rather than by asking a model: the provider *publishes* the
  numbers, and a model asked the same question is reciting a page at best.

- **The button that starts a job must not be the thing that runs it.** The
  index rebuilds write into the `indexes` volume, which the API mounts read-only, and
  they take minutes. So „Jetzt starten" writes a request file into the state
  directory both containers already share and the scheduler claims it on its
  next tick — in the container that has the writable mount and the lock against
  a second copy. Two consequences worth keeping: the request is *removed* when
  claimed, so a failing job is not restarted every twenty seconds; and a
  deployment without the `scheduler` service has nothing to claim it, so
  the scheduler writes a heartbeat and the page says „kein Scheduler" instead
  of offering a button whose effect never arrives.

- **Every list in the area is paged from the first version.** Not when it
  hurts: the account list is a full outer join over `users` and
  `nutzung_konto`, and the deployment where somebody needs to look an account
  up is exactly the one with a thousand of them. The order in every paged query
  ends in a unique column, because a paged list whose rows can swap places
  between pages shows some of them twice and others never.
