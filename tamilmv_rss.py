import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree
import time, json, os
from urllib.parse import parse_qs, urlparse
import re

================= CONFIG =================

BASE_URLS = [
    "https://www.1tamilmv.haus/",
    "https://www.1tamilmv.lc/",
    "https://www.1tamilmv.do/",
    "https://www.1tamilmv.re/",
    "https://www.1tamilmv.band/",
]

OUT_FILE = "tamilmv_predvd.xml"
STATE_FILE = "state_predvd.json"

MAX_SIZE_GB = 4              # Skip >4GB
TOPIC_LIMIT = 15             # Latest PreDVD topics only (increased a bit since filtered)
TOPIC_DELAY = 6              # Seconds between topic fetch
MAX_MAGNETS_PER_RUN = 12     # Flood control, reduced to be safe

PREDVD_FORUM_PATH = "index.php?/forums/forum/10-predvd-dvdscr-cam-tc/"  # Main one from .haus
# Fallback paths if needed
FORUM_PATHS = [
    "index.php?/forums/forum/10-predvd-dvdscr-cam-tc/",
    "index.php?/forums/forum/35-predvd-dvdscr-cam-tc/",
]

# Keywords to filter PreDVD/DVD only
PREDVD_KEYWORDS = re.compile(r'(predvd|dvdscr|dvd|cam|tc|hqp predvd|predvd hq clean)', re.IGNORECASE)

==========================================

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

# Load state
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        state = json.load(f)
else:
    state = {"magnets": []}

processed = set(state.get("magnets", []))

# Resolve working domain
BASE_URL = None
for url in BASE_URLS:
    try:
        r = scraper.get(url, timeout=20)
        if r.status_code == 200 and "PreDVD" in r.text:  # rough check for content
            BASE_URL = url
            break
    except:
        continue

if not BASE_URL:
    print("❌ No working domain found")
    exit()

print("✅ Using:", BASE_URL)

# Try to find exact PreDVD forum URL
PREDVD_FORUM_URL = None
for path in FORUM_PATHS:
    test_url = BASE_URL.rstrip('/') + '/' + path.lstrip('/')
    try:
        r = scraper.get(test_url, timeout=15)
        if r.status_code == 200:
            PREDVD_FORUM_URL = test_url
            break
    except:
        pass

if not PREDVD_FORUM_URL:
    # Fallback to homepage and filter later
    PREDVD_FORUM_URL = BASE_URL
    print("⚠️ Using homepage fallback - will filter by title keywords")

print("PreDVD Forum URL:", PREDVD_FORUM_URL)

# RSS setup
rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")

SubElement(channel, "title").text = "1TamilMV PreDVD/DVD RSS (≤4GB)"
SubElement(channel, "link").text = BASE_URL
SubElement(channel, "description").text = "Auto RSS for PreDVD, DVDScr, CAM, TC only (Below 4GB)"
SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime(
    "%a, %d %b %Y %H:%M:%S GMT"
)

# Fetch PreDVD section or homepage
home = scraper.get(PREDVD_FORUM_URL, timeout=30)
soup = BeautifulSoup(home.text, "lxml")

posts = []
for a in soup.select("a[href*='forums/topic']"):
    title = a.get_text(strip=True)
    href = a["href"]
    # Skip pinned
    if "pinned" in a.get("class", []):
        continue
    # Filter only PreDVD/DVD related titles
    if PREDVD_KEYWORDS.search(title):
        posts.append((title, href))

posts = posts[:TOPIC_LIMIT]
print(f"Found {len(posts)} potential PreDVD topics")

def magnet_size_gb(magnet):
    qs = parse_qs(urlparse(magnet).query)
    if "xl" in qs:
        return int(qs["xl"][0]) / (1024 ** 3)
    return None

# Scrape topics
added_count = 0
new_data = False

for title, post_url in posts:
    if added_count >= MAX_MAGNETS_PER_RUN:
        print("🚑 Flood limit reached")
        break

    full_post_url = post_url if post_url.startswith('http') else BASE_URL.rstrip('/') + '/' + post_url.lstrip('/')
    
    try:
        time.sleep(TOPIC_DELAY)
        page = scraper.get(full_post_url, timeout=30)
        psoup = BeautifulSoup(page.text, "lxml")

        for a in psoup.find_all("a", href=True):
            magnet = a["href"]
            if not magnet.startswith("magnet:?"):
                continue
            if magnet in processed:
                continue

            size = magnet_size_gb(magnet)
            if size and size > MAX_SIZE_GB:
                continue

            # Double-check title has PreDVD keyword (safety)
            if not PREDVD_KEYWORDS.search(title):
                continue

            item = SubElement(channel, "item")
            SubElement(item, "title").text = (
                f"{title} [{round(size,2)}GB]" if size else title
            )
            SubElement(item, "link").text = magnet
            SubElement(item, "guid").text = magnet
            SubElement(item, "pubDate").text = datetime.utcnow().strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )

            processed.add(magnet)
            added_count += 1
            new_data = True
            print("➕ Added PreDVD:", title, size or "size unknown")

            if added_count >= MAX_MAGNETS_PER_RUN:
                break

    except Exception as e:
        print("ERROR on topic:", title, e)

# Save RSS if new
if new_data:
    ElementTree(rss).write(OUT_FILE, encoding="utf-8", xml_declaration=True)
    print("✅ RSS UPDATED with PreDVD only")
else:
    print("ℹ️ No new PreDVD torrents")

with open(STATE_FILE, "w") as f:
    json.dump({"magnets": list(processed)}, f, indent=2)

print("DONE bro! RSS file:", OUT_FILE)
