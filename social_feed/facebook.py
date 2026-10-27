"""Best-effort extraction of posts already exposed on public Facebook pages."""

import json
import re
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse, urlunparse

from social_feed.models import Publication, https_url


def validate_facebook(source: dict) -> None:
    url = urlparse(https_url(source["url"]))
    if (
        url.hostname != "www.facebook.com"
        or url.port is not None
        or url.query
        or url.fragment
        or not re.fullmatch(r"/[A-Za-z0-9.]+/?", url.path)
    ):
        raise ValueError("Facebook subscriptions require a public https://www.facebook.com/PageName/ URL.")


def render_public_page(url: str) -> str:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(locale="en-US", accept_downloads=False)
            page = context.new_page()
            page.route(
                "**/*",
                lambda route: route.abort() if route.request.resource_type in
                ("image", "media", "font") else route.continue_(),
            )
            response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if response is None or response.status >= 400:
                status = response.status if response else "no response"
                raise RuntimeError(f"Facebook public page unavailable: HTTP {status}.")
            if urlparse(page.url).path.startswith(("/login", "/checkpoint", "/challenge")):
                raise RuntimeError("Facebook requires authentication or a challenge; no bypass attempted.")
            try:
                page.wait_for_function(
                    """() => [...document.querySelectorAll('script[type="application/json"]')]
                      .some(script => script.textContent.includes('"creation_time":')
                        && script.textContent.includes('"post_id":'))""",
                    timeout=20000,
                )
            except PlaywrightTimeoutError as error:
                raise RuntimeError(
                    "Facebook exposed no dated public posts. Login, access restrictions, "
                    "or a changed page format may prevent scraping; no bypass attempted."
                ) from error
            # Only scroll the public page; never dismiss login or consent barriers.
            previous_count = 0
            for _ in range(3):
                count = page.evaluate(
                    """() => [...document.querySelectorAll('script[type="application/json"]')]
                      .reduce((n, script) => n + (script.textContent.match(/"creation_time":/g) || []).length, 0)"""
                )
                page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                page.wait_for_timeout(1500)
                if count == previous_count:
                    break
                previous_count = count
            html = page.content()
            if len(html.encode("utf-8")) > 10 * 1024 * 1024:
                raise ValueError("Rendered Facebook page exceeds the 10 MiB limit.")
            return html
        finally:
            browser.close()


class PublicPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.page_id: str | None = None
        self.json_scripts: list[str] = []
        self._capture = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("property") == "al:android:url":
            match = re.fullmatch(r"fb://profile/(\d+)", attributes.get("content") or "")
            if match:
                self.page_id = match.group(1)
        if tag == "script":
            self._capture = attributes.get("type") == "application/json"
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capture:
            self.json_scripts.append("".join(self._parts))
            self._capture = False


def objects(value: object) -> Iterator[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def facebook(source: dict, render: Callable[[str], str] = render_public_page) -> list[Publication]:
    validate_facebook(source)
    parser = PublicPageParser()
    parser.feed(render(source["url"]))
    if not parser.page_id:
        raise ValueError("Facebook did not expose a public page identity.")

    publications = {}
    for script in parser.json_scripts:
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            # Facebook also emits non-feed bootstrap payloads; none are evaluated.
            continue
        for story in objects(payload):
            if story.get("__typename") != "Story" or not story.get("post_id"):
                continue
            actors = story.get("actors") or []
            if not any(actor.get("id") == parser.page_id for actor in actors):
                continue
            timestamp = story.get("creation_time")
            if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp <= 0:
                continue
            post_id = str(story["post_id"])
            if not post_id.isascii() or not post_id.isdecimal():
                raise ValueError("Facebook exposed an invalid post ID.")
            content = (story.get("comet_sections") or {}).get("content") or {}
            content_story = content.get("story") or story
            message = (content_story.get("message") or {}).get("text") or ""
            if not isinstance(message, str):
                raise ValueError("Facebook exposed an invalid post message.")
            excerpt = message.strip()[:240]
            title = message.strip().split("\n", 1)[0][:120] or f"Publication de {source['name']}"
            url = story.get("permalink_url") or f"https://www.facebook.com/{parser.page_id}/posts/{post_id}/"
            parsed_url = urlparse(https_url(url))
            if parsed_url.hostname != "www.facebook.com":
                raise ValueError("Facebook exposed a permalink outside facebook.com.")
            url = urlunparse(parsed_url._replace(query="", fragment=""))
            published = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
            image_url = None
            for attachment in story.get("attachments") or []:
                media = ((attachment.get("styles") or {}).get("attachment") or {}).get("media") or {}
                image_url = (
                    media.get("thumbnailImage") or media.get("image") or media.get("photo_image") or {}
                ).get("uri")
                if image_url:
                    break
            publication = Publication(
                id=f"facebook:{parser.page_id}:{post_id}",
                title=title,
                url=url,
                published_at=published,
                # The public payload has no reliable edit timestamp.
                updated_at=published,
                description=excerpt,
                image_url=image_url,
                source_id=source["id"],
                source_name=source["name"],
                platform="facebook",
            )
            publications[publication.id] = publication
    if not publications:
        raise ValueError(
            "Facebook exposed no dated posts from this page. "
            "Access may be restricted or the public HTML format may have changed."
        )
    return list(publications.values())
