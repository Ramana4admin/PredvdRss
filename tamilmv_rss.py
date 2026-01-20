import os
import json
import time
import re
import random
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ================= CONFIG =================

BASE_URLS = [
    "https://www.1tamilmv.haus/",
    "https://www.1tamilmv.lc/",
    "https://www.1tamilmv.do/",
    "https://www.1tamilmv.re/",
    "https://www.1tamilmv.kiwi/",
    "https://www.1tamilmv.land/",
]

OUT_FILE = "tamilmv_predvd.xml"
STATE_FILE = "state_predvd.json"

MAX_SIZE_GB = 4              # Skip >4GB
TOPIC_LIMIT = 20             # Check more recent on homepage
TOPIC_DELAY = 10 + random.uniform(0, 5)  # Random human-like delay
MAX_MAGNETS_PER_RUN = 8      # Keep low to avoid any rate issues

PREDVD_KEYWORDS = re.compile(
    r'(predvd|hq predvd|dvdscr|dvd scr|dvd|cam|tc|hdcam|hq clean|predvd hq|dvdscreener)',
    re.IGNORECASE
)

# ==========================================

# Load state
processed = set()
if os.path.exists(STATE_FILE):
    with open(STATE_FILE, encoding='utf-8') as f:
        state = json.load(f)
        processed = set(state.get("magnets", []))

def get_page_content(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--disable-dev-shm-usage',
            ]
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='Asia/Kolkata',
            ignore_https_errors=True,
            java_script_enabled=True,
            bypass_csp=True,
        )
        page = context.new_page()

        # Apply stealth
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)

        content = ""
        try:
            page.goto(url, timeout=90000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000 + random.randint(2000, 8000))
            page.evaluate("window.scrollBy(0, window.innerHeight / 2)")
            page.wait_for_timeout(3000 + random.randint(1000, 4000))
            content = page.content()
            if "Just a moment" in content or "Checking your browser" in content:
                print("⚠️ CF challenge detected - extra wait...")
                page.wait_for_timeout(15000)
                content = page.content()
        except Exception as e:
            print(f"Playwright error on {url}: {str(e)}")
        finally:
            browser.close()
    return content

# Resolve working BASE_URL
BASE_URL = None
for url in BASE_URLS:
    content = get_page_content(url)
    if content and len(content) > 5000 and any(kw in content for kw in ['PreDVD', 'HQ PreDVD', 'HQ Clean']):
        BASE_URL = url
        break
    time.sleep(5)

if not BASE_URL:
    print("❌ No working domain found with PreDVD content")
    exit()

print(f"✅ Using domain: {BASE_URL}")

# RSS setup
rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")
SubElement(channel, "title").text = "1TamilMV PreDVD/HQ PreDVD RSS (≤4GB)"
SubElement(channel, "link").text = BASE_URL
SubElement(channel, "description").text = "Auto-generated RSS for PreDVD, HQ PreDVD, DVDScr etc. only (files ≤4GB)"
SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

# Fetch homepage
home_content = get_page_content(BASE_URL)
if not home_content:
    print("❌ Failed to load homepage")
    exit()

soup = BeautifulSoup(home_content, "lxml")

# Find topic links - match real pattern
posts = []
for a in soup.find_all("a", href=re.compile(r'(forums/topic|index\.php\?/forums/topic/)', re.I)):
    title = a.get_text(strip=True)
    href = a.get("href")
    if title and PREDVD_KEYWORDS.search(title) and "pinned" not in str(a.get("class", [])).lower():
        posts.append((title, href))

posts = posts[:TOPIC_LIMIT]
print(f"Found {len(posts)} potential PreDVD/HQ PreDVD topics on homepage")

def magnet_size_gb(magnet):
    try:
        qs = parse_qs(urlparse(magnet).query)
        if "xl" in qs:
            return int(qs["xl"][0]) / (1024 ** 3)
    except:
        pass
    return None

added_count = 0
new_data = False

for title, post_href in posts:
    if added_count >= MAX_MAGNETS_PER_RUN:
        print("🚑 Max magnets per run reached")
        break

    full_post_url = post_href if post_href.startswith('http') else BASE_URL.rstrip('/') + '/' + post_href.lstrip('/')
    
    try:
        time.sleep(TOPIC_DELAY)
        page_content = get_page_content(full_post_url)
        if not page_content:
            print(f"Skipped {title} - page load failed")
            continue

        psoup = BeautifulSoup(page_content, "lxml")

        magnets_found = 0
        for a in psoup.find_all("a", href=re.compile("^magnet:", re.I)):
            magnet = a["href"]
            if magnet in processed:
                continue

            size = magnet_size_gb(magnet)
            if size is not None and size > MAX_SIZE_GB:
                continue

            # Safety check
            if not PREDVD_KEYWORDS.search(title):
                continue

            item = SubElement(channel, "item")
            size_str = f" [{round(size, 2)}GB]" if size is not None else ""
            SubElement(item, "title").text = f"{title}{size_str}"
            SubElement(item, "link").text = magnet
            SubElement(item, "guid").text = magnet
            SubElement(item, "pubDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

            processed.add(magnet)
            added_count += 1
            new_data = True
            magnets_found += 1
            print(f"➕ Added: {title} | Size: {size if size else 'unknown'} GB")

        if magnets_found == 0:
            print(f"No new magnets in: {title}")

    except Exception as e:
        print(f"ERROR processing {title}: {str(e)}")

# Save if updated
if new_data:
    ElementTree(rss).write(OUT_FILE, encoding="utf-8", xml_declaration=True)
    print("✅ RSS file updated with new PreDVD entries!")
else:
    print("ℹ️ No new PreDVD magnets found this run")

with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump({"magnets": list(processed)}, f, indent=2)

print("Script completed! Check RSS:", OUT_FILE)
