"""Translate upstream feeds into the common publication contract."""

import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable

from social_feed.models import Publication, https_url
from social_feed.facebook import facebook, validate_facebook

NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


def fetch_url(url: str) -> bytes:
    https_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SocialFeed/1.0 (+https://github.com/otisdave/social-feed)"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("Source response exceeds the 5 MiB limit.")
            return body
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2**attempt)
    raise RuntimeError("Fetch attempts exhausted.")


def validate_youtube(source: dict) -> None:
    if not re.fullmatch(r"UC[\w-]{22}", source.get("channel_id", ""), flags=re.ASCII):
        raise ValueError(f"Invalid YouTube channel ID for {source['id']}.")


def youtube(source: dict, fetch: Callable[[str], bytes] = fetch_url) -> list[Publication]:
    validate_youtube(source)
    root = ET.fromstring(fetch(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={source['channel_id']}"
    ))
    if root.tag != f"{{{NAMESPACES['atom']}}}feed":
        raise ValueError("YouTube returned something other than an Atom feed.")
    # YouTube's Atom channelId can omit the canonical "UC" prefix.
    if root.findtext("yt:channelId", namespaces=NAMESPACES) not in (
        source["channel_id"], source["channel_id"][2:]
    ):
        raise ValueError("YouTube returned a different channel than requested.")

    publications = []
    for entry in root.findall("atom:entry", NAMESPACES):
        video_id = entry.findtext("yt:videoId", namespaces=NAMESPACES)
        if not video_id or not re.fullmatch(r"[\w-]{11}", video_id, flags=re.ASCII):
            raise ValueError("Missing or invalid YouTube video ID.")
        published = entry.findtext("atom:published", namespaces=NAMESPACES)
        thumbnail = entry.find("media:group/media:thumbnail", NAMESPACES)
        publications.append(Publication(
            id=f"youtube:{video_id}",
            title=entry.findtext("atom:title", default="", namespaces=NAMESPACES),
            url=f"https://www.youtube.com/watch?v={video_id}",
            published_at=published or "",
            updated_at=entry.findtext("atom:updated", namespaces=NAMESPACES) or published or "",
            description=entry.findtext(
                "media:group/media:description", default="", namespaces=NAMESPACES
            ),
            image_url=thumbnail.get("url") if thumbnail is not None else None,
            source_id=source["id"],
            source_name=source["name"],
            platform="youtube",
        ))
    if not publications:
        raise ValueError("YouTube returned no videos; the existing archive was preserved.")
    return publications


ADAPTERS = {"youtube": youtube, "facebook": facebook}
VALIDATORS = {"youtube": validate_youtube, "facebook": validate_facebook}
