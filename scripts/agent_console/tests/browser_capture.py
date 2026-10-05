"""Run against --serve --mode fixture on ports 8001/8101/8201."""
import os
from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=os.getenv("REMEMBER_CHROMIUM_PATH"),
        args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
    page = browser.new_page(permissions=["microphone"])
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://localhost:8001/debug/agent/")
    page.locator("#connect").click()
    page.wait_for_function("() => document.querySelector('#mode').textContent.includes('离线测试')")
    page.locator("#devices").click()
    page.wait_for_function("() => document.querySelector('#microphone').options.length > 1")
    page.locator("#record").click()
    page.wait_for_function("() => !document.querySelector('#stop').disabled")
    page.wait_for_timeout(1400)
    page.locator("#stop").click()
    page.wait_for_function("() => document.querySelector('#preview').src.startsWith('blob:')")
    page.locator("#upload").click()
    page.wait_for_function("() => document.querySelector('#status').dataset.error === 'true'")
    assert "同意" in page.locator("#status").inner_text()
    assert not page.locator("#episode").input_value()
    page.locator("#recording-consent").check()
    page.locator("#cloud-consent").check()
    page.locator("#upload").click()
    page.wait_for_function("() => document.querySelector('#model').textContent.includes('trait_id')", timeout=45000)
    episode = page.locator("#episode").input_value()
    assert episode and "fixture-ai" in page.locator("#memories").inner_text()
    page.locator("#upload").click()
    page.wait_for_function("() => !document.querySelector('#upload').disabled", timeout=45000)
    assert page.locator("#episode").input_value() == episode
    page.locator("summary").click()
    page.locator("#subject").fill("different-subject")
    assert not page.locator("#episode").input_value()
    assert not page.locator("#preview").get_attribute("src")
    assert "trait_id" not in page.locator("#model").inner_text()
    assert not errors, errors
    browser.close()
print("Browser capture, consent gate, async processing, idempotency and session isolation passed.")
