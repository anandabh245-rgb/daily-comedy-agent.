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

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

OUTPUT_DIR = Path("output")
MAX_STORIES = 3
MIN_WORDS = 85
MAX_WORDS = 155

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
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as response:
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
            "temperature": temperature,
            "responseMimeType": "application/json"
        }
    }

    body = json.dumps(payload).encode("utf-8")

    for attempt in range(3):
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))

            candidates = result.get("candidates", [])

            if not candidates:
                raise RuntimeError(
                    "Gemini returned no usable candidate."
                )

            text = candidates[0]["content"]["parts"][0]["text"].strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            return json.loads(text)

        except Exception as exc:
            print(f"Gemini attempt {attempt + 1}: {exc}")

            if attempt < 2:
                time.sleep(3 * (attempt + 1))

    raise RuntimeError("Gemini generation failed after three attempts.")


def writing_rules():
    return """
You are the lead comedy writer for a YouTube channel performed
by an Indian creator speaking directly to the camera.

AUDIENCE:
Viewers in the US, UK, Australia, Canada and other English-speaking
markets who enjoy celebrity news, entertainment, internet culture,
memes and modern stand-up comedy.

THE COMEDY VOICE:
A distinctive mixture of:
1. Funny real-life storytelling.
2. Sharp, clever roasting.
3. Internet-culture and meme-style observations.

The creator should sound like a naturally funny person telling a
friend an unbelievable story, not a newsreader or an AI assistant.

STRUCTURE:
- First 1-2 sentences: a strong hook.
- Set up one clear comedic idea.
- Build through 2-4 increasingly ridiculous comparisons or jokes.
- Include a specific observation people recognise from real life.
- Finish with a genuinely surprising punchline, twist or callback.

QUALITY RULES:
- Aim for 100-140 spoken words.
- Make every sentence earn its place.
- Use specific details, vivid comparisons and natural spoken rhythm.
- Use modern slang only where it makes a joke better.
- Let the creator's Indian perspective emerge naturally; don't force
  Indian references into every script.
- Roast public behaviour, absurd situations and celebrity culture.
- Never rely on insults about protected characteristics.
- No harassment, slurs or cruel attacks on private individuals.
- Avoid repetitive jokes and interchangeable punchlines.
- Avoid generic AI phrases, fake quotes and fabricated reactions.
- Do not invent events, numbers, motives or celebrity behaviour.
- Do not state an allegation as fact merely because it appears
  in a headline.

FACTUAL RULES:
Use only the facts supported by the supplied title and snippet.
Keep the factual setup narrow. Comedy can exaggerate an opinion,
analogy or hypothetical situation, but must not invent real events.
The supplied URL must be copied exactly.
Never claim independent fact-checking has happened.

Avoid openings such as:
"You won't believe..."
"In today's world..."
"Let's talk about..."
"So apparently..."

The ending must be stronger than a generic summary.
"""


def draft_scripts(stories):
    prompt = writing_rules() + """

Choose up to THREE distinct stories with strong comedy potential.

STORY RECORDS:
""" + json.dumps(stories, ensure_ascii=False)

    prompt += """

Return valid JSON only:
{
  "scripts": [
    {
      "headline": "Short, interesting title",
      "source_url": "Exact URL from the supplied records",
      "monologue": "Complete spoken monologue",
      "caption": "Short, funny caption",
      "description": "Brief description and relevant hashtags",
      "fact_check_note": "Specific factual claim to verify before recording"
    }
  ]
}

Choose different stories. Do not force weak stories into the result.
Return fewer than three if there are not enough suitable stories.
"""

    result = call_gemini(prompt, temperature=0.95)
    return result.get("scripts", [])


def review_and_rewrite(stories, drafts):
    prompt = writing_rules() + """

You are now a tough professional stand-up editor reviewing draft
scripts written for this channel.

NEWS RECORDS:
""" + json.dumps(stories, ensure_ascii=False) + """

DRAFTS TO REVIEW:
""" + json.dumps(drafts, ensure_ascii=False) + """

For each draft, silently evaluate:
- Hook strength
- Originality
- Relatable observation
- Joke density
- Escalation
- Spoken naturalness
- Ending punchline
- Factual support

Reject lazy jokes, generic observations, repetitive meme slang,
weak endings and claims unsupported by the supplied news record.

REWRITE the scripts rather than merely commenting on them.
Keep the best original ideas, but make the whole performance sharper.
Do not add new factual claims while improving the comedy.
Prefer a strong, specific joke over three weak jokes.
Do not invent a story to fill the quota.

Return valid JSON only, with this exact structure:
{
  "scripts": [
    {
      "headline": "Short, interesting title",
      "source_url": "Exact supplied URL",
      "monologue": "Rewritten spoken monologue",
      "caption": "Short, funny caption",
      "description": "Brief description and relevant hashtags",
      "fact_check_note": "Specific claim to verify before recording"
    }
  ]
}
"""

    result = call_gemini(prompt, temperature=0.85)
    return result.get("scripts", [])


def validate(scripts, stories):
    allowed = {story["url"]: story for story in stories}
    accepted = []
    used_urls = set()

    for item in scripts:
        required = [
            "headline",
            "source_url",
            "monologue",
            "caption",
            "description",
            "fact_check_note",
        ]

        if not isinstance(item, dict):
            print("Skipped invalid script.")
            continue

        if not all(
            isinstance(item.get(key), str) and item[key].strip()
            for key in required
        ):
            print("Skipped script with missing fields.")
            continue

        url = item["source_url"].strip()

        if url not in allowed:
            print("Skipped script with a URL not in the supplied feeds.")
            continue

        if url in used_urls:
            print("Skipped duplicate story.")
            continue

        monologue = item["monologue"].strip()
        word_count = len(re.findall(r"\b[\w'-]+\b", monologue))

        if not MIN_WORDS <= word_count <= MAX_WORDS:
            print(f"Skipped script with {word_count} spoken words.")
            continue

        item["monologue"] = monologue
        item["_story"] = allowed[url]
        item["_word_count"] = word_count

        accepted.append(item)
        used_urls.add(url)

        if len(accepted) >= MAX_STORIES:
            break

    return accepted


def write_output(scripts):
    today = datetime.now().strftime("%Y-%m-%d")
    path = OUTPUT_DIR / f"{today}.md"

    with path.open("w", encoding="utf-8") as file:
        file.write(f"# Daily Comedy Scripts — {today}\n\n")
        file.write(f"Generated scripts: {len(scripts)}\n\n")
        file.write(
            "> AI-assisted comedy drafts. Verify the original reporting "
            "before recording. The fact-check reminder is not proof.\n\n"
        )

        for number, item in enumerate(scripts, 1):
            story = item["_story"]

            file.write(f"## Script {number}: {item['headline']}\n\n")
            file.write(f"**News feed headline:** {story['title']}\n\n")

            if story["snippet"]:
                file.write("**News feed summary:** ")
                file.write(story["snippet"] + "\n\n")

            file.write(
                f"**Google News feed link (may redirect):** "
                f"{item['source_url']}\n\n"
            )

            file.write("### Full Spoken Monologue\n\n")
            file.write(item["monologue"] + "\n\n")

            file.write("### Caption\n\n")
            file.write(item["caption"].strip() + "\n\n")

            file.write("### Video Description\n\n")
            file.write(item["description"].strip() + "\n\n")

            file.write("### Fact-Check Reminder\n\n")
            file.write(item["fact_check_note"].strip() + "\n\n")

            file.write(
                f"**Spoken word count:** {item['_word_count']}\n\n"
            )
            file.write("---\n\n")

    print(f"Saved {len(scripts)} scripts to {path}")


def main():
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check the repository secret."
        )

    OUTPUT_DIR.mkdir(exist_ok=True)

    stories = collect_stories()

    if not stories:
        raise RuntimeError(
            "No stories collected. No new script file was created."
        )

    drafts = draft_scripts(stories)

    if not drafts:
        raise RuntimeError("Gemini returned no initial scripts.")

    print(f"Initial drafts: {len(drafts)}")
    print("Running comedy review and rewrite...")

    try:
        improved = review_and_rewrite(stories, drafts)

        if improved:
            final_candidates = improved
            print("Using reviewed and rewritten drafts.")
        else:
            final_candidates = drafts
            print("Review returned no scripts; using initial drafts.")

    except Exception as exc:
        print(f"Review failed; keeping initial drafts: {exc}")
        final_candidates = drafts

    scripts = validate(final_candidates, stories)

    if not scripts:
        print("Reviewed drafts failed validation; checking initial drafts.")
        scripts = validate(drafts, stories)

    if not scripts:
        raise RuntimeError(
            "No scripts passed validation. No empty output file was saved."
        )

    write_output(scripts)


if __name__ == "__main__":
    main()
                
