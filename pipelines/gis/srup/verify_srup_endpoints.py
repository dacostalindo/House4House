"""
SRUP WFS Endpoint Verification

Probes all 4 SRUP categories (IC, RAN, DPH, REN) to verify:
1. GetCapabilities returns expected feature types
2. GetFeature with COUNT=2 returns valid GeoJSON
3. resultType=hits returns feature counts

Run: python -m pipelines.gis.srup.verify_srup_endpoints
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import quote

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WFS_BASE = "https://servicos.dgterritorio.pt/SDISNITWFS"
WFS_VERSION = "2.0.0"
WFS_OUTPUT_FORMAT = "application/vnd.geo+json"
REQUEST_TIMEOUT = 120
REQUEST_DELAY = 2.0


@dataclass(frozen=True)
class ProbeTarget:
    category: str
    wfs_suffix: str
    feature_type: str

    @property
    def wfs_url(self) -> str:
        return f"{WFS_BASE}{self.wfs_suffix}/WFService.aspx"

    @property
    def endpoint_label(self) -> str:
        return f"_{self.wfs_suffix.split('_', 1)[1]}" if "_" in self.wfs_suffix else self.wfs_suffix


TARGETS: list[ProbeTarget] = [
    # IC — Heritage sites (national)
    ProbeTarget("IC", "SRUP_IC_PT1", "gmgml:Imóveis_Classificados_com_Zona_de_Proteção"),
    ProbeTarget("IC", "SRUP_IC_PT1", "gmgml:Imóveis_Classificados_Localizados"),
    # RAN — Agricultural reserve (national)
    ProbeTarget("RAN", "SRUP_RAN_PT1", "gmgml:RAN"),
    # DPH — Public water domain (national)
    ProbeTarget("DPH", "SRUP_DPH_PT1", "gmgml:Zona_de_Ocupação_Condicionada"),
    ProbeTarget("DPH", "SRUP_DPH_PT1", "gmgml:Zona_de_Ocupação_Proibida"),
    # REN — Ecological reserve (regional)
    ProbeTarget("REN", "SRUP_REN_NORTE", "gmgml:REN_Norte"),
    ProbeTarget("REN", "SRUP_REN_CENTRO", "gmgml:REN_Centro"),
    ProbeTarget("REN", "SRUP_REN_LVT", "gmgml:REN_LVT"),
    ProbeTarget("REN", "SRUP_REN_ALENTEJO", "gmgml:REN_Alentejo"),
    ProbeTarget("REN", "SRUP_REN_ALGARVE", "gmgml:REN_Algarve"),
]


# ---------------------------------------------------------------------------
# Probing functions
# ---------------------------------------------------------------------------


def check_capabilities(target: ProbeTarget) -> tuple[bool, str]:
    """Verify GetCapabilities lists the expected feature type."""
    url = (
        f"{target.wfs_url}?SERVICE=WFS&VERSION={WFS_VERSION}"
        f"&REQUEST=GetCapabilities"
    )
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        if "WFS_Capabilities" not in resp.text[:2000]:
            return False, "No WFS_Capabilities in response"
        if target.feature_type not in resp.text:
            return False, f"Feature type {target.feature_type} not found"
        return True, "OK"
    except requests.Timeout:
        return False, "Timeout"
    except requests.RequestException as e:
        return False, str(e)[:80]


def get_feature_count(target: ProbeTarget) -> tuple[int | None, str]:
    """Use resultType=hits to get total feature count without downloading data."""
    url = (
        f"{target.wfs_url}?SERVICE=WFS&VERSION={WFS_VERSION}"
        f"&REQUEST=GetFeature"
        f"&TYPENAMES={target.feature_type}"
        f"&resultType=hits"
    )
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        match = re.search(r'numberMatched="(\d+)"', resp.text)
        if match:
            return int(match.group(1)), "OK"
        match = re.search(r'numberOfFeatures="(\d+)"', resp.text)
        if match:
            return int(match.group(1)), "OK"
        return None, "No count in response"
    except requests.Timeout:
        return None, "Timeout"
    except requests.RequestException as e:
        return None, str(e)[:80]


def fetch_sample(target: ProbeTarget) -> dict:
    """Fetch 2 sample features to verify GeoJSON and inspect schema."""
    fmt = quote(WFS_OUTPUT_FORMAT, safe="")
    url = (
        f"{target.wfs_url}?SERVICE=WFS&VERSION={WFS_VERSION}"
        f"&REQUEST=GetFeature"
        f"&TYPENAMES={target.feature_type}"
        f"&OUTPUTFORMAT={fmt}"
        f"&COUNT=2"
    )
    result = {
        "status": "FAIL",
        "fields": 0,
        "field_names": [],
        "geom_type": "?",
        "error": "",
    }
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        data = resp.json()
        features = data.get("features", [])
        if not features:
            result["error"] = "No features returned"
            return result

        props = features[0].get("properties", {})
        geom = features[0].get("geometry", {})

        result["status"] = "OK"
        result["fields"] = len(props)
        result["field_names"] = list(props.keys())
        result["geom_type"] = geom.get("type", "?")
        return result
    except requests.Timeout:
        result["error"] = "Timeout"
        return result
    except Exception as e:
        result["error"] = str(e)[:80]
        return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 100)
    print("SRUP WFS Endpoint Verification")
    print("=" * 100)
    print()

    results: list[dict] = []

    for i, target in enumerate(TARGETS):
        print(f"[{i+1}/{len(TARGETS)}] {target.category} — {target.feature_type}")

        # 1. GetCapabilities
        cap_ok, cap_msg = check_capabilities(target)
        print(f"  GetCapabilities: {cap_msg}")

        time.sleep(REQUEST_DELAY)

        # 2. Feature count (hits)
        count, count_msg = get_feature_count(target)
        count_str = f"{count:,}" if count is not None else count_msg
        print(f"  Feature count:   {count_str}")

        time.sleep(REQUEST_DELAY)

        # 3. Sample features
        sample = fetch_sample(target)
        print(f"  Sample fetch:    {sample['status']}")
        if sample["status"] == "OK":
            print(f"  Fields ({sample['fields']}):    {sample['field_names']}")
            print(f"  Geom type:       {sample['geom_type']}")
        elif sample["error"]:
            print(f"  Error:           {sample['error']}")

        results.append({
            "category": target.category,
            "endpoint": target.endpoint_label,
            "feature_type": target.feature_type,
            "capabilities": "OK" if cap_ok else cap_msg,
            "count": count,
            "sample_status": sample["status"],
            "fields": sample["fields"],
            "geom_type": sample["geom_type"],
            "field_names": sample["field_names"],
        })

        print()
        if i < len(TARGETS) - 1:
            time.sleep(REQUEST_DELAY)

    # Summary table
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print()
    header = f"{'Category':<8} {'Endpoint':<18} {'Feature Type':<50} {'Status':<8} {'Count':>10} {'Fields':>6} {'Geom Type':<20}"
    print(header)
    print("-" * len(header))

    all_ok = True
    for r in results:
        status = r["sample_status"]
        count_str = f"{r['count']:,}" if r["count"] is not None else "?"
        ft_display = r["feature_type"][:48] + ".." if len(r["feature_type"]) > 50 else r["feature_type"]
        print(
            f"{r['category']:<8} {r['endpoint']:<18} {ft_display:<50} {status:<8} {count_str:>10} {r['fields']:>6} {r['geom_type']:<20}"
        )
        if status != "OK":
            all_ok = False

    print()
    if all_ok:
        print("All endpoints verified successfully.")
    else:
        failed = [r for r in results if r["sample_status"] != "OK"]
        print(f"WARNING: {len(failed)} endpoint(s) failed verification:")
        for r in failed:
            print(f"  - {r['category']} {r['feature_type']}")

    # Field schema detail
    print()
    print("=" * 100)
    print("FIELD SCHEMAS")
    print("=" * 100)
    seen = set()
    for r in results:
        if r["sample_status"] == "OK" and r["feature_type"] not in seen:
            seen.add(r["feature_type"])
            print(f"\n{r['category']} — {r['feature_type']}:")
            for field in r["field_names"]:
                print(f"  - {field}")


if __name__ == "__main__":
    main()
