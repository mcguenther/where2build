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
