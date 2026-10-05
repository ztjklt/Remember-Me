"""Exercise the browser lock/compare/capture loop against fixture APIs."""
import json
import os
from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=os.getenv("REMEMBER_CHROMIUM_PATH"))
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://localhost:8001/debug/agent/")
    page.locator("#connect").click()
    page.wait_for_function("() => document.querySelector('#mode').textContent.includes('离线测试')")
    page.locator("#refresh").click()
    page.wait_for_function("() => document.querySelector('#model').textContent.includes('trait_id')")
    assert not page.locator("#human-panel").is_visible()
    page.locator("#question").fill("工作日下班后喜欢怎么度过？")
    page.locator("#ask").click()
    page.wait_for_function("() => document.querySelector('#answer').textContent.includes('response_type')")
    answer = json.loads(page.locator("#answer").inner_text())
    assert answer["evidence"]
    page.locator("#lock").click()
    page.locator("#human-panel").wait_for(state="visible")
    locked = json.loads(page.locator("#calibration").inner_text())
    assert locked["state"] == "LOCKED" and locked["comparison"] is None
    assert not page.locator("#human-answer").input_value()
    lock_id = page.locator("#lock-id").input_value()
    page.reload()
    page.locator("#connect").click()
    page.wait_for_function("() => document.querySelector('#mode').textContent.includes('离线测试')")
    page.locator("#lock-id").fill(lock_id)
    page.locator("#recover").click()
    page.locator("#human-panel").wait_for(state="visible")
    restored = json.loads(page.locator("#calibration").inner_text())
    assert restored["lock_digest"] == locked["lock_digest"]
    page.locator("#human-answer").fill("我现在喜欢先和家人聊聊天，再自己待一会儿。")
    page.locator("#submit").click()
    page.wait_for_function("() => document.querySelector('#calibration').textContent.includes('COMPLETED')")
    completed = json.loads(page.locator("#calibration").inner_text())
    assert len(completed["comparison"]["dimension_diffs"]) == 5
    assert completed["locked_answer"] == locked["locked_answer"]
    assert completed["resulting_revision"] == locked["locked_answer"]["revision"] + 1
    page.locator("#next").click()
    page.wait_for_function("() => document.querySelector('#plan').textContent.includes('target_domain')")
    page.locator("#revoke").click()
    page.wait_for_function("() => document.querySelector('#status').textContent.includes('同意已撤回')")
    assert not page.locator("#human-panel").is_visible()
    assert "evidence_ids" not in page.locator("#answer").inner_text()
    assert "trait_id" not in page.locator("#model").inner_text()
    assert not errors, errors
    browser.close()
print("Browser Twin, lock-before-answer, lock recovery, five-dimension comparison and revocation passed.")
