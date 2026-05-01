# JLL Residential PT — Bronze Pipeline

## Data Source

[JLL Residential Portugal](https://residential.jll.pt) — premium residential real estate.
Platform: eGO Real Estate (`websiteapi.egorealestate.com/v1`).
Auth: public token embedded in page JS (`AuthorizationToken` header).

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/Developments?lng=en-GB&nre=50&pag={n}` | GET | Paginated development list |
| `/v1/Developments/{id}/Fractions?lng=en-GB&nre=200` | GET | Units per development |
| `/v1/Properties?lng=en-GB&type=236,34,37&nre=50&pag={n}` | GET | Land/plot listings |
| `/v1/SearchOptions?lng=en-GB` | GET | Filter options (types, districts, etc.) |

Required headers: `AuthorizationToken`, `UserInfoToken: 0`, `x-async: true`, `X-Served-By: JanelaDigital`.

## Tables

| Table | Write Disposition | PK | ~Rows |
|-------|------------------|-----|-------|
| `jll_developments` | SCD2 | `development_id` | 171 |
| `jll_developments_state` | UPSERT | `development_id` | 171 |
| `jll_listings` | SCD2 | `listing_id` | 7,584 |
| `jll_listings_state` | UPSERT | `listing_id` | 7,584 |
| `jll_plots` | SCD2 | `listing_id` | 0 (currently) |
| `jll_plots_state` | UPSERT | `listing_id` | 0 (currently) |

## Schedule

Thursdays 06:00 UTC (`0 6 * * 4`).

## Cost

$0/run — free public API.

## Rate Limiting

eGO returns HTTP 430 when hit too fast. Pipeline uses 1.0s delay between
requests and exponential backoff (30s × attempt) on 430 responses.
