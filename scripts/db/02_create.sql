-- OAK Audit Working Paper Binder: create two roles and two databases. Run once, as a superuser.
--
-- It first repeats the checks of 01_check_names.sql and STOPS WITHOUT CHANGING ANYTHING if:
--   * you are not a superuser,
--   * the server is older than PostgreSQL 13 (gen_random_uuid() is needed), or
--   * a role or database named oak_binder_owner, oak_binder_app, oak_binder or
--     oak_binder_test already exists (compared case-insensitively).
-- It never drops anything, never touches a name it did not create, and never connects to any
-- other project's database. The Financial Spine's roles and databases are not referenced.
--
-- PostgreSQL cannot run CREATE DATABASE inside a transaction, so the script runs in stages
-- and is arranged to fail closed: whatever stage it stops at, nothing it has created can be
-- logged into or connected to by anyone it was not meant for.
--   1. Roles oak_binder_owner and oak_binder_app, NOLOGIN (nobody can log in as them yet),
--      with none of SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS or INHERIT, and
--      a comment marking them as made by this script. One transaction.
--   2. Database oak_binder (UTF8, owned by you, so oak_binder_owner cannot drop it), created
--      with ALLOW_CONNECTIONS false: nobody can connect to it yet.
--   3. One transaction: marker comment; every right revoked from PUBLIC; CONNECT and CREATE
--      for oak_binder_owner; CONNECT for oak_binder_app; and, last, ALLOW_CONNECTIONS true.
--      The database opens only together with its restricted rights, or not at all.
--   4 and 5. The same for oak_binder_test.
--   6. Inside each database: all rights on the public schema revoked from PUBLIC; USAGE and
--      CREATE for oak_binder_owner; USAGE for oak_binder_app. Rights on tables are granted by
--      the migrations that create them (SELECT and INSERT only on append-only tables).
--   7. One transaction: oak_binder_owner and oak_binder_app may log in. Passwords are unset.
-- If any statement fails, psql stops there (ON_ERROR_STOP). Run 01_check_names.sql to see
-- what exists; nothing is dropped automatically.
--
-- Passwords are not set here. Afterwards, in psql, run \password oak_binder_owner and
-- \password oak_binder_app: psql hides what you type and sends only a hash.
--
-- Do not run it with psql -1 / --single-transaction (CREATE DATABASE would fail at once).
--
-- Run (psql asks for the password itself; nothing is stored):
--   & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -p 5432 -U postgres -d postgres -f scripts\db\02_create.sql

\set ON_ERROR_STOP on

SELECT coalesce((SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user), false)
           AS is_superuser,
       current_setting('server_version_num')::int >= 130000 AS version_ok,
       (SELECT count(*) FROM pg_catalog.pg_roles
         WHERE lower(rolname) IN ('oak_binder_owner', 'oak_binder_app'))
     + (SELECT count(*) FROM pg_catalog.pg_database
         WHERE lower(datname) IN ('oak_binder', 'oak_binder_test')) = 0 AS names_free
\gset

\if :is_superuser
\else
    \echo 'STOPPED: connect as a PostgreSQL superuser (for example postgres). Nothing was changed.'
    \quit
\endif
\if :version_ok
\else
    \echo 'STOPPED: PostgreSQL 13 or later is required. Nothing was changed.'
    \quit
\endif
\if :names_free
\else
    \echo 'STOPPED: a role or database named oak_binder_owner, oak_binder_app, oak_binder or oak_binder_test already exists.'
    \echo 'Run scripts\db\01_check_names.sql to see which. Nothing was changed.'
    \quit
\endif

\echo 'Stage 1: roles, NOLOGIN until the last stage'
BEGIN;
CREATE ROLE oak_binder_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
CREATE ROLE oak_binder_app   NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
COMMENT ON ROLE oak_binder_owner IS 'OAK Working Paper Binder: runs migrations. Created by scripts/db/02_create.sql.';
COMMENT ON ROLE oak_binder_app   IS 'OAK Working Paper Binder: the API, least privilege. Created by scripts/db/02_create.sql.';
COMMIT;

\echo 'Stage 2: database oak_binder, closed to connections'
CREATE DATABASE oak_binder ENCODING 'UTF8' ALLOW_CONNECTIONS false;

\echo 'Stage 3: rights on oak_binder, then open it'
BEGIN;
COMMENT ON DATABASE oak_binder IS 'OAK Working Paper Binder. Created by scripts/db/02_create.sql.';
REVOKE ALL ON DATABASE oak_binder FROM PUBLIC;
GRANT CONNECT, CREATE ON DATABASE oak_binder TO oak_binder_owner;
GRANT CONNECT ON DATABASE oak_binder TO oak_binder_app;
ALTER ROLE oak_binder_app IN DATABASE oak_binder SET search_path = public;
ALTER DATABASE oak_binder ALLOW_CONNECTIONS true;
COMMIT;

\echo 'Stage 4: database oak_binder_test, closed to connections'
CREATE DATABASE oak_binder_test ENCODING 'UTF8' ALLOW_CONNECTIONS false;

\echo 'Stage 5: rights on oak_binder_test, then open it'
BEGIN;
COMMENT ON DATABASE oak_binder_test IS 'OAK Working Paper Binder: automated tests only. Created by scripts/db/02_create.sql.';
REVOKE ALL ON DATABASE oak_binder_test FROM PUBLIC;
GRANT CONNECT, CREATE ON DATABASE oak_binder_test TO oak_binder_owner;
GRANT CONNECT ON DATABASE oak_binder_test TO oak_binder_app;
ALTER ROLE oak_binder_app IN DATABASE oak_binder_test SET search_path = public;
ALTER DATABASE oak_binder_test ALLOW_CONNECTIONS true;
COMMIT;

\echo 'Stage 6: the public schema inside each database'
\connect oak_binder
BEGIN;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO oak_binder_owner;
GRANT USAGE ON SCHEMA public TO oak_binder_app;
COMMIT;
\connect oak_binder_test
BEGIN;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO oak_binder_owner;
GRANT USAGE ON SCHEMA public TO oak_binder_app;
COMMIT;
\connect postgres

\echo 'Stage 7: the roles may log in (passwords still unset)'
BEGIN;
ALTER ROLE oak_binder_owner LOGIN;
ALTER ROLE oak_binder_app LOGIN;
COMMIT;

\echo 'Done. Now set the passwords, still in psql:'
\echo '    \password oak_binder_owner'
\echo '    \password oak_binder_app'
\echo 'Then put them in backend\.env (OAK_DATABASE_URL, OAK_MIGRATION_DATABASE_URL, OAK_TEST_*).'
