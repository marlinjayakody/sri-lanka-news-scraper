#!/usr/bin/env python3
"""Build the static news site from the scraped data.

Reads   data/latest.json (written by scraper.py)
Writes  site/index.html, site/news.json, site/images/..., site/_headers

The page is a vertical feed of full-screen cards: a cover, one card per story
(image, title, summary), and an end card. Cards snap into place as you scroll.

The site/ folder is wiped and rebuilt each run, so it only ever contains today's
edition. Only summaries and metadata are published - the full article text stays
local, and every story links back to Newswire.lk.

Usage:
  python build_site.py                   # build from data/latest.json
  python build_site.py data/2026-10-15.json
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
SITE_TITLE = os.environ.get("SITE_TITLE", "Lanka Daily Digest")
TAGLINE = "Today's Sri Lankan news, summarised"

CATEGORY_SLUGS = {"Political": "political", "Finance": "finance", "Tech": "tech", "General": "general"}
SOURCE_LABELS = {"Bizwire": "Press release", "International": "World"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def e(s) -> str:
    return escape(str(s or ""), quote=True)


def img_src(img: dict | None) -> str | None:
    if not img:
        return None
    return img["src"] or img["remote"]


def fmt_time(iso: str, edition_date: str) -> str:
    dt = datetime.fromisoformat(iso)
    t = dt.strftime("%-I:%M %p")
    return t if dt.date().isoformat() == edition_date else f"Yesterday, {t}"


def labels_for(a: dict) -> list[str]:
    return [SOURCE_LABELS[sc] for sc in a.get("source_categories", []) if sc in SOURCE_LABELS]


# --------------------------------------------------------------------------- #
# Markup
# --------------------------------------------------------------------------- #
def render_story(a: dict, n: int, total: int, edition: str) -> str:
    slug = CATEGORY_SLUGS[a["category"]]
    img = a["images"][0] if a["images"] else None
    lazy = "" if n <= 2 else ' loading="lazy"'
    media = (
        f'<figure class="story-media"><img src="{e(img_src(img))}" alt="{e(img["alt"])}"{lazy} decoding="async"></figure>'
        if img else ""
    )
    labels = "".join(f'<span class="meta-label">{e(l)}</span>' for l in labels_for(a))
    return f"""
  <article class="card story cat-{slug}{'' if img else ' story--text'}" data-cat="{e(a['category'])}" aria-label="{e(a['category'])} story">
    {media}
    <div class="story-text">
      <p class="meta"><span class="meta-cat">{e(a['category'])}</span><time datetime="{e(a['published'])}">{e(fmt_time(a['published'], edition))}</time>{labels}<span class="count">{n:02d} / {total:02d}</span></p>
      <h2 class="story-title">{e(a['title'])}</h2>
      <p class="story-summary">{e(a['summary'])}</p>
      <a class="story-link" href="{e(a['url'])}" target="_blank" rel="noopener">Read the full story <span aria-hidden="true">→</span></a>
    </div>
  </article>"""


def build_html(data: dict) -> str:
    edition = data["edition_date"]
    order = data["categories"]
    counts = data["counts"]
    # Feed order: grouped by category (Political, Finance, Tech, General), newest first within each.
    stories = [a for c in order for a in data["articles"] if a["category"] == c]
    total = len(stories)
    built = datetime.fromisoformat(data["generated_at"])
    weekday, day_month = built.strftime("%A"), built.strftime("%-d %B")

    filter_options = [f'<option value="all">All stories · {total}</option>'] + [
        f'<option value="{e(c)}">{e(c)} · {counts[c]}</option>' for c in order if counts.get(c)
    ]
    contents = "".join(
        f'<li><button type="button" class="toc-item cat-{CATEGORY_SLUGS[c]}" data-go="{e(c)}">'
        f'<span class="toc-name">{e(c)}</span><span class="toc-n">{counts[c]}</span></button></li>'
        for c in order if counts.get(c)
    )
    cards = "".join(render_story(a, i, total, edition) for i, a in enumerate(stories, 1))

    engine_note = {
        "claude": "Summaries and categories written by Claude",
        "mixed": "Summaries and categories written by Claude, with an automatic fallback for some stories",
    }.get(data["enrichment"], "Summaries and categories generated automatically")
    window_from = datetime.fromisoformat(data["window"]["from"]).strftime("%-d %b, %-I:%M %p")
    window_to = datetime.fromisoformat(data["window"]["to"]).strftime("%-d %b, %-I:%M %p")
    og_image = next((img_src(a["images"][0]) for a in stories if a["images"]), "")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(SITE_TITLE)} · {e(weekday)} {e(day_month)}</title>
<meta name="description" content="{e(TAGLINE)}: {total} stories across politics, finance and tech for {e(weekday)} {e(day_month)}.">
<meta property="og:title" content="{e(SITE_TITLE)} · {e(weekday)} {e(day_month)}">
<meta property="og:description" content="{e(TAGLINE)}.">
<meta property="og:image" content="{e(og_image)}">
<meta name="theme-color" content="#fbfbf9" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0f0f0e" media="(prefers-color-scheme: dark)">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='32' fill='%23121212'/%3E%3Ctext x='32' y='44' font-family='Georgia,serif' font-size='34' fill='%23fbfbf9' text-anchor='middle'%3EL%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400..600&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>

<header class="bar">
  <a class="wordmark" href="#top">{e(SITE_TITLE)}</a>
  <span class="bar-date">{e(weekday)}, {e(day_month)}</span>
  <label class="filter">
    <span class="visually-hidden">Show stories from</span>
    <select id="filter">{''.join(filter_options)}</select>
  </label>
</header>

<main>
  <section class="card cover" id="top" aria-label="Today's edition">
    <div class="cover-inner">
      <div>
        <p class="eyebrow">Morning edition · Colombo</p>
        <h1 class="cover-title">{e(weekday)}<br><em>{e(day_month)}</em></h1>
        <p class="cover-lede">{total} stories from across Sri Lanka, summarised.</p>
      </div>
      <ul class="toc">{contents}</ul>
    </div>
    <p class="cover-hint" aria-hidden="true">Scroll <span>↓</span></p>
  </section>
{cards}

  <section class="card end" aria-label="End of edition">
    <div class="end-inner">
      <p class="eyebrow">End of edition</p>
      <h2 class="end-title">You're up to date.</h2>
      <p class="end-lede">The next edition arrives tomorrow at 10:00 AM.</p>
      <button type="button" class="to-top">Back to the top <span aria-hidden="true">↑</span></button>
      <p class="fine">{e(engine_note)} from stories published on <a href="{e(data['source'])}" target="_blank" rel="noopener">Newswire.lk</a> between {e(window_from)} and {e(window_to)}. Headlines, photos and reporting belong to Newswire. Summaries can contain errors, so read the full story at the source.</p>
    </div>
  </section>
</main>

<script>{JS}</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Styles & behaviour
# --------------------------------------------------------------------------- #
CSS = r"""
:root{
  --bg:#fbfbf9;--fg:#121212;--muted:#6f6e69;--line:#e7e6e1;--surface:#f1f0ec;
  --political:#8d153a;--finance:#00665f;--tech:#c25a06;--general:#7a7872;
  --bar:64px;--pad:clamp(20px,4vw,64px);
  --serif:"Instrument Serif",Georgia,"Times New Roman",serif;
  --sans:"Instrument Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f0f0e;--fg:#f3f2ee;--muted:#9c9a94;--line:#2a2a27;--surface:#1a1a18;
  --political:#f06b8f;--finance:#4fc3b4;--tech:#f5a057;--general:#a9a7a0;color-scheme:dark;}}

*,*::before,*::after{box-sizing:border-box}
html{scroll-snap-type:y mandatory;-webkit-text-size-adjust:100%}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:20px;line-height:1.5;-webkit-font-smoothing:antialiased}
img{display:block}
a{color:inherit}
button,select{font:inherit;color:inherit}
:focus-visible{outline:2px solid currentColor;outline-offset:4px}
.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
[hidden]{display:none!important}

.cat-political{--c:var(--political)}.cat-finance{--c:var(--finance)}.cat-tech{--c:var(--tech)}.cat-general{--c:var(--general)}

/* top bar */
.bar{position:fixed;inset:0 0 auto;z-index:10;height:var(--bar);display:flex;align-items:center;gap:24px;padding:0 var(--pad);
  background:color-mix(in srgb,var(--bg) 84%,transparent);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)}
.wordmark{font-family:var(--serif);font-size:26px;line-height:1;text-decoration:none;white-space:nowrap}
.bar-date{color:var(--muted);font-size:16px}
.filter{margin-left:auto;position:relative}
.filter::after{content:"";position:absolute;right:16px;top:50%;width:7px;height:7px;border:solid currentColor;border-width:0 1.5px 1.5px 0;
  transform:translateY(-70%) rotate(45deg);pointer-events:none}
.filter select{appearance:none;-webkit-appearance:none;background:transparent;border:1px solid var(--line);border-radius:99px;
  padding:9px 40px 9px 18px;font-size:16px;cursor:pointer}
.filter select:hover{border-color:var(--muted)}

/* every screen in the feed */
.card{position:relative;height:100vh;height:100dvh;scroll-snap-align:start;scroll-snap-stop:always;overflow:hidden;
  padding:calc(var(--bar) + 8px) var(--pad) clamp(24px,5vh,56px)}

/* shared type */
.eyebrow{margin:0 0 20px;font-size:15px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}

/* cover */
.cover{display:flex;flex-direction:column;justify-content:center}
.cover-inner{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:clamp(32px,6vw,120px);align-items:end}
.cover-title{margin:0;font-family:var(--serif);font-weight:400;font-size:clamp(64px,11vw,168px);line-height:.92;letter-spacing:-.02em}
.cover-title em{color:var(--muted)}
.cover-lede{margin:28px 0 0;font-size:clamp(22px,2.2vw,30px);color:var(--muted);max-width:28ch;line-height:1.35}
.toc{list-style:none;margin:0;padding:0;width:100%;max-width:560px;border-top:1px solid var(--line)}
.toc-item{all:unset;box-sizing:border-box;width:100%;display:flex;justify-content:space-between;align-items:baseline;gap:16px;
  padding:14px 2px;border-bottom:1px solid var(--line);cursor:pointer;font-size:clamp(22px,2vw,28px);transition:padding .25s}
.toc-item:hover{padding-left:10px}
.toc-item:focus-visible{outline:2px solid currentColor;outline-offset:2px}
.toc-name::before{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--c);margin-right:14px;transform:translateY(-2px)}
.toc-n{color:var(--muted);font-variant-numeric:tabular-nums}
.cover-hint{position:absolute;left:0;right:0;bottom:clamp(20px,4vh,40px);margin:0;text-align:center;font-size:15px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.cover-hint span{display:inline-block;margin-left:6px;animation:nudge 2s ease-in-out infinite}
@keyframes nudge{50%{transform:translateY(5px)}}

/* story cards */
.story{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:clamp(32px,4.5vw,80px);align-items:center}
.story-media{margin:0;align-self:stretch;min-height:0;overflow:hidden;border-radius:6px;background:var(--surface)}
.story-media img{width:100%;height:100%;object-fit:cover}
.story-text{min-width:0;max-width:40ch}
.meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin:0 0 22px;font-size:15px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.meta-cat{color:var(--c);font-weight:600}
.meta-cat::before{content:"";display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--c);margin-right:10px;transform:translateY(-1px)}
.meta-label{border:1px solid var(--line);border-radius:99px;padding:1px 10px;font-size:13px}
.count{margin-left:auto;font-variant-numeric:tabular-nums}
.story-title{margin:0 0 22px;font-family:var(--serif);font-weight:400;font-size:clamp(40px,3.9vw,68px);line-height:1.04;letter-spacing:-.01em;
  text-wrap:balance;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:5;line-clamp:5;overflow:hidden}
.story-summary{margin:0 0 28px;font-size:clamp(20px,1.5vw,25px);line-height:1.55;color:color-mix(in srgb,var(--fg) 82%,var(--bg));
  display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:7;line-clamp:7;overflow:hidden}
.story-link{display:inline-flex;gap:8px;font-size:18px;text-decoration:none;border-bottom:1px solid currentColor;padding-bottom:2px}
.story-link span{transition:transform .25s}
.story-link:hover span{transform:translateX(4px)}
.story--text{grid-template-columns:1fr;justify-items:start}
.story--text .story-text{max-width:24ch}
.story--text .story-title{font-size:clamp(48px,6vw,96px)}

/* end card */
.end{display:flex;align-items:center}
.end-inner{max-width:760px}
.end-title{margin:0;font-family:var(--serif);font-weight:400;font-size:clamp(56px,8vw,120px);line-height:.95;letter-spacing:-.02em}
.end-lede{margin:24px 0 36px;font-size:clamp(22px,2vw,28px);color:var(--muted)}
.to-top{all:unset;cursor:pointer;font-size:20px;border-bottom:1px solid currentColor;padding-bottom:2px}
.to-top:focus-visible{outline:2px solid currentColor;outline-offset:4px}
.fine{margin:56px 0 0;font-size:15px;line-height:1.6;color:var(--muted);max-width:60ch}

/* gentle reveal as each card scrolls in. Scroll-driven, so content is never hidden
   if the browser lacks support or JavaScript is off. */
@supports (animation-timeline: view()){
  @media (prefers-reduced-motion:no-preference){
    .story .story-text>*{animation:rise linear both;animation-timeline:view();animation-range:entry 20% entry 100%}
    .story .story-text>:nth-child(2){animation-range:entry 30% entry 100%}
    .story .story-text>:nth-child(3){animation-range:entry 40% entry 100%}
    .story .story-text>:nth-child(4){animation-range:entry 50% entry 100%}
    .story .story-media img{animation:settle linear both;animation-timeline:view();animation-range:entry 0% entry 100%}
  }
}
@keyframes rise{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}
@keyframes settle{from{transform:scale(1.06)}to{transform:none}}

/* portrait / narrow: image on top, text below, still one screen per story */
@media (max-width:860px),(orientation:portrait){
  :root{--bar:58px}
  body{font-size:19px}
  .bar{gap:12px}
  .wordmark{font-size:22px}
  .bar-date{display:none}
  .filter select{padding:8px 36px 8px 14px;font-size:15px}
  .card{padding:calc(var(--bar) + 4px) 20px max(24px,env(safe-area-inset-bottom))}
  .story{grid-template-columns:1fr;grid-template-rows:minmax(0,1fr) auto;gap:22px;align-items:stretch}
  .story-media{border-radius:4px}
  .story-text{max-width:none}
  .meta{margin-bottom:14px;font-size:13px;gap:6px 12px}
  .story-title{font-size:clamp(30px,8vw,44px);margin-bottom:14px;-webkit-line-clamp:4;line-clamp:4}
  .story-summary{font-size:19px;margin-bottom:18px;-webkit-line-clamp:6;line-clamp:6}
  .story-link{font-size:17px}
  .story--text{grid-template-rows:1fr;align-items:center}
  .story--text .story-title{font-size:clamp(40px,11vw,60px);-webkit-line-clamp:7;line-clamp:7}
  .cover-inner{grid-template-columns:1fr;gap:28px;align-items:start}
  .cover-lede{margin:22px 0 0}
  .toc-item{padding:12px 2px}
}
@media (max-height:700px) and ((max-width:860px) or (orientation:portrait)){
  .story-summary{-webkit-line-clamp:4;line-clamp:4}
  .story-title{-webkit-line-clamp:3;line-clamp:3}
}
"""

JS = r"""
(function () {
  var stories = Array.prototype.slice.call(document.querySelectorAll(".story"));
  var select = document.getElementById("filter");
  var pad = function (n) { return (n < 10 ? "0" : "") + n; };

  function show(cat, jump) {
    stories.forEach(function (s) { s.hidden = !(cat === "all" || s.dataset.cat === cat); });
    var visible = stories.filter(function (s) { return !s.hidden; });
    visible.forEach(function (s, i) { s.querySelector(".count").textContent = pad(i + 1) + " / " + pad(visible.length); });
    select.value = cat;
    if (jump) (visible[0] || document.querySelector(".end")).scrollIntoView();
  }

  select.addEventListener("change", function () { show(select.value, true); });
  document.querySelectorAll("[data-go]").forEach(function (b) {
    b.addEventListener("click", function () { show(b.dataset.go, true); });
  });
  document.querySelector(".to-top").addEventListener("click", function () {
    document.getElementById("top").scrollIntoView();
  });

})();
"""

HEADERS_FILE = """/images/*
  Cache-Control: public, max-age=31536000, immutable
/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
"""


# --------------------------------------------------------------------------- #
def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR / "latest.json"
    if not src.exists():
        print(f"No data at {src}. Run scraper.py first.", file=sys.stderr)
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))

    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir()

    # copy only the images the page shows (one per story)
    for a in data["articles"]:
        img = a["images"][0] if a["images"] else None
        if img and img["src"] and (DATA_DIR / img["src"]).exists():
            dest = SITE_DIR / img["src"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(DATA_DIR / img["src"], dest)
        elif img:
            img["src"] = None  # not downloaded on this machine; fall back to the original URL

    (SITE_DIR / "index.html").write_text(build_html(data), encoding="utf-8")
    public = {k: v for k, v in data.items() if k != "articles"}
    public["articles"] = [
        {k: a[k] for k in ("id", "title", "url", "published", "category", "summary", "source_categories", "tags")}
        | {"images": [{"src": img_src(i), "alt": i["alt"]} for i in a["images"][:1]]}
        for a in data["articles"]
    ]
    (SITE_DIR / "news.json").write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
    (SITE_DIR / "_headers").write_text(HEADERS_FILE, encoding="utf-8")

    n_files = sum(1 for p in SITE_DIR.rglob("*") if p.is_file())
    size_mb = sum(p.stat().st_size for p in SITE_DIR.rglob("*") if p.is_file()) / 1e6
    print(f"Built {SITE_DIR.relative_to(ROOT)}/ - {len(data['articles'])} stories, {n_files} files, {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
