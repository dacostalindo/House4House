"""
DGES Concurso Nacional de Acesso (CNA) — per-curso colocações results.

12 years × 3 phases = 36 XLSX/XLS/ODS files (2014–2025). DGES publishes one
file per (year, phase) containing every curso/instituição pair with vagas,
colocados, and nota último colocado at the contingente geral (regime geral).

Why a hard-coded URL dict instead of a URL pattern:
  Every year is a snowflake. Probed 11 candidate URL patterns; only 1
  resolved. Filenames mix `fase{n}_{YY}.xlsx`, `cna{YY}_{n}f_resultados.xls`,
  `cna{YY}_{n}f_resultados.ods`, `site_cna19_{n}f_resultados.xls`, and one-off
  variants like `fase1a25_site.xlsx`. The DGES historical-data page is the
  source of truth; we mirror it as a literal dict.

Why three formats:
  2025/2024/2023 are mostly .xlsx (one .xls outlier per year). 2022-2019 are
  .xls. 2018-2016 are .ods (LibreOffice native). Bronze loader routes by URL
  extension to openpyxl / xlrd / odfpy.

Family A trap (the "reference card" XLSX): DGES also publishes one file per
year named `dges_vagascna_nota_ult_colocado_1afase{Y}_{Y+1}_*.xlsx` showing
next year's vagas + prior year's nota. This duplicates Family B (the
per-phase results files we ingest here) and adds publish-date-axis ambiguity.
Family A is explicitly NOT ingested. See [[dges-acesso]] in the wiki.

Família B trap (the curso codes): `Código Curso` is a 4-char string but can
contain letters (e.g. 'L184' for Música, variante de Formação Musical).
Stored as TEXT, no zfill. `Código Instit.` is 4-digit numeric stored as TEXT
zero-padded for DGEEC.codigo_unidade_organica join compatibility.

Why custom DAG (not the GIS ingestion template):
  Template assumes a single download → unzip → load. We have a parametrised
  (year, phase) download with per-file URL lookups and 3-format dispatch.
  Templatising acesso-shaped sources is parked until a sibling appears.

License: open data, attribution to DGES (Direção-Geral do Ensino Superior).
"""

from __future__ import annotations

# --- URL manifest --------------------------------------------------------------
# Verified 2026-06-07: all 36 entries return HTTP 200.
# 8 .xlsx + 19 .xls + 9 .ods = 36 files. Verified by curl HEAD pass.
YEAR_PHASE_URLS: dict[tuple[int, int], str] = {
    (2025, 1): "https://wwwcdn.dges.gov.pt/sites/default/files/fase1a25_site.xlsx",
    (2025, 2): "https://wwwcdn.dges.gov.pt/sites/default/files/fase2_25.xlsx",
    (2025, 3): "https://wwwcdn.dges.gov.pt/sites/default/files/fase3_25.xlsx",
    (2024, 1): "https://wwwcdn.dges.gov.pt/sites/default/files/fase1_24.xlsx",
    (2024, 2): "https://wwwcdn.dges.gov.pt/sites/default/files/fase2_24.xls",
    (2024, 3): "https://wwwcdn.dges.gov.pt/sites/default/files/fase3_24.xlsx",
    (2023, 1): "https://wwwcdn.dges.gov.pt/sites/default/files/fase1_a23_0.xlsx",
    (2023, 2): "https://wwwcdn.dges.gov.pt/sites/default/files/fase2_23_0.xls",
    (2023, 3): "https://wwwcdn.dges.gov.pt/sites/default/files/fase3_23_0.xlsx",
    (2022, 1): "https://wwwcdn.dges.gov.pt/sites/default/files/cna22_1f_resultados.xls",
    (2022, 2): "https://wwwcdn.dges.gov.pt/sites/default/files/cna22_2f_resultados.xls",
    (2022, 3): "https://wwwcdn.dges.gov.pt/sites/default/files/cna22_3f_resultados.xls",
    (2021, 1): "https://wwwcdn.dges.gov.pt/sites/default/files/cna21_1f_resultados.xls",
    (2021, 2): "https://wwwcdn.dges.gov.pt/sites/default/files/cna21_2f_resultados.xls",
    (2021, 3): "https://wwwcdn.dges.gov.pt/sites/default/files/cna21_3f_resultados.xls",
    (2020, 1): "https://wwwcdn.dges.gov.pt/sites/default/files/cna20_1f_resultados.xls",
    (2020, 2): "https://wwwcdn.dges.gov.pt/sites/default/files/cna20_2f_resultados.xls",
    (2020, 3): "https://wwwcdn.dges.gov.pt/sites/default/files/cna20_3f_resultados.xls",
    (2019, 1): "https://wwwcdn.dges.gov.pt/sites/default/files/site_cna19_1f_resultados.xls",
    (2019, 2): "https://wwwcdn.dges.gov.pt/sites/default/files/site_cna19_2f_resultados.xlsx",
    (2019, 3): "https://wwwcdn.dges.gov.pt/sites/default/files/site_cna19_3f_resultados.xls",
    (2018, 1): "https://www.dges.gov.pt/sites/default/files/cna18_1f_resultados.ods",
    (2018, 2): "https://www.dges.gov.pt/sites/default/files/cna18_2f_resultados.ods",
    (2018, 3): "https://www.dges.gov.pt/sites/default/files/cna18_3f_resultados.ods",
    (2017, 1): "https://www.dges.gov.pt/sites/default/files/cna17_1f_resultados.ods",
    (2017, 2): "https://www.dges.gov.pt/sites/default/files/cna17_2f_resultados.ods",
    (2017, 3): "https://www.dges.gov.pt/sites/default/files/cna17_3f_resultados.ods",
    (2016, 1): "https://www.dges.gov.pt/sites/default/files/cna16_1f_resultados.ods",
    (2016, 2): "https://www.dges.gov.pt/sites/default/files/cna16_2f_resultados.ods",
    (2016, 3): "https://www.dges.gov.pt/sites/default/files/cna16_3f_resultados.ods",
    (
        2015,
        1,
    ): "https://www.dges.gov.pt/sites/default/files/ficheiros_excel_acesso/cna15_1f_resultados.xls",
    (
        2015,
        2,
    ): "https://www.dges.gov.pt/sites/default/files/ficheiros_excel_acesso/cna15_2f_resultados.xls",
    (
        2015,
        3,
    ): "https://www.dges.gov.pt/sites/default/files/ficheiros_excel_acesso/cna15_3f_resultados.xls",
    (
        2014,
        1,
    ): "https://www.dges.gov.pt/sites/default/files/ficheiros_excel_acesso/cna14_1f_resultados.xls",
    (
        2014,
        2,
    ): "https://www.dges.gov.pt/sites/default/files/ficheiros_excel_acesso/cna14_2f_resultados.xls",
    (
        2014,
        3,
    ): "https://www.dges.gov.pt/sites/default/files/ficheiros_excel_acesso/cna14_3f_resultados.xls",
}

# --- Sanity bands per file -----------------------------------------------------
# Probed 2026-06-07: 2025 fase 1 ≈ 92kB / 1132 rows; 2022 fase 1 ≈ 226kB; 2018
# fase 1 .ods ≈ 67kB. Bands are wide because format compression varies.
MIN_FILE_BYTES = 10_000
MAX_FILE_BYTES = 1_500_000

MIN_DATA_ROWS = 800  # 2018-2025 all ≥ ~900 rows per phase
MAX_DATA_ROWS = 1_500

# --- File structure ------------------------------------------------------------
# Probed: row 0-3 are merged title/subtitle/blank, row 4 is the header, row 5+
# is data. Column A (index 0) is always blank — data starts at column B.
# 2018 .ods has an extra annotation row at index 5 ('(1)' '(2)' …) — filtered
# generically because codigo_instit value '(1)' fails the 4-digit shape test.
HEADER_ROW_IDX = 4
DATA_START_ROW_IDX = 5
LEADING_BLANK_COLS = 1  # column A always blank, data starts at column B

# --- Column rename map ---------------------------------------------------------
# Source label → canonical bronze column. Synonyms collapse (L16):
#   "Sobras para\n2ª fase", "Sobras para2ª fase", "Vagas Sobrantes" → vagas_sobrantes
#   "Vagas Iniciais", "Vagas Iniciais 3F" → vagas_iniciais
#   "Nota do últ. colocado", "Nota do últ. colocado (cont. geral)" → nota_ult_colocado
#
# Loader normalizes labels (str.strip(), collapse internal whitespace) before
# lookup. Anything missing from this map is logged as drift in the summarize task.
SOURCE_LABEL_TO_COLUMN: dict[str, tuple[str, str]] = {
    # --- Identity — codigo_instit (label drifts ACROSS YEARS) ---
    "Código Instit.": ("codigo_instit", "text"),  # 2018+
    "Código Instituição": ("codigo_instit", "text"),  # 2017
    "Código da instituição": ("codigo_instit", "text"),  # 2014-2016 (lowercase i)
    # --- Identity — codigo_curso ---
    "Código Curso": ("codigo_curso", "text"),  # 2018+
    "Código do curso": ("codigo_curso", "text"),  # 2014-2016
    # --- Identity — nome_instituicao ---
    "Nome da Instituição": ("nome_instituicao", "text"),  # 2018+
    "Nome da instituição": ("nome_instituicao", "text"),  # 2014-2016 (lowercase i)
    "Instituição de ensino superior": ("nome_instituicao", "text"),  # 2017
    "Instituição": ("nome_instituicao", "text"),  # 2014/2015 F2, 2017/2018 F2
    # --- Identity — nome_curso ---
    "Nome do Curso": ("nome_curso", "text"),  # 2018+
    "Nome do curso": ("nome_curso", "text"),  # 2014-2016
    "Curso": ("nome_curso", "text"),  # 2017
    # --- Identity — grau ---
    "Grau": ("grau", "text"),  # 2014+
    "Grau académico": ("grau", "text"),  # 2016-2017
    # --- Vagas iniciais (label drifts heavily ACROSS YEARS — older years
    # use long-form "Vagas colocadas a concurso" instead of "Vagas Iniciais") ---
    "Vagas Iniciais": ("vagas_iniciais", "integer"),
    "Vagas iniciais": ("vagas_iniciais", "integer"),  # 2014-2015 lowercase
    "Vagas Iniciais 3F": ("vagas_iniciais", "integer"),  # F3 2025+ rename
    "Vagas colocadas a concurso": ("vagas_iniciais", "integer"),  # 2014/2015 F2/F3
    "Vagas colocadas a concurso na 2.ª fase quando da abertura da candidatura": (
        "vagas_iniciais",
        "integer",
    ),  # 2016 F2
    "Vagas colocadas a concurso na 3.ª fase": ("vagas_iniciais", "integer"),  # 2016 F3
    "Vagascolocadas aconcurso na 3.ª fase quando da abertura da candidatura": (
        "vagas_iniciais",
        "integer",
    ),  # 2016 F3 typo
    "Vagascolocadas aconcurso": ("vagas_iniciais", "integer"),  # 2017 F3 typo
    # --- Vagas de recolocação ---
    "Vagas de recolocação": ("vagas_recolocacao", "integer"),
    "Vagas de recolo- cação": ("vagas_recolocacao", "integer"),  # 2022 F3 typo (hyphen + space)
    "Vagas libertadas por recolocação": ("vagas_recolocacao", "integer"),  # 2014 F3
    "Vagas ocupadas na 1.ª fase libertadas pela recolocação de estudantes colocados e matriculados nessa fase": (
        "vagas_recolocacao",
        "integer",
    ),  # 2016 F2
    "Vagas ocupadas nas fases anteriores libertadas pela recolocação de estudantes colocados e matriculados em qualquer dessas fases": (
        "vagas_recolocacao",
        "integer",
    ),  # 2016 F3
    # --- Colocados ---
    "Colocados": ("colocados", "integer"),
    "Estudantes colocados": ("colocados", "integer"),  # 2016 F1
    "Estudantes colocados na 2.ª fase": ("colocados", "integer"),  # 2016 F2
    "Estudantes colocados na 3.ª fase": ("colocados", "integer"),  # 2016 F3
    "Colocados (desemp.)": ("colocados_desemp", "integer"),
    "Colocados em vaga adicional (desempates)": ("colocados_desemp", "integer"),  # 2020 F2
    "Colocados (sem class. final)": ("colocados_sem_class", "integer"),
    "Colocados sem classificação final": ("colocados_sem_class", "integer"),  # 2020 F2
    # --- Vaga adicional — labels are plural ("Vagas") in 2020-2022, singular
    # ("Vaga") in 2023+. Older years bundle multiple add'l-vaga concepts. ---
    "Vaga adic. (sem class. final)": ("vaga_adic_sem_class", "integer"),  # 2023+ singular
    "Vagas adic. (sem class. final)": ("vaga_adic_sem_class", "integer"),  # 2020-2022 plural
    "Vagas adic.(desempates)": ("vaga_adic_sem_class", "integer"),  # 2017 F3 (no space)
    "Vagas adic. (desempates)": ("vaga_adic_sem_class", "integer"),
    "Vagas adicionais (desemp + outros)": ("vaga_adic_sem_class", "integer"),  # 2017/2018 F2
    "Vagas adicionais criadas nos termos do Regulamento": (
        "vaga_adic_sem_class",
        "integer",
    ),  # 2016 F2/F3
    "Vaga adic. (vagas autónomas)": ("vaga_adic_autonomas", "integer"),  # 2023+ singular
    "Vagas adic. (vagas autónomas)": ("vaga_adic_autonomas", "integer"),  # 2022 F1 plural
    "Vagas adic. (desempates e vagas autónomas)": (
        "vaga_adic_autonomas",
        "integer",
    ),  # 2020/2021 F3
    "Vagas adic. (desempates e autónomas)": ("vaga_adic_autonomas", "integer"),  # 2022 F3
    "Vaga adic. (alíneas c) e e) do artº 10º)": ("vaga_adic_alineas_c_e", "integer"),  # F2-only
    # --- Nota (label drifts F1 vs F2/F3 AND across years) ---
    "Nota do últ. colocado (cont. geral)": ("nota_ult_colocado", "numeric"),  # 2018+ F1
    "Nota do últ. colocado": ("nota_ult_colocado", "numeric"),  # 2018+ F2/F3
    "Nota do últ. Colocado (cont. geral)": (
        "nota_ult_colocado",
        "numeric",
    ),  # 2018 F2 (uppercase C)
    "Nota do último colocado (conting. geral)": ("nota_ult_colocado", "numeric"),  # 2020 F2
    "Nota do últ. colocado (contingente geral)": ("nota_ult_colocado", "numeric"),  # 2017
    "Nota de candidatura do último colocado pelo contingente geral": (
        "nota_ult_colocado",
        "numeric",
    ),  # 2014-2015
    "Nota de candidatura do último colocado": ("nota_ult_colocado", "numeric"),  # 2014 F2/F3
    "Nota de candidatura do último colocado na 2.ª fase": (
        "nota_ult_colocado",
        "numeric",
    ),  # 2016 F2
    "Nota de candidatura do último colocado na 3.ª fase": (
        "nota_ult_colocado",
        "numeric",
    ),  # 2016 F3
    # --- Nota do primeiro colocado (2018 F2/F3 only — ceiling signal) ---
    "Nota do primeiro Colocado (cont. geral)": (
        "nota_primeiro_colocado",
        "numeric",
    ),  # 2018 F2 (uppercase C)
    "Nota do primeiro colocado": ("nota_primeiro_colocado", "numeric"),  # 2018 F3
    # --- Sobras → vagas sobrantes (L16 canonical) ---
    "Sobras para 2ª fase": ("vagas_sobrantes", "integer"),
    "Sobras para a 3ª fase": ("vagas_sobrantes", "integer"),  # 2017/2018 F2
    "Sobras para2ª fase": ("vagas_sobrantes", "integer"),  # .ods typo (2017+2018)
    "Vagas Sobrantes": ("vagas_sobrantes", "integer"),
    "Vagas sobrantes": ("vagas_sobrantes", "integer"),  # 2014-2016 lowercase
    "Vagas não ocupadas": ("vagas_sobrantes", "integer"),  # 2014 F2
    "Vagas da 3.ª fase não ocupadas": ("vagas_sobrantes", "integer"),  # 2014 F3
    "Vagas disponíveis no final da 2.ª fase": ("vagas_sobrantes", "integer"),  # 2016 F2
    "Vagas disponíveis no final da 3.ª fase": ("vagas_sobrantes", "integer"),  # 2016 F3
    # --- F3-only sobras-of-prior-phase accounting ---
    "Sobras 2F": ("sobras_2f", "integer"),
    "Não Matric 2F": ("nao_matric_2f", "integer"),
    "Não Matric 2F (sem class. final)": ("nao_matric_2f_sem_class", "integer"),
    "Não Matric 2F (sem class . final)": (
        "nao_matric_2f_sem_class",
        "integer",
    ),  # 2023/2024 F3 extra space
    "Sobras Retiradas": ("sobras_retiradas", "integer"),
}

# Header-anchor candidates — any of these in cols 0–2 of any of the first
# ~20 rows marks the header row. 3 variants observed across 2014–2025.
HEADER_ANCHOR_LABELS: tuple[str, ...] = (
    "Código Instit.",
    "Código Instituição",
    "Código da instituição",
)

# Canonical bronze columns in DDL order (preserves SOURCE_LABEL_TO_COLUMN
# iteration with duplicates removed).
BRONZE_DATA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("codigo_instit", "text"),
    ("codigo_curso", "text"),
    ("nome_instituicao", "text"),
    ("nome_curso", "text"),
    ("grau", "text"),
    ("vagas_iniciais", "integer"),
    ("vagas_recolocacao", "integer"),
    ("colocados", "integer"),
    ("colocados_desemp", "integer"),
    ("colocados_sem_class", "integer"),
    ("vaga_adic_sem_class", "integer"),
    ("vaga_adic_autonomas", "integer"),
    ("vaga_adic_alineas_c_e", "integer"),
    ("nota_ult_colocado", "numeric"),
    ("nota_primeiro_colocado", "numeric"),
    ("vagas_sobrantes", "integer"),
    ("sobras_2f", "integer"),
    ("nao_matric_2f", "integer"),
    ("nao_matric_2f_sem_class", "integer"),
    ("sobras_retiradas", "integer"),
)

# --- MinIO layout --------------------------------------------------------------
# raw/dges_acesso/{year}/fase_{n}/{filename_from_url}
# Original filenames preserved so the source archive is verbatim.
MINIO_BUCKET = "raw"
MINIO_PREFIX = "dges_acesso"

# --- HTTP ----------------------------------------------------------------------
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
        "House4House/pipelines/dges_acesso"
    ),
    "Accept": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/vnd.ms-excel,"
        "application/vnd.oasis.opendocument.spreadsheet,"
        "application/octet-stream"
    ),
}


def url_for(year: int, phase: int) -> str:
    """Lookup helper. Raises KeyError on (year, phase) not in the manifest."""
    return YEAR_PHASE_URLS[(year, phase)]


def filename_for(year: int, phase: int) -> str:
    """Original filename (basename of URL)."""
    return YEAR_PHASE_URLS[(year, phase)].rsplit("/", 1)[-1]


def minio_object_name(year: int, phase: int) -> str:
    """raw/dges_acesso/{year}/fase_{n}/{filename}"""
    return f"{MINIO_PREFIX}/{year}/fase_{phase}/{filename_for(year, phase)}"
