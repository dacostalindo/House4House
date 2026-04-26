"""
VIZTA.pt — Scrape feasibility test
Extracts all available apartment and project data.
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin

BASE_URL = "https://www.vizta.pt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def extract_js_array(text, varname):
    """Extract a JS array variable from page source by matching brackets."""
    pattern = rf'(?:const|let|var)\s+{varname}\s*=\s*\['
    m = re.search(pattern, text)
    if not m:
        return None
    start = m.end() - 1  # position of '['
    depth = 0
    for j in range(start, min(start + 2_000_000, len(text))):
        if text[j] == '[':
            depth += 1
        elif text[j] == ']':
            depth -= 1
        if depth == 0:
            try:
                return json.loads(text[start:j + 1])
            except json.JSONDecodeError:
                return None
    return None


def fetch_all_apartments():
    """Extract all apartment data — handles pagination via URL params."""
    url = f"{BASE_URL}/pt/projetos/apartamentos/"
    print(f"[1/4] Fetching apartment index: {url}")
    resp = session.get(url)
    resp.raise_for_status()

    apartments = extract_js_array(resp.text, "unidades")
    if apartments:
        print(f"       Found {len(apartments)} apartments on page 1")
    else:
        print("       ERROR: Could not extract apartment data")
        return []

    # Extract total count and check for pagination
    total_match = re.search(r'"total"\s*:\s*(\d+)', resp.text)
    total = int(total_match.group(1)) if total_match else len(apartments)
    print(f"       Total apartments reported: {total}")

    # Paginate if needed
    page = 2
    while len(apartments) < total:
        page_url = f"{url}?page={page}"
        print(f"       Fetching page {page}: {page_url}")
        resp = session.get(page_url)
        if not resp.ok:
            break
        page_data = extract_js_array(resp.text, "unidades")
        if not page_data:
            break
        apartments.extend(page_data)
        print(f"       Got {len(page_data)} more ({len(apartments)}/{total})")
        page += 1
        if page > 20:  # safety limit
            break

    print(f"       Total extracted: {len(apartments)}")
    return apartments


def fetch_project_list():
    """Extract all project URLs and basic info from the projects page."""
    url = f"{BASE_URL}/pt/projetos/"
    print(f"\n[2/4] Fetching project index: {url}")
    resp = session.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Also try to extract project data from JS
    projetos_js = extract_js_array(resp.text, "projetos")
    if projetos_js:
        print(f"       Found {len(projetos_js)} projects via JS variable")
        return projetos_js

    projects = []
    for link in soup.find_all("a", href=re.compile(r"/pt/projetos/[^/]+/\d+/")):
        href = link.get("href", "")
        if "/apartamentos/" in href:
            continue
        name = link.get_text(strip=True) or href.split("/")[-3]
        projects.append({
            "name": name,
            "url": urljoin(BASE_URL, href),
        })

    # Deduplicate
    seen = set()
    unique = []
    for p in projects:
        key = p.get("url") or p.get("name")
        if key not in seen:
            seen.add(key)
            unique.append(p)

    print(f"       Found {len(unique)} projects")
    return unique


def fetch_apartment_detail(apartment_url):
    """Scrape a single apartment detail page for additional data."""
    url = urljoin(BASE_URL, apartment_url)
    resp = session.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    detail = {}

    # Description
    desc_el = soup.find("div", class_=re.compile(r"desc|description|text|info"))
    if desc_el:
        detail["description"] = desc_el.get_text(strip=True)[:500]

    # All images (broader search)
    images = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy") or ""
        if src and "vizta.pt" in src and "logo" not in src.lower() and "icon" not in src.lower():
            images.add(urljoin(BASE_URL, src))
    # Also check background images in style attributes
    for el in soup.find_all(style=re.compile(r"background.*url")):
        m = re.search(r"url\(['\"]?(.*?)['\"]?\)", el.get("style", ""))
        if m:
            images.add(urljoin(BASE_URL, m.group(1)))
    detail["images"] = sorted(images)

    # Floor plan links
    plans = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True).lower()
        if "planta" in href.lower() or "planta" in text or "floor" in text.lower():
            plans.add(urljoin(BASE_URL, href))
    detail["floor_plans"] = sorted(plans)

    # GPS coordinates
    gps_match = re.search(
        r"(?:lat|latitude)['\"]?\s*[:=]\s*([0-9.-]+).*?"
        r"(?:lng|longitude|lon)['\"]?\s*[:=]\s*([0-9.-]+)",
        resp.text, re.I | re.DOTALL
    )
    if gps_match:
        lat, lon = float(gps_match.group(1)), float(gps_match.group(2))
        if lat != 0 and lon != 0:
            detail["latitude"] = lat
            detail["longitude"] = lon

    # OG image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        detail["og_image"] = og["content"]

    # OG description
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        detail["og_description"] = og_desc["content"]

    return detail


def fetch_project_detail(project_url):
    """Scrape a project page for development-level data."""
    resp = session.get(project_url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    text = resp.text

    detail = {}

    # Try extracting embedded apartment data for this project
    project_units = extract_js_array(text, "unidades")
    if project_units:
        detail["units_count"] = len(project_units)
        detail["units_sample"] = project_units[:2]

    # Description from og:description or page content
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        detail["description"] = og_desc["content"]

    # All images
    images = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src and "vizta.pt" in src and "logo" not in src.lower() and "icon" not in src.lower():
            images.add(urljoin(BASE_URL, src))
    for el in soup.find_all(style=re.compile(r"background.*url")):
        m = re.search(r"url\(['\"]?(.*?)['\"]?\)", el.get("style", ""))
        if m and "vizta.pt" in m.group(1):
            images.add(urljoin(BASE_URL, m.group(1)))
    detail["images"] = sorted(images)[:20]

    # GPS
    gps_match = re.search(
        r"(?:lat|latitude)['\"]?\s*[:=]\s*([0-9.-]+).*?"
        r"(?:lng|longitude|lon)['\"]?\s*[:=]\s*([0-9.-]+)",
        text, re.I | re.DOTALL
    )
    if gps_match:
        lat, lon = float(gps_match.group(1)), float(gps_match.group(2))
        if lat != 0 and lon != 0:
            detail["latitude"] = lat
            detail["longitude"] = lon

    # Gallery / slideshow images
    for script in soup.find_all("script"):
        st = script.string or ""
        for m in re.finditer(r'(?:src|url)[\'"]?\s*[:=]\s*[\'"]([^"\']+\.(?:jpg|jpeg|png|webp))[\'"]', st, re.I):
            img_url = urljoin(BASE_URL, m.group(1))
            if "vizta.pt" in img_url:
                images.add(img_url)
    detail["images"] = sorted(images)[:30]

    return detail


def main():
    print("=" * 60)
    print("VIZTA.pt — Scrape Feasibility Test")
    print("=" * 60)

    # 1. Get all apartments
    apartments = fetch_all_apartments()

    # 2. Get all projects
    projects = fetch_project_list()

    # 3. Sample apartment detail pages
    print(f"\n[3/4] Sampling apartment detail pages (3 samples)...")
    sample_details = []
    available_apts = [a for a in apartments if a.get("disponivel", True) and a.get("url")]
    for apt in available_apts[:3]:
        url = apt["url"]
        print(f"       Fetching: {url}")
        try:
            detail = fetch_apartment_detail(url)
            sample_details.append({"id": apt.get("id"), "ref": apt.get("referencia"), **detail})
        except Exception as e:
            print(f"       ERROR: {e}")

    # 4. Sample project detail pages
    print(f"\n[4/4] Sampling project detail pages (3 samples)...")
    project_details = []
    for proj in (projects if isinstance(projects[0], dict) and "url" in projects[0] else [])[:3]:
        proj_url = proj.get("url", "")
        if not proj_url.startswith("http"):
            proj_url = urljoin(BASE_URL, proj_url)
        print(f"       Fetching: {proj_url}")
        try:
            detail = fetch_project_detail(proj_url)
            project_details.append({"name": proj.get("name", proj.get("title", "")), "url": proj_url, **detail})
        except Exception as e:
            print(f"       ERROR: {e}")

    # --- REPORT ---
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    if apartments:
        fields = set()
        for a in apartments:
            fields.update(a.keys())

        typologies = sorted(set(a.get("tipologia", "") for a in apartments if a.get("tipologia")))
        estados = sorted(set(a.get("estado_label", a.get("estado", "")) for a in apartments))
        prices = [a.get("preco", 0) for a in apartments if a.get("preco")]
        areas = [a.get("area_bruta", 0) for a in apartments if a.get("area_bruta")]
        project_names = sorted(set(
            a.get("projeto", {}).get("title", "") for a in apartments
            if isinstance(a.get("projeto"), dict) and a["projeto"].get("title")
        ))
        available = sum(1 for a in apartments if a.get("disponivel"))
        with_plans = sum(1 for a in apartments if a.get("planta"))
        with_discount = sum(1 for a in apartments if a.get("preco_desconto", 0) > 0)

        print(f"\nAPARTMENTS: {len(apartments)} total")
        print(f"   Available: {available} | Sold/Reserved: {len(apartments) - available}")
        print(f"   With floor plans (PDF): {with_plans}")
        print(f"   With discounts: {with_discount}")
        print(f"\n   Fields ({len(fields)}): {sorted(fields)}")
        print(f"\n   Typologies: {typologies}")
        print(f"   Status values: {estados}")
        print(f"   Price range: {min(prices):,.0f} - {max(prices):,.0f} EUR" if prices else "   No prices")
        print(f"   Area range: {min(areas)}-{max(areas)} m2" if areas else "   No areas")
        print(f"   Projects: {project_names}")

        # Per-project breakdown
        print(f"\n   Per-project breakdown:")
        from collections import Counter
        proj_counts = Counter(
            a.get("projeto", {}).get("title", "Unknown")
            for a in apartments if isinstance(a.get("projeto"), dict)
        )
        for name, count in proj_counts.most_common():
            proj_apts = [a for a in apartments if isinstance(a.get("projeto"), dict) and a["projeto"].get("title") == name]
            avail = sum(1 for a in proj_apts if a.get("disponivel"))
            typs = sorted(set(a.get("tipologia", "") for a in proj_apts))
            p_range = [a.get("preco", 0) for a in proj_apts if a.get("preco")]
            price_str = f"{min(p_range):,.0f}-{max(p_range):,.0f} EUR" if p_range else "N/A"
            print(f"     {name}: {count} units ({avail} avail) | {typs} | {price_str}")

    print(f"\nPROJECTS: {len(projects)} found")
    for p in projects:
        name = p.get("name", p.get("title", "?"))
        url = p.get("url", "")
        print(f"   - {name}: {url}")

    print(f"\nAPARTMENT DETAIL SAMPLES ({len(sample_details)}):")
    for d in sample_details:
        print(f"   #{d.get('id')} (ref: {d.get('ref')}):")
        print(f"     Images found: {len(d.get('images', []))}")
        if d.get('images'):
            print(f"     Sample image: {d['images'][0][:100]}")
        print(f"     Floor plans: {len(d.get('floor_plans', []))}")
        if d.get('floor_plans'):
            for fp in d['floor_plans']:
                print(f"       {fp[:120]}")
        if d.get("latitude"):
            print(f"     GPS: {d['latitude']}, {d['longitude']}")
        if d.get("og_description"):
            print(f"     Description: {d['og_description'][:150]}...")

    print(f"\nPROJECT DETAIL SAMPLES ({len(project_details)}):")
    for d in project_details:
        print(f"   {d.get('name')}:")
        print(f"     Images found: {len(d.get('images', []))}")
        if d.get("units_count"):
            print(f"     Units on page: {d['units_count']}")
        if d.get("latitude"):
            print(f"     GPS: {d['latitude']}, {d['longitude']}")
        if d.get("description"):
            print(f"     Description: {d['description'][:150]}...")

    # Save full data
    output = {
        "apartments": apartments,
        "projects": projects,
        "apartment_detail_samples": sample_details,
        "project_detail_samples": project_details,
    }
    out_path = "/Users/manuellindo/Desktop/Apps/House4House/scripts/vizta_scrape_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    size_kb = len(json.dumps(output, ensure_ascii=False)) / 1024
    print(f"\nFull data saved to: {out_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
