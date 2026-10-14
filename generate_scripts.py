
import os
import json
import time
import re
import html
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = "gemini-3.5-flash-lite"
OUTPUT_DIR = Path("output")
MAX_STORIES = 3

SEARCHES = [
    "US UK celebrity entertainment when:2d",
    "viral internet culture influencer news when:2d",
    "movies music streaming pop culture when:2d",
    "hip hop social media celebrity drama when:2d",
]

BACKUP_FEEDS = [
    "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "https://variety.com/feed/",
    "https://www.theguardian.com/culture/rss",
    "https://deadline.com/feed/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) "
        "AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36"
    )
}


def download_url(url, attempts=3):
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"Download attempt {attempt + 1} failed: {exc}")
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    return None


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_feed(feed_url):
    content = download_url(feed_url)
    if not content:
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        print(f"Invalid RSS/XML feed: {feed_url}: {exc}")
        return []

    stories = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        description = clean_text(item.findtext("description"))

        if title and link.startswith(("https://", "http://")):
            stories.append({
                "title": title,
                "url": link,
                "description": description,
                "feed": feed_url,
            })

    # Support Atom feeds as well as RSS feeds.
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        summary = clean_text(
            entry.findtext("atom:summary", default="", namespaces=ns)
        )
        link_element = entry.find("atom:link", ns)
        link = link_element.get("href", "") if link_element is not None else ""

        if title and link.startswith(("https://", "http://")):
            stories.append({
                "title": title,
                "url": link,
                "description": summary,
                "feed": feed_url,
            })

    return stories


def collect_stories():
    collected = []
    seen_urls = set()
    seen_titles = set()

    for query in SEARCHES:
        encoded = urllib.parse.quote(query)
        url = (
            "https://news.google.com/rss/search?q="
            + encoded
            + "&hl=en-US&gl=US&ceid=US:en"
        )

        print(f"Checking Google News: {query}")
        for story in parse_feed(url):
            key_url = story["url"].split("&")[0]
            key_title = story["title"].lower()

            if key_url not in seen_urls and key_title not in seen_titles:
                seen_urls.add(key_url)
                seen_titles.add(key_title)
                collected.append(story)

        time.sleep(2)

    if len(collected) < MAX_STORIES:
        print("Not enough Google News stories. Checking backup feeds.")

        for feed in BACKUP_FEEDS:
            for story in parse_feed(feed):
                key_url = story["url"].split("&")[0]
                key_title = story["title"].lower()

                if key_url not in seen_urls and key_title not in seen_titles:
                    seen_urls.add(key_url)
                    seen_titles.add(key_title)
                    collected.append(story)

            if len(collected) >= 12:
                break

    print(f"Collected {len(collected)} unique headlines.")
    return collected


def gemini_generate(prompt):
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is missing.")

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + MODEL
        + ":generateContent?key="
        + urllib.parse.quote(API_KEY)
    )

    body = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.75,
            "responseMimeType": "application/json",
        },
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            "Gemini returned no usable text: "
            + json.dumps(data)[:1000]
        )


def build_prompt(stories):
    supplied = json.dumps(stories, ensure_ascii=False, indent=2)

    return f"""
You are a sharp, natural stand-up comedy writer for a US, UK, Canadian,
and Australian audience.

Create UP TO THREE short news-based comedy scripts using ONLY the supplied
story records below.

STORY RECORDS:
{supplied}

STRICT FACTUAL RULES:
1. Use only claims supported by the supplied headline or description.
2. A headline alone is not independent verification. Do not say that you
   read or verified an article unless the supplied record proves it.
3. Do not invent quotes, expert opinions, motives, actions, injuries,
   legal developments, dates, statistics, or reactions.
4. Do not present a rumour or allegation as established fact.
5. For sensitive allegations, medical events, or criminal claims, use
   cautious wording and only include details explicitly supported.
6. If the evidence is too thin or the story is too sensitive to joke about
   responsibly, skip it.
7. Do not fabricate a source URL. Copy the exact URL from the supplied record.
8. Comedy exaggeration must be clearly figurative, not a fake news detail.
9. Avoid cruel jokes about victims, serious injuries, or unverified claims.
10. Prefer stories with enough context to support a meaningful comedy angle.

STYLE:
- Start with a fast, compelling hook.
- Use conversational stand-up storytelling.
- Build tension and absurdity, then deliver a strong twist or callback.
- Avoid generic AI phrases and repetitive punchlines.
- Target approximately 100-140 spoken words per script.
- Make each script sound distinct and human.

OUTPUT:
Return valid JSON only, in this format:
{{
  "stories": [
    {{
      "headline": "Accurate headline",
      "source_url": "Exact supplied URL",
      "spoken_monologue": "Comedy script",
      "caption": "Short social caption",
      "video_description": "Brief description",
      "fact_check_note": "Clearly state what is supported and what remains unverified"
    }}
  ]
}}

Return no more than 3 stories. Return fewer if fewer are suitable.
If no story meets the rules, return an empty stories array.
"""


def validate_results(results, supplied_stories):
    approved_urls = {story["url"] for story in supplied_stories}
    valid = []
    seen = set()

    for item in results:
        if not isinstance(item, dict):
            continue

        required = [
            "headline",
            "source_url",
            "spoken_monologue",
            "caption",
            "video_description",
            "fact_check_note",
        ]

        if any(not str(item.get(key, "")).strip() for key in required):
            print("Skipping a script with missing required fields.")
            continue

        url = item["source_url"].strip()
        if url not in approved_urls:
            print("Skipping script with an unrecognized source URL.")
            continue

        if url in seen:
            print("Skipping duplicate source URL.")
            continue

        monologue = item["spoken_monologue"].strip()
        word_count = len(monologue.split())

        if word_count < 60:
            print("Skipping a script that is too short.")
            continue

        # This is a basic quality filter, not a guarantee of truth.
        if re.search(
            r"\b(experts are praising|experts confirmed|everyone knows)\b",
            monologue,
            re.IGNORECASE,
        ):
            print("Skipping unsupported expert/generalization claim.")
            continue

        seen.add(url)
        valid.append(item)

        if len(valid) >= MAX_STORIES:
            break

    return valid


def main():
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured in GitHub Actions secrets."
        )

    stories = collect_stories()

    if not stories:
        raise RuntimeError(
            "No headlines were collected. Check the feeds and rerun later."
        )

    prompt = build_prompt(stories)

    try:
        raw = gemini_generate(prompt)
        result = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"Script generation failed: {exc}") from exc

    generated = result.get("stories", [])
    if not isinstance(generated, list):
        raise RuntimeError("Gemini output did not contain a stories list.")

    approved = validate_results(generated, stories)

    if not approved:
        print("No scripts passed validation. Nothing will be published.")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{today}.md"

    sections = [
        f"# Daily Comedy Scripts — {today}",
        "",
        f"Generated scripts: {len(approved)}",
        "",
        "> Drafts only. Check source reporting before publishing.",
        "",
    ]

    for index, item in enumerate(approved, start=1):
        sections.extend([
            f"## Story {index}",
            f"**Headline:** {item['headline']}",
            f"**Source URL:** {item['source_url']}",
            "",
            "**Spoken Monologue:**",
            item["spoken_monologue"].strip(),
            "",
            f"**Caption:** {item['caption'].strip()}",
            "",
            f"**Video Description:** {item['video_description'].strip()}",
            "",
            f"**Fact-check Note:** {item['fact_check_note'].strip()}",
            "",
            "---",
            "",
        ])

    output_path.write_text("\n".join(sections), encoding="utf-8")
    print(f"Saved {len(approved)} scripts to {output_path}")


if __name__ == "__main__":
    main()
