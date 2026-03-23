"""Test SCE: nodriver — read results from DOM after AJAX completes."""
import nodriver as uc
import asyncio
import json
import re
import time


async def main():
    browser = await uc.start(
        headless=False,
        browser_executable_path="/Users/manuellindo/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    )
    page = await browser.get('https://www.sce.pt/pesquisa-certificados/')
    print('Page loaded')
    await asyncio.sleep(5)

    # Set form values
    await page.evaluate("""
        var sel = document.querySelector('select[name="tiposDocumentoSelect"]');
        sel.value = '1;4';
        sel.dispatchEvent(new Event('change', {bubbles: true}));
    """)
    await asyncio.sleep(0.5)

    await page.evaluate("""
        var sel = document.querySelector('select[name="distritosCESelect"]');
        sel.value = '11';
        sel.dispatchEvent(new Event('change', {bubbles: true}));
    """)
    await asyncio.sleep(3)

    await page.evaluate("""
        var sel = document.querySelector('select[name="concelhosCESelect"]');
        sel.value = '6';
        sel.dispatchEvent(new Event('change', {bubbles: true}));
    """)
    await asyncio.sleep(2)

    # Submit
    print('Submitting...')
    await page.evaluate("""
        NOVA_PESQUISA = true;
        jQuery("#numeroPaginaCE").val(0);
        jQuery('#frm_pesquisaCE').submit();
    """)

    # Wait for results to appear in the DOM
    print('Waiting for results...')
    max_wait = 60
    start = time.time()
    while time.time() - start < max_wait:
        has_results = await page.evaluate("""
            (function() {
                var div = document.querySelector('#div_pesquisaCEResult');
                if (!div) return false;
                return div.innerHTML.length > 100;
            })()
        """)
        if has_results:
            print(f'Results appeared after {time.time() - start:.1f}s!')
            break
        await asyncio.sleep(2)
    else:
        print(f'Timed out after {max_wait}s')
        browser.stop()
        return

    # Extract results from DOM
    result_html = await page.evaluate("""
        document.querySelector('#div_pesquisaCEResult').innerHTML
    """)

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result_html, 'html.parser')

    # Check for errors
    error = soup.find('span', class_='search-captcha-error')
    if error:
        print(f'Error: {error.text}')
        browser.stop()
        return

    # Result count
    match = re.search(r'Resultados encontrados:\s*([\d.]+)', result_html)
    if match:
        print(f'\nResults found: {match.group(1)}')

    # Parse table
    rows = []
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td')
        if len(cells) >= 6:
            link = cells[0].find('a')
            if link and link.text.strip().startswith('SCE'):
                rows.append({
                    'doc_number': link.text.strip(),
                    'morada': cells[1].get_text(strip=True),
                    'fracao': cells[2].get_text(strip=True),
                    'localidade': cells[3].get_text(strip=True),
                    'concelho': cells[4].get_text(strip=True),
                    'estado': cells[5].get_text(strip=True),
                    'doc_substituto': cells[6].get_text(strip=True) if len(cells) > 6 else '',
                })

    print(f'\nTable rows: {len(rows)}')
    for r in rows[:5]:
        print(json.dumps(r, ensure_ascii=False, indent=2))

    # Parse detail popups
    if rows:
        doc = rows[0]['doc_number']
        popup = soup.find('div', {'id': f'div_{doc}'})
        if popup:
            print(f'\n=== Popup for {doc} ===')
            print(popup.get_text(separator='\n')[:1500])
        else:
            # Look for any popup divs
            sce_divs = [d.get('id') for d in soup.find_all('div') if d.get('id', '').startswith('div_SCE')]
            print(f'\nSCE popup divs found: {len(sce_divs)}')
            if sce_divs:
                print(f'First 3: {sce_divs[:3]}')
                first = soup.find('div', {'id': sce_divs[0]})
                if first:
                    print(f'\n=== Popup for {sce_divs[0]} ===')
                    print(first.get_text(separator='\n')[:1500])

    # Also check all table headers
    headers = [th.get_text(strip=True) for th in soup.find_all('th')]
    if headers:
        print(f'\nTable headers: {headers}')

    # Save full HTML
    with open('/tmp/sce_results.html', 'w') as f:
        f.write(result_html)
    print(f'\nFull results HTML saved to /tmp/sce_results.html ({len(result_html)} chars)')

    browser.stop()


asyncio.run(main())
