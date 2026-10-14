#!/usr/bin/env python3
"""Build index.html for AI Drama Daily from public RSS feeds (stdlib only)."""
import html
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from zoneinfo import ZoneInfo

LOOKBACK_HOURS = 48
MAX_STORIES = 30

def gnews(q):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q + " when:2d", "hl": "en-US", "gl": "US", "ceid": "US:en"})

FEEDS = [
    gnews('(OpenAI OR Anthropic OR "Google DeepMind" OR xAI OR Meta AI OR Nvidia) (lawsuit OR sued OR feud OR ousted OR resigns OR scandal OR leak)'),
    gnews('"artificial intelligence" (lawsuit OR controversy OR backlash OR investigation OR ban OR fine)'),
    gnews('AI (deepfake OR copyright OR antitrust OR subpoena OR whistleblower)'),
    gnews('(Sam Altman OR Elon Musk OR Dario Amodei OR Mark Zuckerberg OR Sundar Pichai) AI'),
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.wired.com/feed/tag/ai/latest/rss",
    "https://arstechnica.com/ai/feed/",
]

# word -> drama weight
DRAMA = {
    "lawsuit": 5, "sues": 5, "sued": 5, "suing": 5, "scandal": 5, "ousted": 5, "fired": 5,
    "feud": 5, "whistleblower": 5, "subpoena": 4, "leak": 4, "leaked": 4, "resigns": 4,
    "quits": 4, "accuses": 4, "accused": 4, "probe": 4, "investigation": 4, "indicted": 5,
    "fine": 3, "fined": 4, "ban": 3, "banned": 4, "backlash": 4, "controversy": 4,
    "slams": 4, "blasts": 4, "clash": 4, "war": 3, "fight": 3, "drama": 4, "chaos": 4,
    "deepfake": 3, "copyright": 3, "antitrust": 4, "layoffs": 3, "outage": 3, "exodus": 4,
    "poach": 3, "poached": 3, "boycott": 4, "settlement": 3, "lawmakers": 2, "senate": 2,
    "warns": 2, "fury": 4, "outrage": 4, "secret": 3, "exposed": 4, "breach": 4,
    "hack": 3, "hacked": 4, "jailbreak": 3, "rogue": 3, "crackdown": 4, "rift": 4,
    "betrayal": 5, "turmoil": 4, "shake-up": 3, "shakeup": 3, "allegations": 4,
}
AI_WORDS = re.compile(r"\b(ai|a\.i\.|openai|anthropic|claude|chatgpt|gpt|gemini|deepmind|llm|"
                      r"xai|grok|nvidia|copilot|chatbot|altman|musk|amodei|artificial intelligence|"
                      r"mistral|perplexity|midjourney|deepseek|llama)\b", re.I)

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AI-Drama-Daily/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def text(el, *names):
    for n in names:
        found = el.find(n)
        if found is not None:
            return (found.text or found.get("href") or "").strip()
    return ""

def parse(raw, feed_url):
    root = ET.fromstring(raw)
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{atom}entry")
    out = []
    for it in items:
        title = text(it, "title", f"{atom}title")
        link = text(it, "link", f"{atom}link")
        if not link:
            le = it.find(f"{atom}link")
            link = le.get("href") if le is not None else ""
        date_s = text(it, "pubDate", f"{atom}published", f"{atom}updated")
        source = text(it, "source")
        try:
            dt = parsedate_to_datetime(date_s)
        except Exception:
            try:
                dt = datetime.fromisoformat(date_s.replace("Z", "+00:00"))
            except Exception:
                continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if not source:
            source = urllib.parse.urlparse(feed_url).netloc.replace("www.", "")
        # Google News titles end with " - Source"
        if " - " in title and "news.google.com" in feed_url:
            t, s = title.rsplit(" - ", 1)
            title, source = t, s
        out.append({"title": html.unescape(title), "link": link, "dt": dt, "source": source})
    return out

def score(title):
    words = re.findall(r"[a-z\-]+", title.lower())
    return sum(DRAMA.get(w, 0) for w in words)

def norm(t):
    t = re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", t)  # drop trailing " - Source"
    return " ".join(re.findall(r"[a-z0-9]+", t.lower()))[:60]

def ago(dt, now):
    h = int((now - dt).total_seconds() // 3600)
    return "just now" if h < 1 else f"{h}h ago" if h < 24 else f"{h // 24}d ago"

def heat(s):
    return "🔥🔥🔥" if s >= 10 else "🔥🔥" if s >= 6 else "🔥"

def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)
    stories, seen, ok = [], set(), 0
    for url in FEEDS:
        try:
            items = parse(fetch(url), url)
            ok += 1
        except Exception as e:
            print(f"feed failed: {url} ({e})", file=sys.stderr)
            continue
        for s in items:
            if s["dt"] < cutoff or s["dt"] > now + timedelta(hours=1):
                continue
            if not AI_WORDS.search(s["title"]):
                continue
            s["score"] = score(s["title"])
            if s["score"] <= 0:
                continue
            k = norm(s["title"])
            if k in seen:
                continue
            seen.add(k)
            stories.append(s)
    if ok == 0:
        print("all feeds failed; keeping existing page", file=sys.stderr)
        sys.exit(1)
    stories.sort(key=lambda s: (s["score"], s["dt"]), reverse=True)
    stories = stories[:MAX_STORIES]
    write_page(stories, now)
    posted = write_feed(stories, now)
    print(f"{len(stories)} stories from {ok}/{len(FEEDS)} feeds; {posted} new social posts")

SITE_URL = "https://jcbriney71-hub.github.io/AI-drama-Daily/"
POSTS_PER_DAY = 3
FEED_KEEP = 45  # ~2 weeks of posts

def write_feed(stories, now):
    """feed.xml: up to POSTS_PER_DAY new items per run for social auto-posters.
    Keeps prior items, skips headlines already posted, never re-posts on the same day."""
    from xml.sax.saxutils import escape as x
    day = now.astimezone(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    old = []
    try:
        root = ET.parse("feed.xml").getroot()
        for it in root.findall(".//item"):
            old.append({k: (it.findtext(k) or "") for k in ("title", "link", "guid", "pubDate", "description")})
    except Exception:
        pass
    if any(o["guid"].startswith(day + "-") for o in old):
        new = []  # already posted today (e.g. a manual re-run)
    else:
        posted = {norm(o["description"]) for o in old}
        picks = [s for s in stories if norm(s["title"]) not in posted][:POSTS_PER_DAY]
        new = []
        for i, s in enumerate(picks, 1):
            headline = s["title"]
            text = f"{heat(s['score'])} {headline} ({s['source']}) — today's full AI drama roundup:"
            new.append({
                "title": text,
                "link": f"{SITE_URL}?d={day}&n={i}",
                "guid": f"{day}-{i}",
                "pubDate": format_datetime(now + timedelta(minutes=i)),
                "description": headline,
            })
    items = (new[::-1] + old)[:FEED_KEEP]
    body = "\n".join(
        f"""<item><title>{x(it['title'])}</title><link>{x(it['link'])}</link>
<guid isPermaLink="false">{x(it['guid'])}</guid><pubDate>{x(it['pubDate'])}</pubDate>
<description>{x(it['description'])}</description></item>""" for it in items)
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>AI Drama Daily</title><link>{SITE_URL}</link>
<description>The juiciest AI headlines, refreshed every morning.</description>
<lastBuildDate>{format_datetime(now)}</lastBuildDate>
{body}
</channel></rss>
"""
    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(feed)
    return len(new)

def write_page(stories, now):
    central = now.astimezone(ZoneInfo("America/Chicago"))
    stamp = central.strftime("%A, %B %-d, %Y · %-I:%M %p CT")
    e = html.escape
    if stories:
        lead, rest = stories[0], stories[1:]
        lead_html = f"""<a class="lead" href="{e(lead['link'])}" target="_blank" rel="noopener">
  <span class="tag">Top drama {heat(lead['score'])}</span>
  <h2>{e(lead['title'])}</h2>
  <span class="meta">{e(lead['source'])} · {ago(lead['dt'], now)}</span></a>"""
        rows = "\n".join(
            f"""<li><a href="{e(s['link'])}" target="_blank" rel="noopener">
  <span class="n">{i}</span><span class="body"><span class="t">{e(s['title'])}</span>
  <span class="meta">{e(s['source'])} · {ago(s['dt'], now)} <span class="heat">{heat(s['score'])}</span></span></span></a></li>"""
            for i, s in enumerate(rest, 2))
    else:
        lead_html = '<p class="empty">A quiet day in AI. Suspiciously quiet.</p>'
        rows = ""
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Drama Daily</title>
<meta name="description" content="The juiciest AI headlines, refreshed every morning.">
<link rel="alternate" type="application/rss+xml" title="AI Drama Daily" href="feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{{--bg:#fbf7f0;--ink:#16120e;--muted:#6b6259;--red:#d7261e;--rule:#e2d9cc;--card:#fff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14110f;--ink:#f3ede4;--muted:#a59a8d;--red:#ff4a3d;--rule:#2e2823;--card:#1c1815}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 Inter,system-ui,sans-serif}}
.wrap{{max-width:760px;margin:0 auto;padding:0 16px 48px}}
header{{border-bottom:4px solid var(--ink);padding:28px 0 12px;text-align:center}}
h1{{font-family:Anton,Impact,sans-serif;font-weight:400;font-size:clamp(44px,12vw,84px);line-height:.95;margin:0;letter-spacing:.5px;text-transform:uppercase}}
h1 span{{color:var(--red)}}
.date{{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);border-top:1px solid var(--ink);margin-top:12px;padding-top:6px;text-transform:uppercase;letter-spacing:.06em}}
a{{color:inherit;text-decoration:none}}
.lead{{display:block;margin:24px 0;padding:20px;background:var(--red);color:#fff;border-radius:4px}}
.lead h2{{font-family:Anton,Impact,sans-serif;font-weight:400;font-size:clamp(28px,6vw,40px);line-height:1.08;margin:8px 0 10px}}
.lead .meta{{color:#ffe1dc}}
.tag{{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.1em}}
ol{{list-style:none;margin:0;padding:0}}
li a{{display:flex;gap:14px;padding:14px 4px;border-bottom:1px solid var(--rule)}}
li a:hover .t{{color:var(--red)}}
.n{{font-family:Anton,Impact,sans-serif;font-size:26px;color:var(--red);min-width:34px;line-height:1}}
.body{{display:flex;flex-direction:column;gap:4px}}
.t{{font-weight:600;font-size:17px}}
.meta{{font-size:13px;color:var(--muted)}}
.empty{{text-align:center;padding:48px 0;color:var(--muted)}}
footer{{margin-top:28px;font-size:12px;color:var(--muted);text-align:center}}
</style></head>
<body><div class="wrap">
<header><h1>AI <span>Drama</span> Daily</h1>
<div class="date"><span>{e(stamp)}</span><span>{len(stories)} stories</span></div></header>
{lead_html}
<ol>
{rows}
</ol>
<footer>Headlines link to the original reporting. Auto-updated every morning from public news feeds.</footer>
</div></body></html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page)

if __name__ == "__main__":
    main()
