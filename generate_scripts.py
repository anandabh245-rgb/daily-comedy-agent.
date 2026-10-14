import os
import json
import time
import re
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

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
                url, headers={"User-Agent": "Mozilla/5.0"}
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
            print(f"RSS warning for '{query}': {error}")

    unique = {}
    for story in stories:
        unique.setdefault(story["title"], story)

    result = list(unique.values())
    print(f"Collected {len(result)} unique headlines.")
    return result


def build_prompt(stories):
    """Create the comedy brief from real collected RSS entries."""
    headlines = json.dumps(
        stories[:25], ensure_ascii=False, indent=2
    )

    return f"""
You are a sharp, naturally funny stand-up comedian and Indian YouTuber
speaking to audiences in the USA, UK, Canada and Australia.

Turn current celebrity, hip-hop, influencer, entertainment and internet
culture headlines into original spoken comedy.

STYLE:
- Make the first sentence funny or surprising immediately.
- Use a conversational, confident, human voice.
- Build one clear comic premise and escalate it.
- Aim for punchlines every one or two spoken lines.
- End with a strong twist or callback.
- Use an Indian perspective only when it naturally improves the joke.
- Avoid generic AI wording, filler, recycled jokes and forced references.
- Write 100-140 spoken words per script.

FACTUAL RULES:
- The JSON below is the only allowed story list.
- Choose three distinct stories from that list.
- Copy each selected story's title and URL exactly from the input.
- Never invent or alter a source URL, headline, quote, scandal,
  accusation, relationship or celebrity action.
- Only headline text and URLs are supplied; article text has not been
  independently checked. Do not pretend you read the full article.
- Do not add unsupported details as facts.
- Keep exaggerations obviously comedic.
- If a headline is not funny, choose another supplied headline.
- Do not make up a story to fill the quota.

OUTPUT:
Return exactly three scripts in Markdown. For each include:
1. Headline copied from the supplied story
2. Source URL copied exactly from that story
3. Spoken monologue
4. Short caption
5. Concise video description
6. Fact-check note saying the script is based on the supplied headline
   and the linked article should be checked before publication.

Do not include any URLs except exact URLs from the supplied JSON.
Do not claim the stories have been independently verified.

SUPPLIED RSS STORIES:
{headlines}
"""


def call_gemini(prompt):
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 8192,
        },
    }

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(MODEL, safe="-._")
        + ":generateContent?key="
        + urllib.parse.quote(API_KEY)
    )

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

            candidates = result.get("candidates", [])
            if not candidates:
                raise RuntimeError(
                    "Gemini returned no candidates. Check the model and quota."
                )

            parts = candidates[0].get("content", {}).get("parts", [])
            text = "\n".join(
                part.get("text", "")
                for part in parts if part.get("text")
            ).strip()

            if not text:
                raise RuntimeError("Gemini returned empty text.")

            return text

        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")
            print(f"Gemini HTTP {error.code}: {message}")

            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(
                    f"Gemini request failed with HTTP {error.code}."
                ) from error

        except (TimeoutError, OSError) as error:
            print(f"Network error: {error}")
            if attempt == 3:
                raise

        wait = 15 * (attempt + 1)
        print(f"Retrying in {wait} seconds...")
        time.sleep(wait)

    raise RuntimeError("Gemini request failed after retries.")


def validate_source_urls(generated_text, stories):
    """Reject output containing URLs not present in the collected RSS data."""
    allowed_urls = {
        story["link"].strip()
        for story in stories
        if story.get("link")
    }

    found_urls = re.findall(
        r'https?://[^\s<>\]\)"]+', generated_text
    )
    found_urls = [url.rstrip(".,;:!?") for url in found_urls]

    invalid_urls = sorted({
        url for url in found_urls if url not in allowed_urls
    })

    if invalid_urls:
        print("Rejected invented or changed URLs:")
        for url in invalid_urls:
            print(f"  {url}")
        raise RuntimeError(
            "Output rejected. Gemini included URLs that were not in the "
            "RSS input. No script file was saved."
        )

    if len(set(found_urls)) < 3:
        raise RuntimeError(
            "Output rejected: three distinct supplied source URLs were "
            "not included. No script file was saved."
        )

    print("Source URL validation passed.")


def main():
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check GitHub Actions Secrets."
        )

    stories = get_headlines()

    if len(stories) < 3:
        raise RuntimeError(
            "Fewer than three headlines collected. Try the workflow again later."
        )

    prompt = build_prompt(stories)
    generated_text = call_gemini(prompt)

    # Validate before writing anything to the output folder.
    validate_source_urls(generated_text, stories)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{today}.md"

    output_file.write_text(generated_text + "\n", encoding="utf-8")

    print(f"Saved scripts to {output_file}")
    print(f"Output length: {len(generated_text)} characters.")


if __name__ == "__main__":
    main()
    
