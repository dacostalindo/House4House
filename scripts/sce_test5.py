"""Test SCE: extract full form JS handler and try submitting."""
from playwright.sync_api import sync_playwright
import json
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto('https://www.sce.pt/pesquisa-certificados/', timeout=30000)
    print('Page loaded')
    time.sleep(5)

    # Get the FULL inline script that contains pesquisa/submeter
    full_scripts = page.evaluate("""() => {
        var scripts = document.querySelectorAll('script');
        var result = [];
        scripts.forEach(function(s) {
            if (!s.src && s.textContent.length > 50) {
                var text = s.textContent;
                if (text.indexOf('submeter') > -1 || text.indexOf('frm_pesquisa') > -1 ||
                    text.indexOf('formDataStr') > -1) {
                    result.push(text);
                }
            }
        });
        return result;
    }""")

    for i, js in enumerate(full_scripts):
        print(f'\n=== Full Script {i+1} ({len(js)} chars) ===')
        print(js)

    browser.close()
