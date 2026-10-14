
import os
import json
import time
import re
import html
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

QUERIES = [
    "US UK celebrity entertainment when:2d",
    "viral internet culture influencer news when:2d",
    "movies music streaming pop culture when:2d",
    "hip hop social media celebrity drama when:2d",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
)


class ArticleTextParser(HTMLParser):
    """Extract readable article text and useful page metadata."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title_parts = []
        self.description = ""
        self.in_title = False
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "title":
            self.in_title = True

        if tag in ("script", "style", "noscript", "svg"):
            self.skip_depth += 1

        if tag == "meta":
            key = (
                attrs.get("property", "")
                or attrs.get("name", "")
            ).lower()
            if key in ("og:description", "description", "twitter:description"):
                value = attrs.get("content", "").strip()
                if value and len(value) > len(self.description):
                    self.description = value

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

        if tag in ("script", "style", "noscript", "svg"):
            self.skip_depth = max(0, self.skip_depth - 1)

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value:
            return

        if self.in_title:
            self.title_parts.append(value)

        if self.skip_depth == 0 and len(value) > 25:
            self.parts.append(value)


def fetch_url(url, timeout=20):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")

        if "html" not in content_type.lower():
            raise RuntimeError("The page did not return HTML.")

        raw = response.read(2_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
        page = raw.decode(charset, errors="replace")

    return final_url, page


def collect_rss_stories():
    stories = {}

    for query in QUERIES:
        rss_url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )

        try:
            request = urllib.request.Request(
                rss_url, headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                root = ET.fromstring(response.read())

            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                published = item.findtext("pubDate", "").strip()

                if title and link:
                    stories.setdefault(title, {
                        "title": title,
                        "rss_url": link,
                        "published": published,
                    })

        except Exception as error:
            print(f"RSS warning: {error}")

    result = list(stories.values())
    print(f"Collected {len(result)} unique headlines.")
    return result


def verify_article(story):
    """
    Attempt to follow the news link and read the publisher page.
    A successful fetch is not proof that every claim is true.
    """

    try:
        final_url, page = fetch_url(story["rss_url"])
        parser = ArticleTextParser()
        parser.feed(page)

        title = html.unescape(" ".join(parser.title_parts)).strip()
        description = html.unescape(parser.description).strip()
        body = " ".join(parser.parts)
        body = html.unescape(body)

        # Reject pages that provide almost no readable information.
        if len(body) < 250 and len(description) < 100:
            raise RuntimeError(
                "Too little readable article text; possibly blocked or paywalled."
            )

        story["source_url"] = final_url
        story["page_title"] = title
        story["description"] = description
        story["article_text"] = body[:7000]
        story["article_accessible"] = True

        print(f"Article page accessible: {story['title']}")
        return story

    except Exception as error:
        print(f"Could not verify article '{story['title']}': {error}")
        return None


def get_verified_stories():
    headlines = collect_rss_stories()
    verified = []

    # Try recent stories until we have enough accessible publisher pages.
    for story in headlines[:35]:
        result = verify_article(story)
        if result:
            verified.append(result)

        if len(verified) >= 8:
            break

        time.sleep(1)

    print(f"Publisher pages accessible: {len(verified)}")
    return verified


def build_prompt(stories):
    supplied_stories = []

    for story in stories:
        supplied_stories.append({
            "headline": story["title"],
            "publisher_page_title": story["page_title"],
            "publisher_url": story["source_url"],
            "published": story["published"],
            "page_description": story["description"],
            "article_excerpt": story["article_text"][:5000],
        })

    return f"""
You are an excellent stand-up comedy writer creating original,
spoken-word entertainment videos for audiences in the USA, UK,
Canada and Australia. The narrator may occasionally use a natural
Indian perspective when it genuinely improves a joke.

Write exactly THREE original comedy scripts using THREE DIFFERENT
stories from the supplied article data.

COMEDY STYLE
- The first sentence must hook the viewer immediately.
- Sound like a real comedian telling a funny story, not an AI essay.
- Use specific observations, escalation, surprise and callbacks.
- Aim for frequent punchlines without making every line feel forced.
- End each script with its strongest joke or a clever twist.
- Avoid filler, generic motivational language and repeated metaphors.
- Do not force Indian references into every script.
- Aim for about 100-140 spoken words per script.
- Make the joke about the situation, public behavior or absurdity,
  not about humiliating vulnerable people.

FACTUAL RULES
- Use ONLY the stories provided below.
- Read the article excerpts and descriptions before writing.
- Do not invent quotes, events, motives, allegations, relationships,
  legal outcomes, medical details or personal history.
- Do not treat an allegation as proven fact.
- If an article excerpt does not support a detail, do not state it.
- Clearly distinguish reported claims from established facts.
- Exaggeration is allowed only when it is obviously a joke.
- Never invent, rewrite or shorten the supplied publisher URL.
- Do not claim independent fact-checking or certainty.
- If the available article text is ambiguous, keep the script general.
- Do not include any other URLs in the output.

OUTPUT FORMAT
Return exactly THREE scripts in Markdown, numbered 1 to 3.
Use these SIX sections for every script:

1. Headline: copy the supplied headline exactly.
2. Source URL: copy the supplied publisher URL exactly.
3. Spoken Monologue: 100-140 spoken words.
4. Caption: one short, catchy line.
5. Video Description: a concise, natural description.
6. Fact-check Note: state that the script is based on the accessible
   article page and that important claims should be checked before
   publication.

Use this exact section layout:

## Story 1
**Headline:** ...
**Source URL:** ...
**Spoken Monologue:**
...
**Caption:** ...
**Video Description:** ...
**Fact-check Note:** ...

Repeat for Story 2 and Story 3.

ARTICLE DATA:
{json.dumps(supplied_stories, ensure_ascii=False, indent=2)}
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
                    "Gemini returned no candidates. Check model availability and quota."
                )

            parts = candidates[0].get("content", {}).get("parts", [])
            output = "\n".join(
                part.get("text", "")
                for part in parts
                if part.get("text")
            ).strip()

            if not output:
                raise RuntimeError("Gemini returned empty text.")

            return output

        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            print(f"Gemini HTTP {error.code}: {details[:1000]}")

            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(
                    f"Gemini request failed with HTTP {error.code}."
                ) from error

        except (TimeoutError, OSError) as error:
            print(f"Network error: {error}")
            if attempt == 3:
                raise

        wait_seconds = 15 * (attempt + 1)
        print(f"Retrying in {wait_seconds} seconds...")
        time.sleep(wait_seconds)

    raise RuntimeError("Gemini failed after all retry attempts.")


def validate_output(text, stories):
    """Check source links and the six-section format before saving."""

    allowed_urls = {
        story["source_url"].rstrip("/")
        for story in stories
        if story.get("source_url")
    }

    found_urls = re.findall(r'https?://[^\s<>\]\)"]+', text)
    found_urls = [url.rstrip(".,;:!?").rstrip("/") for url in found_urls]

    invalid_urls = sorted({
        url for url in found_urls if url not in allowed_urls
    })

    if invalid_urls:
        print("Output contains unapproved URLs:")
        for url in invalid_urls:
            print(f" - {url}")
        raise RuntimeError(
            "Output rejected: it contains a URL not found in the verified "
            "article list. No new script file was saved."
        )

    unique_urls = set(found_urls)
    if len(unique_urls) != 3:
        raise RuntimeError(
            f"Output must cite exactly three distinct source URLs; found "
            f"{len(unique_urls)}. No new script file was saved."
        )

    required_sections = [
        "Headline:",
        "Source URL:",
        "Spoken Monologue:",
        "Caption:",
        "Video Description:",
        "Fact-check Note:",
    ]

    for section in required_sections:
        if text.count(section) < 3:
            raise RuntimeError(
                f"Output rejected: missing or incomplete section '{section}'. "
                "No new script file was saved."
            )

    if len(re.findall(r"(?m)^## Story [1-3]\s*$", text)) != 3:
        raise RuntimeError(
            "Output rejected: expected exactly three numbered stories. "
            "No new script file was saved."
        )

    print("Output structure and source URL checks passed.")


def main():
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check your GitHub Actions secret."
        )

    stories = get_verified_stories()

    if len(stories) < 3:
        raise RuntimeError(
            "Fewer than three publisher pages could be read. "
            "No scripts were saved. Try running the workflow again later."
        )

    prompt = build_prompt(stories)
    generated = call_gemini(prompt)
    validate_output(generated, stories)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{today}.md"

    output_file.write_text(generated + "\n", encoding="utf-8")

    print(f"Successfully saved scripts: {output_file}")
    print("Reminder: accessible article text is not the same as full fact verification.")


if __name__ == "__main__":
    main()
        
