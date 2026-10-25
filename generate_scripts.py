
#!/usr/bin/env python3
"""Daily Comedy Agent: generate and validate three short comedy scripts."""

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

OUTPUT_DIR = Path("output")
TARGET_SCRIPTS = 3
MIN_WORDS = 85
MAX_WORDS = 115
MAX_HEADLINES = 18
MAX_ATTEMPTS = 4

USER_AGENT = "DailyComedyAgent/4.0"

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


def fetch_url(url, timeout=20):
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


def parse_feed(xml_text, feed_name):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"Warning: invalid RSS from {feed_name}: {exc}")
        return []

    items = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        url = clean_text(item.findtext("link"))
        source = clean_text(item.findtext("source"))
        description = clean_text(item.findtext("description"))
        published = clean_text(item.findtext("pubDate"))

        if not title or not url:
            continue

        items.append({
            "title": title,
            "url": url,
            "source": source or feed_name,
            "description": description[:500],
            "published": published,
        })

    return items


def fetch_feed(url, feed_name):
    try:
        return parse_feed(fetch_url(url), feed_name)
    except Exception as exc:
        print(f"Warning: {feed_name} unavailable: {exc}")
        return []


def collect_news():
    stories = []
    seen = set()

    for query in FEED_QUERIES:
        items = fetch_feed(
            google_news_feed_url(query),
            "Google News",
        )

        for item in items:
            key = re.sub(r"[^a-z0-9]", "", item["title"].lower())

            if key and key not in seen:
                seen.add(key)
                stories.append(item)

            if len(stories) >= MAX_HEADLINES:
                break

        if len(stories) >= MAX_HEADLINES:
            break

        time.sleep(0.2)

    if len(stories) < 8:
        for url in FALLBACK_FEEDS:
            for item in fetch_feed(url, "Publisher RSS"):
                key = re.sub(r"[^a-z0-9]", "", item["title"].lower())

                if key and key not in seen:
                    seen.add(key)
                    stories.append(item)

                if len(stories) >= MAX_HEADLINES:
                    break

            if len(stories) >= MAX_HEADLINES:
                break

    # Prefer recently published stories when dates are available.
    now = datetime.now(timezone.utc)
    recent = []
    undated = []

    for item in stories:
        published = item.get("published", "")

        try:
            dt = parsedate_to_datetime(published)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            age_seconds = (now - dt.astimezone(timezone.utc)).total_seconds()

            if age_seconds <= 5 * 24 * 3600:
                recent.append(item)

        except (TypeError, ValueError, OverflowError):
            undated.append(item)

    return (recent + undated)[:MAX_HEADLINES]


def build_generation_prompt(stories):
    news_json = json.dumps(stories, ensure_ascii=False, indent=2)

    return f"""
You are the head comedy writer for a sharp, modern YouTube channel.

Create exactly THREE distinct comedy monologues using THREE different
stories from the supplied news list.

PERFORMER AND AUDIENCE
The performer is an Indian YouTuber speaking natural English to an
international audience, particularly viewers in the US, UK, Australia,
Germany, and other English-speaking markets.

COMEDY STYLE
Mix funny storytelling, sharp but fair roasting, meme-aware observations,
unexpected comparisons, escalating absurdity, and surprising punchlines.

Every script needs ONE clear comic premise. It should feel like a tiny
stand-up routine, not a news summary or a list of unrelated jokes.

Avoid generic AI humour and tired phrases such as "the internet is wild",
"you can't make this up", and "let that sink in".

Make the first sentence immediately interesting or funny. Establish the
premise quickly, escalate the comedy, and finish with the strongest joke
or a satisfying callback.

Do not force Indian references into every script. Use them only when they
make a joke sharper and understandable.

LENGTH IS IMPORTANT
Each spoken script MUST contain between {MIN_WORDS} and {MAX_WORDS} words.
Aim for around 95-105 words so normal delivery takes approximately
45-50 seconds.

Count the words in the script itself, not its title or metadata.
Do not include stage directions, word counts, or explanations inside
the spoken script.

FACTUAL CARE
Use the supplied stories only. Do not invent facts, quotes, private
details, motives, or outcomes. Clearly absurd exaggeration is allowed
as comedy, but do not present invented events as real.

Avoid hateful or demeaning jokes about protected characteristics.

OUTPUT
Return ONLY valid JSON, without Markdown fences, using this structure:

{{
  "scripts": [
    {{
      "title": "Short, funny title",
      "story_title": "Exact supplied news headline",
      "source": "Publisher name",
      "source_url": "Exact URL copied from the supplied news list",
      "premise": "One sentence explaining the central comic idea",
      "hook": "The exact first sentence of the spoken script",
      "script": "Complete spoken monologue",
      "closing_punchline": "The exact final sentence of the spoken script"
    }}
  ]
}}

The three scripts must use three different source URLs and have different
titles, premises, joke structures, and punchlines.

NEWS LIST:
{news_json}
"""


def call_gemini(prompt):
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it under repository "
            "Settings > Secrets and variables > Actions."
        )

    model_name = MODEL or "gemini-3.5-flash-lite"

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model_name, safe="")
        + ":generateContent?key="
        + urllib.parse.quote(API_KEY, safe="")
    )

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.9,
            "responseMimeType": "application/json",
        },
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8", errors="replace")

    except Exception as exc:
        detail = ""

        if hasattr(exc, "read"):
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:1200]
            except Exception:
                pass

        raise RuntimeError(
            f"Gemini request failed for model '{model_name}': "
            f"{exc}. {detail}"
        ) from exc

    try:
        data = json.loads(body)
        candidates = data.get("candidates", [])

        if not candidates:
            raise ValueError(
                "Gemini returned no candidates: " + body[:1000]
            )

        parts = candidates[0].get("content", {}).get("parts", [])
        result = "\n".join(
            part.get("text", "") for part in parts
        ).strip()

        if not result:
            raise ValueError("Gemini returned an empty response.")

        return result

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Could not read Gemini's response: {exc}. "
            f"Response: {body[:1000]}"
        ) from exc


def extract_json(text):
    text = text.strip()
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end <= start:
        raise ValueError("The model did not return a JSON object.")

    return json.loads(text[start:end + 1])


def normalize_text(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def validate_scripts(data, stories):
    errors = []
    scripts = data.get("scripts") if isinstance(data, dict) else None

    if not isinstance(scripts, list):
        return [], ["The response must contain a scripts list."]

    if len(scripts) != TARGET_SCRIPTS:
        errors.append(
            f"Exactly {TARGET_SCRIPTS} scripts are required; "
            f"the response contains {len(scripts)}."
        )

    known_urls = {item["url"] for item in stories}
    used_urls = set()
    used_titles = set()
    valid_scripts = []

    for index, item in enumerate(scripts, start=1):
        if not isinstance(item, dict):
            errors.append(f"Script {index} is not a JSON object.")
            continue

        required = [
            "title",
            "story_title",
            "source",
            "source_url",
            "premise",
            "hook",
            "script",
            "closing_punchline",
        ]

        missing = [
            field for field in required
            if not str(item.get(field, "")).strip()
        ]

        if missing:
            errors.append(
                f"Script {index} is missing: {', '.join(missing)}."
            )
            continue

        spoken = re.sub(r"\s+", " ", str(item["script"])).strip()
        count = word_count(spoken)

        if count < MIN_WORDS:
            errors.append(
                f"Script {index} has {count} words, which is "
                f"{MIN_WORDS - count} below the minimum of {MIN_WORDS}. "
                f"Expand it to {MIN_WORDS}-{MAX_WORDS} words."
            )

        elif count > MAX_WORDS:
            errors.append(
                f"Script {index} has {count} words, which is "
                f"{count - MAX_WORDS} above the maximum of {MAX_WORDS}. "
                f"Tighten it to {MIN_WORDS}-{MAX_WORDS} words."
            )

        sentences = re.split(r"(?<=[.!?])\s+", spoken)
        first_sentence = sentences[0].strip() if sentences else ""
        last_sentence = sentences[-1].strip() if sentences else ""

        hook = str(item["hook"]).strip()
        punchline = str(item["closing_punchline"]).strip()

        if normalize_text(first_sentence) != normalize_text(hook):
            errors.append(
                f"Script {index}: hook must match its opening sentence."
            )

        if normalize_text(last_sentence) != normalize_text(punchline):
            errors.append(
                f"Script {index}: closing_punchline must match "
                "its final sentence."
            )

        url = str(item["source_url"]).strip()

        if url not in known_urls:
            errors.append(
                f"Script {index}: source_url must be copied exactly "
                "from the supplied news list."
            )

        if url in used_urls:
            errors.append(
                f"Script {index}: each script needs a different source URL."
            )

        used_urls.add(url)

        title_key = re.sub(
            r"[^a-z0-9]",
            "",
            str(item["title"]).lower(),
        )

        if title_key in used_titles:
            errors.append(
                f"Script {index}: the title duplicates another script."
            )

        used_titles.add(title_key)

        item["script"] = spoken
        item["word_count"] = count
        valid_scripts.append(item)

    if len(used_urls) != TARGET_SCRIPTS:
        errors.append("All three scripts must use different news stories.")

    return valid_scripts, errors


def generate_valid_scripts(stories):
    prompt = build_generation_prompt(stories)
    previous_response = ""
    previous_errors = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"Generation/validation attempt {attempt}/{MAX_ATTEMPTS}...")

        if attempt == 1:
            current_prompt = prompt
        else:
            current_prompt = f"""
Your previous response failed validation.

Repair the response now. Return the COMPLETE corrected JSON object,
not an explanation and not just the changed scripts.

STRICT REQUIREMENTS
- Exactly three scripts.
- Each spoken script must contain {MIN_WORDS}-{MAX_WORDS} words.
- If a script is too short, add funny storytelling, specific comic
  comparisons, and escalating jokes. Do not pad with filler.
- If a script is too long, remove unnecessary setup and weaker jokes.
- Keep the opening hook identical to the first sentence.
- Keep the closing_punchline identical to the final sentence.
- Use three distinct stories and exact source URLs from the original
  supplied news list.
- Keep titles, premises, and punchlines distinct.
- Return valid JSON only.

VALIDATION ERRORS TO FIX:
{json.dumps(previous_errors, ensure_ascii=False, indent=2)}

ORIGINAL NEWS LIST:
{json.dumps(stories, ensure_ascii=False, indent=2)}

PREVIOUS RESPONSE TO REPAIR:
{previous_response[:18000]}
"""

        try:
            previous_response = call_gemini(current_prompt)
            data = extract_json(previous_response)
            valid_scripts, errors = validate_scripts(data, stories)

            if not errors and len(valid_scripts) == TARGET_SCRIPTS:
                print("All three scripts passed validation.")
                return valid_scripts

            previous_errors = errors or [
                "The response did not contain three valid scripts."
            ]

            print("Validation failed:")
            for error in previous_errors:
                print(f" - {error}")

        except (ValueError, json.JSONDecodeError) as exc:
            previous_errors = [
                f"Invalid JSON response: {exc}. Return valid JSON only."
            ]
            print(f"Response could not be validated: {exc}")

        if attempt < MAX_ATTEMPTS:
            print("Requesting an automatic correction from Gemini...")
            time.sleep(1)

    raise RuntimeError(
        f"Scripts did not pass validation after {MAX_ATTEMPTS} attempts. "
        "No new output file was saved. Review the errors above and run "
        "the workflow again later."
    )


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
            "(target: 45–50 seconds)",
            "",
            item["script"],
            "",
            "---",
            "",
        ])

    return "\n".join(lines)


def save_output(content):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    output_path = OUTPUT_DIR / f"comedy-scripts-{today}.md"

    output_path.write_text(content, encoding="utf-8")

    print(f"Saved scripts to: {output_path}")
    return output_path


def main():
    print("Daily Comedy Agent — automatic repair enabled")
    print(f"Gemini model: {MODEL or 'gemini-3.5-flash-lite'}")

    stories = collect_news()

    if len(stories) < TARGET_SCRIPTS:
        raise RuntimeError(
            f"Only {len(stories)} usable headlines were found. "
            "Try again when the news feeds are available."
        )

    print(f"Collected {len(stories)} news headlines.")
    scripts = generate_valid_scripts(stories)

    output_path = save_output(render_markdown(scripts))

    print("\nGenerated scripts:")
    for index, item in enumerate(scripts, start=1):
        print(f"{index}. {item['title']} — {item['word_count']} words")

    print(f"Output file: {output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
