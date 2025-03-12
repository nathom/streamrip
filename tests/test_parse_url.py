import unittest
from unittest.mock import AsyncMock, patch

from streamrip.rip.parse_url import (
    DeezerDynamicURL,
    GenericURL,
    SoundcloudURL,
    parse_url,
)


class TestParseURL(unittest.TestCase):
    def test_deezer_dynamic_url(self):
        """Test that Deezer dynamic URLs are matched correctly."""
        url = "https://dzr.page.link/SnV6hCyHihkmCCwUA"
        result = parse_url(url)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, DeezerDynamicURL)
        self.assertEqual(result.source, "deezer")

    def test_qobuz_album_url(self):
        """Test that Qobuz album URLs are matched correctly."""
        url = "https://www.qobuz.com/fr-fr/album/bizarre-ride-ii-the-pharcyde-the-pharcyde/0066991040005"
        result = parse_url(url)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, GenericURL)
        self.assertEqual(result.source, "qobuz")

        # Verify the regex match groups
        groups = result.match.groups()
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0], "qobuz")  # source
        self.assertEqual(groups[1], "album")  # media_type
        self.assertEqual(groups[2], "0066991040005")  # item_id

    def test_tidal_track_url(self):
        """Test that Tidal track URLs are matched correctly."""
        url = "https://tidal.com/browse/track/3083287"
        result = parse_url(url)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, GenericURL)
        self.assertEqual(result.source, "tidal")

        # Verify the regex match groups
        groups = result.match.groups()
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0], "tidal")  # source
        self.assertEqual(groups[1], "track")  # media_type
        self.assertEqual(groups[2], "3083287")  # item_id

    def test_deezer_track_url(self):
        """Test that Deezer track URLs are matched correctly."""
        url = "https://www.deezer.com/track/4195713"
        result = parse_url(url)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, GenericURL)
        self.assertEqual(result.source, "deezer")

        # Verify the regex match groups
        groups = result.match.groups()
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0], "deezer")  # source
        self.assertEqual(groups[1], "track")  # media_type
        self.assertEqual(groups[2], "4195713")  # item_id

    def test_invalid_url(self):
        """Test that invalid URLs return None."""
        urls = [
            "https://example.com",
            "not a url",
            "https://spotify.com/track/123456",  # Unsupported source
            "https://tidal.com/invalid/3083287",  # Invalid media type
        ]

        for url in urls:
            result = parse_url(url)
            self.assertIsNone(result, f"URL should not parse: {url}")

    def test_alternate_url_formats(self):
        """Test various URL formats that should be valid."""
        # Test with different domain prefixes
        url1 = "https://open.tidal.com/track/3083287"
        url2 = "https://play.qobuz.com/album/0066991040005"
        url3 = "https://listen.tidal.com/track/3083287"

        for url in [url1, url2, url3]:
            result = parse_url(url)
            self.assertIsNotNone(result, f"Should parse URL: {url}")
            self.assertIsInstance(result, GenericURL)

    def test_url_with_language_code(self):
        """Test URLs with different language codes."""
        urls = [
            "https://www.qobuz.com/us-en/album/name/id123456",
            "https://www.qobuz.com/gb-en/album/name/id123456",
            "https://www.deezer.com/en/track/4195713",
            "https://www.deezer.com/fr/track/4195713",
        ]

        for url in urls:
            result = parse_url(url)
            self.assertIsNotNone(result, f"Should parse URL: {url}")
            self.assertIsInstance(result, GenericURL)

    def test_soundcloud_url(self):
        """Test that Soundcloud URLs are matched correctly."""
        urls = [
            "https://soundcloud.com/artist-name/track-name",
            "https://soundcloud.com/artist-name/sets/playlist-name",
        ]

        for url in urls:
            result = parse_url(url)
            self.assertIsNotNone(result, f"Should parse URL: {url}")
            self.assertIsInstance(result, SoundcloudURL)
            self.assertEqual(result.source, "soundcloud")


class TestDeezerDynamicURL(unittest.TestCase):
    @patch("streamrip.rip.parse_url.DeezerDynamicURL._extract_info_from_dynamic_link")
    def test_into_pending_album(self, mock_extract):
        """Test conversion of Deezer dynamic URL to a PendingAlbum."""
        import asyncio

        async def run_test():
            url = "https://dzr.page.link/SnV6hCyHihkmCCwUA"
            result = parse_url(url)

            # Mock the extract method to return album type and ID
            mock_extract.return_value = ("album", "12345")

            # Mock the client, config, db
            mock_client = AsyncMock()
            mock_client.source = "deezer"
            mock_config = AsyncMock()
            mock_db = AsyncMock()

            # Call into_pending
            pending = await result.into_pending(mock_client, mock_config, mock_db)

            # Verify the correct pending type was created
            self.assertEqual(pending.__class__.__name__, "PendingAlbum")
            self.assertEqual(pending.id, "12345")

        # Run the coroutine
        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()

