"""Test SCE: proper flow — trigger form submit, wait for Turnstile + AJAX response."""
from playwright.sync_api import sync_playwright
import json
import re
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    # Track AJAX responses to functions.php
    ajax_responses = []
    def handle_response(response):
        if 'functions.php' in response.url:
            try:
                body = response.body().decode('utf-8', errors='replace')
                ajax_responses.append({
                    'status': response.status,
                    'length': len(body),
                    'body': body,
                })
            except Exception as ex:
                ajax_responses.append({'error': str(ex)})
    page.on('response', handle_response)

    page.goto('https://www.sce.pt/pesquisa-certificados/', timeout=30000)
    print('Page loaded')
    time.sleep(5)

    # Set form values
    page.select_option('select[name="tiposDocumentoSelect"]', '1;4')
    time.sleep(0.5)
    page.select_option('select[name="distritosCESelect"]', '11')
    time.sleep(3)
    page.select_option('select[name="concelhosCESelect"]', '6')
    time.sleep(2)

    # Now submit the form via jQuery (triggers the submit handler which renders Turnstile)
    print('Triggering form submit...')
    page.evaluate("""() => {
        NOVA_PESQUISA = true;
        jQuery("#numeroPaginaCE").val(0);
        jQuery('#frm_pesquisaCE').submit();
    }""")

    # Wait for Turnstile to render and auto-solve, then AJAX to complete
    print('Waiting for Turnstile to solve and AJAX response...')
    max_wait = 60  # seconds
    start = time.time()
    while time.time() - start < max_wait:
        if ajax_responses:
            print(f'Got AJAX response after {time.time() - start:.1f}s!')
            break
        # Check if Turnstile iframe appeared
        has_iframe = page.evaluate("""() => {
            var container = document.querySelector('#captcha-container-ce');
            if (!container) return false;
            return container.querySelector('iframe') !== null;
        }""")
        if has_iframe and time.time() - start > 5:
            elapsed = time.time() - start
            print(f'  Turnstile iframe visible at {elapsed:.1f}s, waiting for solve...')
        time.sleep(2)
    else:
        print(f'Timed out after {max_wait}s')

    if not ajax_responses:
        # Check if there's an error
        error = page.evaluate("""() => {
            var container = document.querySelector('#captcha-container-ce');
            return container ? container.innerHTML.substring(0, 500) : 'no container';
        }""")
        print(f'Captcha container: {error}')
        browser.close()
        exit()

    # Parse the response
    resp = ajax_responses[0]
    print(f'Response status: {resp["status"]}')
    print(f'Response length: {resp["length"]}')

    from bs4 import BeautifulSoup
    body = resp['body']
    soup = BeautifulSoup(body, 'html.parser')

    # Check for errors
    error = soup.find('span', class_='search-captcha-error')
    if error:
        print(f'Error: {error.text}')

    # Check result count
    match = re.search(r'Resultados encontrados:\s*([\d.]+)', body)
    if match:
        print(f'\nResults found: {match.group(1)}')

    # Parse table rows
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
            # Try finding any SCE divs
            sce_divs = [d.get('id') for d in soup.find_all('div') if d.get('id', '').startswith('div_SCE')]
            print(f'\nSCE popup divs: {len(sce_divs)}')
            if sce_divs:
                first_div = soup.find('div', {'id': sce_divs[0]})
                if first_div:
                    print(f'\n=== Popup for {sce_divs[0]} ===')
                    print(first_div.get_text(separator='\n')[:1500])

    # Save full response for analysis
    with open('/tmp/sce_ajax_response.html', 'w') as f:
        f.write(body)
    print('\nFull response saved to /tmp/sce_ajax_response.html')

    browser.close()
