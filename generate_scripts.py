
import os
import json
import time
import re
import html
import random
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
)

GOOGLE_QUERIES = [
    "celebrity entertainment news when:2d",
    "viral internet culture influencer news when:2d",
    "movies music streaming pop culture when:2d",
    "hip hop social media celebrity drama when:2d",
]

# Used only if Google News is unavailable.
FALLBACK_FEEDS = [
    "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "https://variety.com/feed/",
    "https://www.theguardian.com/culture/rss",
    "https://www.hollywoodreporter.com/feed/",
]


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


def download_url(url, timeout=25, attempts=3):
    """Retry temporary HTTP errors and network failures."""
    last_error = None

    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/xml, text/xml, text/html, */*",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(2_000_000), response.geturl(), (
                    response.headers.get("Content-Type", "")
                )

        except urllib.error.HTTPError as error:
            last_error = error

            # Retry only temporary or rate-limit errors.
            if error.code not in (408, 425, 429, 500, 502, 503, 504):
                break

            print(
                f"Temporary HTTP {error.code}; "
                f"attempt {attempt + 1}/{attempts}"
            )

        except (TimeoutError, OSError) as error:
            last_error = error
            print(f"Network issue; attempt {attempt + 1}/{attempts}: {error}")

        if attempt < attempts - 1:
            time.sleep((2 ** attempt) * 3 + random.uniform(0, 2))

    raise RuntimeError(f"Could not fetch feed: {last_error}")


def parse_feed(xml_bytes, feed_name):
    """Read standard RSS or Atom feed entries."""
    root = ET.fromstring(xml_bytes)
    stories = []

    # RSS format
    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        published = (
            item.findtext("pubDate", "")
            or item.findtext("{http://purl.org/dc/elements/1.1/}date", "")
        ).strip()

        description = item.findtext("description", "").strip()

        if title and link:
            stories.append({
                "title": html.unescape(title),
                "rss_url": link,
                "published": published,
                "feed": feed_name,
                "feed_description": html.unescape(
                    re.sub(r"<[^>]+>", " ", description)
                )[:1500],
            })

    # Atom format, in case a feed uses it
    if not stories:
        ns = {"a": "http://www.w3.org/2005/Atom"}

        for entry in root.findall(".//a:entry", ns):
            title_node = entry.find("a:title", ns)
            link_node = entry.find("a:link", ns)
            date_node = entry.find("a:updated", ns)

            title = (
                "".join(title_node.itertext()).strip()
                if title_node is not None else ""
            )
            link = (
                link_node.attrib.get("href", "").strip()
                if link_node is not None else ""
            )
            published = (
                date_node.text.strip()
                if date_node is not None and date_node.text else ""
            )

            if title and link:
                stories.append({
                    "title": html.unescape(title),
                    "rss_url": link,
                    "published": published,
                    "feed": feed_name,
                    "feed_description": "",
                })

    return stories


def collect_google_news():
    collected = []

    for query in GOOGLE_QUERIES:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en"
        )

        try:
            data, _, _ = download_url(url, attempts=3)
            collected.extend(parse_feed(data, "Google News"))
            print(f"Google News query succeeded: {query}")

        except Exception as error:
            print(f"Google News query failed: {query} — {error}")

        # Avoid sending a burst of requests.
        time.sleep(2)

    return collected


def collect_fallback_feeds():
    collected = []

    for url in FALLBACK_FEEDS:
        try:
            data, _, _ = download_url(url, attempts=2)
            entries = parse_feed(data, url)
            collected.extend(entries)
            print(f"Fallback feed returned {len(entries)} stories: {url}")

        except Exception as error:
            print(f"Fallback feed unavailable: {url} — {error}")

        time.sleep(1)

    return collected


def collect_stories():
    stories = {}

    # Try Google News first.
    for story in collect_google_news():
        stories.setdefault(story["title"], story)

    if len(stories) < 3:
        print("Google News returned too few stories. Trying fallback feeds.")

        for story in collect_fallback_feeds():
            stories.setdefault(story["title"], story)

    result = list(stories.values())
    print(f"Collected {len(result)} unique headlines across feeds.")
    return result


def fetch_article_metadata(url):
    """Try to read article text; keep the RSS item if access is blocked."""
    try:
        raw, final_url, content_type = download_url(
            url, timeout=15, attempts=1
        )

        if "html" not in content_type.lower():
            return final_url, "", "", ""

        charset = "utf-8"
        page = raw.decode(charset, errors="replace")

        parser = ArticleParser()
        parser.feed(page)

        title = html.unescape(" ".join(parser.title_parts)).strip()
        description = html.unescape(parser.description).strip()
        body = html.unescape(" ".join(parser.text_parts))[:5000]

        return final_url, title, description, body

    except Exception as error:
        print(f"Article unavailable; retaining headline: {error}")
        return url, "", "", ""


def prepare_stories():
    headlines = collect_stories()
    prepared = []

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
            "feed": story["feed"],
            "feed_description": story.get("feed_description", ""),
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
- Build one clear premise, escalate it, and finish with a memorable
  twist or callback.
- Aim for frequent punchlines without forcing every line.
- Avoid generic AI language, filler and repetitive metaphors.
- Use an Indian perspective only when it naturally improves the joke.
- Aim for 100-140 spoken words per monologue.
- Focus jokes on absurd situations, not humiliating vulnerable people.

FACTUAL RULES
- Use only the supplied story records.
- If article_text_accessible is true, use details supported by the
  supplied article text, page title or description.
- If article_text_accessible is false, only the headline and any RSS
  description are available. Do not invent extra events, quotes,
  motives, accusations or context.
- Do not turn allegations into proven facts.
- Do not claim independent fact-checking.
- Never invent or change a source URL.
- Use the exact source_url supplied for each story.
- Include no other URLs.
- If a story cannot support a safe joke, choose another supplied story.

OUTPUT FORMAT
Return exactly THREE scripts in Markdown.

For EACH story, include these six sections:

## Story 1
**Headline:** exact supplied headline
**Source URL:** exact supplied source_url
**Spoken Monologue:** 100-140 words
**Caption:** one short, catchy line
**Video Description:** concise natural description
**Fact-check Note:** State whether the article text was accessible.
If only a headline was available, say the linked article must be
checked before publication.

Repeat using ## Story 2 and ## Story 3.

SUPPLIED STORIES:
{json.dumps(supplied, ensure_ascii=False, indent=2)}
"""


def call_gemini(prompt):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
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
                for part in parts if part.get("text")
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
            print(f"Gemini network error: {error}")
            if attempt == 3:
                raise

        wait_seconds = 15 * (attempt + 1)
        print(f"Retrying Gemini in {wait_seconds} seconds...")
        time.sleep(wait_seconds)

    raise RuntimeError("Gemini failed after all retry attempts.")


def validate_output(text, stories):
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
            "Output rejected: unapproved URLs found: "
            + ", ".join(invalid_urls)
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
            "All news feeds returned fewer than three headlines. "
            "No scripts were generated. Run the workflow again later."
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
