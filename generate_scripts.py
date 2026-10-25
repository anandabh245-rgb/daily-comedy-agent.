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
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
OUTPUT_DIR = Path("output")

MAX_STORIES = 3
MIN_WORDS = 85
MAX_WORDS = 155
TARGET_MIN_WORDS = 105
TARGET_MAX_WORDS = 140

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
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=25) as response:
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
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check repository secrets."
        )

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(MODEL, safe="")
        + ":generateContent?"
        + urllib.parse.urlencode({"key": API_KEY})
    )

    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    body = json.dumps(payload).encode("utf-8")

    for attempt in range(3):
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))

            candidates = result.get("candidates", [])

            if not candidates:
                raise RuntimeError(
                    "Gemini returned no usable candidate. "
                    "Check model access and quota."
                )

            parts = candidates[0].get("content", {}).get("parts", [])

            response_text = next(
                (
                    part.get("text", "").strip()
                    for part in parts
                    if part.get("text")
                ),
                "",
            )

            response_text = re.sub(
                r"^```(?:json)?\s*", "", response_text
            )
            response_text = re.sub(
                r"\s*```$", "", response_text
            )

            parsed = json.loads(response_text)

            if not isinstance(parsed, dict):
                raise RuntimeError(
                    "Gemini response was not a JSON object."
                )

            return parsed

        except Exception as exc:
            print(f"Gemini attempt {attempt + 1}: {exc}")

            if attempt < 2:
                time.sleep(3 * (attempt + 1))

    raise RuntimeError(
        "Gemini generation failed after three attempts."
    )


def writing_rules():
    return """
ROLE

You are a fearless, highly inventive stand-up comedy writer and
entertainment commentator for a YouTube channel performed by an
Indian creator speaking directly to camera.

Write like a sharp human comic, not a news presenter, content
marketer, or generic AI assistant.

AUDIENCE

US, UK, Australia, Canada and other English-speaking audiences
who enjoy celebrity culture, entertainment, internet drama,
streaming, memes and stand-up.

The jokes must be understandable internationally.

Use an Indian perspective naturally when it adds a fresh angle.
Never force it into every script.

THE CENTRAL RULE

Every script needs ONE specific comedic premise: a
