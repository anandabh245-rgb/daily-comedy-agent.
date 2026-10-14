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


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.text_parts = []
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

            if key in (
                "og:description",
                "description",
                "twitter:description",
            ):
                value = attrs.get("content", "").strip()
                if len(value) > len(self.description):
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
            self.text_parts.append(value)


def fetch_article_metadata(url):
    """Try to read an article, but never discard a headline if blocked."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")

            if "html" not in content_type.lower():
                return final_url, "", "", ""

            raw = response.read(1_000_000)
            charset = response.headers.get_content_charset() or "utf-8"
            page = raw.decode(charset, errors="replace")

        parser = ArticleParser()
        parser.feed(page)

        title = html.unescape(" ".join(parser.title_parts)).strip()
        description = html.unescape(parser.description).strip()
        body = html.unescape(" ".join(parser.text_parts))[:5000]

        return final_url, title, description, body

    except Exception as error:
        print(f"Article unavailable; keeping headline: {error}")
        return url, "", "", ""


def collect_stories():
    stories = {}

    for query in QUERIES:
        rss_url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )

        try:
            request = urllib.request.Request(
                rss_url,
                headers={"User-Agent": USER_AGENT},
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
            print(f"RSS warning for '{query}': {error}")

    result = list(stories.values())
    print(f"Collected {len(result)} unique headlines.")
    return result


def prepare_stories():
    headlines = collect_stories()
    prepared = []

    # Article reading is optional. A blocked website no longer
    # prevents the whole workflow from producing scripts.
    for story in headlines[:30]:
        final_url, page_title, description, article_text = (
            fetch_article_metadata(story["rss_url"])
        )

        story["source_url"] = final_url or story["rss_url"]
        story["page_title"] = page_title
        story["description"] = description
        story["article_text"] = article_text
        story["article_accessible"] = (
            len(article_text) >= 250 or len(description) >= 80
        )

        if story["article_accessible"]:
            print(f"Article text available: {story['title']}")
        else:
            print(f"Headline only; manual review needed: {story['title']}")

        prepared.append(story)

        if len(prepared) >= 15:
            break

        time.sleep(0.25)

    print(f"Stories available for drafting: {len(prepared)}")
    return prepared


def build_prompt(stories):
    supplied = []

    for story in stories:
        supplied.append({
            "headline": story["title"],
            "source_url": story["source_url"],
            "published": story["published"],
            "article_page_title": story["page_title"],
            "page_description": story["description"],
            "article_excerpt_if_accessible": story["article_text"][:3500],
            "article_text_accessible": story["article_accessible"],
        })

    return f"""
You are a sharp stand-up comedy writer creating original spoken
comedy for audiences in the USA, UK, Canada and Australia.

Write exactly THREE scripts using THREE DIFFERENT supplied stories.

COMEDY STYLE
- Hook the viewer in the first sentence.
- Sound conversational, specific and naturally funny.
- Build one clear premise and escalate it.
- Use frequent punchlines without forcing every line.
- End each monologue with a memorable twist or callback.
- Avoid generic AI language, filler and repetitive metaphors.
- Use an Indian perspective only when it naturally improves the joke.
- Aim for 100-140 spoken words per monologue.
- Focus jokes on absurd situations, not humiliating vulnerable people.

FACTUAL RULES
- Use only the supplied story records.
- If article_text_accessible is true, use details supported by the
  supplied article text, page title or description.
- If article_text_accessible is false, only the headline is available.
  Keep the script strictly to what the headline says.
- Do not invent quotes, events, motives, allegations or extra context.
- Never turn an allegation into a proven fact.
- Do not claim independent fact-checking.
- Never invent or change a source URL.
- Use the exact source_url supplied for each story.
- Include no other URLs.
- If a story cannot support a safe joke, choose another story.

OUTPUT FORMAT
Return exactly THREE scripts in Markdown.

For EACH story, include all six sections:

## Story 1
**Headline:** exact supplied headline
**Source URL:** exact supplied source_url
**Spoken Monologue:** 100-140 words
**Caption:** one short, catchy line
**Video Description:** concise natural description
**Fact-check Note:** If article text was accessible, say that the
page was accessible but claims still need review. If not, explicitly
say only the headline was available and the linked article must be
checked before publication.

Repeat using ## Story 2 and ## Story 3.

SUPPLIED STORIES:
{json.dumps(supplied, ensure_ascii=False, indent=2)}
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
    """Reject invented URLs and incomplete script formatting."""

    allowed_urls = set()

    for story in stories:
        for key in ("source_url", "rss_url"):
            url = story.get(key, "").strip()

            if url:
                allowed_urls.add(url.rstrip("/"))

    found_urls = re.findall(r'https?://[^\s<>\]\)"]+', text)
    found_urls = [
        url.rstrip(".,;:!?").rstrip("/")
        for url in found_urls
    ]

    invalid_urls = sorted({
        url for url in found_urls
        if url.rstrip("/") not in allowed_urls
    })

    if invalid_urls:
        raise RuntimeError(
            "Output rejected because it contains URLs not present "
            "in the collected RSS data: " + ", ".join(invalid_urls)
        )

    if len(set(found_urls)) != 3:
        raise RuntimeError(
            "Output must contain exactly three distinct source URLs; "
            f"found {len(set(found_urls))}."
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
                f"Output rejected: missing section '{section}'."
            )

    headings = re.findall(r"(?m)^## Story [1-3]\s*$", text)

    if len(headings) != 3:
        raise RuntimeError(
            "Output rejected: expected exactly three story headings."
        )

    print("Output structure and source URL checks passed.")


def main():
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check your GitHub Actions secret."
        )

    stories = prepare_stories()

    if len(stories) < 3:
        raise RuntimeError(
            "Fewer than three headlines were collected. "
            "Try running the workflow again."
        )

    generated = call_gemini(build_prompt(stories))
    validate_output(generated, stories)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{today}.md"
    output_file.write_text(generated + "\n", encoding="utf-8")

    print(f"Successfully saved scripts: {output_file}")
    print(
        "Reminder: URL checks do not prove every claim is true. "
        "Review fact-check notes before publishing."
    )


if __name__ == "__main__":
    main()
            
