"""SCE address normalisation — Appendix A of the v1-wedge design doc.

Two functions, both deterministic:

  - normalize_address(morada, fracao, localidade, concelho) -> str
      The CLUSTERING key. Two SCE certificates for two fracções of the same
      physical building must produce the same string. Strips fração / floor /
      direction / industrial-unit markers, expands PT real-estate abbreviations,
      diacritic-folds, lowercases, and prepends the concelho as a
      cross-município disambiguator. Output shape: f"{concelho_key}|{address}".

  - geocode_query(morada, freguesia_detail, concelho) -> str
      The Nominatim /search input. Same Appendix-A ruleset minus the strips
      that hurt geocoding accuracy — KEEPS the house number, KEEPS diacritics,
      KEEPS casing, appends ", {freguesia}, {concelho}, Portugal".

Pattern set validated against 6,000 Aveiro SCE rows (half the distrito):
function-attributable collapse 44.2% (2,721 distinct address inputs →
1,519 distinct keys ≈ ~4 certs per building), 0.00% leakage across every
strip category. See tests/fixtures/sce_addresses_aveiro.jsonl and
tests/enrichment/test_sce_address_norm.py.

Consumed by:
  - pipelines/enrichment/sce_geocode_dag.py — calls geocode_query() to form
    the Nominatim request, and writes normalize_address() into
    bronze_enrichment.raw_sce_geocoded.normalized_address for downstream
    dbt staging + sprint-09 Slice B Levenshtein clustering.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# PT real-estate abbreviation glossary (Appendix A rule 2)
# Applied AFTER the º/ª strip + diacritic-fold + lowercase, so e.g. "TVª" →
# "tv" → expanded to "travessa". Word-boundary + optional trailing dot;
# only fires when followed by another word (street-prefix position).
# ---------------------------------------------------------------------------

_ABBREVIATIONS: list[tuple[str, str]] = [
    (r"\br\.?(?=\s+\w)", "rua"),
    (r"\bav\.?(?=\s+\w)", "avenida"),
    (r"\btv\.?(?=\s+\w)", "travessa"),
    (r"\blg\.?(?=\s+\w)", "largo"),
    (r"\best\.?(?=\s+\w)", "estrada"),
    (r"\bc\.?(?=\s+\w)", "caminho"),
    (r"\bpc\.?(?=\s+\w)", "praca"),
    (r"\bprc\.?(?=\s+\w)", "praca"),
    (r"\bp\.?(?=\s+\w)", "praca"),
    (r"\bedif\.?(?=\s+\w)", "edificio"),
    (r"\bbr\.?(?=\s+\w)", "bairro"),
    (r"\burb\.?(?=\s+\w)", "urbanizacao"),
    (r"\bdr\.?(?=\s+\w)", "doutor"),
    (r"\bprof\.?(?=\s+\w)", "professor"),
    (r"\beng\.?(?=\s+\w)", "engenheiro"),
]

# Direction / position words (Appendix A rule 3). All abbreviations included:
# esq=esquerdo, dto/drt/dir=direito, frt/fr=frente, cto=centro, tr/tre=trás.
_DIR_WORDS = (
    "andar|esq|dto|drt|esquerdo|direito|frente|centro|tras"
    "|dir|frt|fr|cto|tr|tre"
)

# ---------------------------------------------------------------------------
# Clustering-key strip patterns. Order matters — applied top-to-bottom.
# Locked after iterating against 6,000 Aveiro SCE rows: 0% leakage.
# ---------------------------------------------------------------------------

_FRACAO_STRIPS: list[str] = [
    # Block / lot markers
    r"\blote\s+[\w/-]+",
    r"\blt\s+[\w/-]+",
    r"\blt\d+\w*\b",  # "LT43" (no space)
    r"\bl\s+\d+\w*\b",
    r"\bbloco\s+[\w/-]+",
    r"\bbl\s+\w+\b",
    # Explicit fração marker
    r"\bfracao\s+\w+\b",
    # Sem número
    r"\bs/n\b",
    # Floor + direction — three variants: with-space, no-space, digit-dot-direction
    rf"\b\d+\s+({_DIR_WORDS})\b",
    rf"\b\d+({_DIR_WORDS})\b",
    rf"\b\d+\.\s*({_DIR_WORDS})\b",
    # Piso / loja / armazém markers (commercial / industrial unit identifiers)
    r"\bpiso\s+-?\d+\w*\b",
    r"\b\d+\s+piso\b",  # "N piso" reverse order
    r"\bpiso\b",
    r"\bloja\s+\w+\b",
    r"\bloja\b",
    r"\blj\s*\w*\b",  # "Lj119" / "Lj 119" / "Lj"
    r"\barmazem\s+\w+\b",
    r"\barmazem\b",
    # Decimal fração (e.g. "4.18" = floor.unit)
    r"\b\d+\.\d+\b",
    # Ground floor variants — exhaustive
    r"\bres-do-chao\b",
    r"\bres\s+do\s+chao\b",
    r"\brdc\b",
    r"\brch\b",
    r"\brc\b",
    r"\br\s*[./]\s*ch\b",
    r"\br\s*[./]\s*c\b",
    # Bare direction words (orphans after the digit was stripped earlier).
    # Negative lookahead protects "FR DE" / "FR DA" / "FR DO" (= "Frei de" /
    # archaic noble titles) so those don't get mistaken for the "FR" abbrev
    # of "Frente".
    rf"\b({_DIR_WORDS})\b(?!\s+(de|da|do))",
    # "Nº 8" / "n. 8" / "n.74" — strip the marker prefix, keep the digit
    r"\bn[.º°]?\s*(?=\d)",
    # Parenthetical bits (often per-unit references like "(B204)" / "(3º ESQ)")
    r"\([^)]*\)",
]

# ---------------------------------------------------------------------------
# Geocoding-specific strips — less aggressive (KEEP the house number; it
# sharpens Nominatim's resolution).
# ---------------------------------------------------------------------------

_GEOCODE_STRIPS: list[str] = [
    r"\blote\s+[\w/-]+",
    r"\blt\s+[\w/-]+",
    r"\bbloco\s+[\w/-]+",
    r"\bbl\s+\w+\b",
    r"\bfra[cç][aã]o\s+\w+\b",
    r"\bs/n\b",
    rf"\b\d+[º°]?\s*({_DIR_WORDS})\b",
    r"\bn\.?[º°]?\s+(?=\d)",
    r"\br[ée]s-do-ch[ãa]o\b",
    r"\brdc\b",
    r"\brch\b",
    r"\(([^)]*)\)",
    r"\bpiso\s+-?\d+\w*\b",
    r"\bloja\s+\w+\b",
    r"\barmazem\s+\w+\b",
]


def _strip_ordinals(s: str) -> str:
    """Drop PT ordinal indicators — they don't decompose under NFD."""
    return s.replace("º", "").replace("ª", "").replace("°", "")


def _diacritic_fold(s: str) -> str:
    """NFD-normalise + drop combining marks (São João → Sao Joao)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)
    )


def _normalize_concelho(concelho: str | None) -> str:
    if not concelho:
        return ""
    out = _diacritic_fold(concelho).lower()
    return re.sub(r"[^a-z0-9]+", "", out)


def normalize_address(
    morada: str | None,
    fracao: str | None = None,
    localidade: str | None = None,
    concelho: str | None = None,
) -> str:
    """Return the clustering key for an SCE row. See Appendix A.

    Output: f"{concelho_key}|{address}". Two SCE rows for the same physical
    building produce the same string regardless of which fração they describe.
    Concelho is prepended to disambiguate identically-named streets across
    municípios.
    """
    concelho_key = _normalize_concelho(concelho)
    if not morada:
        return f"{concelho_key}|"

    s = morada
    s = _strip_ordinals(s)
    s = _diacritic_fold(s)
    s = s.lower()
    for pattern, replacement in _ABBREVIATIONS:
        s = re.sub(pattern, replacement, s)
    for pattern in _FRACAO_STRIPS:
        s = re.sub(pattern, " ", s, flags=re.IGNORECASE)

    # If the fracao field is set, also strip occurrences of that exact letter
    # sequence at end of string (e.g. fracao='CY' + morada ends with " CY").
    # Strip ordinals from fracao too — the morada has already had º/ª stripped,
    # so a fracao value like "1º" must be cleaned to "1" to match.
    if fracao and fracao.strip() and fracao.strip() not in ("0",):
        frac_clean = _strip_ordinals(_diacritic_fold(fracao).lower()).strip()
        if frac_clean:
            s = re.sub(rf"\b{re.escape(frac_clean)}\s*$", " ", s)

    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Append localidade when non-trivial and not already present
    if localidade:
        loc = _diacritic_fold(localidade).lower().strip()
        loc = re.sub(r"[^a-z0-9 ]+", " ", loc)
        loc = re.sub(r"\s+", " ", loc).strip()
        if loc and loc not in s and loc != concelho_key:
            s = f"{s} {loc}".strip()

    return f"{concelho_key}|{s}"


def geocode_query(
    morada: str | None,
    freguesia_detail: str | None = None,
    concelho: str | None = None,
) -> str:
    """Return the Nominatim /search input. Keeps house number + diacritics."""
    parts: list[str] = []

    if morada:
        s = morada.strip()
        for pattern in _GEOCODE_STRIPS:
            s = re.sub(pattern, " ", s, flags=re.IGNORECASE)
        s = re.sub(r"[,\s;:-]+\s*$", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            parts.append(s)

    if freguesia_detail:
        fd = freguesia_detail.strip()
        if fd and (not parts or fd.lower() not in parts[0].lower()):
            parts.append(fd.title())

    if concelho:
        c = concelho.strip()
        if c and (not parts or c.lower() not in parts[0].lower()):
            parts.append(c.title())

    parts.append("Portugal")
    return ", ".join(parts)
