#!/usr/bin/env python3
"""Daily Comedy Agent: create three short, source-linked comedy drafts."""

import json
import os
import re
import sys
import time
import html
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

OUTPUT_DIR = Path("output")
MAX_HEADLINES = 18
TARGET_SCRIPTS = 3
MIN_WORDS = 85
MAX_WORDS = 115

USER_AGENT = "DailyComedyAgent/3.0"

FEED_QUERIES = [
    "US UK celebrity entertainment news when:2d",
    "viral internet culture influencer news when:2d",
    "movies streaming music pop culture news when:2d",
    "celebrity reality TV social media drama when:2d",
    "hip hop social media celebrity news when:2d",
]

FALLBACK_FEEDS = [
    "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "https://www.theguardian.com/culture/film/rss",
    "https://www.theguardian.com/music/rss",
]


def clean_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def word_count(text):
    return len(re.findall(r"\b[\w’'-]+\b", text or ""))


def fetch_url(url, timeout=18):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def google_news_feed_url(query):
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })

    return "https://news.google.com/rss/search?" + params


def parse_feed(xml_text, feed_name="News feed"):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(
            f"Warning: couldn't parse {feed_name}: {exc}",
            file=sys.stderr,
        )
        return []

    results = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        link = clean_text(item.findtext("link"))
        source = clean_text(item.findtext("source"))
        description = clean_text(item.findtext("description"))
        published = clean_text(item.findtext("pubDate"))

        if not title or not link:
            continue

        results.append({
            "title": title,
            "url": link,
            "source": source or feed_name,
            "description": description[:500],
            "published": published,
        })

    return results


def fetch_feed(url, feed_name):
    try:
        return parse_feed(fetch_url(url), feed_name)
    except Exception as exc:
        print(
            f"Warning: feed unavailable ({feed_name}): {exc}",
            file=sys.stderr,
        )
        return []


def parse_date(value):
    if not value:
        return None

    try:
        dt = parsedate_to_datetime(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (TypeError, ValueError, OverflowError):
        return None


def collect_news():
    stories = []
    seen = set()

    for query in FEED_QUERIES:
        feed_url = google_news_feed_url(query)

        for item in fetch_feed(feed_url, "Google News"):
            key = re.sub(
                r"[^a-z0-9]",
                "",
                item["title"].lower(),
            )

            if key and key not in seen:
                seen.add(key)
                stories.append(item)

            if len(stories) >= MAX_HEADLINES:
                break

        if len(stories) >= MAX_HEADLINES:
            break

        time.sleep(0.15)

    # Use publisher RSS feeds if Google News returns too few headlines.
    if len(stories) < 8:
        for url in FALLBACK_FEEDS:
            for item in fetch_feed(url, "BBC/Guardian RSS"):
                key = re.sub(
                    r"[^a-z0-9]",
                    "",
                    item["title"].lower(),
                )

                if key and key not in seen:
                    seen.add(key)
                    stories.append(item)

                if len(stories) >= MAX_HEADLINES:
                    break

            if len(stories) >= MAX_HEADLINES:
                break

    # Prefer recent stories where timestamps are available.
    now = datetime.now(timezone.utc)
    dated_recent = []
    undated = []

    for item in stories:
        dt = parse_date(item.get("published", ""))

        if dt is None:
            undated.append(item)
        elif (now - dt).total_seconds() <= 5 * 24 * 3600:
            dated_recent.append(item)

    return (dated_recent + undated)[:MAX_HEADLINES]


def build_prompt(stories):
    news_text = json.dumps(
        stories,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
You are the head writer for a genuinely funny, modern,
fast-paced comedy channel.

YOUR MISSION

Create exactly {TARGET_SCRIPTS} distinct, record-ready comedy
monologues based on the supplied news stories.

The performer is an Indian YouTuber speaking to an international
English-speaking audience, especially viewers in the US, UK,
Australia, Germany, and other English-speaking markets.

The voice must be confident, observant, culturally aware,
playful, surprising, and conversational.

This is NOT a news report.
This is NOT a boring article rewritten as jokes.
This is NOT a generic collection of AI one-liners.

COMEDY STANDARD

Every script must have ONE clear comic premise and feel like
a tiny stand-up story.

Mix these techniques:
- Funny storytelling.
- Sharp but fair roasting.
- Unexpected comparisons.
- Escalating absurdity.
- Specific, vivid images.
- Meme-aware observations.
- Callbacks and surprising punchlines.

Make jokes about public behaviour, absurd situations,
celebrity PR, online reactions, and the story's irony.

Do not make jokes targeting protected traits or vulnerable people.
Be playful rather than cruel.

Do not invent facts, quotations, motives, private details,
or outcomes.

You may use obvious exaggeration for comedy, but viewers must
not mistake an invented exaggeration for a real news fact.

RETENTION AND TIMING

Each script must:
- Contain 85–115 spoken words.
- Aim for approximately 45–50 seconds when performed naturally.
- Begin with an immediately interesting or funny first sentence.
- Have no greeting, introduction, or unnecessary setup.
- Establish the central premise quickly.
- Escalate with increasingly funny turns.
- Include at least two specific, vivid comedic images or comparisons.
- Sound natural when spoken aloud.
- Finish with its strongest punchline or a satisfying callback.

The opening should make someone want to hear the next sentence.

The middle should keep rewarding the viewer with fresh observations.

The ending must feel like a punchline, not a summary.

Do not finish with a bland moral or "what do you think?"

ORIGINALITY

Choose three DIFFERENT news stories.

Give every script a different central comic idea.
Do not repeat the same joke structure three times.

Avoid generic jokes about how crazy the internet is.

Avoid lazy phrases such as:
- "In today's world"
- "The internet is wild"
- "You can't make this up"
- "Let that sink in"

Only use familiar phrases if you give them a genuinely fresh twist.

Do not force Indian references into every script.
Use one only when it makes the joke sharper and understandable.

Make the audience feel they are hearing a comedian with a point of view,
not reading a collection of jokes generated from a headline.

FACT CHECKING

Use only facts supported by the supplied headlines and descriptions.

Do not assume a headline proves every detail.

If a story is ambiguous, joke about the ambiguity or public reaction
rather than asserting unverified information.

Include the exact source URL supplied for the selected story.

OUTPUT FORMAT

Return ONLY valid JSON. Do not use Markdown fences.

Use this exact structure:

{{
  "scripts": [
    {{
      "title": "Short, funny title",
      "story_title": "Exact supplied headline",
      "source": "Publisher name if available",
      "source_url": "Exact supplied URL",
      "premise": "One sentence describing the central comic idea",
      "hook": "The exact opening sentence of the script",
      "script": "Full spoken monologue, with no stage directions",
      "closing_punchline": "The exact final sentence of the script"
    }}
  ]
}}

NEWS STORIES:

{news_text}
"""


def call_gemini(prompt):
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it under GitHub repository "
            "Settings > Secrets and variables > Actions."
        )

    model_name = MODEL or "gemini-2.5-flash"

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model_name, safe="")
        + ":generateContent?key="
        + urllib.parse.quote(API_KEY, safe="")
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.95,
            "responseMimeType": "application/json",
        },
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode(
                "utf-8",
                errors="replace",
            )

    except Exception as exc:
        detail = ""

        if hasattr(exc, "read"):
            try:
                detail = exc.read().decode(
                    "utf-8",
                    errors="replace",
                )[:1000]
            except Exception:
                pass

        raise RuntimeError(
            f"Gemini request failed using model '{model_name}': "
            f"{exc}. {detail}"
        ) from exc

    try:
        data = json.loads(body)
        candidates = data.get("candidates", [])

        text_parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
            if candidates
            else []
        )

        response_text = "\n".join(
            part.get("text", "")
            for part in text_parts
        ).strip()

        if not response_text:
            raise ValueError(
                "Gemini returned no text. Response: " + body[:1000]
            )

        return response_text

    except (
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        raise RuntimeError(
            f"Couldn't read Gemini response: {exc}. "
            f"Response: {body[:1000]}"
        ) from exc


def extract_json(response_text):
    text = response_text.strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end <= start:
        raise ValueError(
            "Gemini did not return a JSON object. Beginning of response: "
            + text[:500]
        )

    try:
        return json.loads(text[start:end + 1])

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Gemini returned invalid JSON: {exc}"
        ) from exc


def validate_scripts(data, stories):
    scripts = data.get("scripts") if isinstance(data, dict) else None

    if not isinstance(scripts, list) or len(scripts) != TARGET_SCRIPTS:
        count = len(scripts) if isinstance(scripts, list) else "an invalid scripts field"

        raise ValueError(
            f"Expected exactly {TARGET_SCRIPTS} scripts; "
            f"Gemini returned {count}."
        )

    known_urls = {item["url"] for item in stories}
    used_story_keys = set()
    used_titles = set()
    cleaned = []

    for number, item in enumerate(scripts, start=1):
        if not isinstance(item, dict):
            raise ValueError(
                f"Script {number} is not a JSON object."
            )

        required = [
            "title",
            "story_title",
            "source_url",
            "premise",
            "hook",
            "script",
            "closing_punchline",
        ]

        missing = [
            key
            for key in required
            if not str(item.get(key, "")).strip()
        ]

        if missing:
            raise ValueError(
                f"Script {number} is missing required fields: "
                + ", ".join(missing)
                + "."
            )

        script_text = re.sub(
            r"\s+",
            " ",
            str(item["script"]),
        ).strip()

        count = word_count(script_text)

        if count < MIN_WORDS or count > MAX_WORDS:
            raise ValueError(
                f"Script {number} has {count} words; target is "
                f"{MIN_WORDS}–{MAX_WORDS}. Run the workflow again "
                "to generate fresh drafts."
            )

        sentences = re.split(
            r"(?<=[.!?])\s+",
            script_text,
        )

        first_sentence = sentences[0].strip()
        hook = re.sub(
            r"\s+",
            " ",
            str(item["hook"]),
        ).strip()

        if first_sentence.rstrip('"”') != hook.rstrip('"”'):
            raise ValueError(
                f"Script {number}: the hook must exactly match "
                "the opening sentence."
            )

        final_sentence = sentences[-1].strip()
        closing = re.sub(
            r"\s+",
            " ",
            str(item["closing_punchline"]),
        ).strip()

        if final_sentence.rstrip('"”') != closing.rstrip('"”'):
            raise ValueError(
                f"Script {number}: closing_punchline must exactly "
                "match the final sentence."
            )

        url = str(item["source_url"]).strip()

        if url not in known_urls:
            raise ValueError(
                f"Script {number} used a source URL not present "
                "in the supplied news list."
            )

        story_key = re.sub(
            r"[^a-z0-9]",
            "",
            str(item["story_title"]).lower(),
        )

        if story_key in used_story_keys:
            raise ValueError(
                "Two scripts used the same story. "
                "Three distinct news stories are required."
            )

        used_story_keys.add(story_key)

        title_key = re.sub(
            r"[^a-z0-9]",
            "",
            str(item["title"]).lower(),
        )

        if title_key in used_titles:
            raise ValueError(
                "Script titles are duplicated. "
                "Three distinct titles are required."
            )

        used_titles.add(title_key)

        item["script"] = script_text
        item["word_count"] = count

        item["source"] = (
            str(item.get("source", "News source")).strip()
            or "News source"
        )

        cleaned.append(item)

    return cleaned


def render_markdown(scripts):
    today = datetime.now().astimezone().strftime("%Y-%m-%d")

    lines = [
        f"# Daily Comedy Scripts — {today}",
        "",
        "> AI-assisted comedy drafts. Verify the original reporting "
        "before recording. The fact-check reminder is not proof.",
        "",
    ]

    for index, item in enumerate(scripts, start=1):
        lines.extend([
            f"## {index}. {item['title']}",
            "",
            f"**News story:** {item['story_title']}",
            f"**Source:** {item['source']}",
            f"**Source link:** {item['source_url']}",
            f"**Comic premise:** {item['premise']}",
            f"**Length:** {item['word_count']} words "
            "(aiming for 45–50 seconds)",
            "",
            item["script"],
            "",
            "---",
            "",
        ])

    return "\n".join(lines)


def save_output(content):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    today = datetime.now().astimezone().strftime("%Y-%m-%d")

    output_path = OUTPUT_DIR / f"comedy-scripts-{today}.md"

    output_path.write_text(
        content,
        encoding="utf-8",
    )

    print(f"Saved scripts to: {output_path}")

    return output_path


def main():
    print("Daily Comedy Agent — refreshed short-form writer")
    print(f"Gemini model: {MODEL or 'gemini-2.5-flash'}")

    stories = collect_news()

    if len(stories) < TARGET_SCRIPTS:
        raise RuntimeError(
            f"Only found {len(stories)} usable news headlines. "
            "Try the workflow again later; no scripts were saved."
        )

    print(
        f"Collected {len(stories)} news headlines. "
        f"Generating {TARGET_SCRIPTS} scripts..."
    )

    prompt = build_prompt(stories)
    response = call_gemini(prompt)
    data = extract_json(response)
    scripts = validate_scripts(data, stories)

    content = render_markdown(scripts)
    output_path = save_output(content)

    print("\nSuccessfully generated 3 scripts:")

    for index, item in enumerate(scripts, start=1):
        print(
            f"{index}. {item['title']} — "
            f"{item['word_count']} words"
        )

    print(f"Output file: {output_path}")


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
