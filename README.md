# Sri Lanka News Scraper → Lanka Daily Digest

Every day at **10:00 Sri Lanka time**, GitHub Actions scrapes the last 24 hours of stories from
[newswire.lk](https://www.newswire.lk/), summarises them, sorts them into **Political / Finance / Tech**
(plus **General** for everything else), builds a static site and publishes it to Netlify:

**Live site:** https://lanka-daily-digest.netlify.app

```
scraper.py ──► data/<date>.json + data/images/ ──► build_site.py ──► site/ ──► deploy.sh ──► Netlify
  (enrich.py: summaries + categories)                                  (committed: data/*.json)
```

| File | What it does |
|---|---|
| `scraper.py` | Pulls stories via the WordPress REST API (RSS fallback): title, link, time, text, featured + in-article images. Downloads and resizes the images. |
| `enrich.py` | Summary + category for each story. Free offline keyword engine by default; uses Claude automatically when `ANTHROPIC_API_KEY` is set. |
| `build_site.py` | Turns `data/latest.json` into `site/index.html` (+ images, `news.json`). Publishes only summaries, never the full article text. |
| `make_icons.py` | Draws the "L." app icon and writes every size to `assets/` (browser tab, iPhone home screen, Android). Re-run after changing the design. |
| `deploy.sh` | Production deploy of `site/` with the Netlify CLI. |
| `run_daily.sh` | The whole pipeline, for running locally by hand (logs to `logs/`). |
| `.github/workflows/daily.yml` | The 10:00 schedule: scrape, build, commit the day's JSON, deploy. |

## One-time setup

Add these as repository secrets (**Settings → Secrets and variables → Actions → New repository secret**):

- `NETLIFY_AUTH_TOKEN` (required): create one at
  [Netlify → User settings → Applications → Personal access tokens](https://app.netlify.com/user/applications#personal-access-tokens).
- `ANTHROPIC_API_KEY` (optional): better summaries and categories from Claude (`claude-opus-5-5`, low effort, about 5 requests a day).

To run it now instead of waiting for 10:00, open **Actions → Daily news digest → Run workflow**.

## Running locally

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
npm install                        # Netlify CLI, only needed for deploys
cp .env.example .env               # add NETLIFY_AUTH_TOKEN, or run `npx netlify login`
.venv/bin/python scraper.py        # options: --since-midnight, --hours 12, --no-llm
.venv/bin/python build_site.py
./deploy.sh
```

## Notes

- GitHub's scheduler can run a few minutes late at busy times. Scheduled workflows stop after 60 days with no repo activity, but the daily commit keeps this one alive.
- If a run finds no stories (for example newswire.lk is down), it stops before deploying, so the previous edition stays live.
- Tune the keyword categories in `KEYWORDS` in `enrich.py`, and the site name with `SITE_TITLE`.
- Headlines, photos and reporting belong to Newswire.lk. The site shows short summaries and links every story back to the source. `data/*.json` holds the full text for re-processing, so keep this repository private.
