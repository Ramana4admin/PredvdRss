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
soup = BeautifulSoup(res.text, "html.parser")

rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")

SubElement(channel, "title").text = "1TamilMV RSS"
SubElement(channel, "link").text = URL
SubElement(channel, "description").text = "Auto RSS for 1TamilMV"
SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

posts = soup.select("article")[:20]

for post in posts:
    a = post.find("a")
    if not a:
        continue

    item = SubElement(channel, "item")
    SubElement(item, "title").text = a.text.strip()
    SubElement(item, "link").text = a["href"]
    SubElement(item, "guid").text = a["href"]
    SubElement(item, "pubDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

ElementTree(rss).write(OUT_FILE, encoding="utf-8", xml_declaration=True)
print("RSS generated")
