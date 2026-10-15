"""Summarise and categorise articles.

Two engines:
  * keywords (default, offline, free): extractive summary + weighted keyword classifier.
  * claude (used automatically when ANTHROPIC_API_KEY is set): Claude writes the
    summary and picks the category. Any article Claude can't handle falls back to
    the keyword engine, so a run never fails because of the LLM.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter

log = logging.getLogger("enrich")

CATEGORIES = ["Political", "Finance", "Tech"]
FALLBACK_CATEGORY = "General"  # stories that are none of the three (weather, crime, sport...)

# --------------------------------------------------------------------------- #
# Keyword classifier
# --------------------------------------------------------------------------- #
# keyword -> weight. All-caps acronyms are matched case-sensitively so "MP" or
# "AI" don't fire on ordinary words.
KEYWORDS: dict[str, dict[str, int]] = {
    "Political": {
        "parliament": 3, "parliamentary": 3, "cabinet": 3, "election": 3, "elections": 3,
        "electoral": 3, "president": 3, "presidential": 3, "prime minister": 3, "pm": 1,
        "minister": 2, "deputy minister": 2, "state minister": 2, "ministry": 1, "MP": 3,
        "MPs": 3, "government": 1, "political": 3, "politician": 3, "politics": 3,
        "opposition": 3, "speaker": 2, "SJB": 3, "NPP": 3, "SLPP": 3, "UNP": 3, "JVP": 3,
        "SLFP": 3, "ITAK": 3, "TNA": 3, "Samagi Jana Balawegaya": 3,
        "National People's Power": 3, "Podujana": 3, "Rajapaksa": 3, "Wickremesinghe": 3,
        "Premadasa": 3, "Sajith": 3, "Namal": 3, "Ranil": 3, "Anura": 3, "Dissanayake": 2,
        "Amarasuriya": 3, "Vijitha Herath": 3, "Gammanpila": 3, "Kiriella": 3,
        "Mano Ganesan": 3, "bill": 1, "amendment": 2, "constitution": 3, "constitutional": 3,
        "gazette": 1, "diplomatic": 3, "diplomat": 3, "bilateral": 3, "embassy": 1,
        "ambassador": 2, "high commissioner": 2, "foreign minister": 3, "foreign affairs": 3,
        "summit": 2, "BIMSTEC": 3, "Commonwealth": 2, "United Nations": 2, "UN": 2,
        "policy": 1, "provincial council": 3, "local government": 3, "pradeshiya sabha": 3,
        "municipal council": 3, "mayor": 2, "governor": 1, "referendum": 3, "vote": 2,
        "voting": 2, "campaign": 1, "select committee": 3, "COPE": 3, "COPA": 3,
        "election law": 3, "sanctions": 2, "geopolitical": 3, "delegation": 2, "pledge": 1,
        "maritime security": 2, "joint statement": 3, "foreign policy": 3, "national security": 2,
    },
    "Finance": {
        "rupee": 3, "dollar": 2, "USD": 2, "exchange rate": 3, "CBSL": 3, "central bank": 3,
        "inflation": 3, "interest rate": 3, "policy rate": 3, "budget": 3, "tax": 3, "taxes": 3,
        "taxpayer": 3, "taxpayers": 3, "income tax": 3, "VAT": 3, "revenue": 2,
        "inland revenue": 3, "customs": 2, "export": 3, "exports": 3, "import": 2,
        "imports": 2, "trade": 2, "investment": 3, "investor": 3, "investors": 3, "stock": 2,
        "shares": 2, "CSE": 3, "Colombo Stock Exchange": 3, "ASPI": 3, "bank": 2,
        "banking": 3, "banks": 2, "loan": 2, "loans": 2, "credit": 1, "IMF": 3,
        "World Bank": 3, "ADB": 3, "debt": 3, "bond": 2, "bonds": 2, "treasury": 2,
        "economy": 3, "economic": 2, "GDP": 3, "growth": 1, "tariff": 3, "tariffs": 3,
        "price": 1, "prices": 1, "fuel price": 3, "market": 1, "business": 2, "company": 1,
        "PLC": 3, "profit": 3, "profits": 3, "earnings": 2, "finance": 3, "financial": 2,
        "fiscal": 3, "monetary": 3, "insurance": 2, "real estate": 3, "property": 1,
        "tourism": 1, "tourist arrivals": 2, "remittances": 3, "apparel": 2, "industry": 1,
        "industrial": 1, "investment cooperation": 3, "oil and gas": 2, "resort": 1, "hotel": 1, "piling": 2,
        "Port City": 2, "shortage": 1,
    },
    "Tech": {
        "technology": 3, "technologies": 3, "tech": 3, "digital": 3, "digitalisation": 3,
        "digitalization": 3, "AI": 3, "artificial intelligence": 3, "app": 2, "apps": 2,
        "software": 3, "cyber": 3, "cybersecurity": 3, "hacker": 3, "hackers": 3,
        "hacking": 3, "internet": 3, "broadband": 3, "telecom": 3, "telecommunications": 3,
        "TRCSL": 3, "smartphone": 3, "smartphones": 3, "5G": 3, "4G": 2, "fibre": 2,
        "startup": 3, "startups": 3, "start-up": 3, "ICT": 3, "IT sector": 3, "robot": 3,
        "robots": 3, "robotics": 3, "satellite": 3, "personal data": 3, "data protection": 3, "data breach": 3, "database": 2, "online": 1,
        "e-government": 3, "GovPay": 3, "blockchain": 3, "crypto": 3, "cryptocurrency": 3,
        "bitcoin": 3, "electric vehicle": 3, "electric vehicles": 3, "EV": 3, "EVs": 3,
        "innovation": 2, "computer": 3, "computers": 3, "laptop": 3, "semiconductor": 3,
        "chip": 2, "Starlink": 3, "SLT": 2, "Dialog": 2, "Mobitel": 3, "Hutch": 2,
        "Google": 2, "Apple": 2, "Microsoft": 3, "Meta": 2, "OpenAI": 3, "ChatGPT": 2,
        "TikTok": 1, "social media": 1, "digital ID": 3, "QR": 2, "fintech": 3, "drone": 3,
        "drones": 3, "deepfake": 3, "deepfakes": 3, "AI-generated": 3,
    },
}

# Newswire's own section labels nudge the decision.
SOURCE_CATEGORY_HINTS = {"Bizwire": ("Finance", 4), "Business": ("Finance", 4), "Tech": ("Tech", 4)}

MIN_SCORE = 6  # below this the story is "General"


def _compile(word: str) -> re.Pattern:
    flags = 0 if (word.isupper() or any(c.isdigit() for c in word)) and len(word) <= 6 else re.I
    return re.compile(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", flags)


_PATTERNS = {cat: [(_compile(w), wt) for w, wt in words.items()] for cat, words in KEYWORDS.items()}


def classify_keywords(title: str, text: str, source_categories: list[str]) -> tuple[str, dict]:
    scores = {}
    for cat, patterns in _PATTERNS.items():
        score = 0
        for pat, wt in patterns:
            if pat.search(title):
                score += wt * 3
            score += wt * min(len(pat.findall(text)), 3)
        scores[cat] = score
    for sc in source_categories:
        if sc in SOURCE_CATEGORY_HINTS:
            cat, boost = SOURCE_CATEGORY_HINTS[sc]
            scores[cat] += boost
    best = max(CATEGORIES, key=lambda c: scores[c])  # ties resolve in CATEGORIES order
    return (best if scores[best] >= MIN_SCORE else FALLBACK_CATEGORY), scores


# --------------------------------------------------------------------------- #
# Extractive summariser
# --------------------------------------------------------------------------- #
_ABBREVIATIONS = [
    "Rs", "Mn", "Bn", "Mr", "Mrs", "Ms", "Dr", "Prof", "St", "No", "Nos", "Jan", "Feb", "Mar",
    "Apr", "Jun", "Jul", "Aug", "Sep", "Sept", "Oct", "Nov", "Dec", "Gen", "Lt", "Col", "Capt",
    "Maj", "Hon", "Ven", "Jr", "Sr", "Co", "Ltd", "Inc", "vs", "etc", "approx", "Govt", "Dept",
]
_ABBR_RE = re.compile(r"\b(" + "|".join(_ABBREVIATIONS) + r")\.", re.I)
_INITIAL_RE = re.compile(r"\b([A-Z])\.")
_SENT_SPLIT = re.compile(r"(?<=[.!?])[\"'”’)]?\s+(?=[\"'“‘(]?[A-Z0-9])")
_STOPWORDS = set(
    """a about above after again against all also am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers herself him himself his how i if in into is it its itself
    just me more most my myself no nor not now of off on once only or other our ours ourselves out over
    own said same says she should so some such than that the their theirs them themselves then there
    these they this those through to too under until up very was we were what when where which while
    who whom why will with would you your yours yourself yourselves according told today yesterday
    newswire sri lanka lankan""".split()
)


def split_sentences(text: str) -> list[str]:
    protected = _ABBR_RE.sub(lambda m: m.group(1) + "<DOT>", text)
    protected = _INITIAL_RE.sub(lambda m: m.group(1) + "<DOT>", protected)
    parts = _SENT_SPLIT.split(protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def summarise_extractive(title: str, text: str, max_sentences: int = 2, max_words: int = 65) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return title
    if len(sentences) <= max_sentences:
        chosen = sentences
    else:
        words = [w for w in re.findall(r"[a-z][a-z'-]+", (title + " " + text).lower()) if w not in _STOPWORDS]
        freq = Counter(words)
        title_words = {w for w in re.findall(r"[a-z][a-z'-]+", title.lower()) if w not in _STOPWORDS}

        def score(idx_sent):
            idx, sent = idx_sent
            toks = [w for w in re.findall(r"[a-z][a-z'-]+", sent.lower()) if w not in _STOPWORDS]
            if not toks:
                return 0
            s = sum(freq[t] for t in toks) / (len(toks) ** 0.7)
            s += 2.0 * len(title_words.intersection(toks))
            s *= 1.6 if idx == 0 else (1.2 if idx == 1 else 1.0)  # news is lede-first
            return s

        ranked = sorted(enumerate(sentences), key=score, reverse=True)[:max_sentences]
        chosen = [s for _, s in sorted(ranked)]
        if 0 not in {i for i, _ in ranked}:  # always keep the lede for context
            chosen = [sentences[0]] + chosen[: max_sentences - 1]

    summary = ""
    for sent in chosen:
        candidate = (summary + " " + sent).strip()
        if summary and len(candidate.split()) > max_words:
            break
        summary = candidate
    if len(summary.split()) > max_words + 15:
        summary = " ".join(summary.split()[:max_words]).rstrip(",;:") + "…"
    return summary


# --------------------------------------------------------------------------- #
# Claude engine (optional)
# --------------------------------------------------------------------------- #
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_BATCH = 12
CLAUDE_MAX_WORDS_PER_ARTICLE = 1500  # Newswire stories are short; this only trims rare long-reads

SYSTEM_PROMPT = """You are the editor of a daily Sri Lankan news digest built from Newswire.lk stories.
For every article you receive, return:
- category: exactly one of "Political", "Finance", "Tech", or "General".
  Political = government, parliament, parties, politicians, elections, diplomacy, public policy, court cases about politicians.
  Finance = economy, markets, currency, banking, tax, trade, investment, business and corporate news.
  Tech = technology, digital services, telecoms, AI, cyber, science and innovation.
  General = anything that is clearly none of the three (weather, crime, accidents, sport, entertainment, health).
  Pick the single best fit by the story's main subject, not passing mentions.
- summary: 2-3 plain sentences (max 60 words) capturing who, what, and why it matters. Neutral tone, no
  hype, no information that isn't in the article. Do not start with "The article".
Return every article id you were given, exactly once."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "category": {"type": "string", "enum": CATEGORIES + [FALLBACK_CATEGORY]},
                    "summary": {"type": "string"},
                },
                "required": ["id", "category", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["articles"],
    "additionalProperties": False,
}


def claude_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _claude_batch(client, batch: list[dict]) -> dict[int, dict]:
    payload = [
        {
            "id": a["id"],
            "title": a["title"],
            "newswire_sections": a["source_categories"],
            "text": " ".join(a["text"].split()[:CLAUDE_MAX_WORDS_PER_ARTICLE]),
        }
        for a in batch
    ]
    response = client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # if a classifier declines, the API retries on Anthropic's recommended model
        system=SYSTEM_PROMPT,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    if response.stop_reason == "refusal":
        log.warning("Claude declined a batch (%s); using keyword engine for it", response.stop_details)
        return {}
    if response.stop_reason == "max_tokens":
        log.warning("Claude output hit max_tokens; using keyword engine for this batch")
        return {}
    text = next((b.text for b in response.content if b.type == "text"), "")
    data = json.loads(text)
    return {item["id"]: item for item in data["articles"]}


def enrich_with_claude(articles: list[dict]) -> int:
    """Fill category/summary in place. Returns how many articles Claude handled."""
    import anthropic

    client = anthropic.Anthropic()
    handled = 0
    for i in range(0, len(articles), CLAUDE_BATCH):
        batch = articles[i : i + CLAUDE_BATCH]
        try:
            results = _claude_batch(client, batch)
        except anthropic.AuthenticationError:
            log.error("ANTHROPIC_API_KEY was rejected; falling back to keyword engine")
            return handled
        except anthropic.RateLimitError:
            log.warning("Rate limited by the Claude API; keyword engine for this batch")
            continue
        except anthropic.APIStatusError as e:
            log.warning("Claude API error %s; keyword engine for this batch", e.status_code)
            continue
        except anthropic.APIConnectionError:
            log.warning("Could not reach the Claude API; keyword engine for this batch")
            continue
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("Unexpected Claude output (%s); keyword engine for this batch", e)
            continue
        for a in batch:
            r = results.get(a["id"])
            if r and r["summary"].strip():
                a["category"] = r["category"]
                a["summary"] = r["summary"].strip()
                a["enriched_by"] = "claude"
                handled += 1
    return handled


# --------------------------------------------------------------------------- #
def enrich(articles: list[dict], use_llm: bool = True) -> str:
    """Give every article a `category` and `summary`. Returns the engine used."""
    for a in articles:
        a["category"], a["category_scores"] = classify_keywords(a["title"], a["text"], a["source_categories"])
        a["summary"] = summarise_extractive(a["title"], a["text"])
        a["enriched_by"] = "keywords"

    if use_llm and claude_available() and articles:
        n = enrich_with_claude(articles)
        log.info("Claude summarised %d/%d articles", n, len(articles))
        return "claude" if n == len(articles) else ("mixed" if n else "keywords")
    return "keywords"
