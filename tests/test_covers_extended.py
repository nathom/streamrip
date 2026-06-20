import pytest

from streamrip.metadata.covers import Covers


class TestCoversIndexOf:
    def test_invalid_size_raises(self):
        with pytest.raises(Exception, match="Invalid"):
            Covers._indexof("xxlarge")


class TestCoversSetLargestPath:
    def test_sets_path_on_largest_url(self):
        c = Covers()
        c.set_cover_url("large", "http://example.com/cover.jpg")
        c.set_largest_path("/tmp/cover.jpg")
        assert c._covers[1] == ("large", "http://example.com/cover.jpg", "/tmp/cover.jpg")

    def test_raises_when_no_url(self):
        c = Covers()
        with pytest.raises(Exception):
            c.set_largest_path("/tmp/cover.jpg")


class TestCoversSetPath:
    def test_set_path_preserves_url(self):
        c = Covers()
        c.set_cover_url("small", "http://example.com/small.jpg")
        c.set_path("small", "/tmp/small.jpg")
        assert c._covers[2] == ("small", "http://example.com/small.jpg", "/tmp/small.jpg")


class TestCoversFromDeezer:
    def test_from_deezer(self):
        resp = {
            "cover_xl": "http://xl.jpg",
            "cover_big": "http://big.jpg",
            "cover_medium": "http://med.jpg",
            "cover_small": "http://small.jpg",
        }
        c = Covers.from_deezer(resp)
        assert c._covers[0] == ("original", "http://xl.jpg", None)
        assert c._covers[1] == ("large", "http://big.jpg", None)
        assert c._covers[2] == ("small", "http://med.jpg", None)
        assert c._covers[3] == ("thumbnail", "http://small.jpg", None)


class TestCoversFromSoundcloud:
    def test_from_soundcloud_artwork_url(self):
        resp = {"artwork_url": "http://sc.com/large.jpg", "user": {}}
        c = Covers.from_soundcloud(resp)
        assert c.largest()[1] == "http://sc.com/t500x500.jpg"

    def test_from_soundcloud_fallback_avatar(self):
        resp = {"artwork_url": None, "user": {"avatar_url": "http://sc.com/large.jpg"}}
        c = Covers.from_soundcloud(resp)
        assert c.largest()[1] == "http://sc.com/t500x500.jpg"


class TestCoversFromTidal:
    def test_from_tidal(self):
        uuid = "12345678-1234-1234-1234-123456789012"
        resp = {"cover": uuid}
        c = Covers.from_tidal(resp)
        assert c is not None
        url = c.largest()[1]
        assert uuid.replace("-", "/") in url

    def test_from_tidal_no_cover(self):
        c = Covers.from_tidal({"cover": None})
        assert c is None

    def test_from_tidal_empty_cover(self):
        c = Covers.from_tidal({"cover": ""})
        assert c is None


class TestCoversFromQobuz:
    def test_from_qobuz(self):
        resp = {
            "image": {
                "large": "http://qobuz.com/cover600.jpg",
                "small": "http://qobuz.com/small.jpg",
                "thumbnail": "http://qobuz.com/thumb.jpg",
            }
        }
        c = Covers.from_qobuz(resp)
        # original is derived from large by replacing last "600" with "org"
        assert "org" in c._covers[0][1]
        assert c._covers[1][1] == "http://qobuz.com/cover600.jpg"


class TestGetTidalCoverUrl:
    def test_valid_size(self):
        url = Covers._get_tidal_cover_url("ab-cd-ef", 640)
        assert "ab/cd/ef" in url
        assert "640x640" in url

    def test_invalid_size_raises(self):
        with pytest.raises(AssertionError):
            Covers._get_tidal_cover_url("ab-cd", 999)
