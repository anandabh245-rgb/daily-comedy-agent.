import os
import json
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

QUERIES = [
    "US UK celebrity entertainment when:2d",
    "viral internet culture influencer news when:2d",
    "movies streaming music pop culture news when:2d",
]


def get_headlines():
    stories = []

    for query in QUERIES:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )

        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                root = ET.fromstring(response.read())

            for item in root.findall(".//item")[:8]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                if title and link:
                    stories.append({"title": title, "link": link})

        except Exception as error:
            print("RSS feed warning:", error)

    unique = {story["title"]: story for story in stories}
    return list(unique.values())


def main():
    stories = get_headlines()

    if len(stories) < 5:
        raise RuntimeError(
            "Not enough headlines. Try running the workflow again later."
        )

    headlines = json.dumps(stories[:20], ensure_ascii=False, indent=2)

    prompt = f"""
You are a fearless, genuinely funny internet-culture comedy writer creating original spoken monologues for a YouTube audience in the USA, UK, Canada, Australia, and English-speaking Europe.

IMPORTANT: The comedy must feel funny, not merely well-written. Avoid generic observations, predictable punchlines, polite sitcom humour, and jokes that sound like they were written by a corporate marketing team.

AUDIENCE AND STYLE:

- Write like a naturally funny, chronically online person talking to friends.
- Use conversational American English as the default, with occasional internet slang and meme-style phrasing where it fits.
- Aim for chaotic, self-aware, slightly unhinged, relatable internet comedy.
- Draw inspiration from current online behaviours: group-chat disasters, dating apps, situationships, doomscrolling, AI dependence, influencer drama, fake productivity, parasocial relationships, online arguments, and embarrassing everyday moments.
- Use contemporary slang when appropriate, such as "cooked," "crash out," "aura," "glazing," "brain rot," or newer expressions supported by the research. Never force slang into every sentence or use a term incorrectly.
- Make fun of absurd situations, online behaviour, and the narrator's own flaws. Avoid lazy stereotypes and punching down.

JOKE-WRITING RULES:

- Open with a surprising, funny, bold statement within the first sentence.
- Include several distinct jokes, not one observation stretched into a paragraph.
- Use exaggeration, unexpected comparisons, misdirection, callbacks, awkward confessions, and ridiculous escalation.
- Every few sentences, introduce a new funny idea or twist.
- Prefer specific, vivid, slightly outrageous details over generic statements.
- Include at least one highly quotable line that could work as an on-screen caption.
- End with a strong punchline, not a summary or moral lesson.
- Read the monologue aloud mentally. If a line sounds unnatural or has no comic payoff, rewrite it.
- Do not copy existing comedians, viral scripts, memes, catchphrases, or copyrighted dialogue.
- Escalation: Every monologue must get progressively more ridiculous, with the final joke being stronger than the opening joke.
- Anti-generic rule: Reject any sentence that could appear in thousands of generic AI comedy scripts. Replace it with a specific, unexpected observation.
- Punchline test: Don't finish with a summary such as “I'm just dramatic” or “we're all cooked.” End with a reversal, an embarrassing confession, or an unexpected consequence.

CURRENT INTERNET CULTURE:
Use the supplied news headlines as research leads. Where possible, identify relevant recent online conversations and cultural references. Do not pretend to know a trend is currently viral without evidence. If a topic is uncertain or the headlines are weak, use a universally relatable internet-life scenario instead. Do not invent news, quotes, allegations, or source details.

CREATE EXACTLY THREE DISTINCT MONOLOGUES:

- Each must contain 110–145 spoken words.
- Give each a different premise, comedic angle, and punchline style.
- Avoid making all three scripts about celebrities or movies.
- Prioritize laugh-out-loud writing over mentioning lots of trending topics.
- The performer is an Indian creator speaking English to a Western audience. Do not make every joke about India; use that background only when it genuinely improves a joke.

RESEARCH LEADS:
{headlines}

OUTPUT FORMAT FOR EACH SCRIPT:

1. Number and catchy title.
2. Source URL for any timely factual premise; write "No factual source needed" for evergreen comedy.
3. Full spoken monologue.
4. Three short, funny on-screen caption highlights.
5. One-sentence video description and relevant hashtags.
6. Brief fact-check reminder for any claims that need verification.

FINAL QUALITY CHECK:
Before returning the scripts, silently rate each one for originality, laugh potential, natural spoken delivery, and strength of its final punchline. Rewrite weak scripts before presenting them. Do not include the ratings or your internal evaluation.

Return readable Markdown only.
Use these research leads:
{headlines}

Treat headlines as leads, not verified facts. Do not invent quotes, events,
relationships, or allegations. If uncertain, choose a broader opinion or
evergreen internet-culture topic. Avoid jokes about tragedies and vulnerable
people. Do not copy existing jokes, scripts, lyrics, or catchphrases.

For each script provide:
1. Number and topic
2. Source URL for any timely factual premise
3. Title under 70 characters
4. Full spoken monologue
5. Three short on-screen caption highlights
6. One-sentence description and relevant hashtags
7. A brief fact-check reminder

Clearly mark anything that needs verification. Return readable Markdown only.
"""

    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
    }
        

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + MODEL
        + ":generateContent?key="
        + urllib.parse.quote(API_KEY)
    )

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    
    import time

    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
            break
        except (urllib.error.HTTPError, TimeoutError, OSError) as error:
            message = error.read().decode("utf-8")
            print("Gemini API error:", message)

            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise

            wait = 15 * (attempt + 1)
            print(f"Temporary API error. Retrying in {wait} seconds...")
            time.sleep(wait)
            

    generated_text = result["candidates"][0]["content"]["parts"][0]["text"]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output = Path("output")
    output.mkdir(exist_ok=True)
    filename = output / f"{today}.md"
    filename.write_text(generated_text, encoding="utf-8")

    print(f"Saved scripts to {filename}")


if __name__ == "__main__":
    main()
