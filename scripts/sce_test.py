"""Quick test of SCE portal with Playwright to capture actual data."""
from playwright.sync_api import sync_playwright
import json
import re
import time

JS_CHECK = """() => {
    var result = {};
    result.turnstileDiv = document.querySelector('.cf-turnstile') ? true : false;
    var scripts = [];
    document.querySelectorAll('script').forEach(function(s) {
        var src = s.getAttribute('src') || '';
        if (src.indexOf('turnstile') > -1 || src.indexOf('cloudflare') > -1) {
            scripts.push(src);
        }
    });
    result.cfScripts = scripts;
    try { result.hasTurnstileObj = typeof turnstile !== 'undefined'; } catch(e) { result.hasTurnstileObj = false; }
    return result;
}"""

JS_GET_FORM_DATA = """() => {
    var result = {};
    var form = document.querySelector('#frm_pesquisaCE');
    if (!form) return {error: 'no form'};
    result.action = form.action;
    result.method = form.method;
    var formData = new FormData(form);
    var entries = {};
    formData.forEach(function(v, k) { entries[k] = v.substring(0, 80); });
    result.formEntries = entries;
    return result;
}"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Intercept responses
    responses_data = []
    def handle_response(response):
        if 'functions.php' in response.url:
            try:
                body = response.body()
                responses_data.append({
                    'status': response.status,
                    'length': len(body),
                    'preview': body[:500].decode('utf-8', errors='replace'),
                })
            except Exception as ex:
                responses_data.append({'error': str(ex)})
    page.on('response', handle_response)

    page.goto('https://www.sce.pt/pesquisa-certificados/', timeout=30000)
    print('Page loaded')
    time.sleep(5)

    # Check turnstile setup
    check = page.evaluate(JS_CHECK)
    print(f'Turnstile check: {json.dumps(check, indent=2)}')

    # Wait longer for Turnstile to solve
    print('Waiting 15s for Turnstile...')
    time.sleep(15)

    # Set form values using JS to ensure onChange handlers fire
    page.evaluate("""() => {
        var sel = document.querySelector('select[name="tiposDocumentoSelect"]');
        sel.value = '1;4';
        sel.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    time.sleep(1)

    page.evaluate("""() => {
        var sel = document.querySelector('select[name="distritosCESelect"]');
        sel.value = '11';
        sel.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    time.sleep(3)

    # Check what concelhos loaded
    concelhos = page.evaluate("""() => {
        var sel = document.querySelector('select[name="concelhosCESelect"]');
        if (!sel) return [];
        var opts = [];
        for (var i = 0; i < sel.options.length; i++) {
            opts.push({value: sel.options[i].value, text: sel.options[i].text});
        }
        return opts;
    }""")
    print(f'\nConcelhos loaded: {len(concelhos)}')
    for c in concelhos[:5]:
        print(f'  {c["value"]}: {c["text"]}')

    # Select Lisboa concelho
    if len(concelhos) > 1:
        page.evaluate("""() => {
            var sel = document.querySelector('select[name="concelhosCESelect"]');
            sel.value = '6';
            sel.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        time.sleep(2)

    # Get form data before submit
    form_data = page.evaluate(JS_GET_FORM_DATA)
    print(f'\nForm data: {json.dumps(form_data, indent=2)}')

    # Submit via JS click
    page.evaluate("""() => {
        var btn = document.querySelector('input[name="submeter"]');
        btn.click();
    }""")
    time.sleep(8)

    print(f'\nNetwork responses: {len(responses_data)}')
    for r in responses_data:
        print(json.dumps(r, indent=2, ensure_ascii=False))

    # Parse final page
    content = page.content()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, 'html.parser')

    match = re.search(r'Resultados encontrados:\s*([\d.]+)', content)
    if match:
        print(f'\nResults: {match.group(1)}')

    error = soup.find('span', class_='search-captcha-error')
    if error:
        print(f'Error: {error.text}')

    rows = []
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td')
        if len(cells) >= 6:
            link = cells[0].find('a')
            if link and link.text.strip().startswith('SCE'):
                row = {
                    'doc_number': link.text.strip(),
                    'morada': cells[1].get_text(strip=True),
                    'fracao': cells[2].get_text(strip=True),
                    'localidade': cells[3].get_text(strip=True),
                    'concelho': cells[4].get_text(strip=True),
                    'estado': cells[5].get_text(strip=True),
                    'doc_substituto': cells[6].get_text(strip=True) if len(cells) > 6 else '',
                }
                rows.append(row)

    print(f'\nTable rows: {len(rows)}')
    for r in rows[:5]:
        print(json.dumps(r, ensure_ascii=False, indent=2))

    # Also parse detail popups if available
    if rows:
        doc = rows[0]['doc_number']
        popup = soup.find('div', {'id': f'div_{doc}'})
        if popup:
            print(f'\nPopup for {doc}:')
            print(popup.get_text(separator='\n')[:600])
        else:
            # Find any divs with SCE IDs
            sce_divs = [d.get('id') for d in soup.find_all('div') if d.get('id', '').startswith('div_SCE')]
            print(f'\nSCE popup divs found: {len(sce_divs)}')
            if sce_divs:
                print(f'First few: {sce_divs[:3]}')

    browser.close()
