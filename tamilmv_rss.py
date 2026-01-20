import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree
import time, json, os, re
from urllib.parse import parse_qs, urlparse

# ================= CONFIG =================
BASE_URL = "https://www.1tamilmv.haus/"

OUT_FILE = "tamilmv.xml"
STATE_FILE = "state.json"

MAX_POSTS_PER_RUN = 5        # ✅ Only 5 posts per cron
TOPIC_LIMIT = 50             # Scan latest 50 topics
TOPIC_DELAY = 3              # Seconds
MOVIE_MAX_SIZE_GB = 4        # 🎬 Movies <4GB only
# ==========================================

SERIES_KEYWORDS = [
    "season", "s01", "s02", "s03", "episode", "ep", "web series", "complete"
]

# Cloudflare bypass
scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

# ---------------- Load state ----------------
if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
else:
    state = {"magnets": []}

processed = set(state.get("magnets", []))

# ---------------- RSS setup ----------------
rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")

SubElement(channel, "title").text = "1TamilMV Smart RSS"
SubElement(channel, "link").text = BASE_URL
SubElement(channel, "description").text = "Movies <4GB | Series Any Size"
SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime(
    "%a, %d %b %Y %H:%M:%S GMT"
)

# ---------------- Helpers ----------------
def magnet_size_gb(magnet):
    qs = parse_qs(urlparse(magnet).query)
    if "xl" in qs:
        return int(qs["xl"][0]) / (1024 ** 3)
    return None

def is_series(title):
    t = title.lower()
    return any(k in t for k in SERIES_KEYWORDS)

# ---------------- Fetch homepage ----------------
home = scraper.get(BASE_URL, timeout=30)
soup = BeautifulSoup(home.text, "lxml")

posts = []
for a in soup.select("a[href*='forums/topic']"):
    posts.append((a.get_text(strip=True), a["href"]))

posts = posts[:TOPIC_LIMIT]

# ---------------- Scrape ----------------
processed_posts = 0

for title, post_url in posts:
    if processed_posts >= MAX_POSTS_PER_RUN:
        break

    try:
        time.sleep(TOPIC_DELAY)
        page = scraper.get(post_url, timeout=30)
        psoup = BeautifulSoup(page.text, "lxml")

        series = is_series(title)
        post_added = False

        for a in psoup.find_all("a", href=True):
            magnet = a["href"]

            if not magnet.startswith("magnet:?"):
                continue

            if magnet in processed:
                continue

            size = magnet_size_gb(magnet)

            # 🎬 Movie rule
            if not series:
                if size and size > MOVIE_MAX_SIZE_GB:
                    continue

            # ✅ Add RSS
            item = SubElement(channel, "item")
            tag = "SERIES" if series else "MOVIE"

            SubElement(item, "title").text = (
                f"{title} [{tag} - {round(size,2)}GB]" if size else f"{title} [{tag}]"
            )
            SubElement(item, "link").text = magnet
            SubElement(item, "guid").text = magnet
            SubElement(item, "pubDate").text = datetime.utcnow().strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )

            processed.add(magnet)
            post_added = True
            print(f"➕ {tag}:", title, size)

        if post_added:
            processed_posts += 1

    except Exception as e:
        print("ERROR:", title, e)

# ---------------- SAVE ----------------
ElementTree(rss).write(OUT_FILE, encoding="utf-8", xml_declaration=True)

with open(STATE_FILE, "w") as f:
    json.dump({"magnets": list(processed)}, f, indent=2)

print(f"✅ DONE | Posts added this run: {processed_posts}")
