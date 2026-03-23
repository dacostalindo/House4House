"""Test SCE: stealth Playwright to bypass Turnstile automation detection."""
from playwright.sync_api import sync_playwright
import json
import re
import time

STEALTH_JS = """
// Override navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Override chrome automation indicators
window.chrome = {runtime: {}};

// Override permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({state: Notification.permission}) :
        originalQuery(parameters)
);

// Override plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Override languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['pt-PT', 'pt', 'en-US', 'en'],
});
"""

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage',
        ],
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='pt-PT',
        timezone_id='Europe/Lisbon',
    )
    # Inject stealth script before any page loads
    context.add_init_script(STEALTH_JS)

    page = context.new_page()

    # Track AJAX responses
    ajax_responses = []
    def handle_response(response):
        if 'functions.php' in response.url:
            try:
                body = response.body().decode('utf-8', errors='replace')
                ajax_responses.append({'status': response.status, 'length': len(body), 'body': body})
            except Exception as ex:
                ajax_responses.append({'error': str(ex)})
    page.on('response', handle_response)

    page.goto('https://www.sce.pt/pesquisa-certificados/', timeout=30000)
    print('Page loaded')
    time.sleep(5)

    # Verify stealth
    wd = page.evaluate('() => navigator.webdriver')
    print(f'navigator.webdriver = {wd}')

    # Set form values
    page.select_option('select[name="tiposDocumentoSelect"]', '1;4')
    time.sleep(0.5)
    page.select_option('select[name="distritosCESelect"]', '11')
    time.sleep(3)
    page.select_option('select[name="concelhosCESelect"]', '6')
    time.sleep(2)

    # Submit
    print('Triggering form submit...')
    page.evaluate("""() => {
        NOVA_PESQUISA = true;
        jQuery("#numeroPaginaCE").val(0);
        jQuery('#frm_pesquisaCE').submit();
    }""")

    print('Waiting for Turnstile + AJAX...')
    max_wait = 60
    start = time.time()
    while time.time() - start < max_wait:
        if ajax_responses:
            print(f'Got AJAX response after {time.time() - start:.1f}s!')
            break

        # Check Turnstile state
        ts_state = page.evaluate("""() => {
            var container = document.querySelector('#captcha-container-ce');
            if (!container) return 'no-container';
            var resp = container.querySelector('[name="cf-turnstile-response"]');
            if (resp && resp.value.length > 0) return 'solved:' + resp.value.length;
            var iframe = container.querySelector('iframe');
            if (iframe) return 'iframe-present';
            return 'waiting';
        }""")
        elapsed = time.time() - start
        if elapsed % 10 < 2:
            print(f'  {elapsed:.0f}s: {ts_state}')
        time.sleep(2)
    else:
        print(f'Timed out after {max_wait}s')
        ts_state = page.evaluate("""() => {
            var container = document.querySelector('#captcha-container-ce');
            if (!container) return 'no-container';
            return container.innerHTML.substring(0, 300);
        }""")
        print(f'Final state: {ts_state}')

    if ajax_responses:
        resp = ajax_responses[0]
        from bs4 import BeautifulSoup
        body = resp['body']
        soup = BeautifulSoup(body, 'html.parser')

        error = soup.find('span', class_='search-captcha-error')
        if error:
            print(f'Error: {error.text}')

        match = re.search(r'Resultados encontrados:\s*([\d.]+)', body)
        if match:
            print(f'\nResults found: {match.group(1)}')

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

        if rows:
            doc = rows[0]['doc_number']
            popup = soup.find('div', {'id': f'div_{doc}'})
            if popup:
                print(f'\n=== Popup for {doc} ===')
                print(popup.get_text(separator='\n')[:1500])
            sce_divs = [d.get('id') for d in soup.find_all('div') if d.get('id', '').startswith('div_SCE')]
            print(f'\nSCE popup divs: {len(sce_divs)}')

        with open('/tmp/sce_ajax_response.html', 'w') as f:
            f.write(body)
        print('\nFull response saved to /tmp/sce_ajax_response.html')

    browser.close()
