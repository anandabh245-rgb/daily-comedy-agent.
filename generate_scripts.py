
#!/usr/bin/env python3
"""Daily Comedy Agent — premise-first, retention-focused comedy writing."""

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
MIN_WORDS = 90
MAX_WORDS = 112
MAX_HEADLINES = 24
MAX_ATTEMPTS = 4
USER_AGENT = "DailyComedyAgent/5.0"

FEED_QUERIES = [
    "US UK celebrity entertainment news when:2d",
    "viral internet culture influencer news when:2d",
    "movies streaming music pop culture news when:2d",
    "celebrity reality TV social media drama when:2d",
    "hip hop social media celebrity news when:2d",
    "celebrity interview controversy public reaction when:2d",
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

        if title and url:
            items.append({
                "title": title,
                "url": url,
                "source": source or feed_name,
                "description": description[:600],
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
    collected = []
    seen = set()

    for query in FEED_QUERIES:
        for item in fetch_feed(google_news_feed_url(query), "Google News"):
            key = re.sub(r"[^a-z0-9]", "", item["title"].lower())
            if key and key not in seen:
                seen.add(key)
                collected.append(item)
            if len(collected) >= MAX_HEADLINES:
                break
        if len(collected) >= MAX_HEADLINES:
            break
        time.sleep(0.15)

    if len(collected) < 10:
        for url in FALLBACK_FEEDS:
            for item in fetch_feed(url, "Publisher RSS"):
                key = re.sub(r"[^a-z0-9]", "", item["title"].lower())
                if key and key not in seen:
                    seen.add(key)
                    collected.append(item)
                if len(collected) >= MAX_HEADLINES:
                    break
            if len(collected) >= MAX_HEADLINES:
                break

    now = datetime.now(timezone.utc)
    recent, undated = [], []

    for item in collected:
        try:
            dt = parsedate_to_datetime(item.get("published", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt.astimezone(timezone.utc)).total_seconds() <= 5 * 86400:
                recent.append(item)
        except (TypeError, ValueError, OverflowError):
            undated.append(item)

    return (recent + undated)[:MAX_HEADLINES]


def call_gemini(prompt, temperature=0.95):
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it in repository Settings > "
            "Secrets and variables > Actions."
        )

    model = MODEL or "gemini-3.5-flash-lite"
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model, safe="")
        + ":generateContent?key="
        + urllib.parse.quote(API_KEY, safe="")
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
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
            f"Gemini request failed for model '{model}': {exc}. {detail}"
        ) from exc

    try:
        data = json.loads(body)
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates: " + body[:800])
        parts = candidates[0].get("content", {}).get("parts", [])
        result = "\n".join(p.get("text", "") for p in parts).strip()
        if not result:
            raise ValueError("Gemini returned an empty response.")
        return result
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Could not parse Gemini response: {exc}") from exc


def extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model did not return a JSON object.")
    return json.loads(text[start:end + 1])


def story_selection_prompt(stories):
    return f"""
You are an elite comedy story editor for an English-language YouTube
commentary channel. Pick the THREE stories with the strongest potential
for an actually funny 45–50 second monologue.

Do NOT pick a story just because it is celebrity news. Rank stories by:
1. An immediately understandable absurdity, contradiction, overreaction,
   hypocrisy, strange public behaviour, ridiculous stakes, or comic irony.
2. Enough concrete information to support a specific premise.
3. International audience familiarity or a clear explanation.
4. Potential for an escalating bit, not just one obvious joke.
5. Avoid stories where humour would rely on cruelty, tragedy, allegations
   treated as fact, or targeting vulnerable people.

Fashion roundups, routine announcements, and thin stories should usually
lose to richer stories unless there is a truly original comic angle.

Return valid JSON only:
{{
  "selected": [
    {{
      "story_url": "exact URL from the list",
      "comic_potential": "why this story can sustain an original comic bit",
      "angle_to_avoid": "the obvious, tired joke to avoid"
    }}
  ]
}}

Select exactly three DIFFERENT URLs. Never invent a story or URL.

STORIES:
{json.dumps(stories, ensure_ascii=False, indent=2)}
"""


def choose_stories(stories):
    if len(stories) < TARGET_SCRIPTS:
        raise RuntimeError(f"Only {len(stories)} usable headlines were found.")

    try:
        result = extract_json(
            call_gemini(story_selection_prompt(stories), 0.35)
        )
        selected = result.get("selected", [])
        by_url = {item["url"]: item for item in stories}
        chosen, used = [], set()

        for entry in selected:
            url = str(entry.get("story_url", "")).strip()
            if url in by_url and url not in used:
                story = dict(by_url[url])
                story["comic_potential"] = str(
                    entry.get("comic_potential", "")
                )
                story["angle_to_avoid"] = str(
                    entry.get("angle_to_avoid", "")
                )
                chosen.append(story)
                used.add(url)

            if len(chosen) == TARGET_SCRIPTS:
                break

        if len(chosen) == TARGET_SCRIPTS:
            print("Selected three stories for comedy potential.")
            return chosen

        print(
            "Warning: story selector returned invalid choices; "
            "using diverse headlines."
        )
    except Exception as exc:
        print(f"Warning: story selection step failed: {exc}")

    return stories[:TARGET_SCRIPTS]


def writer_prompt(stories):
    return f"""
You are not a generic AI assistant. You are a ruthless, highly inventive
stand-up comedy head writer and short-form retention editor. Your drafts
must sound spoken, specific, surprising, and worth sharing.

TASK: Write exactly THREE separate 45–50 second monologues, one per
story below. The performer is an Indian YouTuber speaking natural English
to US, UK, Australian, German, and other international viewers.

THE STANDARD
Do not merely make observations that are mildly amusing. Find a comic
premise that makes the story feel absurd, then build a complete bit.

Before writing each script, silently answer:
- What is the single funniest contradiction or absurdity here?
- What is the fresh angle beyond the first obvious joke?
- What specific image can the audience instantly picture?
- How can each beat escalate the SAME premise?
- What ending changes the meaning of the opening or pays off a callback?

If the premise is weak, find a sharper angle from the facts. Do not
pretend every headline is naturally hilarious. Do not make up facts.

STRUCTURE FOR EACH SCRIPT
1. HOOK (first sentence): a surprising, funny, concrete claim or image.
   No greeting, no "so today", no headline readout.
2. PREMISE: immediately reveal the comic lens and why it is ridiculous.
3. ESCALATION: three or four connected beats, each funnier or more
   specific than the previous one. The jokes must build, not feel like
   separate tweets.
4. TURN: introduce an unexpected comparison, reversal, or new implication.
5. PAYOFF: a concise, genuinely surprising final punchline or callback.
   Do not end with a summary, a moral, or "what do you think?"

COMEDY TECHNIQUES TO USE SELECTIVELY
- Specific, visual comparisons rather than vague adjectives.
- Rule of three with the third item breaking the pattern.
- Misdirection: lead the audience toward one interpretation, then twist it.
- Escalation: every beat raises the ridiculous stakes.
- Status contrast: celebrity-level drama versus ordinary life.
- Callback: bring the opening image back in a transformed way.
- A distinct Indian-commentator perspective only where it naturally
  sharpens the joke; don't force references or explain them.

ANTI-AI RULES
Ban lazy filler: "the internet is wild", "you can't make this up",
"let that sink in", "in today's world", "give them an Oscar",
"rich people are different", "it's basically...", unless there is a
specific original twist that makes the phrase work.
No generic "luxury hotel", "small country", "shadow realm", or tea jokes
unless a truly new setup makes them surprising.
Do not repeat the same joke rhythm across all three scripts.
Do not write a safe article summary followed by a punchline.
Do not use random absurdity that doesn't connect to the premise.
Don't confuse insults with jokes. Punch at public behaviour, PR, absurd
systems, and the situation—not protected traits or vulnerable people.

LENGTH
Each spoken script must be 90–112 words. Aim for 98–105 words.
Count spoken words only, not title, premise, or metadata.
Every sentence must either clarify the premise, add a laugh, escalate,
set up a turn, or pay off a joke. Cut anything that does none of these.
Read it aloud mentally: use varied sentence lengths and conversational
rhythm. No stage directions.

FACTS
Use only supplied story details. Do not invent quotes, motives, events,
or outcomes. Exaggeration is allowed only when clearly comedic and not
misleading. Treat allegations as allegations, not established facts.
Include the exact source URL provided for each story.

RETURN ONLY VALID JSON:
{{
  "scripts": [
    {{
      "title": "Distinct memorable title",
      "story_title": "Exact supplied headline",
      "source": "Publisher name",
      "source_url": "Exact supplied URL",
      "premise": "The central comic idea in one sentence",
      "hook": "Exact first sentence of script",
      "script": "Complete spoken monologue",
      "closing_punchline": "Exact final sentence of script"
    }}
  ]
}}

For each story, the comic angle and the script must avoid the obvious
tired joke listed with that story. The three premises and punchlines
must be meaningfully different.

STORIES:
{json.dumps(stories, ensure_ascii=False, indent=2)}
"""


def validate_scripts(data, stories):
    errors = []
    scripts = data.get("scripts") if isinstance(data, dict) else None

    if not isinstance(scripts, list) or len(scripts) != TARGET_SCRIPTS:
        count = len(scripts) if isinstance(scripts, list) else "invalid"
        return [], [f"Expected exactly three scripts; got {count}."]

    known = {s["url"] for s in stories}
    used_urls, used_titles, used_premises = set(), set(), set()
    result = []

    for i, item in enumerate(scripts, 1):
        if not isinstance(item, dict):
            errors.append(f"Script {i} is not an object.")
            continue

        fields = [
            "title", "story_title", "source", "source_url",
            "premise", "hook", "script", "closing_punchline",
        ]
        missing = [
            f for f in fields if not str(item.get(f, "")).strip()
        ]
        if missing:
            errors.append(f"Script {i} missing fields: {', '.join(missing)}.")
            continue

        spoken = re.sub(r"\s+", " ", str(item["script"])).strip()
        count = word_count(spoken)

        if not MIN_WORDS <= count <= MAX_WORDS:
            errors.append(
                f"Script {i} has {count} words; must be "
                f"{MIN_WORDS}-{MAX_WORDS}."
            )

        sentences = re.split(r"(?<=[.!?])\s+", spoken)
        first = sentences[0].strip() if sentences else ""
        last = sentences[-1].strip() if sentences else ""

        if (
            first.casefold().rstrip('"”')
            != str(item["hook"]).strip().casefold().rstrip('"”')
        ):
            errors.append(
                f"Script {i} hook doesn't exactly match first sentence."
            )

        if (
            last.casefold().rstrip('"”')
            != str(item["closing_punchline"]).strip().casefold().rstrip('"”')
        ):
            errors.append(
                f"Script {i} punchline doesn't exactly match final sentence."
            )

        url = str(item["source_url"]).strip()
        if url not in known:
            errors.append(
                f"Script {i} uses a URL not in the selected story list."
            )
        if url in used_urls:
            errors.append("Every script must use a different source URL.")
        used_urls.add(url)

        title_key = re.sub(
            r"[^a-z0-9]", "", str(item["title"]).lower()
        )
        premise_key = re.sub(
            r"[^a-z0-9]", "", str(item["premise"]).lower()
        )

        if title_key in used_titles:
            errors.append("Script titles must be unique.")
        if premise_key in used_premises:
            errors.append("Script premises must be distinct.")

        used_titles.add(title_key)
        used_premises.add(premise_key)

        item["script"] = spoken
        item["word_count"] = count
        result.append(item)

    return result, errors


def generate_scripts(stories):
    prompt = writer_prompt(stories)
    previous_response = ""
    errors = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(
            f"Comedy writing and quality check: "
            f"attempt {attempt}/{MAX_ATTEMPTS}"
        )

        if attempt == 1:
            current_prompt = prompt
        else:
            current_prompt = f"""
Rewrite the COMPLETE JSON response from scratch to fix these failures.
Do not merely add filler to short scripts. Preserve the strongest ideas,
but make the writing genuinely funnier and more connected. Use the
original story details below. Return valid JSON only.

FAILURES:
{json.dumps(errors, ensure_ascii=False, indent=2)}

PREVIOUS DRAFT:
{previous_response[:16000]}

ORIGINAL STORY DATA:
{json.dumps(stories, ensure_ascii=False, indent=2)}

Requirements: exactly 3 distinct scripts, 90–112 spoken words each,
a hook identical to the first sentence, a final punchline identical to
the last sentence, three different source URLs, distinct premises and
titles. Keep escalation connected to one comic idea. Remove generic
filler, predictable comparisons, and unrelated jokes.
Use the exact JSON structure from the previous writing instructions.
"""

        try:
            previous_response = call_gemini(current_prompt, 0.98)
            data = extract_json(previous_response)
            scripts, errors = validate_scripts(data, stories)

            if not errors and len(scripts) == TARGET_SCRIPTS:
                print("All scripts passed structural validation.")
                return scripts

            print("Draft validation issues:")
            for error in errors:
                print(" - " + error)

        except Exception as exc:
            errors = [f"Invalid model response: {exc}"]
            print(f"Could not validate draft: {exc}")

        if attempt < MAX_ATTEMPTS:
            print("Rewriting all three scripts with the feedback...")
            time.sleep(1)

    raise RuntimeError(
        f"Unable to produce three valid scripts after {MAX_ATTEMPTS} attempts. "
        "No new output file was saved. See validation messages above."
    )


def render_markdown(scripts):
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    lines = [
        f"# Daily Comedy Scripts — {today}",
        "",
        "> AI-assisted comedy drafts. Verify the original reporting before "
        "recording. The fact-check reminder is not proof.",
        "",
    ]

    for i, item in enumerate(scripts, 1):
        lines.extend([
            f"## {i}. {item['title']}",
            "",
            f"**News story:** {item['story_title']}",
            f"**Source:** {item['source']}",
            f"**Source link:** {item['source_url']}",
            f"**Comic premise:** {item['premise']}",
            f"**Length:** {item['word_count']} words (target: 45–50 seconds)",
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
    path = OUTPUT_DIR / f"comedy-scripts-{today}.md"
    path.write_text(content, encoding="utf-8")
    print(f"Saved scripts to: {path}")
    return path


def main():
    print("Daily Comedy Agent — premise-first comedy engine")
    print(f"Gemini model: {MODEL or 'gemini-3.5-flash-lite'}")

    news = collect_news()
    if len(news) < TARGET_SCRIPTS:
        raise RuntimeError(
            f"Only {len(news)} usable news stories were found. Try again later."
        )

    print(f"Collected {len(news)} news headlines.")
    chosen = choose_stories(news)

    print("Selected stories:")
    for story in chosen:
        print(" - " + story["title"])

    scripts = generate_scripts(chosen)
    path = save_output(render_markdown(scripts))

    print("\nFinal scripts:")
    for i, item in enumerate(scripts, 1):
        print(f"{i}. {item['title']} — {item['word_count']} words")

    print(f"Output file: {path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
