import os
import re
import json
import time
import html
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
OUTPUT_DIR = Path("output")
MAX_STORIES = 3

SEARCHES = [
    "US UK celebrity entertainment when:2d",
    "viral internet culture influencer news when:2d",
    "movies music streaming pop culture when:2d",
    "celebrity interviews reality TV entertainment when:2d",
]

def download(url, attempts=3):
    headers = {"User-Agent": "Mozilla/5.0 ComedyResearchBot/1.0"}
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as response:
                return response.read()
        except Exception as exc:
            print(f"Download attempt {attempt + 1} failed: {exc}")
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    return b""

def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def read_feed(url):
    raw = download(url)
    if not raw:
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    items = []
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        if tag not in ("item", "entry"):
            continue

        values = {}
        for child in node:
            key = child.tag.split("}")[-1].lower()
            if key == "link":
                link = child.attrib.get("href", "") or child.text or ""
                values["link"] = link.strip()
            elif key in ("title", "description", "summary", "content"):
                if key not in values:
                    values[key] = clean("".join(child.itertext()))

        title = values.get("title", "")
        link = values.get("link", "")
        snippet = (
            values.get("description", "")
            or values.get("summary", "")
            or values.get("content", "")
        )

        if title and link.startswith("http"):
            items.append({
                "title": title,
                "url": link,
                "snippet": snippet[:700],
            })

    return items

def collect_stories():
    stories = []
    seen = set()

    for query in SEARCHES:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        for story in read_feed(url):
            key = re.sub(r"\W+", "", story["title"].lower())
            if key and key not in seen:
                seen.add(key)
                stories.append(story)

    print(f"Collected {len(stories)} unique feed stories.")
    return stories[:15]

def generate(stories):
    story_text = json.dumps(stories, ensure_ascii=False)

    prompt = f"""
You are the head comedy writer for a sharp, original YouTube
commentary channel performed by an Indian creator for viewers
in the US, UK, Australia, Canada and other English-speaking
countries.

TASK:
Choose up to THREE distinct, promising stories from the supplied
news-feed records. Write one original spoken comedy monologue
for each chosen story.

NEWS RECORDS:
{story_text}

COMEDY STANDARD:
The writing must sound like a funny human telling a story on
camera, not a news anchor, press release or generic AI comedian.

Each monologue must:
- Be approximately 100-140 spoken words.
- Start with a punchy hook, not a greeting or news summary.
- Find a specific, relatable absurdity in the actual story.
- Escalate through 2-4 connected jokes or comparisons.
- Have a clear comedic point of view and natural spoken rhythm.
- Finish with a surprising punchline, twist or callback.
- Feel like modern stand-up mixed with sharp internet-culture
  commentary.
- Allow an Indian creator's personality to come through naturally.
  Do not force Indian references into every script.
- Use current online language only when it fits the joke.
- Be specific. Avoid vague filler and generic motivational lines.
- Make jokes about public situations and behavior, not protected
  characteristics or vulnerable private individuals.
- Avoid cruelty, slurs, harassment and unsupported allegations.

DO NOT:
- Invent quotes, events, numbers, reactions or celebrity behavior.
- Treat a headline as proof of details absent from the feed record.
- Claim that a person said or did something unless the supplied
  record supports that claim.
- Repeat the same joke structure for every script.
- Start with "You won't believe", "In today's world",
  "Let's talk about", or "So apparently".
- Use fake internet slang just to sound current.

FACTUAL RULES:
Use each story's supplied title, snippet and URL as the starting
point. Keep factual claims narrow. If details are uncertain,
make the joke about the public headline or situation itself.
Use the exact URL provided for that story. Never create a URL.
Do not claim independent fact-checking has occurred.

OUTPUT:
Return valid JSON only, with this structure:
{{
  "scripts": [
    {{
      "headline": "Short, catchy title",
      "source_url": "Exact supplied story URL",
      "monologue": "Complete spoken script",
      "caption": "Short funny caption",
      "description": "Brief video description and relevant hashtags",
      "fact_check_note": "What claim to verify before recording"
    }}
  ]
}}

Choose different stories when possible. Prefer stories with a clear
comedic angle. Return fewer than three if there are not enough
suitable stories. Never invent a story to fill the quota.
"""

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + MODEL
        + ":generateContent?"
        + urllib.parse.urlencode({"key": API_KEY})
    )

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.95,
            "responseMimeType": "application/json"
        }
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))

            text = result["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = re.sub(r"\s*```$", "", text)
            return json.loads(text)

        except Exception as exc:
            print(f"Generation attempt {attempt + 1} failed: {exc}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))

    raise RuntimeError("Gemini generation failed after three attempts.")

def validate(scripts, stories):
    supplied_urls = {s["url"] for s in stories}
    accepted = []
    used_urls = set()

    for item in scripts:
        required = [
            "headline", "source_url", "monologue",
            "caption", "description", "fact_check_note"
        ]
        if not all(isinstance(item.get(k), str) and item[k].strip()
                   for k in required):
            print("Skipped script with missing fields.")
            continue

        url = item["source_url"].strip()
        if url not in supplied_urls or url in used_urls:
            print("Skipped script with an unapproved or duplicate URL.")
            continue

        words = re.findall(r"\b[\w'-]+\b", item["monologue"])
        if not 75 <= len(words) <= 155:
            print(f"Skipped script with {len(words)} words.")
            continue

        used_urls.add(url)
        accepted.append(item)

        if len(accepted) >= MAX_STORIES:
            break

    return accepted

def main():
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is missing.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    stories = collect_stories()

    if not stories:
        raise RuntimeError(
            "No news stories were collected. No script file was created."
        )

    result = generate(stories)
    scripts = validate(result.get("scripts", []), stories)

    if not scripts:
        raise RuntimeError(
            "No scripts passed validation. No empty output file was created."
        )

    today = datetime.now().strftime("%Y-%m-%d")
    path = OUTPUT_DIR / f"{today}.md"

    with path.open("w", encoding="utf-8") as file:
        file.write(f"# Daily Comedy Scripts — {today}\n\n")
        file.write(f"Generated scripts: {len(scripts)}\n\n")
        file.write(
            "> Review the original source and verify factual claims "
            "before recording.\n\n"
        )

        for number, item in enumerate(scripts, 1):
            file.write(f"## Script {number}: {item['headline']}\n\n")
            file.write(f"**Source URL:** {item['source_url']}\n\n")
            file.write("### Full Spoken Monologue\n\n")
            file.write(item["monologue"].strip() + "\n\n")
            file.write("### Caption\n\n")
            file.write(item["caption"].strip() + "\n\n")
            file.write("### Video Description\n\n")
            file.write(item["description"].strip() + "\n\n")
            file.write("### Fact-Check Reminder\n\n")
            file.write(item["fact_check_note"].strip() + "\n\n")
            file.write("---\n\n")

    print(f"Saved {len(scripts)} scripts to {path}")

if __name__ == "__main__":
    main()
