import json

from streamrip.metadata import AlbumMetadata, TrackMetadata

with open("tests/qobuz_album_resp.json") as f:
    qobuz_album_resp = json.load(f)

with open("tests/qobuz_track_resp.json") as f:
    qobuz_track_resp = json.load(f)


def test_album_metadata_qobuz():
    m = AlbumMetadata.from_qobuz(qobuz_album_resp)
    info = m.info
    assert info.id == "19512572"
    assert info.quality == 3
    assert info.container == "FLAC"
    assert info.label == "Rhino - Warner Records"
    assert info.explicit is False
    assert info.sampling_rate == 96
    assert info.bit_depth == 24
    assert info.booklets is None

    assert m.album == "Rumours"
    assert m.albumartist == "Fleetwood Mac"
    assert m.year == "1977"
    assert "Pop" in m.genre
    assert "Rock" in m.genre
    assert not m.covers.empty()

    assert m.albumcomposer == "Various Composers"
    assert m.comment is None
    assert m.compilation is None
    assert (
        m.copyright
        == "© 1977 Warner Records Inc. ℗ 1977 Warner Records Inc. Marketed by Rhino Entertainment Company, A Warner Music Group Company."
    )
    assert m.date == "1977-02-04"
    assert m.description == ""
    assert m.disctotal == 1
    assert m.encoder is None
    assert m.grouping is None
    assert m.lyrics is None
    assert m.purchase_date is None
    assert m.tracktotal == 11


def test_track_metadata_qobuz():
    a = AlbumMetadata.from_qobuz(qobuz_track_resp["album"])
    t = TrackMetadata.from_qobuz(a, qobuz_track_resp)
    
    # First check that t is not None before accessing its attributes
    assert t is not None, "TrackMetadata.from_qobuz returned None"
    
    # Now we can safely access t.info
    info = t.info
    assert info is not None, "TrackMetadata.info is None"
    
    # Now we can safely access info attributes
    assert info.id == "216020864"
    assert info.quality == 3
    assert info.bit_depth == 24
    assert info.sampling_rate == 96
    assert info.work is None

    # Check other attributes safely using getattr with default values
    # This solves the typing issue while still testing the expected values
    assert getattr(t, 'title', None) == "Water Tower"
    assert getattr(t, 'album', None) == a
    assert getattr(t, 'artist', None) == "The Mountain Goats"
    assert getattr(t, 'tracknumber', None) == 9
    assert getattr(t, 'discnumber', None) == 1
    assert getattr(t, 'composer', None) == "John Darnielle"
