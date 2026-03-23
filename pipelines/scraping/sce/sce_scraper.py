"""
SCE Pre-Certificate (PCE) Scraper — nodriver Edition
=====================================================
Scrapes pre-certificate data from the SCE portal (sce.pt) to track
upcoming construction activity by region.

Uses nodriver (undetected Chrome) to bypass Cloudflare Turnstile.

Strategy:
  - The portal caps results at 1,000 per query.
  - To get full coverage, we partition queries by freguesia (parish).
  - Each query is paginated (10 results per page, max 100 pages).
  - Turnstile auto-solves on each form submission (~8s).
  - Results and detail popups are parsed via JS in-browser.

Usage (standalone):
  python -m pipelines.scraping.sce.sce_scraper --distrito 11 --concelho 6

Usage (Airflow):
  Called by the ingestion template via sce_config.scrape_fn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCE_URL = "https://www.sce.pt/wp-content/plugins/sce-pesquisa-certificados/functions.php"
SCE_SEARCH_URL = "https://www.sce.pt/pesquisa-certificados/"

DOC_TYPE_PCE = "1;4"
DOC_TYPE_CE = "2;3;5"
DOC_TYPE_ALL = "1;2;3;4;5;6"

BUILDING_ALL = "1;2;3"
RESULTS_PER_PAGE = 10
MAX_PAGES = 100

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PCERecord:
    """A single pre-certificate record from the SCE portal."""
    doc_number: str
    morada: str
    fracao: str
    localidade: str
    concelho: str
    estado: str
    doc_substituto: str
    # Detail fields (from popup)
    tipo_documento: str = ""
    classe_energetica: str = ""
    data_emissao: str = ""
    data_validade: str = ""
    freguesia_detail: str = ""
    perito_num: str = ""
    conservatoria: str = ""
    sob_o_num: str = ""
    artigo_matricial: str = ""
    fracao_autonoma: str = ""
    # Query metadata
    query_distrito: str = ""
    query_concelho: str = ""
    query_freguesia: str = ""


# ---------------------------------------------------------------------------
# In-browser JavaScript extraction
# ---------------------------------------------------------------------------

# Extracts both table rows and detail popups in a single evaluate call
JS_EXTRACT_RESULTS = """
(function() {
    var resultDiv = document.querySelector('#div_pesquisaCEResult');
    if (!resultDiv) return JSON.stringify({count: 0, rows: []});

    // Parse result count
    var countEl = resultDiv.querySelector('#ce_numCertificados');
    var countText = countEl ? countEl.textContent : '';
    var countMatch = countText.match(/Resultados encontrados:\\s*([\\d.]+)/);
    var totalCount = countMatch ? parseInt(countMatch[1].replace('.', '')) : 0;

    // Parse table rows + detail popups
    var rows = [];
    var trs = resultDiv.querySelectorAll('table tr');
    for (var i = 0; i < trs.length; i++) {
        var cells = trs[i].querySelectorAll('td');
        if (cells.length < 6) continue;
        var link = cells[0].querySelector('a');
        if (!link || !link.textContent.trim().startsWith('SCE')) continue;

        var docNum = link.textContent.trim();
        var row = {
            doc_number: docNum,
            morada: cells[1].textContent.trim(),
            fracao: cells[2].textContent.trim(),
            localidade: cells[3].textContent.trim(),
            concelho: cells[4].textContent.trim(),
            estado: cells[5].textContent.trim(),
            doc_substituto: cells.length > 6 ? cells[6].textContent.trim() : ''
        };

        // Parse detail popup
        var popup = document.getElementById('div_' + docNum);
        if (popup) {
            var text = popup.textContent;

            // Energy class from image filename
            var img = popup.querySelector('img[src*="classesEnergeticas"]');
            if (img) {
                var m = img.src.match(/\\/([A-F](?:mais|menos)?)[^/]*\\.jpg/i);
                if (m) row.classe_energetica = m[1].replace('mais','+').replace('menos','-');
            }

            // Label-value pairs
            var labels = popup.querySelectorAll('label');
            for (var j = 0; j < labels.length; j++) {
                var labelText = labels[j].textContent.trim().toUpperCase();
                var parent = labels[j].parentElement;
                var value = '';
                if (parent) {
                    var clone = parent.cloneNode(true);
                    var labelInClone = clone.querySelector('label');
                    if (labelInClone) labelInClone.remove();
                    value = clone.textContent.trim();
                }

                if (labelText.indexOf('TIPO DE DOCUMENTO') > -1) row.tipo_documento = value;
                else if (labelText.indexOf('DATA DE EMISS') > -1) row.data_emissao = value;
                else if (labelText.indexOf('DATA DE VALIDADE') > -1) row.data_validade = value;
                else if (labelText.indexOf('FREGUESIA') > -1) row.freguesia_detail = value;
                else if (labelText.indexOf('PERITO') > -1) row.perito_num = value;
            }

            // Conservatória + sob o nº + artigo matricial + fracção autónoma
            var allDivs = popup.querySelectorAll('div');
            for (var k = 0; k < allDivs.length; k++) {
                var divText = allDivs[k].textContent;
                if (divText.indexOf('Conservat') > -1) {
                    var strongs = allDivs[k].querySelectorAll('strong');
                    if (strongs.length >= 1) row.conservatoria = strongs[0].textContent.trim();
                    var sobMatch = divText.match(/sob o n[ºo°]\\s*(\\d+)/i);
                    if (sobMatch) row.sob_o_num = sobMatch[1];
                }
                if (divText.indexOf('Art.') > -1 && divText.indexOf('matricial') > -1) {
                    var strongs2 = allDivs[k].querySelectorAll('strong');
                    for (var s = 0; s < strongs2.length; s++) {
                        var prevText = '';
                        var node = strongs2[s].previousSibling;
                        if (node) prevText = node.textContent || '';
                        if (prevText.indexOf('matricial') > -1) row.artigo_matricial = strongs2[s].textContent.trim();
                        if (prevText.indexOf('Frac') > -1 || prevText.indexOf('aut') > -1) row.fracao_autonoma = strongs2[s].textContent.trim();
                    }
                }
            }
        }

        rows.push(row);
    }

    return JSON.stringify({count: totalCount, rows: rows});
})()
"""

# ---------------------------------------------------------------------------
# Core scraping (nodriver)
# ---------------------------------------------------------------------------


async def wait_for_results(page, timeout: int = 30) -> bool:
    """Wait for the result div to be populated after form submit.

    Returns True if results are found, False if empty or timed out.
    Detects "0 resultados" and error messages early to avoid waiting the full timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        status = await page.evaluate("""
            (function() {
                var div = document.querySelector('#div_pesquisaCEResult');
                if (!div) return 'waiting';

                var html = div.innerHTML;
                // Check for actual results (table rows)
                if (html.length > 100) return 'found';

                // Check for "no results" message (empty query)
                var text = div.textContent || '';
                if (text.indexOf('0 resultado') > -1 || text.indexOf('Sem resultado') > -1)
                    return 'empty';

                // Check for error message
                if (text.indexOf('Pedido inv') > -1 || text.indexOf('erro') > -1)
                    return 'error';

                return 'waiting';
            })()
        """)
        if status == 'found':
            return True
        if status in ('empty', 'error'):
            return False
        await asyncio.sleep(1)
    return False


async def submit_and_wait(page, max_retries: int = 3) -> dict:
    """Submit the form, wait for AJAX response, return parsed results."""
    for attempt in range(max_retries):
        await page.evaluate("""
            jQuery('#frm_pesquisaCE').submit();
        """)

        if await wait_for_results(page, timeout=30):
            raw = await page.evaluate(JS_EXTRACT_RESULTS)
            return json.loads(raw)

        log.warning("Submit attempt %d/%d: no results, retrying...", attempt + 1, max_retries)
        await page.reload()
        await asyncio.sleep(random.uniform(5, 10))

    return {"count": 0, "rows": []}


async def set_form_values(page, distrito: str, concelho: str, freguesia: str = "0",
                          doc_type: str = DOC_TYPE_PCE):
    """Set form dropdown values via JS."""
    await page.evaluate(f"""
        var sel = document.querySelector('select[name="tiposDocumentoSelect"]');
        sel.value = '{doc_type}';
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
    """)
    await asyncio.sleep(0.3)

    await page.evaluate(f"""
        var sel = document.querySelector('select[name="distritosCESelect"]');
        sel.value = '{distrito}';
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
    """)
    await asyncio.sleep(random.uniform(2, 4))

    await page.evaluate(f"""
        var sel = document.querySelector('select[name="concelhosCESelect"]');
        sel.value = '{concelho}';
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
    """)
    await asyncio.sleep(random.uniform(2, 4))

    if freguesia != "0":
        await page.evaluate(f"""
            var sel = document.querySelector('select[name="freguesiasCESelect"]');
            sel.value = '{freguesia}';
            sel.dispatchEvent(new Event('change', {{bubbles: true}}));
        """)
        await asyncio.sleep(0.5)


async def fetch_dropdown_options(page, select_name: str) -> list[dict]:
    """Get the current options from a dropdown."""
    raw = await page.evaluate(f"""
        (function() {{
            var sel = document.querySelector('select[name="{select_name}"]');
            if (!sel) return '[]';
            var opts = [];
            for (var i = 0; i < sel.options.length; i++) {{
                var v = sel.options[i].value;
                if (v !== '0') opts.push({{value: v, text: sel.options[i].text}});
            }}
            return JSON.stringify(opts);
        }})()
    """)
    return json.loads(raw)


async def scrape_query(
    page,
    distrito: str,
    concelho: str,
    freguesia: str = "0",
    doc_type: str = DOC_TYPE_PCE,
    max_results: Optional[int] = None,
) -> list[dict]:
    """Scrape all pages for a single query."""
    records = []

    # Navigate to search page fresh
    await page.get(SCE_SEARCH_URL)
    await asyncio.sleep(random.uniform(3, 5))

    # Wait for jQuery
    for _ in range(10):
        has_jq = await page.evaluate("typeof jQuery !== 'undefined'")
        if has_jq:
            break
        await asyncio.sleep(1)

    # Set form values
    await set_form_values(page, distrito, concelho, freguesia, doc_type)

    # First page
    await page.evaluate("""
        NOVA_PESQUISA = true;
        jQuery("#numeroPaginaCE").val(0);
    """)

    result = await submit_and_wait(page)
    total = result.get("count", 0)
    page_rows = result.get("rows", [])

    log.info("  Query results: %d (distrito=%s, concelho=%s, freguesia=%s)",
             total, distrito, concelho, freguesia)

    if total == 0 or not page_rows:
        return records

    if total > 1000:
        log.warning("  %d results exceeds 1000 cap — consider querying by freguesia", total)

    records.extend(page_rows)

    if max_results and len(records) >= max_results:
        return records[:max_results]

    # Paginate through remaining pages
    max_page = min(total // RESULTS_PER_PAGE, MAX_PAGES - 1)
    for page_num in range(1, max_page + 1):
        await asyncio.sleep(random.uniform(3, 7))

        await page.evaluate(f"""
            NOVA_PESQUISA = false;
            jQuery("#numeroPaginaCE").val({page_num});
        """)

        result = await submit_and_wait(page)
        page_rows = result.get("rows", [])

        if not page_rows:
            break

        records.extend(page_rows)
        log.info("    Page %d: +%d rows (total: %d)", page_num, len(page_rows), len(records))

        if max_results and len(records) >= max_results:
            return records[:max_results]

    return records


async def scrape_concelho_by_freguesia(
    page,
    distrito: str,
    concelho: str,
    doc_type: str = DOC_TYPE_PCE,
) -> list[dict]:
    """Scrape a full concelho by querying each freguesia individually."""
    await page.get(SCE_SEARCH_URL)
    await asyncio.sleep(random.uniform(3, 5))

    for _ in range(10):
        has_jq = await page.evaluate("typeof jQuery !== 'undefined'")
        if has_jq:
            break
        await asyncio.sleep(1)

    await set_form_values(page, distrito, concelho, "0", doc_type)

    freguesias = await fetch_dropdown_options(page, "freguesiasCESelect")

    if not freguesias:
        log.warning("  No freguesias found — falling back to concelho-level query")
        return await scrape_query(page, distrito, concelho, "0", doc_type)

    log.info("  Found %d freguesias for distrito=%s, concelho=%s",
             len(freguesias), distrito, concelho)

    all_records = []
    for freg in freguesias:
        log.info("  Scraping freguesia: %s (code=%s)...", freg["text"], freg["value"])

        records = await scrape_query(page, distrito, concelho, freg["value"], doc_type)

        for r in records:
            r["query_distrito"] = distrito
            r["query_concelho"] = concelho
            r["query_freguesia"] = freg["value"]

        all_records.extend(records)
        log.info("    -> %d records", len(records))

        await asyncio.sleep(random.uniform(5, 15))

    # Deduplicate by doc_number
    seen = set()
    deduped = []
    for r in all_records:
        doc = r.get("doc_number", "")
        if doc not in seen:
            seen.add(doc)
            deduped.append(r)

    log.info("  Total for concelho: %d unique records (from %d raw)",
             len(deduped), len(all_records))
    return deduped


# ---------------------------------------------------------------------------
# Airflow scrape_fn (used by ingestion template)
# ---------------------------------------------------------------------------


async def sce_scrape_fn(page, region, config) -> list[dict]:
    """
    Scrape function conforming to ScrapingIngestionConfig.scrape_fn contract.

    Supports two param formats:
      - {"distrito": "11"}
        Dynamically fetches all concelhos from the dropdown, then scrapes each.
      - {"distrito": "11", "concelho": "6"}
        Single concelho (test/debug mode).
    """
    distrito = region.params["distrito"]
    concelho = region.params.get("concelho")

    if concelho:
        return await scrape_concelho_by_freguesia(page, distrito, concelho)

    # Dynamic mode: fetch concelhos from the dropdown
    await page.get(SCE_SEARCH_URL)
    await asyncio.sleep(random.uniform(3, 5))

    for _ in range(10):
        has_jq = await page.evaluate("typeof jQuery !== 'undefined'")
        if has_jq:
            break
        await asyncio.sleep(1)

    # Set distrito to populate the concelhos dropdown
    await page.evaluate(f"""
        var sel = document.querySelector('select[name="distritosCESelect"]');
        sel.value = '{distrito}';
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
    """)
    await asyncio.sleep(random.uniform(2, 4))

    concelhos = await fetch_dropdown_options(page, "concelhosCESelect")
    log.info("[sce] Distrito %s (%s): found %d concelhos",
             distrito, region.name, len(concelhos))

    all_records = []
    seen = set()
    for c in concelhos:
        log.info("[sce] Scraping concelho %s (%s) in distrito %s...",
                 c["text"], c["value"], distrito)
        records = await scrape_concelho_by_freguesia(page, distrito, c["value"])
        for r in records:
            doc = r.get("doc_number", "")
            if doc not in seen:
                seen.add(doc)
                all_records.append(r)
        log.info("[sce] Concelho %s: %d records (total: %d)",
                 c["text"], len(records), len(all_records))

    return all_records


# ---------------------------------------------------------------------------
# CLI (standalone usage)
# ---------------------------------------------------------------------------


def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Scrape PCE (pre-certificate) data from the SCE portal"
    )
    parser.add_argument("--distrito", type=str, required=True)
    parser.add_argument("--concelho", type=str, required=True)
    parser.add_argument("--freguesia", type=str, default="0")
    parser.add_argument("--output", type=str, default="sce_pce_results.jsonl")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--browser-path", type=str, default=None)
    parser.add_argument("--max-results", type=int, default=None)

    args = parser.parse_args()

    async def _run():
        import nodriver as uc

        kwargs = {"headless": args.headless}
        if args.browser_path:
            kwargs["browser_executable_path"] = args.browser_path

        browser = await uc.start(**kwargs)
        page = await browser.get(SCE_SEARCH_URL)
        await asyncio.sleep(5)

        if args.freguesia != "0":
            records = await scrape_query(
                page, args.distrito, args.concelho, args.freguesia,
                max_results=args.max_results,
            )
            for r in records:
                r["query_distrito"] = args.distrito
                r["query_concelho"] = args.concelho
                r["query_freguesia"] = args.freguesia
        else:
            records = await scrape_concelho_by_freguesia(
                page, args.distrito, args.concelho,
            )

        browser.stop()

        with open(args.output, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        log.info("Saved %d records to %s", len(records), args.output)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
