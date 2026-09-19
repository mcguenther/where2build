-- The announcement every visitor sees, set by an administrator.
--
-- A maintenance window, a known outage, "the cadastre is down this morning" --
-- the things a deployment has to be able to say without a release. One row,
-- and the check is what makes it one: an announcement table with two rows is a
-- question about which of them is showing.
--
-- Public on the way out (/api/ansage answers it to anybody, signed in or not),
-- so nothing goes in here that is not meant for everybody. That is a property
-- of the table rather than of the interface: there is one text and it is the
-- one on the page.
create table if not exists betriebsansage (
    id           smallint    primary key default 1 check (id = 1),
    text         text        not null default '',
    -- „hinweis" or „warnung". Two, not five: the difference the reader can act
    -- on is "worth knowing" against "something is broken right now".
    art          text        not null default 'hinweis',
    sichtbar     boolean     not null default false,
    -- When it stops showing by itself. Nullable, because "until I take it
    -- down" is a legitimate announcement -- but the interface offers an end,
    -- because the banner nobody removed is the one nobody believes any more.
    bis          timestamptz,
    geaendert_am timestamptz not null default now(),
    -- The account key of whoever last wrote it; the audit trail has the rest.
    von          text
);
