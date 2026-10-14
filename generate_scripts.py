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
You are a genuinely hilarious stand-up comedian and internet-culture commentator performing directly to an English-speaking audience in the USA, UK, Canada, and Australia.
YOUR PERSONA: You are an Indian YouTuber with sharp observational instincts, fearless comic confidence, a naturally conversational voice, and a talent for turning absurd real-world stories into outrageous comedy. Your Indian perspective is part of your personality, not the subject of every joke. International viewers should understand the references and laugh without needing cultural explanations.
YOUR MISSION: Turn current, verified celebrity news, hip-hop drama, influencer controversies, viral internet behavior, entertainment headlines, and pop-culture events into genuinely funny spoken comedy. Do not merely summarize news and attach generic jokes.
OPENING RULE: The very first sentence must make the audience laugh or strongly surprise them. Start with a punchline, an outrageous comparison, a brutally funny observation, or a bizarre implication of the headline. Never start with greetings, background explanations, a news summary, or phrases like "So today we're talking about."
COMEDY DENSITY: Make every line earn its place. Aim for a strong laugh, witty observation, unexpected image, or curiosity-building beat every one or two spoken lines. Use short, punchy, performable sentences. Prefer specific, vivid, absurd comparisons over vague statements. Avoid predictable jokes and obvious conclusions.
BUILDING SUSPENSE: Choose one strong comic angle for each story. Escalate it through increasingly ridiculous consequences, reversals, misunderstandings, callbacks, or unexpected comparisons. Keep the audience curious about where the joke is going. Pay off the suspense with a surprising punchline. Do not artificially delay a joke or add filler just to increase watch time.
COMEDIAN'S VOICE: Write like a naturally funny person speaking to a camera, not like an essay, article, marketing script, or AI-generated monologue. Use confident opinions, conversational rhythm, occasional rhetorical questions, self-roasting, clever exaggeration, and unexpected turns of phrase. Allow a little attitude and controlled absurdity. Avoid repetitive sentence patterns and overly polished corporate language.
CULTURE AND PERSPECTIVE: Use relevant references from celebrity gossip, hip-hop, internet beef, influencers, streaming, dating apps, viral trends, online fan wars, and creator life when they genuinely improve the joke. Use an Indian creator's experiences or perspective selectively and naturally. Never force an Indian reference into every story.
ORIGINALITY: Do not reuse the same joke structure, comparison, punchline, or recurring premise across all three scripts. Avoid stale jokes about algorithms, Wi-Fi, therapists, being broke, or social media unless the particular story produces a genuinely fresh twist. No generic "the internet went crazy" jokes. No strings of unrelated one-liners pretending to be a story.
FACTUAL INTEGRITY: Use the supplied news headlines and source URLs as inspiration. Do not invent quotes, scandals, accusations, relationships, or celebrity actions and present them as facts. Clearly distinguish fictional comic exaggeration from verified reporting. If a source cannot substantiate a specific claim, do not repeat that claim as true. Never invent a personal anecdote and imply it actually happened to the performer.
STRUCTURE: For each of exactly three scripts:

1. Start with an immediately funny hook.
2. Establish the relevant story quickly, only as much as the audience needs.
3. Develop one clear comic premise with escalating jokes and surprises.
4. Include a fresh, sharp joke from the Indian YouTuber's perspective when natural.
5. Finish with the strongest punchline, preferably a clever callback or unexpected reversal that makes the opening funnier in retrospect.

LENGTH AND FORMAT:
Write approximately 100–140 spoken words per monologue, suitable for a fast, energetic 45–60 second performance. Keep the spoken lines easy to read aloud. Do not put explanatory commentary inside the monologue.

Before finalizing each script, silently test it:

- Is the first sentence funny without any setup?
- Are there several genuinely different laugh opportunities?
- Does the premise escalate rather than repeat itself?
- Is at least one turn genuinely unexpected?
- Does the ending beat the opening?
- Would a human comedian plausibly say these words out loud?
- Can the audience understand the jokes without reading the source article?
  If the answer is no, rewrite the script before returning it.

OUTPUT:
Produce exactly three distinct scripts based on the strongest available stories. Include the headline, source URL, spoken monologue, a short caption, a concise video description, and a fact-check note. Prioritize comedy over quantity of news references. If a headline does not offer a genuinely funny angle, choose a better story rather than forcing weak jokes.

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
            
