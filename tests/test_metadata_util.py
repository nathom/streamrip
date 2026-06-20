import pytest

from streamrip.metadata.util import get_album_track_ids, get_quality_id, safe_get, typed


class TestGetAlbumTrackIds:
    def test_qobuz_extracts_from_items(self):
        resp = {"tracks": {"items": [{"id": "a"}, {"id": "b"}]}}
        assert get_album_track_ids("qobuz", resp) == ["a", "b"]

    def test_non_qobuz_direct_list(self):
        resp = {"tracks": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}
        assert get_album_track_ids("deezer", resp) == ["1", "2", "3"]
        assert get_album_track_ids("tidal", resp) == ["1", "2", "3"]

    def test_empty_tracklist(self):
        resp = {"tracks": []}
        assert get_album_track_ids("deezer", resp) == []


class TestSafeGet:
    def test_shallow_key(self):
        assert safe_get({"a": 1}, "a") == 1

    def test_nested_keys(self):
        d = {"a": {"b": {"c": 42}}}
        assert safe_get(d, "a", "b", "c") == 42

    def test_missing_key_returns_default(self):
        assert safe_get({"a": 1}, "b") is None
        assert safe_get({"a": 1}, "b", default="x") == "x"

    def test_missing_nested_key(self):
        assert safe_get({"a": {}}, "a", "b") is None

    def test_non_dict_intermediate(self):
        assert safe_get({"a": 99}, "a", "b") is None


class TestTyped:
    def test_correct_type(self):
        assert typed("hello", str) == "hello"
        assert typed(42, int) == 42

    def test_wrong_type_raises(self):
        with pytest.raises(AssertionError):
            typed("hello", int)


class TestGetQualityId:
    def test_none_bit_depth_returns_1(self):
        assert get_quality_id(None, 44100) == 1

    def test_none_sampling_rate_returns_1(self):
        assert get_quality_id(16, None) == 1

    def test_both_none_returns_1(self):
        assert get_quality_id(None, None) == 1

    def test_16bit_returns_2(self):
        assert get_quality_id(16, 44100) == 2

    def test_24bit_96khz_returns_3(self):
        assert get_quality_id(24, 96) == 3

    def test_24bit_48khz_returns_3(self):
        assert get_quality_id(24, 48) == 3

    def test_24bit_192khz_returns_4(self):
        assert get_quality_id(24, 192) == 4

    def test_24bit_176khz_returns_4(self):
        assert get_quality_id(24, 176.4) == 4

    def test_invalid_bit_depth_raises(self):
        with pytest.raises(Exception, match="bit_depth"):
            get_quality_id(32, 96)
