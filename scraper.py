#!/usr/bin/env python3
"""Scrape today's news from https://www.newswire.lk/.

For every story published in the window (default: the last 24 hours, so a daily
10am run never misses anything between runs) it collects the title, link, publish
time, full text and images, downloads + resizes the images, then adds a summary
and a Political / Finance / Tech category (see enrich.py).

Output:
  data/<YYYY-MM-DD>.json      today's edition
  data/latest.json            copy of the newest edition (what build_site.py reads)
  data/images/<YYYY-MM-DD>/   downloaded images

Usage:
  python scraper.py                 # last 24 hours
  python scraper.py --since-midnight
  python scraper.py --hours 12 --no-llm
"""

from __future__ import annotations

import argparse
import html
import io
import json
import logging
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image

from enrich import CATEGORIES, FALLBACK_CATEGORY, enrich

try:
    from dotenv import load_dotenv
except ImportError:  # optional
    load_dotenv = None

BASE_URL = "https://www.newswire.lk"
SITE_TZ = timezone(timedelta(hours=5, minutes=30))  # Asia/Colombo, no DST
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 SriLankaNewsDigest/1.0"
)
MAX_IMAGE_WIDTH = 960
MAX_EXTRA_IMAGES = 3
EXCLUDE_TITLE_PATTERNS = [re.compile(r"^Today.s News Digest", re.I)]  # roundups duplicate other stories
TRAILING_CREDIT = re.compile(r"\s*\((?:Newswire|Agencies|AFP|Reuters|AP|PMD)\)\s*$", re.I)

log = logging.getLogger("scraper")


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
    adapter = requests.adapters.HTTPAdapter(max_retries=requests.adapters.Retry(
        total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504)))
    s.mount("https://", adapter)
    return s


def fetch_via_rest(session: requests.Session, cutoff_utc: datetime) -> list[dict]:
    """Primary source: the WordPress REST API (structured, includes featured images)."""
    after_local = cutoff_utc.astimezone(SITE_TZ).replace(tzinfo=None).isoformat(timespec="seconds")
    posts, page, total_pages = [], 1, 1
    while page <= total_pages:
        r = session.get(
            f"{BASE_URL}/wp-json/wp/v2/posts",
            params={"after": after_local, "per_page": 100, "page": page, "orderby": "date",
                    "order": "desc", "_embed": "wp:featuredmedia,wp:term"},
            timeout=30,
        )
        r.raise_for_status()
        total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
        posts.extend(r.json())
        page += 1

    articles = []
    for p in posts:
        published_utc = datetime.fromisoformat(p["date_gmt"]).replace(tzinfo=timezone.utc)
        if published_utc < cutoff_utc:
            continue
        embedded = p.get("_embedded", {})
        terms = [t for group in embedded.get("wp:term", []) for t in group]
        featured = (embedded.get("wp:featuredmedia") or [{}])[0] or {}
        articles.append({
            "id": p["id"],
            "title": clean_text(p["title"]["rendered"]),
            "url": p["link"],
            "published": published_utc.astimezone(SITE_TZ).isoformat(),
            "source_categories": [html.unescape(t["name"]) for t in terms if t.get("taxonomy") == "category"],
            "tags": [html.unescape(t["name"]) for t in terms if t.get("taxonomy") == "post_tag"],
            "content_html": p["content"]["rendered"],
            "featured_image": featured.get("source_url"),
            "featured_alt": clean_text(featured.get("alt_text") or ""),
        })
    return articles


def fetch_via_rss(session: requests.Session, cutoff_utc: datetime) -> list[dict]:
    """Fallback if the REST API is ever disabled: the standard WordPress RSS feed."""
    r = session.get(f"{BASE_URL}/feed/", timeout=30)
    r.raise_for_status()
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    articles = []
    for item in ET.fromstring(r.content).iter("item"):
        published = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc)
        if published < cutoff_utc:
            continue
        guid = item.findtext("guid") or ""
        m = re.search(r"[?&]p=(\d+)", guid)
        link = item.findtext("link")
        articles.append({
            "id": int(m.group(1)) if m else abs(hash(link)) % 10**9,
            "title": clean_text(item.findtext("title") or ""),
            "url": link,
            "published": published.astimezone(SITE_TZ).isoformat(),
            "source_categories": [clean_text(c.text or "") for c in item.findall("category")],
            "tags": [],
            "content_html": item.findtext("content:encoded", default="", namespaces=ns)
                            or item.findtext("description") or "",
            "featured_image": None,
            "featured_alt": "",
        })
    return articles


def fetch_og_image(session: requests.Session, url: str) -> str | None:
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        tag = BeautifulSoup(r.text, "html.parser").find("meta", property="og:image")
        return tag["content"] if tag and tag.get("content") else None
    except requests.RequestException:
        return None


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def clean_text(s: str) -> str:
    s = BeautifulSoup(html.unescape(s), "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", s).strip()


def parse_content(content_html: str) -> tuple[str, list[dict]]:
    """Return (plain text, [{url, alt}]) from the article body."""
    soup = BeautifulSoup(content_html, "html.parser")
    images = []
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if src.startswith("http") and "/wp-content/uploads/" in src and not src.endswith(".gif"):
            images.append({"url": src.split("?")[0], "alt": clean_text(img.get("alt") or "")})
    for tag in soup(["script", "style", "figure", "figcaption", "iframe", "noscript"]):
        tag.decompose()
    for tag in soup.select(".more-link, .sharedaddy, .jp-relatedposts"):
        tag.decompose()
    blocks = [re.sub(r"\s+", " ", el.get_text(" ")).strip() for el in soup.find_all(["p", "li", "h2", "h3", "blockquote"])]
    blocks = [b for b in blocks if b]
    text = "\n".join(blocks) if blocks else re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    text = TRAILING_CREDIT.sub("", text).strip()
    return text, images


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #
def download_image(session: requests.Session, url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        r = session.get(url, timeout=30, headers={"Referer": BASE_URL + "/"})
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        img = img.convert("RGB")
        if img.width > MAX_IMAGE_WIDTH:
            img = img.resize((MAX_IMAGE_WIDTH, round(img.height * MAX_IMAGE_WIDTH / img.width)), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "JPEG", quality=82, optimize=True, progressive=True)
        return True
    except Exception as e:  # network, decode, unsupported format...
        log.warning("Image download failed for %s: %s", url, e)
        return False


def collect_images(session, article: dict, image_dir: Path, edition: str) -> list[dict]:
    """Featured image first, then distinct in-article images. Each gets a local copy."""
    candidates = []
    if article["featured_image"]:
        candidates.append({"url": article["featured_image"], "alt": article["featured_alt"]})
    for img in article.pop("_content_images"):
        if all(Path(img["url"]).stem != Path(c["url"]).stem for c in candidates):
            candidates.append(img)
    if not candidates:
        og = fetch_og_image(session, article["url"])
        if og:
            candidates.append({"url": og, "alt": ""})

    images = []
    for n, c in enumerate(candidates[: 1 + MAX_EXTRA_IMAGES]):
        name = f"{article['id']}.jpg" if n == 0 else f"{article['id']}-{n + 1}.jpg"
        ok = download_image(session, c["url"], image_dir / name)
        images.append({
            "src": f"images/{edition}/{name}" if ok else None,  # relative to data/ and to the site root
            "remote": c["url"],
            "alt": c["alt"] or article["title"],
        })
        time.sleep(0.15)  # be polite
    return images


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=24, help="look-back window in hours (default 24)")
    ap.add_argument("--since-midnight", action="store_true", help="only stories published since 00:00 Sri Lanka time")
    ap.add_argument("--no-llm", action="store_true", help="never call Claude, even if ANTHROPIC_API_KEY is set")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    if load_dotenv:
        load_dotenv(ROOT / ".env")

    now = datetime.now(SITE_TZ)
    edition = now.date().isoformat()
    cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0) if args.since_midnight else now - timedelta(hours=args.hours)
    cutoff_utc = cutoff.astimezone(timezone.utc)

    session = make_session()
    try:
        raw = fetch_via_rest(session, cutoff_utc)
        source = "wp-rest-api"
    except (requests.RequestException, ValueError, KeyError) as e:
        log.warning("REST API failed (%s); falling back to RSS feed", e)
        raw = fetch_via_rss(session, cutoff_utc)
        source = "rss"
    log.info("Fetched %d stories since %s via %s", len(raw), cutoff.strftime("%Y-%m-%d %H:%M"), source)

    articles = []
    for a in raw:
        if any(p.search(a["title"]) for p in EXCLUDE_TITLE_PATTERNS):
            continue
        a["text"], a["_content_images"] = parse_content(a.pop("content_html"))
        a["word_count"] = len(a["text"].split())
        a["is_lead"] = "Lead Story" in a["source_categories"]
        articles.append(a)

    engine = enrich(articles, use_llm=not args.no_llm)
    log.info("Summaries + categories via %s engine", engine)

    image_dir = DATA_DIR / "images" / edition
    for a in articles:
        a["images"] = collect_images(session, a, image_dir, edition)
        a.pop("featured_image"), a.pop("featured_alt")

    articles.sort(key=lambda a: a["published"], reverse=True)
    order = CATEGORIES + [FALLBACK_CATEGORY]
    edition_data = {
        "source": BASE_URL + "/",
        "fetched_via": source,
        "edition_date": edition,
        "generated_at": now.isoformat(timespec="seconds"),
        "window": {"from": cutoff.isoformat(timespec="seconds"), "to": now.isoformat(timespec="seconds")},
        "enrichment": engine,
        "categories": order,
        "counts": {c: sum(a["category"] == c for a in articles) for c in order},
        "articles": articles,
    }

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"{edition}.json"
    out.write_text(json.dumps(edition_data, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(out, DATA_DIR / "latest.json")
    log.info("Wrote %s (%d articles: %s)", out.relative_to(ROOT), len(articles),
             ", ".join(f"{c} {n}" for c, n in edition_data["counts"].items()))

    if not articles:
        log.warning("No stories found in the window - is newswire.lk reachable?")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
