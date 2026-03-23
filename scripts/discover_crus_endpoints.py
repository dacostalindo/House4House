#!/usr/bin/env python3
"""
CRUS WFS Endpoint Discovery

Probes DGTERRITORIO's CRUS WFS endpoints for all Portuguese mainland
municipalities to discover which ones have published CRUS data.

Usage:
    # With database (reads municipality list from CAOP bronze table):
    python scripts/discover_crus_endpoints.py --db

    # Without database (uses hardcoded fallback list):
    python scripts/discover_crus_endpoints.py

    # Generate Python config snippet for crus_config.py:
    python scripts/discover_crus_endpoints.py --gen-config

    # Custom output path:
    python scripts/discover_crus_endpoints.py -o results/crus_discovery.json

Output: JSON report with available/unavailable endpoints + optional Python snippet.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CRUS_WFS_URL_TEMPLATE = (
    "https://servicos.dgterritorio.pt/SDISNITWFSCRUS_{code}_1/WFService.aspx"
)
WFS_VERSION = "2.0.0"
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 2.0

# WFS XML namespaces (DGTERRITORIO uses WFS 2.0 schema)
WFS_NS = {
    "wfs": "http://www.wfs.opengis.net/wfs/2.0",
    "ows": "http://www.opengis.net/ows/1.1",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MunicipalityResult:
    code: str
    name: str
    available: bool
    feature_type: str | None = None
    url: str | None = None
    error: str | None = None


@dataclass
class DiscoveryReport:
    timestamp: str
    total_probed: int = 0
    available: list[dict] = field(default_factory=list)
    unavailable: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        return {
            "total_probed": self.total_probed,
            "available": len(self.available),
            "unavailable": len(self.unavailable),
            "errors": len(self.errors),
            "coverage_pct": (
                round(len(self.available) / self.total_probed * 100, 1)
                if self.total_probed
                else 0
            ),
        }


# ---------------------------------------------------------------------------
# Municipality list sources
# ---------------------------------------------------------------------------


def get_municipalities_from_db() -> list[tuple[str, str]]:
    """Query CAOP bronze table for all mainland municipality codes + names."""
    import psycopg2

    host = os.environ.get("WAREHOUSE_HOST", "localhost")
    port = int(os.environ.get("WAREHOUSE_PORT", "5433"))
    dbname = os.environ.get("WAREHOUSE_DB", "warehouse")
    user = os.environ.get("WAREHOUSE_USER", "warehouse")
    password = os.environ.get("WAREHOUSE_PASSWORD", "warehouse")

    conn = psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT dtmn, municipio "
            "FROM bronze_geo.raw_caop_municipios "
            "ORDER BY dtmn"
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    log.info("Loaded %d municipalities from CAOP bronze table", len(rows))
    return [(code, name) for code, name in rows]


def get_municipalities_fallback() -> list[tuple[str, str]]:
    """Hardcoded list of all 278 mainland Portuguese municipality DTCC codes.

    Source: CAOP 2025 — cont_municipios layer.
    This is a fallback when the database is unavailable.
    """
    # fmt: off
    # (DTCC code, municipality name)
    # District 01 — Aveiro
    MUNICIPALITIES = [
        ("0101", "Agueda"), ("0102", "Albergaria-a-Velha"), ("0103", "Anadia"),
        ("0104", "Arouca"), ("0105", "Aveiro"), ("0106", "Castelo de Paiva"),
        ("0107", "Espinho"), ("0108", "Estarreja"), ("0109", "Santa Maria da Feira"),
        ("0110", "Ilhavo"), ("0111", "Mealhada"), ("0112", "Murtosa"),
        ("0113", "Oliveira de Azemeis"), ("0114", "Oliveira do Bairro"),
        ("0115", "Ovar"), ("0116", "Sao Joao da Madeira"),
        ("0117", "Sever do Vouga"), ("0118", "Vagos"),
        ("0119", "Vale de Cambra"),
        # District 02 — Beja
        ("0201", "Aljustrel"), ("0202", "Almodavar"), ("0203", "Alvito"),
        ("0204", "Barrancos"), ("0205", "Beja"), ("0206", "Castro Verde"),
        ("0207", "Cuba"), ("0208", "Ferreira do Alentejo"), ("0209", "Mertola"),
        ("0210", "Moura"), ("0211", "Odemira"), ("0212", "Ourique"),
        ("0213", "Serpa"), ("0214", "Vidigueira"),
        # District 03 — Braga
        ("0301", "Amares"), ("0302", "Barcelos"), ("0303", "Braga"),
        ("0304", "Cabeceiras de Basto"), ("0305", "Celorico de Basto"),
        ("0306", "Esposende"), ("0307", "Fafe"), ("0308", "Guimaraes"),
        ("0309", "Povoa de Lanhoso"), ("0310", "Terras de Bouro"),
        ("0311", "Vieira do Minho"), ("0312", "Vila Nova de Famalicao"),
        ("0313", "Vila Verde"), ("0314", "Vizela"),
        # District 04 — Braganca
        ("0401", "Alfandega da Fe"), ("0402", "Braganca"),
        ("0403", "Carrazeda de Ansiaes"), ("0404", "Freixo de Espada a Cinta"),
        ("0405", "Macedo de Cavaleiros"), ("0406", "Miranda do Douro"),
        ("0407", "Mirandela"), ("0408", "Mogadouro"),
        ("0409", "Torre de Moncorvo"), ("0410", "Vila Flor"),
        ("0411", "Vimioso"), ("0412", "Vinhais"),
        # District 05 — Castelo Branco
        ("0501", "Belmonte"), ("0502", "Castelo Branco"), ("0503", "Covilha"),
        ("0504", "Fundao"), ("0505", "Idanha-a-Nova"), ("0506", "Oleiros"),
        ("0507", "Penamacor"), ("0508", "Proenca-a-Nova"),
        ("0509", "Serta"), ("0510", "Vila de Rei"),
        ("0511", "Vila Velha de Rodao"),
        # District 06 — Coimbra
        ("0601", "Arganil"), ("0602", "Cantanhede"), ("0603", "Coimbra"),
        ("0604", "Condeixa-a-Nova"), ("0605", "Figueira da Foz"),
        ("0606", "Gois"), ("0607", "Lousa"), ("0608", "Mira"),
        ("0609", "Miranda do Corvo"), ("0610", "Montemor-o-Velho"),
        ("0611", "Oliveira do Hospital"), ("0612", "Pampilhosa da Serra"),
        ("0613", "Penacova"), ("0614", "Penela"),
        ("0615", "Soure"), ("0616", "Tabua"),
        ("0617", "Vila Nova de Poiares"),
        # District 07 — Evora
        ("0701", "Alandroal"), ("0702", "Arraiolos"), ("0703", "Borba"),
        ("0704", "Estremoz"), ("0705", "Evora"), ("0706", "Montemor-o-Novo"),
        ("0707", "Mora"), ("0708", "Mourao"), ("0709", "Portel"),
        ("0710", "Redondo"), ("0711", "Reguengos de Monsaraz"),
        ("0712", "Vendas Novas"), ("0713", "Viana do Alentejo"),
        ("0714", "Vila Vicosa"),
        # District 08 — Faro
        ("0801", "Albufeira"), ("0802", "Alcoutim"), ("0803", "Aljezur"),
        ("0804", "Castro Marim"), ("0805", "Faro"), ("0806", "Lagoa"),
        ("0807", "Lagos"), ("0808", "Loule"), ("0809", "Monchique"),
        ("0810", "Olhao"), ("0811", "Portimao"), ("0812", "Sao Bras de Alportel"),
        ("0813", "Silves"), ("0814", "Tavira"),
        ("0815", "Vila do Bispo"), ("0816", "Vila Real de Santo Antonio"),
        # District 09 — Guarda
        ("0901", "Aguiar da Beira"), ("0902", "Almeida"), ("0903", "Celorico da Beira"),
        ("0904", "Figueira de Castelo Rodrigo"), ("0905", "Fornos de Algodres"),
        ("0906", "Gouveia"), ("0907", "Guarda"), ("0908", "Manteigas"),
        ("0909", "Meda"), ("0910", "Pinhel"), ("0911", "Sabugal"),
        ("0912", "Seia"), ("0913", "Trancoso"),
        ("0914", "Vila Nova de Foz Coa"),
        # District 10 — Leiria
        ("1001", "Alcobaca"), ("1002", "Alvaiazere"), ("1003", "Ansiao"),
        ("1004", "Batalha"), ("1005", "Bombarral"), ("1006", "Caldas da Rainha"),
        ("1007", "Castanheira de Pera"), ("1008", "Figueiro dos Vinhos"),
        ("1009", "Leiria"), ("1010", "Marinha Grande"), ("1011", "Nazare"),
        ("1012", "Obidos"), ("1013", "Pedrogao Grande"), ("1014", "Peniche"),
        ("1015", "Pombal"), ("1016", "Porto de Mos"),
        # District 11 — Lisboa
        ("1101", "Alenquer"), ("1102", "Amadora"), ("1103", "Arruda dos Vinhos"),
        ("1104", "Azambuja"), ("1105", "Cadaval"), ("1106", "Lisboa"),
        ("1107", "Loures"), ("1108", "Lourinha"), ("1109", "Mafra"),
        ("1110", "Oeiras"), ("1111", "Sintra"), ("1112", "Sobral de Monte Agraco"),
        ("1113", "Torres Vedras"), ("1114", "Vila Franca de Xira"),
        ("1115", "Cascais"), ("1116", "Odivelas"),
        # District 12 — Portalegre
        ("1201", "Alter do Chao"), ("1202", "Arronches"), ("1203", "Avis"),
        ("1204", "Campo Maior"), ("1205", "Castelo de Vide"), ("1206", "Crato"),
        ("1207", "Elvas"), ("1208", "Fronteira"), ("1209", "Gaviao"),
        ("1210", "Marvao"), ("1211", "Monforte"), ("1212", "Nisa"),
        ("1213", "Ponte de Sor"), ("1214", "Portalegre"),
        ("1215", "Sousel"),
        # District 13 — Porto
        ("1301", "Amarante"), ("1302", "Baiao"), ("1303", "Felgueiras"),
        ("1304", "Gondomar"), ("1305", "Lousada"), ("1306", "Maia"),
        ("1307", "Marco de Canaveses"), ("1308", "Matosinhos"),
        ("1309", "Pacos de Ferreira"), ("1310", "Paredes"),
        ("1311", "Penafiel"), ("1312", "Porto"),
        ("1313", "Povoa de Varzim"), ("1314", "Santo Tirso"),
        ("1315", "Valongo"), ("1316", "Vila do Conde"),
        ("1317", "Vila Nova de Gaia"), ("1318", "Trofa"),
        # District 14 — Santarem
        ("1401", "Abrantes"), ("1402", "Alcanena"), ("1403", "Almeirim"),
        ("1404", "Alpiarca"), ("1405", "Benavente"), ("1406", "Cartaxo"),
        ("1407", "Chamusca"), ("1408", "Constancia"), ("1409", "Coruche"),
        ("1410", "Entroncamento"), ("1411", "Ferreira do Zezere"),
        ("1412", "Golega"), ("1413", "Macao"), ("1414", "Rio Maior"),
        ("1415", "Salvaterra de Magos"), ("1416", "Santarem"),
        ("1417", "Sardoal"), ("1418", "Tomar"), ("1419", "Torres Novas"),
        ("1420", "Vila Nova da Barquinha"), ("1421", "Ourem"),
        # District 15 — Setubal
        ("1501", "Alcacer do Sal"), ("1502", "Alcochete"), ("1503", "Almada"),
        ("1504", "Barreiro"), ("1505", "Grandola"), ("1506", "Moita"),
        ("1507", "Montijo"), ("1508", "Palmela"), ("1509", "Santiago do Cacem"),
        ("1510", "Seixal"), ("1511", "Sesimbra"), ("1512", "Setubal"),
        ("1513", "Sines"),
        # District 16 — Viana do Castelo
        ("1601", "Arcos de Valdevez"), ("1602", "Caminha"),
        ("1603", "Melgaco"), ("1604", "Moncao"),
        ("1605", "Paredes de Coura"), ("1606", "Ponte da Barca"),
        ("1607", "Ponte de Lima"), ("1608", "Valenca"),
        ("1609", "Viana do Castelo"), ("1610", "Vila Nova de Cerveira"),
        # District 17 — Vila Real
        ("1701", "Alijo"), ("1702", "Boticas"), ("1703", "Chaves"),
        ("1704", "Mesao Frio"), ("1705", "Mondim de Basto"),
        ("1706", "Montalegre"), ("1707", "Murca"),
        ("1708", "Peso da Regua"), ("1709", "Ribeira de Pena"),
        ("1710", "Sabrosa"), ("1711", "Santa Marta de Penaguiao"),
        ("1712", "Valpacos"), ("1713", "Vila Pouca de Aguiar"),
        ("1714", "Vila Real"),
        # District 18 — Viseu
        ("1801", "Armamar"), ("1802", "Carregal do Sal"),
        ("1803", "Castro Daire"), ("1804", "Cinfaes"),
        ("1805", "Lamego"), ("1806", "Mangualde"),
        ("1807", "Moimenta da Beira"), ("1808", "Mortagua"),
        ("1809", "Nelas"), ("1810", "Oliveira de Frades"),
        ("1811", "Penalva do Castelo"), ("1812", "Penedono"),
        ("1813", "Resende"), ("1814", "Santa Comba Dao"),
        ("1815", "Sao Joao da Pesqueira"), ("1816", "Sao Pedro do Sul"),
        ("1817", "Satao"), ("1818", "Sernancelhe"),
        ("1819", "Tabuaco"), ("1820", "Tarouca"),
        ("1821", "Tondela"), ("1822", "Vila Nova de Paiva"),
        ("1823", "Viseu"), ("1824", "Vouzela"),
    ]
    # fmt: on
    log.info("Using fallback list: %d municipalities", len(MUNICIPALITIES))
    return MUNICIPALITIES


# ---------------------------------------------------------------------------
# WFS probing
# ---------------------------------------------------------------------------


def _strip_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def probe_wfs_endpoint(code: str, name: str) -> MunicipalityResult:
    """Probe a single municipality's CRUS WFS endpoint via GetCapabilities."""
    url = CRUS_WFS_URL_TEMPLATE.format(code=code)
    caps_url = f"{url}?SERVICE=WFS&VERSION={WFS_VERSION}&REQUEST=GetCapabilities"

    try:
        resp = requests.get(caps_url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        text = resp.text
        if "WFS_Capabilities" not in text[:2000]:
            return MunicipalityResult(
                code=code,
                name=name,
                available=False,
                error="No WFS_Capabilities in response",
            )

        # Parse XML to extract FeatureType name
        feature_type = _extract_feature_type(text)
        if not feature_type:
            return MunicipalityResult(
                code=code,
                name=name,
                available=False,
                error="No CRUS FeatureType found in capabilities",
            )

        return MunicipalityResult(
            code=code,
            name=name,
            available=True,
            feature_type=feature_type,
            url=url,
        )

    except requests.exceptions.Timeout:
        return MunicipalityResult(
            code=code, name=name, available=False, error="Timeout"
        )
    except requests.exceptions.ConnectionError:
        return MunicipalityResult(
            code=code, name=name, available=False, error="Connection refused"
        )
    except requests.exceptions.HTTPError as e:
        return MunicipalityResult(
            code=code, name=name, available=False, error=f"HTTP {e.response.status_code}"
        )
    except Exception as e:
        return MunicipalityResult(
            code=code, name=name, available=False, error=str(e)
        )


def _extract_feature_type(xml_text: str) -> str | None:
    """Extract the CRUS FeatureType name from a WFS GetCapabilities XML response.

    Looks for <FeatureType><Name>gmgml:CRUS_*_V</Name> or similar patterns.
    Falls back to the first FeatureType if no CRUS-specific one is found.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    # Try with WFS 2.0 namespace
    for ns_prefix in [
        "{http://www.opengis.net/wfs/2.0}",
        "{http://www.opengis.net/wfs}",
        "",
    ]:
        feature_types = root.findall(f".//{ns_prefix}FeatureType")
        if not feature_types:
            continue

        for ft in feature_types:
            name_el = ft.find(f"{ns_prefix}Name")
            if name_el is None:
                # Try without namespace on child
                name_el = ft.find("Name")
            if name_el is not None and name_el.text:
                ft_name = name_el.text.strip()
                # Prefer CRUS-specific feature types
                if "CRUS" in ft_name.upper():
                    return ft_name

        # Fallback: return first feature type found
        for ft in feature_types:
            name_el = ft.find(f"{ns_prefix}Name") or ft.find("Name")
            if name_el is not None and name_el.text:
                return name_el.text.strip()

    return None


# ---------------------------------------------------------------------------
# Discovery runner
# ---------------------------------------------------------------------------


def run_discovery(
    municipalities: list[tuple[str, str]],
    delay: float = REQUEST_DELAY,
) -> DiscoveryReport:
    """Probe all municipalities and build a discovery report."""
    report = DiscoveryReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_probed=len(municipalities),
    )

    for i, (code, name) in enumerate(municipalities, 1):
        log.info(
            "[%d/%d] Probing %s (%s)...",
            i,
            len(municipalities),
            name,
            code,
        )

        result = probe_wfs_endpoint(code, name)

        if result.available:
            log.info("  -> AVAILABLE: %s", result.feature_type)
            report.available.append(asdict(result))
        elif result.error:
            log.info("  -> unavailable: %s", result.error)
            report.unavailable.append(asdict(result))

        # Rate limit — be polite to DGTERRITORIO
        if i < len(municipalities):
            time.sleep(delay)

    return report


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def generate_config_snippet(available: list[dict]) -> str:
    """Generate Python code for crus_config.py MUNICIPALITIES list."""
    lines = [
        "MUNICIPALITIES: list[CRUSMunicipalityConfig] = [",
    ]

    current_district = None
    for entry in sorted(available, key=lambda e: e["code"]):
        district = entry["code"][:2]
        if district != current_district:
            current_district = district
            lines.append(f"    # District {district}")

        code = entry["code"]
        name = entry["name"]
        ft = entry["feature_type"]
        lines.append(f'    CRUSMunicipalityConfig("{code}", "{name}", "{ft}"),')

    lines.append("]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Discover CRUS WFS endpoints for all Portuguese municipalities"
    )
    parser.add_argument(
        "--db",
        action="store_true",
        help="Read municipality list from CAOP bronze table (requires DB access)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="scripts/crus_discovery_report.json",
        help="Output JSON report path (default: scripts/crus_discovery_report.json)",
    )
    parser.add_argument(
        "--gen-config",
        action="store_true",
        help="Also generate Python config snippet for crus_config.py",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY,
        help=f"Delay between requests in seconds (default: {REQUEST_DELAY})",
    )
    args = parser.parse_args()

    # Get municipality list
    if args.db:
        try:
            municipalities = get_municipalities_from_db()
        except Exception as e:
            log.error("Failed to read from DB: %s. Falling back to hardcoded list.", e)
            municipalities = get_municipalities_fallback()
    else:
        municipalities = get_municipalities_fallback()

    log.info("Starting CRUS WFS discovery for %d municipalities", len(municipalities))

    # Run discovery
    report = run_discovery(municipalities, delay=args.delay)

    # Output report
    output = {
        "timestamp": report.timestamp,
        "summary": report.summary,
        "available": report.available,
        "unavailable": report.unavailable,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    log.info("Report written to %s", args.output)
    log.info(
        "Summary: %d available, %d unavailable out of %d (%.1f%% coverage)",
        report.summary["available"],
        report.summary["unavailable"],
        report.summary["total_probed"],
        report.summary["coverage_pct"],
    )

    # Generate config snippet
    if args.gen_config and report.available:
        snippet = generate_config_snippet(report.available)
        config_path = args.output.replace(".json", "_config.py")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(snippet)
        log.info("Config snippet written to %s", config_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
