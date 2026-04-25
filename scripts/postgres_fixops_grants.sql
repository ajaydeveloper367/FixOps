-- Extra grants LangGraph checkpoints + new app tables need.
--
-- Why your existing grants may not be enough:
--   - GRANT ALL ON DATABASE … covers database-level rights (e.g. CONNECT) but does
--     NOT replace GRANT CREATE ON SCHEMA public … — creating *new* tables requires
--     CREATE (and USAGE) on the schema, not only privileges on tables that already exist.
--   - GRANT ALL ON ALL TABLES IN SCHEMA public … applies to tables that exist *at grant
--     time* (and default privileges for future objects only if you set ALTER DEFAULT
--     PRIVILEGES). LangGraph creates checkpoint_* tables later; those need schema CREATE.
--
-- Run as any role that is allowed to grant on schema public (often the DB owner or a
-- superuser), connected to database fixops, e.g.:
--   psql "postgresql://…@127.0.0.1:5432/fixops" -f scripts/postgres_fixops_grants.sql

GRANT CONNECT ON DATABASE fixops TO fixops;
GRANT CREATE ON SCHEMA public TO fixops;
GRANT USAGE ON SCHEMA public TO fixops;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO fixops;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO fixops;
