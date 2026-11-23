"""Exercise the release in Chromium and capture the screens that passed."""
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright

root = Path(sys.argv[1]).resolve()
evidence = root / "verification"
evidence.mkdir(exist_ok=True)
server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}/"
checks = []
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    with page.expect_response(lambda r: "/data/prices.json" in r.url) as response:
        page.goto(url)
    feed = response.value.json()
    assert response.value.ok and feed["schema"] == "canbuild-live.v1"
    page.wait_for_function("!document.querySelector('#syncBadge').textContent.includes('Loading')")
    assert page.locator("html").get_attribute("lang") == "en-CA"
    assert not re.search(r"[\u3400-\u9fff]", page.locator("body").inner_text())
    checks.append("The English dashboard loads the published price feed.")
    page.screenshot(path=evidence / "desktop.png")
    page.select_option("#gpu", "super")
    page.fill("#overrideGPU", "1000")
    page.fill("#budget", "3000")
    prices = [Decimal(t.replace("$","").replace(",","")) for t in page.locator("#partsBody .price").all_inner_texts()]
    subtotal = sum(prices)
    def display(value):
        return f"${value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
    assert page.inner_text("#subtotal") == display(subtotal)
    assert page.inner_text("#tax") == display(subtotal * Decimal("0.13"))
    assert page.inner_text("#total") == display(subtotal * Decimal("1.13"))
    checks.append("A manual CAD 1,000 GPU quote produces the expected subtotal, Ontario HST and total.")
    page.locator("#builder").screenshot(path=evidence / "budget.png")
    page.fill("#overrideGPU", "")
    assert page.inner_text("#total") == "—"
    page.click("#resetBtn")
    assert page.input_value("#gpu") == "best5070"
    checks.append("A missing manual quote suppresses the total. Reset restores the default GPU.")
    page.select_option("#series", "g4070")
    page.click('[data-days="30"]')
    assert page.locator("#historySource").get_attribute("href").startswith("https://")
    checks.append("The 30-day history view opens the source for the selected GPU.")
    with page.expect_download() as download:
        page.click("#exportBtn")
    exported = json.loads(Path(download.value.path()).read_text(encoding="utf8"))
    assert exported["schema"] == "canbuild.v1"
    exported["selection"]["budget"] = "4500"
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#importFile").set_input_files({"name":"snapshot.json","mimeType":"application/json","buffer":json.dumps(exported).encode()})
    page.wait_for_function("document.querySelector('#budget').value === '4500'")
    checks.append("A JSON export imports successfully and restores the selected budget.")
    with page.expect_response(lambda r: "/data/prices.json" in r.url) as reload:
        page.click("#syncBtn")
    assert reload.value.ok
    checks.append("Refresh downloads the price feed again.")
    page.set_viewport_size({"width":390,"height":844})
    page.goto(url, wait_until="networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=evidence / "mobile.png")
    assert not errors, errors
    checks.append("At 390 px the page fits the viewport. No uncaught JavaScript errors were observed.")
    browser.close()
server.shutdown()
(evidence / "checks.json").write_text(json.dumps({"passed": checks,"collection": feed.get("run_summary")},indent=2),encoding="utf8")
print("\n".join(checks))

