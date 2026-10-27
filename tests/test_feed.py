import contextlib
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from social_feed.__main__ import make_rss, merge_publications, publish, read_config
from social_feed.adapters import youtube
from social_feed.models import Publication, parse_date

SOURCE = {
    "id": "eco-en-batons", "name": "Éco en bâtons", "platform": "youtube",
    "url": "https://www.youtube.com/@Eco_en_batons",
    "channel_id": "UCJrYJevv7eUOBg857Jx_qIA",
}
CONFIG = {
    "title": "Social Feed", "description": "Le fil",
    "site_url": "https://otisdave.github.io/social-feed/", "sources": [SOURCE],
}
ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"
 xmlns:yt="http://www.youtube.com/xml/schemas/2015"
 xmlns:media="http://search.yahoo.com/mrss/">
  <yt:channelId>JrYJevv7eUOBg857Jx_qIA</yt:channelId>
  <entry>
    <yt:videoId>abcdefghijk</yt:videoId>
    <title>Title &amp; details</title>
    <published>2026-10-25T10:00:00+00:00</published>
    <updated>2026-10-26T10:00:00+00:00</updated>
    <media:group><media:description>&lt;b&gt;Plain text&lt;/b&gt;</media:description>
    <media:thumbnail url="https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg" /></media:group>
  </entry>
</feed>"""


def publication(video_id="abcdefghijk", published="2026-10-25T10:00:00+00:00", **changes):
    values = dict(
        id=f"youtube:{video_id}", title="A video", url=f"https://www.youtube.com/watch?v={video_id}",
        published_at=published, updated_at=published, description="A description",
        image_url=None, source_id=SOURCE["id"], source_name=SOURCE["name"], platform="youtube",
    )
    values.update(changes)
    return Publication(**values)


class FeedTests(unittest.TestCase):
    def test_youtube_normalizes_official_atom_feed(self):
        requested = []

        def fetch(url):
            requested.append(url)
            return ATOM

        items = youtube(SOURCE, fetch)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "youtube:abcdefghijk")
        self.assertEqual(items[0].title, "Title & details")
        self.assertEqual(items[0].description, "<b>Plain text</b>")
        self.assertEqual(items[0].source_name, SOURCE["name"])
        self.assertEqual(requested, [
            "https://www.youtube.com/feeds/videos.xml?channel_id=" + SOURCE["channel_id"]
        ])

    def test_youtube_rejects_empty_malformed_or_wrong_channel(self):
        for payload in [
            b"<html>not a feed</html>", b"<broken",
            ATOM.replace(b"JrYJevv7eUOBg857Jx_qIA", b"0000000000000000000000"),
            ATOM[:ATOM.index(b"  <entry>")] + b"</feed>",
        ]:
            with self.subTest(payload=payload), self.assertRaises((ValueError, ET.ParseError)):
                youtube(SOURCE, lambda url: payload)

    def test_youtube_also_accepts_canonical_channel_id(self):
        atom = ATOM.replace(b"JrYJevv7eUOBg857Jx_qIA", b"UCJrYJevv7eUOBg857Jx_qIA")
        self.assertEqual(len(youtube(SOURCE, lambda url: atom)), 1)

    def test_merge_sorts_by_actual_time_and_keeps_archive(self):
        old = publication("old12345678", "2026-09-01T10:00:00+00:00")
        new = publication("new12345678", "2026-10-25T09:30:00Z")
        offset = publication("off12345678", "2026-10-25T10:00:00+02:00")
        merged = merge_publications([old.to_dict()], [offset, new, new])
        self.assertEqual([item["id"] for item in merged], [new.id, offset.id, old.id])

    def test_merge_updates_metadata_without_accepting_stale_data(self):
        original = publication(updated_at="2026-10-26T10:00:00Z")
        fresh = publication(title="Updated", updated_at="2026-10-27T10:00:00Z")
        result = merge_publications([original.to_dict()], [fresh, original])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Updated")

    def test_identity_is_scoped_to_source(self):
        first = publication()
        second = publication(source_id="another-source")
        self.assertEqual(len(merge_publications([], [first, second])), 2)

    def test_publications_reject_unsafe_urls_and_naive_dates(self):
        for changes in [
            {"url": "javascript:alert(1)"}, {"image_url": "http://example.com/image.jpg"},
            {"url": "https://user:password@example.com"},
            {"published_at": "2026-10-25T10:00:00"}, {"title": " "},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                publication(**changes)
        self.assertEqual(parse_date("2026-10-25T10:00:00+02:00").hour, 8)

    def test_rss_escapes_text_and_uses_stable_guids(self):
        item = publication(title="A & B <test>", description="<script>not executable</script>")
        xml = make_rss(CONFIG, [item.to_dict()], "2026-10-27T10:00:00Z")
        root = ET.fromstring(xml)
        self.assertEqual(root.attrib["version"], "2.0")
        self.assertEqual(root.findtext("channel/item/title"), item.title)
        self.assertEqual(root.findtext("channel/item/description"), item.description)
        self.assertEqual(root.findtext("channel/item/guid"), "eco-en-batons:youtube:abcdefghijk")
        self.assertEqual(root.find("channel/item/guid").attrib["isPermaLink"], "false")
        self.assertTrue(root.findtext("channel/item/pubDate").endswith("GMT"))
        self.assertEqual(root.find("channel/{http://www.w3.org/2005/Atom}link").attrib["href"],
                         CONFIG["site_url"] + "feed.xml")
        html = root.findtext("channel/item/{http://purl.org/rss/1.0/modules/content/}encoded")
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIsNone(root.find("channel/item/enclosure"))

    def test_rss_exposes_images_to_feed_readers(self):
        image = "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg?a=1&b=2"
        xml = make_rss(CONFIG, [publication(image_url=image, description="Line 1\nLine 2").to_dict()],
                       "2026-10-27T10:00:00Z")
        item = ET.fromstring(xml).find("channel/item")
        self.assertEqual(item.find("enclosure").attrib["url"], image)
        self.assertEqual(item.find("enclosure").attrib["type"], "image/jpeg")
        self.assertEqual(item.find("{http://search.yahoo.com/mrss/}thumbnail").attrib["url"], image)
        self.assertEqual(item.find("{http://search.yahoo.com/mrss/}content").attrib["medium"], "image")
        html = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
        self.assertTrue(html.startswith('<p><img src="https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg?a=1&amp;b=2"'))
        self.assertIn("<p>Line 1</p>\n<p>Line 2</p>", html)
        self.assertIn("Voir sur YouTube", html)

    def test_provider_failure_preserves_archive_and_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.assertTrue(publish(CONFIG, path, {"youtube": lambda source: [publication()]}))
            before = json.loads((path / "feed.json").read_text(encoding="utf-8"))

            def failing(source):
                raise RuntimeError("Provider unavailable")

            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertFalse(publish(CONFIG, path, {"youtube": failing}))
            after = json.loads((path / "feed.json").read_text(encoding="utf-8"))
            self.assertEqual(before["items"], after["items"])
            self.assertEqual(after["sources"][0]["status"], "error")
            self.assertEqual(after["sources"][0]["last_success_at"], before["generated_at"])
            self.assertIn("Provider unavailable", errors.getvalue())

    def test_one_failed_source_does_not_block_healthy_sources(self):
        config = {**CONFIG, "sources": [
            SOURCE, {**SOURCE, "id": "other", "name": "Other source"}
        ]}

        def fetch(source):
            if source["id"] == SOURCE["id"]:
                raise RuntimeError("Unavailable")
            return [publication(source_id=source["id"])]

        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(publish(config, Path(directory), {"youtube": fetch}))
            data = json.loads((Path(directory) / "feed.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["items"]), 1)
            self.assertEqual([source["status"] for source in data["sources"]], ["error", "ok"])

    def test_removing_source_removes_its_publications(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            publish(CONFIG, path, {"youtube": lambda source: [publication()]})
            config = {**CONFIG, "sources": [{**SOURCE, "id": "replacement"}]}
            publish(config, path, {"youtube": lambda source: [publication(source_id="replacement")]})
            data = json.loads((path / "feed.json").read_text(encoding="utf-8"))
            self.assertEqual([item["source_id"] for item in data["items"]], ["replacement"])

    def test_invalid_archive_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            archive = path / "feed.json"
            archive.write_text('{"items": [{"invalid": true}], "sources": []}', encoding="utf-8")
            before = archive.read_bytes()
            with self.assertRaises(TypeError):
                publish(CONFIG, path, {"youtube": lambda source: [publication()]})
            self.assertEqual(archive.read_bytes(), before)

    def test_disabled_subscriptions_do_not_fetch_or_erase_existing_items(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            publish(CONFIG, path, {"youtube": lambda source: [publication()]})
            config = {**CONFIG, "sources": [{**SOURCE, "enabled": False}]}

            def unexpected_fetch(source):
                self.fail("A disabled subscription must not be fetched.")

            self.assertTrue(publish(config, path, {"youtube": unexpected_fetch}))
            data = json.loads((path / "feed.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["items"]), 1)
            self.assertEqual(data["sources"][0]["status"], "disabled")

    def test_grouped_config_accepts_pending_facebook_and_empty_reddit(self):
        source = {key: value for key, value in SOURCE.items() if key != "platform"}
        config = {key: value for key, value in CONFIG.items() if key != "sources"}
        config["subscriptions"] = {
            "youtube": [source],
            "facebook": [{"id": "guild-wars", "name": "Guild Wars",
                          "url": "https://www.facebook.com/GuildWars/", "enabled": False}],
            "reddit": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            result = read_config(path)
            self.assertEqual([source["platform"] for source in result["sources"]],
                             ["youtube", "facebook"])
            self.assertFalse(result["sources"][1]["enabled"])

    def test_config_rejects_duplicates_unknown_or_unconnected_adapters(self):
        source = {key: value for key, value in SOURCE.items() if key != "platform"}
        for subscriptions in [
            {"youtube": [source, source]},
            {"reddit": [source]},
            {"facebook": [{**source, "url": "https://example.com/not-facebook/"}]},
            {"youtube": [{**source, "channel_id": "not-a-channel"}]},
            {"youtube": [{**source, "enabled": "false"}]},
            {"youtube": [{**source, "platform": "facebook"}]},
            {"youtube": []},
            {"typo": []},
            {"youtube": {}},
        ]:
            config = {**CONFIG, "subscriptions": subscriptions}
            with self.subTest(subscriptions=subscriptions), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "sources.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_config(path)


if __name__ == "__main__":
    unittest.main()
