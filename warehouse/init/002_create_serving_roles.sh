#!/bin/bash
set -e

# Create read-only roles for the serving layer (Metabase + Streamlit/Kepler.gl).
# These roles connect to the warehouse to query analytics data.
#
# On existing deployments (where the data volume already exists), run manually:
#   docker compose exec warehouse bash /docker-entrypoint-initdb.d/002_create_serving_roles.sh

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'metabase') THEN
        CREATE ROLE metabase LOGIN PASSWORD '${METABASE_DB_PASSWORD}';
      END IF;
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'streamlit') THEN
        CREATE ROLE streamlit LOGIN PASSWORD '${STREAMLIT_DB_PASSWORD}';
      END IF;
    END
    \$\$;

    -- Metabase: read-only on analytics schemas (dashboards, KPIs, charts)
    GRANT USAGE ON SCHEMA gold_analytics, silver_geo, silver_properties, silver_market TO metabase;
    GRANT SELECT ON ALL TABLES IN SCHEMA gold_analytics TO metabase;
    GRANT SELECT ON ALL TABLES IN SCHEMA silver_geo TO metabase;
    GRANT SELECT ON ALL TABLES IN SCHEMA silver_properties TO metabase;
    GRANT SELECT ON ALL TABLES IN SCHEMA silver_market TO metabase;
    ALTER DEFAULT PRIVILEGES FOR ROLE warehouse IN SCHEMA gold_analytics GRANT SELECT ON TABLES TO metabase;
    ALTER DEFAULT PRIVILEGES FOR ROLE warehouse IN SCHEMA silver_geo GRANT SELECT ON TABLES TO metabase;
    ALTER DEFAULT PRIVILEGES FOR ROLE warehouse IN SCHEMA silver_properties GRANT SELECT ON TABLES TO metabase;
    ALTER DEFAULT PRIVILEGES FOR ROLE warehouse IN SCHEMA silver_market GRANT SELECT ON TABLES TO metabase;

    -- Streamlit + Kepler.gl: read-only on analytics + geo (maps, custom apps)
    GRANT USAGE ON SCHEMA gold_analytics, silver_geo, silver_properties TO streamlit;
    GRANT SELECT ON ALL TABLES IN SCHEMA gold_analytics TO streamlit;
    GRANT SELECT ON ALL TABLES IN SCHEMA silver_geo TO streamlit;
    GRANT SELECT ON ALL TABLES IN SCHEMA silver_properties TO streamlit;
    ALTER DEFAULT PRIVILEGES FOR ROLE warehouse IN SCHEMA gold_analytics GRANT SELECT ON TABLES TO streamlit;
    ALTER DEFAULT PRIVILEGES FOR ROLE warehouse IN SCHEMA silver_geo GRANT SELECT ON TABLES TO streamlit;
    ALTER DEFAULT PRIVILEGES FOR ROLE warehouse IN SCHEMA silver_properties GRANT SELECT ON TABLES TO streamlit;
EOSQL
