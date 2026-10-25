import os
import re
import json
import time
import html
import random
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

# ============================================================
# DAILY COMEDY AGENT
# Version: Premise-First Stand-Up Engine
#
# Purpose:
# - Find current celebrity and internet-culture stories.
# - Turn each story into a 40-45 second comedy routine.
# - Use original jokes, escalating premises and strong endings.
# - Save three scripts for manual review and recording.
# ============================================================

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
).strip()

OUTPUT_DIR = Path("output")
TARGET_SCRIPTS = 3

# About 40-45 seconds at a natural performance pace.
IDEAL_MIN_WORDS = 85
IDEAL_MAX_WORDS = 100

# Allow a little flexibility so a good script isn't rejected
# because of a small word-count difference.
ACCEPT_MIN_WORDS = 75
ACCEPT_MAX_WORDS = 110

MAX_STORY_ATTEMPTS = 4
MAX_HEADLINES_TO_COLLECT = 35
REQUEST_TIMEOUT = 25

USER_AGENT = (
    "Mozilla/5.0 (compatible; DailyComedyAgent/3.0; "
    "+https://github.com/)"
)

SEARCH_QUERIES = [
    "US UK celebrity entertainment news when:2d",
    "viral internet culture influencer news when:2d",
    "movies streaming music pop culture news when:2d",
    "celebrity social media drama when:2d",
    "hip hop celebrity internet controversy when:2d",
]

# ============================================================
# NETWORK HELPERS
# ============================================================

def http_get(url, timeout=REQUEST_TIMEOUT):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, application/xml, "
                "text/xml, text/plain, */*"
            ),
        },
    )

    with urllib.request.urlopen(
        request, timeout=timeout
    ) as response:
        return response.read()


def clean_text(value):
    if not value:
        return ""

    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def fetch_google_news(query):
    encoded_query = urllib.parse.quote(query)

    url = (
        "https://news.google.com/rss/search?q="
        + encoded_query
        + "&hl=en-US&gl=US&ceid=US:en"
    )

    try:
        raw_xml = http_get(url)
        root = ET.fromstring(raw_xml)
    except Exception as exc:
        print(
            "RSS warning for "
            + repr(query)
            + ": "
            + str(exc)[:180]
        )
        return []

    stories = []

    for item in root.findall(".//item"):
        title = clean_text(
            item.findtext("title", default="")
        )

        link = clean_text(
            item.findtext("link", default="")
        )

        source = clean_text(
            item.findtext("source", default="")
        )

        pub_date = clean_text(
            item.findtext("pubDate", default="")
        )

        description = clean_text(
            item.findtext("description", default="")
        )

        if not title or not link:
            continue

        # Avoid accidentally treating malformed RSS entries
        # as valid news stories.
        if len(title) < 12:
            continue

        stories.append({
            "title": title,
            "url": link,
            "source": source or "Google News",
            "published": pub_date,
            "description": description[:450],
        })

    return stories


def collect_stories():
    print("Collecting current entertainment headlines...")

    collected = []
    seen_titles = set()

    for query in SEARCH_QUERIES:
        results = fetch_google_news(query)

        for story in results:
            normalized = re.sub(
                r"[^a-z0-9]+",
                " ",
                story["title"].lower()
            ).strip()

            if normalized in seen_titles:
                continue

            seen_titles.add(normalized)
            collected.append(story)

        # A small pause avoids hammering the RSS service.
        time.sleep(0.25)

    # Keep the freshest available stories near the top.
    def publication_time(story):
        value = story.get("published", "")

        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )
            return parsed.timestamp()
        except Exception:
            return 0

    collected.sort(
        key=publication_time,
        reverse=True
    )

    collected = collected[:MAX_HEADLINES_TO_COLLECT]

    print(
        "Collected "
        + str(len(collected))
        + " distinct headlines."
    )

    return collected


# ============================================================
# STORY SELECTION
# ============================================================

def story_comedy_score(story):
    title = story["title"].lower()
    score = 0

    high_interest_terms = [
        "celebrity", "viral", "internet", "influencer",
        "actor", "actress", "singer", "rapper", "pop star",
        "reality tv", "reality show", "dating", "breakup",
        "marriage", "wedding", "divorce", "scandal",
        "awkward", "feud", "drama", "apolog", "roast",
        "meme", "social media", "tiktok", "instagram",
        "youtube", "netflix", "movie", "music", "album",
        "billionaire", "fashion", "red carpet", "interview",
        "fans", "award", "streaming", "ai", "artificial intelligence",
        "prince", "royal", "reality", "controversy",
    ]

    for term in high_interest_terms:
        if term in title:
            score += 2

    if "how to" in title:
        score -= 2

    if "live updates" in title:
        score -= 1

    if "opinion" in title:
        score -= 1

    # Headlines with a clear conflict or unexpected situation
    # often provide a stronger starting point for a premise.
    conflict_terms = [
        "clash", "fight", "feud", "ban", "leak", "exposed",
        "responds", "reacts", "fires back", "backlash",
        "surprise", "unexpected", "caught", "reveals",
        "confession", "fails", "crisis", "meltdown",
        "apologizes", "denies", "slams", "secret",
    ]

    for term in conflict_terms:
        if term in title:
            score += 2

    return score


def select_stories(stories):
    if not stories:
        return []

    ranked = sorted(
        stories,
        key=story_comedy_score,
        reverse=True
    )

    selected = []
    used_names = set()

    for story in ranked:
        title = story["title"].lower()

        # Avoid selecting several headlines about the same
        # person or event whenever possible.
        words = re.findall(r"[a-z]{4,}", title)
        key_words = set(words)

        if any(
            len(key_words & previous) >= 5
            for previous in used_names
        ):
            continue

        selected.append(story)
        used_names.add(key_words)

        if len(selected) >= TARGET_SCRIPTS:
            break

    # Fill any remaining slots with distinct headlines.
    if len(selected) < TARGET_SCRIPTS:
        selected_urls = {
            story["url"] for story in selected
        }

        for story in ranked:
            if story["url"] in selected_urls:
                continue

            selected.append(story)
            selected_urls.add(story["url"])

            if len(selected) >= TARGET_SCRIPTS:
                break

    return selected


# ============================================================
# THE NEW COMEDY WRITING ENGINE
# ============================================================

COMEDY_RULES = r"""
You are writing original short stand-up comedy for a real
Indian YouTube commentator speaking to a predominantly
American and other English-speaking audience.

THIS IS A COMEDY PERFORMANCE, NOT A NEWS SUMMARY.

Your job is to make the audience laugh, not to explain an
article.

PERFORMANCE LENGTH:
Aim for 85-100 spoken words. This should take approximately
40-45 seconds when performed with natural pauses and emphasis.
Never write a long introduction.

THE COMEDY STRUCTURE:

1. THE IMMEDIATE LAUGH:
Start with a funny, surprising observation or a strong joke.
The first sentence must sound like a comedian starting a bit,
not a reporter introducing a headline.

2. THE COMEDIC PREMISE:
Find ONE ridiculous, relatable or revealing angle in the story.
Ask yourself what makes this situation absurd if you look at it
from an everyday person's perspective.

3. THE ESCALATION:
Build on that same idea. Each new sentence should make the
original premise more ridiculous, more specific or more
recognizable. Do not jump randomly between unrelated jokes.

4. THE MISDIRECTION:
Set up an expectation, then turn it into a more surprising
and funnier observation. Use contrasts, reversals, unexpected
comparisons, exaggerated logic and short punchy phrasing.

5. THE FINAL PUNCHLINE:
End on the strongest joke available. Prefer a sharp reversal,
a callback to the opening, or an unexpected final image.
The last line must feel like an actual punchline.

COMEDY CRAFT:
Use broad techniques found in strong American stand-up:
specific observations, conversational storytelling, misdirection,
exaggeration, rhythm, escalating absurdity, contrast, callbacks,
and jokes about recognizable human behavior.

Do not imitate or reproduce the signature style, wording,
routines or identifiable material of any particular comedian.

VOICE AND PERSONALITY:
The performer is an Indian commentator with a confident,
observant, self-aware point of view. He can make fun of himself,
celebrity culture, online behavior, fame, relationships,
technology and everyday human absurdity.

Make the cultural perspective natural. Do not force an India
reference into every script. Do not use fake accents, stereotypes
or lazy jokes about nationalities.

ORIGINALITY:
Write the joke as if a comedian found a funny idea and developed
it on stage. Do not write five generic one-liners.
Avoid generic openings such as:
"Have you ever noticed..."
"So, apparently..."
"Let's talk about..."
"Today's news is..."
"You won't believe this..."
"Isn't it crazy how..."

Avoid generic endings such as:
"And that's the world we live in."
"What a time to be alive."
"Anyway, that's life."
"Let that sink in."

Avoid tired, obvious comparisons unless you discover a genuinely
new twist. Do not add random jokes just to increase the count.
Every line should serve the central comedic premise.

FACTUAL RESPONSIBILITY:
Use the supplied headline and information as the factual basis.
Do not invent quotes, dialogue, private thoughts, motives,
events, statistics, relationships or allegations.
Do not present speculation as fact.
You may invent an obviously fictional analogy or hypothetical
situation to make a joke, provided the audience will not mistake
it for something that actually happened.

If the headline alone gives limited information, joke about the
public-facing situation or the absurdity of the headline itself.
Do not pretend to know details you have not been given.

TARGET AUDIENCE:
Adults who understand American internet culture, celebrity news,
memes, streaming platforms, relationships and everyday life.
Keep references understandable without lengthy explanation.

SAFETY AND PERFORMANCE:
No slurs, hateful stereotypes, threats or targeted harassment.
Do not turn unverified allegations into facts.
Sharp criticism of public behavior is acceptable.
Do not make the routine sound like a corporate press release.

OUTPUT FORMAT:
Return ONLY the spoken script.
No headline, title, explanation, word count, labels, bullet points,
quotation marks around the entire script, or stage directions.
Use natural spoken English.
"""


def build_prompt(story, previous_attempt="", feedback=""):
    title = story["title"]
    source = story.get("source", "Google News")
    description = story.get("description", "")

    prompt = f"""
{COMEDY_RULES}

STORY HEADLINE:
{title}

PUBLISHER:
{source}

AVAILABLE STORY DESCRIPTION:
{description if description else "No additional description supplied."}

IMPORTANT CREATIVE CHALLENGE:

Do not merely paraphrase this headline.

Find the funniest defensible premise hidden in this situation.
Write one cohesive mini-routine that escalates that premise and
finishes with a genuinely surprising punchline.

The first sentence must already be funny.
The last sentence must deliver the payoff.

Aim for {IDEAL_MIN_WORDS}-{IDEAL_MAX_WORDS} spoken words.
Count the words before returning your answer.

Before answering, silently check:
- Is the opening immediately interesting and funny?
- Is there one clear central premise?
- Does each joke build on the previous joke?
- Is there a specific, surprising observation?
- Does the ending land harder than the opening?
- Is this actually funny, rather than merely clever or informative?
- Are the factual claims supported by the supplied information?
- Is the spoken script within the requested length?

If a line is generic, replace it with a more specific joke.
If the ending is predictable, rewrite it.
Return only the finished spoken script.
"""

    if previous_attempt:
        prompt += f"""

YOUR PREVIOUS DRAFT FAILED VALIDATION.

Rewrite the whole routine rather than adding filler.

PREVIOUS DRAFT:
{previous_attempt}

VALIDATION FEEDBACK:
{feedback}

Keep the central idea only if it works. Improve the jokes,
make the structure tighter, and return only the new script.
"""

    return prompt


# ============================================================
# GEMINI API
# ============================================================

def call_gemini(prompt):
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check the GitHub "
            "repository secret named GEMINI_API_KEY."
        )

    model_name = MODEL
    if not model_name.startswith("models/"):
        model_name = "models/" + model_name

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/"
        + model_name
        + ":generateContent?key="
        + urllib.parse.quote(API_KEY, safe="")
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
            "temperature": 1.0,
            "topP": 0.95,
            "maxOutputTokens": 700,
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=60
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8", errors="replace"
        )

        raise RuntimeError(
            "Gemini API HTTP "
            + str(exc.code)
            + ": "
            + error_body[:900]
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            "Gemini request failed: "
            + str(exc)[:500]
        ) from exc

    candidates = result.get("candidates", [])

    if not candidates:
        block_reason = (
            result.get("promptFeedback", {})
            .get("blockReason", "unknown")
        )

        raise RuntimeError(
            "Gemini returned no candidates. "
            "Block reason: " + str(block_reason)
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    text_parts = [
        part.get("text", "")
        for part in parts
        if part.get("text")
    ]

    answer = "\n".join(text_parts).strip()

    if not answer:
        raise RuntimeError(
            "Gemini returned an empty text response."
        )

    return answer


# ============================================================
# SCRIPT CLEANING AND VALIDATION
# ============================================================

def clean_script(script):
    script = html.unescape(script).strip()

    # Remove Markdown fences if the model ignores instructions.
    script = re.sub(
        r"^\s*```(?:text|markdown)?\s*",
        "",
        script,
        flags=re.IGNORECASE
    )
    script = re.sub(r"\s*```\s*$", "", script)

    # Remove common unwanted labels.
    script = re.sub(
        r"^\s*(?:script|comedy script|routine)\s*:\s*",
        "",
        script,
        flags=re.IGNORECASE
    )

    # Remove accidental title headings.
    script = re.sub(r"^\s*#{1,6}\s*", "", script)

    # Remove stage directions while keeping spoken content.
    script = re.sub(
        r"\[(?:pause|laughs?|beat|audience laughs?|"
        r"looks at camera|smiles?)\]",
        "",
        script,
        flags=re.IGNORECASE
    )

    script = re.sub(
        r"\((?:pause|laughs?|beat|audience laughs?)\)",
        "",
        script,
        flags=re.IGNORECASE
    )

    # Normalize whitespace without destroying punctuation.
    script = re.sub(r"[ \t]+", " ", script)
    script = re.sub(r"\n{3,}", "\n\n", script)

    return script.strip()


def count_words(script):
    return len(
        re.findall(
            r"\b[\w]+(?:['’][\w]+)*\b",
            script,
            flags=re.UNICODE
        )
    )


def validate_script(script):
    if not script:
        return False, "The response was empty."

    words = count_words(script)

    if words < ACCEPT_MIN_WORDS:
        return (
            False,
            "Only "
            + str(words)
            + " words. Expand the routine with stronger "
              "escalation, not filler."
        )

    if words > ACCEPT_MAX_WORDS:
        return (
            False,
            str(words)
            + " words. Tighten the routine to fit "
              "a 40-45 second performance."
        )

    sentences = re.split(
        r"(?<=[.!?])\s+",
        script.strip()
    )

    if len(sentences) < 3:
        return (
            False,
            "The routine needs a clearer setup, escalation "
            "and ending."
        )

    first_sentence = sentences[0].strip().lower()

    weak_openings = [
        "have you ever noticed",
        "today we're talking about",
        "today we are talking about",
        "let's talk about",
        "so apparently",
        "in today's news",
        "according to the news",
        "today's headline",
    ]

    if any(
        first_sentence.startswith(phrase)
        for phrase in weak_openings
    ):
        return (
            False,
            "The opening sounds like a news report. "
            "Start with a funny observation instead."
        )

    weak_endings = [
        "what a time to be alive",
        "and that's the world we live in",
        "and that is the world we live in",
        "let that sink in",
        "anyway, that's life",
    ]

    final_sentence = sentences[-1].strip().lower()

    if any(
        phrase in final_sentence
        for phrase in weak_endings
    ):
        return (
            False,
            "The ending is generic. Replace it with a "
            "specific punchline or callback."
        )

    return True, "Valid: " + str(words) + " words."


def generate_one_script(story, index):
    previous_attempt = ""
    feedback = ""

    print("")
    print(
        "Writing script "
        + str(index)
        + ": "
        + story["title"]
    )
