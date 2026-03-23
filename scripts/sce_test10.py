"""Test SCE: use nodriver (undetected Chrome) to bypass Turnstile."""
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

    # Check webdriver
    wd = await page.evaluate('navigator.webdriver')
    print(f'navigator.webdriver = {wd}')

    # Set form values using JS (nodriver doesn't have select_option)
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

    # Check concelhos loaded
    concelhos_count = await page.evaluate("""
        document.querySelector('select[name="concelhosCESelect"]').options.length
    """)
    print(f'Concelhos loaded: {concelhos_count}')

    await page.evaluate("""
        var sel = document.querySelector('select[name="concelhosCESelect"]');
        sel.value = '6';
        sel.dispatchEvent(new Event('change', {bubbles: true}));
    """)
    await asyncio.sleep(2)

    # Check jQuery
    has_jquery = await page.evaluate("typeof jQuery !== 'undefined'")
    print(f'jQuery available: {has_jquery}')

    # Check Turnstile
    has_turnstile = await page.evaluate("typeof turnstile !== 'undefined'")
    print(f'Turnstile available: {has_turnstile}')

    # Set up a listener for the AJAX response by monkey-patching XMLHttpRequest
    await page.evaluate("""
        window._sce_ajax_responses = [];
        var origXHROpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url) {
            this._sce_url = url;
            origXHROpen.apply(this, arguments);
        };
        var origXHRSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function() {
            var xhr = this;
            xhr.addEventListener('load', function() {
                var url = xhr._sce_url || xhr.responseURL || '';
                if (url.indexOf('functions.php') > -1) {
                    window._sce_ajax_responses.push({
                        status: xhr.status,
                        length: (xhr.responseText || '').length,
                        body: xhr.responseText || '',
                        url: url,
                        source: 'xhr-intercept'
                    });
                }
            });
            origXHRSend.apply(this, arguments);
        };

        // Also patch jQuery ajax
        if (typeof jQuery !== 'undefined') {
            jQuery(document).ajaxComplete(function(event, xhr, settings) {
                if (settings.url && settings.url.indexOf('functions.php') > -1) {
                    window._sce_ajax_responses.push({
                        status: xhr.status,
                        length: (xhr.responseText || '').length,
                        body: xhr.responseText || '',
                        url: settings.url
                    });
                }
            });
        }

        // Also patch the specific jQuery ajax success handler
        var origAjax = jQuery.ajax;
        jQuery.ajax = function(opts) {
            if (opts.url && opts.url.indexOf('functions.php') > -1) {
                var origSuccess = opts.success;
                opts.success = function(data) {
                    window._sce_ajax_responses.push({
                        status: 200,
                        length: (data || '').length,
                        body: data || '',
                        url: opts.url,
                        source: 'ajax-intercept'
                    });
                    if (origSuccess) origSuccess.apply(this, arguments);
                };
            }
            return origAjax.apply(this, arguments);
        };
    """)

    # Submit
    print('Triggering form submit...')
    await page.evaluate("""
        NOVA_PESQUISA = true;
        jQuery("#numeroPaginaCE").val(0);
        jQuery('#frm_pesquisaCE').submit();
    """)

    print('Waiting for Turnstile + AJAX...')
    max_wait = 60
    start = time.time()
    while time.time() - start < max_wait:
        responses = await page.evaluate("window._sce_ajax_responses")
        if responses and len(responses) > 0:
            print(f'Got AJAX response after {time.time() - start:.1f}s!')
            break

        ts_state = await page.evaluate("""
            (function() {
                var container = document.querySelector('#captcha-container-ce');
                if (!container) return 'no-container';
                var resp = container.querySelector('[name="cf-turnstile-response"]');
                if (resp && resp.value.length > 0) return 'solved:' + resp.value.length;
                var iframe = container.querySelector('iframe');
                if (iframe) return 'iframe-present';
                return 'children:' + container.children.length;
            })()
        """)
        elapsed = time.time() - start
        if int(elapsed) % 10 == 0:
            print(f'  {elapsed:.0f}s: {ts_state}')
        await asyncio.sleep(2)
    else:
        print(f'Timed out after {max_wait}s')

    responses = await page.evaluate("window._sce_ajax_responses")
    if responses and len(responses) > 0:
        body = responses[0]['body']
        print(f'Response status: {responses[0]["status"]}')
        print(f'Response length: {responses[0]["length"]}')

        from bs4 import BeautifulSoup
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

        # Parse detail popups
        if rows:
            doc = rows[0]['doc_number']
            popup = soup.find('div', {'id': f'div_{doc}'})
            if popup:
                print(f'\n=== Popup for {doc} ===')
                print(popup.get_text(separator='\n')[:1500])

            sce_divs = [d.get('id') for d in soup.find_all('div') if d.get('id', '').startswith('div_SCE')]
            print(f'\nSCE popup divs: {len(sce_divs)}')
            if sce_divs and not popup:
                first = soup.find('div', {'id': sce_divs[0]})
                if first:
                    print(f'\n=== First popup ===')
                    print(first.get_text(separator='\n')[:1500])

        with open('/tmp/sce_ajax_response.html', 'w') as f:
            f.write(body)
        print('\nResponse saved to /tmp/sce_ajax_response.html')
    else:
        final = await page.evaluate("""
            (function() {
                var container = document.querySelector('#captcha-container-ce');
                return container ? container.innerHTML.substring(0, 500) : 'no container';
            })()
        """)
        print(f'Final captcha state: {final}')

    browser.stop()


asyncio.run(main())
