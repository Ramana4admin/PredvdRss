import os
import json
import time
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

================= CONFIG =================

BASE_URLS = [
    "https://www.1tamilmv.haus/",
    "https://www.1tamilmv.lc/",
    "https://www.1tamilmv.do/",
    "https://www.1tamilmv.re/",
    "https://www.1tamilmv.band/",
    "https://www.1tamilmv.kiwi/",  # Add recent mirrors if needed
]

OUT_FILE = "tamilmv_predvd.xml"
STATE_FILE = "state_predvd.json"

MAX_SIZE_GB = 4
TOPIC_LIMIT = 20             # Homepage లో recent ఎక్కువ ఉంటాయి
TOPIC_DELAY = 8
MAX_MAGNETS_PER_RUN = 10

PREDVD_KEYWORDS = re.compile(r'(predvd|hq predvd|dvdscr|dvd scr|dvd|cam|tc|hdcam|hq clean|predvd hq|dvdscreener)', re.IGNORECASE)

==========================================

# Load state
processed = set()
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        state = json.load(f)
        processed = set(state.get("magnets", []))

def get_page_content(url, timeout=60000):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        try:
            page.goto(url, timeout=timeout, wait_until="networkidle")
            page.wait_for_timeout(5000)  # Extra wait for CF
            content = page.content()
        except Exception as e:
            print(f"Playwright error on {url}: {e}")
            content = ""
        finally:
            browser.close()
    return content

# Resolve BASE_URL
BASE_URL = None
for url in BASE_URLS:
    content = get_page_content(url)
    if content and len(content) > 5000 and "PreDVD" in content:  # Rough check
        BASE_URL = url
        break

if not BASE_URL:
    print("❌ No working domain (all blocked or no PreDVD content)")
    exit()

print("✅ Using:", BASE_URL)

# RSS setup
rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")
SubElement(channel, "title").text = "1TamilMV PreDVD/DVD RSS (≤4GB)"
SubElement(channel, "link").text = BASE_URL
SubElement(channel, "description").text = "Auto RSS for PreDVD, HQ PreDVD etc. only (Below 4GB)"
SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

# Fetch homepage (no forum path needed now)
home_content = get_page_content(BASE_URL)
soup = BeautifulSoup(home_content, "lxml")

posts = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    title = a.get_text(strip=True)
    if not title:
        continue
    if "topic" in href.lower() and PREDVD_KEYWORDS.search(title):
        posts.append((title, href))

posts = posts[:TOPIC_LIMIT]
print(f"Found {len(posts)} potential PreDVD topics from homepage")

def magnet_size_gb(magnet):
    qs = parse_qs(urlparse(magnet).query)
    if "xl" in qs:
        return int(qs["xl"][0]) / (1024 ** 3)
    return None

added_count = 0
new_data = False

for title, post_rel_url in posts:
    if added_count >= MAX_MAGNETS_PER_RUN:
        break

    full_post_url = post_rel_url if post_rel_url.startswith('http') else BASE_URL.rstrip('/') + '/' + post_rel_url.lstrip('/')
    
    try:
        time.sleep(TOPIC_DELAY)
        page_content = get_page_content(full_post_url)
        psoup = BeautifulSoup(page_content, "lxml")

        magnets_found = False
        for a in psoup.find_all("a", href=True):
            magnet = a["href"]
            if not magnet.startswith("magnet:?"):
                continue
            if magnet in processed:
                continue

            size = magnet_size_gb(magnet)
            if size and size > MAX_SIZE_GB:
                continue

            if not PREDVD_KEYWORDS.search(title):
                continue

            item = SubElement(channel, "item")
            size_str = f" [{round(size,2)}GB]" if size else ""
            SubElement(item, "title").text = title + size_str
            SubElement(item, "link").text = magnet
            SubElement(item, "guid").text = magnet
            SubElement(item, "pubDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

            processed.add(magnet)
            added_count += 1
            new_data = True
            print("➕ Added:", title, size or "unknown size")
            magnets_found = True

            if added_count >= MAX_MAGNETS_PER_RUN:
                break

        if not magnets_found:
            print("No magnets in:", title)

    except Exception as e:
        print("ERROR on topic:", title, e)

if new_data:
    ElementTree(rss).write(OUT_FILE, encoding="utf-8", xml_declaration=True)
    print("✅ RSS UPDATED with PreDVD only")
else:
    print("ℹ️ No new PreDVD torrents/magnets found")

with open(STATE_FILE, "w") as f:
    json.dump({"magnets": list(processed)}, f, indent=2)

print("DONE!")
