"""Test SCE with headed browser + wait for AJAX response."""
from playwright.sync_api import sync_playwright
import json
import re
import time

with sync_playwright() as p:
    # Try headed mode - Turnstile may need visible browser
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    # Intercept AJAX
    responses_data = []
    def handle_response(response):
        if 'functions.php' in response.url or 'pesquisa' in response.url:
            try:
                body = response.body()
                responses_data.append({
                    'url': response.url,
                    'status': response.status,
                    'length': len(body),
                    'preview': body[:800].decode('utf-8', errors='replace'),
                })
            except Exception as ex:
                responses_data.append({'error': str(ex)})
    page.on('response', handle_response)

    page.goto('https://www.sce.pt/pesquisa-certificados/', timeout=30000)
    print('Page loaded, waiting 10s for Turnstile...')
    time.sleep(10)

    # Check turnstile
    has_turnstile = page.evaluate("() => { return document.querySelector('.cf-turnstile') !== null; }")
    print(f'Turnstile div present: {has_turnstile}')

    # Check if there's a rendered turnstile iframe
    iframes = page.evaluate("""() => {
        var frames = document.querySelectorAll('iframe');
        var result = [];
        frames.forEach(function(f) { result.push(f.src.substring(0, 100)); });
        return result;
    }""")
    print(f'Iframes: {iframes}')

    # Select options using page.select_option (Playwright native)
    page.select_option('select[name="tiposDocumentoSelect"]', '1;4')
    time.sleep(0.5)
    page.select_option('select[name="distritosCESelect"]', '11')
    time.sleep(3)
    page.select_option('select[name="concelhosCESelect"]', '6')
    time.sleep(2)

    # Try clicking the submit button and wait for network response
    print('Submitting...')
    with page.expect_response(lambda r: 'functions.php' in r.url, timeout=15000) as resp_info:
        page.click('input[name="submeter"]')

    response = resp_info.value
    body = response.body().decode('utf-8', errors='replace')
    print(f'Response status: {response.status}')
    print(f'Response length: {len(body)}')

    # Parse the response
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, 'html.parser')

    match = re.search(r'Resultados encontrados:\s*([\d.]+)', body)
    if match:
        print(f'Results: {match.group(1)}')

    error = soup.find('span', class_='search-captcha-error')
    if error:
        print(f'Error: {error.text}')

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
            print(popup.get_text(separator='\n')[:800])

        sce_divs = [d.get('id') for d in soup.find_all('div') if d.get('id', '').startswith('div_SCE')]
        print(f'\nSCE popup divs: {len(sce_divs)}')

    browser.close()
