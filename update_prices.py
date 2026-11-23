#!/usr/bin/env python3
"""Best-effort Canadian PC-part price snapshots, for GitHub Pages.

Prices are observations, *not* guaranteed checkout prices or live stock confirmations.
This monitor intentionally uses modest request rates and no auth/captcha evasion.
If the site cannot be read, it retains the previous observation and its timestamp.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'prices.json'
NOW = dt.datetime.now(dt.timezone.utc)
STAMP = NOW.isoformat(timespec='seconds').replace('+00:00', 'Z')
DAY = NOW.date().isoformat()

# A source can change or block automated requests; unsuccessful checks are flagged.
TRACKERS = {
    'cpu': 'https://pctechvault.com/market-watch/amd-ryzen-7-9800x3d/?market=new-retail&region=CA',
    'best5070': 'https://pctechvault.com/market-watch/geforce-rtx-5070-ti/?market=new-retail&region=CA',
    'best4070': 'https://pctechvault.com/market-watch/geforce-rtx-4070-ti-super/?market=new-retail&region=CA',
    'best9070': 'https://pctechvault.com/market-watch/amd-radeon-rx-9070-xt/?market=new-retail&region=CA',
    'ram': 'https://pctechvault.com/market-watch/gskill-trident-z5-neo-rgb-32-gb-ddr5-6000-cl30/?market=new-retail&region=CA',
    'rme': 'https://pctechvault.com/market-watch/corsair-rm850e/?market=new-retail&region=CA',
}
RETAIL = {
    'pny4070': ('DeployDepot', 'https://deploydepot.ca/products/pny-nvidia-geforce-rtx-4070-ti-super-graphic-card-16-gb-gddr6x-vcg4070ts16tfxpb1-o'),
    'kit': ('Canada Computers', 'https://www.canadacomputers.com/en/amd-desktop-processors/283326/amd-ryzen-7-9800x3d-cpu-asus-tuf-gaming-b850-e-wifi-motherboard-t-force-32gb-d5-6000mhz-cl30-ram.html'),
    'board': ('Canada Computers', 'https://www.canadacomputers.com/en/amd-motherboards/267132/gigabyte-b850-eagle-wifi6e-amd-am5-lga-1718-motherboard-atx-ddr5-b850-eagle-wifi6e.html'),
    'mlg': ('Memory Express', 'https://www.memoryexpress.com/Products/MX00135516'),
    'win': ('Canada Computers', 'https://www.canadacomputers.com/en/powered-by-nvidia/268823/gigabyte-geforce-rtx-5070-ti-windforce-oc-sff-16g-graphics-card-gv-n507twf3oc-16gd.html'),
    'nv3a': ('Canada Computers', 'https://www.canadacomputers.com/en/desktop-laptop-internal-ssds/261114/kingston-nv3-1tb-nvme-pcie-4x4-ssd-snv3s-1000g.html'),
    'nv3b': ('Canada Computers', 'https://www.canadacomputers.com/en/desktop-laptop-internal-ssds/261116/kingston-nv3-2tb-nvme-pcie-4x4-ssd-snv3s-2000g.html'),
    'sn850': ('Canada Computers', 'https://www.canadacomputers.com/en/desktop-laptop-internal-ssds/282003/wd-black-sn850x-2tb-pcie-gen4-nvme-m-2-ssd-wdbb9g0020bnc.html'),
    'air903': ('Modcom', 'https://www.modcom.ca/collections/case/products/montech-air-903-base-e-atx-mid-tower-case-high-airflow-with-max-capacity-3x-140mm-pwm-fans-pre-installed-tempered-glass-side-panel-mesh-front-type-c_black'),
}
RETAIL_HOSTS = ('canadacomputers.com', 'memoryexpress.com', 'newegg.ca', 'amazon.ca', 'bestbuy.ca', 'vuugo.com', 'modcom.ca')
CC = 'https://www.canadacomputers.com/en/'
DIRECT_ALTERNATIVES = {
    'cpu': ['amd-desktop-processors/264908/amd-ryzen-7-9800x3d-8-core-4nm-am5-104mb-cache-120w-zen-5-cpu-100-100001084wof.html'],
    'ram': ['desktop-memory/227127/g-skill-trident-z5-neo-rgb-32gb-2x16gb-ddr5-6000mhz-cl30-udimm-f5-6000j3038f16gx2-tz5nr.html'],
    'rme': ['power-supplies/266815/corsair-corsair-rm850e-850w-gold-atx-power-supply-black-cp-9020296-na.html'],
    'best5070': [
        'powered-by-nvidia/268906/msi-geforce-rtx-5070-ti-16g-ventus-3x-oc-rtx-5070-ti-16g-ventus-3x-oc.html',
        'powered-by-nvidia/290028/msi-geforce-rtx-5070-ti-16g-frieren-edition-oc-rtx-5070-ti-16g-frieren-edition-oc.html',
        'powered-by-nvidia/282429/msi-geforce-rtx-5070-ti-16g-ventus-3x-pz-16gb-gddr7-graphics-card-rtx-5070-ti-16g-ventus-3x-pz-oc.html',
    ],
    'best9070': [
        'powered-by-amd/269139/sapphire-pulse-amd-radeon-rx-9070-xt-16gb-gddr6-11348-03-20g.html',
        'powered-by-amd/268723/asrock-radeon-rx-9070-xt-taichi-16gb-rx9070xt-tc-16go-rx9070xt-tc-16go.html',
    ],
}
NEWEGG_4070 = 'https://www.newegg.ca/p/pl?N=100007708+601432392'
PRICE = re.compile(r'(?:CA\s*)?\$\s*([\d,]+(?:\.\d{2})?)', re.I)
CURRENCY = re.compile(r'CA\$\s*([\d,]+(?:\.\d{2})?)', re.I)


def extract_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).replace(',', '').strip()
    if s.startswith('$'): s = s[1:]
    if s.startswith('CA$'): s = s[3:]
    try:
        amount = round(float(s), 2)
    except (TypeError, ValueError):
        return None
    return amount if 20 <= amount <= 20000 else None


def text_lines(soup: BeautifulSoup) -> list[str]:
    for t in soup(['script','style','noscript']):
        t.decompose()
    return [s.strip() for s in soup.get_text('\n', strip=True).splitlines() if s.strip()]


def parse_tracker(html: str, page_url: str) -> dict:
    """Extract lowest currently tracked buyable *variant* from a component-family tracker.
    Never treat a GPU family price as a stable exact-card price.
    """
    soup = BeautifulSoup(html, 'html.parser')
    h = soup.find(lambda node: node.name in ['h1','h2','h3'] and node.get_text(' ', strip=True).lower() == 'where to buy now')
    if not h:
        raise ValueError('No "Where to buy now" section; listing may be unavailable')
    possible = []
    for node in h.next_elements:
        if getattr(node, 'name', None) in ('h1', 'h2') and node is not h:
            break
        if getattr(node, 'name', None) != 'li':
            continue
        text = node.get_text(' ', strip=True)
        m = CURRENCY.search(text)
        if not m:
            continue
        link = next((a for a in node.find_all('a', href=True)
                    if any(host in urlparse(urljoin(page_url, a['href'])).netloc for host in RETAIL_HOSTS)), None)
        if not link or re.search(r'\b(out of stock|sold out|unavailable)\b', text, re.I):
            continue
        shop = link.get_text(' ', strip=True)
        product_url = urljoin(page_url, link['href']) if link else page_url
        amount = extract_amount(m.group(1))
        if amount:
            description = text[m.end():].split('Part no.')[0].split(shop)[0].strip()
            possible.append((amount, shop, product_url, description[:155]))
    if not possible:
        # Fail closed rather than mislabel a historic / no-stock price as buyable.
        raise ValueError('No buyable variant rows in tracker')
    amount, shop, product_url, product = min(possible, key=lambda x: x[0])
    if not product:
        product = 'Lowest tracked variant'
    return {'price': amount, 'shop': shop, 'product': product,
            'url': product_url, 'track_url': page_url,
            'stock': 'tracker_in_stock', 'basis': 'lowest_in_stock_variant',
            'note': 'Lowest available variant reported by the tracker. Models may vary between dates. Confirm shipping at checkout.'}


def extract_jsonld_price(html_soup: BeautifulSoup) -> tuple[float | None, str]:
    for s in html_soup.find_all('script', type='application/ld+json'):
        try:
            val = json.loads(s.string or s.get_text())
        except (ValueError, TypeError):
            continue
        nodes = (val if isinstance(val, list) else [val])
        while nodes:
            el = nodes.pop()
            if not isinstance(el, dict):
                continue
            nodes.extend(el.get('@graph', []))
            if 'Product' not in str(el.get('@type','')):
                continue
            offers = el.get('offers', {})
            offers = offers[0] if isinstance(offers, list) and offers else offers
            if not isinstance(offers, dict):
                continue
            if str(offers.get('priceCurrency', 'CAD')).upper() != 'CAD':
                raise ValueError('Non-CAD offer')
            amt = extract_amount(offers.get('price') or offers.get('lowPrice'))
            if amt:
                availability = str(offers.get('availability') or '').lower()
                stock = 'in_stock' if 'instock' in availability else 'out_of_stock' if 'outofstock' in availability else 'unknown'
                return amt, stock
    return None, 'unknown'


def parse_retail(html: str, name: str, page_url: str) -> dict:
    raw_soup = BeautifulSoup(html, 'html.parser')
    if name == 'Modcom':
        marker = raw_soup.select_one('meta[property="og:price:currency"], meta[property="product:price:currency"]')
        currency = re.search(r'Shopify\.currency\s*=\s*\{[^}]*"active"\s*:\s*"([A-Z]{3})"', html)
        active_currency = currency.group(1) if currency else (marker.get('content') if marker else None)
        if active_currency != 'CAD':
            raise ValueError('Canadian-dollar storefront not confirmed')
    ld_price, stock = extract_jsonld_price(raw_soup)
    soup = BeautifulSoup(html, 'html.parser')
    lines = text_lines(soup)
    # The product title anchors the extraction to the product detail, not cart
    # recommendations, protections, ads, or other components in a bundle.
    title_el = soup.find('h1')
    title = title_el.get_text(' ', strip=True) if title_el else ''
    if re.search(r'\b(open[\s-]*box|refurbished|pre[\s-]*owned)\b', title, re.I):
        raise ValueError('Listing is not a new retail unit')
    if not title or len(title)<10:
        raise ValueError('Product title missing; refusing unsafe price extraction')
    idx = next((i for i,s in enumerate(lines) if s == title), -1)
    if idx<0:
        raise ValueError('Could not locate product title in page text')
    fragment = lines[max(idx,0):max(idx,0)+150]
    amount = ld_price
    if not amount:
        if name == 'Memory Express':
            for pos, line in enumerate(fragment):
                if re.fullmatch(r'Only', line, re.I) or re.match(r'^Only\s*\$', line, re.I):
                    m = PRICE.search(' '.join(fragment[pos:pos + 3]))
                    if m: amount = extract_amount(m.group(1));break
            # Protection prices appear before the listing price; never take the first dollar.
        else:
            # Select the first price after the title, but before optional bundles/components.
            stop_terms = ['This pack contains', 'Shop the collection', 'People also bought', 'Customers also purchased']
            for line in fragment[:75]:
                if any(t.lower() in line.lower() for t in stop_terms):
                    break
                m = re.fullmatch(r'(?:CA\s*)?\$\s*([\d,]+\.\d{2})', line)
                if m:
                    amount = extract_amount(m.group(1));break
    if not amount:
        raise ValueError(f'Could not isolate a valid product sale price ({name})')

    plain = ' '.join(lines)
    if name == 'Memory Express':
        # Online availability is authoritative for the online checkout expectation.
        m = re.search(r'Online Store:\s*(Out of Stock|In Stock|\d+ In Stock)', plain, re.I)
        if m:
            stock = 'out_of_stock' if 'out of stock' in m.group(1).lower() else 'in_stock'
        else:
            stock = 'unknown'
    elif name == 'Canada Computers':
        if re.search(r'Delivery\s+(?:Unavailable|Not Available|Sold out online)|Online\s+0\b', plain, re.I):
            stock = 'out_of_stock'
        elif re.search(r'\bAvailable to Ship\b|Online\s+[1-9]\d*\+|Online\s+(?:In Stock|Available)', plain, re.I):
            stock = 'in_stock'
        else:
            stock = 'unknown'
    elif name == 'Modcom':
        # In Shopify, ld+json stock is usually most reliable, else leave unknown.
        pass
    return {'price':amount, 'currency':'CAD', 'shop': name,'product':title[:160],
            'url':page_url,'track_url':page_url,'stock':stock,
            'basis':'exact_sku', 'note':'Retailer observation. Check current stock and local delivery on the product page.'}


def validate_result(record: dict) -> None:
    if not isinstance(record.get('price'), (float,int)) or not (20 <= record['price'] <= 20000):
        raise ValueError('Invalid price')
    link = record.get('url', '')
    if not link.startswith('https://'):
        raise ValueError('Invalid source link')


def add_observation(existing: dict, item: str, result: dict) -> None:
    result = {**result, 'checked_at': STAMP, 'date': DAY}
    existing.setdefault('items', {})[item] = result
    h = existing.setdefault('history', {}).setdefault(item, [])
    point = {'date': DAY, 'price': result['price'], 'url':result['url'], 'product':result.get('product','')}
    # At most one point per calendar day. Later same-day runs overwrite the final daily close.
    if h and h[-1].get('date') == DAY:
        h[-1] = point
    else:
        h.append(point)
    existing['history'][item] = h[-365:]


def fetch(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=(8, 18), headers={'Accept-Language':'en-CA,en;q=0.9'})
    response.raise_for_status()
    if len(response.content)<1500 or len(response.content)>6_000_000:
        raise ValueError('Unexpected page size')
    lower = response.text.lower()
    if 'verify you are human' in lower or 'just a moment...' in lower or 'access denied' in lower[:5000]:
        raise ValueError('Retailer bot-block / access denied; no retry bypass')
    return response.text


def newegg_4070(html: str) -> dict:
    offers = []
    soup = BeautifulSoup(html, 'html.parser')
    for card in soup.select('.item-cell'):
        title = card.select_one('a.item-title[href]')
        price = card.select_one('.price-current')
        if not title or not price:
            continue
        name = title.get_text(' ', strip=True)
        listing = card.get_text(' ', strip=True)
        if not re.search(r'4070\s*Ti\s*Super', name, re.I) or re.search(r'refurbished|open box|used|BTF|water block', name, re.I):
            continue
        if not re.search(r'add to cart', listing, re.I):
            continue
        amount_match = PRICE.search(price.get_text('', strip=True))
        amount = extract_amount(amount_match.group(1)) if amount_match else None
        link = urljoin(NEWEGG_4070, title['href'])
        if amount and urlparse(link).hostname in ('www.newegg.ca','newegg.ca'):
            offers.append({'price':amount, 'shop':'Newegg Canada marketplace', 'product':name, 'url':link,
                           'stock':'in_stock','currency':'CAD','track_url':NEWEGG_4070,'basis':'lowest_in_stock_variant'})
    if not offers:
        raise ValueError('No qualifying new, orderable Newegg.ca listing')
    return min(offers, key=lambda offer: offer['price'])


def observe(session, key, kind, item):
    if kind == 'retail':
        name, url = item
        if key == 'pny4070':
            response = session.get(url + '?country=CA&currency=CAD', timeout=(8,18))
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup.select('script[type="application/ld+json"]'):
                try:
                    doc = json.loads(script.string or script.get_text())
                except ValueError:
                    continue
                nodes = doc if isinstance(doc,list) else [doc]
                for node in nodes:
                    if not isinstance(node,dict):
                        continue
                    if '@graph' in node:
                        nodes.extend(node['@graph'])
                    if node.get('@type') != 'Product' or '4070 TI SUPER' not in str(node.get('name','')).upper():
                        continue
                    offers = node.get('offers', [])
                    for offer in (offers if isinstance(offers,list) else [offers]):
                        if offer.get('priceCurrency') != 'CAD':
                            continue
                        price = extract_amount(offer.get('price'))
                        availability = str(offer.get('availability','')).split('/')[-1].lower()
                        if price and availability in ('instock','outofstock','soldout'):
                            return {'price':price,'currency':'CAD','stock':'in_stock' if availability=='instock' else 'out_of_stock',
                                    'basis':'exact_sku','shop':name,'product':node['name'],'url':url,'track_url':url}
            raise ValueError('No matching CAD offer with confirmed stock status')
        if name == 'Modcom':
            url += '?country=CA&currency=CAD'
        return parse_retail(fetch(session, url), name, url)
    try:
        return parse_tracker(fetch(session, item), item)
    except (ValueError, OSError) as exc:
        print(f'{key}: primary source unavailable ({exc}); checking alternative listings')
    if key == 'best4070':
        return newegg_4070(fetch(session, NEWEGG_4070))
    candidates = []
    for path in DIRECT_ALTERNATIVES.get(key, []):
        url = CC + path
        time.sleep(2)
        try:
            record = parse_retail(fetch(session, url), 'Canada Computers', url)
        except (ValueError, OSError):
            continue
        if not key.startswith('best'):
            return record
        if record['stock'] == 'in_stock':
            record.update(basis='lowest_in_stock_variant', track_url=item)
            candidates.append(record)
    if not candidates:
        raise ValueError('No qualifying direct retailer quote')
    return min(candidates, key=lambda offer: offer['price'])


def main() -> None:
    import requests
    try:
        data = json.loads(DATA.read_text('utf-8'))
    except (OSError, ValueError):
        data = {'schema':'canbuild-live.v1','items':{},'history':{},'failures':{}}
    data.update(schema='canbuild-live.v1', last_run_at=STAMP)
    open_box_psu = '/power-supplies/270519/'
    if open_box_psu in data.get('items', {}).get('rme', {}).get('url', ''):
        del data['items']['rme']
    if 'rme' in data.get('history', {}):
        data['history']['rme'] = [p for p in data['history']['rme'] if open_box_psu not in p.get('url', '')]
    # The original Shopify check did not verify the storefront currency.
    legacy = data.get('items', {}).get('air903', {})
    if legacy and legacy.get('shop') == 'Modcom' and not legacy.get('currency'):
        data['history']['air903'] = [p for p in data['history'].get('air903', []) if p['date'] != legacy.get('date')]
        data['items'].pop('air903')
    session = requests.Session()
    session.headers.update({'User-Agent': 'CANBUILD personal hardware price watch/1.0 (scheduled; low request rate; no captcha bypass)'})
    errors = {}
    n_ok = 0
    targets = [(k,'tracker',v) for k,v in TRACKERS.items()] + [(k,'retail',v) for k,v in RETAIL.items()]
    only = {s.strip() for s in os.environ.get('CANBUILD_ONLY','').split(',') if s.strip()}
    for pos, (key, kind, item) in enumerate(targets):
        if only and key not in only:
            continue
        url = item if kind=='tracker' else item[1]
        try:
            result = observe(session, key, kind, item)
            validate_result(result)
            previous = data.get('items', {}).get(key)
            if previous:
                before, after = previous['price'], result['price']
                if before and (after / before < .35 or after / before > 2.8):
                    raise ValueError(f'Suspicious price jump {before} -> {after}; keeping earlier observation')
            add_observation(data,key,result)
            data.get('failures',{}).pop(key, None)
            n_ok += 1
            print(f'OK {key}: CA${result["price"]:.2f} ({result["stock"]})')
        except Exception as exc:
            error = str(exc)[:240]
            errors[key] = error
            data.setdefault('failures', {})[key] = {'last_failure_at':STAMP, 'reason':error}
            print(f'SKIP {key}: {error}')
        if pos + 1 < len(targets):
            time.sleep(float(os.environ.get('CANBUILD_REQUEST_DELAY','3.0')))
    # A confirmed retailer "out of stock" status overrides a generic tracker
    # report for the *same URL*. Never label a contradictory offer as buyable.
    best = data.get('items', {}).get('best5070')
    if best:
        for variant in ['mlg', 'win']:
            retail = data.get('items', {}).get(variant)
            if (retail and best.get('url', '').split('?')[0].rstrip('/') == retail.get('url', '').split('?')[0].rstrip('/')
                    and retail.get('stock') == 'out_of_stock'
                    and abs((dt.datetime.fromisoformat(best['checked_at'].replace('Z','+00:00'))
                            - dt.datetime.fromisoformat(retail['checked_at'].replace('Z','+00:00'))).total_seconds()) < 8 * 3600):
                best['stock'] = 'out_of_stock'
                best['note'] = 'The retailer reports this listing out of stock. It conflicts with the tracker observation.'
                print(f'WARNING best5070 conflicts with direct {variant} out-of-stock result')
                break
    data['last_successful_run_at'] = STAMP if n_ok else data.get('last_successful_run_at')
    data['run_summary'] = {'successful':n_ok, 'failed':len(errors), 'attempted':len(targets) if not only else len(only)}
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(f'Updated {DATA}: {n_ok} successful, {len(errors)} failed')
    # Do not make workflow fail if one retailer blocks scraping; site indicates stale values.
    # If all sources fail, non-zero so GitHub Action shows a visible failure in Actions.
    if n_ok == 0:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
