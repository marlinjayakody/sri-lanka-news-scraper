#!/usr/bin/env python3
"""Build the static news site from the scraped data.

Reads   data/latest.json (written by scraper.py)
Writes  site/index.html, site/news.json, site/images/..., site/_headers

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

CATEGORY_META = {
    "Political": {"slug": "political", "blurb": "Government, parliament, parties & diplomacy"},
    "Finance": {"slug": "finance", "blurb": "Economy, markets, the rupee & business"},
    "Tech": {"slug": "tech", "blurb": "Technology, digital, telecoms & innovation"},
    "General": {"slug": "general", "blurb": "Everything else making news today"},
}
SOURCE_LABELS = {"Bizwire": "Press release", "International": "World", "Lead Story": "Lead story"}


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
    out = []
    for sc in a.get("source_categories", []):
        if sc in SOURCE_LABELS and sc != "Lead Story":
            out.append(SOURCE_LABELS[sc])
    return out


def pick_hero(articles: list[dict]) -> dict | None:
    with_img = [a for a in articles if a["images"]]
    for pool in ([a for a in with_img if a["is_lead"]],
                 [a for a in with_img if a["category"] in ("Political", "Finance")], with_img):
        if pool:
            return pool[0]
    return articles[0] if articles else None


# --------------------------------------------------------------------------- #
# Markup
# --------------------------------------------------------------------------- #
def render_card(a: dict, i: int, edition: str) -> str:
    slug = CATEGORY_META[a["category"]]["slug"]
    src = img_src(a["images"][0] if a["images"] else None)
    figure = (
        f'<figure class="card-media"><img src="{e(src)}" alt="{e(a["images"][0]["alt"])}" loading="lazy" decoding="async"></figure>'
        if src else '<figure class="card-media card-media--empty" aria-hidden="true"><span>NW</span></figure>'
    )
    extra = len(a["images"]) - 1
    badge = f'<span class="photo-count" title="{extra + 1} photos">+{extra}</span>' if extra > 0 else ""
    chips = "".join(f'<span class="chip">{e(l)}</span>' for l in labels_for(a))
    search = f'{a["title"]} {a["summary"]} {" ".join(a.get("tags", []))}'.lower()
    return f"""
      <article class="card cat-{slug}" data-id="{a['id']}" data-cat="{e(a['category'])}" data-search="{e(search)}" style="--i:{min(i, 14)}">
        <div class="card-media-wrap">{figure}{badge}</div>
        <div class="card-body">
          <p class="kicker"><span class="kicker-cat">{e(a['category'])}</span><time datetime="{e(a['published'])}">{e(fmt_time(a['published'], edition))}</time>{chips}</p>
          <h3 class="card-title"><button type="button" class="open-story" data-id="{a['id']}">{e(a['title'])}</button></h3>
          <p class="card-summary">{e(a['summary'])}</p>
          <a class="source-link" href="{e(a['url'])}" target="_blank" rel="noopener">Read on Newswire <span aria-hidden="true">↗</span></a>
        </div>
      </article>"""


def render_hero(a: dict, edition: str) -> str:
    slug = CATEGORY_META[a["category"]]["slug"]
    img = a["images"][0]
    return f"""
    <article class="hero cat-{slug}" data-id="{a['id']}" data-cat="{e(a['category'])}" data-search="{e((a['title'] + ' ' + a['summary']).lower())}">
      <figure class="hero-media"><img src="{e(img_src(img))}" alt="{e(img['alt'])}" fetchpriority="high"></figure>
      <div class="hero-body">
        <p class="kicker"><span class="kicker-cat">{e(a['category'])}</span><span class="kicker-lead">Lead story</span><time datetime="{e(a['published'])}">{e(fmt_time(a['published'], edition))}</time></p>
        <h2 class="hero-title"><button type="button" class="open-story" data-id="{a['id']}">{e(a['title'])}</button></h2>
        <p class="hero-summary">{e(a['summary'])}</p>
        <a class="source-link" href="{e(a['url'])}" target="_blank" rel="noopener">Read the full story on Newswire <span aria-hidden="true">↗</span></a>
      </div>
    </article>"""


def render_brief(items: list[dict], edition: str) -> str:
    rows = []
    for n, a in enumerate(items, 1):
        slug = CATEGORY_META[a["category"]]["slug"]
        rows.append(f"""
        <li class="brief-item cat-{slug}" data-id="{a['id']}" data-cat="{e(a['category'])}" data-search="{e((a['title'] + ' ' + a['summary']).lower())}">
          <span class="brief-num">{n:02d}</span>
          <div>
            <p class="kicker"><span class="kicker-cat">{e(a['category'])}</span><time datetime="{e(a['published'])}">{e(fmt_time(a['published'], edition))}</time></p>
            <h3 class="brief-title"><button type="button" class="open-story" data-id="{a['id']}">{e(a['title'])}</button></h3>
          </div>
        </li>""")
    return f'<aside class="brief" aria-labelledby="brief-h"><h2 id="brief-h" class="rail-heading">Also leading today</h2><ol>{"".join(rows)}</ol></aside>'


def build_html(data: dict) -> str:
    edition = data["edition_date"]
    articles = data["articles"]
    order = data["categories"]
    counts = data["counts"]
    edition_dt = datetime.fromisoformat(data["generated_at"])
    date_long = edition_dt.strftime("%A, %-d %B %Y")
    hero = pick_hero(articles)
    rest = [a for a in articles if a is not hero]
    leads = [a for a in rest if a["is_lead"]]
    brief = (leads + [a for a in rest if not a["is_lead"]])[:5]

    tabs = [f'<button type="button" class="tab is-active" data-filter="all" aria-pressed="true">All <span class="tab-count">{len(articles)}</span></button>']
    for c in order:
        if counts.get(c):
            tabs.append(f'<button type="button" class="tab tab-{CATEGORY_META[c]["slug"]}" data-filter="{e(c)}" aria-pressed="false">{e(c)} <span class="tab-count">{counts[c]}</span></button>')

    sections = []
    for c in order:
        items = [a for a in articles if a["category"] == c]
        if not items:
            continue
        meta = CATEGORY_META[c]
        cards = "".join(render_card(a, i, edition) for i, a in enumerate(items))
        sections.append(f"""
    <section class="section cat-{meta['slug']}" data-section="{e(c)}" id="{meta['slug']}" aria-labelledby="h-{meta['slug']}">
      <header class="section-head">
        <h2 id="h-{meta['slug']}">{e(c)}</h2>
        <p>{e(meta['blurb'])}</p>
        <span class="section-count">{len(items)} {'story' if len(items) == 1 else 'stories'}</span>
      </header>
      <div class="grid">{cards}
      </div>
    </section>""")

    ticker_items = "".join(
        f'<li><span class="t-cat cat-{CATEGORY_META[a["category"]]["slug"]}">{e(a["category"])}</span>{e(a["title"])}</li>'
        for a in articles[:14]
    )

    # Data for the story modal - summaries and images only, never the full text.
    modal_data = {
        str(a["id"]): {
            "title": a["title"], "summary": a["summary"], "category": a["category"], "url": a["url"],
            "time": fmt_time(a["published"], edition), "labels": labels_for(a), "tags": a.get("tags", [])[:6],
            "images": [{"src": img_src(i), "alt": i["alt"]} for i in a["images"]],
        }
        for a in articles
    }
    modal_json = json.dumps(modal_data, ensure_ascii=False).replace("</", "<\\/")

    engine_note = {
        "claude": "Summaries and categories written by Claude",
        "mixed": "Summaries and categories written by Claude, with an automatic fallback for some stories",
    }.get(data["enrichment"], "Summaries and categories generated automatically")
    window_from = datetime.fromisoformat(data["window"]["from"]).strftime("%-d %b, %-I:%M %p")
    window_to = datetime.fromisoformat(data["window"]["to"]).strftime("%-d %b, %-I:%M %p")
    og_image = img_src(hero["images"][0]) if hero and hero["images"] else ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(SITE_TITLE)} · {e(date_long)}</title>
<meta name="description" content="{e(TAGLINE)}: {len(articles)} stories across politics, finance and tech for {e(date_long)}.">
<meta property="og:title" content="{e(SITE_TITLE)} · {e(date_long)}">
<meta property="og:description" content="{e(hero['title'] if hero else TAGLINE)}">
<meta property="og:image" content="{e(og_image)}">
<meta name="theme-color" content="#f4efe6" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#14110d" media="(prefers-color-scheme: dark)">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='10' fill='%238d153a'/%3E%3Ctext x='32' y='45' font-family='Georgia,serif' font-size='38' font-weight='700' fill='%23f4efe6' text-anchor='middle'%3EL%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:ital,opsz,wght@0,6..96,500..900;1,6..96,500..900&family=IBM+Plex+Mono:wght@400;500;600&family=Newsreader:ital,opsz,wght@0,6..72,300..800;1,6..72,300..800&display=swap" rel="stylesheet">
<style>{CSS}</style>
<script>
  try {{ var t = localStorage.getItem("ldd-theme"); if (t) document.documentElement.dataset.theme = t; }} catch (_) {{}}
</script>
</head>
<body>
<a class="skip" href="#main">Skip to stories</a>

<div class="topbar">
  <div class="wrap topbar-inner">
    <span>{e(date_long)}</span>
    <span class="topbar-mid">Colombo · Morning edition</span>
    <button type="button" class="theme-toggle" aria-label="Toggle dark mode"><span class="sun">☀</span><span class="moon">☾</span></button>
  </div>
</div>

<header class="masthead wrap">
  <p class="masthead-kicker">{len(articles)} stories · {counts.get('Political', 0)} political · {counts.get('Finance', 0)} finance · {counts.get('Tech', 0)} tech</p>
  <h1 class="masthead-title">{e(SITE_TITLE)}</h1>
  <p class="masthead-tag">{e(TAGLINE)}. Sourced from <a href="{e(data['source'])}" target="_blank" rel="noopener">Newswire.lk</a></p>
</header>

<div class="ticker" aria-label="Latest headlines">
  <span class="ticker-label">The wire</span>
  <div class="ticker-track"><ul>{ticker_items}</ul><ul aria-hidden="true">{ticker_items}</ul></div>
</div>

<nav class="filters" aria-label="Filter stories">
  <div class="wrap filters-inner">
    <div class="tabs" role="toolbar">{''.join(tabs)}</div>
    <label class="search"><span class="visually-hidden">Search stories</span>
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input type="search" id="q" placeholder="Search today's stories" autocomplete="off">
    </label>
  </div>
</nav>

<main id="main" class="wrap">
  <div class="front">
    {render_hero(hero, edition) if hero else ''}
    {render_brief(brief, edition) if brief else ''}
  </div>
  {''.join(sections)}
  <p class="empty" hidden>No stories match your search.</p>
</main>

<footer class="footer">
  <div class="wrap footer-inner">
    <p class="footer-title">{e(SITE_TITLE)}</p>
    <p>{e(engine_note)} from stories published on <a href="{e(data['source'])}" target="_blank" rel="noopener">Newswire.lk</a> between {e(window_from)} and {e(window_to)}. Headlines, images and original reporting belong to Newswire; summaries may contain errors, so always read the full story at the source.</p>
    <p class="footer-meta">Built {e(edition_dt.strftime('%-d %B %Y at %-I:%M %p'))} Sri Lanka time · Updated daily at 10:00 AM</p>
  </div>
</footer>

<dialog id="story" class="story" aria-labelledby="story-title">
  <form method="dialog"><button class="story-close" aria-label="Close">×</button></form>
  <div class="story-inner"></div>
</dialog>

<script type="application/json" id="story-data">{modal_json}</script>
<script>{JS}</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Styles & behaviour
# --------------------------------------------------------------------------- #
CSS = r"""
:root{
  --paper:#f4efe6;--paper-2:#ebe3d4;--card:#fbf8f2;--ink:#1b1712;--ink-soft:#5d5447;--ink-faint:#8c8273;
  --rule:#1b1712;--rule-soft:#d6ccbb;
  --political:#8d153a;--finance:#00534e;--tech:#c25a06;--general:#6b6255;--gold:#e9a521;
  --shadow:0 1px 0 rgba(27,23,18,.06),0 10px 30px -12px rgba(27,23,18,.25);
  --serif:"Newsreader",Georgia,"Times New Roman",serif;--display:"Bodoni Moda","Didot",Georgia,serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --grain:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 .55 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.35'/%3E%3C/svg%3E");
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#14110d;--paper-2:#1c1813;--card:#1d1914;--ink:#efe7d8;--ink-soft:#b3a893;--ink-faint:#7f7564;
  --rule:#efe7d8;--rule-soft:#3a3329;--political:#e45d84;--finance:#3cbcab;--tech:#f39a46;--general:#a89d89;
  --shadow:0 1px 0 rgba(0,0,0,.4),0 14px 34px -14px rgba(0,0,0,.8);color-scheme:dark;}}
:root[data-theme="dark"]{
  --paper:#14110d;--paper-2:#1c1813;--card:#1d1914;--ink:#efe7d8;--ink-soft:#b3a893;--ink-faint:#7f7564;
  --rule:#efe7d8;--rule-soft:#3a3329;--political:#e45d84;--finance:#3cbcab;--tech:#f39a46;--general:#a89d89;
  --shadow:0 1px 0 rgba(0,0,0,.4),0 14px 34px -14px rgba(0,0,0,.8);color-scheme:dark;}

*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);font-size:17px;line-height:1.55;
  font-optical-sizing:auto;-webkit-font-smoothing:antialiased;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;background-image:var(--grain);pointer-events:none;z-index:100;mix-blend-mode:multiply;opacity:.5}
:root[data-theme="dark"] body::before{mix-blend-mode:screen;opacity:.18}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) body::before{mix-blend-mode:screen;opacity:.18}}
a{color:inherit}
img{display:block;max-width:100%}
button{font:inherit;color:inherit}
.wrap{width:min(1240px,100% - 32px);margin-inline:auto}
.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:-999px;top:8px;background:var(--ink);color:var(--paper);padding:8px 14px;z-index:200}
.skip:focus{left:16px}
:focus-visible{outline:2px solid var(--gold);outline-offset:3px}

/* category colour plumbing */
.cat-political{--c:var(--political)}.cat-finance{--c:var(--finance)}.cat-tech{--c:var(--tech)}.cat-general{--c:var(--general)}

/* top bar */
.topbar{border-bottom:1px solid var(--rule-soft);font-family:var(--mono);font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-soft)}
.topbar-inner{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:38px}
.theme-toggle{background:none;border:1px solid var(--rule-soft);border-radius:99px;padding:2px 10px;cursor:pointer;display:flex;gap:8px;font-size:13px}
.theme-toggle .moon{opacity:.35}.theme-toggle .sun{opacity:1}
:root[data-theme="dark"] .theme-toggle .moon{opacity:1}:root[data-theme="dark"] .theme-toggle .sun{opacity:.35}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .theme-toggle .moon{opacity:1}:root:not([data-theme="light"]) .theme-toggle .sun{opacity:.35}}

/* masthead */
.masthead{text-align:center;padding:34px 0 22px;border-bottom:4px double var(--rule)}
.masthead-kicker{margin:0 0 6px;font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-soft)}
.masthead-title{margin:0;font-family:var(--display);font-weight:900;font-size:clamp(46px,9.2vw,124px);line-height:.92;letter-spacing:-.02em;
  font-variation-settings:"opsz" 96;animation:rise .9s cubic-bezier(.2,.7,.2,1) both}
.masthead-tag{margin:14px 0 0;font-style:italic;font-size:clamp(16px,2vw,19px);color:var(--ink-soft)}
.masthead-tag a{color:var(--political);text-decoration-thickness:1px;text-underline-offset:3px}

/* ticker */
.ticker{display:flex;align-items:stretch;border-block:1px solid #000;background:#16120e;color:#f4efe6;font-family:var(--mono);font-size:13px;overflow:hidden}
.ticker-label{flex:none;padding:9px 14px;background:var(--political);color:#fff;text-transform:uppercase;letter-spacing:.12em;font-weight:600;position:relative;z-index:1}
.ticker-track{display:flex;overflow:hidden;-webkit-mask-image:linear-gradient(90deg,transparent,#000 40px,#000 calc(100% - 40px),transparent);mask-image:linear-gradient(90deg,transparent,#000 40px,#000 calc(100% - 40px),transparent)}
.ticker ul{display:flex;gap:42px;margin:0;padding:9px 21px;list-style:none;white-space:nowrap;animation:tick 110s linear infinite;flex:none}
.ticker:hover ul{animation-play-state:paused}
.ticker li{display:flex;gap:10px;align-items:center}
.t-cat{font-size:10.5px;text-transform:uppercase;letter-spacing:.1em;padding:1px 6px;border:1px solid currentColor;color:var(--c)}
:root .ticker .t-cat.cat-political{color:#ff8fae}:root .ticker .t-cat.cat-finance{color:#5fd6c4}:root .ticker .t-cat.cat-tech{color:#ffb36b}:root .ticker .t-cat.cat-general{color:#cfc4b0}
@keyframes tick{to{transform:translateX(-100%)}}

/* filters */
.filters{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--paper) 88%,transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--rule-soft)}
.filters-inner{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 0}
.tabs{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;margin:-4px;padding:4px}
.tabs::-webkit-scrollbar{display:none}
.tab{flex:none;cursor:pointer;background:transparent;border:1px solid var(--rule-soft);border-radius:99px;padding:6px 14px;font-family:var(--mono);font-size:12.5px;
  letter-spacing:.05em;text-transform:uppercase;transition:background .2s,color .2s,border-color .2s}
.tab:hover{border-color:var(--ink)}
.tab-count{opacity:.6;margin-left:4px}
.tab.is-active{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.tab-political.is-active{background:var(--political);border-color:var(--political);color:#fff}
.tab-finance.is-active{background:var(--finance);border-color:var(--finance);color:#fff}
.tab-tech.is-active{background:var(--tech);border-color:var(--tech);color:#fff}
.tab-general.is-active{background:var(--general);border-color:var(--general);color:#fff}
.search{display:flex;align-items:center;gap:8px;border-bottom:1.5px solid var(--ink);padding:4px 2px;min-width:0;flex:0 1 260px}
.search svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;flex:none}
.search input{border:0;background:transparent;font:inherit;font-size:15px;color:var(--ink);width:100%;outline:none;min-width:0}
.search input::placeholder{color:var(--ink-faint);font-style:italic}

/* shared bits */
.kicker{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:0 0 8px;font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-faint)}
.kicker-cat{color:var(--c);font-weight:600}
.kicker-cat::before{content:"";display:inline-block;width:8px;height:8px;background:var(--c);margin-right:7px;transform:translateY(-1px)}
.kicker-lead{color:var(--gold);font-weight:600}
.chip{border:1px solid var(--rule-soft);padding:0 6px;border-radius:3px;font-size:10.5px}
.open-story{all:unset;cursor:pointer}
.open-story::after{content:"";position:absolute;inset:0;z-index:1}
.open-story:focus-visible{outline:none}
.card:has(.open-story:focus-visible),.hero:has(.open-story:focus-visible),.brief-item:has(.open-story:focus-visible){outline:2px solid var(--gold);outline-offset:4px}
.source-link{position:relative;z-index:2;display:inline-flex;gap:4px;font-family:var(--mono);font-size:12px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--c);text-decoration:none;border-bottom:1px solid transparent;transition:border-color .2s}
.source-link:hover{border-bottom-color:currentColor}

/* front page */
.front{display:grid;grid-template-columns:minmax(0,2.15fr) minmax(0,1fr);gap:0;margin:30px 0 10px;border-bottom:1px solid var(--rule)}
.hero{position:relative;padding:0 30px 30px 0;border-right:1px solid var(--rule-soft);animation:rise .8s .1s cubic-bezier(.2,.7,.2,1) both}
.hero-media{margin:0 0 20px;overflow:hidden;aspect-ratio:16/9;background:var(--paper-2)}
.hero-media img{width:100%;height:100%;object-fit:cover;transition:transform 1.2s cubic-bezier(.2,.7,.2,1)}
.hero:hover .hero-media img{transform:scale(1.025)}
.hero-title{margin:0 0 12px;font-weight:700;font-size:clamp(28px,3.6vw,46px);line-height:1.06;letter-spacing:-.015em;font-variation-settings:"opsz" 72;text-wrap:balance}
.hero:hover .hero-title{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:6px;text-decoration-color:var(--c)}
.hero-summary{margin:0 0 16px;font-size:clamp(17px,1.6vw,20px);line-height:1.5;color:var(--ink-soft);max-width:62ch}
.hero-summary::first-letter{float:left;font-family:var(--display);font-weight:800;font-size:3.4em;line-height:.8;padding:6px 8px 0 0;color:var(--c)}
.brief{padding:0 0 26px 28px;animation:rise .8s .25s cubic-bezier(.2,.7,.2,1) both}
.rail-heading{margin:0 0 6px;font-family:var(--mono);font-size:12px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;padding-bottom:10px;border-bottom:2px solid var(--rule)}
.brief ol{list-style:none;margin:0;padding:0}
.brief-item{position:relative;display:grid;grid-template-columns:auto 1fr;gap:14px;padding:16px 0;border-bottom:1px solid var(--rule-soft)}
.brief-item:last-child{border-bottom:0}
.brief-num{font-family:var(--display);font-style:italic;font-weight:700;font-size:30px;line-height:1;color:var(--c);min-width:1.4em}
.brief-title{margin:0;font-size:18.5px;line-height:1.25;font-weight:600}
.brief-item:hover .brief-title{text-decoration:underline;text-decoration-color:var(--c);text-underline-offset:4px}

/* sections */
.section{padding:44px 0 10px}
.section-head{display:grid;grid-template-columns:auto 1fr auto;align-items:baseline;gap:6px 18px;border-top:3px solid var(--c);padding-top:12px;margin-bottom:24px}
.section-head h2{margin:0;font-family:var(--display);font-weight:800;font-style:italic;font-size:clamp(32px,4.4vw,52px);line-height:1;color:var(--c);letter-spacing:-.01em}
.section-head p{margin:0;font-style:italic;color:var(--ink-soft)}
.section-count{font-family:var(--mono);font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-faint)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr));gap:30px 26px}

/* cards */
.card{position:relative;display:flex;flex-direction:column;animation:rise .7s calc(var(--i,0) * 45ms + 150ms) cubic-bezier(.2,.7,.2,1) both}
.card-media-wrap{position:relative;margin-bottom:14px}
.card-media{margin:0;aspect-ratio:3/2;overflow:hidden;background:var(--paper-2);box-shadow:var(--shadow)}
.card-media img{width:100%;height:100%;object-fit:cover;filter:saturate(.92);transition:transform .8s cubic-bezier(.2,.7,.2,1),filter .5s}
.card:hover .card-media img{transform:scale(1.045);filter:saturate(1.08)}
.card-media--empty{display:grid;place-items:center;background:repeating-linear-gradient(-45deg,var(--paper-2) 0 10px,transparent 10px 20px)}
.card-media--empty span{font-family:var(--display);font-weight:900;font-size:40px;color:var(--c);opacity:.5}
.photo-count{position:absolute;right:10px;bottom:10px;background:rgba(20,17,13,.78);color:#fff;font-family:var(--mono);font-size:11px;padding:2px 7px;border-radius:3px}
.card-media-wrap::after{content:"";position:absolute;left:0;top:0;height:4px;width:44px;background:var(--c)}
.card-title{margin:0 0 8px;font-size:21px;line-height:1.2;font-weight:650;letter-spacing:-.005em;text-wrap:balance}
.card:hover .card-title{text-decoration:underline;text-decoration-color:var(--c);text-decoration-thickness:1.5px;text-underline-offset:4px}
.card-summary{margin:0 0 12px;color:var(--ink-soft);font-size:16px;line-height:1.5;flex:1;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:5;line-clamp:5;overflow:hidden;align-self:stretch}
.card-body{display:flex;flex-direction:column;flex:1;align-items:flex-start}

.empty{text-align:center;font-style:italic;color:var(--ink-soft);padding:60px 0;font-size:20px}

/* footer */
.footer{margin-top:60px;border-top:4px double var(--rule);padding:30px 0 50px;color:var(--ink-soft);font-size:15px}
.footer-inner{max-width:760px;text-align:center}
.footer-title{font-family:var(--display);font-weight:900;font-size:28px;color:var(--ink);margin:0 0 8px}
.footer-meta{font-family:var(--mono);font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-faint)}

/* story dialog */
.story{width:min(860px,100% - 24px);max-height:min(92vh,980px);padding:0;border:0;background:var(--card);color:var(--ink);box-shadow:0 30px 80px -20px rgba(0,0,0,.55)}
.story::backdrop{background:rgba(20,17,13,.62);backdrop-filter:blur(3px)}
.story[open]{animation:pop .35s cubic-bezier(.2,.7,.2,1)}
.story form{position:sticky;top:0;height:0;z-index:3}
.story-close{position:absolute;right:12px;top:12px;box-shadow:var(--shadow);width:38px;height:38px;border-radius:50%;border:1px solid var(--rule-soft);background:var(--card);font-size:24px;line-height:1;cursor:pointer}
.story-inner{padding:0 0 28px}
.story-media{margin:0;background:var(--paper-2)}
.story-media img{width:100%;max-height:520px;object-fit:contain;background:#0d0b09}
.story-thumbs{display:flex;gap:8px;padding:10px 28px 0;overflow-x:auto}
.story-thumbs button{flex:none;width:84px;height:56px;padding:0;border:2px solid transparent;cursor:pointer;background:none;opacity:.7}
.story-thumbs button.is-active{border-color:var(--c);opacity:1}
.story-thumbs img{width:100%;height:100%;object-fit:cover}
.story-body{padding:22px 28px 0}
.story-body h2{margin:0 0 14px;font-size:clamp(26px,3.4vw,36px);line-height:1.1;font-weight:700;text-wrap:balance}
.story-body .story-summary{font-size:19px;line-height:1.55;margin:0 0 18px}
.story-tags{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 20px;padding:0;list-style:none}
.story-tags li{font-family:var(--mono);font-size:11px;letter-spacing:.05em;border:1px solid var(--rule-soft);padding:2px 8px;border-radius:99px;color:var(--ink-soft)}
.story-cta{display:inline-block;background:var(--c);color:#fff;text-decoration:none;font-family:var(--mono);font-size:13px;letter-spacing:.08em;text-transform:uppercase;padding:11px 18px}
.story-cta:hover{filter:brightness(1.1)}
.story-note{font-size:13.5px;font-style:italic;color:var(--ink-faint);margin:14px 0 0}

@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes pop{from{opacity:0;transform:translateY(16px) scale(.98)}to{opacity:1;transform:none}}

/* hidden states */
[hidden]{display:none!important}

@media (max-width:900px){
  .front{grid-template-columns:1fr}
  .hero{padding:0 0 24px;border-right:0;border-bottom:1px solid var(--rule-soft)}
  .brief{padding:20px 0 16px}
}
@media (max-width:640px){
  body{font-size:16px}
  .topbar-mid{display:none}
  .filters-inner{flex-direction:column;align-items:stretch;gap:8px}
  .search{flex-basis:auto}
  .section-head{grid-template-columns:1fr auto}
  .section-head p{grid-column:1/-1;grid-row:2}
  .story-body,.story-thumbs{padding-inline:18px}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
}
"""

JS = r"""
(function () {
  var data = JSON.parse(document.getElementById("story-data").textContent);
  var root = document.documentElement;
  var slugs = {Political: "political", Finance: "finance", Tech: "tech", General: "general"};

  // theme toggle
  document.querySelector(".theme-toggle").addEventListener("click", function () {
    var dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("ldd-theme", root.dataset.theme); } catch (_) {}
  });

  // filtering + search
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".tab"));
  var q = document.getElementById("q");
  var filter = "all";
  function apply() {
    var term = q.value.trim().toLowerCase();
    var anyVisible = false;
    document.querySelectorAll(".section").forEach(function (sec) {
      var catOk = filter === "all" || sec.dataset.section === filter;
      var shown = 0;
      sec.querySelectorAll(".card").forEach(function (card) {
        var ok = catOk && (!term || card.dataset.search.indexOf(term) !== -1);
        card.hidden = !ok;
        if (ok) shown++;
      });
      sec.hidden = shown === 0;
      if (shown) anyVisible = true;
    });
    var front = document.querySelector(".front");
    if (front) front.hidden = !(filter === "all" && !term);
    document.querySelector(".empty").hidden = anyVisible;
  }
  tabs.forEach(function (t) {
    t.addEventListener("click", function () {
      filter = t.dataset.filter;
      tabs.forEach(function (o) { var on = o === t; o.classList.toggle("is-active", on); o.setAttribute("aria-pressed", on); });
      apply();
      var target = filter === "all" ? document.getElementById("main") : document.querySelector('[data-section="' + filter + '"]');
      var nav = document.querySelector(".filters");
      if (target) window.scrollTo({top: target.getBoundingClientRect().top + window.scrollY - nav.offsetHeight - 8, behavior: "smooth"});
    });
  });
  q.addEventListener("input", apply);
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "/" && document.activeElement !== q && !dialog.open) { ev.preventDefault(); q.focus(); }
  });

  // story dialog
  var dialog = document.getElementById("story");
  var inner = dialog.querySelector(".story-inner");
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function open(id) {
    var s = data[id]; if (!s) return;
    dialog.className = "story cat-" + slugs[s.category];
    inner.textContent = "";
    if (s.images.length) {
      var fig = el("figure", "story-media"), big = el("img");
      big.src = s.images[0].src; big.alt = s.images[0].alt; fig.appendChild(big); inner.appendChild(fig);
      if (s.images.length > 1) {
        var strip = el("div", "story-thumbs");
        s.images.forEach(function (im, i) {
          var b = el("button"); b.type = "button"; b.setAttribute("aria-label", "Photo " + (i + 1));
          if (!i) b.classList.add("is-active");
          var t = el("img"); t.src = im.src; t.alt = ""; b.appendChild(t);
          b.addEventListener("click", function () {
            big.src = im.src; big.alt = im.alt;
            strip.querySelectorAll("button").forEach(function (o) { o.classList.toggle("is-active", o === b); });
          });
          strip.appendChild(b);
        });
        inner.appendChild(strip);
      }
    }
    var body = el("div", "story-body");
    var k = el("p", "kicker");
    k.appendChild(el("span", "kicker-cat", s.category));
    k.appendChild(el("time", null, s.time));
    s.labels.forEach(function (l) { k.appendChild(el("span", "chip", l)); });
    body.appendChild(k);
    var h = el("h2", null, s.title); h.id = "story-title"; body.appendChild(h);
    body.appendChild(el("p", "story-summary", s.summary));
    if (s.tags.length) {
      var ul = el("ul", "story-tags");
      s.tags.forEach(function (t) { ul.appendChild(el("li", null, "#" + t)); });
      body.appendChild(ul);
    }
    var a = el("a", "story-cta", "Read the full story on Newswire ↗");
    a.href = s.url; a.target = "_blank"; a.rel = "noopener"; body.appendChild(a);
    body.appendChild(el("p", "story-note", "Summary generated automatically. The original article, photos and reporting are by Newswire.lk."));
    inner.appendChild(body);
    dialog.showModal();
    dialog.scrollTop = 0;
  }
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest(".open-story");
    if (b) open(b.dataset.id);
  });
  dialog.addEventListener("click", function (ev) { if (ev.target === dialog) dialog.close(); });
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

    # copy only the images this edition uses
    for a in data["articles"]:
        for img in a["images"]:
            if img["src"]:
                dest = SITE_DIR / img["src"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(DATA_DIR / img["src"], dest)

    (SITE_DIR / "index.html").write_text(build_html(data), encoding="utf-8")
    public = {k: v for k, v in data.items() if k != "articles"}
    public["articles"] = [
        {k: a[k] for k in ("id", "title", "url", "published", "category", "summary", "source_categories", "tags")}
        | {"images": [{"src": img_src(i), "alt": i["alt"]} for i in a["images"]]}
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
