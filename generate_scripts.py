import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

QUERIES = [
    "US UK celebrity entertainment when:2d",
    "viral internet culture influencer news when:2d",
    "movies streaming music pop culture news when:2d",
    "internet culture dating apps social media trends when:2d",
]


def get_headlines():
    """Collect recent headlines from Google News RSS."""
    stories = []

    for query in QUERIES:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )

        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
            )

            with urllib.request.urlopen(request, timeout=25) as response:
                root = ET.fromstring(response.read())

            for item in root.findall(".//item")[:8]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                published = item.findtext("pubDate", "").strip()

                if title and link:
                    stories.append({
                        "title": title,
                        "link": link,
                        "published": published,
                    })

        except Exception as error:
            print(f"RSS feed warning for '{query}': {error}")

    unique = {}
    for story in stories:
        unique.setdefault(story["title"], story)

    result = list(unique.values())
    print(f"Collected {len(result)} unique headlines.")
    return result


def build_prompt(stories):
    """Build the complete comedy-writing brief."""
    headlines = json.dumps(
        stories[:25],
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
You are the head comedy writer for a distinctive YouTube creator.
Write original, genuinely funny spoken comedy monologues ready
for direct-to-camera performance.

CREATOR AND AUDIENCE:
The performer is an Indian creator speaking English to audiences
in the USA, UK, Canada, and Australia. The delivery should feel
like a stand-up comedian talking directly to the camera, not a
journalist reading the news.

Use the Indian perspective when it naturally improves a joke.
Do not make every joke about India. Never invent the creator's
personal history, family events, education, or experiences.

COMEDY DIRECTION:
FUNNY REAL-LIFE STORYTELLING WITH A KILLER TWIST.

STORY RULES:
1. Each monologue needs ONE central comic premise.
2. Start immediately with a specific confession, awkward situation,
   embarrassing decision, or surprising detail.
3. Establish one relatable problem.
4. Let the narrator make a questionable but understandable choice.
5. Escalate through two or three connected consequences.
6. Use concrete details and natural dialogue where useful.
7. Include at least two funny moments exposing the narrator's own
   flaws, insecurity, bad judgment, or embarrassment.
8. End with an unexpected, earned reversal that changes the meaning
   of an earlier detail.
9. Make the final punchline the strongest joke.
10. Write for natural speech, pauses, facial expressions, and timing.

JOKE QUALITY:
- Prioritize funny situations and human behaviour over clever wording.
- Make the audience picture the scene.
- Mix storytelling with short, sharp punchlines.
- Make the narrator self-aware, imperfect, and relatable.
- Let events create the humour instead of explaining every joke.
- Make each story's premise, escalation, and ending distinct.
- Use conversational English and occasional slang naturally.
- Prefer a surprising consequence over a random comparison.
- Make the script genuinely entertaining when spoken aloud.

AVOID:
- Generic AI jokes, corporate language, and motivational speeches.
- Lists of unrelated one-liners instead of a story.
- Predictable endings about being broke, deleting an app, or needing
  therapy unless the particular story makes that ending surprising.
- Automatic jokes about Indian parents, aunties, WhatsApp groups,
  strict teachers, accents, or arranged marriage.
- Forced slang, repetitive lists of three, and random metaphors.
- Copying any comedian's distinctive voice, jokes, or scripts.
- Making the performer sound like a news presenter.

NEWS AND FACT-CHECKING:
The headlines below are research leads, not verified facts.
Use a news story only if it creates a strong comedy premise.
Preserve verifiable facts and clearly separate jokes from facts.
Never invent quotes, scandals, allegations, relationships, or events
involving real people. Do not imply someone said or did something
unless the source supports it. Avoid tragedies and vulnerable people.
If a headline is weak, choose an evergreen situation about online
life, friendships, dating, work, awkward misunderstandings,
technology, or the narrator's own questionable decisions.
Do not claim something is viral without evidence.

CREATE EXACTLY THREE DISTINCT MONOLOGUES.

    
SCRIPT REQUIREMENTS:
- Create exactly three scripts with different premises.
- Each spoken monologue must contain 110-145 words.
- Do not count the title, captions, description, or source as spoken words.
- Use different types of escalation and different kinds of twists.
- Do not make all three scripts about celebrities or movies.
- Prefer strong comedy over mentioning lots of trending topics.
- Include a timely story only when a suitable, credible source exists.
- At least one script should use an evergreen everyday situation.

SILENT QUALITY CHECK:
Before returning each script, check that the opening grabs attention,
the story escalates naturally, the jokes sound believable aloud, and
the ending genuinely surprises the audience.
Rewrite weak or predictable sections. Do not output your scores
or your internal evaluation.

OUTPUT FORMAT:
Return readable Markdown only, using this structure for each script:

## Script 1: Catchy title

**Topic:** One-sentence premise.

**Source:** Full source URL for a factual news premise, or
"No factual source needed" for evergreen comedy.

**Spoken monologue:**
The complete 110-145-word performance, ready to read to camera.

**On-screen captions:**
- First short, funny caption.
- Second short, funny caption.
- Third short, funny caption.

**Video description:** One engaging sentence and relevant hashtags.

**Fact-check reminder:** Explain what needs verification, or write
"No specific factual claims to verify" for evergreen comedy.

Repeat this format for Script 2 and Script 3.

Use correct punctuation, readable paragraphs, and catchy titles.
Do not include an introduction, process explanation, word counts,
comedy ratings, or any extra commentary.

RESEARCH HEADLINES:
{headlines}
"""

    return prompt


def main():
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it in GitHub Actions Secrets."
        )

    stories = get_headlines()

    if len(stories) < 3:
        raise RuntimeError(
            "Not enough headlines were collected. Run the workflow again later."
        )

    prompt = build_prompt(stories)

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 8192,
        },
    }

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(MODEL, safe="-._")
        + ":generateContent?key="
        + urllib.parse.quote(API_KEY)
    )

    result = None

    for attempt in range(4):
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
            break

        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")
            print("Gemini API error:", message)

            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(
                    f"Gemini API request failed with HTTP {error.code}: "
                    f"{message}"
                ) from error

            wait = 15 * (attempt + 1)
            print(f"Temporary API error. Retrying in {wait} seconds...")
            time.sleep(wait)

        except (TimeoutError, OSError) as error:
            print("Network error:", error)

            if attempt == 3:
                raise

            wait = 15 * (attempt + 1)
            print(f"Retrying in {wait} seconds...")
            time.sleep(wait)

    if not result:
        raise RuntimeError("Gemini returned no response.")

    candidates = result.get("candidates", [])

    if not candidates:
        raise RuntimeError(
            "Gemini returned no candidates. Check the model, API quota, "
            "and API response."
        )

    parts = candidates[0].get("content", {}).get("parts", [])
    generated_text = "\n".join(
        part.get("text", "")
        for part in parts
        if part.get("text")
    ).strip()

    if not generated_text:
        raise RuntimeError("Gemini returned empty script text.")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{today}.md"

    output_file.write_text(generated_text + "\n", encoding="utf-8")

    print(f"Saved comedy scripts to {output_file}")
    print(f"Generated output: {len(generated_text)} characters.")


if __name__ == "__main__":
    main()
            
