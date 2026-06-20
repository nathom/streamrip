import pytest

from streamrip.metadata.artist import ArtistMetadata
from streamrip.metadata.label import LabelMetadata

# ---- ArtistMetadata ----

class TestArtistMetadataFromResp:
    def test_from_qobuz(self):
        resp = {"name": "Pink Floyd", "albums": {"items": [{"id": "1"}, {"id": "2"}]}}
        meta = ArtistMetadata.from_resp(resp, "qobuz")
        assert meta.name == "Pink Floyd"
        assert meta.album_ids() == ["1", "2"]

    def test_from_tidal(self):
        resp = {"name": "Radiohead", "albums": [{"id": "10"}, {"id": "20"}]}
        meta = ArtistMetadata.from_resp(resp, "tidal")
        assert meta.name == "Radiohead"
        assert meta.album_ids() == ["10", "20"]

    def test_from_deezer(self):
        resp = {"name": "Daft Punk", "albums": [{"id": "99"}]}
        meta = ArtistMetadata.from_resp(resp, "deezer")
        assert meta.name == "Daft Punk"
        assert meta.album_ids() == ["99"]

    def test_unsupported_source_raises(self):
        with pytest.raises(NotImplementedError):
            ArtistMetadata.from_resp({"name": "x", "albums": []}, "soundcloud")

    def test_empty_album_list(self):
        resp = {"name": "Solo", "albums": {"items": []}}
        meta = ArtistMetadata.from_resp(resp, "qobuz")
        assert meta.album_ids() == []


# ---- LabelMetadata ----

class TestLabelMetadataFromResp:
    def test_from_qobuz(self):
        resp = {"name": "ECM", "albums": {"items": [{"id": "a"}, {"id": "b"}]}}
        meta = LabelMetadata.from_resp(resp, "qobuz")
        assert meta.name == "ECM"
        assert meta.album_ids() == ["a", "b"]

    def test_from_tidal(self):
        resp = {"name": "Blue Note", "albums": [{"id": "100"}]}
        meta = LabelMetadata.from_resp(resp, "tidal")
        assert meta.name == "Blue Note"
        assert meta.album_ids() == ["100"]

    def test_from_deezer(self):
        resp = {"name": "Verve", "albums": [{"id": "200"}, {"id": "201"}]}
        meta = LabelMetadata.from_resp(resp, "deezer")
        assert meta.name == "Verve"
        assert meta.album_ids() == ["200", "201"]

    def test_unsupported_source_raises(self):
        with pytest.raises(NotImplementedError):
            LabelMetadata.from_resp({"name": "x", "albums": []}, "soundcloud")
