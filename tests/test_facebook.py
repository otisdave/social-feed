import json
import unittest

from social_feed.facebook import facebook, validate_facebook

SOURCE = {
    "id": "guild-wars", "name": "Guild Wars", "platform": "facebook",
    "url": "https://www.facebook.com/GuildWars/",
}


def story(**changes):
    return {
        "__typename": "Story",
        "post_id": "123456789",
        "creation_time": 1793037665,
        "actors": [{"id": "100069958479615", "name": "Guild Wars"}],
        "permalink_url": "https://www.facebook.com/reel/123456789/?tracking=remove",
        "comet_sections": {"content": {"story": {
            "message": {"text": "A public announcement\nAdditional details."}
        }}},
        "attachments": [{"styles": {"attachment": {"media": {
            "thumbnailImage": {"uri": "https://example.com/image.jpg"}
        }}}}],
        **changes,
    }


def page(payload):
    return (
        '<html><meta property="al:android:url" content="fb://profile/100069958479615">'
        '<script type="application/json">'
        + json.dumps(payload) + "</script></html>"
    )


class FacebookTests(unittest.TestCase):
    def test_extracts_only_public_posts_from_the_requested_page(self):
        payload = {"data": [
            story(),
            story(post_id="999", actors=[{"id": "another-page"}]),
            {"__typename": "Comment", "creation_time": 1793037665, "post_id": "555"},
        ]}
        items = facebook(SOURCE, lambda url: page(payload))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "facebook:100069958479615:123456789")
        self.assertEqual(items[0].title, "A public announcement")
        self.assertEqual(items[0].description, "A public announcement\nAdditional details.")
        self.assertEqual(items[0].url, "https://www.facebook.com/reel/123456789/")
        self.assertEqual(items[0].published_at, "2026-10-26T18:01:05+00:00")
        self.assertEqual(items[0].image_url, "https://example.com/image.jpg")

    def test_deduplicates_repeated_script_payloads(self):
        self.assertEqual(len(facebook(SOURCE, lambda url: page([story(), story()]))), 1)

    def test_extracts_images_from_photo_posts(self):
        photo = story(attachments=[{"styles": {"attachment": {"media": {
            "photo_image": {"uri": "https://example.com/photo.jpg"}
        }}}}])
        self.assertEqual(facebook(SOURCE, lambda url: page([photo]))[0].image_url, "https://example.com/photo.jpg")

    def test_limits_excerpts_and_preserves_real_publication_date(self):
        item = story(comet_sections={"content": {"story": {"message": {"text": "x" * 1000}}}})
        result = facebook(SOURCE, lambda url: page(item))[0]
        self.assertEqual(len(result.description), 240)
        self.assertEqual(len(result.title), 120)
        self.assertEqual(result.updated_at, result.published_at)

    def test_never_invents_dates_or_turns_page_metadata_into_posts(self):
        for payload in [
            {}, story(creation_time=None), story(creation_time=True),
            story(creation_time="21 hours ago"), {"title": "Guild Wars", "url": SOURCE["url"]},
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                facebook(SOURCE, lambda url: page(payload))

    def test_requires_public_page_identity_and_handles_login_pages(self):
        with self.assertRaisesRegex(ValueError, "page identity"):
            facebook(SOURCE, lambda url: "<html><h1>Log in</h1></html>")
        with self.assertRaisesRegex(ValueError, "no dated posts"):
            facebook(SOURCE, lambda url: page({"login_required": True}))

    def test_photo_only_posts_have_attribution_and_stable_links(self):
        item = story(comet_sections={}, permalink_url=None, attachments=[])
        result = facebook(SOURCE, lambda url: page(item))[0]
        self.assertEqual(result.title, "Publication de Guild Wars")
        self.assertEqual(result.description, "")
        self.assertIsNone(result.image_url)
        self.assertEqual(result.url, "https://www.facebook.com/100069958479615/posts/123456789/")

    def test_rejects_non_facebook_pages_and_unsafe_post_links(self):
        for url in [
            "https://example.com/GuildWars/", "http://www.facebook.com/GuildWars/",
            "https://www.facebook.com/login/?next=GuildWars",
            "https://www.facebook.com/GuildWars/?query=ignored",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_facebook({**SOURCE, "url": url})
        with self.assertRaisesRegex(ValueError, "outside facebook.com"):
            facebook(SOURCE, lambda url: page(story(permalink_url="https://example.com/post")))


if __name__ == "__main__":
    unittest.main()
