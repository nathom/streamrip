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


class TestDeezerFavoriteURL(unittest.TestCase):
    def test_from_str_matches(self):
        from streamrip.rip.parse_url import DeezerFavoriteURL

        url = "https://www.deezer.com/fr/profile/123456789/loved"
        result = DeezerFavoriteURL.from_str(url)
        self.assertIsNotNone(result)
        self.assertEqual(result.source, "deezer")

    def test_from_str_no_match(self):
        from streamrip.rip.parse_url import DeezerFavoriteURL

        self.assertIsNone(DeezerFavoriteURL.from_str("https://www.deezer.com/fr/album/123"))

    def test_into_pending_creates_playlist(self):
        import asyncio

        from streamrip.rip.parse_url import DeezerFavoriteURL

        async def run():
            url = "https://www.deezer.com/fr/profile/123456789/loved"
            result = DeezerFavoriteURL.from_str(url)
            pending = await result.into_pending(AsyncMock(), AsyncMock(), AsyncMock())
            self.assertEqual(pending.__class__.__name__, "PendingPlaylist")
            self.assertEqual(pending.id, "favorites:123456789")

        asyncio.run(run())


class TestQobuzInterpreterURL(unittest.TestCase):
    def test_from_str_matches(self):
        from streamrip.rip.parse_url import QobuzInterpreterURL

        url = "https://www.qobuz.com/us-en/interpreter/pink-floyd/1234567"
        result = QobuzInterpreterURL.from_str(url)
        self.assertIsNotNone(result)
        self.assertEqual(result.source, "qobuz")

    def test_from_str_no_match(self):
        from streamrip.rip.parse_url import QobuzInterpreterURL

        self.assertIsNone(QobuzInterpreterURL.from_str("https://www.qobuz.com/fr-fr/album/test/123"))

    def test_into_pending_with_digit_id(self):
        import asyncio

        from streamrip.rip.parse_url import QobuzInterpreterURL

        async def run():
            url = "https://www.qobuz.com/us-en/interpreter/pink-floyd/1234567"
            result = QobuzInterpreterURL.from_str(url)
            mock_client = AsyncMock()
            mock_client.source = "qobuz"
            pending = await result.into_pending(mock_client, AsyncMock(), AsyncMock())
            self.assertEqual(pending.__class__.__name__, "PendingArtist")
            self.assertEqual(pending.id, "1234567")

        asyncio.run(run())


class TestPendingFromType(unittest.TestCase):
    def test_invalid_type_raises(self):
        from streamrip.rip.parse_url import _pending_from_type

        with self.assertRaises(NotImplementedError):
            _pending_from_type("video", "123", AsyncMock(), AsyncMock(), AsyncMock())

    def test_valid_types(self):
        from streamrip.rip.parse_url import _pending_from_type

        for media_type in ("track", "album", "playlist", "artist", "label"):
            pending = _pending_from_type(media_type, "42", AsyncMock(), AsyncMock(), AsyncMock())
            self.assertIsNotNone(pending)


class TestParseUrlFavoriteAndInterpreter(unittest.TestCase):
    def test_favorite_url_parsed(self):
        from streamrip.rip.parse_url import DeezerFavoriteURL

        result = parse_url("https://www.deezer.com/fr/profile/123/loved")
        self.assertIsInstance(result, DeezerFavoriteURL)

    def test_interpreter_url_fallback_to_generic(self):
        # /interpreter/artist/ID — "artist" is a valid GenericURL media type, so GenericURL wins
        result = parse_url("https://www.qobuz.com/us-en/interpreter/artist/9876543")
        self.assertIsInstance(result, GenericURL)
        self.assertEqual(result.match.group(2), "artist")

    def test_interpreter_url_no_known_media_type_uses_interpreter_class(self):
        from streamrip.rip.parse_url import QobuzInterpreterURL

        # Path doesn't contain a known media-type word → GenericURL returns None
        url = "https://www.qobuz.com/us-en/interpreter/pink-floyd/download-streaming-albums"
        result = parse_url(url)
        self.assertIsInstance(result, QobuzInterpreterURL)


if __name__ == "__main__":
    unittest.main()
