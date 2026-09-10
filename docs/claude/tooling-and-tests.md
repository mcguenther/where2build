# Tooling, tests and the sandbox

How this repo is checked, and what the checking itself has cost. The commands
themselves are in `CLAUDE.md`; what is here is the behaviour behind them.

Two claims run through everything below. **A green suite is not a working
screen** — most of the mistakes this project has made produced no error at all,
so the pictures and the browser walks are not decoration. And **a test can pass
for the wrong reason**, which is worse than a red one, so every property worth
having is worth breaking on purpose once to see the test fail.

## What to run, and what each one is good for

| | Catches | Blind to |
|---|---|---|
| `pytest` | The backend's own logic, every upstream stubbed with respx | Anything about a real service, and anything about a screen |
| `pytest` with `TEST_DATABASE_URL` | SQL: the upsert, the row lock, `on delete cascade`, the jsonb codec | Same |
| `vitest` | Components in jsdom: geometry, formats, what a view renders from which state | Layout, colour, anything needing WebGL or a network |
| `node scripts/screenshots.mjs` | Collapsed layouts, unreadable colour, console errors, horizontal overflow, a map that drew nothing | Anything behind a sign-in — the run has no identity provider |
| A browser walk against the throwaway provider | Sign-in, the account page, sharing, withdrawing — the paths a screenshot cannot reach | Everything it was not written to click |
| `node scripts/bookmarklet.mjs` | The handover across two real origins: a real `window.open`, a real `postMessage`, and the coordinate that only a whole document carries | Everything else about the wizard |
| The containers (`scripts/docker-build-sandbox.sh up`) | The shipped `nginx.conf`, the images, what actually ends up inside them | Nothing the compose stack does not start — there is no database in it |

None of them replaces another. The share switches were green in `vitest` and
correct in the browser walk, and the walk is what found that the list announced
a „Kaufpreis" the link did not carry.

## The dev database

Postgres 16 lives at `/var/lib/postgresql/where2build-dev`, port 5433, user and
database `where2build`, `trust`. Start it with `pg_ctl`, and put its log file
*inside that directory*: the scratchpad path is not traversable for the
`postgres` user, and `pg_ctl` then fails with a permission error that names the
log file rather than the reason.

It does not survive a sandbox restart, and the failure looks like a code bug:
`ConnectionRefusedError` in **fixture setup**, so all 41 database tests error at
once and none of them is about what changed. The port lives nowhere but in the
start command — `postgresql.conf` carries `listen_addresses` and no `port` — so
a `pg_ctl … start` without `-o '-p 5433'` comes up happily on 5432 and produces
that same failure while `pg_isready` on 5432 says everything is fine.

`TEST_DATABASE_URL` points the suite at it. Everything in that database is
dropped between tests, so it must never name anything worth keeping.

## Signing in, without a provider

`fake-oidc.py` in the scratchpad answers the discovery document, the
authorisation endpoint and the token endpoint on `:9099` — enough for the whole
Authorization Code round trip. Two things it will not survive: it dies quietly
(then every walk reports "not signed in", which reads like a bug in the app),
and it must be started with `setsid nohup … < /dev/null &` or it goes with the
shell.

**A walk through the sign-in needs a real proxy in front of the static files** —
one that passes method, headers, body and 3xx through untouched. Anything that
follows redirects itself, or rewrites them, tests nothing: the whole flow is a
chain of redirects that sets a cookie on the way back.

## Docker in this sandbox

The daemon is not running at session start:

```bash
dockerd > /var/log/dockerd.log 2>&1 &
until docker info >/dev/null 2>&1; do sleep 1; done
```

`docker compose build` then still fails, and it is not a pip problem: the
sandbox re-terminates outbound HTTPS through its own CA
(`/root/.ccr/README.md`), which a fresh build container does not trust.
`pip install` fails against pypi.org with "self-signed certificate in
certificate chain"; `npm ci` fails the same way against the npm registry, just
with different error text ("Exit handler never called!"). It is a **trust**
problem, not a routing one — measured again 10.09.2026: with the CA in place a
build reaches pypi with no proxy variable and no `--network host`, and adding
either changes nothing.

Trusting the bundle from inside the container fixes both: `PIP_CERT` /
`REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` for pip, `NODE_EXTRA_CA_CERTS` for npm
— Node ships its own CA list and ignores the system trust store exactly the
way pip does.

**Use `scripts/docker-build-sandbox.sh build|up`.** It applies that to a
temporary, `sed`-patched copy of each Dockerfile — through BuildKit's
`--build-context`, so neither committed Dockerfile is touched and nothing has
to be copied into the build context — and falls back to a plain
`docker compose` call wherever `/root/.ccr/ca-bundle.crt` does not exist, i.e.
everywhere but here. On a real machine `docker compose up --build` needs none
of it and the script is a passthrough.

Its `up` already builds, so **`… up -d --build` fails**: the `--build` is
passed through to the plain `docker compose up` behind it, which is the
untrusted build the script exists to avoid. The error arrives as a pip
certificate failure, i.e. as though the script had not worked.

`docker pull python:3.11-slim` answers **429** from Docker Hub often enough
that one retry is routine.

**`docker compose up` brings the whole app, not a demo of half of it.** For a
while the stack was nginx plus the backend, so a person who ran the documented
command got an app whose sign-in button was absent and whose „Teilen" answered
„Teilen ist in diesem Betrieb nicht eingerichtet" — two symptoms, one cause,
and nothing anywhere said a database and a provider were missing. The file now
also starts Postgres and authentik (`ops/authentik/where2build.yaml`). An
optional feature may default to off in the code and still have to be **on in
the stack that is handed to someone to try**, or the first thing they meet is
a dead end.

The first provider in that stack was dex, which was a **second** dead end and
a subtler one: it came up, it answered, and it had no registration at all —
so a page whose own button says „Anmelden oder Konto anlegen" led to a bare
English form where the only account was one nobody could guess. A stack that
runs is not the same as a stack somebody can get through. authentik was what
the plan named in the first place.

To reach the dev Postgres from a container, it has to listen on the bridge
(`listen_addresses = '*'`) *and* the bridge has to be in `pg_hba.conf`. The
error names the container's own address, which is on `172.18.x` for a
user-defined network, not the `172.17.x` of the default bridge — a `172.17.0.0/16`
line looks right and does not match.

## Ways a test has lied here

- **`node scripts/screenshots.mjs` serves `frontend/dist`, not the dev server.**
  Run `npm run build` first or the pictures show the previous code.
  Its Playwright import is an absolute sandbox path (`/opt/node22/...`), so the
  script only runs where that path exists — on a plain machine it fails before
  the first picture.

- **A dead upstream connection pool survives a container restart.** After the
  sandbox restarted, the running backend answered 502 for every Transitous call
  while the same request from `curl` returned 200. Restarting uvicorn fixed it;
  do not go looking for the bug in the code first.

- **The sandbox browser has no route to the internet**, only the shell has.
  Basemap tiles therefore cannot be verified by screenshot here; the camera
  maths is covered by `tests/projection.test.js` instead. Tiles that come
  through *our own* backend are a different matter — the browser reaches those,
  so the route cards' raster ground can be photographed here.

- **An optional dependency has to be optional in one place only.** The backend
  image installed `.[poi]` and never `tesseract-ocr`, so every Compose
  deployment reported „keine Bilderkennung eingerichtet“ while the code, the
  tests and the README all said it was wired up. `apt-get install tesseract-ocr
  tesseract-ocr-deu` plus `.[poi,ocr]`; the German data is not optional either,
  because the patterns key on the words around the number.

- **A test that mocks by call order breaks when the run gets better.** Six
  tests pinned an ordered `side_effect` list, so fetching the district outline
  one step earlier failed them all — for a change that made the product better
  and cost no extra request. `_cadastre()` exists for exactly this and its
  docstring says so; the ordered lists are gone.

- **jsdom does not submit a form from a dispatched click.** Wrapping the
  wizard's first step in a `<form>` (so Enter submits, as it does everywhere
  else) broke two tests that click the button, with no change to the component's
  logic. The button's click carries `.prevent` so a real browser does not submit
  twice, and the two paths — `trigger("click")` on the button, `trigger("submit")`
  on the form — are tested separately.

- **A positional selector into the main navigation breaks the day it grows an
  entry.** `screenshots.mjs` clicked `.main-nav a:nth-child(1..4)`, so adding
  „Start" in front silently shifted every one of them by a place — the run
  would have photographed the wrong pages, not failed. It clicks by name now.
  Two things to know: a nav entry carries its counter inside its text
  („Grundstücke7"), so an exact-name match finds nothing, and the brand link's
  aria-label is „Zur Startseite", so a loose match for „Start" finds two. The
  selector is `.main-nav a` filtered by text.

- **The screenshot script is the only place the old UI's selectors still
  lived.** Four steps of it drove the wizard's removed source radios („Text
  durchsuchen“, „Seite einfügen“, „Flurstück direkt“) and their two field ids
  (`#q-text`, `#q-paste`) long after `QueryBox` replaced them with one field,
  and `addPlot` clicked „Grundstück hinzufügen“ on a start page that no longer
  carries it. Nothing type-checks a Playwright selector, `npm run test` and
  `pytest` were both green, and the run dies 30 s into a five-minute job — so
  a UI change is not done until the pictures have actually been taken. The one
  field is `QUERY_FIELD` now, in one place.

- **What a whole drive-through of the app costs, measured.** One
  `node scripts/screenshots.mjs` — two themes, a narrow pass, three listing
  searches, one plot appraised end to end, both print sheets, 64 images and two
  PDFs — is **59 service calls and 1 007 map tiles** on a cold cache
  (09.09.2026). That is the number to size any per-account ceiling against, and
  it is why the run needs no exemption from the one in `app/ratelimit.py`.

- **The screenshot run clicks the navigation, so a page that drops it breaks
  the run.** `nav(page, "Grundstücke")` was the first step after `start-leer`,
  and the fresh start page has no sections to click. That step goes by route
  now, with the reason written next to it; every later `nav()` in the run has a
  stand behind it and finds the sections where they belong.

- **A test fixture that drops a named list of tables breaks on the next
  table.** `drop table plots, settings, users` failed outright the day
  `freigaben` arrived, because it references `users` — and it failed in
  *setup*, so all 34 database tests errored at once and none of them was about
  the new feature. The fixture enumerates `pg_tables` now and drops what it
  finds, so it follows `schema.sql` without anybody remembering.

- **An asyncpg pool belongs to the loop that made it, and there are two ways to
  forget that.** A second `TestClient` opened *inside* the first is two event
  loops on one pool; `asyncio.run(service().sweep())` against a pool built in
  the client's loop is the same mistake from the other side. Both report a
  future attached to a different loop, which does not name the cause. Drop the
  client's cookies instead of opening a second one, and `reset_services()`
  before driving the service from a loop of your own.

- **`page.fill` with 171 kB of markup takes ~27 s** — Playwright inserts it
  through the input pipeline — which sits just under the 30 s default and fails
  whenever the machine is busy. Measured identical before and after the change
  that appeared to break it. Dispatch a `paste` with a `DataTransfer` instead:
  instant, and it is the action the product is actually built around.

- **A note that says three causes where there is one sends the next reader
  looking in two wrong places.** The first version of the Docker entry above
  named `--network host` and `--build-arg HTTPS_PROXY` alongside the CA,
  because the run that finally worked had all three. Re-measured 10.09.2026,
  one at a time: with the CA in place and neither of the others, the build
  reaches pypi and the npm registry. Only the CA was ever doing anything. A
  finding is what a variable was *held against*, not what happened to be set.
  What the run did confirm stands: both images build, and the preview card
  draws **inside** the slim image — so FreeType there really does read the
  vendored `.woff` without brotli.

- **A `vi.mock` factory that omits a new named export breaks at *import*
  time.** `PAGE_LIMIT` moved into `lib/api.js` — next to the request that
  sends it, so neither the paste field nor the bookmarklet can forget the cap
  — and five test files mock that module by listing its surface. The importer
  then throws before a single test body runs, and vitest reports it against
  whichever component happened to be mounting: two failures about a chip's
  state and an uncalled `readPage`, neither of them the cause. Adding an
  export means adding it to the factories.

- **`git checkout <file>` on an uncommitted file is a delete, not an undo.** A
  line was broken on purpose to check that a test would catch it; `git
  checkout backend/app/services/oidc.py` put the file back to `HEAD` and took
  the whole day's unstaged change with it. The break was two characters, so
  `git diff` looked plausible right up until `grep -c _reachable` answered 0.
  Undo a deliberate break with the editor, or stage the work first — and after
  any checkout of a file that was dirty, grep for the thing that should be
  there.
