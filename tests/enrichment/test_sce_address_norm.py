"""Tests for pipelines.enrichment.sce_address_norm.

Two layers:

  1. Curated rule-coverage assertions — one per Appendix-A rule path. A
     regression on a specific rule (e.g. someone tweaks abbreviations and
     "Av." stops expanding to "avenida") fails its own named test with a
     clear assertion error.
  2. Real-row snapshot — runs the function against
     tests/fixtures/sce_addresses_aveiro.jsonl (38 diverse real Aveiro
     SCE rows across 24 bucket categories) and asserts the snapshot.
     Catches unintended pattern interactions that the curated tests
     miss.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines.enrichment.sce_address_norm import (
    geocode_query,
    normalize_address,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "sce_addresses_aveiro.jsonl"
)


# ---------------------------------------------------------------------------
# Layer 1 — curated rule-coverage assertions
# Each test exercises one Appendix-A rule path with hand-crafted inputs.
# ---------------------------------------------------------------------------


class TestAbbreviationExpansion:
    """Appendix A rule 2 — PT real-estate abbreviation glossary."""

    @pytest.mark.parametrize("prefix,expansion", [
        ("R.", "rua"),
        ("R", "rua"),
        ("Av.", "avenida"),
        ("AV", "avenida"),
        ("Tv.", "travessa"),
        ("TV", "travessa"),
        ("Lg.", "largo"),
        ("Est.", "estrada"),
        ("Edif.", "edificio"),
        ("URB", "urbanizacao"),
        ("Dr.", "doutor"),
        ("Prof.", "professor"),
        ("Eng.", "engenheiro"),
    ])
    def test_street_prefix_expansion(self, prefix, expansion):
        out = normalize_address(f"{prefix} Direita 45", concelho="Aveiro")
        assert out.startswith(f"aveiro|{expansion} "), (
            f"Expected {prefix!r} to expand to {expansion!r}, got: {out}"
        )

    def test_tv_with_ordinal(self):
        # "TVª" is a common variant of "Tv." (travessa)
        out = normalize_address("TVª do Eucalipto 12", concelho="Aveiro")
        assert "travessa" in out


class TestDiacriticFold:
    """Appendix A rule 4 — NFD normalise + strip combining marks."""

    def test_basic_diacritics(self):
        assert normalize_address("Rua São João", concelho="Aveiro") == (
            "aveiro|rua sao joao"
        )

    def test_circumflex_acute_cedilla(self):
        out = normalize_address("Rua Heróis de Angola", concelho="Aveiro")
        assert "herois" in out
        assert "ó" not in out

    def test_concelho_diacritics_folded(self):
        out = normalize_address("Rua X", concelho="São João da Madeira")
        assert out.startswith("saojoaodamadeira|")


class TestFracaoStripping:
    """Appendix A rule 3 — fração markers must be stripped."""

    def test_lote(self):
        assert "lote" not in normalize_address("Rua Direita Lote 5", concelho="Aveiro")

    def test_lt_with_space(self):
        assert "lt" not in normalize_address("Rua Direita LT 5", concelho="Aveiro")

    def test_lt_no_space(self):
        # "LT43" is a real Aveiro pattern (no whitespace between marker and digit)
        assert "lt43" not in normalize_address("Rua Direita LT43", concelho="Aveiro")

    def test_bloco(self):
        assert "bloco" not in normalize_address(
            "Rua Direita Bloco A", concelho="Aveiro"
        )

    def test_bl_short(self):
        assert "bl" not in normalize_address(
            "Rua Direita BL A1 RC", concelho="Aveiro"
        ).split()

    def test_fracao_keyword(self):
        out = normalize_address("Rua Direita Fração D", concelho="Aveiro")
        assert "fracao" not in out
        assert "d" not in out.split()[-1:]

    def test_s_n(self):
        assert "s/n" not in normalize_address(
            "Rua Direita s/n", concelho="Aveiro"
        )


class TestFloorAndDirection:
    """Appendix A rule 3 — floor + direction markers."""

    def test_andar(self):
        out = normalize_address("Rua Direita 4º Andar", concelho="Aveiro")
        assert "andar" not in out

    def test_esq_dto(self):
        for marker in ("1º Esq", "2º Dto", "3º Direito", "4º Esquerdo"):
            out = normalize_address(f"Rua Direita {marker}", concelho="Aveiro")
            for word in ("esq", "dto", "esquerdo", "direito"):
                assert word not in out.split()

    def test_no_space_variant(self):
        # "5ºandar" (no space between number and direction word)
        out = normalize_address("Rua Direita 5ºandar", concelho="Aveiro")
        assert "andar" not in out
        assert "5andar" not in out

    def test_digit_dot_direction(self):
        # "1.DIREITO" / "2.º Drt." patterns
        out = normalize_address("Rua Direita 1.DIREITO", concelho="Aveiro")
        assert "direito" not in out

    def test_drt_tr_tre_abbrev(self):
        # Rarer sub-floor abbreviations
        for marker in ("2.º Drt.", "1ºTR", "1ºTRE"):
            out = normalize_address(f"Rua Direita 17 {marker}", concelho="Aveiro")
            assert "drt" not in out.split()
            assert "tr" not in out.split()
            assert "tre" not in out.split()


class TestGroundFloorVariants:
    """Appendix A rule 3 — ground-floor markers (rés-do-chão)."""

    @pytest.mark.parametrize("variant", [
        "Rés-do-chão", "Res-do-chao", "RDC", "RCH", "R/c", "R/ch", "R.c.",
        "R.ch", "RC", "Rés do Chão", "rés do chão",
    ])
    def test_variant_stripped(self, variant):
        out = normalize_address(f"Rua Direita {variant}", concelho="Aveiro")
        for token in ("rdc", "rch", "rc", "res-do-chao"):
            assert token not in out.split(), f"{variant!r} → {out!r}"


class TestCommercialIndustrialMarkers:
    """Appendix A rule 3 — piso / loja / armazem markers."""

    def test_piso(self):
        for variant in ("Piso 2", "Piso -1", "2 piso"):
            out = normalize_address(f"Rua Direita {variant}", concelho="Aveiro")
            assert "piso" not in out

    def test_loja_word(self):
        out = normalize_address("Rua Direita Loja A", concelho="Aveiro")
        assert "loja" not in out

    def test_lj_abbreviation(self):
        # "Lj119" no-space variant from real Aveiro data
        out = normalize_address("Rua Direita Lj119", concelho="Aveiro")
        assert "lj119" not in out
        assert "lj" not in out.split()

    def test_armazem(self):
        out = normalize_address("Rua Direita Armazém 2", concelho="Aveiro")
        assert "armazem" not in out


class TestNumberMarker:
    """Appendix A rule 3 — 'Nº N' marker stripped, digit kept."""

    @pytest.mark.parametrize("variant", ["Nº 8", "N.º 8", "N. 8", "n.74", "Nº8"])
    def test_marker_stripped_digit_kept(self, variant):
        out = normalize_address(f"Rua Direita {variant}", concelho="Aveiro")
        # Marker (n.) gone, digit (8 or 74) survives
        digit = "".join(c for c in variant if c.isdigit())
        assert digit in out, f"Expected digit {digit!r} kept in {out!r}"
        assert " n " not in f" {out} "
        assert " n. " not in f" {out} "


class TestDecimalFracao:
    """Appendix A rule 3 — decimal fração markers (e.g. '4.18')."""

    def test_decimal_stripped(self):
        out = normalize_address("Rua Direita 25 RC 0.6", concelho="Aveiro")
        assert "0.6" not in out
        assert "06" not in out.split()


class TestParenthetical:
    """Appendix A rule 3 — parenthetical bits removed."""

    def test_parenthetical_stripped(self):
        out = normalize_address(
            "Rua Direita Bloco B2 (B204)", concelho="Aveiro"
        )
        assert "b204" not in out
        assert "(" not in out and ")" not in out


class TestNegativeLookahead:
    """Negative lookahead protects 'FR DE' / 'FR DA' / 'FR DO' from being
    stripped as the 'frente' abbreviation."""

    def test_fr_de_preserved(self):
        # Archaic noble title: "AV D FR DE MIGUEL..." — the 'FR' is 'Frei'
        out = normalize_address(
            "AV D FR DE Miguel de Bulhões e Sousa 42", concelho="Aveiro"
        )
        assert "fr" in out.split(), f"'FR DE' protection failed: {out!r}"
        assert "de" in out.split()


class TestConcelhoPrefix:
    """Appendix A rule 7 — concelho prepended as disambiguator."""

    def test_prefix_present(self):
        out = normalize_address("Rua Direita", concelho="Aveiro")
        assert out.startswith("aveiro|")

    def test_prefix_diacritic_folded(self):
        out = normalize_address("Rua X", concelho="Évora")
        assert out.startswith("evora|")

    def test_no_concelho(self):
        out = normalize_address("Rua Direita")
        assert out.startswith("|")


class TestFracaoFieldEndStrip:
    """The fracao FIELD is stripped from the end of morada if it appears
    there as a trailing token."""

    def test_trailing_fracao_stripped(self):
        out = normalize_address(
            "Rua Direita CY", fracao="CY", concelho="Aveiro"
        )
        assert " cy" not in out
        assert not out.endswith(" cy")

    def test_fracao_with_ordinal(self):
        # fracao field with ordinal indicator must be cleaned (matching the
        # morada which has already had º/ª stripped).
        out = normalize_address(
            "Rua Direita 91 1", fracao="1º", concelho="Aveiro"
        )
        # "1º" → frac_clean="1" → matches trailing " 1" → stripped
        assert not out.endswith(" 1")


class TestClusteringSemantics:
    """Two SCE certificates for the same physical building must collapse."""

    def test_abbreviated_vs_full(self):
        assert (
            normalize_address("R. Direita 45", concelho="Aveiro")
            == normalize_address("Rua Direita 45", concelho="Aveiro")
        )

    def test_case_insensitive(self):
        assert (
            normalize_address("RUA DIREITA 45", concelho="Aveiro")
            == normalize_address("Rua Direita 45", concelho="Aveiro")
        )

    def test_two_fracoes_same_building(self):
        # Two real Aveiro rows: same building "R Vicente de Almeida de Eca 64",
        # different fração suffixes B vs C.
        a = normalize_address(
            "R VICENTE DE ALMEIDA DE ECA 64 R/C - B",
            fracao="B", concelho="AVEIRO",
        )
        b = normalize_address(
            "R VICENTE DE ALMEIDA DE ECA 64 R/C - C",
            fracao="C", concelho="AVEIRO",
        )
        assert a == b, f"Same building must collapse: {a!r} vs {b!r}"

    def test_different_buildings_distinct(self):
        a = normalize_address("R Direita 45", concelho="Aveiro")
        b = normalize_address("R Direita 47", concelho="Aveiro")
        assert a != b, "Different house numbers must NOT collapse"

    def test_different_concelhos_distinct(self):
        a = normalize_address("Rua Direita 45", concelho="Aveiro")
        b = normalize_address("Rua Direita 45", concelho="Lisboa")
        assert a != b, "Same street in different concelhos must NOT collapse"


# ---------------------------------------------------------------------------
# Layer 2 — geocode_query coverage
# ---------------------------------------------------------------------------


class TestGeocodeQuery:
    """geocode_query keeps house numbers + diacritics, appends , freguesia, concelho, Portugal."""

    def test_basic_shape(self):
        q = geocode_query("Rua Direita 199", "Aradas", "Aveiro")
        assert q.endswith(", Portugal")
        assert "Aradas" in q
        assert "Aveiro" in q

    def test_house_number_kept(self):
        q = geocode_query("Rua Direita 199", "Aradas", "Aveiro")
        assert "199" in q

    def test_diacritics_preserved(self):
        q = geocode_query("Rua São João 5", "Esgueira", "Aveiro")
        assert "São João" in q

    def test_lote_stripped(self):
        q = geocode_query("Rua Direita Lote 5", "Aradas", "Aveiro")
        assert "Lote" not in q

    def test_parenthetical_stripped(self):
        q = geocode_query("Rua Direita Bloco B2 (B204)", "Aradas", "Aveiro")
        assert "(" not in q and ")" not in q

    def test_freguesia_skipped_when_present_in_morada(self):
        q = geocode_query("Rua Direita Aveiro", None, "Aveiro")
        # Don't duplicate "Aveiro" when it's already in the morada
        assert q.lower().count("aveiro") == 1


# ---------------------------------------------------------------------------
# Layer 3 — real-row snapshot test
# ---------------------------------------------------------------------------


def _load_fixture():
    rows = []
    with FIXTURE_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


_FIXTURE_ROWS = _load_fixture()


@pytest.mark.parametrize(
    "row",
    _FIXTURE_ROWS,
    ids=[
        f"{r['bucket']}:{r['morada'][:30]}".replace(" ", "_")
        for r in _FIXTURE_ROWS
    ],
)
def test_fixture_snapshot(row):
    """Snapshot regression on 38 diverse real Aveiro SCE rows across 24 buckets."""
    actual_normalize = normalize_address(
        row["morada"], row.get("fracao"),
        row.get("localidade"), row.get("concelho"),
    )
    actual_geocode = geocode_query(
        row["morada"], row.get("freguesia_detail"), row.get("concelho"),
    )
    assert actual_normalize == row["expected_normalize_address"]
    assert actual_geocode == row["expected_geocode_query"]
