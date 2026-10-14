import os
import json
import time
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

MAX_STORIES = 20
MAX_RETRIES = 4


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
                headers={"User-Agent": "Mozilla/5.0"}
            )

            with urllib.request.urlopen(request, timeout=20) as response:
                root = ET.fromstring(response.read())

            for item in root.findall(".//item")[:8]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                source = item.findtext("source", "").strip()

                if title and link:
                    stories.append({
                        "title": title,
                        "link": link,
                        "source": source
                    })

        except Exception as error:
            print(f"RSS feed warning for '{query}': {error}")

    unique = {}
    for story in stories:
        unique.setdefault(story["title"], story)

    return list(unique.values())


def build_prompt(stories):
    """Build the writing brief for the channel's comedy persona."""
   • Every monologue must have a central comic premise, not just a collection of topical jokes.
   • At least two punchlines must come from the narrator's own behaviour, insecurity, or embarrassing reaction.
   • Include one unexpected reversal that reinterprets an earlier detail.
   • Avoid defaulting to predictable Indian-parent, auntie, WhatsApp, and teacher jokes unless the specific situation makes them original.
   • Don't invent biographical details about the performer.
   • Prefer one excellent story with a strong ending over six loosely connected jokes.
   • Treat the final punchline as the most important line in the script.

    headlines = json.dumps(
        stories,
        ensure_ascii=False,
        indent=2
    )

    return f"""
You are the HEAD WRITER for a distinctive, laugh-out-loud
YouTube comedy channel.

Your job is to write material for an INDIAN MALE YOUTUBER
who appears on camera and performs stand-up-style commentary.

He is not a news presenter, journalist, or faceless narrator.

He is an expressive Indian guy in a cap, T-shirt or hoodie,
looking directly into the camera and telling a hilarious story
to an English-speaking audience in the USA, UK, Canada,
Australia and other English-speaking countries.

THE CORE IDENTITY:
An Indian guy observes Western celebrity culture, influencer
drama, online behaviour and modern life, then reacts with the
honesty, imagination and comic timing of a brilliant storyteller.

His point of view should feel personal and original.
He can be confused, overconfident, petty, dramatic, insecure,
judgmental, self-aware or completely wrong about something.
His own reactions and flaws are often funnier than the news.

The viewer should feel:
"This guy is absolutely ridiculous. I want to hear what
he says about the next thing."

Do not write generic news commentary with jokes added.
Write an actual COMEDY PERFORMANCE.

COMEDY CRAFT:
Use the principles of excellent stand-up storytelling:
- A strong opening that immediately creates curiosity.
- A clear premise the audience understands.
- Specific details that make the situation visual.
- Unexpected comparisons that reveal something funny.
- Escalation: every new beat makes the problem worse.
- Misleading assumptions and reversals.
- Short punchlines mixed with conversational storytelling.
- Pauses and deadpan reactions where appropriate.
- Callbacks that make earlier details funnier.
- A strong closing punchline that changes the audience's
  understanding of the story.

Be original. Do not imitate a particular comedian's
voice, catchphrases, delivery, or recognizable material.

INDIAN PERSPECTIVE:
The performer is Indian, but the audience is international.

Use Indian cultural observations when they genuinely improve
the joke: family WhatsApp groups, relatives who know everything,
Indian parents, middle-class ambition, bargaining, wedding
politics, UPI payments, customer service, or the experience
of explaining an internet trend to family.

Use these selectively. Do not turn every script into a list
of Indian references or make Indian identity the punchline.

A strong joke might come from comparing the absurdity of
American influencer culture with the practical logic of an
Indian household, or from the narrator's own inability to
understand something everyone else appears to understand.

The reference must make the joke FUNNIER, not merely different.

LANGUAGE AND DELIVERY:
Write natural, conversational English.
Use American English as the default where appropriate.
The performer may use occasional Indian English expressions
naturally, but never force slang into every sentence.

The monologue must sound good when spoken aloud to a phone
camera. Use contractions, varied sentence lengths, dramatic
pauses, confidence, disbelief, self-roasting and occasional
deadpan delivery.

The performer should sound like a real person telling a
friend an unbelievable story, not reading an essay.

JOKE QUALITY:
Prioritize human behaviour and funny situations over
clever-sounding but empty phrases.

Avoid:
- "The internet is crazy."
- "What is happening to the world?"
- "Let that sink in."
- Generic bro jokes.
- Forced metaphors and random absurdity without a setup.
- Repetitive three-item lists.
- Slang used as a substitute for a punchline.
- Predictable endings about being broke, deleting an app,
  needing therapy, or being "cooked".
- Fake dialogue presented as a real quotation.
- A joke in every single sentence.
- Long introductions and unnecessary explanations.

Allow some sentences to breathe. Make the big jokes land.

STORYTELLING STRUCTURE:
Each script should have:
1. An immediate, funny opening.
2. One clear central premise.
3. A believable but questionable reaction by the narrator.
4. Two or three connected escalations.
5. A vivid detail or short piece of imagined dialogue.
6. A surprising final reversal or punchline.

Do not mechanically follow this structure if a different
sequence makes a particular story funnier.

NEWS AND FACTUAL ACCURACY:
Use the supplied headlines as research leads, not verified facts.

Do not invent celebrity statements, allegations, relationships,
statistics, feuds or events and present them as true.

The narrator may imagine what he would do in a situation.
Clearly hypothetical comedy scenarios are allowed.

If a headline cannot support a reliable factual premise,
write a funny evergreen story about online behaviour instead.
Mark the source as "No factual source needed" for that script.

Never use a tragedy or a vulnerable person's suffering as
the target of a joke.

THE THREE SCRIPTS MUST BE DIFFERENT:
Create EXACTLY THREE complete monologues.

Use different premises, emotional attitudes, story structures,
and punchline styles.

At least one script should, where suitable source material
allows, use current celebrity or influencer news.

The remaining scripts may cover internet culture, relationships,
online embarrassment, AI, dating apps, group chats, social
media behaviour, everyday awkwardness or other relatable
modern experiences.

Do not make all three scripts celebrity roasts.
Do not make all three scripts about India.
Do not reuse the same joke structure or final twist.

LENGTH:
Each spoken monologue must contain 110-145 words.
The title, captions, description and fact-check note do not
count toward the spoken word limit.

ON-CAMERA PERFORMANCE:
For each script, add brief acting notes indicating where
the performer should use:
- A facial expression or change in expression.
- A dramatic pause or deadpan look.
- A change in pace or emphasis.
- A physical reaction when useful.

These are practical performance directions, not extra
spoken words.

ON-SCREEN CAPTIONS:
Provide exactly three short caption highlights per script.
Use memorable phrases from the monologue or concise versions
of its best jokes. Make them readable on a phone screen.

YOUTUBE PACKAGING:
Provide a clickable title under 70 characters, a one-sentence
description, relevant hashtags and a brief fact-check reminder.

Avoid misleading titles or claims that the video does not
actually support.

FINAL SILENT QUALITY CHECK:
Before returning the scripts, check each one for:
- Immediate hook.
- Originality.
- Indian point of view where it naturally helps.
- Natural spoken delivery.
- Specific, escalating jokes.
- A genuinely strong final punchline.
- Correct word count.
- Accurate treatment of factual claims.

Rewrite weak material before returning it.
Do not reveal ratings or internal evaluations.

OUTPUT FORMAT:
Return readable Markdown only.

For each of exactly THREE scripts, use this structure:

## SCRIPT 1: [Catchy topic]

**Source URL:** [URL or "No factual source needed"]

**YouTube Title:** [Under 70 characters]

**Spoken Monologue:**
[110-145 spoken words]

**Performance Notes:**
- [Expression, pause or delivery direction]
- [Expression, pause or delivery direction]
- [Expression, pause or delivery direction]

**On-Screen Caption Highlights:**
- [Caption 1]
- [Caption 2]
- [Caption 3]

**Description and Hashtags:**
[One sentence and relevant hashtags]

**Fact-Check Reminder:**
[Claims to verify, or state that the premise is fictional
or evergreen and has no factual claim requiring verification.]

Repeat for scripts 2 and 3.

NEWS RESEARCH LEADS:
{headlines}

Remember: the news is only the setup.
The performer and the comedy are the main attraction.

Write something a person would actually enjoy watching,
laugh at, quote to a friend, and share.
"""


def call_gemini(prompt):
    """Call Gemini with retries for temporary API failures."""

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + MODEL
        + ":generateContent?key="
        + urllib.parse.quote(API_KEY)
    )

    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.95,
            "responseMimeType": "text/plain"
        }
    }

    request_data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=request_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(
                request, timeout=180
            ) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            candidates = result.get("candidates", [])
            if not candidates:
                raise RuntimeError(
                    "Gemini returned no candidates: "
                    + json.dumps(result)[:1200]
                )

            parts = candidates[0].get(
                "content", {}
            ).get("parts", [])

            generated_text = "\n".join(
                part["text"]
                for part in parts
                if "text" in part
            ).strip()

            if not generated_text:
                raise RuntimeError("Gemini returned empty text.")

            return generated_text

        except urllib.error.HTTPError as error:
            details = error.read().decode(
                "utf-8", errors="replace"
            )
            print(f"Gemini HTTP error {error.code}: {details[:1200]}")

            retryable = error.code in (
                408, 429, 500, 502, 503, 504
            )

            if not retryable or attempt == MAX_RETRIES - 1:
                raise

        except (TimeoutError, urllib.error.URLError, OSError) as error:
            print(f"Gemini connection error: {error}")

            if attempt == MAX_RETRIES - 1:
                raise

        wait = 10 * (attempt + 1)
        print(f"Retrying in {wait} seconds...")
        time.sleep(wait)

    raise RuntimeError("Gemini failed after all retry attempts.")


def main():
    print("Starting Daily Comedy Agent...")
    print("Comedy persona: Indian on-camera stand-up commentator")

    stories = get_headlines()

    if len(stories) < 5:
        raise RuntimeError(
            f"Only {len(stories)} headlines collected. "
            "Try running the workflow again later."
        )

    selected_stories = stories[:MAX_STORIES]

    print(f"Collected {len(stories)} unique headlines.")

    prompt = build_prompt(selected_stories)
    generated_text = call_gemini(prompt)

    if not generated_text.strip():
        raise RuntimeError("Generated scripts are empty.")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    output = Path("output")
    output.mkdir(parents=True, exist_ok=True)

    filename = output / f"{today}.md"

    filename.write_text(
        generated_text.rstrip() + "\n",
        encoding="utf-8"
    )

    print(f"Saved comedy scripts to {filename}")


if __name__ == "__main__":
    main()
