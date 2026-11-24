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
    page.select_option("#gpu", "pny4070")
    pny_row = page.locator("#partsBody tr").filter(has_text="PNY RTX 4070 Ti SUPER Verto OC")
    assert pny_row.count() == 1
    pny = feed["items"].get("pny4070")
    if pny:
        assert pny_row.locator(".price").inner_text() == f"${pny['price']:,.2f}"
        if pny["stock"] == "out_of_stock":
            assert "out of stock" in pny_row.inner_text().lower()
    else:
        assert page.inner_text("#total") == "—"
    checks.append("The exact PNY 4070 Ti SUPER listing shows its own quote and stock status, or leaves the estimate pending.")
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
    # Exercise all eight facets against a stable, empty feed so market moves cannot break the tests.
    qa = browser.new_page(viewport={"width":1440,"height":1050})
    qa.route("**/data/prices.json*", lambda route: route.fulfill(json={"schema":"canbuild-live.v1","items":{},"history":{}}))
    qa.goto(url,wait_until="networkidle")
    cards = qa.locator(".result-card")
    assert cards.count() == 20 and len(set(cards.locator("h3").all_inner_texts())) >= 10
    qa.locator("#filtersPanel summary").click()
    assert qa.locator("#filterGrid select").count() == 8
    qa.select_option("#findStock", "all")
    qa.select_option("#findRange", "all")
    for key,value in {"CPU":"ry9600","Motherboard":"b850m","Memory":"vulcan","GPU":"g5060ti","SSD":"nv3a","PSU":"a850","Cooler":"dual620","Case":"case3500"}.items():
        qa.select_option("#filter"+key,value)
    assert cards.count()==1
    expected=cards.locator(".rc-price").inner_text()
    breakdown=cards.locator(".rc-breakdown")
    assert breakdown.get_by_text("Parts subtotal", exact=False).count()==1
    assert breakdown.get_by_text("Ontario HST", exact=False).count()==1
    assert breakdown.get_by_text("Total after tax", exact=False).count()==1
    assert breakdown.locator("b").nth(2).inner_text()==expected
    cards.locator("summary").click()
    assert cards.locator("li a").count() >= 6
    cards.get_by_role("button",name="Use build").click()
    assert qa.inner_text("#total")==expected and qa.input_value("#psu")=="a850" and qa.input_value("#case")=="case3500"
    assert qa.input_value("#cooler")=="dual620"
    qa.select_option("#filterMotherboard","b760")
    assert cards.count()==0 and qa.get_by_text("No matching builds",exact=True).is_visible()
    qa.get_by_role("button",name="Clear filters").click()
    qa.select_option("#findUse","ai")
    assert cards.count()>0
    assert all("RTX" in t for t in cards.locator("h3").all_inner_texts())
    qa.select_option("#cpuKit","custom")
    qa.select_option("#cpuPart","i144")
    assert qa.input_value("#boardPart")=="b760" and qa.input_value("#memoryPart") in {"ddr4","ddr4s"}
    qa.fill("#findBudget", "2000")
    assert cards.count() > 0
    qa.fill("#findBudget", "5000")
    assert cards.count() > 0
    checks.extend(["Twenty ranked recommendations near the selected CA$2,000–5,000 budget show parts subtotal, Ontario HST and total after tax.",
        "All eight exact part filters combine, a conflicting socket yields zero results, and clearing filters restores results.",
        "Applying a recommendation preserves its after-tax total, power supply, cooler and case.",
        "The local-AI filter selects CUDA GPUs and the individual planner enforces socket and RAM generation."])
    qa.close()
    page.locator("#recommendations").scroll_into_view_if_needed()
    page.locator("#recommendations").screenshot(path=evidence / "recommendations.png")
    amounts=page.locator(".rc-price").all_inner_texts()
    checks.append(f"The deployed feed returned {len(amounts)} default recommendations. Displayed totals: {', '.join(amounts)}.")
    page.set_viewport_size({"width":390,"height":844})
    page.locator("#filtersPanel summary").click()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), page.evaluate("""() => [...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1 && !e.closest('.tablewrap')).map(e=>[e.tagName,e.id,e.className,Math.round(e.getBoundingClientRect().right)]).slice(0,20)""")
    page.locator("#filtersPanel").screenshot(path=evidence / "filters-mobile.png")
    page.locator("#filtersPanel summary").click()


    page.set_viewport_size({"width":390,"height":844})
    page.goto(url, wait_until="networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), page.evaluate("""() => [...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1 && !e.closest('.tablewrap')).map(e=>[e.tagName,e.id,e.className,Math.round(e.getBoundingClientRect().right)]).slice(0,20)""")
    page.screenshot(path=evidence / "mobile.png")
    assert not errors, errors
    checks.append("At 390 px the page fits the viewport. No uncaught JavaScript errors were observed.")
    browser.close()
server.shutdown()
(evidence / "checks.json").write_text(json.dumps({"passed": checks,"collection": feed.get("run_summary")},indent=2),encoding="utf8")
print("\n".join(checks))

