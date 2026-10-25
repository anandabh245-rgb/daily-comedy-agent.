import os
import re
import json
import time
import html
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

from datetime import datetime
from pathlib import Path
from email.utils import parsedate_to_datetime


# ============================================================
# DAILY COMEDY AGENT — SHORT-FORM EDITION
#
# Target: 45–50 seconds of spoken comedy.
# Style: Modern stand-up, storytelling, sharp roasting,
#        escalating jokes, and memorable punchlines.
# ============================================================

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
).strip()

OUTPUT_DIR = Path("output")

SCRIPT_COUNT = 3

MIN_WORDS = 90
MAX_WORDS = 110

REQUEST_TIMEOUT = 25
MAX_HEADLINES = 35
MAX_RETRIES = 3

USER_AGENT = (
    "Mozilla/5.0 (compatible; DailyComedyAgent/4.0)"
)


# ============================================================
# NEWS SEARCH QUERIES
# ============================================================

GOOGLE_NEWS_QUERIES = [
    "US UK celebrity entertainment news when:2d",
    "viral internet culture influencer news when:2d",
    "movies streaming music pop culture news when:2d",
    "celebrity reality television controversy when:2d",
    "hip hop social media celebrity drama when:2d",
]

FALLBACK_FEEDS = [
    (
        "BBC Entertainment",
        "https://feeds.bbci.co.uk/news/"
        "entertainment_and_arts/rss.xml",
    ),
    (
        "The Guardian Film",
        "https://www.theguardian.com/film/rss",
    ),
]


# ============================================================
# UTILITIES
# ============================================================

def log(message):
    print(
        f"[Daily Comedy Agent] {message}",
        flush=True
    )


def clean_text(value):
    if not value:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def word_count(text):
    return len(
        re.findall(
            r"\b[\w]+(?:['’][\w]+)*\b",
            text
        )
    )


def fetch_url(url, timeout=REQUEST_TIMEOUT):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, application/xml, "
                "text/xml, text/html, */*"
            ),
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:
        return response.read()


def normalize_url(url):
    url = clean_text(url)

    if url.startswith(("http://", "https://")):
        return url

    return ""


# ============================================================
# NEWS COLLECTION
# ============================================================

def google_news_feed_url(query):
    encoded_query = urllib.parse.quote_plus(query)

    return (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}"
        "&hl=en-US&gl=US&ceid=US:en"
    )


def parse_rss(xml_data, feed_name):
    stories = []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        log(f"RSS parsing failed for {feed_name}: {exc}")
        return stories

    for item in root.iter():
        tag = item.tag.split("}")[-1].lower()

        if tag not in ("item", "entry"):
            continue

        fields = {}

        for child in item:
            key = child.tag.split("}")[-1].lower()
            value = child.text or ""

            if key == "link" and not value:
                value = child.attrib.get("href", "")

            if key not in fields:
                fields[key] = value

        title = clean_text(fields.get("title", ""))

        link = normalize_url(
            fields.get("link", "")
        )

        description = clean_text(
            fields.get("description", "")
            or fields.get("summary", "")
            or fields.get("content", "")
        )

        published = (
            fields.get("pubdate", "")
            or fields.get("published", "")
            or fields.get("updated", "")
        )

        source_name = feed_name

        for child in item:
            if child.tag.split("}")[-1].lower() == "source":
                source_name = clean_text(
                    child.text or feed_name
                )
                break

        if not title or not link:
            continue

        stories.append(
            {
                "title": title,
                "url": link,
                "description": description[:1200],
                "source": source_name,
                "published": clean_text(published),
            }
        )

    return stories


def fetch_feed(url, name):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = fetch_url(url)
            stories = parse_rss(data, name)

            log(
                f"{name}: found {len(stories)} stories"
            )

            return stories

        except Exception as exc:
            log(
                f"{name}: attempt {attempt}/"
                f"{MAX_RETRIES} failed: {exc}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)

    return []


def parse_published_date(value):
    if not value:
        return None

    try:
        return parsedate_to_datetime(value)
    except Exception:
        pass

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except Exception:
        return None


def collect_news():
    all_stories = []
    seen_titles = set()

    for query in GOOGLE_NEWS_QUERIES:
        url = google_news_feed_url(query)

        results = fetch_feed(
            url,
            "Google News"
        )

        for story in results:
            key = re.sub(
                r"[^a-z0-9]+",
                "",
                story["title"].lower()
            )

            if key and key not in seen_titles:
                seen_titles.add(key)
                all_stories.append(story)

        time.sleep(1)

    if len(all_stories) < SCRIPT_COUNT:
        log(
            "Insufficient Google News stories. "
            "Trying fallback feeds."
        )

        for name, url in FALLBACK_FEEDS:
            results = fetch_feed(url, name)

            for story in results:
                key = re.sub(
                    r"[^a-z0-9]+",
                    "",
                    story["title"].lower()
                )

                if key and key not in seen_titles:
                    seen_titles.add(key)
                    all_stories.append(story)

    def sort_key(story):
        date = parse_published_date(
            story["published"]
        )

        if date is None:
            return 0

        try:
            return date.timestamp()
        except Exception:
            return 0

    all_stories.sort(
        key=sort_key,
        reverse=True
    )

    log(
        f"Unique stories collected: {len(all_stories)}"
    )

    return all_stories[:MAX_HEADLINES]


# ============================================================
# PROFESSIONAL SHORT-FORM COMEDY BRIEF
# ============================================================

def writing_rules():
    return """
ROLE:
You are an elite short-form stand-up comedy writer,
comedy storyteller, and audience-retention specialist.

You write for an Indian YouTuber speaking directly to
an international English-speaking audience.

The target audience includes viewers in the USA, UK,
Australia, Germany, India, and other countries.

The style combines:
- Modern stand-up comedy.
- Funny storytelling.
- Sharp, intelligent roasting.
- Unexpected comparisons.
- Meme-aware observations.
- Natural conversational delivery.
- An Indian perspective used creatively.
- Strong punchlines and satisfying callbacks.

THE OBJECTIVE:
Create short comedy videos that make people stop scrolling,
become curious about the story, laugh throughout, and want
to hear the final punchline.

The script must sound like a comedian talking to an audience,
not an AI summarizing a news article.

LENGTH:
Every spoken monologue MUST contain 90 to 110 words.

Target delivery duration: approximately 45–50 seconds,
depending on speaking speed, pauses, and performance.

Never add filler just to reach a word count.
Never sacrifice the final punchline to shorten the script.

MANDATORY COMEDY STRUCTURE:

STAGE 1 — THE FIRST 3 SECONDS:
Open with a genuinely funny, surprising, specific line.

The first sentence must immediately create curiosity,
surprise, recognition, or an unexpected mental image.

No greetings.
No introductions.
No background explanation.
No announcing the headline.
No "Have you ever wondered?"
No "Today we're talking about."
No "So, apparently."

The hook must work even for someone who has not seen
the news story.

STAGE 2 — THE NEXT 10 SECONDS:
Establish one strong central comedic premise.

The premise must give the audience a reason to stay.
Introduce an absurd situation, an unexpected interpretation,
or a funny contradiction connected to the story.

Do not explain the entire news article.

STAGE 3 — THE MIDDLE:
Escalate the same premise.

Use increasingly funny observations, vivid comparisons,
short storytelling, reversals, callbacks, and surprise.

Every line should do at least one of these things:
- Make the central idea funnier.
- Add a surprising new detail.
- Raise the absurdity.
- Create anticipation for the next joke.
- Set up a later punchline.

Do not produce a random list of unrelated jokes.

Do not repeat a joke in different words.

STAGE 4 — THE FINAL PAYOFF:
The final sentence must be the strongest available punchline.

Use a surprising reversal, a clever callback, an unexpected
comparison, or a concise final image.

The ending must reward the audience for staying.

Do not finish with a news summary.
Do not explain why the joke is funny.
Do not finish with a moral lesson.
Do not finish with a generic question.
Do not add "like and subscribe" to the punchline.

AUDIENCE RETENTION:

Build a curiosity gap early.

Give the audience a reason to anticipate what happens next.

Escalate the jokes instead of revealing every funny idea
in the opening.

Use a small setup that can pay off in the final line.

Prefer concrete, visual, specific comedy over vague claims.

Make the audience feel that the next line could be funnier
or more surprising than the previous one.

Do not artificially label sections or insert stage directions.

COMEDY QUALITY:

Be bold, clever, specific, and entertaining.

Prefer funny storytelling to generic commentary.

Roast absurd behavior, public entertainment, internet habits,
media exaggeration, and the situation itself.

Avoid bland article summaries followed by one joke.

Avoid lazy jokes about AI, influencers, celebrities,
or cancel culture unless the story gives the joke a fresh angle.

Use Indian cultural comparisons selectively and naturally.
Do not repeatedly use family WhatsApp groups, uncles,
weddings, or property disputes as automatic punchlines.

Make the jokes accessible to international viewers.

Use natural spoken English, varied sentence lengths,
and a rhythm that sounds good when read aloud.

Do not make every sentence long.

FACTUAL RESPONSIBILITY:

Use the supplied headlines and snippets as limited evidence.

Do not invent events, quotations, private motives,
relationships, scandals, or allegations.

Do not turn an unconfirmed rumor into a confirmed fact.

If a headline describes speculation, make the speculation,
media behavior, or absurdity of the situation the target.

Do not claim to have read an article if only a headline
or snippet was supplied.

Do not make the comedian's joke sound like a verified claim.

STORY SELECTION:

Choose three distinct stories.

Prefer stories with a strong comedic contradiction,
relatable behavior, surprising public reactions,
absurd entertainment situations, or internet culture.

Avoid stories that have no usable comedic angle.

Use different central premises and different joke structures
for all three scripts.

OUTPUT FORMAT:

Return valid JSON only. No Markdown fences.

Use exactly this structure:

{
  "scripts": [
    {
      "title": "Short, catchy comedy title",
      "story_title": "Exact supplied headline",
      "central_premise": "One clear comedic premise",
      "hook": "The exact first sentence",
      "spoken_monologue": "Complete spoken monologue",
      "ending_punchline": "The exact final sentence",
      "fact_check_note": "What needs verification"
    }
  ]
}

Return exactly three scripts.

The hook must be the first sentence of the monologue.

The ending_punchline must be the final sentence.

Each monologue must contain 90 to 110 spoken words.

The premise must be developed throughout the monologue.

Return no word counts. The program calculates them.

Return no additional text outside the JSON object.
"""


# ============================================================
# GEMINI API
# ============================================================

def gemini_generate(prompt):
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. "
            "Check GitHub repository Actions secrets."
        )

    endpoint = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{urllib.parse.quote(MODEL, safe='')}"
        ":generateContent"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        },
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": API_KEY,
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=90
    ) as response:
        response_text = response.read().decode(
            "utf-8"
        )

    data = json.loads(response_text)

    candidates = data.get("candidates", [])

    if not candidates:
        raise RuntimeError(
            "Gemini returned no candidates. "
            f"Feedback: {data.get('promptFeedback', {})}"
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    result = "\n".join(
        part.get("text", "")
        for part in parts
        if part.get("text")
    ).strip()

    if not result:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    return result


def parse_json_response(response_text):
    value = response_text.strip()

    value = re.sub(
        r"^```(?:json)?\s*",
        "",
        value,
        flags=re.IGNORECASE
    )

    value = re.sub(
        r"\s*```$",
        "",
        value
    )

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass

    start = value.find("{")
    end = value.rfind("}")

    if start >= 0 and end > start:
        return json.loads(value[start:end + 1])

    raise ValueError(
        "The Gemini response was not valid JSON."
    )


# ============================================================
# BUILD NEWS CONTEXT
# ============================================================

def build_news_context(stories):
    blocks = []

    for index, story in enumerate(
        stories,
        start=1
    ):
        blocks.append(
            f"STORY {index}\n"
            f"Headline: {story['title']}\n"
            f"Publisher: {story['source']}\n"
            f"Published: "
            f"{story['published'] or 'Unknown'}\n"
            f"URL: {story['url']}\n"
            f"Available snippet: "
            f"{story['description'] or 'No snippet'}\n"
        )

    return "\n".join(blocks)


# ============================================================
# SCRIPT VALIDATION
# ============================================================

def validate_script(script):
    required_fields = [
        "title",
        "story_title",
        "central_premise",
        "hook",
        "spoken_monologue",
        "ending_punchline",
        "fact_check_note",
    ]

    if not isinstance(script, dict):
        raise ValueError(
            "A generated script is not a JSON object."
        )

    for field in required_fields:
        value = script.get(field)

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Missing or empty field: {field}"
            )

    title = clean_text(script["title"])
    story_title = clean_text(script["story_title"])
    premise = clean_text(script["central_premise"])
    hook = clean_text(script["hook"])
    monologue = clean_text(script["spoken_monologue"])
    ending = clean_text(script["ending_punchline"])
    fact_note = clean_text(script["fact_check_note"])

    count = word_count(monologue)

    if not MIN_WORDS <= count <= MAX_WORDS:
        raise ValueError(
            f"'{title}' has {count} words. "
            f"Required range: {MIN_WORDS}-{MAX_WORDS}."
        )

    if not monologue.lower().startswith(hook.lower()):
        raise ValueError(
            f"'{title}': the hook must begin the monologue."
        )

    if not monologue.rstrip().lower().endswith(
        ending.rstrip().lower()
    ):
        raise ValueError(
            f"'{title}': the final punchline must end "
           
