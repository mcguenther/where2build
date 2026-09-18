-- Server storage for signed-in accounts.
--
-- Applied at start-up, every start-up, with CREATE TABLE IF NOT EXISTS. That
-- is enough for a schema that has never changed and is deliberately not a
-- migration tool: the moment a column has to be renamed, dropped or backfilled,
-- IF NOT EXISTS says nothing about the database it found and silently leaves it
-- as it was. A real tool (Alembic, or plain numbered .sql files with a
-- schema_migrations table) is due before the first change to anything below --
-- not before the first deployment.
--
-- Column names are German where the API is German. `dokument` and
-- `geaendert_am` are the wire format the frontend sends and reads back, the
-- same way `flaeche_amtlich_m2` is ALKIS'; renaming them here would put a
-- translation table between two places that agree.

-- Who has an account here. Created on first *write*, not at sign-in: the
-- sign-in path never touches this database, and somebody who signs in and
-- stores nothing leaves no row behind. What is kept is the minimum OpenID
-- gives us -- no mail address, no contact detail of any kind.
create table if not exists users (
    id          bigserial   primary key,
    issuer      text        not null,
    subject     text        not null,
    -- Nullable: the `profile` scope is optional and a provider may grant none
    -- of it. The interface then greets the person as "Angemeldet".
    anzeigename text,
    angelegt    timestamptz not null default now(),
    -- The pair OpenID Connect guarantees to be unique and never reassigned.
    unique (issuer, subject)
);

-- One row per plot, not one document per account: "zuletzt geändert" is an
-- ORDER BY, and a conflict has to be about one plot rather than about the
-- whole state.
--
-- `id` comes from the frontend (`plot-x7k2a9f`), so it is only unique within an
-- account and the primary key says so. That also makes the separation between
-- two accounts structural rather than a WHERE clause somebody has to remember.
create table if not exists plots (
    id           text        not null,
    user_id      bigint      not null references users (id) on delete cascade,
    dokument     jsonb       not null,
    geaendert_am timestamptz not null default now(),
    primary key (user_id, id)
);

-- The list on the start page and in "Meine Grundstücke", in one index.
create index if not exists plots_user_geaendert_idx
    on plots (user_id, geaendert_am desc);

-- A plot shared by link. Its own table and not a flag on `plots`, because a
-- share is a *copy*: what was shared stays what it was on the day, however the
-- original changes afterwards. Someone who got the link weeks ago has no
-- business seeing today's asking price.
--
-- `id` is the token in the URL and therefore the whole of the access control:
-- unguessable, and nothing else is checked. `laeuft_ab` is what keeps this
-- table from being a landfill -- every row has an end, and the sweep job
-- removes what is past it.
create table if not exists freigaben (
    id           text        primary key,
    user_id      bigint      not null references users (id) on delete cascade,
    -- The snapshot, already stripped of the personal note. Cut on the way in
    -- rather than on the way out, so a share can never hold what it must not
    -- show.
    dokument     jsonb       not null,
    angelegt     timestamptz not null default now(),
    laeuft_ab    timestamptz not null
);

-- The owner's own list, newest first.
create index if not exists freigaben_user_idx on freigaben (user_id, angelegt desc);
-- And the sweep, which asks only "what is past its end".
create index if not exists freigaben_ablauf_idx on freigaben (laeuft_ab);

-- The rest of the document: house types, destinations, the selection. One row
-- per account, because none of it is worth a conflict of its own.
create table if not exists settings (
    user_id      bigint      primary key references users (id) on delete cascade,
    dokument     jsonb       not null,
    geaendert_am timestamptz not null default now()
);

-- Where the deterministic readers and a model disagreed. Not a user's data and
-- deliberately not tied to an account: it is a note about the *pipeline*, made
-- while reading somebody's listing, and what it keeps is the sentence a pattern
-- could be written against — never the listing and never who was selling.
--
-- `text_hash` names the listing without storing it, so the same advert read
-- three times is one row. The unique key is what makes that true; re-reading is
-- the normal case, because the extraction cache has no expiry and a changed
-- prompt makes every listing new again.
--
-- No foreign key, no `user_id`, and it survives an account deletion on purpose:
-- there is nothing personal in it to delete. Belege are scrubbed of telephone
-- numbers and mail addresses on the way in (`services/lehrbuch.py`), because a
-- sentence out of an advert can carry what the extraction schema cannot.
create table if not exists abweichungen (
    id          bigserial   primary key,
    -- 'luecke' | 'widerspruch' | 'verworfen'
    art         text        not null,
    feld        text        not null,
    regulaer    text,
    modell      text,
    beleg       text,
    grund       text,
    text_hash   text        not null,
    quelle_url  text,
    modell_id   text,
    vorlage     text,
    gesehen_am  timestamptz not null default now(),
    unique (text_hash, art, feld, modell)
);

-- What the evaluation asks: everything of one kind, newest first.
create index if not exists abweichungen_art_idx on abweichungen (art, gesehen_am desc);
