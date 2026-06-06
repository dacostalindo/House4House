"""
Público School Rankings — per-year file resolver table.

Público (jornal) publishes annual school rankings as static JSON files served
from CloudFront-fronted S3 buckets. The hosting convention changed three times
in seven years, so a static `download_url` doesn't fit; this config holds the
verified per-year tuples instead.

Source eras (verified 2026-06-06 via tests/3ciclo-all-years.har):

    2018-2020:  static.publicocdn.com/files/rankings{Y}/data/listas/rankings{Y}{kind}.js
    2021-2023:  static.publico.pt/files/rankings{Y}/data/listas/rankings{kind}.js
    2024+:      static.publico.pt/s3/rankings{Y}/data/listas/rankings{kind}.js

`kind` is "sec" (secundário, 11º+12º exames) or "9ano" (3º ciclo Provas Finais).
Provas Finais 9º ano were cancelled in 2020 and 2021 (COVID) so those tuples
are absent — this is intentional, not a TODO.

Despite the `.js` extension, the file body is a plain JSON array (no JSONP
wrapper, no `var x =` prefix). Anonymous fetch; requires Referer header.

Soft-404 gotcha: an unknown URL returns HTTP 200 with a 22634-byte HTML body
(Público's standard 404 page). Validation MUST size-check, not status-check.
"""

from __future__ import annotations

from dataclasses import dataclass

# Latest year a Público release is known to be public. Probe `rankings{Y+1}/`
# during the Mar-May window of each year and bump this when 200 OK + body
# size > soft-404 threshold.
LATEST_RELEASE_YEAR = 2024

# Header set the Público edge requires for anonymous fetches. Without Referer
# the CDN returns 403 on the /s3/ era buckets.
REQUEST_HEADERS = {
    "Referer": "https://www.publico.pt/",
    "Origin": "https://www.publico.pt",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}

# Public 404 sentinel — any response of this exact size is the HTML 404 page,
# regardless of HTTP status. Newer responses may grow; treat as a floor.
SOFT_404_BYTES = 22634

# Minimum credible body size for a real ranking JSON. The smallest verified
# real file is 2019 9ano at ~376 KB. Floor an order of magnitude under that.
MIN_REAL_BODY_BYTES = 100_000


@dataclass(frozen=True)
class RankingFile:
    """One Público ranking file — year × kind × verified URL."""

    year: int
    kind: str  # "sec" | "9ano"
    url: str
    expected_min_bytes: int  # observed size minus 10% slack


# All URLs verified live 2026-06-06. Sizes from production responses.
# Keep this table append-only at the bottom; never rewrite historical rows
# (those URLs have stable bodies — Público hasn't backfilled corrections).
YEAR_FILE_TABLE: tuple[RankingFile, ...] = (
    # --- Era 1: static.publicocdn.com, year-embedded filenames ---
    RankingFile(
        2018,
        "sec",
        "https://static.publicocdn.com/files/rankings2018/data/listas/rankings2018sec.js",
        290_000,
    ),
    RankingFile(
        2018,
        "9ano",
        "https://static.publicocdn.com/files/rankings2018/data/listas/rankings20189ano.js",
        360_000,
    ),
    RankingFile(
        2019,
        "sec",
        "https://static.publicocdn.com/files/rankings2019/data/listas/rankings2019sec.js",
        275_000,
    ),
    RankingFile(
        2019,
        "9ano",
        "https://static.publicocdn.com/files/rankings2019/data/listas/rankings20199ano.js",
        335_000,
    ),
    RankingFile(
        2020,
        "sec",
        "https://static.publicocdn.com/files/rankings2020/data/listas/rankings2020sec.js",
        280_000,
    ),
    # 2020 9ano omitted — Provas Finais 9º ano cancelled (COVID).
    # --- Era 2: static.publico.pt /files/, year stripped from filename ---
    RankingFile(
        2021,
        "sec",
        "https://static.publico.pt/files/rankings2021/data/listas/rankingssec.js",
        685_000,
    ),
    # 2021 9ano omitted — Provas Finais 9º ano cancelled (COVID).
    RankingFile(
        2022,
        "sec",
        "https://static.publico.pt/files/rankings2022/data/listas/rankingssec.js",
        930_000,
    ),
    RankingFile(
        2022,
        "9ano",
        "https://static.publico.pt/files/rankings2022/data/listas/rankings9ano.js",
        925_000,
    ),
    RankingFile(
        2023,
        "sec",
        "https://static.publico.pt/files/rankings2023/data/listas/rankingssec.js",
        525_000,
    ),
    RankingFile(
        2023,
        "9ano",
        "https://static.publico.pt/files/rankings2023/data/listas/rankings9ano.js",
        540_000,
    ),
    # --- Era 3: static.publico.pt /s3/, same filename convention as Era 2 ---
    RankingFile(
        2024, "sec", "https://static.publico.pt/s3/rankings2024/data/listas/rankingssec.js", 555_000
    ),
    RankingFile(
        2024,
        "9ano",
        "https://static.publico.pt/s3/rankings2024/data/listas/rankings9ano.js",
        575_000,
    ),
)


def files_for_year(year: int) -> tuple[RankingFile, ...]:
    """Return the (0..2) RankingFile entries for a single year."""
    return tuple(rf for rf in YEAR_FILE_TABLE if rf.year == year)


# MinIO storage layout: raw/publico_rankings/{year}/{kind}.json
MINIO_BUCKET = "raw"
MINIO_PREFIX = "publico_rankings"
