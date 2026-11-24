#!/usr/bin/env python3
"""Build the large component catalogue used by the static CAN/BUILD site.

The crawler reads public Canada Computers category pages at a deliberately low
rate.  It never logs in, bypasses a challenge, or invents products.  When a
category cannot be refreshed, the last successful catalogue is retained.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data" / "catalog.json"
TARGET_PER_KIND = 100
MAX_PAGES = 16
REQUEST_DELAY = 2.0
NOW = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

SOURCES = {
    "GPU": "https://www.canadacomputers.com/en/914/graphics-cards",
    "SSD": "https://www.canadacomputers.com/en/1291/desktop-laptop-internal-ssds",
    "PSU": "https://www.canadacomputers.com/en/1346/power-supplies",
}

PRICE = re.compile(r"(?:CA\s*)?\$\s*([\d,]+(?:\.\d{2})?)", re.I)
PRODUCT_PATH = re.compile(r"/en/[^/?#]+/(\d+)/[^/?#]+\.html$", re.I)
BRANDS = (
    "ASUS", "GIGABYTE", "MSI", "SAPPHIRE", "XFX", "ASRock", "ZOTAC", "PNY",
    "PowerColor", "Intel", "NVIDIA", "WD", "Western Digital", "Samsung", "Kingston",
    "Lexar", "Crucial", "TeamGroup", "Corsair", "Seagate", "SanDisk", "Patriot",
    "ADATA", "MSI", "FSP", "Super Flower", "Thermaltake", "be quiet!", "DeepCool",
    "Cooler Master", "EVGA", "NZXT", "Seasonic", "AZZA", "Antec", "Lian Li",
)


def amount(raw: object) -> float | None:
    try:
        value = round(float(str(raw).replace(",", "").replace("$", "").strip()), 2)
    except (TypeError, ValueError):
        return None
    return value if 20 <= value <= 20000 else None


def page_url(base: str, page: int) -> str:
    split = urlsplit(base)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def fetch(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=(10, 30), headers={"Accept-Language": "en-CA,en;q=0.9"})
    response.raise_for_status()
    if len(response.content) < 2000 or len(response.content) > 8_000_000:
        raise ValueError("unexpected category page size")
    lower = response.text.lower()
    if "verify you are human" in lower or "just a moment..." in lower or "access denied" in lower[:8000]:
        raise ValueError("retailer challenge; no bypass attempted")
    return response.text


def jsonld_products(soup: BeautifulSoup, page: str) -> list[dict]:
    found: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            document = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        stack = document if isinstance(document, list) else [document]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            stack.extend(v for k, v in node.items() if k in {"@graph", "itemListElement", "item"})
            if "Product" not in str(node.get("@type", "")):
                continue
            offers = node.get("offers", {})
            offers = offers[0] if isinstance(offers, list) and offers else offers
            if not isinstance(offers, dict):
                offers = {}
            url = urljoin(page, str(node.get("url") or offers.get("url") or "")).split("?")[0]
            name = str(node.get("name") or "").strip()
            price = amount(offers.get("price") or offers.get("lowPrice"))
            availability = str(offers.get("availability") or "").lower()
            stock = "out_of_stock" if "outofstock" in availability else "in_stock" if "instock" in availability else "unknown"
            if PRODUCT_PATH.search(urlsplit(url).path) and name and price:
                found.append({"name": name, "url": url, "reference": price, "referenceStock": stock})
    return found


def closest_price_container(link) -> tuple[str, str] | None:
    node = link
    for _ in range(7):
        if node is None:
            break
        text = node.get_text(" ", strip=True)
        match = PRICE.search(text)
        if match and len(text) < 5000:
            return text, match.group(1)
        node = node.parent
    return None


def dom_products(soup: BeautifulSoup, page: str) -> list[dict]:
    candidates: dict[str, dict] = {}
    for link in soup.find_all("a", href=True):
        url = urljoin(page, link["href"]).split("?")[0]
        match = PRODUCT_PATH.search(urlsplit(url).path)
        if not match:
            continue
        name = (link.get("title") or link.get("aria-label") or link.get_text(" ", strip=True)).strip()
        nearby = closest_price_container(link)
        if not nearby:
            continue
        text, raw_price = nearby
        if len(name) < 8:
            heading = link.find_next(["h2", "h3", "h4", "a"])
            if heading:
                name = (heading.get("title") or heading.get_text(" ", strip=True)).strip()
        if len(name) < 8:
            continue
        price = amount(raw_price)
        if not price:
            continue
        stock = "out_of_stock" if re.search(r"online\s*[-–:]?\s*sold out|out of stock", text, re.I) else "in_stock" if re.search(r"add to cart|buy now|available to order", text, re.I) else "unknown"
        record = {"name": name, "url": url, "reference": price, "referenceStock": stock}
        previous = candidates.get(match.group(1))
        if not previous or len(name) > len(previous["name"]):
            candidates[match.group(1)] = record
    return list(candidates.values())


def brand_of(name: str) -> str:
    lowered = name.lower()
    for brand in sorted(BRANDS, key=len, reverse=True):
        if brand.lower() in lowered:
            return brand
    return name.split()[0].strip("®™")[:24] if name else "Other"


def capacity_tb(name: str) -> float:
    values = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*TB\b", name, re.I)]
    if values:
        return max(values)
    gb = [float(x) for x in re.findall(r"(\d{3,5})\s*GB\b", name, re.I)]
    return round(max(gb) / 1000, 3) if gb else 1.0


def gpu_family(name: str) -> str:
    patterns = [
        r"RTX\s*(\d{4})(?:\s*(Ti))?(?:\s*(SUPER))?",
        r"RX\s*(\d{4})(?:\s*(XT|XTX|GRE))?",
        r"Arc\s*([AB]\d{3})",
        r"GTX\s*(\d{4})(?:\s*(Ti))?",
    ]
    for pattern in patterns:
        match = re.search(pattern, name, re.I)
        if match:
            return " ".join(x.upper() for x in match.groups() if x)
    return "Other"


def specs(kind: str, name: str) -> list:
    if kind == "GPU":
        maker = "NVIDIA" if re.search(r"GeForce|RTX|GTX", name, re.I) else "AMD" if re.search(r"Radeon|\bRX\s*\d", name, re.I) else "Intel"
        memory = [int(x) for x in re.findall(r"(\d{1,2})\s*GB\b", name, re.I)]
        return [maker, max(memory) if memory else 8, gpu_family(name)]
    if kind == "SSD":
        generation = "Gen5" if re.search(r"PCIe\s*(?:Gen\s*)?5|5\.0", name, re.I) else "Gen4" if re.search(r"PCIe\s*(?:Gen\s*)?4|4\.0|4x4", name, re.I) else "SATA" if "SATA" in name.upper() else "Other"
        return [capacity_tb(name), generation]
    watts = [int(x) for x in re.findall(r"\b(\d{3,4})\s*W\b", name, re.I)]
    efficiency = "Platinum" if "platinum" in name.lower() else "Titanium" if "titanium" in name.lower() else "Gold" if "gold" in name.lower() else "Bronze" if "bronze" in name.lower() else "Unrated"
    return [max(watts) if watts else 650, efficiency]


def tier_of(kind: str, name: str, spec: list, price: float) -> str:
    if kind == "GPU":
        family = str(spec[2])
        number = int(re.search(r"\d{3,4}", family).group()) if re.search(r"\d{3,4}", family) else 0
        if number in {5080, 5090, 7900, 9070} or price >= 1400:
            return "high"
        if number in {5060, 5070, 7800, 7700, 9060} or price >= 650:
            return "mid"
        return "low"
    if kind == "SSD":
        if spec[1] == "Gen5" or spec[0] >= 4:
            return "high"
        if spec[1] == "Gen4" and spec[0] >= 1:
            return "mid"
        return "low"
    if spec[0] >= 1000 or spec[1] in {"Platinum", "Titanium"}:
        return "high"
    if spec[0] >= 750 and spec[1] == "Gold":
        return "mid"
    return "low"


def value_metric(kind: str, record: dict) -> float:
    spec, price = record["spec"], record["reference"]
    if kind == "SSD":
        return price / max(spec[0], .25)
    if kind == "PSU":
        quality = 1.12 if spec[1] in {"Platinum", "Titanium"} else 1.05 if spec[1] == "Gold" else 1
        return price / max(spec[0] * quality, 1)
    # Compare board-partner cards within the same GPU family. Lower is better.
    return price


def enrich(kind: str, records: list[dict]) -> dict[str, dict]:
    unique: dict[str, dict] = {}
    for record in records:
        match = PRODUCT_PATH.search(urlsplit(record["url"]).path)
        if not match or re.search(r"open[\s-]*box|refurbished|pre[\s-]*owned", record["name"], re.I):
            continue
        product_id = match.group(1)
        spec = specs(kind, record["name"])
        record.update(kind=kind, spec=spec, brand=brand_of(record["name"]), tier=tier_of(kind, record["name"], spec, record["reference"]), source="Canada Computers")
        record["metric"] = value_metric(kind, record)
        unique[product_id] = record
    rows = list(unique.items())
    if kind == "GPU":
        groups: dict[str, list[tuple[str, dict]]] = {}
        for item in rows:
            groups.setdefault(item[1]["spec"][2], []).append(item)
        picks = {min(items, key=lambda x: x[1]["metric"])[0] for family, items in groups.items() if family != "Other"}
    else:
        eligible = [x for x in rows if (kind != "SSD" or x[1]["spec"][0] >= 1) and (kind != "PSU" or x[1]["spec"][0] >= 750)]
        picks = {x[0] for x in sorted(eligible, key=lambda x: x[1]["metric"])[: max(10, len(eligible) // 7)]}
    metrics = sorted(x[1]["metric"] for x in rows)
    for product_id, record in rows:
        rank = metrics.index(record["metric"]) / max(len(metrics) - 1, 1)
        record["value"] = product_id in picks
        record["valueScore"] = max(1, min(99, round(100 - rank * 55 + (8 if record["value"] else 0))))
        record.pop("metric", None)
    return {f"cc_{kind.lower()}_{product_id}": record for product_id, record in rows}


def parse_category(html: str, kind: str, page: str) -> dict[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    merged = jsonld_products(soup, page) + dom_products(soup, page)
    return enrich(kind, merged)


def crawl_category(session: requests.Session, kind: str, base: str) -> dict[str, dict]:
    found: dict[str, dict] = {}
    stale_pages = 0
    for page in range(1, MAX_PAGES + 1):
        url = page_url(base, page)
        html = fetch(session, url)
        before = len(found)
        found.update(parse_category(html, kind, url))
        added = len(found) - before
        print(f"{kind} page {page}: +{added}, {len(found)} unique products")
        if len(found) >= TARGET_PER_KIND:
            break
        stale_pages = stale_pages + 1 if added == 0 else 0
        if stale_pages >= 2:
            break
        time.sleep(REQUEST_DELAY)
    if len(found) < TARGET_PER_KIND:
        raise ValueError(f"{kind} returned only {len(found)} unique products; keeping previous data")
    # Stable ordering keeps diffs and the browser predictable.
    return dict(sorted(found.items(), key=lambda x: (x[1]["reference"], x[1]["name"]))[:TARGET_PER_KIND])


def main() -> None:
    previous: dict = {}
    try:
        previous = json.loads(OUTPUT.read_text("utf-8"))
    except (OSError, ValueError):
        pass
    old_parts = previous.get("parts", {}) if isinstance(previous, dict) else {}
    session = requests.Session()
    session.headers.update({"User-Agent": "CANBUILD catalogue monitor/1.0 (scheduled; low request rate; no challenge bypass)"})
    all_parts: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for index, (kind, url) in enumerate(SOURCES.items()):
        try:
            all_parts.update(crawl_category(session, kind, url))
        except Exception as exc:
            retained = {key: value for key, value in old_parts.items() if value.get("kind") == kind}
            if len(retained) >= TARGET_PER_KIND:
                all_parts.update(dict(list(retained.items())[:TARGET_PER_KIND]))
                errors[kind] = f"{exc}; retained previous {len(retained)}"
            else:
                errors[kind] = str(exc)
            print(f"WARNING {kind}: {errors[kind]}")
        if index + 1 < len(SOURCES):
            time.sleep(REQUEST_DELAY)
    counts = {kind: sum(1 for item in all_parts.values() if item.get("kind") == kind) for kind in SOURCES}
    document = {
        "schema": "canbuild-catalog.v1",
        "generated_at": NOW,
        "target_per_kind": TARGET_PER_KIND,
        "counts": counts,
        "errors": errors,
        "sources": SOURCES,
        "parts": all_parts,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}: {counts}")
    if any(counts.get(kind, 0) < TARGET_PER_KIND for kind in SOURCES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
