"""Exercise internal navigation and embeds without contacting social platforms."""

import argparse
import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright


def main(browser_name: str = "chromium") -> None:
    directory = Path(__file__).resolve().parents[1] / "site"
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/"
    archive = json.loads((directory / "feed.json").read_text(encoding="utf-8"))
    video = next(item for item in archive["items"] if item["platform"] == "youtube")
    facebook = {
        **video, "id": "facebook:1:2", "source_id": "test-facebook",
        "source_name": "Test Facebook", "platform": "facebook",
        "title": "<script>alert('not executable')</script>",
        "description": "First line\nSecond line", "image_url": None,
        "url": "https://www.facebook.com/reel/123456789/",
    }

    def detail_url(item):
        return base + "publication.html?" + urlencode({"source": item["source_id"], "id": item["id"]})

    try:
        with sync_playwright() as playwright:
            browser = getattr(playwright, browser_name).launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.route("https://**/*", lambda route: route.abort())
            stale_scripts = []

            def stale_asset(route):
                stale_scripts.append(route.request.url)
                route.fulfill(content_type="text/javascript", body=(
                    "throw new Error('Unversioned cached script must not be used.');"
                ))

            for name in ("app.js", "publication.js", "embeds.js"):
                page.route(base + name, stale_asset)
            feed_fixture = {
                **archive,
                "items": [video, facebook, {
                    **facebook, "id": "facebook:1:3",
                    "url": "https://www.facebook.com/Test/posts/123456789/",
                }],
            }
            page.route("**/feed.json", lambda route: route.fulfill(
                content_type="application/json", body=json.dumps(feed_fixture),
            ))
            page.goto(base)
            page.locator("#publications[aria-busy=false]").wait_for()
            assert page.locator("iframe").count() == 0
            assert page.locator(".card-playback").count() == 0
            assert page.locator(".card-official").count() == 3
            video_card = page.locator(".card").filter(has=page.locator(
                f'.card-official[href="{video["url"]}"]'
            ))
            facebook_card = page.locator(".card").filter(has=page.locator(
                f'.card-official[href="{facebook["url"]}"]'
            ))
            assert page.url == base
            assert video_card.locator(".card-image-link").is_visible()
            assert facebook_card.locator(".card-image-link").is_visible()
            assert "publication.html?" in facebook_card.locator(".card-image-link").get_attribute("href")
            for width in (375, 768, 1280):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            video_card.locator(".card-image-link").click()
            page.locator("#detail").wait_for(state="visible")
            assert page.locator("iframe").count() == 1
            page.go_back()
            page.locator("#publications[aria-busy=false]").wait_for()
            assert page.locator("iframe").count() == 0
            page.locator("#search").fill("no-such-publication-12345")
            assert page.locator("iframe").count() == 0
            assert page.locator("#empty").is_visible()
            page.unroute("**/feed.json")
            page.goto(base)
            page.locator("#publications[aria-busy=false]").wait_for()
            link = page.locator(".card h3 a").first
            assert "publication.html?" in link.get_attribute("href")
            assert link.get_attribute("target") is None
            link.click()
            page.locator("#detail").wait_for(state="visible")
            assert page.locator("#official-link").get_attribute("target") == "_blank"
            page.goto(detail_url(video))
            page.locator("#detail").wait_for(state="visible")
            assert page.locator("iframe").count() == 1
            assert page.locator("#publication-description").inner_text() == (
                video["description"] or "Aucun texte archivé pour cette publication."
            )
            iframe = page.locator("iframe")
            assert iframe.count() == 1
            assert iframe.get_attribute("src").startswith("https://www.youtube-nocookie.com/embed/")
            assert "autoplay" not in iframe.get_attribute("src")
            assert page.locator("#embed-fallback").is_visible()
            assert page.locator("#activate-embed").is_hidden()
            assert page.locator("#official-link").get_attribute("href") == video["url"]
            page.locator("#retry-embed").click()
            assert page.locator("iframe").count() == 1
            assert "Firefox" in page.locator("#embed-fallback").inner_text()
            page.locator("#close-embed").click()
            assert page.locator("iframe").count() == 0
            assert page.locator("#activate-embed").is_visible()
            page.locator("#activate-embed").click()
            assert page.locator("iframe").count() == 1
            page.go_back()
            page.go_forward()
            page.locator("#detail").wait_for(state="visible")
            assert page.locator("iframe").count() == 1

            def use_fixture(item):
                page.route("**/feed.json", lambda route: route.fulfill(
                    content_type="application/json",
                    body=json.dumps({**archive, "items": [item]}),
                ))
                page.goto(detail_url(item))
                page.locator("#publication[aria-busy=false]").wait_for()

            page.route("https://www.facebook.com/plugins/**", lambda route: route.fulfill(
                content_type="text/html", body="<!doctype html><html><body></body></html>",
            ))
            use_fixture(facebook)
            assert page.locator("#publication-title").inner_text() == facebook["title"]
            assert page.locator("#publication-description").inner_text() == facebook["description"]
            assert page.locator("#excerpt-note").is_visible()
            assert page.locator("iframe").count() == 1
            assert "/plugins/video.php?" in page.locator("iframe").get_attribute("src")
            assert page.locator("#embed-fallback").is_visible()
            assert "Firefox" in page.locator("#embed-fallback").inner_text()
            page.locator("#retry-embed").click()
            assert page.locator("iframe").count() == 1
            page.locator("#close-embed").click()
            assert page.locator("iframe").count() == 0
            assert page.locator("#publication-description").is_visible()
            assert page.locator("#official-link").is_visible()
            post = {**facebook, "url": "https://www.facebook.com/Test/posts/123456789/"}
            use_fixture(post)
            assert "/plugins/post.php?" in page.locator("iframe").get_attribute("src")
            for width in (375, 768, 1280):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.goto(base + "publication.html")
            page.locator("#publication-error").wait_for(state="visible")
            page.goto(base + "publication.html?source=missing&id=missing")
            page.locator("#publication-error").wait_for(state="visible")
            assert "introuvable" in page.locator("#publication-error").inner_text()
            use_fixture({**facebook, "url": "javascript:alert(1)"})
            assert page.locator("#publication-error").is_visible()
            assert page.locator("#detail").is_hidden()
            page.route("**/feed.json", lambda route: route.fulfill(status=503, body="Unavailable"))
            page.goto(detail_url(video))
            page.locator("#publication-error").wait_for(state="visible")
            assert "503" in page.locator("#publication-error").inner_text()
            assert not page_errors, page_errors
            assert not stale_scripts, stale_scripts
            browser.close()
        print("Image-only feed and automatic article players: navigation, no autoplay, retry/close, fallbacks, safe text, responsive layout and errors OK.")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", choices=("chromium", "firefox"), default="chromium")
    main(parser.parse_args().browser)
