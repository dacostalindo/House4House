"""Test SCE: investigate Turnstile and form JS handlers."""
from playwright.sync_api import sync_playwright
import json
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    # Enable console logging
    page.on('console', lambda msg: print(f'[CONSOLE] {msg.type}: {msg.text}') if 'turnstile' in msg.text.lower() or 'captcha' in msg.text.lower() or 'error' in msg.text.lower() else None)

    page.goto('https://www.sce.pt/pesquisa-certificados/', timeout=30000)
    print('Page loaded, waiting 15s for Turnstile to initialize...')
    time.sleep(15)

    # Deep dive into Turnstile state
    turnstile_state = page.evaluate("""() => {
        var result = {};

        // Check turnstile object
        try { result.turnstileExists = typeof turnstile !== 'undefined'; } catch(e) { result.turnstileExists = false; }
        try { result.turnstileRender = typeof turnstile !== 'undefined' && typeof turnstile.render !== 'undefined'; } catch(e) {}

        // Check for turnstile div with data attributes
        var tsDiv = document.querySelector('.cf-turnstile');
        if (tsDiv) {
            result.turnstileDiv = true;
            result.siteKey = tsDiv.getAttribute('data-sitekey');
            result.theme = tsDiv.getAttribute('data-theme');
            result.size = tsDiv.getAttribute('data-size');
            result.callback = tsDiv.getAttribute('data-callback');
            result.innerHTML = tsDiv.innerHTML.substring(0, 200);
        } else {
            result.turnstileDiv = false;
            // Check all divs with cf- or turnstile class
            var cfDivs = document.querySelectorAll('[class*="cf-"], [class*="turnstile"], [id*="turnstile"]');
            result.cfDivCount = cfDivs.length;
            var cfDivInfo = [];
            cfDivs.forEach(function(d) {
                cfDivInfo.push({id: d.id, className: d.className, tag: d.tagName});
            });
            result.cfDivs = cfDivInfo;
        }

        // Check for turnstile response token
        var tokenInput = document.querySelector('[name="cf-turnstile-response"]');
        result.hasToken = tokenInput !== null;
        if (tokenInput) {
            result.tokenLength = tokenInput.value.length;
        }

        // Check all hidden inputs for any token-like values
        var hiddens = document.querySelectorAll('input[type="hidden"]');
        var hiddenInfo = [];
        hiddens.forEach(function(h) {
            hiddenInfo.push({name: h.name, valueLen: h.value.length, valuePreview: h.value.substring(0, 60)});
        });
        result.hiddenInputs = hiddenInfo;

        // Check form onsubmit
        var form = document.querySelector('#frm_pesquisaCE');
        if (form) {
            result.formOnsubmit = form.getAttribute('onsubmit');
            // Check for event listeners (can't enumerate but check common patterns)
            result.formAction = form.action;
        }

        // Check for any jQuery form submit handlers
        try {
            if (typeof jQuery !== 'undefined') {
                var events = jQuery._data(jQuery('#frm_pesquisaCE')[0], 'events');
                if (events && events.submit) {
                    result.jquerySubmitHandlers = events.submit.length;
                }
            }
        } catch(e) {
            result.jqueryEventsError = e.message;
        }

        return result;
    }""")
    print(f'\nTurnstile state: {json.dumps(turnstile_state, indent=2)}')

    # Check the SCE plugin JS source for form handling logic
    sce_js = page.evaluate("""() => {
        var scripts = document.querySelectorAll('script');
        var inlineScripts = [];
        scripts.forEach(function(s) {
            if (!s.src && s.textContent.length > 50) {
                var text = s.textContent;
                if (text.indexOf('pesquisa') > -1 || text.indexOf('submeter') > -1 ||
                    text.indexOf('turnstile') > -1 || text.indexOf('frm_pesquisa') > -1) {
                    inlineScripts.push(text.substring(0, 2000));
                }
            }
        });
        return inlineScripts;
    }""")
    print(f'\nRelevant inline scripts: {len(sce_js)}')
    for i, js in enumerate(sce_js):
        print(f'\n--- Script {i+1} ---')
        print(js[:2000])

    # Also fetch the main plugin JS file
    plugin_scripts = page.evaluate("""() => {
        var scripts = document.querySelectorAll('script[src]');
        var pluginSrcs = [];
        scripts.forEach(function(s) {
            if (s.src.indexOf('sce-pesquisa') > -1 && s.src.indexOf('jquery') === -1 && s.src.indexOf('fancybox') === -1) {
                pluginSrcs.push(s.src);
            }
        });
        return pluginSrcs;
    }""")
    print(f'\nPlugin scripts: {json.dumps(plugin_scripts, indent=2)}')

    # Try to find the formDataStrCE hidden input purpose
    form_data_str = page.evaluate("""() => {
        var el = document.querySelector('[name="formDataStrCE"]');
        if (el) return {value: el.value, type: el.type, id: el.id};
        return null;
    }""")
    print(f'\nformDataStrCE: {json.dumps(form_data_str, indent=2)}')

    # Wait a bit more and check if Turnstile appears after interaction
    page.select_option('select[name="tiposDocumentoSelect"]', '1;4')
    time.sleep(1)
    page.select_option('select[name="distritosCESelect"]', '11')
    time.sleep(3)

    # Check again after interaction
    post_interaction = page.evaluate("""() => {
        var tsDiv = document.querySelector('.cf-turnstile');
        var token = document.querySelector('[name="cf-turnstile-response"]');
        var formDataStr = document.querySelector('[name="formDataStrCE"]');
        return {
            turnstileDiv: tsDiv !== null,
            hasToken: token !== null,
            tokenLen: token ? token.value.length : 0,
            formDataStr: formDataStr ? formDataStr.value.substring(0, 200) : null
        };
    }""")
    print(f'\nAfter interaction: {json.dumps(post_interaction, indent=2)}')

    browser.close()
