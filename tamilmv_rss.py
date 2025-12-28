import requests
from bs4 import BeautifulSoup
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree

URL = "https://www.1tamilmv.lc/"
OUT_FILE = "tamilmv.xml"

headers = {
    "User-Agent": "Mozilla/5.0"
}

res = requests.get(URL, headers=headers, timeout=30)
res.raise_for_status()

soup = BeautifulSoup(res.text, "html.parser")

rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")

SubElement(channel, "title").text = "1TamilMV RSS"
SubElement(channel, "link").text = URL
SubElement(channel, "description").text = "Auto RSS feed for 1TamilMV"
SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime(
    "%a, %d %b %Y %H:%M:%S GMT"
)

# Forum posts / topics
posts = soup.select("a[href*='topic']")[:30]

added = set()

for a in posts:
    title = a.get_text(strip=True)
    link = a.get("href")

    if not title or not link:
        continue

    if link in added:
        continue

    added.add(link)

    item = SubElement(channel, "item")
    SubElement(item, "title").text = title
    SubElement(item, "link").text = link
    SubElement(item, "guid").text = link
    SubElement(item, "pubDate").text = datetime.utcnow().strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )

ElementTree(rss).write(OUT_FILE, encoding="utf-8", xml_declaration=True)
print("RSS generated successfully")
