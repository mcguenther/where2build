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
| The containers (`docker compose`) | The shipped `nginx.conf`, the images, what actually ends up inside them | Nothing the compose stack does not start — there is no database in it |

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
once and none of them is about what changed.

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

A build then needs **three** things, because the agent proxy re-terminates TLS:

```bash
docker build --network host --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  -f <a copy of the Dockerfile with the CA added> -t … <context>
```

with `/root/.ccr/ca-bundle.crt` copied into the context and installed in an
early layer. Missing the CA gives "certificate verify failed"; having the CA
but not the proxy gets *past* the certificate and then times out mid-download,
which reads like a completely different failure. `docker pull python:3.11-slim`
answers **429** from Docker Hub often enough that one retry is routine.

None of that belongs in the repo's Dockerfiles — build from a copy under a
different `-f`, and delete it afterwards.

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

- **Docker builds in this sandbox need three things, and the base image needs
  patience.** The agent proxy re-terminates TLS, so a build has to run with
  `--network host`, carry `/root/.ccr/ca-bundle.crt` into an early layer, and
  be given `--build-arg HTTPS_PROXY=$HTTPS_PROXY` — with the CA but no proxy
  pip gets past the certificate and then times out, which reads like a
  different failure. `docker pull python:3.11-slim` also answers **429** from
  Docker Hub often enough that one retry is normal. None of it belongs in the
  repo's Dockerfiles; build with a copy under a different `-f`. Verified this
  way on 09.09.2026: both images build, the shipped `nginx.conf` sends a
  WhatsApp user agent to the backend and a browser to the app, and the preview
  card draws **inside** the slim image — so FreeType there really does read the
  vendored `.woff` without brotli.
