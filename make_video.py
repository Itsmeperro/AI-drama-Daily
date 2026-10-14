#!/usr/bin/env python3
"""Make today's vertical (1080x1920) AI Drama Daily video from today.json.

Output: drama.mp4 (voiceover + animated title cards) and caption.txt (ready-to-paste post text).
TTS: edge-tts neural voice, falling back to gTTS. Set FAKE_TTS=1 to test offline with silent audio.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
VOICE = "en-US-AndrewMultilingualNeural"
SITE = "jcbriney71-hub.github.io/AI-drama-Daily"
RED, INK, CREAM, GOLD = (215, 38, 30), (18, 14, 11), (251, 247, 240), (255, 196, 0)

FONT_CANDIDATES = ["fonts/Anton-Regular.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
BODY_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "fonts/Anton-Regular.ttf"]

def font(cands, size):
    for p in cands:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)

def clean(t):
    t = re.sub(r"\s+", " ", t).strip()
    return t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')

def wrap_to_fit(draw, text, fnt_cands, max_w, max_h, start=110, minimum=54):
    size = start
    while size >= minimum:
        f = font(fnt_cands, size)
        avg = draw.textlength("abcdefghijklmnopqrstuvwxyz", font=f) / 26
        lines = textwrap.wrap(text, width=max(8, int(max_w / avg)))
        lh = int(size * 1.15)
        if len(lines) * lh <= max_h and all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f, lines, lh
        size -= 4
    f = font(fnt_cands, minimum)
    lines = textwrap.wrap(text, width=28)[: max_h // int(minimum * 1.15)]
    return f, lines, int(minimum * 1.15)

def fit(d, text, cands, size, max_w=W - 120):
    while size > 30:
        f = font(cands, size)
        if d.textlength(text, font=f) <= max_w:
            return f
        size -= 6
    return font(cands, size)

def centered(d, text, cands, size, y, fill):
    f = fit(d, text, cands, size)
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)

def base(bg=INK):
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    # diagonal hazard stripes, top and bottom
    for y0 in (0, H - 90):
        for x in range(-200, W + 200, 80):
            d.polygon([(x, y0), (x + 40, y0), (x + 130, y0 + 90), (x + 90, y0 + 90)], fill=RED)
    return img, d

def slide_intro(date_str):
    img, d = base()
    for i, word in enumerate(["AI", "DRAMA", "DAILY"]):
        centered(d, word, FONT_CANDIDATES, 210, 440 + i * 240, RED if word == "DRAMA" else CREAM)
    centered(d, date_str.upper(), BODY_CANDIDATES, 52, 1210, GOLD)
    centered(d, "TOP 3 AI DRAMAS TODAY", BODY_CANDIDATES, 46, 1300, CREAM)
    return img

def slide_story(rank, story):
    img, d = base()
    # giant faint rank number in background
    ghost = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(ghost)
    gf = font(FONT_CANDIDATES, 1100)
    num = str(rank)
    gd.text(((W - gd.textlength(num, font=gf)) / 2, 260), num, font=gf, fill=60)
    img.paste(Image.new("RGB", (W, H), (60, 20, 16)), mask=ghost.filter(ImageFilter.GaussianBlur(2)))
    d = ImageDraw.Draw(img)
    # rank badge
    tag = f"#{rank}" + ("  BIGGEST DRAMA" if rank == 1 else "")
    tf = font(FONT_CANDIDATES, 96)
    tw = d.textlength(tag, font=tf)
    d.rectangle([60, 250, 60 + tw + 60, 390], fill=RED)
    d.text((90, 258), tag, font=tf, fill=CREAM)
    # headline card
    d.rectangle([60, 430, W - 60, 1270], fill=CREAM)
    hf, lines, lh = wrap_to_fit(d, clean(story["title"]), BODY_CANDIDATES, W - 220, 760)
    y = 430 + (840 - len(lines) * lh) / 2
    for ln in lines:
        d.text((110, y), ln, font=hf, fill=INK)
        y += lh
    sf = font(BODY_CANDIDATES, 44)
    src = f"via {clean(story['source'])}"
    d.text((70, 1300), src[:40], font=sf, fill=GOLD)
    heat = "HEAT: " + "|" * min(10, max(1, story.get("score", 1)))
    d.text((70, 1370), heat, font=sf, fill=RED)
    return img

def slide_outro():
    img, d = base(RED)
    for i, ln in enumerate(["FOLLOW FOR", "DAILY", "AI DRAMA"]):
        centered(d, ln, FONT_CANDIDATES, 150, 480 + i * 190, CREAM)
    centered(d, "Full roundup: link in bio", BODY_CANDIDATES, 46, 1100, INK)
    centered(d, SITE, BODY_CANDIDATES, 38, 1180, CREAM)
    return img

async def tts_edge(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="+8%").save(path)

def tts(text, path):
    if os.environ.get("FAKE_TTS"):
        secs = max(2.5, len(text.split()) / 2.8)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "anullsrc=r=24000:cl=mono", "-t", f"{secs:.2f}", path], check=True)
        return
    try:
        asyncio.run(tts_edge(text, path))
        if os.path.getsize(path) > 1000:
            return
    except Exception as e:
        print(f"edge-tts failed ({e}); falling back to gTTS", file=sys.stderr)
    from gtts import gTTS
    gTTS(text, lang="en", tld="us").save(path)

def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())

def clip(img_path, audio_path, out_path, pad=0.45):
    dur = duration(audio_path) + pad
    frames = int(dur * FPS)
    vf = (f"scale={W*2}:{H*2},zoompan=z='min(1+on*0.0009,1.12)':"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
          f"fade=t=in:st=0:d=0.25,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img_path,
                    "-i", audio_path, "-vf", vf, "-af", f"apad=pad_dur={pad}",
                    "-t", f"{dur:.2f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium",
                    "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
                    out_path], check=True)

def main():
    data = json.load(open("today.json"))
    stories = data["stories"][:3]
    if len(stories) < 3:
        print("fewer than 3 stories; skipping video", file=sys.stderr)
        sys.exit(1)
    now = datetime.now(ZoneInfo("America/Chicago"))
    date_str = now.strftime("%A, %B %-d")
    ordinals = {3: "Number three.", 2: "Number two.", 1: "And the biggest AI drama today."}
    segments = [(slide_intro(date_str), f"Here are the three biggest A.I. dramas for {date_str}.")]
    for rank, s in zip((3, 2, 1), reversed(stories)):
        segments.append((slide_story(rank, s), f"{ordinals[rank]} {clean(s['title'])}."))
    segments.append((slide_outro(), "Full roundup is at the link in bio. Follow for your daily A.I. drama."))

    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, (img, line) in enumerate(segments):
            ip, ap, cp = (os.path.join(tmp, f"{i}.{ext}") for ext in ("png", "mp3", "mp4"))
            img.save(ip)
            tts(line, ap)
            clip(ip, ap, cp)
            parts.append(cp)
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w") as f:
            f.writelines(f"file '{p}'\n" for p in parts)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", lst, "-c", "copy", "-movflags", "+faststart", "drama.mp4"], check=True)
        segments[1][0].save("thumbnail.jpg", quality=88)

    tops = "\n".join(f"{r}. {clean(s['title'])}" for r, s in zip((3, 2, 1), reversed(stories)))
    caption = (f"The 3 biggest AI dramas today 🍿🔥\n\n{tops}\n\n"
               f"Follow for daily AI drama. Full roundup: link in bio\n\n"
               f"#AI #AInews #tech #OpenAI #ChatGPT #technews #drama")
    open("caption.txt", "w").write(caption)
    print(f"drama.mp4: {duration('drama.mp4'):.1f}s")

if __name__ == "__main__":
    main()
