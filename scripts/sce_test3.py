"""Test SCE: investigate form submission mechanism."""
from playwright.sync_api import sync_playwright
import json
import re
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    # Track ALL network requests
    requests_log = []
    def handle_request(request):
        if 'sce.pt' in request.url:
            requests_log.append({
                'method': request.method,
                'url': request.url[:120],
                'post_data': (request.post_data or '')[:200],
            })
    page.on('request', handle_request)

    page.goto('https://www.sce.pt/pesquisa-certificados/', timeout=30000)
    print('Page loaded')
    time.sleep(5)

    # Check form action and method
    form_info = page.evaluate("""() => {
        var form = document.querySelector('#frm_pesquisaCE');
        if (!form) return {error: 'no form found', forms: document.querySelectorAll('form').length};
        return {
            action: form.action,
            method: form.method,
            id: form.id,
            enctype: form.enctype,
            target: form.target,
            inputs: Array.from(form.elements).map(e => ({
                name: e.name, type: e.type, tagName: e.tagName, value: e.value.substring(0, 50)
            })).filter(e => e.name)
        };
    }""")
    print(f'\nForm info: {json.dumps(form_info, indent=2)}')

    # Check for any turnstile or captcha elements
    captcha_info = page.evaluate("""() => {
        return {
            turnstile: document.querySelector('.cf-turnstile') !== null,
            turnstileResponse: document.querySelector('[name="cf-turnstile-response"]') !== null,
            captchaInput: document.querySelector('[name="captchaInput"]') !== null,
            recaptcha: document.querySelector('.g-recaptcha') !== null,
            hiddenInputs: Array.from(document.querySelectorAll('input[type="hidden"]')).map(e => ({
                name: e.name, value: e.value.substring(0, 80)
            }))
        };
    }""")
    print(f'\nCaptcha info: {json.dumps(captcha_info, indent=2)}')

    # Check what scripts are loaded
    scripts = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('script[src]'))
            .map(s => s.src)
            .filter(s => s.includes('turnstile') || s.includes('cloudflare') || s.includes('captcha') || s.includes('sce-pesquisa'));
    }""")
    print(f'\nRelevant scripts: {json.dumps(scripts, indent=2)}')

    # Select form values
    page.select_option('select[name="tiposDocumentoSelect"]', '1;4')
    time.sleep(0.5)
    page.select_option('select[name="distritosCESelect"]', '11')
    time.sleep(3)
    page.select_option('select[name="concelhosCESelect"]', '6')
    time.sleep(2)

    # Clear request log before submit
    requests_log.clear()

    # Check the submit button - is it a regular submit or JS?
    submit_info = page.evaluate("""() => {
        var btn = document.querySelector('input[name="submeter"]');
        if (!btn) return {error: 'no submit button'};
        return {
            type: btn.type,
            value: btn.value,
            onclick: btn.getAttribute('onclick'),
            form: btn.form ? btn.form.id : null,
        };
    }""")
    print(f'\nSubmit button: {json.dumps(submit_info, indent=2)}')

    # Listen for navigation
    print('\nSubmitting and waiting for navigation...')
    try:
        with page.expect_navigation(timeout=30000):
            page.click('input[name="submeter"]')
        print('Navigation completed!')
    except Exception as e:
        print(f'Navigation error: {e}')
        # Maybe it's AJAX - wait and check
        time.sleep(8)

    print(f'\nRequests after submit: {len(requests_log)}')
    for r in requests_log[:10]:
        print(json.dumps(r, indent=2, ensure_ascii=False))

    # Parse the current page content
    content = page.content()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, 'html.parser')

    # Check for results
    match = re.search(r'Resultados encontrados:\s*([\d.]+)', content)
    if match:
        print(f'\nResults found: {match.group(1)}')

    error = soup.find('span', class_='search-captcha-error')
    if error:
        print(f'\nCaptcha error: {error.text}')

    # Check for result table
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
            print(popup.get_text(separator='\n')[:1000])

        sce_divs = [d.get('id') for d in soup.find_all('div') if d.get('id', '').startswith('div_SCE')]
        print(f'\nSCE popup divs: {len(sce_divs)}')
        if sce_divs:
            print(f'First few: {sce_divs[:3]}')

    # Also save full page HTML for analysis
    with open('/tmp/sce_response.html', 'w') as f:
        f.write(content)
    print('\nFull page saved to /tmp/sce_response.html')

    browser.close()
