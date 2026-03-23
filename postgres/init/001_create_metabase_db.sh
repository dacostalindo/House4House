#!/bin/bash
set -e

# Create the Metabase internal database and user.
# Metabase uses this DB to store its own metadata (users, dashboards, saved questions).
# The analytics warehouse is added as a data source through the Metabase UI.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE metabase;
    CREATE USER metabase_internal WITH PASSWORD '${METABASE_INTERNAL_DB_PASSWORD}';
    GRANT ALL PRIVILEGES ON DATABASE metabase TO metabase_internal;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "metabase" <<-EOSQL
    GRANT ALL ON SCHEMA public TO metabase_internal;
EOSQL
