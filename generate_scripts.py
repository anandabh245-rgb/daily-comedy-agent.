import os
import json
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

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
You are an original comedy writer for a YouTube channel aimed at adults
in the USA, UK, Canada, Australia, and English-speaking Europe.

Create exactly THREE distinct, original, approximately one-minute spoken
comedy monologues. Each must contain 110-145 words.

Use witty conversational English, a strong opening hook, escalating jokes,
and a memorable closing punchline. The performer is an Indian creator
speaking English to a Western audience. Avoid fake accents and stereotypes.

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

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        print("Gemini API error:", error.read().decode("utf-8"))
        raise

    generated_text = result["candidates"][0]["content"]["parts"][0]["text"]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output = Path("output")
    output.mkdir(exist_ok=True)
    filename = output / f"{today}.md"
    filename.write_text(generated_text, encoding="utf-8")

    print(f"Saved scripts to {filename}")


if __name__ == "__main__":
    main()
