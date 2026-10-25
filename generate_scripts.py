
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
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
OUTPUT_DIR = Path("output")

MAX_STORIES = 3
MIN_WORDS = 85
MAX_WORDS = 155
TARGET_MIN_WORDS = 105
TARGET_MAX_WORDS = 140

SEARCHES = [
    "US UK celebrity entertainment when:2d",
    "viral internet culture influencer news when:2d",
    "movies music streaming pop culture when:2d",
    "celebrity interviews reality TV entertainment when:2d",
]


def download(url, attempts=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ComedyScriptAgent/1.0)"
    }

    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read()
        except Exception as exc:
            print(f"Download attempt {attempt + 1}: {exc}")
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

    stories = []

    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()

        if tag not in ("item", "entry"):
            continue

        fields = {}

        for child in node:
            key = child.tag.split("}")[-1].lower()

            if key == "link":
                link = child.attrib.get("href", "") or child.text or ""
                fields["link"] = link.strip()

            elif key in ("title", "description", "summary", "content"):
                if key not in fields:
                    fields[key] = clean("".join(child.itertext()))

        title = fields.get("title", "")
        link = fields.get("link", "")

        snippet = (
            fields.get("description", "")
            or fields.get("summary", "")
            or fields.get("content", "")
        )

        if title and link.startswith("http"):
            stories.append({
                "title": title,
                "url": link,
                "snippet": snippet[:900],
            })

    return stories


def collect_stories():
    stories = []
    seen = set()

    for query in SEARCHES:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )

        print(f"Searching: {query}")

        for story in read_feed(url):
            key = re.sub(r"\W+", "", story["title"].lower())

            if key and key not in seen:
                seen.add(key)
                stories.append(story)

    print(f"Collected {len(stories)} unique stories.")
    return stories[:15]


def call_gemini(prompt, temperature=0.9):
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check repository secrets."
        )

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(MODEL, safe="")
        + ":generateContent?"
        + urllib.parse.urlencode({"key": API_KEY})
    )

    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    body = json.dumps(payload).encode("utf-8")

    for attempt in range(3):
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            candidates = result.get("candidates", [])

            if not candidates:
                feedback = result.get("promptFeedback", {})
                raise RuntimeError(
                    f"Gemini returned no usable candidate. {feedback}"
                )

            parts = candidates[0].get("content", {}).get("parts", [])

            response_text = next(
                (
                    part.get("text", "").strip()
                    for part in parts
                    if part.get("text")
                ),
                "",
            )

            response_text = re.sub(
                r"^```(?:json)?\s*", "", response_text
            )
            response_text = re.sub(
                r"\s*```$", "", response_text
            )

            parsed = json.loads(response_text)

            if not isinstance(parsed, dict):
                raise RuntimeError(
                    "Gemini response was not a JSON object."
                )

            return parsed

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(
                "utf-8", errors="replace"
            )[:1200]

            print(
                f"Gemini attempt {attempt + 1}: "
                f"HTTP {exc.code}: {detail}"
            )

            if exc.code in (400, 401, 403, 404):
                break

        except Exception as exc:
            print(f"Gemini attempt {attempt + 1}: {exc}")

        if attempt < 2:
            time.sleep(3 * (attempt + 1))

    raise RuntimeError(
        "Gemini generation failed. Check the model name, "
        "API access, and quota."
    )


def writing_rules():
    return """
ROLE

You are a fearless, highly inventive stand-up comedy writer
and entertainment commentator for a YouTube channel performed
by an Indian creator speaking directly to camera.

Write like a sharp human comic, not a news presenter,
content marketer, or generic AI assistant.

AUDIENCE

US, UK, Australia, Canada and other English-speaking audiences
who enjoy celebrity culture, entertainment, internet drama,
streaming, memes and stand-up.

Jokes must be understandable internationally.

Use an Indian perspective naturally when it adds a fresh angle.
Never force it into every script.

THE CENTRAL RULE

Every script needs ONE specific comedic premise: a strong,
funny interpretation of the story that the whole monologue
keeps developing.

Do not merely summarize the news and attach unrelated jokes.
Find the absurd human truth, contradiction, ego, awkwardness,
hypocrisy, or ridiculous consequence inside the story.

COMEDY STYLE

Mix funny real-life storytelling, sharp but fair roasting,
surprising comparisons, vivid images, escalating absurdity,
and meme-aware punchlines.

Sound conversational and performable aloud.

Be specific, bold, clever and fresh.

Avoid generic lines like "the internet went crazy,"
"you can't make this up," "in today's world," and "this is wild."

Avoid repeating the headline as the opening.
Avoid filler, motivational endings, and lists of disconnected
one-liners.

STRUCTURE

Open with a suspenseful, funny hook in the first sentence,
ideally creating a question or an unexpected image.

Establish the story quickly.

Introduce the central premise, then escalate it with two or
three increasingly funny turns.

Add a strong final punchline that feels earned.

Keep the pace tight for a roughly one-minute direct-to-camera
performance.

FACTUAL CARE

Use only the supplied headline and snippet as factual grounding.

Do not invent quotes, motives, private details, dates,
accusations, or events.

Clearly distinguish a joke or hypothetical comparison from
a factual claim.

Do not present rumors as confirmed facts.

Roast public behavior and public-facing decisions, not
protected traits or private individuals.

Avoid hateful, demeaning, or discriminatory jokes.

If the story is too thin or serious for comedy, say so and
create a careful angle without mocking victims or harm.

LENGTH AND DELIVERY

Aim for 105–140 spoken words.
Hard limit: 85–155 words.

Use natural spoken English and short sentences.

No stage directions, camera directions, headings inside the
spoken monologue, emojis, or explanations of the joke.

The final line must be the strongest punchline, not a summary.

OUTPUT

Return valid JSON only, with exactly these keys:
"title", "premise", "script", "angle_note".

The script must be one spoken monologue.

The title should be punchy and concise.

The premise should describe the single comedic idea in one
sentence.

The angle_note should briefly state the factual basis and
any uncertainty.

Do not wrap the JSON in Markdown fences.
""".strip()


def word_count(text):
    return len(re.findall(r"\b[\w’'-]+\b", text or ""))


def generate_script(story):
    prompt = f"""{writing_rules()}

Write one original comedy monologue about this story.

HEADLINE: {story['title']}
PUBLISHER LINK: {story['url']}
AVAILABLE SNIPPET: {story.get('snippet', '') or '(No snippet available; rely only on the headline and be cautious.)'}

Remember: one central comedic premise, a funny first sentence,
escalating jokes, and a strong final punchline.

Aim for {TARGET_MIN_WORDS}–{TARGET_MAX_WORDS} spoken words.
Return the required JSON object only.
"""

    result = call_gemini(prompt)

    title = clean(str(result.get("title", ""))) or story["title"]
    premise = clean(str(result.get("premise", "")))
    script = clean(str(result.get("script", "")))
    angle_note = clean(str(result.get("angle_note", "")))

    if not script:
        raise RuntimeError("Gemini returned an empty script.")

    count = word_count(script)

    if count < MIN_WORDS or count > MAX_WORDS:
        revise_prompt = f"""Rewrite the following spoken comedy
monologue to be between {TARGET_MIN_WORDS} and
{TARGET_MAX_WORDS} words.

Preserve its central premise, make the hook and final punchline
strong, and do not add unsupported factual claims.

Return valid JSON only with keys title, premise, script,
angle_note.

Original JSON:
{json.dumps({
    'title': title,
    'premise': premise,
    'script': script,
    'angle_note': angle_note
})}
"""

        revised = call_gemini(revise_prompt, temperature=0.75)

        title = clean(str(revised.get("title", title))) or title
        premise = clean(str(revised.get("premise", premise))) or premise
        script = clean(str(revised.get("script", script))) or script
        angle_note = clean(
            str(revised.get("angle_note", angle_note))
        ) or angle_note

    return {
        "title": title,
        "premise": premise,
        "script": script,
        "angle_note": angle_note,
        "source_title": story["title"],
        "source_url": story["url"],
        "word_count": word_count(script),
    }


def build_prompt_for_story_selection(stories):
    listing = [
        {
            "index": i,
            "title": item["title"],
            "snippet": item.get("snippet", "")[:350],
            "url": item["url"],
        }
        for i, item in enumerate(stories)
    ]

    return f"""Choose up to {MAX_STORIES} distinct stories that
offer the strongest potential for funny, safe, specific stand-up
commentary for an international English-speaking audience.

Prefer fresh, clear, absurd, high-interest entertainment or
internet-culture stories.

Exclude tragedy, serious harm, and stories where jokes would
target victims.

Do not invent facts.

Return valid JSON only in this shape:
{{"indices": [0, 2, 4]}}

Use only indices that appear in the list and do not repeat
an index.

STORIES:
{json.dumps(listing, ensure_ascii=False)}
"""


def select_stories(stories):
    if len(stories) <= MAX_STORIES:
        return stories

    try:
        result = call_gemini(
            build_prompt_for_story_selection(stories),
            temperature=0.25,
        )

        indices = result.get("indices", [])
        selected = []
        used = set()

        for value in indices:
            if (
                isinstance(value, int)
                and 0 <= value < len(stories)
                and value not in used
            ):
                selected.append(stories[value])
                used.add(value)

            if len(selected) >= MAX_STORIES:
                break

        if selected:
            return selected

    except Exception as exc:
        print(
            "Story selection failed; using first available "
            f"stories: {exc}"
        )

    return stories[:MAX_STORIES]


def save_output(scripts):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    output_path = OUTPUT_DIR / f"comedy-scripts-{today}.md"

    lines = [
        f"# Daily Comedy Scripts — {today}",
        "",
        "> AI-assisted comedy drafts. Verify the original "
        "reporting before recording. The fact-check reminder "
        "is not proof.",
        "",
    ]

    if not scripts:
        lines.extend(["No scripts were generated today.", ""])

    for number, item in enumerate(scripts, start=1):
        lines.extend([
            f"## Script {number}: {item['title']}",
            "",
            f"**Central premise:** "
            f"{item.get('premise', '') or 'Not supplied'}",
            "",
            "**Spoken monologue**",
            "",
            item["script"],
            "",
            f"**Word count:** {item['word_count']}",
            "",
            f"**Story used:** {item['source_title']}",
            f"**Source link:** {item['source_url']}",
            f"**Fact-check note:** "
            f"{item.get('angle_note', '') or 'Verify the source before recording.'}",
            "",
            "---",
            "",
        ])

    output_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Saved {len(scripts)} script(s) to {output_path}")
    return output_path


def main():
    print("Daily Comedy Script Agent starting.")
    print(f"Using Gemini model: {MODEL}")

    stories = collect_stories()

    if not stories:
        raise RuntimeError(
            "No news stories were collected from Google News RSS. "
            "Try again later."
        )

    chosen = select_stories(stories)

    print(
        f"Selected {len(chosen)} story/stories "
        "for script generation."
    )

    scripts = []

    for index, story in enumerate(chosen, start=1):
        print(
            f"Generating script {index}/{len(chosen)}: "
            f"{story['title']}"
        )

        try:
            item = generate_script(story)
            scripts.append(item)

            print(
                f"Generated '{item['title']}' "
                f"({item['word_count']} words)."
            )

        except Exception as exc:
            print(
                f"Could not generate a script for "
                f"'{story['title']}': {exc}"
            )

    if not scripts:
        raise RuntimeError(
            "No scripts were generated successfully. "
            "See the log above."
        )

    save_output(scripts)


if __name__ == "__main__":
    main()
